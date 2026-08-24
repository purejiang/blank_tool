"""T1 tests: shared event renderer + task-log tee in WorkflowStreamHandler.

Covers:
  - render_event_line() exact output for all 7 event types + unknown fallback
  - Tee writes 6 lifecycle types into _per_task_buffers[task_log_id]
  - Tee silent when task_log_id=None
  - Tee STILL writes when callback=None but task_log_id set
  - Child-namespacing rule: handlers with workflow_id != task_log_id prefix
    node_id with workflow_id in the log line, leaving callback unchanged
  - Root handlers (workflow_id == task_log_id) render un-prefixed
"""

import json

import pytest

from app.utils.task_log_writer import (
    _per_task_buffers,
    append_task_log,
    cleanup_task_log,
)
from app.workflow.streaming import (
    NODE_COMPLETED,
    NODE_FAILED,
    NODE_OUTPUT,
    NODE_STARTED,
    WORKFLOW_CANCELLED,
    WORKFLOW_COMPLETED,
    WORKFLOW_FAILED,
    WorkflowStreamHandler,
    render_event_line,
)


# ---------------------------------------------------------------------------
# render_event_line — all 7 known event types
# ---------------------------------------------------------------------------


def test_render_node_started():
    line = render_event_line(
        {"type": NODE_STARTED, "node_id": "n1", "tool": "file.read"}
    )
    assert line == "[node_started] n1 (file.read)"


def test_render_node_started_missing_tool():
    line = render_event_line({"type": NODE_STARTED, "node_id": "n1"})
    assert line == "[node_started] n1 ()"


def test_render_node_completed():
    line = render_event_line(
        {"type": NODE_COMPLETED, "node_id": "n1", "duration_ms": 42}
    )
    assert line == "[node_completed] n1 (42 ms)"


def test_render_node_completed_missing_duration():
    line = render_event_line({"type": NODE_COMPLETED, "node_id": "n1"})
    assert line == "[node_completed] n1 (? ms)"


def test_render_node_failed():
    line = render_event_line(
        {"type": NODE_FAILED, "node_id": "n1", "error": "boom"}
    )
    assert line == "[node_failed] n1: boom"


def test_render_node_failed_missing_error():
    line = render_event_line({"type": NODE_FAILED, "node_id": "n1"})
    assert line == "[node_failed] n1: "


def test_render_node_output():
    line = render_event_line(
        {"type": NODE_OUTPUT, "node_id": "n1", "data": {"path": "/tmp/a"}}
    )
    assert line == '[node_output] n1: {"path": "/tmp/a"}'


def test_render_node_output_empty_data():
    line = render_event_line({"type": NODE_OUTPUT, "node_id": "n1"})
    assert line == "[node_output] n1: {}"


def test_render_workflow_completed():
    line = render_event_line({"type": WORKFLOW_COMPLETED, "success": True})
    assert line == "[workflow_completed] success=True"


def test_render_workflow_failed():
    line = render_event_line({"type": WORKFLOW_FAILED, "error": "kapow"})
    assert line == "[workflow_failed] kapow"


def test_render_workflow_cancelled_bare_tag():
    """workflow_cancelled produces a bare tag (empty message)."""
    line = render_event_line({"type": WORKFLOW_CANCELLED})
    assert line == "[workflow_cancelled]"


def test_render_unknown_type_falls_back_to_json_dumps():
    line = render_event_line({"type": "custom_event", "x": 1})
    parsed = json.loads(line[line.index(" ") + 1 :])  # after "[custom_event] "
    assert parsed == {"type": "custom_event", "x": 1}


def test_render_missing_type_defaults_to_event():
    line = render_event_line({})
    assert line.startswith("[event] ")


# ---------------------------------------------------------------------------
# Tee: lifecycle types are written to the buffer
# ---------------------------------------------------------------------------

TASK_ID = "tee-test-1"

#: The 6 lifecycle types that the tee must capture.
_LIFECYCLE_EMIT_ARGS = [
    ("emit_node_started", ("n1", "file.read")),
    ("emit_node_completed", ("n1", 42)),
    ("emit_node_failed", ("n1", "boom")),
    ("emit_workflow_completed", (True,)),
    ("emit_workflow_failed", ("kapow",)),
    ("emit_workflow_cancelled", ()),
]


def _cleanup_tee_test():
    """Remove buffer for TASK_ID so tests don't leak across runs."""
    cleanup_task_log(TASK_ID)


@pytest.fixture(autouse=True)
def _clean_buffers():
    """Teardown: clean _per_task_buffers after every test."""
    yield
    # Clean any known task_ids that might have leaked
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
        # The last line should contain the event type tag
        event_type_tag = method_name.replace("emit_", "").replace("_", "")
        # map emit_workflow_completed → workflowcompleted, etc.
        # Actually, just check the buffer captured something
        assert any(
            "[" in line for line in lines
        ), f"buffer should contain rendered line for {method_name}"


class TestTeeSilentWhenTaskLogIdNone:
    """No writes when task_log_id is None (default)."""

    def test_no_task_log_id_no_buffer_write(self):
        handler = WorkflowStreamHandler(
            workflow_id="w1", callback=lambda e: None
        )
        before = len(_buffer_lines())
        handler.emit_node_started("n1", "file.read")
        handler.emit_node_completed("n1", 42)
        handler.emit_workflow_completed(True)
        assert len(_buffer_lines()) == before


class TestTeeWithCallbackNone:
    """Tee STILL writes when callback is None but task_log_id is set.

    This is the Metis fold (c): the tee must run BEFORE the callback-None
    early return.
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


class TestChildNamespacingRule:
    """Child handlers (workflow_id != task_log_id) prefix node_id in log.

    The callback receives the ORIGINAL node_id unchanged.
    """

    def test_child_prefixes_node_id_in_log(self):
        """workflow_id="sub1/sub", task_log_id="sub1", node_id="w"
        → log line has node_id "sub1/sub/w", callback has "w"."""
        events = []
        handler = WorkflowStreamHandler(
            workflow_id="sub1/sub",
            callback=events.append,
            task_log_id="sub1",
        )
        handler.emit_node_started("w", "flow.log")
        handler.emit_node_completed("w", 10)
        handler.emit_node_failed("w", "err")

        lines = _buffer_lines("sub1")
        assert len(lines) == 3, f"expected 3 lines, got {len(lines)}: {lines}"

        # Log lines have namespaced node_id
        assert "[node_started] sub1/sub/w (flow.log)" in lines
        assert "[node_completed] sub1/sub/w (10 ms)" in lines
        assert "[node_failed] sub1/sub/w: err" in lines

        # Callback received UNCHANGED node_id
        assert len(events) == 3
        assert all(e["node_id"] == "w" for e in events if "node_id" in e)

    def test_root_handler_renders_unprefixed(self):
        """workflow_id == task_log_id → no prefix on node_id."""
        events = []
        handler = WorkflowStreamHandler(
            workflow_id="sub1",
            callback=events.append,
            task_log_id="sub1",
        )
        handler.emit_node_started("w", "flow.log")
        handler.emit_node_completed("w", 5)

        lines = _buffer_lines("sub1")
        assert "[node_started] w (flow.log)" in lines
        assert "[node_completed] w (5 ms)" in lines

        # Callback unchanged
        assert events[0]["node_id"] == "w"

    def test_child_workflow_events_not_prefixed(self):
        """Workflow-level events (completed/failed/cancelled) have no
        node_id to prefix; they should render normally."""
        events = []
        handler = WorkflowStreamHandler(
            workflow_id="sub1/sub",
            callback=events.append,
            task_log_id="sub1",
        )
        handler.emit_workflow_completed(True)
        handler.emit_workflow_failed("sub-boom")
        handler.emit_workflow_cancelled()

        lines = _buffer_lines("sub1")
        assert "[workflow_completed] success=True" in lines
        assert "[workflow_failed] sub-boom" in lines
        assert "[workflow_cancelled]" in lines

        # Callback still received events
        assert len(events) == 3


class TestCallbackEventDictUnchanged:
    """The event dict passed to the callback is NEVER mutated by the tee."""

    def test_callback_event_not_mutated(self):
        events = []
        handler = WorkflowStreamHandler(
            workflow_id="sub1/sub",
            callback=events.append,
            task_log_id="sub1",
        )
        handler.emit_node_started("w", "file.read")
        assert events[0]["node_id"] == "w"
        assert events[0]["tool"] == "file.read"

    def test_callback_event_has_exact_fields(self):
        """Verify the exact schema of the callback event dict."""
        events = []
        handler = WorkflowStreamHandler(
            workflow_id="wf",
            callback=events.append,
            task_log_id="wf",
        )
        handler.emit_node_started("n1", "file.read")
        handler.emit_node_completed("n1", 100)

        assert events[0] == {
            "type": NODE_STARTED,
            "workflow_id": "wf",
            "node_id": "n1",
            "tool": "file.read",
        }
        assert events[1] == {
            "type": NODE_COMPLETED,
            "workflow_id": "wf",
            "node_id": "n1",
            "duration_ms": 100,
        }


# ---------------------------------------------------------------------------
# Exact content assertions for all 6 lifecycle types (not just tag presence)
# ---------------------------------------------------------------------------


def test_exact_node_started_line_in_buffer():
    handler = WorkflowStreamHandler(
        workflow_id=TASK_ID, callback=None, task_log_id=TASK_ID
    )
    handler.emit_node_started("read", "file.read")
    assert "[node_started] read (file.read)" in _buffer_lines()


def test_exact_node_completed_line_in_buffer():
    handler = WorkflowStreamHandler(
        workflow_id=TASK_ID, callback=None, task_log_id=TASK_ID
    )
    handler.emit_node_completed("read", 123)
    assert "[node_completed] read (123 ms)" in _buffer_lines()


def test_exact_node_failed_line_in_buffer():
    handler = WorkflowStreamHandler(
        workflow_id=TASK_ID, callback=None, task_log_id=TASK_ID
    )
    handler.emit_node_failed("read", "ZOG")
    assert "[node_failed] read: ZOG" in _buffer_lines()


def test_exact_workflow_completed_line_in_buffer():
    handler = WorkflowStreamHandler(
        workflow_id=TASK_ID, callback=None, task_log_id=TASK_ID
    )
    handler.emit_workflow_completed(False)
    assert "[workflow_completed] success=False" in _buffer_lines()


def test_exact_workflow_failed_line_in_buffer():
    handler = WorkflowStreamHandler(
        workflow_id=TASK_ID, callback=None, task_log_id=TASK_ID
    )
    handler.emit_workflow_failed("final error")
    assert "[workflow_failed] final error" in _buffer_lines()


def test_exact_workflow_cancelled_line_in_buffer():
    handler = WorkflowStreamHandler(
        workflow_id=TASK_ID, callback=None, task_log_id=TASK_ID
    )
    handler.emit_workflow_cancelled()
    assert "[workflow_cancelled]" in _buffer_lines()
