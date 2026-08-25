"""Tests: flow.branch conditional sub-workflow primitive.

Covers the branch semantics end to end at the tool level (stub engine +
stub store, mirroring test_foreach.py): true/false template selection,
no-else no-op, input pass-through, child failure surfacing, recursion and
depth guards, and the missing-store / missing-engine / unknown-template
error paths.  Registration visibility is covered by
test_builtin_shipped.py (CORE_NAMES) and the workflow contracts.
"""

from types import SimpleNamespace

import pytest

from app.common.exceptions import ToolException
from app.template.store import TemplateNotFoundError
from app.tools.builtin.base import ToolContext
from app.tools.builtin.flow_tools import FlowBranch
from app.tools.builtin.workflow_tools import MAX_NESTING_DEPTH
from app.workflow.definition import WorkflowDefinition


class _StubStore:
    """Returns a definition named after the requested template."""

    def load(self, name):
        return WorkflowDefinition(name=name, nodes=[])


class _MissingStore:
    def load(self, name):
        raise TemplateNotFoundError(name)


class _StubEngine:
    """Captures (definition name, inputs) and returns a canned result."""

    def __init__(self, success=True, outputs=None, error=None):
        self.success = success
        self.outputs = outputs if outputs is not None else {"ok": True}
        self.error = error
        self.seen = []

    def execute(self, definition, inputs, context):
        self.seen.append((definition.name, dict(inputs)))
        return SimpleNamespace(
            success=self.success, outputs=self.outputs, error=self.error
        )


def _ctx(tmp_path, engine, store, **overrides):
    kwargs = dict(work_dir=str(tmp_path), template_store=store, engine=engine)
    kwargs.update(overrides)
    return ToolContext(**kwargs)


def test_truthy_condition_runs_true_template(tmp_path):
    engine = _StubEngine(outputs={"chosen": "yes"})
    result = FlowBranch().execute(
        {
            "condition": True,
            "true_template": "on-true",
            "false_template": "on-false",
            "inputs": {"x": 1},
        },
        _ctx(tmp_path, engine, _StubStore()),
    )
    assert result == {
        "executed": True,
        "template": "on-true",
        "outputs": {"chosen": "yes"},
    }
    assert engine.seen == [("on-true", {"x": 1})]


def test_falsy_condition_runs_false_template(tmp_path):
    engine = _StubEngine()
    result = FlowBranch().execute(
        {
            "condition": False,
            "true_template": "on-true",
            "false_template": "on-false",
        },
        _ctx(tmp_path, engine, _StubStore()),
    )
    assert result["executed"] is True
    assert result["template"] == "on-false"
    assert engine.seen[0][0] == "on-false"
    # inputs defaults to {}
    assert engine.seen[0][1] == {}


def test_falsy_condition_without_false_template_is_noop(tmp_path):
    engine = _StubEngine()
    result = FlowBranch().execute(
        {"condition": False, "true_template": "on-true"},
        _ctx(tmp_path, engine, _StubStore()),
    )
    assert result == {"executed": False, "template": "", "outputs": {}}
    assert engine.seen == []  # nothing ran


def test_child_failure_raises_tool_exception(tmp_path):
    engine = _StubEngine(success=False, outputs={}, error="child boom")
    with pytest.raises(ToolException, match="child boom"):
        FlowBranch().execute(
            {"condition": True, "true_template": "on-true"},
            _ctx(tmp_path, engine, _StubStore()),
        )


def test_recursion_guard_raises(tmp_path):
    engine = _StubEngine()
    ctx = _ctx(
        tmp_path, engine, _StubStore(),
        in_progress_templates=frozenset({"on-true"}),
    )
    with pytest.raises(ToolException, match="recursion detected"):
        FlowBranch().execute(
            {"condition": True, "true_template": "on-true"}, ctx
        )


def test_depth_guard_raises(tmp_path):
    engine = _StubEngine()
    ctx = _ctx(
        tmp_path, engine, _StubStore(), nesting_depth=MAX_NESTING_DEPTH
    )
    with pytest.raises(ToolException, match="maximum nesting depth"):
        FlowBranch().execute(
            {"condition": True, "true_template": "on-true"}, ctx
        )


def test_unknown_template_raises(tmp_path):
    engine = _StubEngine()
    with pytest.raises(ToolException, match="template not found"):
        FlowBranch().execute(
            {"condition": True, "true_template": "ghost"},
            _ctx(tmp_path, engine, _MissingStore()),
        )


def test_missing_template_store_raises(tmp_path):
    with pytest.raises(ToolException, match="template_store not available"):
        FlowBranch().execute(
            {"condition": True, "true_template": "on-true"},
            _ctx(tmp_path, _StubEngine(), None),
        )


def test_missing_engine_raises(tmp_path):
    with pytest.raises(ToolException, match="engine not available"):
        FlowBranch().execute(
            {"condition": True, "true_template": "on-true"},
            _ctx(tmp_path, None, _StubStore()),
        )


def test_truthiness_follows_flow_assert_convention(tmp_path):
    """Non-bool truthy/falsy values work (e.g. a string from $env.*)."""
    engine = _StubEngine()
    result = FlowBranch().execute(
        {"condition": "yes", "true_template": "t"},
        _ctx(tmp_path, engine, _StubStore()),
    )
    assert result["template"] == "t"

    engine2 = _StubEngine()
    result2 = FlowBranch().execute(
        {"condition": "", "true_template": "t"},
        _ctx(tmp_path, engine2, _StubStore()),
    )
    assert result2["executed"] is False
