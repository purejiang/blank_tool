#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base command executor — template method pattern with ProcessExecutor delegation.
"""

import re
import subprocess
import traceback
import shutil
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Union
from app.utils.logger import Logger
from app.common.executor import ProcessExecutor
from app.common.exceptions import TimeoutException


class CommandExecutionContext:
    """
    Command execution context.

    Attributes:
        cwd: Working directory
        timeout: Timeout in seconds
        encoding: Text encoding
        errors: Encoding error handling
        text: Whether to run in text mode
        shell: Whether to use shell execution
        capture_output: Whether to capture output
        env: Environment variables
        stream: Whether to use streaming output
        log_output: Whether to log output
    """

    def __init__(self,
                 cwd: str = None,
                 timeout: int = 60 * 10,
                 encoding: str = 'utf-8',
                 errors: str = 'ignore',
                 text: bool = True,
                 shell: bool = False,
                 capture_output: bool = True,
                 env: Dict[str, str] = None,
                 stream: bool = False,
                 log_output: bool = True,
                 process_holder: Dict[str, Any] = None):
        self.cwd = cwd
        self.timeout = timeout
        self.encoding = encoding
        self.errors = errors
        self.text = text
        self.shell = shell
        self.capture_output = capture_output
        self.env = env
        self.stream = stream
        self.log_output = log_output
        self.process_holder = process_holder


class BaseCommandExecutor(ABC):
    """Abstract base for command executors (template method pattern)."""

    def __init__(self):
        self.name = self.__class__.__name__
        self.logger = Logger.get_logger(self.name)

    @abstractmethod
    def execute(self, command: Union[str, List[str]],
                context: CommandExecutionContext = None) -> Dict[str, Any]:
        """
        Execute a command.

        Args:
            command: Command as string or list
            context: Execution context

        Returns:
            Result dict with keys: returncode, stdout, stderr, success, command
        """
        pass

    @abstractmethod
    def validate_command(self, command: Union[str, List[str]]) -> bool:
        """
        Validate whether a command is executable.

        Args:
            command: Command to validate

        Returns:
            True if the command is valid
        """
        pass

    def _log_info(self, message: str):
        if self.logger:
            self.logger.info(message)

    def _log_warning(self, message: str):
        if self.logger:
            self.logger.warning(message)

    def _log_error(self, message: str):
        if self.logger:
            self.logger.error(message)

    def _log_debug(self, message: str):
        if self.logger:
            self.logger.debug(message)


class CommandExecutor(BaseCommandExecutor):
    """Command-line executor — delegates subprocess lifecycle to ProcessExecutor."""

    _SENSITIVE_PATTERNS = [
        # apksigner --ks-pass pass:XXX
        (re.compile(r'(--ks-pass\s+pass:)[^\s]+', re.IGNORECASE), r'\1***'),
        (re.compile(r'(--key-pass\s+pass:)[^\s]+', re.IGNORECASE), r'\1***'),
        # jarsigner -storepass XXX, -keypass XXX
        (re.compile(r'(-storepass\s+)[^\s]+', re.IGNORECASE), r'\1***'),
        (re.compile(r'(-keypass\s+)[^\s]+', re.IGNORECASE), r'\1***'),
        # generic pass: prefix in combined args
        (re.compile(r'(pass:)[^\s,\]]+', re.IGNORECASE), r'\1***'),
    ]

    @staticmethod
    def _redact_sensitive_args(cmd_str: str) -> str:
        """Mask passwords and secrets in command strings before logging."""
        for pattern, replacement in CommandExecutor._SENSITIVE_PATTERNS:
            cmd_str = pattern.sub(replacement, cmd_str)
        return cmd_str

    def execute(self, command: Union[str, List[str]],
                context: CommandExecutionContext) -> Union[Dict[str, Any], subprocess.Popen]:
        """
        Execute a system command.

        If context.stream is True, returns a subprocess.Popen object for
        streaming output. Otherwise returns a result dict.

        Args:
            command: Command as string or list
            context: Execution context

        Returns:
            Result dict or Popen object (if streaming)
        """
        if context is None:
            context = CommandExecutionContext()

        if isinstance(command, str):
            cmd_str = command
            if context.shell is None:
                context.shell = True
        else:
            cmd_str = ' '.join(command)
            if context.shell is None:
                context.shell = False

        self._log_info(f"[COMMAND] Executing: {self._redact_sensitive_args(cmd_str)}")
        self._log_debug(
            f"[CONTEXT] cwd={context.cwd} shell={context.shell} stream={context.stream}"
        )

        # Streaming mode: return a live Popen object for line-by-line reading
        if context.stream:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=context.text,
                encoding=context.encoding,
                errors=context.errors,
                cwd=context.cwd,
                shell=context.shell,
                env=context.env,
            )
            if context.process_holder is not None:
                context.process_holder["process"] = proc
            return proc

        # Non-streaming mode: delegate to ProcessExecutor
        try:
            executor = ProcessExecutor(timeout=context.timeout, process_holder=context.process_holder)
            returncode, stdout, stderr = executor.run(
                cmd=command,
                cwd=context.cwd,
                env=context.env,
                shell=context.shell,
                text=context.text,
                encoding=context.encoding,
                errors=context.errors,
            )

            success = returncode == 0

            if not success:
                self._log_warning(f"[COMMAND] Return code: {returncode}")
                if context.log_output:
                    if stdout:
                        self._log_warning(f"[STDOUT] {stdout.strip()}")
                    if stderr:
                        self._log_warning(f"[STDERR] {stderr.strip()}")
            else:
                self._log_debug(f"[COMMAND] Return code: {returncode}")
                if context.log_output:
                    if stdout:
                        self._log_debug(f"[STDOUT] {stdout.strip()}")
                    if stderr:
                        self._log_debug(f"[STDERR] {stderr.strip()}")

            return {
                "success": success,
                "stdout": stdout,
                "stderr": stderr,
                "returncode": returncode,
                "command": cmd_str,
            }

        except TimeoutException:
            error_msg = f"Command timed out ({context.timeout}s): {self._redact_sensitive_args(cmd_str)}"
            self._log_error(f"[COMMAND] {error_msg}")
            raise
        except Exception as e:
            error_msg = f"Command execution error: {self._redact_sensitive_args(cmd_str)}, error: {str(e)}"
            tb = traceback.format_exc()
            self._log_error(f"[COMMAND] {error_msg}\n{tb}")
            raise

    def validate_command(self, command: Union[str, List[str]]) -> bool:
        """
        Validate whether a system command is available.

        Args:
            command: Command as string or list

        Returns:
            True if the command executable is found in PATH
        """
        if isinstance(command, str):
            cmd_name = command.split()[0] if command.strip() else ""
        else:
            cmd_name = command[0] if command else ""

        if not cmd_name:
            return False

        return shutil.which(cmd_name) is not None
