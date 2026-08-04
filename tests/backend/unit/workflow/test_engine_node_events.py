"""T11 tests: real-time node lifecycle events from WorkflowEngine.

Verifies the engine emits node_started/completed/failed and workflow-
completed/failed events through context.workflow_stream during execute(),
in the correct order, and silently tolerates a missing stream handler.
"""

import pytest

from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.engine import ExecutionContext, WorkflowEngine
from app.workflow.streaming import WorkflowStreamHandler


class RecordingHandler:
    """A WorkflowStreamHandler-compatible recorder that captures every event.

    Each ``emit_*`` call appends a dict with the event type, the method name,
    and every keyword argument, plus a positional-index key so ordering
    bugs (batching, reordering) are detectable.
    """

    def __init__(self):
        self.events: list = []
        self._workflow_id = "wf-test"

    # -- WorkflowStreamHandler protocol ------------------------------------
    def emit_node_started(self, node_id: str, tool: str) -> None:
        self.events.append({"type": "node_started", "node_id": node_id, "tool": tool})

    def emit_node_output(self, node_id, data):
        self.events.append({"type": "node_output", "node_id": node_id, "data": data})

    def emit_node_completed(self, node_id: str, duration_ms: int) -> None:
        self.events.append(
            {"type": "node_completed", "node_id": node_id, "duration_ms": duration_ms}
        )

    def emit_node_failed(self, node_id: str, error: str) -> None:
        self.events.append(
            {"type": "node_failed", "node_id": node_id, "error": error}
        )

    def emit_workflow_completed(self, success: bool) -> None:
        self.events.append(
            {"type": "workflow_completed", "success": success}
        )

    def emit_workflow_failed(self, error: str) -> None:
        self.events.append({"type": "workflow_failed", "error": error})

    def emit_workflow_cancelled(self) -> None:
        self.events.append({"type": "workflow_cancelled"})


# -- helpers ---------------------------------------------------------------

def _node(node_id, tool="file.write", **overrides) -> WorkflowNode:
    data = {"id": node_id, "tool": tool}
    data.update(overrides)
    return WorkflowNode(**data)


def _definition(nodes) -> WorkflowDefinition:
    return WorkflowDefinition(name="wf", nodes=nodes)


def _engine() -> WorkflowEngine:
    return WorkflowEngine()


def _context(tmp_path, **overrides) -> ExecutionContext:
    data = {"work_dir": str(tmp_path)}
    data.update(overrides)
    return ExecutionContext(**data)


# ---------------------------------------------------------------------------
# (a) 2-node workflow emits node_started/completed per node IN ORDER,
#     then workflow completion
# ---------------------------------------------------------------------------

def test_two_node_workflow_emits_events_in_order(tmp_path):
    """Given a 2-node linear workflow (write → read), When the engine
    executes it with a recording stream handler, Then events appear as:
    node_started(write), node_completed(write), node_started(read),
    node_completed(read), workflow_completed."""
    recorder = RecordingHandler()
    nodes = [
        _node("write", "file.write", next="read",
              params={"path": "out.txt", "content": "hello"}),
        _node("read", "file.read", params={"path": "$nodes.write.outputs.path"}),
    ]
    ctx = _context(tmp_path, workflow_stream=recorder)

    result = _engine().execute(_definition(nodes), {}, ctx)

    assert result.success is True, f"workflow failed: {result.error}"
    assert len(recorder.events) == 5, f"expected 5 events, got {len(recorder.events)}"

    event_types = [e["type"] for e in recorder.events]
    assert event_types == [
        "node_started",
        "node_completed",
        "node_started",
        "node_completed",
        "workflow_completed",
    ], f"bad event order: {event_types}"

    # Check per-node content
    assert recorder.events[0]["node_id"] == "write"
    assert recorder.events[0]["tool"] == "file.write"
    assert recorder.events[1]["node_id"] == "write"
    assert isinstance(recorder.events[1]["duration_ms"], int)

    assert recorder.events[2]["node_id"] == "read"
    assert recorder.events[2]["tool"] == "file.read"
    assert recorder.events[3]["node_id"] == "read"
    assert isinstance(recorder.events[3]["duration_ms"], int)

    assert recorder.events[4]["success"] is True


# ---------------------------------------------------------------------------
# (b) failing node emits node_failed + workflow_failed carrying the error
# ---------------------------------------------------------------------------

def test_failing_node_emits_node_failed_and_workflow_failed(tmp_path):
    """Given a workflow whose first node fails (flow.assert with condition
    False), When executed, Then the engine emits node_started, node_failed
    with the error message, and workflow_failed — and does NOT emit
    node_completed or workflow_completed."""
    recorder = RecordingHandler()
    nodes = [
        _node("check", "flow.assert", next="write",
              params={"condition": False, "message": "boom"}),
        _node("write", "file.write", params={"path": "never.txt", "content": "x"}),
    ]
    ctx = _context(tmp_path, workflow_stream=recorder)

    result = _engine().execute(_definition(nodes), {}, ctx)

    assert result.success is False
    assert len(recorder.events) == 3, f"expected 3 events, got {len(recorder.events)}"

    event_types = [e["type"] for e in recorder.events]
    assert event_types == [
        "node_started",
        "node_failed",
        "workflow_failed",
    ], f"bad event order: {event_types}"

    assert recorder.events[0]["node_id"] == "check"
    assert "boom" in recorder.events[1]["error"]
    assert recorder.events[1]["node_id"] == "check"
    assert "boom" in recorder.events[2]["error"]


# ---------------------------------------------------------------------------
# (c) no stream_handler present → no crash (guard works)
# ---------------------------------------------------------------------------

def test_no_stream_handler_is_silent_no_crash(tmp_path):
    """Given a workflow with context.workflow_stream=None, When executed,
    Then the engine completes without raising an exception."""
    nodes = [
        _node("write", "file.write", next="read",
              params={"path": "out.txt", "content": "ok"}),
        _node("read", "file.read", params={"path": "$nodes.write.outputs.path"}),
    ]
    ctx = _context(tmp_path, workflow_stream=None)

    result = _engine().execute(_definition(nodes), {}, ctx)

    assert result.success is True
    assert result.outputs["content"] == "ok"


def test_unknown_tool_fails_emits_null_stream_guard(tmp_path):
    """An unknown tool node with context.workflow_stream=None doesn't crash."""
    nodes = [_node("a", "does.not.exist")]
    result = _engine().execute(_definition(nodes), {}, _context(tmp_path, workflow_stream=None))
    assert result.success is False
    assert "tool not found" in result.error


def test_on_failure_skip_emits_node_failed_then_continues(tmp_path):
    """When a node with on_failure=skip fails, emit node_failed but continue
    to the next node and finish with workflow_completed."""
    recorder = RecordingHandler()
    nodes = [
        _node("check", "flow.assert", next="write", on_failure="skip",
              params={"condition": False, "message": "skipped-boom"}),
        _node("write", "file.write", params={"path": "done.txt", "content": "x"}),
    ]
    ctx = _context(tmp_path, workflow_stream=recorder)

    result = _engine().execute(_definition(nodes), {}, ctx)

    assert result.success is True
    assert len(recorder.events) == 5, f"expected 5 events, got {len(recorder.events)}"

    event_types = [e["type"] for e in recorder.events]
    assert event_types == [
        "node_started",   # check
        "node_failed",    # check (skip)
        "node_started",   # write
        "node_completed", # write
        "workflow_completed",
    ], f"bad event order: {event_types}"

    assert "skipped-boom" in recorder.events[1]["error"]
