#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data-driven execution of third-party tools via JSON descriptors.

A :class:`ToolDescriptor` declares *what* an external tool is (name, binary
location, env dependencies, validation/version rules) as plain data.
:class:`DescriptorTool` turns that declaration into a runnable object
mirroring the legacy :class:`~app.tools.base_tool.BaseTool` surface (``name``,
``is_valid``, ``version``, ``tool_path``, ``execute``), so the tool registry
can manage code-based and descriptor-based tools uniformly.  The binary is
resolved via :class:`~app.env.registry.EnvironmentRegistry`, the command line
built from the descriptor ``type``, and execution delegated to
:class:`~app.common.base_executor.CommandExecutor`.
"""

import json
import os
import platform
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.common.base_executor import CommandExecutor, CommandExecutionContext
from app.common.exceptions import ToolException
from app.env.registry import EnvironmentRegistry
from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.tools.builtin.base import ToolContext
from app.utils.env import get_java_bin, get_node_bin, get_python_bin, get_runtime_dir
from app.utils.logger import Logger

# platform.system() -> key in a per-platform tool path dict.
_PLATFORM_KEY: Dict[str, str] = {"Windows": "win", "Darwin": "mac", "Linux": "linux"}


@dataclass
class Operation:
    """A single named operation a descriptor tool can perform.

    ``inputs``/``outputs`` are the typed ports the operation declares;
    ``args_map`` is a mixed list of literal command fragments and
    placeholders.  A placeholder is either ``{"param": <input_name>}``
    (substitute the bound value of that input) or ``{"flag": <bool_input>,
    "value": <arg>}`` (emit ``value`` when the boolean input is true).
    Placeholder shape is not validated beyond "is a str or dict".

    ``timeout`` overrides the execution timeout for this operation, in
    seconds (None = executor default, 600).  ``cwd`` overrides the working
    directory for this operation: a static path, ``$workdir`` (the
    workflow's work dir), or ``$inputs.<key>`` (the bound value of a
    declared input); None = the workflow's work dir.
    """

    name: str
    description: str = ""
    inputs: List[Port] = field(default_factory=list)
    outputs: List[Port] = field(default_factory=list)
    args_map: list = field(default_factory=list)
    timeout: Optional[int] = None
    cwd: Optional[str] = None


@dataclass
class ToolDescriptor:
    """Data declaration of an external third-party tool (descriptor D1).

    ``path`` is an absolute path, a relative path (anchored at the runtime
    directory), or a per-platform dict ``{"win": ..., "mac": ...,
    "linux": ...}``.  ``type`` follows the same rules — a plain type string,
    or a per-platform dict (e.g. apksigner is a ``java_jar`` on Windows but
    a plain ``binary`` on mac/linux).  ``validate`` carries ``{"cmd",
    "expect_contains", "expect_in", "expect_returncode"}``; ``version``
    carries ``{"cmd", "regex", "from_stream"}``.  ``sensitive_arg_patterns``
    is a log-redaction extension point (CommandExecutor applies its own).
    """

    name: str
    display_name: str
    type: Union[str, Dict[str, str]]  # binary | java_jar | python_script | node_script | shell_script
    path: Union[str, Dict[str, str]]
    env_deps: List[str]
    validate: Dict[str, Any]
    version: Dict[str, Any]
    inputs: List[Port]
    outputs: List[Port]
    sensitive_arg_patterns: List[str] = field(default_factory=list)
    operations: List[Operation] = field(default_factory=list)
    parse_stdout_json: bool = False

    _VALID_TYPES = frozenset(
        {"binary", "java_jar", "python_script", "node_script", "shell_script"}
    )

    def __post_init__(self) -> None:
        """Validate the descriptor's core fields."""
        if isinstance(self.type, str):
            if self.type not in self._VALID_TYPES:
                raise ValueError(
                    f"invalid tool type {self.type!r}; must be one of "
                    f"{sorted(self._VALID_TYPES)}"
                )
        elif isinstance(self.type, dict):
            if not self.type:
                raise ValueError("type dict must not be empty")
            invalid = [v for v in self.type.values() if v not in self._VALID_TYPES]
            if invalid:
                raise ValueError(
                    f"invalid tool type(s) {invalid!r}; must be one of "
                    f"{sorted(self._VALID_TYPES)}"
                )
        else:
            raise ValueError(
                f"type must be a string or per-platform dict, got {type(self.type).__name__}"
            )
        if not self.name:
            raise ValueError("name must be a non-empty string")
        if not self.display_name:
            raise ValueError("display_name must be a non-empty string")
        if not self.path:
            raise ValueError("path must be a string or per-platform dict")
        if not isinstance(self.env_deps, list):
            raise ValueError(
                f"env_deps must be a list, got {type(self.env_deps).__name__}"
            )


def _port_from_dict(data: dict) -> Port:
    """Build a Port from a JSON port dict (validates the type annotation)."""
    type_data = data.get("type")
    if isinstance(type_data, dict):
        annotation = TypeAnnotation(BaseType(type_data["base"]), type_data.get("subtype"))
    else:
        annotation = TypeAnnotation(BaseType(type_data), None)
    return Port(
        name=data["name"],
        type=annotation,
        required=data.get("required", True),
        description=data.get("description", ""),
        direction=data.get("direction", "input"),
    )


def _ports_from(entries: Any, role: str, path: str) -> List[Port]:
    """Parse a JSON port list (``role`` is "inputs" or "outputs")."""
    if not isinstance(entries, list):
        raise ValueError(f"descriptor field {role!r} must be a list: {path}")
    ports: List[Port] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"descriptor {role}[{index}] must be an object: {path}")
        try:
            ports.append(_port_from_dict(entry))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid {role}[{index}] in {path}: {exc}") from exc
    return ports


def _operations_from(entries: Any, path: str, tool_name: str) -> List[Operation]:
    """Parse the JSON ``operations`` list into :class:`Operation` objects.

    An operation dict must declare ``name``; its inputs/outputs reuse the
    same port parsing as the descriptor-level ports, and ``args_map`` is
    taken as-is (literal strings and dict placeholders).
    """
    if not isinstance(entries, list):
        raise ValueError(f"descriptor field 'operations' must be a list: {path}")
    operations: List[Operation] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"descriptor operations[{index}] must be an object: {path}")
        if "name" not in entry:
            raise ValueError(
                f"operation missing required field 'name' in descriptor {tool_name}"
            )
        operations.append(
            Operation(
                name=entry["name"],
                description=entry.get("description", ""),
                inputs=_ports_from(entry.get("inputs", []), "inputs", path),
                outputs=_ports_from(entry.get("outputs", []), "outputs", path),
                args_map=list(entry.get("args_map", [])),
                timeout=entry.get("timeout"),
                cwd=entry.get("cwd"),
            )
        )
    return operations


def load_descriptor(path: str) -> ToolDescriptor:
    """Load a tool descriptor from a JSON file.

    Raises ValueError when the file is missing, malformed, or fails
    descriptor validation.
    """
    file_path = Path(path)
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"descriptor file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"descriptor file is not valid JSON: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"descriptor root must be an object: {path}")

    for key in ("name", "display_name", "type", "path"):
        if key not in raw:
            raise ValueError(f"descriptor missing required field: {key!r}: {path}")

    operations = (
        _operations_from(raw["operations"], path, raw["name"])
        if "operations" in raw
        else []
    )

    return ToolDescriptor(
        name=raw["name"],
        display_name=raw["display_name"],
        type=raw["type"],
        path=raw["path"],
        env_deps=list(raw.get("env_deps", [])),
        validate=dict(raw.get("validate") or {}),
        version=dict(raw.get("version") or {}),
        inputs=_ports_from(raw.get("inputs", []), "inputs", path),
        outputs=_ports_from(raw.get("outputs", []), "outputs", path),
        sensitive_arg_patterns=list(raw.get("sensitive_arg_patterns", [])),
        operations=operations,
        parse_stdout_json=bool(raw.get("parse_stdout_json", False)),
    )


def _select_platform_path(path: Union[str, Dict[str, str]]) -> str:
    """Pick the path for the current platform from a per-platform dict.

    Falls back to the first usable entry (``win``, ``mac``, ``linux`` order)
    when the current platform's key is absent.
    """
    if isinstance(path, str):
        return path
    current = _PLATFORM_KEY.get(platform.system())
    if current and path.get(current):
        return path[current]
    for key in ("win", "mac", "linux"):
        if path.get(key):
            return path[key]
    raise ValueError(f"per-platform path dict has no usable entry: {path}")


def _select_platform_type(tool_type: Union[str, Dict[str, str]]) -> str:
    """Pick the tool type for the current platform from a per-platform dict.

    Plain type strings pass through unchanged; dicts reuse the same
    platform-selection rules as ``_select_platform_path``.
    """
    if isinstance(tool_type, str):
        return tool_type
    return _select_platform_path(tool_type)


def _get_platform_shell() -> str:
    """Return the platform shell interpreter for ``shell_script`` tools.

    On Windows: ``COMSPEC`` (cmd.exe) or ``cmd.exe`` from PATH.
    On other platforms: ``/bin/sh``.
    """
    if platform.system() == "Windows":
        return os.environ.get("COMSPEC", "") or shutil.which("cmd.exe") or "cmd.exe"
    return "/bin/sh"


class DescriptorTool:
    """Execute a third-party tool declared by a :class:`ToolDescriptor`.

    Mirrors :class:`~app.tools.base_tool.BaseTool` (``name``, ``is_valid``,
    ``version``, ``tool_path``) so the tool registry can manage descriptor-
    based and code-based tools uniformly.  ``is_valid`` requires every
    env_dep to resolve, the binary to exist, and validation to pass.
    """

    # Interpreter env_dep name per script-type tool.
    _INTERPRETER_DEP_BY_TYPE = {
        "java_jar": "java",
        "python_script": "python",
        "node_script": "node",
    }

    def __init__(
        self,
        descriptor: ToolDescriptor,
        env_registry: EnvironmentRegistry,
        source_dir: Optional[str] = None,
    ):
        """Resolve env deps, locate the binary, and validate the tool.

        Args:
            descriptor: tool declaration data.
            env_registry: resolves named environments to concrete paths.
            source_dir: optional directory the descriptor was loaded from;
                relative script paths resolve against it (then runtime dir,
                then unchanged).
        """
        self._descriptor = descriptor
        self._env_registry = env_registry
        self._source_dir = source_dir
        self._logger = Logger.get_logger(descriptor.name or "DescriptorTool")
        self._command_executor = CommandExecutor()
        self.name = descriptor.name
        self.tool_path = self._resolve_tool_path()
        self._env_resolutions = self._resolve_env_deps()
        self.is_valid = self._compute_valid()
        self.version = "" if not self.is_valid else self.get_tool_version()

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def _resolve_tool_path(self) -> str:
        """Resolve the descriptor path to an absolute path on this platform.

        Priority:
        1. Absolute paths (used as-is).
        2. Relative to ``_source_dir`` (descriptor file location) — exists-or-not;
           non-existent paths fall through to the next level.
        3. Relative to the runtime directory.
        4. Unchanged (backward-compatible, caller decides).
        """
        path = _select_platform_path(self._descriptor.path)
        if os.path.isabs(path):
            return os.path.normpath(path)
        # Try the descriptor's source directory first
        if self._source_dir:
            candidate = os.path.normpath(os.path.join(self._source_dir, path))
            if os.path.exists(candidate):
                return candidate
        runtime_dir = get_runtime_dir()
        if runtime_dir:
            return os.path.normpath(os.path.join(runtime_dir, path))
        # Final fallback: source_dir-relative (for overlay scripts that
        # resolved at import time but are not yet on disk)
        if self._source_dir:
            return os.path.normpath(os.path.join(self._source_dir, path))
        return os.path.normpath(path)

    def _resolve_env_deps(self) -> Dict[str, str]:
        """Resolve every declared env_dep to its binary path ("" when missing)."""
        resolutions: Dict[str, str] = {}
        for dep in self._descriptor.env_deps:
            resolutions[dep] = self._env_registry.resolve(dep).binary_path or ""
        return resolutions

    def get_env_resolutions(self) -> Dict[str, str]:
        """Return the resolved binary path for every declared env_dep."""
        return dict(self._env_resolutions)

    @property
    def ports(self) -> PortSet:
        """The declared input/output port set (uniform with BuiltinTool)."""
        return PortSet(self._descriptor.inputs, self._descriptor.outputs)

    # ------------------------------------------------------------------
    # Validation & versioning
    # ------------------------------------------------------------------

    def _compute_valid(self) -> bool:
        """Validity: env deps resolve, binary exists, validate passes."""
        if any(not binary for binary in self._env_resolutions.values()):
            return False
        if not self.tool_path or not os.path.exists(self.tool_path):
            return False
        return self.validate_tool()

    def validate_tool(self) -> bool:
        """Run the validate command; check returncode and expected output.

        True when the returncode matches ``expect_returncode`` (default 0)
        and the output contains ``expect_contains`` in the configured stream
        (default ``either``); a descriptor without a validate spec falls
        back to binary existence.
        """
        validate_spec = self._descriptor.validate
        if not validate_spec:
            return bool(self.tool_path) and os.path.exists(self.tool_path)
        cmd = validate_spec.get("cmd")
        if not cmd:
            return False
        result = self._run(cmd)
        if result.get("returncode") != int(validate_spec.get("expect_returncode", 0)):
            return False
        expect_contains = validate_spec.get("expect_contains")
        if not expect_contains:
            return True
        return expect_contains in self._select_stream(
            result, validate_spec.get("expect_in", "either")
        )

    def get_tool_version(self) -> str:
        """Run the version command and extract the version via the regex.

        Returns the captured group, or "" when there is no version spec,
        the command fails, the regex does not match, or it is invalid.
        """
        version_spec = self._descriptor.version
        if not version_spec:
            return ""
        cmd = version_spec.get("cmd")
        regex = version_spec.get("regex")
        if not cmd or not regex:
            return ""
        result = self._run(cmd)
        output = self._select_stream(result, version_spec.get("from_stream", "stdout"))
        try:
            match = re.search(regex, output)
        except re.error as exc:
            self._logger.warning(f"invalid version regex for {self.name}: {exc}")
            return ""
        return match.group(1) if match else ""

    @staticmethod
    def _select_stream(result: Dict[str, Any], stream: str) -> str:
        """Return the configured stream's output from an execute result."""
        stdout = result.get("stdout") or ""
        stderr = result.get("stderr") or ""
        if stream == "stdout":
            return stdout
        if stream == "stderr":
            return stderr
        return stdout + stderr

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(
        self,
        inputs: dict,
        context: ToolContext,
    ) -> Dict[str, Any]:
        """Unified execution entry point (single ToolProtocol contract).

        Routes internally:
        - ``inputs["operation"]`` → operation path: lookup the named
          operation, validate bound values against its typed input ports,
          build the command from ``args_map``, execute via ``_run``.
        - ``inputs["args"]`` → bare-args path: extract the command list,
          execute via ``_run`` (backward-compatible).

        Returns ``{success, stdout, stderr, returncode, command}``.
        """
        cmd_context = self._to_command_context(context)

        operation_name = inputs.get("operation")
        if operation_name:
            return self._execute_operation(operation_name, inputs, cmd_context)

        command_list = inputs.get("args")
        if isinstance(command_list, list):
            return self._run(command_list, cmd_context)

        raise ToolException(
            f"tool {self.name!r} requires either 'operation' or 'args' "
            f"in inputs, got keys: {list(inputs.keys())}"
        )

    def _execute_operation(
        self,
        operation_name: str,
        inputs: dict,
        cmd_context: CommandExecutionContext,
    ) -> Dict[str, Any]:
        """Execute via a named operation: lookup, validate, build command, run.

        Returns:
            dict: ``{success, stdout, stderr, returncode, command}``.
        Raises:
            ToolException: on unknown operation, missing required inputs,
                or execution failure.
        """
        # ── 1. Look up the operation ──────────────────────────────────
        op = None
        for candidate in self._descriptor.operations:
            if candidate.name == operation_name:
                op = candidate
                break

        if op is None:
            raise ToolException(
                f"unknown operation {operation_name!r} for tool {self.name!r}"
            )

        # ── 2. Validate inputs against the operation's typed ports ────
        if op.inputs:
            op_port_set = PortSet(list(op.inputs), list(op.outputs))
            validation_errors = op_port_set.validate_inputs(inputs)
            if validation_errors:
                raise ToolException("; ".join(validation_errors))

        # ── 3. Build command list from args_map ───────────────────────
        command = self._build_operation_command(op, inputs)

        # ── 3.5 Apply per-operation cwd / timeout overrides ─────────────
        if op.timeout is not None:
            if isinstance(op.timeout, (int, float)) and not isinstance(op.timeout, bool):
                cmd_context.timeout = op.timeout
            else:
                self._logger.warning(
                    "operation timeout must be a number, got %r; using default",
                    op.timeout,
                )
        if op.cwd:  # 空字符串视为「不覆盖」，避免 cwd="" 破坏 subprocess
            cmd_context.cwd = self._resolve_operation_cwd(op.cwd, inputs, cmd_context.cwd)

        # ── 4. Execute via the internal _run contract ─────────────────
        result = self._run(command, cmd_context)

        # ── 4.5 Surface script stdout JSON as structured outputs ──────
        # When the descriptor declares ``parse_stdout_json``, a successful
        # script's stdout is expected to be a JSON object.  Its keys are
        # merged into the result so downstream nodes can reference them
        # directly (``$nodes.<id>.outputs.passed`` etc.).  The executor's
        # control keys (success/returncode/stdout/stderr/command) win over
        # same-named script keys, and a non-object / unparsable stdout is
        # left untouched (no failure — the raw stdout string is still there).
        if self._descriptor.parse_stdout_json:
            self._merge_parsed_stdout_json(result)

        # ── 5. Surface input ports declared direction=output ──────────
        # Tools that produce files (e.g. ``--out <path>``) declare those
        # paths as inputs with ``direction=output``.  The bound value is
        # the user-supplied destination; copy it into the result dict so
        # downstream nodes can reference it as ``$nodes.<id>.outputs.<name>``
        # without the descriptor having to redeclare the port on the
        # ``outputs`` side.  Real tool output (stdout/stderr/returncode)
        # is preserved — output-direction inputs only ADD keys, never
        # overwrite existing ones.
        for in_port in op.inputs:
            if getattr(in_port, "direction", "input") == "output":
                if in_port.name in inputs:
                    result.setdefault(in_port.name, inputs[in_port.name])
        return result

    def _merge_parsed_stdout_json(self, result: Dict[str, Any]) -> None:
        """Merge a JSON-object stdout into *result* (mutates in place).

        Only when ``parse_stdout_json`` is declared: parses ``stdout`` as JSON
        and, when it is an object, adds every key via ``setdefault`` so the
        executor's control keys (``success``/``returncode``/``stdout``/
        ``stderr``/``command``) are never overwritten by a script key of the
        same name.  Unparsable or non-object stdout is silently ignored.
        """
        raw = result.get("stdout")
        if not isinstance(raw, str) or not raw.strip():
            return
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return
        if isinstance(parsed, dict):
            for key, value in parsed.items():
                result.setdefault(key, value)

    @staticmethod
    def _build_operation_command(op: Any, resolved_params: dict) -> list:
        """Build the command list from an operation's args_map.

        Each entry in ``op.args_map`` is either:
        - A literal string (passed through unchanged).
        - A ``{"param": <name>}`` dict: the bound value of ``<name>`` is
          looked up in *resolved_params* and stringified.
        - A ``{"flag": <name>, "value": <arg>}`` dict: ``<arg>`` is emitted
          only when ``resolved_params[<name>]`` is truthy.

        Returns:
            A flat list of strings ready for ``self._run(command, ctx)``.
        """
        command: list = []
        for entry in op.args_map:
            if isinstance(entry, str):
                command.append(entry)
            elif isinstance(entry, dict):
                if "param" in entry:
                    value = resolved_params.get(entry["param"], "")
                    command.append(str(value))
                elif "flag" in entry:
                    flag_value = resolved_params.get(entry["flag"], False)
                    if flag_value:
                        command.append(str(entry["value"]))
        return command

    def _resolve_operation_cwd(
        self, cwd_spec: str, inputs: dict, default_cwd: Optional[str]
    ) -> Optional[str]:
        if cwd_spec == "$workdir":
            return default_cwd
        if cwd_spec.startswith("$inputs."):
            key = cwd_spec[len("$inputs."):]
            value = inputs.get(key)
            if isinstance(value, str) and value:
                return value
            self._logger.warning(
                "operation cwd %r references missing/empty input %r; "
                "falling back to work dir",
                cwd_spec,
                key,
            )
            return default_cwd
        return cwd_spec

    @staticmethod
    def _to_command_context(context: ToolContext) -> CommandExecutionContext:
        """Convert a workflow ToolContext to a CommandExecutionContext."""
        return CommandExecutionContext(
            cwd=context.work_dir,
            task_id=context.task_id,
            env=dict(context.env) or None,
            process_holder={},
        )

    def _run(
        self,
        command: List[str],
        context: Optional[CommandExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Build the full command and delegate to CommandExecutor.

        For script-type tools the required interpreter env_dep is verified
        BEFORE any command is built — missing/unresolved environments raise
        ToolException immediately with no subprocess spawn.
        """
        self._ensure_script_env_available()
        full_command = self._build_command(command)
        ctx = context or CommandExecutionContext()
        return self._command_executor.execute(full_command, ctx)

    def _ensure_script_env_available(self) -> None:
        """Raise ToolException if a script tool's required env_dep is unresolved.

        The mapping ``_INTERPRETER_DEP_BY_TYPE`` defines which env_dep every
        script type needs (e.g. ``python_script`` → ``"python"``).  That dep
        MUST be present in the descriptor's ``env_deps`` and MUST have
        resolved to a non-empty binary path through the registry.

        ``shell_script`` resolves the platform shell instead of an env_dep;
        when the platform shell cannot be located, the same "not available"
        class of error is raised.
        """
        tool_type = _select_platform_type(self._descriptor.type)
        if tool_type not in ("python_script", "node_script", "shell_script"):
            return

        if tool_type == "shell_script":
            shell = _get_platform_shell()
            if not shell or not os.path.exists(shell):
                raise ToolException(
                    f"environment 'shell' not available for script tool "
                    f"{self.name!r}: no platform shell found"
                )
            return

        dep_name = self._INTERPRETER_DEP_BY_TYPE.get(tool_type)
        if not dep_name:
            raise ToolException(
                f"cannot determine required environment for script tool "
                f"{self.name!r} of type {tool_type!r}"
            )

        # The interpreter dep MUST be in the descriptor's env_deps AND
        # resolve via the registry (legacy helper fallback is NOT used
        # for the gate — the descriptor must declare what it needs).
        resolved = self._env_resolutions.get(dep_name, "")
        if not resolved:
            raise ToolException(
                f"environment {dep_name!r} not available — cannot execute "
                f"script tool {self.name!r}"
            )

    def _build_command(self, command: List[str]) -> List[str]:
        """Prefix *command* with the invocation for this tool's type.

        Callers that already pass the full invocation (the resolved tool
        path, or ``[java, "-jar", tool_path]`` — legacy handler habit) are
        not double-prefixed: the prefix is skipped when *command* already
        starts with it, mirroring ``BinaryTool.execute`` dedupe.
        """
        tool_type = _select_platform_type(self._descriptor.type)
        if tool_type == "binary":
            if command and command[0] == self.tool_path:
                return list(command)
            return [self.tool_path] + list(command)
        if tool_type == "shell_script":
            # Shell handling: wrap in platform shell (cmd.exe on Windows, /bin/sh elsewhere).
            shell = _get_platform_shell()
            return [shell, self.tool_path] + list(command)
        dep_name = self._INTERPRETER_DEP_BY_TYPE.get(tool_type)
        interpreter = self._interpreter_for(dep_name)
        if tool_type == "java_jar":
            invocation = [interpreter, "-jar", self.tool_path]
            if command and command[: len(invocation)] == invocation:
                return list(command)
            return invocation + list(command)
        # python_script / node_script
        return [interpreter, self.tool_path] + list(command)

    def get_java_path(self) -> str:
        """Return the resolved Java interpreter path (JavaTool compatibility).

        Legacy handlers build bundletool/jarsigner command lines manually
        via ``tool.get_java_path()``; a descriptor-based java_jar tool
        exposes the same surface so those callers keep working unchanged.
        """
        resolved = self._env_resolutions.get("java")
        if resolved:
            return resolved
        return get_java_bin()

    def _interpreter_for(self, dep_name: Optional[str]) -> str:
        """Return the interpreter binary for a script-type tool.

        Prefers the env_dep resolved through the registry, falling back to
        the legacy ``app.utils.env`` helper (which delegates to the registry).
        """
        if dep_name:
            resolved = self._env_resolutions.get(dep_name)
            if resolved:
                return resolved
            if dep_name == "java":
                return get_java_bin()
            if dep_name == "python":
                return get_python_bin()
            if dep_name == "node":
                return get_node_bin()
        raise ToolException(
            f"tool {self.name!r} requires environment {dep_name!r} "
            f"which could not be resolved"
        )
