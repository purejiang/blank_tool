"""Verify that the workflow engine breaks at the next checkpoint when
is_cancelled returns True for the run, and that a cancelled run is reported
as cancelled (neither a success nor a failure).
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
    returns WorkflowResult(success=False, cancelled=True) and no nodes run."""
    nodes = [
        _node("a", next="b"),
        _node("b"),
    ]
    definition = WorkflowDefinition(name="wf", nodes=nodes)
    engine = WorkflowEngine(registry=_StubRegistry())
    context = ExecutionContext(work_dir=str(tmp_path), run_id="run-1")

    with patch("app.workflow.engine.is_cancelled", return_value=True):
        result = engine.execute(definition, {}, context)

    assert result.success is False
    assert result.cancelled is True
    assert result.status == "cancelled"
    assert result.error == "workflow cancelled"
    # No nodes should have been recorded (broke before executing any)
    assert len(result.node_results) == 0


# ---------------------------------------------------------------------------
# Cancellation between nodes (after 1st node succeeds, before 2nd)
# ---------------------------------------------------------------------------

def test_cancel_between_nodes_stops_after_first_success(tmp_path):
    """A cancel that lands while node "a" runs must stop the workflow before
    node "b": node "a" is recorded as successful, node "b" never runs."""
    from app.protocol import PortSet
    from app.tools.builtin.base import BuiltinTool

    flag = {"cancelled": False}

    class _FlipTool(BuiltinTool):
        """Node "a": succeeds and flips the cancel flag."""

        name = "test.flip"
        description = "flips the cancel flag"
        ports = PortSet(inputs=[], outputs=[])

        def execute(self, inputs, context):
            flag["cancelled"] = True
            return {"done": True}

    class _Registry:
        def get_tool(self, name):
            return _FlipTool() if name == "test.flip" else None

    nodes = [
        _node("a", "test.flip", next="b"),
        _node("b", "test.flip"),
    ]
    definition = WorkflowDefinition(name="wf", nodes=nodes)
    engine = WorkflowEngine(registry=_Registry())
    context = ExecutionContext(work_dir=str(tmp_path), run_id="run-2")

    with patch(
        "app.workflow.engine.is_cancelled",
        side_effect=lambda _target: flag["cancelled"],
    ):
        result = engine.execute(definition, {}, context)

    assert result.success is False
    assert result.cancelled is True
    assert result.error == "workflow cancelled"
    # Only node "a" should be recorded; node "b" was skipped
    assert "a" in result.node_results
    assert "b" not in result.node_results
    assert result.node_results["a"]["status"] == "ok"
    assert result.node_results["a"]["error"] is None
