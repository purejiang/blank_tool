#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProcessExecutor — manages subprocess lifecycle: spawn, monitor, kill.
"""

import logging
import os
import signal
import subprocess
import time
from typing import Callable, Optional, Union

from app.common import proc_tree
from app.common.exceptions import TimeoutException

logger = logging.getLogger(__name__)

#: Cancellation poll interval while waiting for a subprocess, in seconds.
_POLL_SLICE_SECONDS = 0.5

#: Grace period between the graceful terminate and the hard kill, in seconds.
_TERMINATE_GRACE_SECONDS = 5

#: Timeout for the Windows ``taskkill`` tree-kill helper, in seconds.
_TASKKILL_TIMEOUT_SECONDS = 10

#: How long to wait for a killed process to be reaped, in seconds.
_KILL_GRACE_SECONDS = 5.0

#: How long the post-kill drain waits for the pipe buffers, in seconds.
_DRAIN_TIMEOUT_SECONDS = 5.0

#: A command line may be a list (shell=False on POSIX) or a string
#: (``shell=True`` — Windows ``exec.shell``).
Command = Union[str, list, tuple]


def _describe(cmd: Command) -> str:
    """Render *cmd* for a message without iterating a string's characters."""
    if isinstance(cmd, (list, tuple)):
        return " ".join(str(part) for part in cmd)
    return str(cmd)


class ProcessExecutor:
    """Manages subprocess lifecycle: spawn, monitor, kill.

    If *process_holder* is provided it must be a dict; the running
    ``subprocess.Popen`` is stored as ``process_holder['process']`` and a
    tree-killing callable as ``process_holder['kill']``, so an external
    coordinator (e.g. TaskManager) can stop it on cancel.

    *cancel_check* is an independent, polled cancellation source: while
    waiting for the process the executor re-checks it every
    ``_POLL_SLICE_SECONDS`` and kills the process when it reports True.  Both
    sources are honored — the holder flag covers a cancel that arrived before
    the process existed, the callback covers everything after, and the check
    is repeated *after* the wait because an out-of-band kill (TaskManager
    calling ``holder['kill']``) makes ``communicate()`` return normally
    instead of raising.

    Cancellation is reported through :attr:`cancelled`; the ``run`` contract
    itself (a ``(returncode, stdout, stderr)`` tuple) is unchanged, so callers
    that must distinguish "cancelled" from "failed" check that flag (see
    ``app.common.base_executor`` and the ``exec.*`` builtins).

    On Windows the child is additionally enrolled in a job object (see
    :mod:`app.common.proc_tree`) immediately after ``Popen`` returns.  Job
    membership is inherited, so that early assignment is what lets a tree kill
    reach grandchildren whose parent has already exited — the case
    ``taskkill /T`` cannot cover.
    """

    def __init__(
        self,
        timeout: int = 600,
        process_holder: Optional[dict] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ):
        self.timeout = timeout
        self.process: Optional[subprocess.Popen] = None
        #: True when the command was stopped because of a cancellation.
        self.cancelled = False
        self._process_holder = process_holder
        self._cancel_check = cancel_check
        #: Job-object handle covering the whole child tree (Windows only).
        self._job: Optional[int] = None
        #: True once a job covered this process — the job is then the only
        #: kill mechanism used, never the (possibly recycled) PID.
        self._job_managed = False

    def run(
        self,
        cmd: Command,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
        shell: bool = False,
        text: bool = True,
        encoding: str = 'utf-8',
        errors: str = 'ignore',
    ) -> tuple[int, str, str]:
        """Execute command and return (returncode, stdout, stderr).

        Returns a negative/forced returncode when the command was killed by
        cancellation, and sets :attr:`cancelled` so the caller reports the
        node as cancelled rather than failed.
        """
        popen_kwargs: dict = {}
        if os.name == "nt":
            # No console window for the child (the Electron-hosted backend
            # has no console to flash into).
            popen_kwargs["creationflags"] = getattr(
                subprocess, "CREATE_NO_WINDOW", 0
            )
        else:
            # Own process group, so a cancel/timeout can terminate the whole
            # tree instead of just the direct child.
            popen_kwargs["start_new_session"] = True

        self.process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            encoding=encoding,
            errors=errors,
            **popen_kwargs,
        )
        try:
            # Enrol the child in a job object straight after spawn: membership
            # is inherited, so this is the only moment at which the whole future
            # tree (``cmd.exe`` plus the real command it is about to start) can
            # be captured.  On POSIX ``attach_job`` returns ``None`` and the
            # ``start_new_session`` process group is the tree mechanism.
            self._job = proc_tree.attach_job(self.process, self._process_holder)
            self._job_managed = self._job is not None

            if self._process_holder is not None:
                self._process_holder["process"] = self.process
                self._process_holder["_pid"] = self.process.pid
                # Lets TaskManager cancel terminate the tree, not just the child.
                self._process_holder["kill"] = self._kill_tree
                # Cancel may have arrived before the subprocess was spawned
                if self._process_holder.get("_cancel_pending"):
                    self.cancelled = True
                    self._kill_tree()
                    return self.process.returncode or -1, "", ""

            if self._cancel_check is None:
                result = self._communicate_once()
            else:
                result = self._communicate_cancellable(cmd)

            # A process killed out-of-band (holder['kill']) makes communicate()
            # return normally, so the cancel sources are checked once more here.
            if not self.cancelled and self._cancelled():
                self.cancelled = True
                self._kill_tree()
            return result
        finally:
            # Release the handle without terminating anything: descendants
            # that are meant to outlive the command (``adb start-server``)
            # must survive a normal exit.  Idempotent with a kill that already
            # took the handle out of the holder.
            self._release_job()

    def _communicate_once(self) -> tuple[int, str, str]:
        try:
            stdout, stderr = self.process.communicate(timeout=self.timeout)
            return self.process.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            # Kill, then let the caller recover the pipes through
            # :meth:`drain_output` — the same shape as the cancellable path.
            # The exception itself is no help: on timeout CPython leaves the
            # reader threads open and raises without attaching any output.
            self._kill_tree()
            raise TimeoutException(
                f"Command timed out after {self.timeout}s: "
                f"{_describe(self.process.args)}"
            )
        except BaseException:
            # Ctrl+C / any interpreter-level unwind: never leak the child.
            self._kill_tree()
            raise

    def _communicate_cancellable(self, cmd: Command) -> tuple[int, str, str]:
        """Wait for the process in short slices, checking cancellation.

        ``Popen.communicate(timeout=...)`` may be re-entered after a
        ``TimeoutExpired`` without losing buffered output, so the loop is
        safe and the wait stays responsive to cancellation.
        """
        deadline = time.monotonic() + self.timeout
        try:
            while True:
                if self._cancelled():
                    self.cancelled = True
                    self._kill_tree()
                    # Drain rather than discard: the *tool* boundary drops the
                    # value anyway (a killed run raises WorkflowCancelled), but
                    # keeping the branch symmetric with the timeout path means
                    # `drain_output` is the single recovery mechanism.
                    return self.drain_output()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._kill_tree()
                    raise TimeoutException(
                        f"Command timed out after {self.timeout}s: "
                        f"{_describe(cmd)}"
                    )
                try:
                    stdout, stderr = self.process.communicate(
                        timeout=min(_POLL_SLICE_SECONDS, remaining)
                    )
                    return self.process.returncode, stdout, stderr
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            self._kill_tree()
            raise

    def _cancelled(self) -> bool:
        """True when either cancellation source has fired."""
        if self._process_holder is not None and self._process_holder.get(
            "_cancel_pending"
        ):
            return True
        if self._cancel_check is None:
            return False
        try:
            return bool(self._cancel_check())
        except Exception:
            return False

    def _kill_tree(self) -> None:
        """Shut the process down, then sweep its descendants.

        When a job object covers this process it is the *only* kill mechanism
        used: ``TerminateJobObject`` kills the whole tree atomically —
        including grandchildren reparented to another process.  The PID-based
        fallbacks are skipped deliberately, because the child is already cold
        at this point and Windows could in principle have recycled its PID onto
        an unrelated process.

        Otherwise ``terminate()`` runs first for the direct child (portable,
        and the only thing a test double can react to).  Descendant cleanup
        goes through :meth:`_kill_descendants` and is best-effort: it only
        applies to a real ``subprocess.Popen`` and never raises.  Ordering
        matters on Windows: ``taskkill /T`` only reaches the descendants while
        the tree is still alive, so it runs *before* the direct child is
        terminated.
        """
        if self._job_managed:
            self._terminate_job()
            self._reap()
            return

        process = self.process
        if process is None:
            return

        if os.name == "nt":
            # The tree must still exist for /T to walk it.
            self._kill_descendants(process)

        try:
            alive = process.poll() is None
        except Exception:
            alive = False
        if alive:
            try:
                process.terminate()
            except Exception:
                pass
            try:
                process.wait(timeout=_TERMINATE_GRACE_SECONDS)
            except Exception:
                pass

        if os.name != "nt":
            # POSIX: the child led its own session (start_new_session), so its
            # pid IS the process-group id — sweepable even after the leader
            # was reaped.
            self._kill_descendants(process)

        try:
            if process.poll() is None:
                process.kill()
                process.wait()
        except Exception:
            pass

        # NOTE: the pipes are deliberately *not* closed here.  Closing the
        # parent's read ends would make a later :meth:`drain_output` return
        # nothing, silently dropping the output a timeout is supposed to keep
        # — and a job (Windows) or the child's own session (POSIX, swept just
        # above) already reaps any surviving grandchild, so the pipes close on
        # their own once the tree is gone.

    def drain_output(self) -> tuple[int, str, str]:
        """Return ``(returncode, stdout, stderr)`` of a finished process.

        Called after a kill so the caller sees the output the process had
        already produced instead of an empty result — the pipes are drained
        rather than discarded.  A killed process may not have a returncode
        yet, which is reported as ``-1``.

        Re-entering ``communicate()`` **is** the recovery mechanism, and that is
        deliberate: after a timeout CPython leaves the reader threads and the
        pipe handles open precisely so a second call can still collect
        everything the child wrote.  Do not "simplify" this away by reading the
        ``TimeoutExpired`` raised on the way here — it carries no output at all.
        """
        if self.process is None:
            return -1, "", ""
        stdout = stderr = ""
        try:
            stdout, stderr = self.process.communicate(timeout=_DRAIN_TIMEOUT_SECONDS)
        except Exception:
            pass
        returncode = self.process.returncode
        return (
            returncode if returncode is not None else -1,
            stdout or "",
            stderr or "",
        )

    def _reap(self) -> None:
        """Collect the exit status of a process that was already killed."""
        if self.process is None:
            return
        try:
            self.process.wait(timeout=_KILL_GRACE_SECONDS)
        except Exception:
            pass

    def _terminate_job(self) -> bool:
        """Terminate the job covering this process tree. True when one existed.

        When a ``process_holder`` is present it *owns* the handle — the
        out-of-band cancel path takes it out of the holder under a lock.  This
        method therefore drops its own mirror without touching it, rather than
        closing a handle value that the cancel path may already have released
        and that Windows may since have recycled.
        """
        if self._process_holder is not None:
            self._job = None
            return proc_tree.terminate_job_in(self._process_holder)
        job, self._job = self._job, None
        if job is None:
            return False
        proc_tree.terminate_job(job)
        proc_tree.close_job_handle(job)
        return True

    def _release_job(self) -> None:
        """Release the job handle on the normal completion path.

        Same ownership rule as :meth:`_terminate_job`; the holder is asked to
        release the handle so a racing cancel cannot close it twice.  Closing a
        handle kills nothing (no ``KILL_ON_JOB_CLOSE``), so descendants that
        outlive their command survive.
        """
        if self._process_holder is not None:
            self._job = None
            proc_tree.close_job_in(self._process_holder)
            return
        job, self._job = self._job, None
        if job is None:
            return
        proc_tree.close_job_handle(job)

    def _kill_descendants(self, process: "subprocess.Popen") -> None:
        """Best-effort tree kill; a non-real Popen (test double) is skipped."""
        if type(process) is not subprocess.Popen:
            return
        pid = getattr(process, "pid", None)
        if not pid:
            return
        if os.name == "nt":
            self._taskkill(pid)
            return

        killpg = getattr(os, "killpg", None)
        sigkill = getattr(signal, "SIGKILL", None)
        if killpg is None or sigkill is None:
            return
        try:
            # pid == pgid: the child was spawned with start_new_session=True.
            killpg(pid, sigkill)
        except OSError:
            pass

    def _taskkill(self, pid: int) -> None:
        """Kill *pid* and its descendants on Windows, logging any failure."""
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=_TASKKILL_TIMEOUT_SECONDS,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            logger.warning("taskkill for pid=%s failed to run: %s", pid, exc)
            return
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            logger.warning(
                "taskkill for pid=%s returned %s (%s); "
                "falling back to a direct kill",
                pid,
                result.returncode,
                detail or "no output",
            )
        else:
            logger.info("Killed process tree for pid=%s", pid)
