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

import base64
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

def get_display_transform(device_id: str) -> Dict[str, Any]:
    """Query the current surface rotation and natural (panel) size.

    Recorded scripts store touch-panel RAW coordinates (getevent native
    orientation, e.g. 900x1600 portrait) while ``input tap`` expects
    DISPLAY coordinates for the CURRENT rotation (e.g. 1600x900 landscape
    when a game forces landscape). Map one to the other with
    ``rotate_to_display``.

    Returns ``{"rotation": 0..3, "width": int, "height": int}`` where
    width/height are the natural (unrotated) dimensions.
    """
    rotation = 0
    width = height = 0
    try:
        r = run_adb(device_id, ["shell", "dumpsys", "input"])
        for line in (r.get("stdout") or "").splitlines():
            if "SurfaceOrientation" in line:
                try:
                    rotation = int(line.split(":", 1)[1].strip() or 0) % 4
                except ValueError:
                    rotation = 0
                break
        r2 = run_adb(device_id, ["shell", "wm", "size"])
        for line in (r2.get("stdout") or "").splitlines():
            if "Physical size" in line:
                part = line.split("Physical size:", 1)[1].strip().split()[0]
                try:
                    width, height = (int(v) for v in part.lower().split("x"))
                except ValueError:
                    width = height = 0
                break
    except Exception as e:  # defensive: never crash a run over metadata
        logger.warning(f"get_display_transform failed: {e}")
    return {"rotation": rotation, "width": width, "height": height}


def rotate_to_display(
    x: int, y: int, rotation: int, panel_w: int, panel_h: int
) -> Tuple[int, int]:
    """Map panel-native raw coords to display coords for ``input tap``."""
    x, y = int(x), int(y)
    if rotation == 1:
        return y, panel_w - x
    if rotation == 2:
        return panel_w - x, panel_h - y
    if rotation == 3:
        return panel_h - y, x
    return x, y


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
    """Type text into the currently FOCUSED editor.

    Two paths:
    - ASCII: ``input text`` with device-shell-safe quoting. adb forwards
      shell args through the device shell, so spaces/quotes/metachars must
      be escaped or the command breaks silently.
    - Non-ASCII (CJK etc.): ``input text`` silently DROPS non-ASCII on
      virtually every ROM, so route through ADBKeyboard
      (com.android.adbkeyboard) broadcast instead. The IME is enabled and
      switched automatically; ``restore_ime`` puts the original back.

    The text lands in whatever editor has input focus — pair an `input`
    step with a preceding `tap` on the field (or set by/value so the step
    taps it first).
    """
    if text is None or text == "":
        return {"success": False, "error": "empty text"}
    if any(ord(c) > 0x7F for c in text):
        ok, err = ensure_adb_ime(device_id)
        if not ok:
            return {
                "success": False,
                "error": (
                    "non-ASCII input requires ADBKeyboard ({err}); install "
                    "ADBKeyBoard.apk from github.com/senzhk/ADBKeyBoard"
                ).format(err=err),
            }
        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        r = run_adb(
            device_id,
            ["shell", "am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "text", b64],
        )
        if r.get("returncode", 1) != 0:
            return {"success": False, "error": "ADBKeyboard broadcast failed"}
        return {"success": True}
    # Single-quote the payload for the device shell (embedded quotes doubled
    # via the classic '\'' dance). This makes spaces and shell metachars
    # literal — no %s hack needed.
    payload = "'" + text.replace("'", "'\\''") + "'"
    r = run_adb(device_id, ["shell", "input", "text", payload])
    return {"success": r.get("returncode", 1) == 0}


# ----------------------------------------------------------------------
# ADBKeyboard IME management (for non-ASCII input)
# ----------------------------------------------------------------------

ADB_IME_PKG = "com.android.adbkeyboard"
ADB_IME_ID = "com.android.adbkeyboard/.AdbIME"
# device_id -> original default IME while ADBKeyboard is switched in
_IME_ORIGINAL: Dict[str, Optional[str]] = {}


def adb_ime_installed(device_id: str) -> bool:
    r = run_adb(device_id, ["shell", "pm", "list", "packages", ADB_IME_PKG])
    return ADB_IME_PKG in (r.get("stdout") or "")


def ensure_adb_ime(device_id: str) -> Tuple[bool, str]:
    """Switch the default IME to ADBKeyboard (remembering the original).

    Idempotent within a run: once switched, later ``input_text`` calls are
    no-ops. The caller should ``restore_ime`` when the run finishes.
    """
    if device_id in _IME_ORIGINAL:
        return True, ""
    cur = _current_ime(device_id)
    if cur == ADB_IME_ID:
        # Already active (user set it manually) — nothing to restore.
        _IME_ORIGINAL[device_id] = None
        return True, ""
    if not adb_ime_installed(device_id):
        return False, "not installed"
    if run_adb(device_id, ["shell", "ime", "enable", ADB_IME_ID]).get("returncode", 1) != 0:
        return False, "ime enable failed"
    if run_adb(device_id, ["shell", "ime", "set", ADB_IME_ID]).get("returncode", 1) != 0:
        return False, "ime set failed"
    _IME_ORIGINAL[device_id] = cur
    logger.info(f"IME switched to ADBKeyboard (was {cur!r}) for {device_id}")
    return True, ""


def restore_ime(device_id: str) -> None:
    """Restore the original default IME after a run switched it."""
    orig = _IME_ORIGINAL.pop(device_id, None)
    if orig:
        run_adb(device_id, ["shell", "ime", "set", orig])
        logger.info(f"IME restored to {orig!r} for {device_id}")


def _current_ime(device_id: str) -> str:
    r = run_adb(device_id, ["shell", "settings", "get", "secure", "default_input_method"])
    return (r.get("stdout") or "").strip()


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
    device_id: str, by: str, value: str, timeout_ms: int = 10000, instance: int = 0
) -> Dict[str, Any]:
    """Poll the UI hierarchy until the ``instance``-th ``by=value`` match
    (substring, document order) appears, or timeout.

    ``instance`` picks among multiple same-selector matches (0-based,
    default 0 = first, which preserves the legacy behaviour). Returns
    ``{"found": bool, "node": {...} | None, "error": str}``. Never raises
    on "not found" — the caller decides abort vs continue.
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
                matches = []
                for node in root.iter("node"):
                    v = node.get(attr)
                    if v and value in v:
                        if _parse_bounds(node):
                            matches.append(node)
                if len(matches) > instance:
                    node = matches[instance]
                    b = _parse_bounds(node)
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
    device_id: str, by: str, value: str, timeout_ms: int = 10000, instance: int = 0
) -> Dict[str, Any]:
    """Find an element then tap its center. Returns success + node."""
    res = find_element(device_id, by, value, timeout_ms=timeout_ms, instance=instance)
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
