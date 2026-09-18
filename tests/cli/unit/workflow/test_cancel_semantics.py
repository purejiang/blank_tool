"""End-to-end cancellation semantics.

Covers the contract the refactor introduced:

1. cancelling a run terminates the subprocess it is currently running;
2. a cancelled run does NOT consume its retry budget;
3. cancellation survives nested composition (flow.foreach / flow.branch /
   workflow.run) instead of being reported as one failed item / a node
   failure;
4. TaskManager run identity: re-register resets, cancel-before-register is
   honored, and two runs sharing a task id do not clobber each other.

The subprocess tests use a stub ``Popen``: the DSH sandbox forbids real pipe
creation, and the behaviour under test (poll the cancel source, kill, return)
is entirely in Python.
"""

import subprocess
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.common.exceptions import NonRetryableToolError, WorkflowCancelled
from app.common.executor import ProcessExecutor
from app.common.task_manager import TaskManager
from app.protocol import PortSet
from app.tools.builtin.base import BuiltinTool, ToolContext
from app.tools.builtin.flow_tools import FlowBranch, FlowForeach
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.engine import ExecutionContext, WorkflowEngine


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_task_manager():
    """Drop every registration the test created (singleton across tests)."""
    manager = TaskManager()
    yield
    for run in manager.list_tasks():
        manager.unregister(run["run_id"])


class _StubPopen:
    """Stands in for subprocess.Popen (real pipes are sandbox-blocked)."""

    def __init__(self, *args, **kwargs):
        self.args = args[0] if args else []
        self.pid = 4242
        self.returncode = None
        self.terminated = False

    def communicate(self, timeout=None):
        if self.returncode is not None:
            return "", ""
        if timeout is None:
            raise AssertionError("communicate() must be called with a timeout")
        time.sleep(min(timeout, 0.02))
        raise subprocess.TimeoutExpired(cmd="stub", timeout=timeout)

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.terminated = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class _BoomTool(BuiltinTool):
    """Always fails, counting its executions."""

    name = "test.boom"
    description = "always fails"
    ports = PortSet(inputs=[], outputs=[])
    calls = 0

    def execute(self, inputs, context):
        type(self).calls += 1
        raise RuntimeError("always fails")


class _BoomRegistry:
    def get_tool(self, name):
        return _BoomTool() if name == _BoomTool.name else None


class _StubStore:
    """Template store returning a one-node child workflow."""

    def __init__(self, name="child"):
        self.name = name
        self.loads = 0

    def load(self, template_name):
        self.loads += 1
        return WorkflowDefinition(
            name=template_name,
            nodes=[
                WorkflowNode(id="w", tool="flow.log", params={"message": "hi"})
            ],
        )


def _child_result(success=True, outputs=None, error=None, cancelled=False):
    return SimpleNamespace(
        success=success,
        outputs=outputs or {},
        error=error,
        cancelled=cancelled,
    )


# ---------------------------------------------------------------------------
# 1. subprocess cancellation
# ---------------------------------------------------------------------------

def test_process_executor_kills_subprocess_when_cancel_check_fires():
    flag = {"cancelled": False}
    threading.Timer(0.15, lambda: flag.update(cancelled=True)).start()

    with patch("app.common.executor.subprocess.Popen", _StubPopen):
        executor = ProcessExecutor(timeout=30, cancel_check=lambda: flag["cancelled"])
        start = time.monotonic()
        returncode, _stdout, _stderr = executor.run(["stub"])
        elapsed = time.monotonic() - start

    assert executor.process.terminated, "the subprocess must be killed"
    assert returncode != 0, "a killed command is not a success"
    assert elapsed < 5, f"cancel took {elapsed:.2f}s"


def test_task_manager_cancel_terminates_attached_process():
    manager = TaskManager()
    holder = {"process": _StubPopen(["stub"])}
    manager.register("run-p", "task-p", threading.Event())
    manager.attach_process("run-p", holder)

    assert manager.cancel("task-p") is True
    assert holder["process"].terminated
    assert manager.is_cancelled("run-p") is True
    assert holder["_cancel_pending"] is True


def test_cancel_of_a_finished_run_returns_false():
    manager = TaskManager()
    manager.register("run-f", "task-f")
    manager.unregister("run-f")
    assert manager.cancel("run-f") is False


def test_reregistering_a_run_resets_cancelled():
    manager = TaskManager()
    manager.register("run-r", "task-r")
    manager.cancel("run-r")
    assert manager.is_cancelled("run-r") is True

    manager.register("run-r", "task-r")
    assert manager.is_cancelled("run-r") is False


def test_cancel_before_register_is_honored_by_the_tombstone():
    manager = TaskManager()
    # The UI can cancel before the run has registered.
    assert manager.cancel("run-t") is True
    manager.register("run-t", "task-t")
    assert manager.is_cancelled("run-t") is True


def test_two_runs_sharing_a_task_id_do_not_clobber_each_other():
    manager = TaskManager()
    manager.register("run-1", "task-shared")
    manager.register("run-2", "task-shared")

    manager.unregister("run-1")
    # The surviving run is still cancellable and not cancelled.
    assert manager.is_cancelled("run-2") is False
    assert manager.cancel("task-shared") is True
    assert manager.is_cancelled("run-2") is True


def test_list_tasks_reports_run_identity():
    manager = TaskManager()
    manager.register("run-l", "task-l", threading.Event())
    entry = [
        item for item in manager.list_tasks() if item["run_id"] == "run-l"
    ].pop()
    assert entry["task_id"] == "task-l"
    assert entry["cancelled"] is False
    assert entry["has_process"] is False
    assert entry["started_at"] is not None


# ---------------------------------------------------------------------------
# 2. retries are never spent on a cancelled run
# ---------------------------------------------------------------------------

def test_cancel_during_retry_does_not_retry(tmp_path):
    _BoomTool.calls = 0
    engine = WorkflowEngine(registry=_BoomRegistry())
    context = ExecutionContext(work_dir=str(tmp_path), run_id="run-retry")
    node = WorkflowNode(id="n1", tool=_BoomTool.name, retry=2)

    calls = {"n": 0}

    def _is_cancelled(_target):
        calls["n"] += 1
        return calls["n"] > 1  # first check passes, then the user cancels

    with patch("app.workflow.engine.is_cancelled", side_effect=_is_cancelled):
        outcome = engine._run_node(node, {}, context)

    assert outcome.cancelled is True
    assert _BoomTool.calls == 1, "a cancelled run must not retry"


def test_cancelled_node_is_recorded_with_cancelled_status(tmp_path):
    definition = WorkflowDefinition(
        name="wf",
        nodes=[WorkflowNode(id="a", tool="file.write",
                            params={"path": "a.txt", "content": "x"})],
    )
    engine = WorkflowEngine()
    context = ExecutionContext(work_dir=str(tmp_path), run_id="run-status")

    call_count = [0]

    def _is_cancelled(_target):
        call_count[0] += 1
        # 1: loop guard, 2: loop guard inside _run_node → cancel before running
        return call_count[0] >= 2

    with patch("app.workflow.engine.is_cancelled", side_effect=_is_cancelled):
        result = engine.execute(definition, {}, context)

    assert result.cancelled is True
    assert result.status == "cancelled"
    assert result.node_results["a"]["status"] == "cancelled"


def test_unknown_tool_is_not_retried(tmp_path):
    """An unknown tool can never start existing — do not spend retries on it."""
    engine = WorkflowEngine(registry=_EmptyRegistry())
    context = ExecutionContext(work_dir=str(tmp_path), run_id="run-nr")
    node = WorkflowNode(id="n1", tool="nope.tool", retry=3)

    original = engine._attempt_node
    attempts = []

    def _spy(*args, **kwargs):
        attempts.append(1)
        return original(*args, **kwargs)

    engine._attempt_node = _spy
    outcome = engine._run_node(node, {}, context)

    assert len(attempts) == 1, "a non-retryable failure must not be retried"
    assert "tool not found" in outcome.error


class _EmptyRegistry:
    def get_tool(self, name):
        return None


# ---------------------------------------------------------------------------
# 3. cancellation survives nested composition
# ---------------------------------------------------------------------------

def test_foreach_cancel_stops_the_loop(tmp_path):
    store = _StubStore()
    engine = _StubEngineReturning(
        SimpleNamespace(
            success=True, outputs={}, error=None, cancelled=False
        )
    )
    context = ToolContext(
        work_dir=str(tmp_path),
        run_id="run-foreach",
        template_store=store,
        engine=engine,
        current_node_path="loop",
        cancel_check=lambda: True,
    )

    with pytest.raises(WorkflowCancelled):
        FlowForeach().execute(
            {"items": [1, 2, 3, 4, 5], "template": "child"}, context
        )
    assert engine.calls == 0, "a cancelled loop must not start a child run"


def test_foreach_propagates_a_cancelled_child(tmp_path):
    store = _StubStore()
    engine = _StubEngineReturning(
        SimpleNamespace(
            success=False, outputs={}, error="workflow cancelled", cancelled=True
        )
    )
    context = ToolContext(
        work_dir=str(tmp_path),
        run_id="run-foreach2",
        template_store=store,
        engine=engine,
        current_node_path="loop",
        cancel_check=lambda: False,
    )

    with pytest.raises(WorkflowCancelled):
        FlowForeach().execute({"items": [1, 2], "template": "child"}, context)
    assert engine.calls == 1


def test_branch_propagates_cancellation_not_failure(tmp_path):
    engine = _StubEngineReturning(
        SimpleNamespace(
            success=False, outputs={}, error="workflow cancelled", cancelled=True
        )
    )
    context = ToolContext(
        work_dir=str(tmp_path),
        run_id="run-branch",
        template_store=_StubStore(),
        engine=engine,
        current_node_path="choose",
    )

    with pytest.raises(WorkflowCancelled):
        FlowBranch().execute(
            {"condition": True, "true_template": "child"}, context
        )


def test_workflow_run_propagates_cancellation(tmp_path):
    from app.tools.builtin.workflow_tools import WorkflowRun

    engine = _StubEngineReturning(
        SimpleNamespace(
            success=False, outputs={}, error="workflow cancelled", cancelled=True
        )
    )
    context = ToolContext(
        work_dir=str(tmp_path),
        run_id="run-sub",
        template_store=_StubStore(),
        engine=engine,
        current_node_path="sub",
    )

    with pytest.raises(WorkflowCancelled):
        WorkflowRun().execute({"template": "child"}, context)


class _StubEngineReturning:
    """Engine stub returning a fixed child result and counting invocations."""

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def execute(self, definition, inputs, context):
        self.calls += 1
        return self.result


# ---------------------------------------------------------------------------
# 4. flow.assert is non-retryable
# ---------------------------------------------------------------------------

def test_flow_assert_raises_non_retryable():
    from app.tools.builtin.flow_tools import FlowAssert

    with pytest.raises(NonRetryableToolError):
        FlowAssert().execute({"condition": False}, ToolContext(work_dir="."))


# ---------------------------------------------------------------------------
# 5. out-of-band termination is still a cancellation
# ---------------------------------------------------------------------------

class _ExitingStubPopen:
    """A child that is terminated out of band *while* communicate() waits.

    This is what TaskManager.cancel does through ``holder['kill']``: the
    process dies, so ``communicate()`` returns its output normally instead of
    raising TimeoutExpired — the cancel source must be re-checked after the
    wait, otherwise the node would look like an ordinary failure and burn a
    retry.
    """

    def __init__(self, *args, **kwargs):
        self.args = args[0] if args else []
        self.pid = 4242
        self.returncode = None
        self.terminated = False
        self._exited = threading.Event()

    def communicate(self, timeout=None):
        self._exited.wait(0.1)
        if self.returncode is None:
            self.returncode = -9
        return "out", "err"

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15
        self._exited.set()

    def kill(self):
        self.terminated = True
        self.returncode = -9
        self._exited.set()

    def wait(self, timeout=None):
        return self.returncode


def test_out_of_band_kill_during_communicate_marks_the_run_cancelled():
    holder: dict = {}
    flag = {"cancelled": False}
    cancel_check = lambda: flag["cancelled"]

    def _cancel():
        flag["cancelled"] = True
        holder["kill"]()  # exactly what TaskManager._terminate invokes

    with patch("app.common.executor.subprocess.Popen", _ExitingStubPopen):
        executor = ProcessExecutor(
            timeout=30, process_holder=holder, cancel_check=cancel_check
        )
        threading.Timer(0.05, _cancel).start()
        returncode, _stdout, _stderr = executor.run(["stub"])

    assert executor.cancelled is True, "an out-of-band kill must not look like a plain failure"
    assert returncode != 0
    assert holder["process"].terminated


def test_cancel_before_spawn_marks_the_run_cancelled():
    holder = {"_cancel_pending": True}
    with patch("app.common.executor.subprocess.Popen", _ExitingStubPopen):
        executor = ProcessExecutor(timeout=30, process_holder=holder)
        returncode, _stdout, _stderr = executor.run(["stub"])

    assert executor.cancelled is True
    assert returncode != 0


# ---------------------------------------------------------------------------
# 6. stop events as an external cancellation source (opt-in)
# ---------------------------------------------------------------------------

def test_honor_stop_event_treats_a_set_event_as_cancelled():
    manager = TaskManager()
    event = threading.Event()
    manager.register("run-se", "task-se", event, honor_stop_event=True)

    assert manager.is_cancelled("run-se") is False
    event.set()

    assert manager.is_cancelled("run-se") is True
    # The task-id alias and the listing must agree with the run id.
    assert manager.is_cancelled("task-se") is True
    entry = [t for t in manager.list_tasks() if t["run_id"] == "run-se"].pop()
    assert entry["cancelled"] is True


def test_stop_event_is_ignored_without_the_opt_in():
    """The JSON-RPC layer passes a stop event but keeps flag-only semantics."""
    manager = TaskManager()
    event = threading.Event()
    manager.register("run-noopt", "", event)

    event.set()

    assert manager.is_cancelled("run-noopt") is False
    entry = [t for t in manager.list_tasks() if t["run_id"] == "run-noopt"].pop()
    assert entry["cancelled"] is False


# ---------------------------------------------------------------------------
# 7. task-log buffers survive a sibling run under the same task id
# ---------------------------------------------------------------------------

def test_unregister_keeps_a_task_log_buffer_shared_with_another_run(
    tmp_path, monkeypatch
):
    from app.utils import task_log_writer as writer

    monkeypatch.setenv("BT_TASKS_DIR", str(tmp_path / "tasks"))
    writer.cleanup_task_log("shared-task")

    manager = TaskManager()
    manager.register("run-sib-a", "shared-task")
    manager.register("run-sib-b", "shared-task")
    writer.append_task_log("shared-task", "line from a")

    manager.unregister("run-sib-a")

    # The sibling is still running under the same task id: its lines must be
    # flushed to disk but the buffer entry must NOT be dropped.
    log_path = tmp_path / "tasks" / "shared-task" / "logs" / "task_exec.log"
    assert log_path.is_file()
    assert "line from a" in log_path.read_text(encoding="utf-8")
    assert "shared-task" in writer._per_task_buffers

    writer.append_task_log("shared-task", "line from b")
    manager.unregister("run-sib-b")

    assert "shared-task" not in writer._per_task_buffers
    assert "line from b" in log_path.read_text(encoding="utf-8")
