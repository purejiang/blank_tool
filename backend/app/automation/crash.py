#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crash / ANR log export from ``logcat -d``."""

import os
import re
import time
from typing import Any, Dict, Optional

from app.automation.adb import run_adb

# Lines that identify a crash regardless of age (kept out-of-window too).
_CRASH_KEEP_KEYS = (
    "FATAL EXCEPTION",
    "AndroidRuntime",
    "ANR in",
    "has died",
    "Force finishing activity",
    "Force stopping",
)


def dump_crash_log(
    device_id: str, out_path: str, window_sec: int = 300
) -> Dict[str, Any]:
    """Export the relevant tail of ``logcat -d`` after a crash.

    Keeps lines from the last ``window_sec`` seconds plus every crash-
    relevant line (FATAL EXCEPTION / AndroidRuntime / ANR / process death)
    regardless of age. Returns ``{"success", "file_path", "error"}``.
    """
    r = run_adb(device_id, ["shell", "logcat", "-d", "-v", "threadtime"])
    if r.get("returncode", 1) != 0:
        return {"success": False, "file_path": "", "error": "logcat -d failed"}
    lines = (r.get("stdout") or "").splitlines()
    cutoff = time.time() - window_sec
    now = time.localtime()

    def ts_of(line: str) -> Optional[float]:
        # threadtime stamp: "MM-DD HH:MM:SS.mmm"
        m = re.match(r"(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})\.(\d+)", line)
        if not m:
            return None
        mo, d, hh, mm, ss, ms = m.groups()
        try:
            t = time.struct_time(
                (now.tm_year, int(mo), int(d), int(hh), int(mm), int(ss), 0, 0, -1)
            )
            return time.mktime(t) + float("0." + ms)
        except (ValueError, OverflowError):
            return None

    out = []
    for line in lines:
        if line.startswith("--------- beginning of"):
            continue
        if any(k in line for k in _CRASH_KEEP_KEYS):
            out.append(line)
            continue
        ts = ts_of(line)
        if ts is not None and ts >= cutoff:
            out.append(line)
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8", errors="replace") as f:
            f.write("\n".join(out) + "\n")
        return {"success": True, "file_path": out_path, "error": ""}
    except OSError as e:
        return {"success": False, "file_path": "", "error": str(e)}
