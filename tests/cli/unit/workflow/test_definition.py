"""Wave 3 tests: WorkflowNode / WorkflowDefinition model.

Covers the schema validation rules (unique ids, `next` references, single
entry node, cycle detection), to_dict / from_dict and JSON-file roundtrips,
the `on_failure` / `retry` failure-handling fields, and the tolerant
`from_dict` that drops unknown keys left over from older schema revisions
(`condition` / `on_success` / `edges`).
"""

import json

import pytest

from app.protocol import BaseType, Port, TypeAnnotation
from app.workflow.definition import WorkflowDefinition, WorkflowNode


def _node(node_id, tool="file.read", **overrides) -> WorkflowNode:
    data = {"id": node_id, "tool": tool}
    data.update(overrides)
    return WorkflowNode(**data)


def _definition(nodes, **overrides) -> WorkflowDefinition:
    data = {"name": "wf", "nodes": nodes}
    data.update(overrides)
    return WorkflowDefinition(**data)


# ---------------------------------------------------------------------------
# Construction / validation rules
# ---------------------------------------------------------------------------

def test_valid_2_node_linear_workflow_constructs():
    nodes = [
        _node("write", "file.write", next="read"),
        _node("read", "file.read"),
    ]
    wf = _definition(nodes)
    assert wf.name == "wf"
    assert [node.id for node in wf.nodes] == ["write", "read"]


def test_duplicate_node_ids_raises_value_error():
    nodes = [
        _node("a", next="b"),
        _node("b"),
        _node("a", "file.write"),
    ]
    with pytest.raises(ValueError, match="duplicate node id: 'a'"):
        _definition(nodes)


def test_next_referencing_nonexistent_node_raises():
    with pytest.raises(ValueError, match="references unknown next node 'ghost'"):
        _definition([_node("a", next="ghost")])


def test_zero_entry_nodes_rejected():
    # a -> b -> a: both nodes have an incoming `next` reference.
    nodes = [_node("a", next="b"), _node("b", next="a")]
    with pytest.raises(ValueError, match="must have exactly one entry node"):
        _definition(nodes)


def test_two_entry_nodes_rejected():
    nodes = [_node("a"), _node("b")]
    with pytest.raises(ValueError, match="must have exactly one entry node"):
        _definition(nodes)


def test_cycle_detection_raises_value_error():
    # Single entry (n1) but the chain loops back at n2 -> n3 -> n2.
    nodes = [
        _node("n1", next="n2"),
        _node("n2", next="n3"),
        _node("n3", next="n2"),
    ]
    with pytest.raises(ValueError, match="cycle detected"):
        _definition(nodes)


def test_empty_node_id_raises():
    with pytest.raises(ValueError, match="non-empty string"):
        _node("")


def test_invalid_on_failure_raises():
    with pytest.raises(ValueError, match="invalid on_failure"):
        _node("a", on_failure="explode")


def test_empty_workflow_is_valid():
    wf = _definition([])
    assert wf.nodes == []
    assert wf.to_dict()["nodes"] == []


# ---------------------------------------------------------------------------
# Failure handling (on_failure / retry)
# ---------------------------------------------------------------------------

def test_legacy_retry_on_failure_string_raises():
    # The "retry:N" string form was removed: retries are expressed solely by
    # the integer `retry` field.
    with pytest.raises(ValueError, match="invalid on_failure 'retry:3'"):
        _node("a", on_failure="retry:3")


def test_on_failure_and_retry_fields_roundtrip():
    node = _node("a", on_failure="skip", retry=2)
    restored = WorkflowNode.from_dict(node.to_dict())
    assert restored.on_failure == "skip"
    assert restored.retry == 2


def test_retry_roundtrips_as_int():
    wf = _definition([_node("a", retry=3)])
    restored = WorkflowDefinition.from_dict(wf.to_dict())
    assert restored.nodes[0].retry == 3
    assert isinstance(restored.nodes[0].retry, int)
    assert wf.to_dict()["nodes"][0]["retry"] == 3


# ---------------------------------------------------------------------------
# Unknown keys are ignored on load (stale editor output)
# ---------------------------------------------------------------------------

def test_node_from_dict_ignores_removed_keys():
    node = WorkflowNode.from_dict(
        {
            "id": "a",
            "tool": "file.read",
            "condition": "inputs.x > 0",
            "on_success": "b",
        }
    )
    assert node.id == "a"
    assert node.tool == "file.read"
    assert not hasattr(node, "condition")
    assert not hasattr(node, "on_success")
    assert "condition" not in node.to_dict()
    assert "on_success" not in node.to_dict()


def test_definition_from_dict_ignores_edges_key():
    data = _definition([_node("a")]).to_dict()
    data["edges"] = [{"from": "a", "to": "b"}]
    restored = WorkflowDefinition.from_dict(data)
    assert [node.id for node in restored.nodes] == ["a"]
    assert not hasattr(restored, "edges")
    assert "edges" not in restored.to_dict()


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def test_to_dict_from_dict_roundtrip_preserves_fields():
    nodes = [
        _node("write", "file.write", params={"path": "out.txt", "content": "hi"}, next="read"),
        _node("read", "file.read", params={"path": "$nodes.write.outputs.path"}),
    ]
    wf = _definition(nodes, version="1.0", description="demo")
    restored = WorkflowDefinition.from_dict(wf.to_dict())
    assert restored == wf
    assert restored.name == "wf"
    assert restored.version == "1.0"
    assert [n.id for n in restored.nodes] == ["write", "read"]
    assert restored.nodes[0].params == {"path": "out.txt", "content": "hi"}


def test_ports_roundtrip_preserves_subtype():
    port = Port("aab_path", TypeAnnotation(BaseType.FILE, "apk"), required=True)
    wf = _definition(
        [_node("a")],
        inputs=[port],
        outputs=[Port("out", TypeAnnotation(BaseType.TEXT))],
    )
    restored = WorkflowDefinition.from_dict(wf.to_dict())
    assert restored.inputs[0].type.base == BaseType.FILE
    assert restored.inputs[0].type.subtype == "apk"
    assert restored.outputs[0].type.base == BaseType.TEXT
    assert restored == wf


def test_to_json_file_from_json_file_roundtrip(tmp_path):
    wf = _definition(
        [
            _node("write", "file.write", params={"path": "out.txt", "content": "hi"}, next="read"),
            _node("read", "file.read"),
        ],
        description="disk roundtrip",
    )
    path = tmp_path / "wf.json"
    wf.to_json_file(str(path))
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["name"] == "wf"
    restored = WorkflowDefinition.from_json_file(str(path))
    assert restored == wf


def test_from_json_file_missing_raises(tmp_path):
    with pytest.raises(ValueError, match="workflow file not found"):
        WorkflowDefinition.from_json_file(str(tmp_path / "nope.json"))
