"""
Contract tests for the automation recording handlers
(``app.handlers.automation_record_handler``).

Pins the streaming record lifecycle:
  * ``automation.record_start`` returns a stream init envelope
    (``{"stream_id": ...}``, ``finished: False``) and emits ``started`` /
    ``record_event`` / ``process_finished`` / ``record_stopped`` stream events.
  * ``automation.record_stop`` snapshots the accumulated steps, pops the
    session and returns them with the record device geometry.
  * one recording per device (liveness = session existence).

The handler module is imported lazily inside each test (never at module top)
so ``manager = ToolManager.instance()`` binds to the conftest mock, and
``run_adb`` is patched on the handler module's own binding name.
"""
import io
import time
from unittest.mock import MagicMock

import pytest

from app.utils.getevent_parser import GeteventStatefulParser


# ---------------------------------------------------------------------------
# helpers (line formats mirror tests/contracts/test_getevent_parser.py)
# ---------------------------------------------------------------------------

def _ev(ts: float, etype: str, code: str, value: str,
        dev: str = "/dev/input/event2") -> str:
    """One ``getevent -lt`` event line (spacing mirrors real output)."""
    return f"[  {ts:.6f}] {dev}: EV_{etype:<11} {code:<20} {value}"


def _pl_block(index: int, dev: str, name: str, key_lines, abs_lines) -> str:
    lines = [f"add device {index}: {dev}", f'  name: "{name}"', "  events: "]
    lines += [f"    KEY (0001): {k}" for k in key_lines]
    lines += [f"    ABS (0003): {a}" for a in abs_lines]
    return "\n".join(lines)


GETEVENT_PL_TEXT = (
    _pl_block(1, "/dev/input/event0", "mtk-kpd", ["014a  014b"], [])
    + "\n\n"
    + _pl_block(
        2, "/dev/input/event2", "goodix-ts",
        key_lines=["BTN_TOUCH"],
        abs_lines=[
            "ABS_MT_POSITION_X : value 0, min 0, max 3974, fuzz 0, flat 0, resolution 0",
            "ABS_MT_POSITION_Y : value 0, min 0, max 2198, fuzz 0, flat 0, resolution 0",
            "ABS_MT_TRACKING_ID : value 0, min 0, max 65535, fuzz 0, flat 0",
        ],
    )
    + "\n"
)

WM_SIZE_TEXT = "Physical size: 1080x600\n"

# one tap then one swipe (same coordinate anchors as test_getevent_parser.py)
SAMPLE_EVENT_STREAM = "\n".join([
    # tap: raw (852, 500) -> screen (232, 136), 50 ms
    _ev(100.000000, "ABS", "ABS_MT_TRACKING_ID", "00000d4f"),
    _ev(100.000000, "KEY", "BTN_TOUCH", "DOWN"),
    _ev(100.001000, "ABS", "ABS_MT_POSITION_X", "00000354"),
    _ev(100.001000, "ABS", "ABS_MT_POSITION_Y", "000001f4"),
    _ev(100.002000, "SYN", "SYN_REPORT", "00000000"),
    _ev(100.050000, "KEY", "BTN_TOUCH", "UP"),
    # swipe: (852, 900)->(232, 246) then (3100, 640)->(842, 175), 350 ms
    _ev(200.000000, "ABS", "ABS_MT_TRACKING_ID", "00000e10"),
    _ev(200.000000, "KEY", "BTN_TOUCH", "00000001"),
    _ev(200.001000, "ABS", "ABS_MT_POSITION_X", "00000354"),
    _ev(200.001000, "ABS", "ABS_MT_POSITION_Y", "00000384"),
    _ev(200.002000, "SYN", "SYN_REPORT", "00000000"),
    _ev(200.150000, "ABS", "ABS_MT_POSITION_X", "00000c1c"),
    _ev(200.150000, "ABS", "ABS_MT_POSITION_Y", "00000280"),
    _ev(200.151000, "SYN", "SYN_REPORT", "00000000"),
    _ev(200.350000, "KEY", "BTN_TOUCH", "00000000"),
]) + "\n"


def _expected_steps():
    """Reference parse of SAMPLE_EVENT_STREAM via the T1 parser."""
    p = GeteventStatefulParser(3974, 2198, 1080, 600)
    for line in SAMPLE_EVENT_STREAM.splitlines():
        p.feed(line)
    return p.pop_completed_steps()


class FakePopen:
    """Popen-like object whose stdout replays a fixed event stream."""

    def __init__(self, stream_text: str):
        self.pid = 12345
        self.stdout = io.StringIO(stream_text)
        self.stderr = io.StringIO("")
        self._returncode = 0

    def poll(self) -> int:
        return self._returncode

    def wait(self, timeout=None) -> int:
        return self._returncode


def _wire_fakes(monkeypatch, mock_tool_manager,
                stream_text: str = SAMPLE_EVENT_STREAM):
    """Patch the handler-module ``run_adb`` binding and install a scripted adb
    tool mock. Returns (handler_module, adb_mock)."""
    import app.handlers.automation_record_handler as arh

    def fake_run_adb(device_id, args, capture=True):
        if args[:2] == ["shell", "getevent"] and "-pl" in args:
            return {"returncode": 0, "stdout": GETEVENT_PL_TEXT}
        if args[:2] == ["shell", "wm"] and args[2:] == ["size"]:
            return {"returncode": 0, "stdout": WM_SIZE_TEXT}
        raise AssertionError(f"unexpected run_adb args: {args}")

    # patch the handler module's own binding (from-import), not the source module
    monkeypatch.setattr(
        "app.handlers.automation_record_handler.run_adb", fake_run_adb
    )
    # the module-level ``manager = ToolManager.instance()`` binds once per
    # pytest session (first fixture that triggers the import), so rebind it
    # to THIS test's mock manager or scripted tool mocks are never seen
    monkeypatch.setattr(arh, "manager", mock_tool_manager)

    adb_mock = MagicMock()
    adb_mock.name = "adb"
    adb_mock.is_valid = True
    adb_mock.tool_path = "/fake/path/adb"
    adb_mock.execute.side_effect = lambda command, context=None: (
        FakePopen(stream_text)
        if context is not None and getattr(context, "stream", False)
        else {"returncode": 0, "stdout": "", "stderr": ""}
    )
    mock_tool_manager.get_tool.side_effect = None
    mock_tool_manager.get_tool.return_value = adb_mock
    return arh, adb_mock


def _join_stream(api_handler, stream_id, timeout: float = 5.0):
    """Wait for the stream worker: prefer the registered thread handle, else
    poll captured events with a deadline (never blocks forever)."""
    entry = api_handler.streaming_threads.get(stream_id)
    if entry is not None:
        entry[0].join(timeout=timeout)
        return
    deadline = time.time() + 2
    while time.time() < deadline:
        for c in api_handler._captured:
            if c.get("stream_id") != stream_id:
                continue
            if c.get("finished") or c.get("result", {}).get("type") == "record_stopped":
                return
        time.sleep(0.05)


# ---------------------------------------------------------------------------
# 1-2. record_start
# ---------------------------------------------------------------------------

class TestAutomationRecordStart:
    def test_start_forces_remote_pty_via_shell_tt(
            self, api_handler, mock_tool_manager, monkeypatch):
        """getevent must run under a forced remote PTY (``shell -tt``).

        Launched from Popen, adb's stdin is a pipe, so plain ``adb shell``
        allocates no PTY and the device-side getevent writes to a fully
        buffered stdout — events never reach the recorder in real time.
        (adb itself warns: "Remote PTY will not be allocated because stdin
        is not a terminal. Use multiple -t options to force remote PTY
        allocation.")
        """
        arh, adb_mock = _wire_fakes(monkeypatch, mock_tool_manager)
        arh._SESSIONS.clear()
        request = {
            "id": 26,
            "method": "automation.record_start",
            "params": {"device_id": "devTT"},
        }
        response = api_handler.handle_request(request)
        stream_id = response["result"]["stream_id"]
        _join_stream(api_handler, stream_id)

        stream_calls = []
        for call in adb_mock.execute.call_args_list:
            ctx = call[1].get("context") if call[1].get("context") is not None else (
                call[0][1] if len(call[0]) > 1 else None
            )
            if ctx is not None and getattr(ctx, "stream", False):
                stream_calls.append(call)
        assert stream_calls, "record_start must issue a streaming adb execute"
        command = stream_calls[0][0][0]
        assert command == [
            "-s", "devTT", "shell", "-tt", "getevent", "-lt",
            "/dev/input/event2",
        ]

    def test_start_returns_stream_init_envelope(
            self, api_handler, mock_tool_manager, monkeypatch):
        arh, _adb = _wire_fakes(monkeypatch, mock_tool_manager)
        arh._SESSIONS.clear()
        request = {
            "id": 21,
            "method": "automation.record_start",
            "params": {"device_id": "devA"},
        }
        response = api_handler.handle_request(request)
        assert response["id"] == 21
        assert response["finished"] is False
        stream_id = response["result"]["stream_id"]
        assert isinstance(stream_id, str) and stream_id
        _join_stream(api_handler, stream_id)

    def test_start_emits_record_events_and_record_stopped(
            self, api_handler, mock_tool_manager, monkeypatch):
        arh, _adb = _wire_fakes(monkeypatch, mock_tool_manager)
        arh._SESSIONS.clear()
        request = {
            "id": 22,
            "method": "automation.record_start",
            "params": {"device_id": "devB"},
        }
        response = api_handler.handle_request(request)
        stream_id = response["result"]["stream_id"]
        _join_stream(api_handler, stream_id)

        events = [
            c["result"] for c in api_handler._captured
            if c.get("stream_id") == stream_id and "result" in c
        ]
        expected = _expected_steps()
        types = [e["type"] for e in events]
        assert types == (
            ["started"]
            + ["record_event"] * len(expected)
            + ["process_finished", "record_stopped"]
        )
        assert events[0]["payload"] == {"process_id": "12345"}
        assert events[-2]["payload"] == {"process_id": "12345", "return_code": 0}
        for i, step in enumerate(expected, start=1):
            assert events[i]["payload"]["index"] == i
            assert events[i]["payload"]["step"] == step
        assert events[-1]["payload"] == {"count": len(expected)}
        # natural exit popped the session (sentinel semantics)
        assert "devB" not in arh._SESSIONS


# ---------------------------------------------------------------------------
# 3-4. record_stop
# ---------------------------------------------------------------------------

class TestAutomationRecordStop:
    def test_stop_returns_steps_and_record_device(
            self, api_handler, mock_tool_manager, monkeypatch):
        arh, adb_mock = _wire_fakes(monkeypatch, mock_tool_manager)
        arh._SESSIONS.clear()
        arh._SESSIONS["devC"] = {
            "process_id": "9999",
            "parser": None,
            "steps": [{"action": "tap", "x": 232, "y": 136}],
            "screen": (1080, 600),
            "device_path": "/dev/input/event2",
        }
        request = {
            "id": 23,
            "method": "automation.record_stop",
            "params": {"device_id": "devC"},
        }
        response = api_handler.handle_request(request)
        assert response["finished"] is True
        result = response["result"]
        assert result["type"] == "success"
        assert result["payload"]["steps"] == [{"action": "tap", "x": 232, "y": 136}]
        assert result["payload"]["record_device"] == {
            "serial": "devC", "screen_w": 1080, "screen_h": 600,
        }
        adb_mock.stop_process.assert_called_once_with("9999")
        assert "devC" not in arh._SESSIONS

    def test_stop_without_session_returns_error_envelope(
            self, api_handler, mock_tool_manager, monkeypatch):
        arh, _adb = _wire_fakes(monkeypatch, mock_tool_manager)
        arh._SESSIONS.clear()
        request = {
            "id": 24,
            "method": "automation.record_stop",
            "params": {"device_id": "devD"},
        }
        response = api_handler.handle_request(request)
        assert response["finished"] is True
        result = response["result"]
        assert result["type"] == "error"
        assert "no active recording" in result["payload"]["message"]


# ---------------------------------------------------------------------------
# 5. session mutex: second start on the same device
# ---------------------------------------------------------------------------

class TestAutomationRecordMutex:
    def test_second_start_on_same_device_emits_error_event(
            self, api_handler, mock_tool_manager, monkeypatch):
        arh, _adb = _wire_fakes(monkeypatch, mock_tool_manager)
        arh._SESSIONS.clear()
        # white-box preseed: a session already alive on this device
        arh._SESSIONS["devX"] = {
            "process_id": "fake",
            "parser": None,
            "steps": [],
            "screen": (1080, 600),
            "device_path": "/dev/input/event2",
        }
        request = {
            "id": 25,
            "method": "automation.record_start",
            "params": {"device_id": "devX"},
        }
        response = api_handler.handle_request(request)
        stream_id = response["result"]["stream_id"]
        _join_stream(api_handler, stream_id)

        errors = [
            c["result"] for c in api_handler._captured
            if c.get("stream_id") == stream_id and "result" in c
            and c["result"].get("type") == "error"
        ]
        assert errors, "expected an error stream event for duplicate start"
        assert "already active" in errors[0]["payload"]["message"]
