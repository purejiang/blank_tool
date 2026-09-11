#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
automation.orchestrator — ADB UI automation run orchestration.

Orchestrates a JSON step list against a device: launch app, tap / swipe /
input / keyevent, tap elements by text / resource-id / content-desc, wait,
assert element / activity, and screenshot.

Atomic device ops live in ``app.automation`` (stdlib only); step execution is
table-driven in ``app.automation.steps`` (``ACTIONS`` registry). This module
only orchestrates and streams progress / logs through ``StreamContext``.

Served by the ``automation.run`` streaming handler
(``app/handlers/automation_handler.py``) — this used to be the ``adb_auto``
"plugin" and was deliberately moved OUT of the plugin framework: automation
is a first-class feature, plugins are for external tools (jadx, scrapy, ...).

Cancel / error contract (plan defects 1 & 2):
  * Always end with exactly one ``context.complete(result)`` — never hang.
  * Non-fatal step failures are reported via ``_log("[FAIL] ...")``
    ONLY. ``context.error()`` is reserved for truly fatal / exceptional cases
    (it tears down the stream listener and rejects ``waitForPhase``), so an
    aborted run still calls ``context.complete(success=False)`` rather than
    ``context.error()``.
  * Check ``context.is_cancelled()`` at the top of every step and bail out
    with ``context.complete(cancelled=True)`` when the user hits Stop.
"""

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from app.utils.env import get_auto_task_dir, get_auto_tasks_root, get_output_dir
from app.automation import traffic as traffic_capture
from app.automation.apps import get_app_pid, take_screenshot
from app.automation.crash import dump_crash_log
from app.automation.coords import get_display_transform
from app.automation.input import restore_ime
from app.automation.steps import execute_step
from app.utils.logger import Logger

logger = Logger.get_logger("automation")


def _fallback_run_dir() -> str:
    """Run dir when no task_id is available (probe/manual invocation).

    Still lands under the automation root so every script run lives in
    ``auto_tasks/`` regardless of how it was launched.
    """
    d = os.path.join(
        get_auto_tasks_root(),
        f"auto-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}",
    )
    os.makedirs(d, exist_ok=True)
    return d


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
    task_id: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    steps = steps or []
    started_t = time.time()
    started_iso = time.strftime("%Y-%m-%dT%H:%M:%S")

    # Per-run artifact directory — one folder per run, in the automation root
    # ({BT_AUTO_TASKS_DIR}/{task_id}/, a sibling of tasks/) with artifacts
    # categorized into screenshots/ traffic/ crash_logs/ plus report.json.
    if task_id:
        try:
            run_dir = get_auto_task_dir(str(task_id))
        except ValueError:
            run_dir = _fallback_run_dir()
    else:
        run_dir = _fallback_run_dir()
    shots_dir = os.path.join(run_dir, "screenshots")
    # step handlers (steps.py) read this to keep their artifacts in-run-dir
    context.run_dir = run_dir

    result: Dict[str, Any] = {
        "success": True,
        "task_id": str(task_id or ""),
        "total": len(steps),
        "passed": 0,
        "failed": 0,
        "cancelled": False,
        "screenshots": [],
        "shots_meta": [],
        "steps": [],
        # Persisted log lines ({ts, text}) — the run report's log tab reads
        # these so a historical run shows the same feed the live console did.
        # ``context.log`` also streams each line to the frontend unchanged.
        "logs": [],
        "run_dir": run_dir,
    }

    def _log(message: str) -> None:
        """Stream a log line AND keep it for report.json.

        The frontend receives the raw string via ``context.log`` (payload
        shape unchanged); the copy stored here carries an epoch timestamp
        so the report viewer can place it on the run's clock.
        """
        context.log(message)
        result["logs"].append({"ts": time.time(), "text": message})

    def _shot(name: str, step_index: Optional[int] = None) -> Optional[str]:
        """Capture into the run dir and record its metadata (path + ts).

        The timestamp lets the report viewer line screenshots up with the
        step they belong to and with network requests captured at the
        same moment.
        """
        r = take_screenshot(device_id, name, out_dir=shots_dir)
        if not r.get("success"):
            return None
        path = r["file_path"]
        if path not in result["screenshots"]:
            result["screenshots"].append(path)
        result["shots_meta"].append({
            "path": path,
            "name": name,
            "ts": time.time(),
            "step_index": step_index,
        })
        return path

    def _write_report() -> None:
        """Persist ``report.json`` — machine-readable summary of this run."""
        try:
            report = {
                "kind": "automation_run",
                "task_id": str(task_id or ""),
                "device_id": device_id or "",
                "package_name": package_name or "",
                "started_at": started_iso,
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                # epoch anchors — the report viewer correlates steps,
                # screenshots and captured requests on the same clock
                "started_ts": started_t,
                "finished_ts": time.time(),
                "duration_ms": int((time.time() - started_t) * 1000),
                "success": bool(result.get("success")),
                "cancelled": bool(result.get("cancelled")),
                "aborted_by_crash": bool(result.get("aborted_by_crash")),
                "total": result.get("total", 0),
                "passed": result.get("passed", 0),
                "failed": result.get("failed", 0),
                "steps": result.get("steps", []),
                "logs": result.get("logs", []),
                "screenshots": result.get("screenshots", []),
                "shots_meta": result.get("shots_meta", []),
                "traffic_log": result.get("traffic_log"),
                "traffic_requests": result.get("traffic_requests"),
                "traffic_https_ready": result.get("traffic_https_ready"),
                "crash_log": result.get("crash_log"),
                "run_dir": run_dir,
            }
            with open(os.path.join(run_dir, "report.json"), "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        except Exception as e:  # never let reporting break the run
            logger.warning(f"failed to write report.json: {e}")

    if not device_id:
        _log("[FAIL] missing device_id")
        result["success"] = False
        result["steps"].append(
            {"index": 0, "action": "init", "ok": False,
             "message": "missing device_id", "duration_ms": 0,
             "started_at": started_t, "ended_at": time.time()}
        )
        context.step(result["steps"][-1])
        _write_report()
        context.complete(result)
        return result

    if not steps:
        _log("no steps to run")
        _write_report()
        context.complete(result)
        return result

    n = len(steps)
    # Recorded steps store touch-panel RAW coords (getevent native
    # orientation); `input tap` needs display coords for the CURRENT
    # rotation (e.g. a landscape-locked game rotates the 900x1600 panel
    # to 1600x900 — raw y>900 would land off-screen and silently no-op).
    dt = get_display_transform(device_id)
    if dt.get("rotation"):
        _log(
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
            _log(f"crash watch on {package_name} (pid {watch_pid})")

    # Traffic capture (optional): mitmdump on the PC + device HTTP proxy.
    # The device proxy MUST be restored on EVERY exit path — a device left
    # pointing at a dead proxy loses connectivity — hence try/finally below.
    capture_on = False
    if capture_traffic:
        jsonl = os.path.join(
            run_dir, "traffic",
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
            _log(
                f"traffic capture started (port {cap['port']})"
                + (" — HTTPS decryptable" if cap.get("https_ready")
                   else " — CA not installed, HTTPS stays encrypted")
            )
        else:
            _log(
                f"[FAIL] traffic capture unavailable: {cap.get('error')}"
                " — continuing without capture"
            )

    try:
        for i, step in enumerate(steps):
            # Cancel check at the top of every step.
            if context.is_cancelled():
                _log(f"cancelled before step {i + 1}/{n}")
                _shot(f"cancel-{i + 1}", i + 1)
                result["cancelled"] = True
                result["success"] = False
                restore_ime(device_id)  # CJK input path may have switched the IME
                return result

            # Crash check — only once the app was seen alive at least once
            # (a script may launch it itself; pid None before launch is normal).
            if watch:
                cur = get_app_pid(device_id, package_name)
                if watch_pid is not None and cur != watch_pid:
                    died = "exited" if cur is None else f"restarted (pid {watch_pid} -> {cur})"
                    crash_msg = f"app {package_name} crashed: {died}"
                    _log(f"[FAIL] {crash_msg}")
                    _shot("crash", i + 1)
                    crash = dump_crash_log(
                        device_id,
                        os.path.join(
                            run_dir, "crash_logs",
                            f"crash-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.log",
                        ),
                    )
                    _now = time.time()
                    rec = {
                        "index": i + 1, "action": "app_crash", "ok": False,
                        "message": crash_msg, "duration_ms": 0,
                        "started_at": _now, "ended_at": _now,
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
                _log(f"cancelled during step {i + 1}/{n}")
                if ok:
                    result["steps"].append(
                        {"index": i + 1, "action": action, "ok": True,
                         "message": message, "duration_ms": duration_ms,
                         "started_at": t0, "ended_at": t0 + duration_ms / 1000.0}
                    )
                    result["passed"] += 1
                _shot(f"cancel-{i + 1}", i + 1)
                result["cancelled"] = True
                result["success"] = False
                restore_ime(device_id)
                return result

            step_rec: Dict[str, Any] = {
                "index": i + 1,
                "action": action,
                "ok": ok,
                "message": message,
                "duration_ms": duration_ms,
                "started_at": t0,
                "ended_at": t0 + duration_ms / 1000.0,
            }
            if screenshot:
                step_rec["screenshot"] = screenshot
                if screenshot not in result["screenshots"]:
                    result["screenshots"].append(screenshot)
                result["shots_meta"].append({
                    "path": screenshot,
                    "name": f"step-{i + 1}",
                    "ts": t0 + duration_ms / 1000.0,
                    "step_index": i + 1,
                })
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
                _log(f"[FAIL] step {i + 1} aborted ({action}): {message}")
                sp = _shot(f"fail-{i + 1}", i + 1)
                if sp:
                    step_rec["screenshot"] = sp
                result["success"] = False
                restore_ime(device_id)
                context.step(step_rec)
                return result
            _log(f"[FAIL] step {i + 1} continued ({action}): {message}")

        _log(
            f"done: {result['passed']}/{result['total']} passed"
            + (f", {result['failed']} failed" if result["failed"] else "")
        )
        restore_ime(device_id)
        return result
    finally:
        if capture_on:
            stopped = traffic_capture.stop_capture(device_id)
            result["traffic_requests"] = stopped.get("requests", 0)
            if stopped.get("jsonl"):
                result["traffic_log"] = stopped["jsonl"]
            _log(
                f"traffic capture stopped ({result.get('traffic_requests', 0)} requests)"
            )
        # Order matters: persist the report BEFORE emitting the terminal
        # `complete` event. The frontend reacts to `complete` by refreshing
        # its run list (and may replay the record), so report.json must
        # already be on disk — otherwise the run that just finished is
        # missing from the history until a manual refresh.
        # Emitting `complete` exactly once, here, also means every exit path
        # (cancel / crash / abort / normal end) goes through the same
        # write-then-notify sequence.
        _write_report()
        context.complete(result)

