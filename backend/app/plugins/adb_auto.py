#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adb_auto — ADB UI automation plugin.

Orchestrates a JSON step list against a device: launch app, tap / swipe /
input / keyevent, tap elements by text / resource-id / content-desc, wait,
assert element / activity, and screenshot.

Atomic device ops live in ``app.automation`` (stdlib only); step execution is
table-driven in ``app.automation.steps`` (``ACTIONS`` registry). This
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
from typing import Any, Dict, List, Optional

from app.utils.env import get_output_dir
from app.automation import traffic as traffic_capture
from app.automation.apps import get_app_pid, take_screenshot
from app.automation.crash import dump_crash_log
from app.automation.coords import get_display_transform
from app.automation.input import restore_ime
from app.automation.steps import execute_step
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
            ok, message, screenshot = execute_step(
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

