#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProcessExecutor — manages subprocess lifecycle: spawn, monitor, kill.
"""

import subprocess
import time
from typing import Callable, Optional

from app.common import proc_tree
from app.common.exceptions import TimeoutException

#: Cancellation poll interval while waiting for a subprocess, in seconds.
_POLL_SLICE_SECONDS = 0.5

#: How long to wait for a killed process to be reaped, in seconds.
_KILL_GRACE_SECONDS = 5.0

#: How long the post-kill drain waits for the pipe buffers, in seconds.
_DRAIN_TIMEOUT_SECONDS = 5.0


class ProcessExecutor:
    """Manages subprocess lifecycle: spawn, monitor, kill.

    If *process_holder* is provided it must be a dict; the running
    ``subprocess.Popen`` is stored as ``process_holder['process']`` so an
    external coordinator (e.g. TaskManager) can kill it on cancel.

    *cancel_check* is an independent, polled cancellation source: while
    waiting for the process the executor re-checks it every
    ``_POLL_SLICE_SECONDS`` and kills the process when it reports True.  Both
    sources are honored — the holder flag covers a cancel that arrived before
    the process existed, the callback covers everything after.
    """

    def __init__(
        self,
        timeout: int = 600,
        process_holder: Optional[dict] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ):
        self.timeout = timeout
        self.process: Optional[subprocess.Popen] = None
        self._process_holder = process_holder
        self._cancel_check = cancel_check
        #: Job-object handle covering the whole child tree (Windows only).
        self._job: Optional[int] = None
        #: True once a job covered this process — the job is then the only
        #: kill mechanism used, never the (possibly recycled) PID.
        self._job_managed = False

    def run(
        self,
        cmd: "list[str] | str",
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
        shell: bool = False,
        text: bool = True,
        encoding: str = 'utf-8',
        errors: str = 'ignore',
        on_output: Optional[Callable[[str], None]] = None,
    ) -> tuple[int, str, str]:
        """Execute command and return (returncode, stdout, stderr).

        Returns a negative/forced returncode when the command was killed by
        cancellation, so the caller reports a failed node rather than a hang.

        ``cmd`` is a list on POSIX-style invocations and a **string** when the
        caller runs through a shell (``shell=True``), which is how
        ``exec.shell`` reaches ``cmd.exe`` on Windows.
        """
        # Enrol the child in a job object straight after spawn: membership is
        # inherited, so this is the only moment at which the whole future tree
        # (``cmd.exe`` plus the real command it is about to start) can be
        # captured.
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
            **proc_tree.spawn_options(),
        )
        try:
            self._job = proc_tree.attach_job(self.process, self._process_holder)
            self._job_managed = self._job is not None

            if self._process_holder is not None:
                self._process_holder["process"] = self.process
                self._process_holder["_pid"] = self.process.pid
                # Cancel may have arrived before the subprocess was spawned
                if self._process_holder.get("_cancel_pending"):
                    self._kill()
                    return self.drain_output()

            if self._cancel_check is None:
                return self._communicate_once()

            return self._communicate_cancellable(cmd)
        finally:
            # Release the handle without terminating anything: descendants
            # that are meant to outlive the command (``adb start-server``)
            # must survive a normal exit.
            self._release_job()

    def _communicate_once(self) -> tuple[int, str, str]:
        try:
            stdout, stderr = self.process.communicate(timeout=self.timeout)
            return self.process.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            # Same shape as the cancellable path: kill, then let the caller
            # recover the pipes through :meth:`drain_output`.  The exception
            # itself is no help — on timeout CPython leaves the reader threads
            # open and raises without attaching any output.
            self._kill()
            raise TimeoutException(
                f"Command timed out after {self.timeout}s: "
                f"{' '.join(self.process.args) if isinstance(self.process.args, list) else self.process.args}"
            )

    def _communicate_cancellable(self, cmd: "list[str] | str") -> tuple[int, str, str]:
        """Wait for the process in short slices, checking cancellation.

        ``Popen.communicate(timeout=...)`` may be re-entered after a
        ``TimeoutExpired`` without losing buffered output, so the loop is
        safe and the wait stays responsive to cancellation.
        """
        deadline = time.monotonic() + self.timeout
        while True:
            if self._cancelled():
                self._kill()
                return self.drain_output()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._kill()
                raise TimeoutException(
                    f"Command timed out after {self.timeout}s: "
                    f"{' '.join(cmd) if isinstance(cmd, list) else cmd}"
                )
            try:
                stdout, stderr = self.process.communicate(
                    timeout=min(_POLL_SLICE_SECONDS, remaining)
                )
                return self.process.returncode, stdout, stderr
            except subprocess.TimeoutExpired:
                continue

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

    def _kill(self):
        """Kill the whole process tree: job object, tree tools, then ``Popen``."""
        if self._job_managed:
            # A job covers this process, so it is the only kill mechanism used:
            # ``TerminateJobObject`` kills the entire tree atomically —
            # including grandchildren reparented to another process.  The
            # PID-based fallbacks are skipped deliberately, because the child
            # is already cold at this point and Windows could in principle have
            # recycled its PID onto an unrelated process.
            self._terminate_job()
            self._reap()
            return
        if self.process is None or self.process.poll() is not None:
            return
        if not proc_tree.terminate_tree(self.process.pid, grace=_KILL_GRACE_SECONDS):
            self.process.terminate()
        try:
            self.process.wait(timeout=_KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

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
        release the handle so a racing cancel cannot close it twice.
        """
        if self._process_holder is not None:
            self._job = None
            proc_tree.close_job_in(self._process_holder)
            return
        job, self._job = self._job, None
        if job is None:
            return
        proc_tree.close_job_handle(job)
