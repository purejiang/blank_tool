"""Tests: engine retry backoff policy.

The directory-level ``conftest.py`` neutralizes ``_sleep_before_retry`` for
retry-SEMANTICS tests; this file tests the backoff itself:

- the delay table is ``min(2^(n-1), 30)`` seconds;
- the sleep honors cancellation within one slice instead of after the full
  delay;
- the engine actually invokes the backoff hook between retries.
"""

from app.common.exceptions import ToolException
from app.protocol import PortSet
from app.tools.builtin.base import BuiltinTool
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.engine import ExecutionContext, WorkflowEngine

# Capture the real implementation at import time — the directory conftest
# replaces ``_sleep_before_retry`` with a no-op during test setup, so the
# direct-policy tests below invoke the original as an unbound function.
_REAL_SLEEP_BEFORE_RETRY = WorkflowEngine._sleep_before_retry


class _AlwaysFailTool(BuiltinTool):
    name = "always.fail"
    description = "stub that always raises"
    ports = PortSet(inputs=[], outputs=[])

    def __init__(self):
        self.attempts = 0

    def execute(self, inputs, context):
        self.attempts += 1
        raise ToolException("always fails")


class _Registry:
    def __init__(self, tool):
        self._tool = tool

    def get_tool(self, name):
        return self._tool if name == self._tool.name else None


def test_retry_delay_table():
    expected = [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]
    actual = [WorkflowEngine._retry_delay(n) for n in range(1, 8)]
    assert actual == expected


def _fake_clock(monkeypatch, slept):
    """Patch engine time: ``sleep`` records AND advances the fake monotonic."""
    now = [1000.0]

    def _sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    monkeypatch.setattr("app.workflow.engine.time.sleep", _sleep)
    monkeypatch.setattr(
        "app.workflow.engine.time.monotonic", lambda: now[0]
    )


def test_sleep_sums_to_delay_when_not_cancelled(monkeypatch):
    slept = []
    _fake_clock(monkeypatch, slept)
    monkeypatch.setattr(
        "app.workflow.engine.is_cancelled", lambda task_id: False
    )

    engine = WorkflowEngine(registry=_Registry(_AlwaysFailTool()))
    _REAL_SLEEP_BEFORE_RETRY(engine, 2, ExecutionContext(work_dir="."))

    assert sum(slept) == 2.0
    # Sliced (no single sleep longer than the slice) so cancellation is
    # polled during the backoff.
    assert all(s <= WorkflowEngine._RETRY_SLEEP_SLICE_SECONDS for s in slept)


def test_sleep_ends_early_on_cancellation(monkeypatch):
    slept = []
    _fake_clock(monkeypatch, slept)
    monkeypatch.setattr(
        "app.workflow.engine.is_cancelled", lambda task_id: True
    )

    engine = WorkflowEngine(registry=_Registry(_AlwaysFailTool()))
    _REAL_SLEEP_BEFORE_RETRY(engine, 5, ExecutionContext(work_dir="."))

    # Cancelled before any slice is slept (16s delay would dominate otherwise).
    assert slept == []


def test_engine_invokes_backoff_between_retries(monkeypatch):
    """The hook fires with 1-indexed attempt numbers between retries."""
    calls = []
    monkeypatch.setattr(
        WorkflowEngine,
        "_sleep_before_retry",
        lambda self, attempt, context: calls.append(attempt),
    )

    tool = _AlwaysFailTool()
    engine = WorkflowEngine(registry=_Registry(tool))
    definition = WorkflowDefinition(
        name="wf",
        nodes=[
            WorkflowNode(id="f", tool="always.fail", retry=2),
        ],
    )
    result = engine.execute(definition, {}, ExecutionContext(work_dir="."))

    assert result.success is False
    assert tool.attempts == 3  # initial + 2 retries
    assert calls == [1, 2]
