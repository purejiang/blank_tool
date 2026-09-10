#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ADB automation package — focused, stdlib-only device-operation modules.

Layout:
  * ``adb``      low-level ``adb -s <id>`` runner (ToolManager bridge)
  * ``coords``   display rotation / raw→display coordinate mapping
  * ``input``    tap / swipe / text / keyevent + ADBKeyboard IME
  * ``elements`` uiautomator dump / find_element / tap_element
  * ``apps``     launch / clear data / activity / screenshot / pid
  * ``crash``    logcat crash + ANR tail export
  * ``traffic``  mitmdump orchestration (per-run network capture)
"""

from app.automation.adb import run_adb
from app.automation.coords import get_display_transform, rotate_to_display
from app.automation.input import (
    ADB_IME_ID,
    ADB_IME_PKG,
    adb_ime_installed,
    back,
    ensure_adb_ime,
    home,
    input_text,
    keyevent,
    restore_ime,
    shell,
    swipe,
    tap,
)
from app.automation.elements import find_element, tap_element, ui_dump
from app.automation.apps import (
    clear_app_data,
    current_activity,
    get_app_pid,
    launch_app,
    take_screenshot,
)
from app.automation.crash import dump_crash_log
from app.automation import traffic

__all__ = [
    "run_adb",
    "get_display_transform", "rotate_to_display",
    "tap", "swipe", "input_text", "keyevent", "back", "home", "shell",
    "ADB_IME_PKG", "ADB_IME_ID", "adb_ime_installed", "ensure_adb_ime",
    "restore_ime",
    "ui_dump", "find_element", "tap_element",
    "launch_app", "clear_app_data", "current_activity", "take_screenshot",
    "get_app_pid",
    "dump_crash_log",
    "traffic",
]
