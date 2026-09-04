#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADB UI automation core — stdlib-only atomic device operations.

Used by:
  * ``adb_handler`` (batch-1 backend APIs: device.tap / swipe / input_text /
    keyevent / ui_dump / find_element / tap_element / current_activity)
  * the ``adb_auto`` plugin (batch 2 orchestration)

No third-party dependencies: re / time / os / uuid / xml.etree only.
UI hierarchy is dumped via ``uiautomator dump`` to a device-side temp file
(uuid-named to avoid concurrent-automation collisions), pulled locally,
parsed for node attributes + bounds center, then the temp file is removed.
"""

import os
import re
import time
import uuid
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from app.tools.tool_manager import ToolManager
from app.common.base_executor import CommandExecutionContext
from app.common.exceptions import ToolNotFoundError
from app.utils.env import get_output_dir
from app.utils.logger import Logger

logger = Logger.get_logger("AdbAutoCore")


# ----------------------------------------------------------------------
# low-level runner
# ----------------------------------------------------------------------

def run_adb(device_id: str, args: List[str], capture: bool = True) -> Dict[str, Any]:
    """Run ``adb -s <device_id> <args>`` and return the raw result dict."""
    mgr = ToolManager.instance()
    adb = mgr.get_tool("adb")
    if not adb or not getattr(adb, "is_valid", False):
        raise ToolNotFoundError("adb")
    ctx = CommandExecutionContext(capture_output=capture, log_output=False)
    return adb.execute(["-s", device_id] + list(args), ctx)


# ----------------------------------------------------------------------
# coordinate / input actions
# ----------------------------------------------------------------------

def tap(device_id: str, x: int, y: int) -> Dict[str, Any]:
    r = run_adb(device_id, ["shell", "input", "tap", str(int(x)), str(int(y))])
    return {"success": r.get("returncode", 1) == 0}


def swipe(
    device_id: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
) -> Dict[str, Any]:
    r = run_adb(
        device_id,
        ["shell", "input", "swipe", str(int(x1)), str(int(y1)),
         str(int(x2)), str(int(y2)), str(int(duration_ms))],
    )
    return {"success": r.get("returncode", 1) == 0}


def input_text(device_id: str, text: str) -> Dict[str, Any]:
    """Type text via ``input text``. Spaces become %s (adb space token).

    Non-ASCII text is usually ignored by the default IME (needs ADBKeyboard);
    we log a warning but do not abort.
    """
    if text is None:
        return {"success": False, "error": "empty text"}
    if any(ord(c) > 0x7F for c in text):
        logger.warning(
            f"input_text contains non-ASCII chars ({text!r}); default IME may "
            f"drop them — install ADBKeyboard for CJK input"
        )
    payload = text.replace(" ", "%s")
    r = run_adb(device_id, ["shell", "input", "text", payload])
    return {"success": r.get("returncode", 1) == 0}


_KEYEVENT_ALIASES = {
    "BACK": "KEYCODE_BACK",
    "HOME": "KEYCODE_HOME",
    "ENTER": "KEYCODE_ENTER",
    "MENU": "KEYCODE_MENU",
    "VOLUME_UP": "KEYCODE_VOLUME_UP",
    "VOLUME_DOWN": "KEYCODE_VOLUME_DOWN",
    "POWER": "KEYCODE_POWER",
    "DEL": "KEYCODE_DEL",
    "TAB": "KEYCODE_TAB",
}


def keyevent(device_id: str, key: str) -> Dict[str, Any]:
    if not key:
        return {"success": False, "error": "empty key"}
    token = _KEYEVENT_ALIASES.get(str(key).upper(), str(key))
    r = run_adb(device_id, ["shell", "input", "keyevent", token])
    return {"success": r.get("returncode", 1) == 0}


def back(device_id: str) -> Dict[str, Any]:
    return keyevent(device_id, "BACK")


def home(device_id: str) -> Dict[str, Any]:
    return keyevent(device_id, "HOME")


def shell(device_id: str, command: str) -> Dict[str, Any]:
    if not command:
        return {"success": False, "error": "empty command"}
    r = run_adb(device_id, ["shell", command])
    return {
        "success": r.get("returncode", 1) == 0,
        "output": r.get("stdout", ""),
        "error": r.get("stderr", ""),
    }


# ----------------------------------------------------------------------
# app-level actions
# ----------------------------------------------------------------------

def launch_app(device_id: str, package_name: str) -> Dict[str, Any]:
    if not package_name:
        return {"success": False, "error": "empty package_name"}
    r = run_adb(
        device_id,
        ["shell", "monkey", "-p", package_name,
         "-c", "android.intent.category.LAUNCHER", "1"],
    )
    return {"success": r.get("returncode", 1) == 0}


def clear_app_data(device_id: str, package_name: str) -> Dict[str, Any]:
    if not package_name:
        return {"success": False, "error": "empty package_name"}
    r = run_adb(device_id, ["shell", "pm", "clear", package_name])
    stdout = (r.get("stdout", "") or "").strip()
    ok = r.get("returncode", 1) == 0 and "Success" in stdout
    return {"success": ok, "error": "" if ok else (stdout or r.get("stderr", ""))}


# ----------------------------------------------------------------------
# UI hierarchy
# ----------------------------------------------------------------------

_BY_ATTR = {
    "text": "text",
    "resource_id": "resource-id",
    "resource-id": "resource-id",
    "content_desc": "content-desc",
    "content-desc": "content-desc",
    "class": "class",
}


def _center(bounds: Tuple[int, int, int, int]) -> Tuple[int, int]:
    x1, y1, x2, y2 = bounds
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def _parse_bounds(node: ET.Element) -> Optional[Tuple[int, int, int, int]]:
    b = node.get("bounds")
    if not b:
        return None
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))


def ui_dump(
    device_id: str, timeout_ms: int = 8000, retries: int = 1
) -> Tuple[bool, str]:
    """Dump active UI hierarchy to a local XML string.

    Returns ``(ok, xml_or_error)``. Dumps to a uuid-named device temp file,
    pulls to a uuid-named local file, then removes both. Retries ``retries``
    extra times on failure (plan: retry once).
    """
    remote = f"/sdcard/blank_tool_ui_{uuid.uuid4().hex}.xml"
    local = os.path.join(get_output_dir(), "ui", f"ui_{uuid.uuid4().hex}.xml")
    os.makedirs(os.path.dirname(local), exist_ok=True)

    last_err = "ui dump failed"
    attempts = max(1, retries + 1)
    for _ in range(attempts):
        cap = run_adb(device_id, ["shell", "uiautomator", "dump",
                                  "--compressed", remote])
        if cap.get("returncode", 1) != 0:
            last_err = cap.get("stderr", "") or cap.get("stdout", "") or last_err
            continue
        pull = run_adb(device_id, ["pull", remote, local])
        if pull.get("returncode", 1) != 0:
            last_err = pull.get("stderr", "") or last_err
            continue
        try:
            with open(local, "r", encoding="utf-8", errors="ignore") as f:
                xml_text = f.read()
            if xml_text.strip():
                return True, xml_text
            last_err = "empty ui xml"
        except OSError as e:
            last_err = str(e)
        finally:
            try:
                os.remove(local)
            except OSError:
                pass
        # best-effort device temp cleanup
        run_adb(device_id, ["shell", "rm", "-f", remote])
        if time.time() + timeout_ms / 1000.0 < 0:  # safety no-op
            break

    try:
        run_adb(device_id, ["shell", "rm", "-f", remote])
    except Exception:
        pass
    return False, last_err


def find_element(
    device_id: str, by: str, value: str, timeout_ms: int = 10000
) -> Dict[str, Any]:
    """Poll the UI hierarchy until ``by=value`` matches (substring) or timeout.

    Returns ``{"found": bool, "node": {...} | None, "error": str}``. Never
    raises on "not found" — the caller decides abort vs continue.
    """
    attr = _BY_ATTR.get(by)
    if not attr:
        return {"found": False, "node": None, "error": f"unsupported by: {by}"}
    if value is None:
        return {"found": False, "node": None, "error": "empty value"}

    deadline = time.time() + timeout_ms / 1000.0
    last_err = ""
    while True:
        ok, xml_text = ui_dump(device_id, timeout_ms=2000)
        if ok:
            try:
                root = ET.fromstring(xml_text)
                for node in root.iter("node"):
                    v = node.get(attr)
                    if v and value in v:
                        b = _parse_bounds(node)
                        if b:
                            return {
                                "found": True,
                                "node": {
                                    "bounds": node.get("bounds"),
                                    "text": node.get("text"),
                                    "resource_id": node.get("resource-id"),
                                    "content_desc": node.get("content-desc"),
                                    "class": node.get("class"),
                                    "center": list(_center(b)),
                                },
                                "error": "",
                            }
            except ET.ParseError as e:
                last_err = f"ui xml parse error: {e}"
        if time.time() > deadline:
            break
        time.sleep(1)
    return {"found": False, "node": None, "error": last_err}


def tap_element(
    device_id: str, by: str, value: str, timeout_ms: int = 10000
) -> Dict[str, Any]:
    """Find an element then tap its center. Returns success + node."""
    res = find_element(device_id, by, value, timeout_ms=timeout_ms)
    if not res.get("found"):
        return {"success": False, "node": None,
                "error": res.get("error") or "element not found"}
    cx, cy = res["node"]["center"]
    r = tap(device_id, cx, cy)
    return {"success": r.get("success", False), "node": res["node"], "error": ""}


# ----------------------------------------------------------------------
# activity / screenshot
# ----------------------------------------------------------------------

def current_activity(device_id: str, timeout_ms: int = 3000) -> Dict[str, Any]:
    """Get the resumed activity via ``dumpsys activity activities``."""
    r = run_adb(device_id, ["shell", "dumpsys", "activity", "activities"])
    out = (r.get("stdout", "") or r.get("stderr", ""))
    m = re.search(r"mResumedActivity.*?(\S+/\S+)", out)
    if m:
        activity = m.group(1).split(" ")[0]
        return {"success": True, "activity": activity, "error": ""}
    return {"success": False, "activity": "",
            "error": "mResumedActivity not found"}


def take_screenshot(device_id: str, name: str = "") -> Dict[str, Any]:
    """Capture screen to ``output/screenshots/<name|uuid>.png``; return path."""
    ts = time.strftime("%Y%m%d-%H%M%S")
    suffix = f"-{name}" if name else ""
    screenshots_dir = os.path.join(get_output_dir(), "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)
    file_path = os.path.join(
        screenshots_dir, f"auto-{ts}{suffix}-{uuid.uuid4().hex[:6]}.png"
    )
    remote = "/sdcard/blank_tool_auto_shot.png"
    cap = run_adb(device_id, ["shell", "screencap", "-p", remote])
    if cap.get("returncode", 1) != 0:
        return {"success": False, "file_path": "",
                "error": cap.get("stderr", "screencap failed")}
    pull = run_adb(device_id, ["pull", remote, file_path])
    run_adb(device_id, ["shell", "rm", "-f", remote])
    if pull.get("returncode", 1) != 0:
        return {"success": False, "file_path": "",
                "error": pull.get("stderr", "pull failed")}
    return {"success": True, "file_path": file_path, "error": ""}
