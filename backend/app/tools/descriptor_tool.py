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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.common.base_executor import CommandExecutor, CommandExecutionContext
from app.common.exceptions import ToolException
from app.env.registry import EnvironmentRegistry
from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.utils.env import get_java_bin, get_node_bin, get_python_bin, get_runtime_dir
from app.utils.logger import Logger

# platform.system() -> key in a per-platform tool path dict.
_PLATFORM_KEY: Dict[str, str] = {"Windows": "win", "Darwin": "mac", "Linux": "linux"}


@dataclass
class ToolDescriptor:
    """Data declaration of an external third-party tool (descriptor D1).

    ``path`` is an absolute path, a relative path (anchored at the runtime
    directory), or a per-platform dict ``{"win": ..., "mac": ...,
    "linux": ...}``.  ``validate`` carries ``{"cmd", "expect_contains",
    "expect_in", "expect_returncode"}``; ``version`` carries ``{"cmd",
    "regex", "from_stream"}``.  ``sensitive_arg_patterns`` is a
    log-redaction extension point (CommandExecutor applies its own).
    """

    name: str
    display_name: str
    type: str  # binary | java_jar | python_script | node_script | shell_script
    path: Union[str, Dict[str, str]]
    env_deps: List[str]
    validate: Dict[str, Any]
    version: Dict[str, Any]
    inputs: List[Port]
    outputs: List[Port]
    sensitive_arg_patterns: List[str] = field(default_factory=list)

    _VALID_TYPES = frozenset(
        {"binary", "java_jar", "python_script", "node_script", "shell_script"}
    )

    def __post_init__(self) -> None:
        """Validate the descriptor's core fields."""
        if self.type not in self._VALID_TYPES:
            raise ValueError(
                f"invalid tool type {self.type!r}; must be one of "
                f"{sorted(self._VALID_TYPES)}"
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

    def __init__(self, descriptor: ToolDescriptor, env_registry: EnvironmentRegistry):
        """Resolve env deps, locate the binary, and validate the tool."""
        self._descriptor = descriptor
        self._env_registry = env_registry
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

        Absolute paths are used as-is; relative paths anchor at the runtime
        directory (or stay backend-relative when none is configured).
        """
        path = _select_platform_path(self._descriptor.path)
        if os.path.isabs(path):
            return os.path.normpath(path)
        runtime_dir = get_runtime_dir()
        if runtime_dir:
            return os.path.normpath(os.path.join(runtime_dir, path))
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
        command: List[str],
        context: Optional[CommandExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Execute the tool with *command* appended after the invocation prefix.

        ``context.process_holder`` is threaded through untouched so an
        external coordinator (e.g. TaskManager) can cancel long-running
        descriptor tools.  Returns ``{success, stdout, stderr, returncode,
        command}``.
        """
        return self._run(command, context)

    def _run(
        self,
        command: List[str],
        context: Optional[CommandExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Build the full command and delegate to CommandExecutor.

        The *context* is forwarded as-is (never rebuilt), so its
        ``process_holder`` reaches the subprocess and cancellation works.
        """
        full_command = self._build_command(command)
        ctx = context or CommandExecutionContext()
        return self._command_executor.execute(full_command, ctx)

    def _build_command(self, command: List[str]) -> List[str]:
        """Prefix *command* with the invocation for this tool's type."""
        tool_type = self._descriptor.type
        if tool_type == "binary":
            return [self.tool_path] if not command else [self.tool_path] + list(command)
        if tool_type == "shell_script":
            # Shell handling (e.g. .sh on Windows) is governed by the context.
            return [self.tool_path] + list(command)
        dep_name = self._INTERPRETER_DEP_BY_TYPE.get(tool_type)
        interpreter = self._interpreter_for(dep_name)
        if tool_type == "java_jar":
            return [interpreter, "-jar", self.tool_path] + list(command)
        # python_script / node_script
        return [interpreter, self.tool_path] + list(command)

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
