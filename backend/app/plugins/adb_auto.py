#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adb_auto — ADB UI automation plugin.

Orchestrates a JSON step list against a device: launch app, tap / swipe /
input / keyevent, tap elements by text / resource-id / content-desc, wait,
assert element / activity, and screenshot.

Atomic device ops live in ``app.utils.adb_auto_core`` (stdlib only). This
plugin only orchestrates and streams progress / logs through ``PluginContext``.

Cancel / error contract (plan defects 1 & 2):
  * Always end with exactly one ``context.complete(result)`` — never hang.
  * Non-fatal step failures are reported via ``context.log("[FAIL] ...")``
    ONLY. ``context.error()`` is reserved for truly fatal / exceptional cases
    (it tears down the stream listener and rejects ``waitForPhase``), so an
    aborted run still calls ``context.complete(success=False)`` rather than
    ``context.error()``.
  * Check ``context.is_cancelled()`` at the top of every step and bail out
    with ``context.complete(cancelled=True)`` when the user hits Stop.
"""

import time
from typing import Any, Dict, List, Optional, Tuple

from app.utils.adb_auto_core import (
    launch_app,
    clear_app_data,
    get_display_transform,
    rotate_to_display,
    tap,
    swipe,
    input_text,
    keyevent,
    back,
    home,
    shell,
    find_element,
    tap_element,
    current_activity,
    take_screenshot,
)
from app.utils.logger import Logger

logger = Logger.get_logger("adb_auto")

DESCRIPTION = (
    "ADB UI automation: run a JSON step list "
    "(launch/tap/swipe/input/assert/screenshot) against a device."
)
VERSION = "1.0.0"
AUTHOR = "blank_tool"


def run(
    context,
    device_id: Optional[str] = None,
    package_name: Optional[str] = None,
    steps: Optional[List[Dict[str, Any]]] = None,
    continue_on_error: bool = False,
    **kwargs,
) -> Dict[str, Any]:
    steps = steps or []
    result: Dict[str, Any] = {
        "success": True,
        "total": len(steps),
        "passed": 0,
        "failed": 0,
        "cancelled": False,
        "screenshots": [],
        "steps": [],
    }

    if not device_id:
        context.log("[FAIL] missing device_id")
        result["success"] = False
        result["steps"].append(
            {"index": 0, "action": "init", "ok": False,
             "message": "missing device_id", "duration_ms": 0}
        )
        context.step(result["steps"][-1])
        context.complete(result)
        return result

    if not steps:
        context.log("no steps to run")
        context.complete(result)
        return result

    n = len(steps)
    # Recorded steps store touch-panel RAW coords (getevent native
    # orientation); `input tap` needs display coords for the CURRENT
    # rotation (e.g. a landscape-locked game rotates the 900x1600 panel
    # to 1600x900 — raw y>900 would land off-screen and silently no-op).
    dt = get_display_transform(device_id)
    if dt.get("rotation"):
        context.log(
            f"display rotation={dt['rotation']}, panel={dt['width']}x{dt['height']}"
            " — raw coords will be rotated to display space"
        )
    for i, step in enumerate(steps):
        # Cancel check at the top of every step.
        if context.is_cancelled():
            context.log(f"cancelled before step {i + 1}/{n}")
            shot = take_screenshot(device_id, f"cancel-{i + 1}")
            if shot.get("success"):
                result["screenshots"].append(shot["file_path"])
            result["cancelled"] = True
            result["success"] = False
            context.complete(result)
            return result

        action = step.get("action", "")
        # Stream the pending row BEFORE executing so the UI shows progress
        # step by step (long waits / element polling no longer look frozen).
        context.step_start(i + 1, action)
        t0 = time.time()
        ok, message, screenshot = _exec_step(
            context, device_id, package_name, action, step, dt
        )
        duration_ms = int((time.time() - t0) * 1000)

        step_rec: Dict[str, Any] = {
            "index": i + 1,
            "action": action,
            "ok": ok,
            "message": message,
            "duration_ms": duration_ms,
        }
        if screenshot:
            step_rec["screenshot"] = screenshot
            if screenshot not in result["screenshots"]:
                result["screenshots"].append(screenshot)
        result["steps"].append(step_rec)
        # Live progress: one event per finished step.
        context.step(step_rec)

        if ok:
            result["passed"] += 1
            continue

        # Step failed.
        result["failed"] += 1
        step_on_error = step.get("on_error") or (
            "continue" if continue_on_error else "abort"
        )
        if step_on_error == "abort":
            context.log(f"[FAIL] step {i + 1} aborted ({action}): {message}")
            shot = take_screenshot(device_id, f"fail-{i + 1}")
            if shot.get("success"):
                result["screenshots"].append(shot["file_path"])
                step_rec["screenshot"] = shot["file_path"]
            result["success"] = False
            context.step(step_rec)
            context.complete(result)
            return result
        context.log(f"[FAIL] step {i + 1} continued ({action}): {message}")

    context.log(
        f"done: {result['passed']}/{result['total']} passed"
        + (f", {result['failed']} failed" if result["failed"] else "")
    )
    context.complete(result)
    return result


def _exec_step(
    context,
    device_id: str,
    package_name: Optional[str],
    action: str,
    step: Dict[str, Any],
    dt: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str, Optional[str]]:
    """Execute one step. Returns (ok, message, screenshot_path|None)."""
    dt = dt or {"rotation": 0, "width": 0, "height": 0}

    def disp(x, y):
        """Panel raw coords → display coords for `input tap/swipe`."""
        return rotate_to_display(x, y, dt["rotation"], dt["width"], dt["height"])

    # Unified intents: legacy element action names map onto their base
    # action; the by/value pair then selects the element target.
    action = {"tap_element": "tap", "wait_element": "wait"}.get(action, action)

    def has_element_target() -> bool:
        return bool(str(step.get("by", "")) and str(step.get("value", "")))

    def elem_instance() -> int:
        """0-based match index among same-selector nodes (default first)."""
        try:
            return max(0, int(step.get("instance", 0)))
        except (TypeError, ValueError):
            return 0

    try:
        if action == "launch_app":
            pkg = step.get("package") or package_name
            r = launch_app(device_id, pkg)
            return _ok(r), _err(r, "launch failed"), None

        if action == "tap":
            if has_element_target():
                r = tap_element(
                    device_id, step.get("by", ""), step.get("value", ""),
                    timeout_ms=int(step.get("timeout_ms", 10000)),
                    instance=elem_instance(),
                )
                ok = r.get("success", False)
                return ok, "" if ok else (r.get("error") or "element tap failed"), None
            x, y = disp(int(step["x"]), int(step["y"]))
            r = tap(device_id, x, y)
            return _ok(r), _err(r, "tap failed"), None

        if action == "swipe":
            x1, y1 = disp(int(step["x1"]), int(step["y1"]))
            x2, y2 = disp(int(step["x2"]), int(step["y2"]))
            r = swipe(
                device_id,
                x1, y1, x2, y2,
                int(step.get("duration_ms", 300)),
            )
            return _ok(r), _err(r, "swipe failed"), None

        if action == "input":
            r = input_text(device_id, str(step.get("text", "")))
            return _ok(r), _err(r, "input failed"), None

        if action == "keyevent":
            r = keyevent(device_id, str(step.get("key", "")))
            return _ok(r), _err(r, "keyevent failed"), None

        if action == "back":
            return back(device_id).get("success", False), "", None

        if action == "home":
            return home(device_id).get("success", False), "", None

        if action == "clear_app_data":
            pkg = step.get("package") or package_name
            r = clear_app_data(device_id, pkg)
            return _ok(r), _err(r, "clear failed"), None

        if action == "shell":
            r = shell(device_id, str(step.get("command", "")))
            return _ok(r), _err(r, "shell failed"), None

        if action == "wait":
            if has_element_target():
                # wait for an element to appear (poll uiautomator dump)
                r = find_element(
                    device_id, step.get("by", ""), step.get("value", ""),
                    timeout_ms=int(step.get("timeout_ms", 10000)),
                    instance=elem_instance(),
                )
                ok = r.get("found", False)
                return ok, "" if ok else (r.get("error") or "element not found (wait)"), None
            ms = int(step.get("ms", 0))
            if ms > 0:
                # Sleep in slices so Stop takes effect during long waits
                # (otherwise a 5s wait swallows the cancel for 5 seconds).
                deadline = time.time() + ms / 1000.0
                while time.time() < deadline:
                    if context.is_cancelled():
                        break
                    time.sleep(min(0.1, max(0.0, deadline - time.time())))
            return True, "", None

        if action == "tap_element":  # legacy name — handled via alias above
            r = tap_element(
                device_id, step.get("by", ""), step.get("value", ""),
                timeout_ms=int(step.get("timeout_ms", 10000)),
                instance=elem_instance(),
            )
            ok = r.get("success", False)
            return ok, "" if ok else (r.get("error") or "element not found"), None

        if action == "wait_element":  # legacy name — handled via alias above
            r = find_element(
                device_id, step.get("by", ""), step.get("value", ""),
                timeout_ms=int(step.get("timeout_ms", 10000)),
                instance=elem_instance(),
            )
            ok = r.get("found", False)
            return ok, "" if ok else (r.get("error") or "element not found (wait)"), None

        if action == "assert_element":
            r = find_element(
                device_id, step.get("by", ""), step.get("value", ""),
                timeout_ms=int(step.get("timeout_ms", 10000)),
                instance=elem_instance(),
            )
            found = r.get("found", False)
            expect = step.get("expect", "exists")
            ok = (found is True) if expect != "not_exists" else (found is False)
            msg = "" if ok else f"assert_element failed: found={found}, expect={expect}"
            return ok, msg, None

        if action == "assert_activity":
            r = current_activity(device_id, timeout_ms=int(step.get("timeout_ms", 3000)))
            act = r.get("activity", "")
            sub = step.get("activity", "")
            ok = bool(sub) and (sub in act)
            msg = "" if ok else f"assert_activity failed: current={act!r}, expect contains {sub!r}"
            return ok, msg, None

        if action == "screenshot":
            r = take_screenshot(device_id, step.get("name", ""))
            if r.get("success"):
                return True, "", r.get("file_path")
            return False, r.get("error") or "screenshot failed", None

        return False, f"unknown action: {action}", None
    except KeyError as e:
        return False, f"missing field {e} for action {action}", None
    except Exception as e:  # defensive: never let a step crash the whole run
        return False, f"{action} error: {e}", None


def _ok(r: Dict[str, Any]) -> bool:
    return bool(r.get("success", False))


def _err(r: Dict[str, Any], default: str) -> str:
    return "" if r.get("success", False) else (r.get("error") or default)
