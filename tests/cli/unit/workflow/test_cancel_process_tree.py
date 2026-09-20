"""Cancellation → process-tree teardown, and the cancelled-vs-failed split.

These cover the wiring added on top of ``proc_tree``:

1. the job handle is disposed **exactly once** when the out-of-band cancel path
   and the executor's own cleanup race for it;
2. a process already covered by a job is never killed through its PID again
   (by then the child is cold and its PID could have been recycled);
3. a killed run drains the output it had already produced instead of throwing
   it away;
4. ``exec.shell`` / ``exec.code`` / descriptor tools report a killed run as
   ``WorkflowCancelled`` rather than an ordinary non-zero-exit failure;
5. the engine files a killed tool as ``cancelled``, not ``failed``.

Every test replaces the job primitives with recorders; no real job object and
no real process is used, so the suite is platform-independent.
"""

import subprocess
import threading
from types import SimpleNamespace

import pytest

from app.common import proc_tree
from app.common.exceptions import WorkflowCancelled
from app.common.executor import ProcessExecutor
from app.protocol import PortSet
from app.tools.builtin.base import BuiltinTool, ToolContext
from app.tools.builtin.exec_tools import CodeExec, ShellExec
from app.workflow.definition import WorkflowNode
from app.workflow.engine import ExecutionContext, WorkflowEngine


class _StubPopen:
    """Stands in for ``subprocess.Popen``."""

    def __init__(self, *args, **kwargs):
        self.args = args[0] if args else []
        self.pid = 4242
        self.returncode = None
        self.terminated = False

    def communicate(self, timeout=None):
        return "", ""

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.terminated = True
        self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = -1
        return self.returncode


@pytest.fixture
def recorder(monkeypatch):
    """Record job kills/closes instead of calling into the kernel."""
    killed, closed = [], []
    monkeypatch.setattr(
        proc_tree, "terminate_job", lambda job: killed.append(job) or True
    )
    monkeypatch.setattr(proc_tree, "close_job_handle", lambda job: closed.append(job))
    return killed, closed


# ---------------------------------------------------------------------------
# 1. job-handle ownership
# ---------------------------------------------------------------------------

def test_release_does_not_close_a_handle_the_cancel_path_already_took(recorder):
    """Regression: the executor's mirror must not double-close a taken handle.

    ``attach_job`` leaves the handle in both the holder and the executor, so
    the cancel path can consume it first.  Unwinding afterwards must notice
    that the handle is gone rather than closing the stale value again —
    Windows may already have recycled it for an unrelated object.
    """
    killed, closed = recorder
    holder = {"job": 555}
    executor = ProcessExecutor(process_holder=holder)
    executor._job = 555  # the mirror attach_job leaves behind

    assert proc_tree.terminate_job_in(holder) is True, "the cancel path wins"
    executor._release_job()  # then run() unwinds

    assert killed == [555]
    assert closed == [555], "the handle must be closed exactly once"
    assert executor._job is None


def test_executor_closes_its_own_handle_when_no_holder_is_shared(recorder):
    killed, closed = recorder
    executor = ProcessExecutor()  # no holder: the executor owns the handle
    executor._job = 556

    executor._release_job()
    assert closed == [556]
    assert executor._job is None

    executor._job = 557
    assert executor._terminate_job() is True
    assert killed == [557]
    assert closed == [556, 557]
    assert executor._job is None


# ---------------------------------------------------------------------------
# 2. a job-covered process is never killed by PID
# ---------------------------------------------------------------------------

def test_a_job_managed_process_is_never_killed_by_pid(monkeypatch):
    monkeypatch.setattr(
        proc_tree,
        "terminate_tree",
        lambda pid, grace: pytest.fail("a job-covered process must not be killed by PID"),
    )
    monkeypatch.setattr(proc_tree, "terminate_job", lambda job: True)
    monkeypatch.setattr(proc_tree, "close_job_handle", lambda job: None)

    executor = ProcessExecutor()
    executor.process = _StubPopen(["stub"])
    executor._job = 600
    executor._job_managed = True

    executor._kill()

    assert executor.process.terminated is False, (
        "TerminateJobObject already killed the tree; Popen must be left alone"
    )


def test_a_process_without_a_job_falls_back_to_the_tree_then_to_popen(monkeypatch):
    seen = []
    monkeypatch.setattr(
        proc_tree, "terminate_tree", lambda pid, grace: seen.append(pid) or False
    )

    executor = ProcessExecutor()
    executor.process = _StubPopen(["stub"])
    executor._job_managed = False

    executor._kill()

    assert seen == [4242], "the tree kill is attempted first"
    assert executor.process.terminated, "Popen.terminate() is the last resort"


def test_a_process_that_already_exited_is_not_shot_again(monkeypatch):
    monkeypatch.setattr(
        proc_tree, "terminate_tree", lambda pid, grace: pytest.fail("nothing to kill")
    )

    executor = ProcessExecutor()
    executor.process = _StubPopen(["stub"])
    executor.process.returncode = 0
    executor._job_managed = False

    executor._kill()  # must be a no-op


# ---------------------------------------------------------------------------
# 3. a killed run keeps the output it already produced
# ---------------------------------------------------------------------------

def test_cancel_drains_the_output_produced_before_the_kill(monkeypatch):
    class _TalkingPopen(_StubPopen):
        """Raises TimeoutExpired while alive, then yields partial output."""

        def communicate(self, timeout=None):
            if self.returncode is None:
                raise subprocess.TimeoutExpired(cmd="stub", timeout=timeout or 1)
            return "partial stdout", "partial stderr"

    import app.common.executor as executor_module

    monkeypatch.setattr(executor_module.subprocess, "Popen", _TalkingPopen)
    monkeypatch.setattr(proc_tree, "terminate_job", lambda job: False)
    monkeypatch.setattr(proc_tree, "close_job_handle", lambda job: None)
    monkeypatch.setattr(proc_tree, "terminate_tree", lambda pid, grace: True)

    flag = {"cancelled": False}
    threading.Timer(0.05, lambda: flag.update(cancelled=True)).start()

    executor = ProcessExecutor(timeout=30, cancel_check=lambda: flag["cancelled"])
    returncode, stdout, stderr = executor.run(["stub"])

    assert returncode != 0, "a killed command is not a success"
    assert stdout == "partial stdout", "the pipe must be drained, not discarded"
    assert stderr == "partial stderr"


# ---------------------------------------------------------------------------
# 4. builtin tools report a killed run as cancelled
# ---------------------------------------------------------------------------

def test_shell_exec_reports_a_killed_run_as_cancelled(monkeypatch, tmp_path):
    monkeypatch.setattr(ProcessExecutor, "run", lambda self, **kwargs: (1, "out", "err"))
    context = ToolContext(work_dir=str(tmp_path), cancel_check=lambda: True)

    with pytest.raises(WorkflowCancelled):
        ShellExec().execute({"command": "echo hi"}, context)


def test_shell_exec_returns_a_normal_result_when_not_cancelled(monkeypatch, tmp_path):
    monkeypatch.setattr(ProcessExecutor, "run", lambda self, **kwargs: (0, "hello", ""))
    context = ToolContext(work_dir=str(tmp_path))

    result = ShellExec().execute({"command": "echo hello"}, context)

    assert result == {
        "returncode": 0,
        "stdout": "hello",
        "stderr": "",
        "success": True,
    }


def test_shell_exec_reports_a_real_failure_as_a_failure(monkeypatch, tmp_path):
    """A non-zero exit that was *not* caused by cancellation stays a failure."""
    monkeypatch.setattr(ProcessExecutor, "run", lambda self, **kwargs: (3, "", "boom"))
    context = ToolContext(work_dir=str(tmp_path))

    result = ShellExec().execute({"command": "exit 3"}, context)

    assert result["success"] is False
    assert result["returncode"] == 3, "the real exit code is preserved"


def test_code_exec_reports_a_killed_run_as_cancelled(monkeypatch, tmp_path):
    monkeypatch.setattr(ProcessExecutor, "run", lambda self, **kwargs: (1, "out", "err"))
    context = ToolContext(work_dir=str(tmp_path), cancel_check=lambda: True)

    with pytest.raises(WorkflowCancelled):
        CodeExec().execute({"code": "x = 1"}, context)


def test_descriptor_forwards_the_cancel_controls_to_the_command_executor(tmp_path):
    """Without this forwarding a long adb/aapt call could not be interrupted."""
    from app.tools.descriptor_tool import DescriptorTool

    holder = {}
    check = lambda: False  # noqa: E731 - identity is what matters here
    context = ToolContext(
        work_dir=str(tmp_path), cancel_check=check, process_holder=holder
    )

    cmd_context = DescriptorTool._to_command_context(context)

    assert cmd_context.cancel_check is check
    assert cmd_context.process_holder is holder


# ---------------------------------------------------------------------------
# 5. the engine classifies a killed tool as cancelled
# ---------------------------------------------------------------------------

class _KilledTool(BuiltinTool):
    """Flips the cancel flag as it runs, then fails like a killed process."""

    name = "test.killed"
    description = "flips cancellation then fails"
    ports = PortSet(inputs=[], outputs=[])
    flips_cancel = True

    def execute(self, inputs, context):
        if type(self).flips_cancel:
            flag["cancelled"] = True
        raise RuntimeError("killed by cancellation")


class _KilledToolRegistry:
    def get_tool(self, name):
        return _KilledTool() if name == _KilledTool.name else None


flag = {"cancelled": False}


def _run_killed_node(tmp_path, monkeypatch, cancelled_during_run):
    flag["cancelled"] = False
    _KilledTool.flips_cancel = cancelled_during_run

    monkeypatch.setattr(
        "app.workflow.engine.is_cancelled", lambda _target: flag["cancelled"]
    )
    engine = WorkflowEngine(registry=_KilledToolRegistry())
    context = ExecutionContext(work_dir=str(tmp_path), run_id="run-killed")
    node = WorkflowNode(id="n1", tool=_KilledTool.name, retry=0)
    return engine._run_node(node, {}, context)


def test_a_killed_tool_is_reported_as_cancelled_not_failed(tmp_path, monkeypatch):
    """The tool exits non-zero, but the run was cancelled underneath it."""
    outcome = _run_killed_node(tmp_path, monkeypatch, cancelled_during_run=True)

    assert outcome.cancelled is True
    assert outcome.error is None, "a cancelled node is not a failed node"


def test_the_same_failure_is_reported_as_failed_when_not_cancelled(
    tmp_path, monkeypatch
):
    """Control case: without the cancellation the failure is genuine."""
    outcome = _run_killed_node(tmp_path, monkeypatch, cancelled_during_run=False)

    assert outcome.cancelled is False
    assert outcome.error is not None
