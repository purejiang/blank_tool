#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProcessExecutor — manages subprocess lifecycle: spawn, monitor, kill.
"""

import subprocess
import threading
from typing import Optional, Callable
from app.common.exceptions import TimeoutException


class ProcessExecutor:
    """Manages subprocess lifecycle: spawn, monitor, kill."""

    def __init__(self, timeout: int = 600):
        self.timeout = timeout
        self.process: Optional[subprocess.Popen] = None

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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            encoding=encoding,
            errors=errors,
        )

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
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None
