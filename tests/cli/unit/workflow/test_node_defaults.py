"""Node behaviour defaults (``node_defaults``) — schema + engine resolution.

Covers the run-level defaults introduced for the editor's "follow the system
defaults" node behaviour:

- :func:`app.workflow.definition.normalize_node_defaults` drops malformed
  payloads instead of failing a run;
- a node with ``on_failure=None`` / ``retry=None`` inherits the run default,
  while an EXPLICIT value (including an explicit ``retry=0``) always wins;
- with no run defaults a node falls back to the historical ``fail`` / ``0``.

The end-to-end path (``run_workflow`` ← ``params["node_defaults"]``) is covered
by ``tests/contracts/test_workflow_contracts.py``, which drives the real
``workflow.execute`` handler.
"""

import pytest

from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.tools.builtin.base import BuiltinTool
from app.tools.tool_manager import ToolManager
from app.workflow.engine import ExecutionContext, WorkflowEngine
from app.workflow.definition import (
    WorkflowDefinition,
    WorkflowNode,
    normalize_node_defaults,
)


# ---------------------------------------------------------------------------
# normalize_node_defaults
# ---------------------------------------------------------------------------

def test_normalize_keeps_valid_values():
    assert normalize_node_defaults({"on_failure": "skip", "retry": 3}) == {
        "on_failure": "skip",
        "retry": 3,
    }


def test_normalize_accepts_numeric_strings_for_retry():
    # The renderer sends real numbers, but the parameter is untrusted input.
    assert normalize_node_defaults({"retry": "2"}) == {"retry": 2}


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "skip",
        [],
        3,
        {},
        {"on_failure": "explode"},
        {"on_failure": None},
        {"retry": -1},
        {"retry": True},
        {"retry": "many"},
        {"unknown": "value"},
    ],
)
def test_normalize_drops_invalid_payloads(raw):
    assert normalize_node_defaults(raw) in ({}, {"on_failure": "fail"})


def test_normalize_partial_payload_keeps_the_valid_half():
    assert normalize_node_defaults({"on_failure": "nope", "retry": 1}) == {"retry": 1}


# ---------------------------------------------------------------------------
# Engine resolution
# ---------------------------------------------------------------------------

def _node(**overrides) -> WorkflowNode:
    data = {"id": "n", "tool": "boom.tool"}
    data.update(overrides)
    return WorkflowNode(**data)


def test_unset_fields_inherit_the_run_default():
    context = ExecutionContext(
        work_dir=".", node_defaults={"on_failure": "skip", "retry": 2}
    )
    node = _node()

    assert WorkflowEngine._effective_on_failure(node, context) == "skip"
    assert WorkflowEngine._effective_retry(node, context) == 2


def test_explicit_values_beat_the_run_default():
    context = ExecutionContext(
        work_dir=".", node_defaults={"on_failure": "skip", "retry": 2}
    )
    node = _node(on_failure="fail", retry=0)

    assert WorkflowEngine._effective_on_failure(node, context) == "fail"
    # An explicit 0 means "no retry" — it must NOT inherit the default budget.
    assert WorkflowEngine._effective_retry(node, context) == 0


def test_without_run_defaults_the_builtin_fallback_applies():
    context = ExecutionContext(work_dir=".")
    node = _node()

    assert WorkflowEngine._effective_on_failure(node, context) == "fail"
    assert WorkflowEngine._effective_retry(node, context) == 0


def test_invalid_run_default_is_ignored_not_trusted():
    context = ExecutionContext(
        work_dir=".", node_defaults={"on_failure": "bogus", "retry": True}
    )
    node = _node()

    assert WorkflowEngine._effective_on_failure(node, context) == "fail"
    assert WorkflowEngine._effective_retry(node, context) == 0


# ---------------------------------------------------------------------------
# Execution-level: the inherited values actually drive the run
# ---------------------------------------------------------------------------

class _BoomTool(BuiltinTool):
    """A tool that always fails (retryable), so on_failure/retry are visible."""

    name = "boom.tool"
    description = "always fails"
    ports = PortSet([], [])
    calls = 0

    def execute(self, inputs, context):
        type(self).calls += 1
        raise RuntimeError("boom")


class _RecordingRegistry:
    def __init__(self, *tools):
        self._tools = {tool.name: tool for tool in tools}

    def get_tool(self, name):
        return self._tools.get(name)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Neutralize the retry backoff (it sleeps real seconds)."""
    monkeypatch.setattr(
        WorkflowEngine, "_sleep_before_retry", lambda self, attempt, context: None
    )


def _run(node, node_defaults):
    _BoomTool.calls = 0
    definition = WorkflowDefinition(name="wf", nodes=[node])
    engine = WorkflowEngine(registry=_RecordingRegistry(_BoomTool()))
    context = ExecutionContext(
        work_dir=".", node_defaults=node_defaults, run_id="run-defaults"
    )
    return engine.execute(definition, {}, context)


def test_inherited_on_failure_skip_continues_past_the_failure():
    result = _run(_node(on_failure=None, retry=None), {"on_failure": "skip"})

    assert result.success is True
    assert result.node_results["n"]["status"] == "skipped"


def test_inherited_retry_budget_is_consumed():
    result = _run(_node(on_failure=None, retry=None), {"on_failure": "skip", "retry": 2})

    assert result.success is True
    assert result.node_results["n"]["attempts"] == 3  # initial + two retries
    assert _BoomTool.calls == 3


def test_explicit_fail_still_stops_even_with_a_skip_default():
    result = _run(_node(on_failure="fail", retry=None), {"on_failure": "skip"})

    assert result.success is False
    assert result.node_results["n"]["status"] == "failed"
    assert _BoomTool.calls == 1


def test_no_defaults_reproduces_the_historical_behaviour():
    result = _run(_node(), {})

    assert result.success is False
    assert result.node_results["n"]["status"] == "failed"
    assert _BoomTool.calls == 1
