"""T1 tests: shared event renderer + task-log tee in WorkflowStreamHandler.

Covers:
  - render_event_line() exact output for every event type + unknown fallback
  - Tee writes each lifecycle type into _per_task_buffers[task_log_id]
  - Tee silent when task_log_id=None
  - Tee STILL writes when callback=None but task_log_id set
  - The tee never rewrites ids: the log line and the callback event agree
"""

import json
import re

import pytest

from app.utils.task_log_writer import (
    _per_task_buffers,
    append_task_log,
    cleanup_task_log,
)
from app.workflow.streaming import (
    LOG,
    NODE_COMPLETED,
    NODE_STARTED,
    WORKFLOW_CANCELLED,
    WORKFLOW_COMPLETED,
    WORKFLOW_FAILED,
    WorkflowStreamHandler,
    render_event_line,
)


# ---------------------------------------------------------------------------
# render_event_line — every known event type
# ---------------------------------------------------------------------------

#: Fixed timestamp passed as ``ts`` so exact assertions stay deterministic.
TS = "12:00:01"

#: Every line starts with ``[<ts>] `` — helper strips it for the asserts below.
_TS_PREFIX_RE = re.compile(r"^\[\d{1,2}:\d{2}:\d{2}\] ")


def _render(event: dict) -> str:
    """render_event_line with a fixed ts injected (unless the event has one)."""
    return render_event_line({**{"ts": TS}, **event})


def test_render_node_started():
    line = _render({"type": NODE_STARTED, "node_id": "n1", "tool": "file.read"})
    assert line == "[12:00:01] [node_started] n1 (file.read)"


def test_render_log_line():
    """Tool-level `log` events render as ``[log] <node> [<level>] <message>``."""
    line = _render(
        {"type": LOG, "level": "warning", "message": "样本文件 115 字节", "node_id": "n1"}
    )
    assert line == "[12:00:01] [log] n1 [warning] 样本文件 115 字节"


def test_render_log_line_without_node():
    """No node_id → the node segment is omitted."""
    assert _render({"type": LOG, "message": "hi"}) == "[12:00:01] [log] [info] hi"


def test_render_log_line_defaults_level_to_info():
    assert _render({"type": LOG, "message": "hi"}) == "[12:00:01] [log] [info] hi"


def test_render_node_started_missing_tool():
    line = _render({"type": NODE_STARTED, "node_id": "n1"})
    assert line == "[12:00:01] [node_started] n1 ()"


def test_render_node_completed_with_status():
    line = _render(
        {"type": NODE_COMPLETED, "node_id": "n1", "status": "ok", "duration_ms": 42}
    )
    assert line == "[12:00:01] [node_completed] n1 status=ok (42 ms)"


def test_render_node_completed_missing_duration():
    line = _render({"type": NODE_COMPLETED, "node_id": "n1", "status": "ok"})
    assert line == "[12:00:01] [node_completed] n1 status=ok (? ms)"


def test_render_node_completed_attempts_appended_when_above_one():
    line = _render(
        {
            "type": NODE_COMPLETED,
            "node_id": "n1",
            "status": "ok",
            "duration_ms": 42,
            "attempts": 3,
        }
    )
    assert line == "[12:00:01] [node_completed] n1 status=ok (42 ms, attempts=3)"


def test_render_node_completed_failed_includes_error():
    line = _render(
        {
            "type": NODE_COMPLETED,
            "node_id": "sub/r",
            "status": "failed",
            "duration_ms": 10,
            "error": "boom",
        }
    )
    assert line == "[12:00:01] [node_completed] sub/r status=failed (10 ms) error: boom"


def test_render_node_completed_skipped_without_error_suffix():
    line = _render(
        {"type": NODE_COMPLETED, "node_id": "n1", "status": "skipped", "duration_ms": 1}
    )
    assert "error:" not in line
    assert "status=skipped" in line


def test_render_workflow_completed():
    line = _render({"type": WORKFLOW_COMPLETED, "success": True})
    assert line == "[12:00:01] [workflow_completed] success=True"


def test_render_workflow_failed():
    line = _render({"type": WORKFLOW_FAILED, "error": "kapow"})
    assert line == "[12:00:01] [workflow_failed] kapow"


def test_render_workflow_cancelled_bare_tag():
    """workflow_cancelled produces a bare tag (empty message)."""
    line = _render({"type": WORKFLOW_CANCELLED})
    assert line == "[12:00:01] [workflow_cancelled]"


def test_render_missing_ts_falls_back_to_now():
    """No ``ts`` field → the current local time is stamped on the line."""
    line = render_event_line({"type": LOG, "message": "hi"})
    assert _TS_PREFIX_RE.match(line), f"missing time prefix: {line}"
    assert line.endswith("[log] [info] hi")


def test_render_unknown_type_falls_back_to_json_dumps():
    event = {"type": "custom_event", "x": 1, "ts": TS}
    line = render_event_line(event)
    prefix = f"[{TS}] [custom_event] "
    assert line.startswith(prefix)
    parsed = json.loads(line[len(prefix):])
    assert parsed == event


def test_render_missing_type_defaults_to_event():
    line = render_event_line({"ts": TS})
    assert line.startswith(f"[{TS}] [event] ")


# ---------------------------------------------------------------------------
# Tee: lifecycle types are written to the buffer
# ---------------------------------------------------------------------------

TASK_ID = "tee-test-1"

#: The lifecycle emits the tee must capture.
_LIFECYCLE_EMIT_ARGS = [
    ("emit_node_started", ("n1", "file.read")),
    ("emit_node_completed", ("n1", "ok", 42)),
    ("emit_workflow_completed", (True,)),
    ("emit_workflow_failed", ("kapow",)),
    ("emit_workflow_cancelled", ()),
]


@pytest.fixture(autouse=True)
def _clean_buffers():
    """Teardown: clean _per_task_buffers after every test."""
    yield
    for key in list(_per_task_buffers.keys()):
        cleanup_task_log(key)


def _buffer_lines(task_id: str = TASK_ID):
    return _per_task_buffers.get(task_id, [])


class TestTeeWritesLifecycleTypes:
    """Every lifecycle type is captured when task_log_id is set."""

    @pytest.mark.parametrize("method_name,args", _LIFECYCLE_EMIT_ARGS)
    def test_lifecycle_type_writes_to_buffer(self, method_name, args):
        handler = WorkflowStreamHandler(
            workflow_id="w1", callback=lambda e: None, task_log_id=TASK_ID
        )
        getattr(handler, method_name)(*args)
        lines = _buffer_lines()
        assert len(lines) >= 1, f"{method_name} did not write to buffer"
        assert any("[" in line for line in lines), (
            f"buffer should contain a rendered line for {method_name}"
        )


class TestTeeSilentWhenTaskLogIdNone:
    """No writes when task_log_id is None (default)."""

    def test_no_task_log_id_no_buffer_write(self):
        handler = WorkflowStreamHandler(
            workflow_id="w1", callback=lambda e: None
        )
        before = len(_buffer_lines())
        handler.emit_node_started("n1", "file.read")
        handler.emit_node_completed("n1", "ok", 42)
        handler.emit_workflow_completed(True)
        assert len(_buffer_lines()) == before


class TestTeeWithCallbackNone:
    """Tee STILL writes when callback is None but task_log_id is set.

    The tee must run BEFORE the callback-None early return.
    """

    def test_tee_writes_with_callback_none(self):
        handler = WorkflowStreamHandler(
            workflow_id="w1", callback=None, task_log_id=TASK_ID
        )
        before_count = len(_buffer_lines())
        handler.emit_node_started("n1", "file.read")
        after = _buffer_lines()
        assert len(after) > before_count, (
            "tee must write even when callback=None"
        )
        assert any(
            "node_started" in line and "n1" in line for line in after
        ), f"buffer missing node_started for n1: {after}"


class TestTeeAndCallbackAgree:
    """The tee renders exactly what the callback receives.

    Node ids are already run-root-relative paths (``<parent node>/<child
    node>``), so the handler must NOT rewrite them for the log — a hidden
    prefix was what produced doubled ids before.
    """

    def test_log_line_matches_callback_event(self):
        events = []
        handler = WorkflowStreamHandler(
            workflow_id="sub1",
            callback=events.append,
            task_log_id="sub1",
        )
        handler.emit_node_started("sub/w", "flow.log")
        handler.emit_node_completed("sub/w", "ok", 10)

        lines = _buffer_lines("sub1")
        assert len(lines) == 2
        # Time prefix varies (now()) — assert the dialect after it.
        assert _TS_PREFIX_RE.match(lines[0]) and lines[0].endswith(
            "[node_started] sub/w (flow.log)"
        )
        assert _TS_PREFIX_RE.match(lines[1]) and lines[1].endswith(
            "[node_completed] sub/w status=ok (10 ms)"
        )
        assert [e["node_id"] for e in events] == ["sub/w", "sub/w"]

    def test_workflow_level_events_render_normally(self):
        events = []
        handler = WorkflowStreamHandler(
            workflow_id="sub1",
            callback=events.append,
            task_log_id="sub1",
        )
        handler.emit_workflow_completed(True)
        handler.emit_workflow_failed("sub-boom")
        handler.emit_workflow_cancelled()

        lines = _buffer_lines("sub1")
        assert any(
            l.endswith("[workflow_completed] success=True") for l in lines
        ), f"missing workflow_completed line: {lines}"
        assert any(
            l.endswith("[workflow_failed] sub-boom") for l in lines
        ), f"missing workflow_failed line: {lines}"
        assert any(
            l.endswith("[workflow_cancelled]") for l in lines
        ), f"missing workflow_cancelled line: {lines}"
        assert len(events) == 3


class TestCallbackEventDictUnchanged:
    """The event dict passed to the callback is NEVER mutated by the tee."""

    def test_callback_event_not_mutated(self):
        events = []
        handler = WorkflowStreamHandler(
            workflow_id="sub1",
            callback=events.append,
            task_log_id="sub1",
        )
        handler.emit_node_started("w", "file.read")
        assert events[0]["node_id"] == "w"
        assert events[0]["tool"] == "file.read"

    def test_callback_event_has_exact_fields(self):
        """Verify the exact schema of the callback event dict.

        ``ts`` is the local emission time — validated by shape, then removed
        before the exact-field comparison.
        """
        events = []
        handler = WorkflowStreamHandler(
            workflow_id="wf",
            callback=events.append,
            run_id="run-9",
            task_log_id="wf",
        )
        handler.emit_node_started("n1", "file.read")
        handler.emit_node_completed("n1", "ok", 100)

        ts_re = re.compile(r"^\d{2}:\d{2}:\d{2}$")
        for event in events:
            assert ts_re.match(event.pop("ts"))

        assert events[0] == {
            "type": NODE_STARTED,
            "run_id": "run-9",
            "workflow_id": "wf",
            "node_id": "n1",
            "tool": "file.read",
        }
        assert events[1] == {
            "type": NODE_COMPLETED,
            "run_id": "run-9",
            "workflow_id": "wf",
            "node_id": "n1",
            "status": "ok",
            "duration_ms": 100,
            "attempts": 1,
        }


# ---------------------------------------------------------------------------
# Exact content assertions for the lifecycle types
# ---------------------------------------------------------------------------


def test_exact_node_started_line_in_buffer():
    handler = WorkflowStreamHandler(
        workflow_id=TASK_ID, callback=None, task_log_id=TASK_ID
    )
    handler.emit_node_started("read", "file.read")
    assert any(l.endswith("[node_started] read (file.read)") for l in _buffer_lines())


def test_exact_node_completed_line_in_buffer():
    handler = WorkflowStreamHandler(
        workflow_id=TASK_ID, callback=None, task_log_id=TASK_ID
    )
    handler.emit_node_completed("read", "ok", 123)
    assert any(
        l.endswith("[node_completed] read status=ok (123 ms)") for l in _buffer_lines()
    )


def test_exact_node_failed_line_in_buffer():
    handler = WorkflowStreamHandler(
        workflow_id=TASK_ID, callback=None, task_log_id=TASK_ID
    )
    handler.emit_node_completed("read", "failed", 5, error="ZOG")
    assert any(
        l.endswith("[node_completed] read status=failed (5 ms) error: ZOG")
        for l in _buffer_lines()
    )


def test_exact_workflow_completed_line_in_buffer():
    handler = WorkflowStreamHandler(
        workflow_id=TASK_ID, callback=None, task_log_id=TASK_ID
    )
    handler.emit_workflow_completed(False)
    assert any(
        l.endswith("[workflow_completed] success=False") for l in _buffer_lines()
    )


def test_exact_workflow_failed_line_in_buffer():
    handler = WorkflowStreamHandler(
        workflow_id=TASK_ID, callback=None, task_log_id=TASK_ID
    )
    handler.emit_workflow_failed("final error")
    assert any(l.endswith("[workflow_failed] final error") for l in _buffer_lines())


def test_exact_workflow_cancelled_line_in_buffer():
    handler = WorkflowStreamHandler(
        workflow_id=TASK_ID, callback=None, task_log_id=TASK_ID
    )
    handler.emit_workflow_cancelled()
    assert any(l.endswith("[workflow_cancelled]") for l in _buffer_lines())


def test_buffer_lines_carry_a_time_prefix():
    """Every tee'd line starts with ``[HH:MM:SS] `` — the panel parses it."""
    handler = WorkflowStreamHandler(
        workflow_id=TASK_ID, callback=None, task_log_id=TASK_ID
    )
    handler.emit_node_started("read", "file.read")
    handler.emit_workflow_completed(True)
    for line in _buffer_lines():
        assert _TS_PREFIX_RE.match(line), f"missing time prefix: {line}"
