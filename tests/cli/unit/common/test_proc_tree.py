"""Unit tests for the process-tree lifecycle helpers.

``proc_tree`` is the only module that knows how to stop a whole child tree, so
these tests pin the contract the cancellation paths depend on:

1. a job is enrolled strictly by process handle, never by resolving a bare PID
   (which could put an unrelated process into the job and kill it);
2. a job handle is disposed **exactly once**, even when the out-of-band cancel
   path and the executor's own cleanup race for it — a double ``CloseHandle``
   on a recycled handle value is a real bug, not a cosmetic one;
3. releasing a handle never kills anything (descendants such as
   ``adb start-server`` are meant to outlive their command);
4. the PID-based fallbacks are only reachable when no job covered the process.

The kernel is never touched: ``create_job`` / ``terminate_job`` /
``close_job_handle`` are replaced with recorders, so these tests are
platform-independent and safe to run anywhere.
"""

import os
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from app.common import proc_tree


class _FakeProcess:
    """Minimal ``subprocess.Popen`` stand-in.

    ``handle=None`` models a ``Popen``-like object that does not expose its
    process handle, which is what the handle-based enrolment must refuse.
    """

    def __init__(self, handle=None, pid=4242):
        self.pid = pid
        if handle is not None:
            self._handle = handle


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
# spawn options
# ---------------------------------------------------------------------------

def test_spawn_options_are_platform_specific(monkeypatch):
    monkeypatch.setattr(proc_tree, "IS_WINDOWS", True)
    assert proc_tree.spawn_options() == {}

    monkeypatch.setattr(proc_tree, "IS_WINDOWS", False)
    assert proc_tree.spawn_options() == {"start_new_session": True}


def test_windows_keeps_children_in_the_console_process_group(monkeypatch):
    """Windows adds no ``CREATE_NEW_PROCESS_GROUP``.

    Staying in the console group is what lets a console Ctrl+C reach the
    children for free; tree cleanup is the job object's responsibility.
    """
    monkeypatch.setattr(proc_tree, "IS_WINDOWS", True)
    options = proc_tree.spawn_options()
    assert "creationflags" not in options
    assert "start_new_session" not in options


# ---------------------------------------------------------------------------
# enrolment (handle-based only)
# ---------------------------------------------------------------------------

def test_attach_job_refuses_a_process_without_a_handle(monkeypatch):
    monkeypatch.setattr(proc_tree, "IS_WINDOWS", True)
    monkeypatch.setattr(proc_tree, "create_job", lambda: 4321)
    closed = []
    monkeypatch.setattr(proc_tree, "close_job_handle", closed.append)

    holder = {}
    assert proc_tree.attach_job(_FakeProcess(handle=None), holder) is None
    assert closed == [4321], "a refused enrolment must not leak the job handle"
    assert "job" not in holder


def test_attach_job_never_resolves_a_pid(monkeypatch):
    """Enrolment must not fall back to ``OpenProcess``.

    Doing so could enrol an unrelated process (a recycled PID) into the job,
    where a later ``TerminateJobObject`` would kill it.
    """
    monkeypatch.setattr(proc_tree, "IS_WINDOWS", True)
    monkeypatch.setattr(proc_tree, "create_job", lambda: 4321)
    monkeypatch.setattr(proc_tree, "close_job_handle", lambda job: None)

    calls = []
    monkeypatch.setattr(
        proc_tree, "assign_to_job", lambda job, process: calls.append(process) or False
    )

    proc_tree.attach_job(_FakeProcess(handle=None), {})
    assert calls, "the process object is handed over as-is, never its PID"


def test_attach_job_records_the_handle_in_the_holder(monkeypatch):
    monkeypatch.setattr(proc_tree, "IS_WINDOWS", True)
    monkeypatch.setattr(proc_tree, "create_job", lambda: 777)
    monkeypatch.setattr(proc_tree, "assign_to_job", lambda job, process: True)

    holder = {}
    assert proc_tree.attach_job(_FakeProcess(handle=1), holder) == 777
    assert holder["job"] == 777, "a shared holder is what cancel reaches through"


def test_attach_job_is_a_no_op_off_windows(monkeypatch):
    monkeypatch.setattr(proc_tree, "IS_WINDOWS", False)
    holder = {}
    assert proc_tree.attach_job(_FakeProcess(handle=1), holder) is None
    assert "job" not in holder


# ---------------------------------------------------------------------------
# take-and-dispose
# ---------------------------------------------------------------------------

def test_terminate_job_in_disposes_the_handle_exactly_once(recorder):
    killed, closed = recorder
    holder = {"job": 555}

    assert proc_tree.terminate_job_in(holder) is True
    assert holder == {}, "the handle must be taken out of the holder"
    assert killed == [555]
    assert closed == [555]

    # The executor's own cleanup then unwinds and finds nothing left.
    assert proc_tree.terminate_job_in(holder) is False
    assert killed == [555], "a taken handle must never be terminated twice"
    assert closed == [555], "a taken handle must never be closed twice"


def test_only_one_of_many_concurrent_terminations_wins(recorder):
    """The cancel path and the executor's cleanup can race on one handle."""
    killed, closed = recorder
    holder = {"job": 999}
    workers = 8
    barrier = threading.Barrier(workers)
    results = []
    results_lock = threading.Lock()

    def _terminate():
        barrier.wait()
        outcome = proc_tree.terminate_job_in(holder)
        with results_lock:
            results.append(outcome)

    threads = [threading.Thread(target=_terminate) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count(True) == 1, "exactly one caller may take the handle"
    assert killed == [999]
    assert closed == [999]


def test_close_job_in_releases_without_killing(recorder):
    killed, closed = recorder
    holder = {"job": 556}

    assert proc_tree.close_job_in(holder) is True
    assert killed == [], "releasing a handle must never kill the tree"
    assert closed == [556]
    assert holder == {}


def test_job_helpers_tolerate_a_missing_or_odd_holder(recorder):
    assert proc_tree.terminate_job_in(None) is False
    assert proc_tree.terminate_job_in("not-a-mapping") is False
    assert proc_tree.terminate_job_in({}) is False
    assert proc_tree.close_job_in(None) is False
    assert proc_tree.close_job_in({}) is False


# ---------------------------------------------------------------------------
# platform dispatch of the PID-based fallback
# ---------------------------------------------------------------------------

def test_job_primitives_are_inert_off_windows(monkeypatch):
    monkeypatch.setattr(proc_tree, "IS_WINDOWS", False)
    assert proc_tree.create_job() is None
    assert proc_tree.terminate_job(123) is False
    assert proc_tree.close_job_handle(123) is None


@pytest.mark.parametrize("bad_pid", [0, -1, None, "abc", ""])
def test_terminate_tree_rejects_a_pid_it_cannot_use(bad_pid):
    assert proc_tree.terminate_tree(bad_pid) is False


def test_terminate_tree_uses_taskkill_on_windows(monkeypatch):
    seen = []
    monkeypatch.setattr(proc_tree, "IS_WINDOWS", True)
    monkeypatch.setattr(
        proc_tree, "_taskkill_tree", lambda pid, grace: seen.append(pid) or True
    )
    monkeypatch.setattr(
        proc_tree, "_killpg_tree", lambda pid, grace: pytest.fail("wrong platform")
    )

    assert proc_tree.terminate_tree(4321, grace=1.0) is True
    assert seen == [4321]


def test_terminate_tree_uses_the_process_group_off_windows(monkeypatch):
    seen = []
    monkeypatch.setattr(proc_tree, "IS_WINDOWS", False)
    monkeypatch.setattr(
        proc_tree, "_killpg_tree", lambda pid, grace: seen.append(pid) or True
    )
    monkeypatch.setattr(
        proc_tree, "_taskkill_tree", lambda pid, grace: pytest.fail("wrong platform")
    )

    assert proc_tree.terminate_tree(4321, grace=1.0) is True
    assert seen == [4321]


def test_killpg_refuses_to_signal_its_own_process_group(monkeypatch):
    """A child that never got its own session shares our group — signalling it
    would kill the engine itself, so the fallback must decline.

    ``proc_tree.os`` is swapped for a stub because ``os.getpgid`` is POSIX-only
    and therefore absent on the Windows machine running this suite.
    """
    monkeypatch.setattr(proc_tree, "os", SimpleNamespace(getpgid=lambda pid: 1234))

    assert proc_tree._killpg_tree(4242, grace=0.0) is False


def test_killpg_signals_a_group_the_child_owns(monkeypatch):
    signalled = []
    monkeypatch.setattr(
        proc_tree,
        "os",
        SimpleNamespace(
            getpgid=lambda pid: 100 if pid == 4242 else 999,
            killpg=lambda pgid, sig: signalled.append((pgid, sig)),
        ),
    )
    monkeypatch.setattr(proc_tree, "pid_alive", lambda pid: False)

    assert proc_tree._killpg_tree(4242, grace=0.1) is True
    assert signalled == [(100, proc_tree.signal.SIGTERM)]


# ---------------------------------------------------------------------------
# liveness probe (real processes)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_pid", [0, -1, None, "abc", ""])
def test_pid_alive_rejects_a_pid_it_cannot_use(bad_pid):
    assert proc_tree.pid_alive(bad_pid) is False


def test_pid_alive_reports_the_running_test_process_as_alive():
    assert proc_tree.pid_alive(os.getpid()) is True


def test_pid_alive_tracks_a_real_child_process():
    """Also a regression guard for the probe itself.

    If the Windows branch were reverted to ``os.kill(pid, 0)``, that call would
    *terminate* the child instead of probing it — and the final assertion would
    then report a dead process as alive.
    """
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert proc_tree.pid_alive(child.pid) is True
    finally:
        child.kill()
        child.wait()

    assert proc_tree.pid_alive(child.pid) is False
