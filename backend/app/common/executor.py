#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProcessExecutor — manages subprocess lifecycle: spawn, monitor, kill.
"""

import subprocess
import threading
from typing import Optional, Callable
from app.common.exceptions import TimeoutException
from app.utils.logger import Logger


def terminate_gracefully(proc: Optional[subprocess.Popen], grace: float = 5.0) -> bool:
    """Terminate ``proc``: SIGTERM, wait ``grace`` seconds, then SIGKILL.

    Safe to call on an already-exited or ``None`` process. Returns True when a
    live process was actually signalled. Single implementation — the streaming
    deadline watcher, ProcessExecutor and TaskManager cancel all route here.
    """
    if proc is None or proc.poll() is not None:
        return False
    try:
        proc.terminate()
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            Logger.warning(
                f"Process {proc.pid} ignored SIGTERM after {grace}s, killing"
            )
            proc.kill()
            proc.wait()
    except Exception as exc:  # pragma: no cover - OS-level race
        Logger.warning(f"Failed to terminate process: {exc}")
    return True


class ProcessExecutor:
    """Manages subprocess lifecycle: spawn, monitor, kill.

    If *process_holder* is provided it must be a dict; the running
    ``subprocess.Popen`` is stored as ``process_holder['process']`` so
    an external coordinator (e.g. TaskManager) can kill it on cancel.
    """

    def __init__(self, timeout: int = 600, process_holder: Optional[dict] = None):
        self.timeout = timeout
        self.process: Optional[subprocess.Popen] = None
        self._process_holder = process_holder

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
        """Execute command and return (returncode, stdout, stderr)."""
        self.process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            shell=shell,
            # never let a child share our stdin (JSON-RPC pipe) — see
            # base_executor.execute() for the stolen-request incident
            stdin=subprocess.DEVNULL,
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

        try:
            stdout, stderr = self.process.communicate(timeout=self.timeout)
            return self.process.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            self._kill()
            raise TimeoutException(
                f"Command timed out after {self.timeout}s: {' '.join(cmd)}"
            )

    def _kill(self):
        """Graceful shutdown: SIGTERM -> 5s wait -> SIGKILL."""
        terminate_gracefully(self.process)

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None
