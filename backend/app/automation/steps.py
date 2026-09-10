#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Table-driven step executor — the backend half of the step action contract.

``ACTIONS`` maps each v2 action name (mirroring the renderer's
``stepTypes.ts`` ``StepAction`` union — the single source of truth) to its
handler. ``execute_step`` is the only entry point the plugin needs.

Handler signature::

    handler(ctx, device_id, package_name, step, dt)
      -> (ok: bool, message: str, screenshot_path: str | None)

``ctx`` supplies ``is_cancelled()`` (used for cancel_check during element
polling and sliced waits); ``dt`` is the display transform from
``coords.get_display_transform`` used to map panel-raw touch coords to
display space.
"""

import time
from typing import Any, Dict, Optional, Tuple

from app.automation.apps import (
    clear_app_data,
    current_activity,
    launch_app,
    take_screenshot,
)
from app.automation.coords import rotate_to_display
from app.automation.elements import find_element, tap_element
from app.automation.input import (
    back,
    home,
    input_text,
    keyevent,
    shell,
    swipe,
    tap,
)

StepHandlerReturn = Tuple[bool, str, Optional[str]]


# ----------------------------------------------------------------------
# shared helpers
# ----------------------------------------------------------------------

def _tgt(step: Dict[str, Any]) -> Tuple[str, str, int, int]:
    """Extract the nested element target ``(by, value, instance, timeout_ms)``."""
    t = step.get("target") or {}
    try:
        instance = max(0, int(t.get("instance", 0) or 0))
    except (TypeError, ValueError):
        instance = 0
    try:
        timeout = int(t.get("timeout_ms", 10000) or 10000)
    except (TypeError, ValueError):
        timeout = 10000
    return str(t.get("by", "")), str(t.get("value", "")), instance, timeout


def _disp(step_ctx: Dict[str, Any], x: int, y: int) -> Tuple[int, int]:
    """Panel raw coords → display coords for ``input tap/swipe``."""
    return rotate_to_display(
        x, y, step_ctx["rotation"], step_ctx["width"], step_ctx["height"]
    )


def _ok(r: Dict[str, Any]) -> bool:
    return bool(r.get("success", False))


def _err(r: Dict[str, Any], default: str) -> str:
    return "" if r.get("success", False) else (r.get("error") or default)


# ----------------------------------------------------------------------
# action handlers
# ----------------------------------------------------------------------

def _launch_app(ctx, device_id, package_name, step, dt) -> StepHandlerReturn:
    pkg = step.get("package") or package_name
    r = launch_app(device_id, pkg)
    return _ok(r), _err(r, "launch failed"), None


def _tap(ctx, device_id, package_name, step, dt) -> StepHandlerReturn:
    if step.get("mode") == "element" or step.get("target"):
        by, value, instance, timeout = _tgt(step)
        r = tap_element(
            device_id, by, value,
            timeout_ms=timeout,
            instance=instance,
            cancel_check=ctx.is_cancelled,
        )
        ok = r.get("success", False)
        return ok, "" if ok else (r.get("error") or "element tap failed"), None
    c = step.get("coord") or {}
    x, y = _disp(dt, int(c.get("x", 0)), int(c.get("y", 0)))
    r = tap(device_id, x, y)
    return _ok(r), _err(r, "tap failed"), None


def _swipe(ctx, device_id, package_name, step, dt) -> StepHandlerReturn:
    p = step.get("path") or {}
    x1, y1 = _disp(dt, int(p.get("x1", 0)), int(p.get("y1", 0)))
    x2, y2 = _disp(dt, int(p.get("x2", 0)), int(p.get("y2", 0)))
    try:
        duration = int(p.get("duration_ms", 300))
    except (TypeError, ValueError):
        duration = 300
    r = swipe(device_id, x1, y1, x2, y2, duration)
    return _ok(r), _err(r, "swipe failed"), None


def _input(ctx, device_id, package_name, step, dt) -> StepHandlerReturn:
    # Optional focus: with a non-empty target, tap the field first —
    # `input text` only types into the focused editor.
    by, value, instance, timeout = _tgt(step)
    if value:
        fr = tap_element(
            device_id, by, value,
            timeout_ms=timeout,
            instance=instance,
            cancel_check=ctx.is_cancelled,
        )
        if not fr.get("success", False):
            return False, (fr.get("error") or "input field not found"), None
        time.sleep(0.3)  # let the editor settle before typing
    r = input_text(device_id, str(step.get("text", "")))
    return _ok(r), _err(r, "input failed"), None


def _keyevent(ctx, device_id, package_name, step, dt) -> StepHandlerReturn:
    r = keyevent(device_id, str(step.get("key", "")))
    return _ok(r), _err(r, "keyevent failed"), None


def _back(ctx, device_id, package_name, step, dt) -> StepHandlerReturn:
    return back(device_id).get("success", False), "", None


def _home(ctx, device_id, package_name, step, dt) -> StepHandlerReturn:
    return home(device_id).get("success", False), "", None


def _clear_app_data(ctx, device_id, package_name, step, dt) -> StepHandlerReturn:
    pkg = step.get("package") or package_name
    r = clear_app_data(device_id, pkg)
    return _ok(r), _err(r, "clear failed"), None


def _shell(ctx, device_id, package_name, step, dt) -> StepHandlerReturn:
    r = shell(device_id, str(step.get("command", "")))
    return _ok(r), _err(r, "shell failed"), None


def _wait(ctx, device_id, package_name, step, dt) -> StepHandlerReturn:
    if step.get("mode") == "element" or step.get("target"):
        by, value, instance, timeout = _tgt(step)
        # wait for an element to appear (poll uiautomator dump)
        r = find_element(
            device_id, by, value,
            timeout_ms=timeout,
            instance=instance,
            cancel_check=ctx.is_cancelled,
        )
        ok = r.get("found", False)
        return ok, "" if ok else (r.get("error") or "element not found (wait)"), None
    ms = int(step.get("ms", 0))
    if ms > 0:
        # Sleep in slices so Stop takes effect during long waits
        # (otherwise a 5s wait swallows the cancel for 5 seconds).
        deadline = time.time() + ms / 1000.0
        while time.time() < deadline:
            if ctx.is_cancelled():
                break
            time.sleep(min(0.1, max(0.0, deadline - time.time())))
    return True, "", None


def _assert_element(ctx, device_id, package_name, step, dt) -> StepHandlerReturn:
    by, value, instance, timeout = _tgt(step)
    r = find_element(
        device_id, by, value,
        timeout_ms=timeout,
        instance=instance,
        cancel_check=ctx.is_cancelled,
    )
    found = r.get("found", False)
    expect = step.get("expect", "exists")
    ok = (found is True) if expect != "not_exists" else (found is False)
    msg = "" if ok else f"assert_element failed: found={found}, expect={expect}"
    return ok, msg, None


def _assert_activity(ctx, device_id, package_name, step, dt) -> StepHandlerReturn:
    try:
        timeout = int(step.get("timeout_ms", 3000) or 3000)
    except (TypeError, ValueError):
        timeout = 3000
    r = current_activity(device_id, timeout_ms=timeout)
    act = r.get("activity", "")
    sub = str(step.get("activity", ""))
    ok = bool(sub) and (sub in act)
    msg = "" if ok else f"assert_activity failed: current={act!r}, expect contains {sub!r}"
    return ok, msg, None


def _screenshot(ctx, device_id, package_name, step, dt) -> StepHandlerReturn:
    r = take_screenshot(device_id, str(step.get("name", "")))
    if r.get("success"):
        return True, "", r.get("file_path")
    return False, r.get("error") or "screenshot failed", None


# ----------------------------------------------------------------------
# registry — keep in sync with renderer stepTypes.ts StepAction (C1 test)
# ----------------------------------------------------------------------

ACTIONS: Dict[str, Any] = {
    "launch_app": _launch_app,
    "tap": _tap,
    "swipe": _swipe,
    "input": _input,
    "keyevent": _keyevent,
    "back": _back,
    "home": _home,
    "clear_app_data": _clear_app_data,
    "shell": _shell,
    "wait": _wait,
    "assert_element": _assert_element,
    "assert_activity": _assert_activity,
    "screenshot": _screenshot,
}


def execute_step(
    ctx,
    device_id: str,
    package_name: Optional[str],
    action: str,
    step: Dict[str, Any],
    dt: Optional[Dict[str, Any]] = None,
) -> StepHandlerReturn:
    """Execute one v2 step via the ACTIONS registry.

    Returns ``(ok, message, screenshot_path|None)``. Never raises — a step
    exception is reported as a failed step so one bad step cannot crash
    the whole run.
    """
    handler = ACTIONS.get(action)
    if handler is None:
        return False, f"unknown action: {action}", None
    step_ctx = dt or {"rotation": 0, "width": 0, "height": 0}
    try:
        return handler(ctx, device_id, package_name, step, step_ctx)
    except KeyError as e:
        return False, f"missing field {e} for action {action}", None
    except Exception as e:  # defensive: never let a step crash the whole run
        return False, f"{action} error: {e}", None
