"""Wave 2 tests: DescriptorTool — load, validate, execute, env_dep resolution,
per-platform paths, and process_holder cancellation threading.

The binary under test is the real ``sys.executable`` (a fast, always-present
stand-in for a third-party binary); env deps are stubbed with a tiny
in-memory registry so no real environments or binaries are probed.
"""

import json
import os
import sys
from types import SimpleNamespace

import pytest

from app.common.base_executor import CommandExecutionContext
from app.tools.builtin.base import ToolContext
from app.tools.descriptor_tool import (
    DescriptorTool,
    ToolDescriptor,
    _select_platform_path,
    _select_platform_type,
    load_descriptor,
)


class _StubEnvRegistry:
    """Minimal registry: resolve(name) -> {binary_path} ("" when missing)."""

    def __init__(self, binary_by_dep=None):
        self._bins = dict(binary_by_dep or {})

    def resolve(self, name):
        return SimpleNamespace(binary_path=self._bins.get(name, ""))


def _descriptor(**overrides) -> ToolDescriptor:
    """A binary-type descriptor pointing at sys.executable (always exists)."""
    data = {
        "name": "stub_tool",
        "display_name": "Stub Tool",
        "type": "binary",
        "path": sys.executable,
        "env_deps": [],
        "validate": {},
        "version": {},
        "inputs": [],
        "outputs": [],
    }
    data.update(overrides)
    return ToolDescriptor(**data)


def _make_tool(descriptor=None, env=None) -> DescriptorTool:
    return DescriptorTool(descriptor or _descriptor(), _StubEnvRegistry(env or {}))


# ---------------------------------------------------------------------------
# load_descriptor
# ---------------------------------------------------------------------------

def test_load_descriptor_from_valid_json(tmp_path):
    path = tmp_path / "tool.json"
    path.write_text(
        json.dumps(
            {
                "name": "demo",
                "display_name": "Demo",
                "type": "binary",
                "path": "bin/demo",
                "env_deps": ["java"],
                "inputs": [{"name": "arg", "type": "text"}],
                "outputs": [{"name": "out", "type": "text"}],
            }
        ),
        encoding="utf-8",
    )
    descriptor = load_descriptor(str(path))
    assert descriptor.name == "demo"
    assert descriptor.display_name == "Demo"
    assert descriptor.type == "binary"
    assert descriptor.path == "bin/demo"
    assert descriptor.env_deps == ["java"]
    assert descriptor.inputs[0].name == "arg"
    assert descriptor.outputs[0].name == "out"


def test_load_descriptor_missing_required_field_raises(tmp_path):
    path = tmp_path / "tool.json"
    path.write_text(
        json.dumps({"name": "demo", "display_name": "Demo", "type": "binary"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing required field: 'path'"):
        load_descriptor(str(path))


def test_load_descriptor_malformed_json_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_descriptor(str(path))


# ---------------------------------------------------------------------------
# Validation & versioning
# ---------------------------------------------------------------------------

def test_is_valid_true_with_mock_binary_and_version_extracted():
    descriptor = _descriptor(
        version={"cmd": ["--version"], "regex": r"Python (\d+\.\d+\.\d+)"}
    )
    tool = _make_tool(descriptor)
    assert tool.is_valid is True
    assert tool.tool_path == os.path.normpath(sys.executable)
    assert tool.version.startswith("3.")


def test_missing_env_dep_makes_tool_invalid():
    descriptor = _descriptor(env_deps=["nonexistent_env"])
    tool = _make_tool(descriptor, env={"nonexistent_env": ""})
    assert tool.is_valid is False
    assert tool.version == ""
    assert tool._env_resolutions == {"nonexistent_env": ""}


def test_validate_expect_in_stream_selects_configured_stream():
    spec = {
        "cmd": [
            "-c",
            "import sys; sys.stderr.write('ERRMARK'); sys.stdout.write('OUTMARK')",
        ],
        "expect_contains": "ERRMARK",
    }
    on_stderr = _make_tool(
        _descriptor(validate={**spec, "expect_in": "stderr"})
    )
    assert on_stderr.is_valid is True
    on_stdout = _make_tool(_descriptor(validate={**spec, "expect_in": "stdout"}))
    assert on_stdout.is_valid is False
    on_either = _make_tool(_descriptor(validate={**spec, "expect_in": "either"}))
    assert on_either.is_valid is True


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def test_execute_runs_command_and_returns_result_dict():
    tool = _make_tool()
    result = tool.execute(
        {"args": ["-c", "print(42)"]}, ToolContext(work_dir=os.getcwd())
    )
    assert result["success"] is True
    assert result["returncode"] == 0
    assert "42" in result["stdout"]


def test_command_executor_threads_process_holder_through_to_subprocess():
    """The holder wiring TaskManager cancellation relies on lives at the
    CommandExecutor/ProcessExecutor layer.

    ``DescriptorTool._to_command_context`` forwards the workflow context's
    ``process_holder`` and ``cancel_check`` when it has them (see
    ``test_to_command_context_forwards_holder_and_cancel_check``), so the
    engine's per-node holder reaches the subprocess; the executor-level
    threading is asserted directly here.
    """
    from app.common.base_executor import CommandExecutor

    holder: dict = {}
    ctx = CommandExecutionContext(process_holder=holder)
    executor = CommandExecutor()
    executor.execute([sys.executable, "-c", "import time; time.sleep(0.2)"], ctx)
    assert "process" in holder, (
        "process_holder must reach the subprocess so TaskManager can cancel"
    )
    assert hasattr(holder["process"], "pid")


def test_to_command_context_forwards_holder_and_cancel_check():
    """The workflow context's holder/cancel_check reach the command context.

    Without this the descriptor's ``ProcessExecutor`` would take the
    uncancellable ``communicate(timeout=600)`` path (the apktool bug).
    """
    from types import SimpleNamespace

    from app.tools.descriptor_tool import DescriptorTool

    holder: dict = {}

    def cancel_check():
        return True

    context = ToolContext(
        work_dir="/wd", task_id="t1", env={},
        process_holder=holder, cancel_check=cancel_check,
    )

    cmd_context = DescriptorTool._to_command_context(context)

    assert cmd_context.process_holder is holder
    assert cmd_context.cancel_check is cancel_check


def test_to_command_context_tolerates_a_context_without_holder():
    """Duck-typed contexts (no holder/cancel_check attributes) still work."""
    from types import SimpleNamespace

    from app.tools.descriptor_tool import DescriptorTool

    context = SimpleNamespace(work_dir="/wd", task_id="t1", env={})
    cmd_context = DescriptorTool._to_command_context(context)

    assert cmd_context.process_holder is None
    assert cmd_context.cancel_check is None


def test_java_jar_build_command_uses_interpreter_prefix():
    descriptor = _descriptor(
        type={"win": "java_jar", "mac": "binary", "linux": "binary"},
        env_deps=["java"],
    )
    tool = _make_tool(descriptor, env={"java": sys.executable})
    command = tool._build_command(["version"])
    assert command[0] == sys.executable  # java interpreter
    assert command[1] == "-jar"
    assert command[2] == tool.tool_path
    assert command[3:] == ["version"]


# ---------------------------------------------------------------------------
# Per-platform resolution
# ---------------------------------------------------------------------------

def test_per_platform_path_selects_current_platform(monkeypatch):
    monkeypatch.setattr("app.tools.descriptor_tool.platform.system", lambda: "Windows")
    assert _select_platform_path({"win": "w.exe", "mac": "m", "linux": "l"}) == "w.exe"
    monkeypatch.setattr("app.tools.descriptor_tool.platform.system", lambda: "Darwin")
    assert _select_platform_path({"win": "w.exe", "mac": "m", "linux": "l"}) == "m"
    monkeypatch.setattr("app.tools.descriptor_tool.platform.system", lambda: "Linux")
    assert _select_platform_path({"win": "w.exe", "mac": "m", "linux": "l"}) == "l"


def test_per_platform_type_selects_platform_value(monkeypatch):
    tool_type = {"win": "java_jar", "mac": "binary", "linux": "binary"}
    monkeypatch.setattr("app.tools.descriptor_tool.platform.system", lambda: "Windows")
    assert _select_platform_type(tool_type) == "java_jar"
    monkeypatch.setattr("app.tools.descriptor_tool.platform.system", lambda: "Darwin")
    assert _select_platform_type(tool_type) == "binary"


def test_tool_path_resolves_per_platform_dict_on_current_platform(monkeypatch):
    # Force the current-platform key to be present and absolute.
    monkeypatch.setattr(
        "app.tools.descriptor_tool.platform.system", lambda: "Windows"
    )
    descriptor = _descriptor(
        path={"win": sys.executable, "mac": "/opt/m", "linux": "/usr/bin/l"}
    )
    tool = _make_tool(descriptor)
    assert tool.tool_path == os.path.normpath(sys.executable)
