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
from app.utils.logger import Logger
from app.utils.png import recompress_png_lossless_async

logger = Logger.get_logger("Automation")

# Resumed-activity key → the ``pkg/activity`` token that follows it. See
# ``current_activity`` for why three spellings are accepted.
_RESUMED_ACTIVITY_RE = re.compile(
    r"(?:topResumedActivity|mResumedActivity|ResumedActivity)\b.*?(\S+/\S+)"
)


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
    """Get the resumed activity via ``dumpsys activity activities``.

    Polls until the activity resolves or ``timeout_ms`` elapses. Callers are
    assertions fired right after a navigation, so a single shot failed
    whenever the transition had not settled — ``timeout_ms`` used to be
    accepted and then ignored.

    The resumed-activity KEY differs by ROM/API level: ``mResumedActivity``
    is the legacy spelling, Android 10+ prints ``topResumedActivity`` and
    some vendor builds emit a bare ``ResumedActivity``. Matching only the
    legacy key made this fail on every modern device.
    """
    try:
        budget = max(0, int(timeout_ms))
    except (TypeError, ValueError):
        budget = 3000
    deadline = time.time() + budget / 1000.0
    last_error = "resumed activity not found in dumpsys output"
    while True:
        r = run_adb(device_id, ["shell", "dumpsys", "activity", "activities"])
        out = (r.get("stdout", "") or r.get("stderr", ""))
        m = _RESUMED_ACTIVITY_RE.search(out or "")
        if m:
            activity = m.group(1).split(" ")[0]
            return {"success": True, "activity": activity, "error": ""}
        if r.get("returncode", 1) != 0:
            last_error = (r.get("stderr") or "").strip() or "dumpsys failed"
        if time.time() >= deadline:
            return {"success": False, "activity": "", "error": last_error}
        time.sleep(0.25)


def take_screenshot(
    device_id: str, name: str = "", out_dir: str = ""
) -> Dict[str, Any]:
    """Capture screen to a PNG; return ``{"success", "file_path", "error"}``.

    Default location is ``<output>/screenshots/``; automation runs pass
    ``out_dir`` to keep artifacts inside the per-run directory.
    """
    ts = time.strftime("%Y%m%d-%H%M%S")
    suffix = f"-{name}" if name else ""
    screenshots_dir = out_dir or os.path.join(get_output_dir(), "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)
    file_path = os.path.join(
        screenshots_dir, f"auto-{ts}{suffix}-{uuid.uuid4().hex[:6]}.png"
    )
    # UNIQUE remote name: a fixed /sdcard path is shared by every device and
    # by every concurrent capture (a step screenshot racing the crash-log shot
    # on the same device), so one capture could pull another's image — or have
    # it deleted by that capture's cleanup `rm`.
    remote = f"/sdcard/blank_tool_shot_{uuid.uuid4().hex}.png"
    cap = run_adb(device_id, ["shell", "screencap", "-p", remote])
    if cap.get("returncode", 1) != 0:
        return {"success": False, "file_path": "",
                "error": cap.get("stderr", "screencap failed")}
    pull = run_adb(device_id, ["pull", remote, file_path])
    run_adb(device_id, ["shell", "rm", "-f", remote])
    if pull.get("returncode", 1) != 0:
        return {"success": False, "file_path": "",
                "error": pull.get("stderr", "pull failed")}
    # Lossless shrink in place (~10% on screencap PNGs) on a background
    # thread — level-9 deflate takes seconds, which must not delay the
    # step. Atomic replace + never-raises, so this cannot fail the step.
    recompress_png_lossless_async(file_path, logger)
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
