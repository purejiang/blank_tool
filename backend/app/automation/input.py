#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Touch / text / key input plus ADBKeyboard IME management."""

import base64
import time
from typing import Any, Dict, Optional, Tuple

from app.automation.adb import run_adb
from app.utils.logger import Logger

logger = Logger.get_logger("AutomationInput")


# ----------------------------------------------------------------------
# touch / basic input
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
            # ADBKeyboard v2.0 reads the base64 payload from the "msg" extra
            ["shell", "am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", b64],
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


def _adb_ime_bound(device_id: str) -> bool:
    """True once the system has actually bound ADBKeyboard as the IME.

    ``settings get`` flips instantly on ``ime set``, but the IME service
    (whose receiver must be alive to take our broadcast) binds a moment
    later — check ``dumpsys input_method``'s mCurMethodId instead.
    """
    r = run_adb(device_id, ["shell", "dumpsys", "input_method"])
    return "mCurMethodId=com.android.adbkeyboard/.AdbIME" in (r.get("stdout") or "")


def ensure_adb_ime(device_id: str) -> Tuple[bool, str]:
    """Switch the default IME to ADBKeyboard (remembering the original).

    Waits until the IME service is actually bound before returning — a
    broadcast fired between ``ime set`` and the service's receiver
    registration is silently dropped. Idempotent within a run: once
    switched, later ``input_text`` calls are no-ops. The caller should
    ``restore_ime`` when the run finishes.
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
    # Wait (up to ~4s) for the IME service to bind, then a small settle so
    # the focused editor's input connection restarts with the new IME.
    deadline = time.time() + 4.0
    while time.time() < deadline:
        if _adb_ime_bound(device_id):
            break
        time.sleep(0.1)
    time.sleep(0.3)
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
