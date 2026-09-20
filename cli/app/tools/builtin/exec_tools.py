#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Builtin command / code execution tools (exec.shell, exec.code).

Security note (CRITICAL): ``exec.code`` never executes user code in-process.
In-process ``exec``/``eval`` sandboxes are escapable via the well-known
``__class__.__mro__[].__subclasses__()`` chain, so they provide no real
isolation. Instead ``exec.code`` serializes the user snippet into a wrapper
script and runs it in a *separate* subprocess via
``ProcessExecutor.run([get_python_bin(), '-c', wrapped], ...)``. The child only
receives the inputs handed to it through the ``CODE_EXEC_INPUTS`` environment
variable — it never sees the workflow engine's internal state.

``exec.shell`` runs a command line in a subprocess too: with ``shell=True`` on
Windows (cmd.exe interprets the string) or ``shell=False`` with
:func:`shlex.split` on Unix (no shell involved, metacharacters such as
``&``/``|``/``;`` are passed literally to the program — safer).

Both go through :class:`~app.common.executor.ProcessExecutor` so a cancelled
run interrupts the process instead of waiting for its timeout, and so the node
is classified as cancelled rather than failed (``WorkflowCancelled``).
"""

# allow: SIZE_OK — port-contract declarations (PortSet inputs/outputs with
# descriptions) are declarative data, not logic; actual executable logic is
# ~130 LOC. Splitting would violate the plan's single-file mandate.
import json
import locale
import os
import shlex

from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.tools.builtin.base import BuiltinTool, ToolContext
from app.common.executor import ProcessExecutor
from app.common.exceptions import TimeoutException, WorkflowCancelled
from app.env import get_python_bin

# Sentinel printed by the exec.code child right before the JSON result payload.
# The parent splits stdout on this marker: everything before is user output,
# the line after is the JSON-serialized ``result`` value.
_EXEC_RESULT_SENTINEL = "===CODE_EXEC_RESULT==="
# Environment variable carrying the JSON-serialized inputs to the child.
_EXEC_INPUTS_ENV = "CODE_EXEC_INPUTS"


def _child_text_encoding() -> str:
    """Encoding used to decode a child process's output.

    ``subprocess.run(text=True)`` decoded with the locale encoding (the ANSI
    code page — ``cp936`` on a Chinese Windows — for ``cmd.exe`` output), while
    ``ProcessExecutor`` defaults to UTF-8.  Pinning the locale encoding here
    keeps the switch to the cancellable executor from changing how non-ASCII
    output is read.
    """
    return locale.getpreferredencoding(False) or "utf-8"


def _build_wrapped_code(code_text: str) -> str:
    """Embed *code_text* into the sandbox runner executed by the child process.

    The wrapper:
      1. reads ``inputs`` from the ``CODE_EXEC_INPUTS`` env var (JSON);
      2. executes the user snippet with ``exec(code_text, globals)`` where the
         globals expose ``inputs`` and ``__name__ == '__main__'``;
      3. reads the ``result`` variable out of the exec namespace;
      4. prints the sentinel followed by the JSON payload to stdout.

    Any exception (including ``SyntaxError``) propagates out of the wrapper,
    so the child prints the traceback to stderr and exits non-zero; the parent
    then reports ``success=False`` with the traceback in ``stderr``.
    """
    return "\n".join(
        [
            "import json, os, sys",
            "def _run():",
            "    _inputs = {}",
            "    try:",
            "        _inputs = json.loads(os.environ.get('CODE_EXEC_INPUTS', '{}'))",
            "    except Exception:",
            "        _inputs = {}",
            "    _globals = {'inputs': _inputs, '__name__': '__main__'}",
            "    exec(" + repr(code_text) + ", _globals)",
            "    _result = _globals.get('result')",
            "    try:",
            "        _payload = json.dumps(_result)",
            "    except Exception:",
            "        _payload = json.dumps({'error': 'result is not JSON-serializable: ' + repr(_result)})",
            "    sys.stdout.write('\\n===CODE_EXEC_RESULT===\\n')",
            "    sys.stdout.write(_payload)",
            "try:",
            "    _run()",
            "except SystemExit:",
            "    raise",
            "except BaseException:",
            "    import traceback",
            "    traceback.print_exc()",
            "    sys.exit(1)",
        ]
    )


class ShellExec(BuiltinTool):
    """Execute a shell command in a subprocess and capture its output.

    On Windows the command string is handed to ``cmd.exe`` via
    ``shell=True``. On Unix the command is split with :func:`shlex.split` and
    run with ``shell=False`` — no shell is involved, so shell metacharacters
    (``&``, ``|``, ``;``, ...) are passed literally to the program rather than
    interpreted, which is safer.

    A non-zero exit code is not an error: the process result is returned as-is
    with ``success=False``; only a subprocess-level failure (e.g. timeout,
    invalid command) surfaces via ``stderr`` with ``returncode=-1``.  A
    cancelled run is different again: it raises ``WorkflowCancelled`` so the
    engine can mark the node cancelled.

    On Windows the real command runs as a grandchild of ``cmd.exe``, so
    ``Popen.terminate()`` on the immediate child would leave it running — the
    executor's job object is what actually stops the work.
    """

    name = "exec.shell"
    description = "Execute a shell command in a subprocess and capture its stdout/stderr and exit code."

    ports = PortSet(
        inputs=[
            Port(
                "command",
                TypeAnnotation(BaseType.TEXT),
                True,
                "The command line to execute.",
            ),
            Port(
                "cwd",
                TypeAnnotation(BaseType.DIRECTORY),
                False,
                "Working directory for the command; defaults to the tool context work_dir.",
            ),
            Port(
                "timeout",
                TypeAnnotation(BaseType.NUMBER),
                False,
                "Timeout in seconds before the process is killed (default 600).",
            ),
            Port(
                "env",
                TypeAnnotation(BaseType.JSON),
                False,
                "Extra environment variables merged over the parent environment (default {}).",
            ),
        ],
        outputs=[
            Port(
                "returncode",
                TypeAnnotation(BaseType.NUMBER),
                True,
                "Process exit code (-1 on subprocess failure).",
            ),
            Port(
                "stdout",
                TypeAnnotation(BaseType.TEXT),
                True,
                "Captured standard output.",
            ),
            Port(
                "stderr",
                TypeAnnotation(BaseType.TEXT),
                True,
                "Captured standard error.",
            ),
            Port(
                "success",
                TypeAnnotation(BaseType.BOOLEAN),
                True,
                "True when the process exited with code 0.",
            ),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        """Run ``inputs["command"]`` and return its captured result."""
        command = inputs["command"]
        cwd = inputs.get("cwd") or context.work_dir
        timeout = inputs.get("timeout", 600)
        extra_env = inputs.get("env") or {}
        env = {**os.environ, **extra_env}

        if os.name == "nt":
            # Windows: cmd.exe interprets the command string, so the command
            # that actually does the work is a grandchild of the process we
            # spawn — the executor needs the job object to stop it.
            args = command
            shell = True
        else:
            # Unix: no shell, metacharacters passed literally to the program.
            args = shlex.split(command)
            shell = False

        executor = ProcessExecutor(
            timeout=timeout,
            process_holder=context.process_holder,
            cancel_check=context.cancel_check,
        )
        try:
            returncode, stdout, stderr = executor.run(
                cmd=args,
                cwd=cwd,
                env=env,
                shell=shell,
                encoding=_child_text_encoding(),
            )
        except TimeoutException:
            return {
                "returncode": -1,
                "stdout": executor.drain_output()[1],
                "stderr": f"timeout after {timeout}s",
                "success": False,
            }
        except Exception as exc:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": str(exc),
                "success": False,
            }

        # A killed run must not surface as a plain failure: raising lets the
        # engine classify the node as cancelled instead of failed.
        if context.cancelled():
            raise WorkflowCancelled()

        return {
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "success": returncode == 0,
        }


class CodeExec(BuiltinTool):
    """Execute a code snippet in an isolated subprocess and return its result.

    The snippet runs as the body of ``exec(code, {'inputs': inputs, '__name__':
    '__main__'})`` inside a freshly spawned Python interpreter (see the module
    docstring for the security rationale). The value it assigns to the
    ``result`` variable is JSON-serialized and returned; ``stdout`` carries
    whatever the snippet printed. Only ``language='python'`` is supported in
    the MVP — any other value raises :class:`NotImplementedError`.
    """

    name = "exec.code"
    description = "Execute a code snippet in an isolated subprocess and return the JSON result variable it assigns."

    ports = PortSet(
        inputs=[
            Port(
                "code",
                TypeAnnotation(BaseType.TEXT),
                True,
                "Source code to execute.",
            ),
            Port(
                "language",
                TypeAnnotation(BaseType.TEXT),
                False,
                "Code language; only 'python' is supported (default 'python').",
            ),
            Port(
                "inputs",
                TypeAnnotation(BaseType.JSON),
                False,
                "JSON object exposed to the snippet as the `inputs` variable (default {}).",
            ),
            Port(
                "timeout",
                TypeAnnotation(BaseType.NUMBER),
                False,
                "Timeout in seconds before the snippet is killed (default 30).",
            ),
        ],
        outputs=[
            Port(
                "result",
                TypeAnnotation(BaseType.JSON),
                True,
                "JSON-serializable value of the `result` variable (null if unset).",
            ),
            Port(
                "stdout",
                TypeAnnotation(BaseType.TEXT),
                True,
                "Standard output produced by the snippet.",
            ),
            Port(
                "stderr",
                TypeAnnotation(BaseType.TEXT),
                True,
                "Standard error; contains the traceback when the snippet fails.",
            ),
            Port(
                "success",
                TypeAnnotation(BaseType.BOOLEAN),
                True,
                "True when the snippet executed without raising.",
            ),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        """Run ``inputs["code"]`` in a separate subprocess and parse the result."""
        code_text = inputs["code"]
        language = inputs.get("language", "python")
        user_inputs = inputs.get("inputs") or {}
        timeout = inputs.get("timeout", 30)

        if language != "python":
            raise NotImplementedError(
                f"exec.code only supports language='python', got {language!r}"
            )

        wrapped = _build_wrapped_code(code_text)
        child_env = {**os.environ, _EXEC_INPUTS_ENV: json.dumps(user_inputs)}
        python_bin = get_python_bin()

        executor = ProcessExecutor(
            timeout=timeout,
            process_holder=context.process_holder,
            cancel_check=context.cancel_check,
        )
        try:
            returncode, stdout, stderr = executor.run(
                cmd=[python_bin, "-c", wrapped],
                env=child_env,
                shell=False,
                encoding=_child_text_encoding(),
            )
        except TimeoutException:
            return {
                "result": None,
                "stdout": executor.drain_output()[1],
                "stderr": f"timeout after {timeout}s",
                "success": False,
            }
        except Exception as exc:
            return {
                "result": None,
                "stdout": "",
                "stderr": str(exc),
                "success": False,
            }

        # A killed run must not surface as a plain failure: raising lets the
        # engine classify the node as cancelled instead of failed.
        if context.cancelled():
            raise WorkflowCancelled()

        stdout = stdout or ""
        stderr = stderr or ""
        result_value = None
        user_stdout = stdout
        if _EXEC_RESULT_SENTINEL in stdout:
            before, _, after = stdout.partition(_EXEC_RESULT_SENTINEL)
            user_stdout = before.rstrip()
            payload = after.strip()
            if payload:
                try:
                    result_value = json.loads(payload)
                except (json.JSONDecodeError, TypeError):
                    result_value = None

        return {
            "result": result_value,
            "stdout": user_stdout,
            "stderr": stderr,
            "success": returncode == 0,
        }
