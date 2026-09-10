#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI hierarchy dump / element lookup (uiautomator based).

UI hierarchy is dumped via ``uiautomator dump`` to a device-side temp file
(uuid-named to avoid concurrent-automation collisions), pulled locally,
parsed for node attributes + bounds center, then the temp file is removed.
"""

import os
import re
import time
import uuid
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional, Tuple

from app.automation.adb import run_adb
from app.utils.env import get_output_dir

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
    device_id: str, by: str, value: str, timeout_ms: int = 10000, instance: int = 0,
    cancel_check: Optional[Any] = None,
) -> Dict[str, Any]:
    """Poll the UI hierarchy until the ``instance``-th ``by=value`` match
    (substring, document order) appears, or timeout.

    ``instance`` picks among multiple same-selector matches (0-based,
    default 0 = first, which preserves the legacy behaviour).
    ``cancel_check`` (optional callable) is probed between polls so a user
    Stop takes effect within ~100ms instead of at timeout. Returns
    ``{"found": bool, "node": {...} | None, "error": str, "cancelled": bool}``.
    Never raises on "not found" — the caller decides abort vs continue.
    """
    attr = _BY_ATTR.get(by)
    if not attr:
        return {"found": False, "node": None, "error": f"unsupported by: {by}"}
    if value is None:
        return {"found": False, "node": None, "error": "empty value"}

    deadline = time.time() + timeout_ms / 1000.0
    last_err = ""
    while True:
        if cancel_check is not None and cancel_check():
            return {"found": False, "node": None, "error": "cancelled",
                    "cancelled": True}
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
        # Sliced sleep so cancellation lands within ~100ms.
        deadline_now = time.time() + 1.0
        while time.time() < deadline_now:
            if cancel_check is not None and cancel_check():
                return {"found": False, "node": None, "error": "cancelled",
                        "cancelled": True}
            time.sleep(min(0.1, max(0.0, deadline_now - time.time())))
    return {"found": False, "node": None, "error": last_err}


def tap_element(
    device_id: str, by: str, value: str, timeout_ms: int = 10000, instance: int = 0,
    cancel_check: Optional[Any] = None,
) -> Dict[str, Any]:
    """Find an element then tap its center. Returns success + node."""
    from app.automation.input import tap  # late import keeps modules flat

    res = find_element(device_id, by, value, timeout_ms=timeout_ms,
                       instance=instance, cancel_check=cancel_check)
    if res.get("cancelled"):
        return {"success": False, "node": None, "error": "cancelled",
                "cancelled": True}
    if not res.get("found"):
        return {"success": False, "node": None,
                "error": res.get("error") or "element not found"}
    cx, cy = res["node"]["center"]
    r = tap(device_id, cx, cy)
    return {"success": r.get("success", False), "node": res["node"], "error": ""}
