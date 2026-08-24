"""Tests: flow.foreach loop primitive (iteration, flattening, pass rule, guards)."""

import json
import os
from types import SimpleNamespace

import pytest

from app.common.exceptions import ToolException
from app.template.store import FileTemplateStore
from app.tools.builtin.base import ToolContext
from app.tools.builtin.flow_tools import FlowForeach
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.engine import ExecutionContext, WorkflowEngine


def _node(node_id, tool="file.write", **overrides) -> WorkflowNode:
    data = {"id": node_id, "tool": tool}
    data.update(overrides)
    return WorkflowNode(**data)


def _definition(name="wf", nodes=None) -> WorkflowDefinition:
    return WorkflowDefinition(name=name, nodes=nodes or [])


def _save(store: FileTemplateStore, name: str, nodes):
    store.save(name, _definition(name, nodes), {"description": f"auto: {name}"})


# ── direct unit tests (stub engine + stub store) ──────────────────────────

class _StubStore:
    def load(self, name):
        return _definition(name)


class _StubEngine:
    """Returns a result whose outputs are driven by a per-input handler."""

    def __init__(self, handler):
        self.handler = handler
        self.seen = []

    def execute(self, definition, inputs, context):
        self.seen.append(dict(inputs))
        return self.handler(inputs)


def _foreach_ctx(tmp_path, engine, store):
    return ToolContext(work_dir=str(tmp_path), template_store=store, engine=engine)


def test_foreach_flattens_dict_items_and_counts_pass_rule(tmp_path):
    """Dict items flatten into child inputs; child `passed` output drives counts."""
    engine = _StubEngine(
        lambda inputs: SimpleNamespace(
            success=True, outputs={"passed": inputs.get("ok", True)}, error=None
        )
    )
    result = FlowForeach().execute(
        {
            "items": [{"name": "a", "ok": True}, {"name": "b", "ok": False}],
            "template": "child",
        },
        _foreach_ctx(tmp_path, engine, _StubStore()),
    )
    assert result["count"] == 2
    assert result["passed_count"] == 1
    assert result["failed_count"] == 1
    assert result["all_passed"] is False
    # flattening: item dict keys merged into child inputs
    assert engine.seen[0]["name"] == "a"
    assert engine.seen[1]["name"] == "b"
    assert engine.seen[0]["ok"] is True
    assert engine.seen[1]["ok"] is False


def test_foreach_child_execution_failure_counts_failed(tmp_path):
    engine = _StubEngine(
        lambda inputs: SimpleNamespace(
            success=False, outputs={}, error="boom"
        )
    )
    result = FlowForeach().execute(
        {"items": [1, 2, 3], "template": "child"},
        _foreach_ctx(tmp_path, engine, _StubStore()),
    )
    assert result["count"] == 3
    assert result["failed_count"] == 3
    assert result["all_passed"] is False
    assert all(r["error"] == "boom" for r in result["results"])


def test_foreach_empty_items_all_pass(tmp_path):
    engine = _StubEngine(
        lambda inputs: SimpleNamespace(success=True, outputs={}, error=None)
    )
    result = FlowForeach().execute(
        {"items": [], "template": "child"},
        _foreach_ctx(tmp_path, engine, _StubStore()),
    )
    assert result["count"] == 0
    assert result["passed_count"] == 0
    assert result["failed_count"] == 0
    assert result["all_passed"] is True
    assert result["results"] == []


def test_foreach_normalizes_entries_wrapper_and_single_object(tmp_path):
    engine = _StubEngine(
        lambda inputs: SimpleNamespace(success=True, outputs={}, error=None)
    )
    tool = FlowForeach()
    ctx = _foreach_ctx(tmp_path, engine, _StubStore())

    wrapped = tool.execute(
        {"items": {"entries": [{"n": 1}, {"n": 2}]}, "template": "child"}, ctx
    )
    assert wrapped["count"] == 2

    single = tool.execute({"items": {"n": 1}, "template": "child"}, ctx)
    assert single["count"] == 1
    assert single["results"][0]["item"] == {"n": 1}


def test_foreach_extra_inputs_merge_and_item_wins(tmp_path):
    engine = _StubEngine(
        lambda inputs: SimpleNamespace(success=True, outputs={}, error=None)
    )
    result = FlowForeach().execute(
        {
            "items": [{"name": "entry-name"}],
            "template": "child",
            "inputs": {"apk_path": "/a.apk", "name": "extra-name"},
        },
        _foreach_ctx(tmp_path, engine, _StubStore()),
    )
    # item keys override extra-input defaults
    assert engine.seen[0]["apk_path"] == "/a.apk"
    assert engine.seen[0]["name"] == "entry-name"


def test_foreach_writes_results_file(tmp_path):
    engine = _StubEngine(
        lambda inputs: SimpleNamespace(
            success=True, outputs={"passed": True, "name": inputs.get("name")}, error=None
        )
    )
    result = FlowForeach().execute(
        {"items": [{"name": "x"}], "template": "child"},
        _foreach_ctx(tmp_path, engine, _StubStore()),
    )
    assert result["results_file"]
    assert os.path.isfile(result["results_file"])
    payload = json.loads(open(result["results_file"], encoding="utf-8").read())
    assert payload["count"] == 1
    assert payload["all_passed"] is True
    assert payload["results"][0]["outputs"]["passed"] is True


def test_foreach_accepts_json_string_items(tmp_path):
    """A JSON-encoded list/dict string is parsed instead of raising."""
    engine = _StubEngine(
        lambda inputs: SimpleNamespace(success=True, outputs={}, error=None)
    )
    tool = FlowForeach()
    ctx = _foreach_ctx(tmp_path, engine, _StubStore())

    as_list = tool.execute(
        {"items": '[{"n": 1}, {"n": 2}]', "template": "child"}, ctx
    )
    assert as_list["count"] == 2

    as_wrapped = tool.execute(
        {"items": '{"entries": [{"n": 1}]}', "template": "child"}, ctx
    )
    assert as_wrapped["count"] == 1


def test_foreach_non_list_json_string_still_raises(tmp_path):
    engine = _StubEngine(
        lambda inputs: SimpleNamespace(success=True, outputs={}, error=None)
    )
    ctx = _foreach_ctx(tmp_path, engine, _StubStore())
    with pytest.raises(ToolException, match="must be a list"):
        FlowForeach().execute({"items": '"just a string"', "template": "child"}, ctx)
    with pytest.raises(ToolException, match="must be a list"):
        FlowForeach().execute({"items": "not json at all", "template": "child"}, ctx)


def test_foreach_missing_template_raises(tmp_path):
    ctx = ToolContext(
        work_dir=str(tmp_path), template_store=None, engine=_StubEngine(lambda i: None)
    )
    with pytest.raises(ToolException, match="template_store"):
        FlowForeach().execute({"items": [], "template": "child"}, ctx)


# ── engine integration (real TemplateStore + real engine + core file.write) ─

def test_foreach_runs_child_through_engine(tmp_path):
    store = FileTemplateStore(templates_dir=str(tmp_path))
    _save(
        store,
        "child",
        [_node("w", "file.write", params={"path": "$inputs.name", "content": "x"})],
    )
    parent = _definition(
        "parent",
        [
            _node(
                "loop",
                "flow.foreach",
                params={
                    "items": [{"name": "a.txt"}, {"name": "b.txt"}],
                    "template": "child",
                },
            )
        ],
    )
    ctx = ExecutionContext(work_dir=str(tmp_path), template_store=store)
    result = WorkflowEngine().execute(parent, {}, ctx)

    assert result.success is True
    out = result.outputs
    assert out["count"] == 2
    assert out["passed_count"] == 2
    assert out["all_passed"] is True
    assert len(out["results"]) == 2
    assert all(r["error"] is None for r in out["results"])
    # child really wrote the files (flattened $inputs.name reached file.write)
    assert os.path.isfile(os.path.join(str(tmp_path), "a.txt"))
    assert os.path.isfile(os.path.join(str(tmp_path), "b.txt"))
