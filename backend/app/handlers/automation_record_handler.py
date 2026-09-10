#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automation recording handlers.

``automation.record_start`` probes the touchscreen via ``getevent -pl``,
spawns ``adb shell getevent -lt <device>`` as a streaming process, feeds every
line through the stateful getevent parser and pushes completed tap/swipe steps
as ``record_event`` stream events. ``automation.record_stop`` terminates the
recording process and returns the accumulated steps plus device geometry.

Session liveness is defined by existence in ``_SESSIONS``: registered on
start, popped by ``record_stop`` or by the stream thread's natural-exit
sentinel (which only announces ``record_stopped`` when the session was still
registered, i.e. the user did not stop it explicitly).
"""

import threading
from typing import Any, Dict

from app.tools.tool_manager import ToolManager
from app.common.base_executor import CommandExecutionContext
from app.common.exceptions import ToolNotFoundError, ToolException
from app.automation.adb import run_adb
from app.utils.getevent_parser import (
    GeteventStatefulParser,
    find_touchscreen,
    parse_screen_size,
)
from app.common.decorators import streaming, logs_errors
from app.utils.logger import Logger

logger = Logger.get_logger("AutomationRecordHandler")

manager = ToolManager.instance()

# device_id -> {process_id, parser, steps, screen, device_path}
_SESSIONS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


@streaming
@logs_errors("AutomationRecordHandler")
def record_start(params, stream_handler):
    device_id = params.get("device_id")

    # 1. probe the touchscreen device + axis maxima
    pl = run_adb(device_id, ["shell", "getevent", "-pl"])
    try:
        touchscreen = find_touchscreen(pl.get("stdout", "") or "")
    except ValueError as e:
        stream_handler({"type": "error", "payload": {"message": str(e)}})
        return
    device_path = str(touchscreen["device"])

    # 2. screen geometry (override size wins over physical)
    wm = run_adb(device_id, ["shell", "wm", "size"])
    screen_w, screen_h = parse_screen_size(wm.get("stdout", "") or "")

    # 3. one recording per device; liveness = session existence
    with _LOCK:
        if device_id in _SESSIONS:
            raise ToolException("recording already active on this device")

    # 4. spawn the streaming getevent process (lifecycle mirrors start_logcat)
    adb_tool = manager.get_tool("adb")
    if not adb_tool or not adb_tool.is_valid:
        raise ToolNotFoundError("adb")

    parser = GeteventStatefulParser(
        touchscreen["max_x"], touchscreen["max_y"], screen_w, screen_h
    )
    session = {
        "process_id": "",
        "parser": parser,
        "steps": [],
        "screen": (screen_w, screen_h),
        "device_path": device_path,
    }

    context = CommandExecutionContext(stream=True)
    # "-tt" forces a remote PTY. Launched from Popen, adb's stdin is a pipe,
    # so plain `adb shell getevent` runs without a PTY and the device-side
    # getevent writes to a FULLY-BUFFERED (4KB) stdout — taps never reach us
    # until the buffer fills (or the process dies), so the UI shows nothing.
    # With a PTY, stdout is line-buffered and events stream in real time.
    # The PTY adds \r line endings, which the parser's `\s*$` regex absorbs.
    process = adb_tool.execute(
        ["-s", device_id, "shell", "-tt", "getevent", "-lt", device_path], context
    )
    process_id = f"{process.pid}"
    session["process_id"] = process_id
    adb_tool._running_processes[process_id] = process
    with _LOCK:
        _SESSIONS[device_id] = session

    try:
        stream_handler({"type": "started", "payload": {"process_id": process_id}})
        for line in iter(process.stdout.readline, ''):
            if not line:
                break
            parser.feed(line)
            for step in parser.pop_completed_steps():
                session["steps"].append(step)
                stream_handler({
                    "type": "record_event",
                    "payload": {"index": len(session["steps"]), "step": step},
                })
    except Exception as e:
        logger.warning(f"record stream read error: {e}")
    finally:
        try:
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
        except Exception:
            pass
        rc = process.wait()
        stream_handler({
            "type": "process_finished",
            "payload": {"process_id": process_id, "return_code": rc},
        })
        # Sentinel pop: a still-registered session means the stream ended on
        # its own -> announce the stop; after record_stop the session is
        # already gone and no event is sent.
        session = _SESSIONS.pop(device_id, None)
        if session is not None:
            stream_handler({
                "type": "record_stopped",
                "payload": {"count": len(session["steps"])},
            })


@logs_errors("AutomationRecordHandler")
def record_stop(params, stream_handler):
    device_id = params.get("device_id")

    with _LOCK:
        session = _SESSIONS.get(device_id)
    if session is None:
        raise ToolException("no active recording")

    adb_tool = manager.get_tool("adb")
    if not adb_tool:
        raise ToolNotFoundError("adb")
    adb_tool.stop_process(session["process_id"])

    with _LOCK:
        steps = list(session["steps"])
        _SESSIONS.pop(device_id, None)

    return {
        "steps": steps,
        "record_device": {
            "serial": device_id,
            "screen_w": session["screen"][0],
            "screen_h": session["screen"][1],
        },
    }


API_MAP = {
    "automation.record_start": record_start,
    "automation.record_stop": record_stop,
}
