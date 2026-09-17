#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProcessExecutor — manages subprocess lifecycle: spawn, monitor, kill.
"""

import subprocess
import time
from typing import Callable, Optional

from app.common.exceptions import TimeoutException

#: Cancellation poll interval while waiting for a subprocess, in seconds.
_POLL_SLICE_SECONDS = 0.5


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

    def run(
        self,
        cmd: list[str],
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
        """
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
        )
        if self._process_holder is not None:
            self._process_holder["process"] = self.process
            self._process_holder["_pid"] = self.process.pid
            # Cancel may have arrived before the subprocess was spawned
            if self._process_holder.get("_cancel_pending"):
                self._kill()
                return self.process.returncode or -1, "", ""

        if self._cancel_check is None:
            return self._communicate_once()

        return self._communicate_cancellable(cmd)

    def _communicate_once(self) -> tuple[int, str, str]:
        try:
            stdout, stderr = self.process.communicate(timeout=self.timeout)
            return self.process.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            self._kill()
            raise TimeoutException(
                f"Command timed out after {self.timeout}s: "
                f"{' '.join(self.process.args) if isinstance(self.process.args, list) else self.process.args}"
            )

    def _communicate_cancellable(self, cmd: list[str]) -> tuple[int, str, str]:
        """Wait for the process in short slices, checking cancellation.

        ``Popen.communicate(timeout=...)`` may be re-entered after a
        ``TimeoutExpired`` without losing buffered output, so the loop is
        safe and the wait stays responsive to cancellation.
        """
        deadline = time.monotonic() + self.timeout
        while True:
            if self._cancelled():
                self._kill()
                return self.process.returncode or -1, "", ""
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._kill()
                raise TimeoutException(
                    f"Command timed out after {self.timeout}s: "
                    f"{' '.join(cmd)}"
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
        """Graceful shutdown: SIGTERM -> 5s wait -> SIGKILL."""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
