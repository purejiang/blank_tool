"""T11 tests: real-time node lifecycle events from WorkflowEngine.

Verifies the engine emits node_started / node_completed (with status and
attempts) and workflow-completed / workflow-failed events through
context.workflow_stream during execute(), in the correct order, that every
node gets exactly one terminal event, and that a missing stream handler is
tolerated silently.
"""

import pytest

from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.engine import ExecutionContext, WorkflowEngine
from app.workflow.streaming import WorkflowStreamHandler


class RecordingHandler:
    """A WorkflowStreamHandler-compatible recorder that captures every event."""

    def __init__(self):
        self.events: list = []
        self.workflow_id = "wf-test"

    # -- WorkflowStreamHandler protocol ------------------------------------
    def emit_node_started(self, node_id: str, tool: str) -> None:
        self.events.append({"type": "node_started", "node_id": node_id, "tool": tool})

    def emit_node_completed(
        self, node_id: str, status: str, duration_ms: int, **kwargs
    ) -> None:
        self.events.append(
            {
                "type": "node_completed",
                "node_id": node_id,
                "status": status,
                "duration_ms": duration_ms,
                "attempts": kwargs.get("attempts", 1),
                "error": kwargs.get("error"),
            }
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
    assert recorder.events[1]["status"] == "ok"
    assert isinstance(recorder.events[1]["duration_ms"], int)

    assert recorder.events[2]["node_id"] == "read"
    assert recorder.events[2]["tool"] == "file.read"
    assert recorder.events[3]["node_id"] == "read"
    assert recorder.events[3]["status"] == "ok"
    assert isinstance(recorder.events[3]["duration_ms"], int)

    assert recorder.events[4]["success"] is True


# ---------------------------------------------------------------------------
# (b) failing node emits a failed node_completed + workflow_failed
# ---------------------------------------------------------------------------

def test_failing_node_emits_failed_completion_and_workflow_failed(tmp_path):
    """Given a workflow whose first node fails (flow.assert with condition
    False), When executed, Then the engine emits node_started, a
    node_completed with status="failed" carrying the error, and
    workflow_failed — and no node_completed for the second node."""
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
        "node_completed",
        "workflow_failed",
    ], f"bad event order: {event_types}"

    assert recorder.events[0]["node_id"] == "check"
    assert recorder.events[1]["node_id"] == "check"
    assert recorder.events[1]["status"] == "failed"
    assert "boom" in recorder.events[1]["error"]
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


def test_on_failure_skip_still_gets_a_terminal_event(tmp_path):
    """A skipped node must still emit its single terminal event, otherwise a
    UI keyed on node_completed shows it as running forever."""
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
        "node_completed", # check (skipped)
        "node_started",   # write
        "node_completed", # write
        "workflow_completed",
    ], f"bad event order: {event_types}"

    assert recorder.events[1]["status"] == "skipped"
    assert "skipped-boom" in recorder.events[1]["error"]
    assert recorder.events[3]["status"] == "ok"
    # The skipped node is recorded with the skip status, not as a success
    assert result.node_results["check"]["status"] == "skipped"
    assert result.node_results["check"]["error"] == "skipped-boom"


def test_retried_node_reports_attempts(tmp_path):
    """attempts on node_completed tells the consumer how many tries it took."""
    recorder = RecordingHandler()

    class _Flaky:
        name = "test.flaky"
        calls = 0

        def execute(self, inputs, context):
            type(self).calls += 1
            if type(self).calls == 1:
                raise RuntimeError("first attempt fails")
            return {"ok": True}

    class _Registry:
        def get_tool(self, name):
            return _Flaky() if name == "test.flaky" else None

    _Flaky.calls = 0
    nodes = [_node("flaky", "test.flaky", retry=1)]
    ctx = _context(tmp_path, workflow_stream=recorder)
    result = WorkflowEngine(registry=_Registry()).execute(_definition(nodes), {}, ctx)

    assert result.success is True
    completed = [e for e in recorder.events if e["type"] == "node_completed"]
    assert completed[0]["attempts"] == 2
    assert result.node_results["flaky"]["attempts"] == 2
