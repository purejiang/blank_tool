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

import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.utils.env import get_output_dir
from app.automation import traffic as traffic_capture
from app.automation import (
    launch_app,
    clear_app_data,
    get_display_transform,
    get_app_pid,
    dump_crash_log,
    rotate_to_display,
    tap,
    swipe,
    input_text,
    restore_ime,
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
    abort_on_crash: bool = True,
    capture_traffic: bool = False,
    traffic_port: int = traffic_capture.DEFAULT_PORT,
    traffic_host_filter: str = "",
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

    # Crash watch: track the target app's pid and abort the run as soon as
    # the process dies / restarts (checked at every step boundary — steps
    # are serial, so this is effectively real-time without a thread).
    watch_pid: Optional[int] = None
    watch = bool(abort_on_crash and package_name)
    if watch:
        watch_pid = get_app_pid(device_id, package_name)
        if watch_pid:
            context.log(f"crash watch on {package_name} (pid {watch_pid})")

    # Traffic capture (optional): mitmdump on the PC + device HTTP proxy.
    # The device proxy MUST be restored on EVERY exit path — a device left
    # pointing at a dead proxy loses connectivity — hence try/finally below.
    capture_on = False
    if capture_traffic:
        jsonl = os.path.join(
            get_output_dir(), "traffic",
            f"traffic-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.jsonl",
        )
        cap = traffic_capture.start_capture(
            device_id, jsonl, port=int(traffic_port),
            host_filter=str(traffic_host_filter or ""),
        )
        if cap.get("success"):
            capture_on = True
            result["traffic_log"] = cap["jsonl"]
            result["traffic_https_ready"] = bool(cap.get("https_ready"))
            context.log(
                f"traffic capture started (port {cap['port']})"
                + (" — HTTPS decryptable" if cap.get("https_ready")
                   else " — CA not installed, HTTPS stays encrypted")
            )
        else:
            context.log(
                f"[FAIL] traffic capture unavailable: {cap.get('error')}"
                " — continuing without capture"
            )

    try:
        for i, step in enumerate(steps):
            # Cancel check at the top of every step.
            if context.is_cancelled():
                context.log(f"cancelled before step {i + 1}/{n}")
                shot = take_screenshot(device_id, f"cancel-{i + 1}")
                if shot.get("success"):
                    result["screenshots"].append(shot["file_path"])
                result["cancelled"] = True
                result["success"] = False
                restore_ime(device_id)  # CJK input path may have switched the IME
                context.complete(result)
                return result

            # Crash check — only once the app was seen alive at least once
            # (a script may launch it itself; pid None before launch is normal).
            if watch:
                cur = get_app_pid(device_id, package_name)
                if watch_pid is not None and cur != watch_pid:
                    died = "exited" if cur is None else f"restarted (pid {watch_pid} -> {cur})"
                    crash_msg = f"app {package_name} crashed: {died}"
                    context.log(f"[FAIL] {crash_msg}")
                    shot = take_screenshot(device_id, "crash")
                    if shot.get("success"):
                        result["screenshots"].append(shot["file_path"])
                    crash = dump_crash_log(
                        device_id,
                        os.path.join(
                            get_output_dir(), "crash_logs",
                            f"crash-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.log",
                        ),
                    )
                    rec = {
                        "index": i + 1, "action": "app_crash", "ok": False,
                        "message": crash_msg, "duration_ms": 0,
                    }
                    if crash.get("success"):
                        rec["crash_log"] = crash["file_path"]
                        result["crash_log"] = crash["file_path"]
                    else:
                        rec["message"] += f"; logcat export failed: {crash.get('error')}"
                    result["steps"].append(rec)
                    context.step(rec)
                    result["failed"] += 1
                    result["success"] = False
                    result["aborted_by_crash"] = True
                    restore_ime(device_id)
                    context.complete(result)
                    return result
                if cur is not None:
                    watch_pid = cur

            action = step.get("action", "")
            # Stream the pending row BEFORE executing so the UI shows progress
            # step by step (long waits / element polling no longer look frozen).
            context.step_start(i + 1, action)
            t0 = time.time()
            ok, message, screenshot = _exec_step(
                context, device_id, package_name, action, step, dt
            )
            duration_ms = int((time.time() - t0) * 1000)

            # Stop pressed while the step ran (e.g. mid element-poll): finish
            # the run as cancelled right away instead of continuing to step 2.
            if context.is_cancelled():
                context.log(f"cancelled during step {i + 1}/{n}")
                if ok:
                    result["steps"].append(
                        {"index": i + 1, "action": action, "ok": True,
                         "message": message, "duration_ms": duration_ms}
                    )
                    result["passed"] += 1
                shot = take_screenshot(device_id, f"cancel-{i + 1}")
                if shot.get("success"):
                    result["screenshots"].append(shot["file_path"])
                result["cancelled"] = True
                result["success"] = False
                restore_ime(device_id)
                context.complete(result)
                return result

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
                restore_ime(device_id)
                context.step(step_rec)
                context.complete(result)
                return result
            context.log(f"[FAIL] step {i + 1} continued ({action}): {message}")

        context.log(
            f"done: {result['passed']}/{result['total']} passed"
            + (f", {result['failed']} failed" if result["failed"] else "")
        )
        restore_ime(device_id)
        context.complete(result)
        return result
    finally:
        if capture_on:
            stopped = traffic_capture.stop_capture(device_id)
            result["traffic_requests"] = stopped.get("requests", 0)
            if stopped.get("jsonl"):
                result["traffic_log"] = stopped["jsonl"]
            context.log(
                f"traffic capture stopped ({result.get('traffic_requests', 0)} requests)"
            )


def _exec_step(
    context,
    device_id: str,
    package_name: Optional[str],
    action: str,
    step: Dict[str, Any],
    dt: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str, Optional[str]]:
    """Execute one v2 step. Returns (ok, message, screenshot_path|None).

    v2 step model (see renderer stepTypes.ts — the single source of truth):
      * mode discriminates the target for tap (coord|element) and
        wait (time|element);
      * element targets are the nested target object
        {by, value, instance?, timeout_ms?} shared by tap/wait/input/assert;
      * swipe carries path {x1,y1,x2,y2,duration_ms?}, tap carries
        coord {x,y}.
    """
    dt = dt or {"rotation": 0, "width": 0, "height": 0}

    def disp(x, y):
        """Panel raw coords → display coords for input tap/swipe."""
        return rotate_to_display(x, y, dt["rotation"], dt["width"], dt["height"])

    def tgt() -> Tuple[str, str, int, int]:
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

    try:
        if action == "launch_app":
            pkg = step.get("package") or package_name
            r = launch_app(device_id, pkg)
            return _ok(r), _err(r, "launch failed"), None

        if action == "tap":
            if step.get("mode") == "element" or step.get("target"):
                by, value, instance, timeout = tgt()
                r = tap_element(
                    device_id, by, value,
                    timeout_ms=timeout,
                    instance=instance,
                    cancel_check=context.is_cancelled,
                )
                ok = r.get("success", False)
                return ok, "" if ok else (r.get("error") or "element tap failed"), None
            c = step.get("coord") or {}
            x, y = disp(int(c.get("x", 0)), int(c.get("y", 0)))
            r = tap(device_id, x, y)
            return _ok(r), _err(r, "tap failed"), None

        if action == "swipe":
            p = step.get("path") or {}
            x1, y1 = disp(int(p.get("x1", 0)), int(p.get("y1", 0)))
            x2, y2 = disp(int(p.get("x2", 0)), int(p.get("y2", 0)))
            try:
                duration = int(p.get("duration_ms", 300))
            except (TypeError, ValueError):
                duration = 300
            r = swipe(device_id, x1, y1, x2, y2, duration)
            return _ok(r), _err(r, "swipe failed"), None

        if action == "input":
            # Optional focus: with a non-empty target, tap the field first —
            # `input text` only types into the focused editor.
            by, value, instance, timeout = tgt()
            if value:
                fr = tap_element(
                    device_id, by, value,
                    timeout_ms=timeout,
                    instance=instance,
                    cancel_check=context.is_cancelled,
                )
                if not fr.get("success", False):
                    return False, (fr.get("error") or "input field not found"), None
                time.sleep(0.3)  # let the editor settle before typing
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
            if step.get("mode") == "element" or step.get("target"):
                by, value, instance, timeout = tgt()
                # wait for an element to appear (poll uiautomator dump)
                r = find_element(
                    device_id, by, value,
                    timeout_ms=timeout,
                    instance=instance,
                    cancel_check=context.is_cancelled,
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

        if action == "assert_element":
            by, value, instance, timeout = tgt()
            r = find_element(
                device_id, by, value,
                timeout_ms=timeout,
                instance=instance,
                cancel_check=context.is_cancelled,
            )
            found = r.get("found", False)
            expect = step.get("expect", "exists")
            ok = (found is True) if expect != "not_exists" else (found is False)
            msg = "" if ok else f"assert_element failed: found={found}, expect={expect}"
            return ok, msg, None

        if action == "assert_activity":
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

        if action == "screenshot":
            r = take_screenshot(device_id, str(step.get("name", "")))
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
