"""Wave: reserved DAG-mode fields are rejected at validation time.

``condition`` and ``on_success`` are stored on WorkflowNode for forward
compatibility, but the linear executor does not honor them: ``condition``
raises NotImplementedError at runtime (engine.py) and ``on_success`` is
silently ignored.  validate_workflow must reject ``condition`` as an error
and surface ``on_success`` as a warning, so the user hears about it before
execution rather than as a mid-run crash.
"""

import pytest

from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.validation import validate_workflow


class _StubTool:
    """Minimal tool with a PortSet contract, as consumed by the validator."""

    def __init__(self, name, inputs=None, outputs=None):
        self.name = name
        self.ports = PortSet(inputs=inputs or [], outputs=outputs or [])


class _StubRegistry:
    def __init__(self, tools=None):
        self._tools = dict(tools or {})

    def get_tool(self, name):
        return self._tools.get(name)


def _node(node_id, tool, **overrides) -> WorkflowNode:
    data = {"id": node_id, "tool": tool}
    data.update(overrides)
    return WorkflowNode(**data)


def _definition(nodes, **overrides) -> WorkflowDefinition:
    data = {"name": "wf", "nodes": nodes}
    data.update(overrides)
    return WorkflowDefinition(**data)


def _write_tool():
    return _StubTool(
        "write", inputs=[Port("content", TypeAnnotation(BaseType.TEXT))], outputs=[]
    )


def _registry():
    return _StubRegistry({"write": _write_tool()})


def test_condition_set_is_validation_error():
    nodes = [
        _node(
            "a",
            "write",
            params={"content": "x"},
            condition="inputs.x != null",
        )
    ]
    errors = validate_workflow(_definition(nodes), _registry())
    assert any(
        error.node_id == "a"
        and error.severity == "error"
        and "condition" in error.message
        for error in errors
    )


def test_condition_null_passes():
    nodes = [_node("a", "write", params={"content": "x"}, condition=None)]
    errors = validate_workflow(_definition(nodes), _registry())
    assert errors == []


def test_on_success_set_is_warning():
    nodes = [
        _node("a", "write", params={"content": "x"}, on_success="next_node")
    ]
    errors = validate_workflow(_definition(nodes), _registry())
    assert any(
        error.node_id == "a"
        and error.severity == "warning"
        and "on_success" in error.message
        for error in errors
    )


def test_condition_is_error_not_warning():
    # A set condition must be an error, never downgraded to a warning.
    nodes = [
        _node("a", "write", params={"content": "x"}, condition="1 == 1")
    ]
    errors = validate_workflow(_definition(nodes), _registry())
    assert any(
        error.node_id == "a" and "condition" in error.message for error in errors
    )
    assert all(error.severity != "warning" for error in errors if "condition" in error.message)
