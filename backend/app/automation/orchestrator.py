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

Run span / pacing:
  * ``start_index`` (0-based) starts the run MID-SCRIPT: the earlier steps are
    not executed at all (they are not "skipped" steps in the report — the run
    simply begins at the given step). Step numbers in the report keep their
    ORIGINAL 1-based position so the run rows still match the script rows.
  * ``step_interval_ms`` is a per-run default wait inserted BEFORE each step
    (except the first executed one) so a script does not need hand-written
    ``wait`` steps between every action. A step may override it with its own
    ``delay_ms`` (0 = no wait for that step).
  * ``recorded_gap_ms`` (recorded steps only) is the pause the recorder
    measured between two real operations. It is ADDITIVE: a recorded step
    waits ``step_interval_ms + recorded_gap_ms``, so recording keeps its true
    rhythm AND still gets the run-level interval. An explicit ``delay_ms``
    replaces both.
"""

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from app.utils.env import get_auto_task_dir, get_auto_tasks_root, get_output_dir
from app.automation import runstate
from app.automation import traffic as traffic_capture
from app.automation.apps import get_app_pid, take_screenshot
from app.automation.crash import dump_crash_log
from app.automation.coords import get_display_transform
from app.automation.input import restore_ime
from app.automation.steps import execute_step
from app.utils.logger import Logger

logger = Logger.get_logger("automation")

# Steps that intentionally kill / replace the target process. The crash watch
# must re-anchor after these, otherwise a scripted restart looks exactly like
# a crash (`clear_app_data` -> pid gone -> next step's check aborts the run).
_RESTART_ACTIONS = frozenset({"clear_app_data", "launch_app"})

# Fields `automation.list_runs` needs for the history list. The full report
# also carries steps / logs / screenshots / traffic, which is why the index is
# a separate (small) file: listing 100 runs used to parse 100 full reports.
SUMMARY_NAME = "summary.json"
_SUMMARY_KEYS = (
    "kind", "task_id", "device_id", "package_name", "started_at", "finished_at",
    "started_ts", "finished_ts", "duration_ms", "success", "cancelled",
    "aborted_by_crash", "total", "passed", "failed", "run_dir",
)


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


# Cancel latency inside an inter-step interval: the sleep is sliced so Stop is
# honoured within ~50ms instead of after the whole interval (same trick as the
# sliced fixed wait in steps.py ``_wait``).
_INTERVAL_SLICE_S = 0.05


def _as_int(value: Any, default: int = 0) -> int:
    """Coerce a JSON-provided number to an int without ever raising.

    ``bool`` is an ``int`` subclass, so ``True`` would silently become 1; a
    boolean here means a malformed payload, hence the default instead.
    """
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_non_negative_int(value: Any) -> int:
    """Like ``_as_int`` but negative / malformed values collapse to 0."""
    return max(0, _as_int(value, 0))


def _interruptible_sleep(ctx, ms: int) -> None:
    """Sleep ``ms`` in slices, returning early as soon as a cancel arrives."""
    deadline = time.time() + ms / 1000.0
    while time.time() < deadline:
        if ctx.is_cancelled():
            return
        time.sleep(min(_INTERVAL_SLICE_S, max(0.0, deadline - time.time())))


def _recorded_gap_ms(step: Dict[str, Any]) -> int:
    """Pause measured while recording this step, in ms (``recorded_gap_ms``).

    Written only by the recorder (上一步触摸结束 → 这一步触摸结束 的设备时间差),
    so hand-written steps simply have no such key. Malformed / negative /
    boolean payloads collapse to 0 — same defensive stance as ``delay_ms``.
    """
    raw = step.get("recorded_gap_ms")
    if raw is None or isinstance(raw, bool):
        return 0
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _step_gap_ms(step: Dict[str, Any], run_interval_ms: int, is_first: bool) -> int:
    """Wait BEFORE this step, in ms.

    Resolution order:

    1. An explicit ``delay_ms`` on the step always wins (``0`` = this step needs
       no wait). It REPLACES the run-level interval and any recorded pause —
       that is how a user silences one step's pacing.
    2. Otherwise the wait is ADDITIVE: ``step_interval_ms`` + ``recorded_gap_ms``.
       录制的实测节奏因此不会被默认间隔抹掉（也不是二选一），默认间隔对**每**
       一步都照常生效。
    3. Before the FIRST executed step there is nothing to space away from, so
       the wait is 0 — exactly the case when a run starts midway
       (``start_index``) or when the script's first step launches the app.
       A recorded pause is dropped there too: it was measured against a
       previous step this run never executed.
    """
    raw = step.get("delay_ms")
    if not isinstance(raw, bool):
        try:
            if raw is not None:
                return max(0, int(raw))
        except (TypeError, ValueError):
            pass
    if is_first:
        return 0
    return run_interval_ms + _recorded_gap_ms(step)


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
    use_ime: bool = True,
    task_id: Optional[str] = None,
    start_index: int = 0,
    step_interval_ms: int = 0,
    **kwargs,
) -> Dict[str, Any]:
    steps = steps or []
    started_t = time.time()
    started_iso = time.strftime("%Y-%m-%dT%H:%M:%S")

    # Run span + pacing (see module docstring). Both are coerced defensively —
    # they arrive straight off the wire and a bad value must never make the
    # whole run fail.
    interval_ms = _as_non_negative_int(step_interval_ms)
    requested_start = _as_int(start_index, 0)
    # Clamp: a stale UI (step deleted after the menu was built) must not turn
    # into "no step executed at all" — running the last step is the closest
    # honest interpretation, and the clamp is logged below.
    start_index = max(0, min(requested_start, len(steps) - 1)) if steps else 0

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
    # 「开启中文输入」(run setting): steps.py reads it to decide whether a
    # non-ASCII input may switch the device IME to ADBKeyboard.
    context.use_ime = bool(use_ime)

    result: Dict[str, Any] = {
        "success": True,
        "task_id": str(task_id or ""),
        # `total` counts the steps this run will actually attempt — starting
        # midway means fewer than len(steps) (passed + failed + total stay
        # mutually consistent, which is what the history row reads).
        "total": len(steps) - start_index,
        "passed": 0,
        "failed": 0,
        "cancelled": False,
        # run span / pacing in force (0-based start; step indices in `steps`
        # keep their original 1-based position)
        "start_index": start_index,
        "step_interval_ms": interval_ms,
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

    def _write_summary(report: Dict[str, Any], status: str) -> None:
        """Persist ``summary.json`` — the small index the history list reads.

        Written at run START (status ``running``) and again by
        ``_write_report`` (status ``finished``). The start marker is what makes
        an interrupted run identifiable at all: after a force-quit the file
        still says ``running`` while nothing is executing, which is how
        ``list_runs`` spots the orphan. Atomic (tmp + replace) so a kill can
        never leave a half-written index behind.
        """
        summary = {k: report.get(k) for k in _SUMMARY_KEYS}
        summary["status"] = status
        summary["screenshot_count"] = len(report.get("screenshots") or [])
        path = os.path.join(run_dir, SUMMARY_NAME)
        tmp = f"{path}.{uuid.uuid4().hex[:6]}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False)
            os.replace(tmp, path)
        except OSError as e:
            logger.warning(f"failed to write {SUMMARY_NAME}: {e}")
            try:
                if os.path.isfile(tmp):
                    os.remove(tmp)
            except OSError:
                pass

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
                # the failure policy in force for this run — a report that
                # says "2 passed / 1 failed, success=false" is much easier to
                # read once you know whether continuing was intended.
                "continue_on_error": bool(continue_on_error),
                "abort_on_crash": bool(abort_on_crash),
                # where the run started (0-based) and the pacing it used —
                # without these, "why is passed+failed < the script length?"
                # and "why did this run take an extra 30s?" are unanswerable.
                "start_index": result.get("start_index", 0),
                "step_interval_ms": result.get("step_interval_ms", 0),
                # whether this run was allowed to switch the IME for CJK input
                "use_ime": bool(use_ime),
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
            # Index AFTER the report: a dir with report.json but a stale
            # `running` summary still lists correctly (the handler prefers the
            # report when the summary claims a run that is not executing).
            _write_summary(report, "finished")
        except Exception as e:  # never let reporting break the run
            logger.warning(f"failed to write report.json: {e}")
        finally:
            # `_write_report` is the run's terminal write on EVERY exit path
            # (normal / cancel / crash / abort / raise), so deregistering here
            # keeps the in-process registry and the on-disk `finished` summary
            # in lockstep. A run that never deregisters would block its own
            # deletion and hide itself from the prune rules.
            runstate.mark_finished(str(task_id or ""))

    # Interrupted-run marker: from here on the history handler can tell this
    # run apart from a leftover directory. `_write_report` (every exit path)
    # rewrites it as finished, and the finally block deregisters the run.
    runstate.mark_started(str(task_id or ""), run_dir)
    _write_summary({
        "kind": "automation_run",
        "task_id": str(task_id or ""),
        "device_id": device_id or "",
        "package_name": package_name or "",
        "started_at": started_iso,
        "started_ts": started_t,
        "run_dir": run_dir,
        "total": len(steps) - start_index,
        "screenshots": [],
    }, "running")

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
    # Run span / pacing announcements — the console is the only place the user
    # can see that a run deliberately started midway or is padded with waits.
    if requested_start != start_index:
        _log(
            f"[WARN] start_index {requested_start} out of range (0..{n - 1})"
            f" — starting at step {start_index + 1} instead"
        )
    if start_index:
        _log(f"starting at step {start_index + 1}/{n} — steps 1..{start_index} are not executed")
    if interval_ms:
        _log(f"step interval {interval_ms}ms before each step")
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
        for i in range(start_index, n):
            step = steps[i]

            # Inter-step interval: run-level default + the recorded pause
            # (`recorded_gap_ms`, recording only), with per-step `delay_ms`
            # overriding both. Done BEFORE the cancel check on purpose: the
            # sleep is sliced, so a Stop pressed during it lands here within
            # ~50ms and the check right below reports "cancelled before step N".
            gap_ms = _step_gap_ms(step, interval_ms, i == start_index)
            if gap_ms > 0:
                _interruptible_sleep(context, gap_ms)

            # Cancel check at the top of every step.
            if context.is_cancelled():
                _log(f"cancelled before step {i + 1}/{n}")
                _shot(f"cancel-{i + 1}", i + 1)
                result["cancelled"] = True
                result["success"] = False
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

            # Re-anchor the crash watch after a step that legitimately
            # restarted the target (clear_app_data / launch_app). Without
            # this, the next iteration sees "pid gone/changed" and aborts the
            # run as a crash — the normal way a script relaunches an app.
            if watch and action in _RESTART_ACTIONS:
                watch_pid = get_app_pid(device_id, package_name)

            if ok:
                result["passed"] += 1
                continue

            # Step failed.
            result["failed"] += 1
            # A run with a failed step is never a success — including when the
            # policy is "continue": the remaining steps ran, but the outcome
            # the report records must not read as a clean pass.
            result["success"] = False
            # Per-step policy wins over the run-level flag; an unrecognised
            # value (typo, old script) falls back to the run setting instead of
            # being treated as "continue" — silently running on after a
            # failure the user asked to stop on is the expensive mistake.
            step_on_error = step.get("on_error")
            if step_on_error not in ("continue", "abort"):
                step_on_error = "continue" if continue_on_error else "abort"
            if step_on_error == "abort":
                _log(f"[FAIL] step {i + 1} aborted ({action}): {message}")
                sp = _shot(f"fail-{i + 1}", i + 1)
                if sp:
                    step_rec["screenshot"] = sp
                context.step(step_rec)
                return result
            _log(f"[FAIL] step {i + 1} continued ({action}): {message}")

        _log(
            f"done: {result['passed']}/{result['total']} passed"
            + (f", {result['failed']} failed" if result["failed"] else "")
        )
        return result
    finally:
        # IME restore lives here (not on each return path) so a step that
        # RAISES — execute_step swallows exceptions, but a stream/socket
        # error can still escape — cannot leave the device on ADBKeyboard.
        restore_ime(device_id)
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
