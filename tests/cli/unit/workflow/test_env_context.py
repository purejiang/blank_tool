#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
``$env.<name>`` resolution for workflow runs.

``ExpressionEngine`` resolves ``$env.<key>`` against ``WorkflowContext.env``,
which comes from ``ExecutionContext.env`` — populated by the caller.  Both
entry points (the IPC ``workflow.execute`` handler via
``app.workflow.runner.run_workflow`` and the headless CLI ``run``) must expose
the process environment, otherwise every ``$env.*`` reference fails with
"missing key" at run time while the editor happily offers the reference.

These tests pin both halves of that contract:
  * the engine resolves ``$env.X`` from the context it is handed;
  * ``run_workflow`` hands it the process environment.
"""

import os

import pytest

from app.workflow.engine import ExecutionContext, WorkflowEngine, WorkflowResult
from app.workflow.expression import ExpressionEngine, WorkflowContext
from app.workflow.runner import run_workflow


class _EchoTool:
    """Trivial tool: returns its inputs as outputs."""

    name = "test.echo"
    description = "echo inputs"

    def execute(self, inputs, context):  # noqa: D401 - test double
        return {"echoed": inputs.get("value")}


class _EchoRegistry:
    """Minimal registry accepted by WorkflowEngine(registry=...)."""

    def get_tool(self, name):
        return _EchoTool() if name == "test.echo" else None


def test_expression_engine_resolves_env_from_context():
    """`$env.X` reads the mapping the caller put on the context."""
    engine = ExpressionEngine()
    context = WorkflowContext(inputs={}, nodes={}, env={"BT_TEST_ENV": "hello"})

    assert engine.resolve("$env.BT_TEST_ENV", context) == "hello"
    assert engine.resolve("value=${env.BT_TEST_ENV}", context) == "value=hello"


def test_expression_engine_keeps_failing_for_missing_env_key():
    """An unset variable stays a loud error (never silently empty)."""
    engine = ExpressionEngine()
    context = WorkflowContext(inputs={}, nodes={}, env={})

    with pytest.raises(Exception) as excinfo:
        engine.resolve("$env.BT_DEFINITELY_MISSING", context)
    assert "missing key" in str(excinfo.value)


def test_run_workflow_exposes_process_environment(monkeypatch):
    """run_workflow fills ExecutionContext.env from os.environ."""
    monkeypatch.setenv("BT_TEST_ENV", "runner-value")

    # Keep the test hermetic: no history record is written for this fake run.
    from app.history import store as history_store

    monkeypatch.setattr(history_store, "record_run", lambda record: None)

    from app.workflow.definition import WorkflowDefinition, WorkflowNode

    captured = {}

    def spy_execute(self, definition, inputs, context):
        captured["env"] = dict(context.env)
        captured["workdir"] = context.work_dir
        return WorkflowResult(success=True, outputs={}, node_results={})

    monkeypatch.setattr(WorkflowEngine, "execute", spy_execute)

    definition = WorkflowDefinition(
        name="env-context-test",
        nodes=[WorkflowNode(id="echo", tool="test.echo", params={"value": "$env.BT_TEST_ENV"})],
    )

    result = run_workflow(definition, {"inputs": {}}, None, "task-env-test", "run-env-test")

    assert result["success"] is True
    assert captured["env"].get("BT_TEST_ENV") == "runner-value"
    # The whole process environment is exposed, not just the one key.
    assert "PATH" in captured["env"] or "Path" in captured["env"]


def test_run_workflow_env_reaches_tool_inputs(monkeypatch):
    """End-to-end: $env inside a node param resolves through a real engine run."""
    monkeypatch.setenv("BT_TEST_ENV", "tool-value")

    from app.workflow.definition import WorkflowDefinition, WorkflowNode

    definition = WorkflowDefinition(
        name="env-tool-test",
        nodes=[
            WorkflowNode(
                id="echo",
                tool="test.echo",
                params={"value": "$env.BT_TEST_ENV"},
            )
        ],
    )

    engine = WorkflowEngine(registry=_EchoRegistry())
    context = ExecutionContext(work_dir=os.getcwd(), env=dict(os.environ))
    result = engine.execute(definition, {}, context)

    assert result.success is True
    assert result.outputs == {"echoed": "tool-value"}
