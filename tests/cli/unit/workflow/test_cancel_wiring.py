"""Real-process cancellation wiring (B1.2 / B1.3 / B1.6).

``test_cancel_process_tree.py`` stubs ``Popen`` and therefore only covers
control flow.  These tests spawn **real** processes and assert the work
actually stops.

Why the assertions watch a *heartbeat file* rather than the child's PID:
``pid_alive(dead_pid)`` is not a safe way to assert a kill, because Windows
recycles PIDs — the moment the child is terminated its PID is freed and can be
handed to the next process the suite spawns, which makes the probe report a
lively stranger.  A file that the child keeps rewriting stops changing when the
child dies, whoever ends up owning that PID.

Covered:

1. ``exec.shell`` (B1.2) and a descriptor tool (B1.3) interrupt a running
   command and raise ``WorkflowCancelled`` instead of waiting out the timeout
   and reporting an ordinary failure;
2. on Windows, where ``shell=True`` makes the real command a **grandchild** of
   ``cmd.exe``, the *grandchild* stops — not just ``cmd.exe`` (this is the
   assertion ``Popen.terminate()`` alone cannot satisfy);
3. ``ProcessExecutor`` drains and returns the output produced before the kill
   (B1.6);
4. releasing the job handle on the normal path kills nothing, so a descendant
   that outlives its command survives (the ``adb start-server`` case,
   i.e. the deliberate absence of ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``).

Every test reaps the processes it started, even when an assertion fails.
"""

import os
import sys
import threading
import time

import pytest

from app.common import proc_tree
from app.common.exceptions import WorkflowCancelled
from app.common.executor import ProcessExecutor
from app.tools.builtin.base import ToolContext
from app.tools.builtin.exec_tools import ShellExec

#: Long enough that a passing test can only mean "the kill worked".
_SLEEP_SECONDS = 120

#: Heartbeat cadence of the worker script (seconds).
_BEAT_SECONDS = 0.15

#: How long to wait for a worker to report before calling it a failure.
_START_TIMEOUT = 25.0

#: How long execute() may take to unwind after the cancel flag is raised.
_UNWIND_TIMEOUT = 25.0

#: Quiet period used to prove a heartbeat has stopped advancing.
_FREEZE_WINDOW = 1.5


def _worker_source(*, detach_stdio: bool) -> str:
    """Source for a worker that pins a PID and then keeps heartbeating.

    argv: ``<pid_file> <heartbeat_file>``.  The PID file is written once; the
    heartbeat keeps being rewritten so an observer can tell a live worker from
    a dead one without trusting PID liveness.

    The heartbeat is published atomically (write a sibling, then ``os.replace``)
    because ``open(path, 'w')`` truncates first: a kill landing in that window
    would leave an empty file, which an observer cannot tell apart from a
    worker that stopped.
    """
    lines = [
        "import os, sys, time",
        "pid_path, beat_path = sys.argv[1], sys.argv[2]",
        "open(pid_path, 'w').write(str(os.getpid()))",
    ]
    if detach_stdio:
        lines += [
            "devnull = os.open(os.devnull, os.O_RDWR)",
            "os.dup2(devnull, 1)",
            "os.dup2(devnull, 2)",
        ]
    lines += [
        "while True:",
        "    beat_tmp = beat_path + '.tmp'",
        "    with open(beat_tmp, 'w') as fh:",
        "        fh.write('%.6f' % time.time())",
        "    os.replace(beat_tmp, beat_path)",
        f"    time.sleep({_BEAT_SECONDS})",
    ]
    return "\n".join(lines) + "\n"


def _write_worker(tmp_path, *, detach_stdio: bool, name: str = "worker.py"):
    script = tmp_path / name
    script.write_text(_worker_source(detach_stdio=detach_stdio), encoding="utf-8")
    return script


def _write_file(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _wait_for_text(path, timeout: float = _START_TIMEOUT) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        if text:
            return text
        time.sleep(0.05)
    raise AssertionError(f"nothing appeared in {path} within {timeout}s")


def _assert_heartbeat_stopped(beat_file, pid_file) -> None:
    """Assert the worker is no longer running.

    Samples the heartbeat, waits, samples again: a live worker always advances
    it, so an unchanged value means the process is gone.  A short settle lets
    any write already in flight land before the first sample.
    """
    time.sleep(_BEAT_SECONDS * 2)
    before = _wait_for_text(beat_file)
    time.sleep(_FREEZE_WINDOW)
    after = beat_file.read_text(encoding="utf-8").strip()
    assert before == after, (
        f"the worker is still running (heartbeat advanced {before} -> {after}, "
        f"pid {_read_pid(pid_file)})"
    )


def _read_pid(pid_file):
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _kill_quietly(pid):
    """Best-effort cleanup so a failing test cannot leak a process."""
    if pid and proc_tree.pid_alive(pid):
        proc_tree.terminate_tree(pid, grace=2.0)


class _Background:
    """Run a blocking ``execute``/``run`` call off the main thread."""

    def __init__(self, call):
        self.result = None
        self.error = None
        self.elapsed = None
        self._call = call
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        start = time.monotonic()
        try:
            self.result = self._call()
        except BaseException as exc:  # noqa: BLE001 - surfaced by assertions
            self.error = exc
        finally:
            self.elapsed = time.monotonic() - start

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc_info):
        self._thread.join(timeout=_UNWIND_TIMEOUT)
        return False

    @property
    def finished(self) -> bool:
        return not self._thread.is_alive()


def _shell_inputs(script, pid_file, beat_file, timeout=120):
    return {
        "command": f'"{sys.executable}" "{script}" "{pid_file}" "{beat_file}"',
        "timeout": timeout,
    }


# ---------------------------------------------------------------------------
# B1.6 — the executor drains what the command produced before the kill
# ---------------------------------------------------------------------------

def test_process_executor_drains_output_produced_before_the_cancel(tmp_path):
    script = _write_file(
        tmp_path,
        "chatty.py",
        "import time\n"
        "print('produced-before-cancel', flush=True)\n"
        f"time.sleep({_SLEEP_SECONDS})\n",
    )
    flag = {"cancelled": False}
    threading.Timer(2.0, lambda: flag.update(cancelled=True)).start()

    executor = ProcessExecutor(
        timeout=120,
        process_holder={},
        cancel_check=lambda: flag["cancelled"],
    )
    command = f'"{sys.executable}" "{script}"'
    args = command if os.name == "nt" else [sys.executable, str(script)]

    returncode, stdout, stderr = executor.run(
        cmd=args,
        cwd=str(tmp_path),
        shell=os.name == "nt",
    )

    assert returncode != 0, "a killed command is not a success"
    assert "produced-before-cancel" in stdout, (
        "the pipe must be drained rather than discarded"
    )


# ---------------------------------------------------------------------------
# B1.2 — exec.shell
# ---------------------------------------------------------------------------

def test_shell_exec_interrupts_a_real_command(tmp_path):
    script = _write_worker(tmp_path, detach_stdio=False)
    pid_file = tmp_path / "worker.pid"
    beat_file = tmp_path / "worker.beat"
    flag = {"cancelled": False}
    context = ToolContext(
        work_dir=str(tmp_path),
        process_holder={},
        cancel_check=lambda: flag["cancelled"],
    )

    try:
        with _Background(
            lambda: ShellExec().execute(
                _shell_inputs(script, pid_file, beat_file), context
            )
        ) as run:
            _wait_for_text(beat_file)
            flag["cancelled"] = True

        assert run.finished, "execute() must return once the run is cancelled"
        assert isinstance(run.error, WorkflowCancelled), (
            f"a killed command must be reported as cancelled, got {run.error!r}"
        )
        assert run.elapsed < _UNWIND_TIMEOUT
        _assert_heartbeat_stopped(beat_file, pid_file)
    finally:
        _kill_quietly(_read_pid(pid_file))


@pytest.mark.skipif(
    os.name != "nt", reason="the cmd.exe grandchild shape is Windows-only"
)
def test_windows_kills_the_grandchild_not_just_cmd_exe(tmp_path):
    """``shell=True`` on Windows means the real work belongs to a *grandchild*.

    Asserts the shape first (the PID the worker reports is a different process
    from the one ``Popen`` returned, because that one is ``cmd.exe``), then that
    the reporting process itself stopped.  This fails if the kill ever degrades
    back to ``Popen.terminate()`` on the immediate child.
    """
    script = _write_worker(tmp_path, detach_stdio=False)
    pid_file = tmp_path / "grandchild.pid"
    beat_file = tmp_path / "grandchild.beat"
    flag = {"cancelled": False}
    holder = {}
    context = ToolContext(
        work_dir=str(tmp_path),
        process_holder=holder,
        cancel_check=lambda: flag["cancelled"],
    )

    try:
        with _Background(
            lambda: ShellExec().execute(
                _shell_inputs(script, pid_file, beat_file), context
            )
        ) as run:
            worker_pid = int(_wait_for_text(pid_file))
            forwarded = holder.get("process")

            assert forwarded is not None
            assert forwarded.pid != worker_pid, (
                "expected the command to run as a grandchild of cmd.exe"
            )

            flag["cancelled"] = True

        assert isinstance(run.error, WorkflowCancelled)
        _assert_heartbeat_stopped(beat_file, pid_file)
    finally:
        _kill_quietly(_read_pid(pid_file))


# ---------------------------------------------------------------------------
# normal completion must not kill descendants
# ---------------------------------------------------------------------------

def test_normal_completion_leaves_a_descendant_alive(tmp_path):
    """Guards the deliberate absence of ``KILL_ON_JOB_CLOSE``.

    ``adb start-server`` leaves a daemon behind that has to outlive the node
    which started it, so releasing the job handle on the normal path must not
    kill anything.  The parent here exits immediately, leaving a detached
    descendant that inherits job membership.
    """
    worker = _write_worker(tmp_path, detach_stdio=True, name="detached.py")
    launcher = _write_file(
        tmp_path,
        "launcher.py",
        "import os, subprocess, sys\n"
        "worker, pid_path, beat_path = sys.argv[1], sys.argv[2], sys.argv[3]\n"
        "devnull = open(os.devnull, 'wb')\n"
        "subprocess.Popen(\n"
        "    [sys.executable, worker, pid_path, beat_path],\n"
        "    stdin=subprocess.DEVNULL, stdout=devnull, stderr=devnull,\n"
        ")\n",
    )
    pid_file = tmp_path / "detached.pid"
    beat_file = tmp_path / "detached.beat"
    context = ToolContext(work_dir=str(tmp_path), process_holder={})
    inputs = {
        "command": (
            f'"{sys.executable}" "{launcher}" '
            f'"{worker}" "{pid_file}" "{beat_file}"'
        ),
        "timeout": 60,
    }

    descendant_pid = None
    try:
        result = ShellExec().execute(inputs, context)

        assert result["success"] is True, (
            f"the launcher exits immediately, so this must succeed: {result!r}"
        )
        descendant_pid = int(_wait_for_text(pid_file))
        first = _wait_for_text(beat_file)

        # Still heartbeating well after its parent finished ⇒ not killed.
        time.sleep(_BEAT_SECONDS * 4)
        assert beat_file.read_text(encoding="utf-8").strip() != first, (
            "a descendant that outlives its command must survive a normal exit"
        )
    finally:
        _kill_quietly(descendant_pid)


# ---------------------------------------------------------------------------
# B1.3 — descriptor path (the adb / aapt / apktool shape)
# ---------------------------------------------------------------------------

class _StubEnvRegistry:
    """The descriptor's ``binary`` path is absolute, so nothing to resolve."""

    def resolve(self, name):
        from types import SimpleNamespace

        return SimpleNamespace(binary_path="")


def test_descriptor_interrupts_a_real_command(tmp_path):
    """Before the fix ``_to_command_context`` passed ``process_holder={}`` and
    no ``cancel_check``, so a long adb / aapt call could not be interrupted."""
    from app.tools.descriptor_tool import DescriptorTool, ToolDescriptor

    descriptor = ToolDescriptor(
        name="stub_tool",
        display_name="Stub Tool",
        type="binary",
        path=sys.executable,
        env_deps=[],
        validate={},
        version={},
        inputs=[],
        outputs=[],
    )
    tool = DescriptorTool(descriptor, _StubEnvRegistry())

    script = _write_worker(tmp_path, detach_stdio=False)
    pid_file = tmp_path / "descriptor.pid"
    beat_file = tmp_path / "descriptor.beat"
    flag = {"cancelled": False}
    context = ToolContext(
        work_dir=str(tmp_path),
        process_holder={},
        cancel_check=lambda: flag["cancelled"],
    )

    try:
        with _Background(
            lambda: tool.execute(
                {"args": [str(script), str(pid_file), str(beat_file)]}, context
            )
        ) as run:
            _wait_for_text(beat_file)
            flag["cancelled"] = True

        assert run.finished, "the descriptor call must return once cancelled"
        assert isinstance(run.error, WorkflowCancelled), (
            f"expected WorkflowCancelled, got {run.error!r}"
        )
        _assert_heartbeat_stopped(beat_file, pid_file)
    finally:
        _kill_quietly(_read_pid(pid_file))
