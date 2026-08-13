"""Wave 3 tests: workflow static validation.

Covers validate_workflow's tool-existence check, required-param presence
(expression-valued params treated as potentially resolvable), node-to-node
port type compatibility, dangling node references, and the defensive
connectivity checks (orphan / missing entry) which require bypassing
WorkflowDefinition.__post_init__ via object.__new__.
"""

import pytest

from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.validation import ValidationError, validate_workflow


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


def _bare_definition(**fields) -> WorkflowDefinition:
    """Build a WorkflowDefinition bypassing __post_init__ (for checks 4/5)."""
    definition = object.__new__(WorkflowDefinition)
    for name, value in fields.items():
        setattr(definition, name, value)
    return definition


def _text_port(name, required=True) -> Port:
    return Port(name, TypeAnnotation(BaseType.TEXT), required=required)


def _file_port(name, required=True) -> Port:
    return Port(name, TypeAnnotation(BaseType.FILE), required=required)


def _write_tool():
    return _StubTool("write", inputs=[_text_port("content")], outputs=[_file_port("path")])


# ---------------------------------------------------------------------------
# Tool existence + param presence
# ---------------------------------------------------------------------------

def test_valid_workflow_returns_no_errors():
    nodes = [_node("a", "write", params={"content": "x"})]
    errors = validate_workflow(_definition(nodes), _StubRegistry({"write": _write_tool()}))
    assert errors == []


def test_nonexistent_tool_flagged_as_error():
    nodes = [_node("a", "does.not.exist")]
    errors = validate_workflow(_definition(nodes), _StubRegistry())
    assert len(errors) == 1
    error = errors[0]
    assert error.node_id == "a"
    assert error.field == "tool"
    assert "does.not.exist" in error.message
    assert error.severity == "error"


def test_missing_required_param_flagged():
    nodes = [_node("a", "write", params={})]
    errors = validate_workflow(_definition(nodes), _StubRegistry({"write": _write_tool()}))
    assert any(
        error.field == "params" and "missing required input: content" in error.message
        for error in errors
    )


def test_expression_params_not_flagged():
    # $inputs.x satisfies presence: the key exists, so it is treated as
    # potentially resolvable at runtime.
    nodes = [_node("a", "write", params={"content": "$inputs.x"})]
    errors = validate_workflow(_definition(nodes), _StubRegistry({"write": _write_tool()}))
    assert errors == []


# ---------------------------------------------------------------------------
# Port compatibility
# ---------------------------------------------------------------------------

def test_dangling_node_reference_flagged():
    # $nodes.nope.outputs.path references a node that does not exist.
    read_tool = _StubTool("read", inputs=[_text_port("content")])
    nodes = [_node("a", "read", params={"content": "$nodes.nope.outputs.path"})]
    errors = validate_workflow(
        _definition(nodes), _StubRegistry({"read": read_tool})
    )
    assert any(
        error.field == "port_compatibility"
        and "unknown node 'nope'" in error.message
        and error.severity == "error"
        for error in errors
    )


def test_type_mismatch_is_warning():
    gen_tool = _StubTool("gen", outputs=[_file_port("path")])
    read_tool = _StubTool("read", inputs=[_text_port("content")])
    nodes = [
        _node("gen", "gen", next="read"),
        _node("read", "read", params={"content": "$nodes.gen.outputs.path"}),
    ]
    errors = validate_workflow(
        _definition(nodes), _StubRegistry({"gen": gen_tool, "read": read_tool})
    )
    assert any(
        error.field == "port_compatibility"
        and error.severity == "warning"
        and "type mismatch" in error.message
        and "gen.outputs.path" in error.message
        for error in errors
    )


# ---------------------------------------------------------------------------
# Connectivity (defensive checks 4/5 — __post_init__ bypassed)
# ---------------------------------------------------------------------------

def test_orphan_node_not_reachable_from_entry_flagged():
    nodes = [
        _node("a", "write", next="b", params={"content": "x"}),
        _node("b", "write", params={"content": "y"}),
        _node("c", "write", params={"content": "z"}),  # orphan
    ]
    definition = _bare_definition(
        name="wf",
        version="1.0",
        description="",
        inputs=[],
        outputs=[],
        nodes=nodes,
        edges=[],
    )
    errors = validate_workflow(
        definition,
        _StubRegistry({"write": _write_tool()}),
    )
    assert any(
        error.node_id == "c"
        and error.field == "connectivity"
        and "orphan" in error.message
        for error in errors
    )
    # a and b are reachable from the entry and must NOT be flagged.
    assert not any(error.node_id in ("a", "b") for error in errors)


def test_no_entry_node_flagged():
    nodes = [
        _node("a", "write", next="b"),
        _node("b", "write", next="a"),  # cycle -> no entry
    ]
    definition = _bare_definition(
        name="wf",
        version="1.0",
        description="",
        inputs=[],
        outputs=[],
        nodes=nodes,
        edges=[],
    )
    errors = validate_workflow(
        definition,
        _StubRegistry({"write": _write_tool()}),
    )
    assert any(
        error.node_id is None
        and error.field == "structure"
        and "no entry node" in error.message
        for error in errors
    )


def test_empty_workflow_is_trivially_valid():
    errors = validate_workflow(_definition([]), _StubRegistry())
    assert errors == []


# ---------------------------------------------------------------------------
# ValidationError shape
# ---------------------------------------------------------------------------

def test_validation_error_fields():
    error = ValidationError(
        node_id="a", field="tool", message="tool not found: x", severity="error"
    )
    assert error.node_id == "a"
    assert error.field == "tool"
    assert error.message == "tool not found: x"
    assert error.severity == "error"


def test_validation_error_default_severity_is_error():
    error = ValidationError(node_id=None, field="structure", message="m")
    assert error.severity == "error"
