#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""App-level actions: launch / clear data / activity / screenshot / pid."""

import os
import re
import time
import uuid
from typing import Any, Dict, Optional

from app.automation.adb import run_adb
from app.utils.env import get_output_dir


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


def get_app_pid(device_id: str, package: str) -> Optional[int]:
    """Main pid of ``package`` or None when it is not running."""
    if not package:
        return None
    r = run_adb(device_id, ["shell", "pidof", package])
    if r.get("returncode", 1) != 0:
        return None
    parts = (r.get("stdout") or "").split()
    try:
        return int(parts[0])
    except (IndexError, ValueError):
        return None
