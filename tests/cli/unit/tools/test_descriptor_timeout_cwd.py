"""Coverage for per-operation ``timeout`` / ``cwd`` overrides.

Verifies the three layers that cooperate to let a descriptor declare a
per-operation execution timeout and working directory:

1. ``_operations_from`` parses ``timeout`` / ``cwd`` from the JSON
   operation dict (and defaults both to None when absent).
2. ``DescriptorTool._execute_operation`` applies the overrides onto the
   ``CommandExecutionContext`` before invoking ``_run``.
3. ``_resolve_operation_cwd`` resolves static / ``$workdir`` /
   ``$inputs.<key>`` cwd specs, warning and falling back to the work dir
   when an ``$inputs.<key>`` reference is missing/empty.
"""

import sys
from types import SimpleNamespace
from unittest.mock import patch

from app.protocol import Port, TypeAnnotation
from app.protocol.types import BaseType
from app.tools.descriptor_tool import (
    DescriptorTool,
    Operation,
    ToolDescriptor,
    _operations_from,
)


# ---------------------------------------------------------------------------
# Stubs (mirrors tests/cli/unit/tools/test_descriptor_direction_output.py)
# ---------------------------------------------------------------------------


class _StubEnvRegistry:
    def __init__(self, binary_by_dep=None):
        self._bins = dict(binary_by_dep or {})

    def resolve(self, name):
        return SimpleNamespace(binary_path=self._bins.get(name, ""))


def _descriptor_with_timeout_cwd_op() -> ToolDescriptor:
    """A binary descriptor whose single operation declares ``timeout=5``
    and ``cwd="$inputs.repo_dir"``."""
    op = Operation(
        name="fix",
        inputs=[
            Port(
                name="repo_dir",
                type=TypeAnnotation(BaseType.DIRECTORY),
                required=False,
            ),
        ],
        outputs=[],
        args_map=["echo", "fix"],
        timeout=5,
        cwd="$inputs.repo_dir",
    )
    return ToolDescriptor(
        name="stub_fixer",
        display_name="Stub Fixer",
        type="binary",
        path=sys.executable,
        env_deps=[],
        validate={},
        version={},
        inputs=[],
        outputs=[],
        operations=[op],
    )


def _make_tool(descriptor=None) -> DescriptorTool:
    return DescriptorTool(
        descriptor or _descriptor_with_timeout_cwd_op(), _StubEnvRegistry()
    )


# ---------------------------------------------------------------------------
# _operations_from parses timeout / cwd
# ---------------------------------------------------------------------------


def test_operations_from_parses_timeout_cwd():
    operations = _operations_from(
        [
            {
                "name": "fix",
                "args_map": [],
                "timeout": 1800,
                "cwd": "$inputs.repo_dir",
            }
        ],
        "fake.json",
        "stub",
    )
    assert len(operations) == 1
    assert operations[0].timeout == 1800
    assert operations[0].cwd == "$inputs.repo_dir"


def test_operations_from_defaults_when_absent():
    operations = _operations_from(
        [{"name": "fix", "args_map": []}],
        "fake.json",
        "stub",
    )
    assert len(operations) == 1
    assert operations[0].timeout is None
    assert operations[0].cwd is None


# ---------------------------------------------------------------------------
# _execute_operation applies timeout / cwd overrides
# ---------------------------------------------------------------------------


def test_execute_operation_applies_timeout_cwd():
    """``op.timeout=5`` / ``op.cwd="$inputs.repo_dir"`` must be applied to
    the ``CommandExecutionContext`` handed to ``_run``."""
    tool = _make_tool()

    captured = {}

    def fake_run(command, cmd_context):
        captured["command"] = command
        captured["cmd_context"] = cmd_context
        return {
            "success": True,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        }

    with patch.object(tool, "_run", side_effect=fake_run) as mock_run:
        result = tool.execute(
            inputs={
                "operation": "fix",
                "repo_dir": "/tmp/repo",
            },
            context=SimpleNamespace(
                work_dir="/wd", task_id="t1", env={}, process_holder={}
            ),
        )

    mock_run.assert_called_once()
    assert captured["cmd_context"].timeout == 5
    assert captured["cmd_context"].cwd == "/tmp/repo"
    assert result["success"] is True


# ---------------------------------------------------------------------------
# _resolve_operation_cwd
# ---------------------------------------------------------------------------


def test_resolve_cwd_missing_input_falls_back(caplog):
    """An ``$inputs.<key>`` reference with no bound value warns and falls
    back to the default cwd instead of raising."""
    tool = _make_tool()
    with caplog.at_level("WARNING", logger="stub_fixer"):
        resolved = tool._resolve_operation_cwd("$inputs.repo_dir", {}, "/wd")
    assert resolved == "/wd"
    assert "references missing/empty input" in caplog.text


def test_resolve_cwd_static_and_workdir():
    tool = _make_tool()
    assert tool._resolve_operation_cwd("/abs/path", {}, "/wd") == "/abs/path"
    assert tool._resolve_operation_cwd("$workdir", {}, "/wd") == "/wd"
