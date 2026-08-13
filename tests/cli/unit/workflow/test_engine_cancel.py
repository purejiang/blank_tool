"""Verify that the workflow engine breaks at the next node boundary
when is_cancelled returns True for the workflow_id.
"""

from unittest.mock import patch

import pytest

from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.engine import ExecutionContext, WorkflowEngine


class _StubRegistry:
    """Minimal tool registry returning None for any tool — tests never
    actually call tool.execute because cancellation kicks in first."""

    def get_tool(self, name):
        return None


def _node(node_id, tool="noop.tool", **overrides) -> WorkflowNode:
    data: dict = {"id": node_id, "tool": tool}
    data.update(overrides)
    return WorkflowNode(**data)


# ---------------------------------------------------------------------------
# Cancellation before the first node
# ---------------------------------------------------------------------------

def test_cancel_before_first_node_stops_immediately(tmp_path):
    """When is_cancelled returns True before the first node, the engine
    returns WorkflowResult(success=False, error='workflow cancelled')
    and no nodes are executed."""
    nodes = [
        _node("a", next="b"),
        _node("b"),
    ]
    definition = WorkflowDefinition(name="wf", nodes=nodes)
    engine = WorkflowEngine(registry=_StubRegistry())
    context = ExecutionContext(work_dir=str(tmp_path), task_id="task-1")

    with patch("app.workflow.engine.is_cancelled", return_value=True):
        result = engine.execute(definition, {}, context)

    assert result.success is False
    assert result.error == "workflow cancelled"
    # No nodes should have been recorded (broke before executing any)
    assert len(result.node_results) == 0


# ---------------------------------------------------------------------------
# Cancellation between nodes (after 1st node succeeds, before 2nd)
# ---------------------------------------------------------------------------

def test_cancel_between_nodes_stops_after_first_success(tmp_path):
    """When is_cancelled returns False on the first check but True on the
    second, the first node should be recorded and the second skipped."""
    nodes = [
        _node("a", "file.write", next="b",
              params={"path": "a.txt", "content": "hello"}),
        _node("b", "file.read",
              params={"path": "$nodes.a.outputs.path"}),
    ]
    definition = WorkflowDefinition(name="wf", nodes=nodes)
    engine = WorkflowEngine(registry=_StubRegistry())
    context = ExecutionContext(work_dir=str(tmp_path), task_id="task-2")

    call_count = [0]

    def _is_cancelled(workflow_id):
        call_count[0] += 1
        # First call (before node "a"): False — let it run
        # Second call (before node "b"): True — cancel
        return call_count[0] >= 2

    with patch("app.workflow.engine.is_cancelled", side_effect=_is_cancelled):
        result = engine.execute(definition, {"message": "hello"}, context)

    assert result.success is False
    assert result.error == "workflow cancelled"
    # Only node "a" should be recorded; node "b" was skipped
    assert "a" in result.node_results
    assert "b" not in result.node_results
    # The first node should have completed (it was a real file.write)
    assert result.node_results["a"]["error"] is None
