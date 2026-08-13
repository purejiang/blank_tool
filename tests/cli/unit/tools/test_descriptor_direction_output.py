"""End-to-end coverage for ``direction=output`` input ports.

Verifies the three layers that cooperate to surface an input port's bound
value as a node output:

1. ``descriptor_tool._port_from_dict`` reads ``direction`` from JSON.
2. ``DescriptorTool._execute_operation`` copies the bound value of every
   ``direction=output`` input port into the returned outputs dict (so
   downstream ``$nodes.<id>.outputs.<name>`` references resolve).
3. ``workflow_handler._operations_payload`` mirrors direction=output input
   ports into the ``outputs`` array (deduped by name) so the workflow
   editor renders them as declared outputs without the descriptor author
   redeclaring them on the outputs side.
"""

import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.protocol import Port, TypeAnnotation
from app.protocol.types import BaseType
from app.tools.descriptor_tool import (
    DescriptorTool,
    Operation,
    ToolDescriptor,
    _port_from_dict,
)


# ---------------------------------------------------------------------------
# Stubs (mirrors tests/cli/unit/tools/test_descriptor_tool.py)
# ---------------------------------------------------------------------------


class _StubEnvRegistry:
    def __init__(self, binary_by_dep=None):
        self._bins = dict(binary_by_dep or {})

    def resolve(self, name):
        return SimpleNamespace(binary_path=self._bins.get(name, ""))


def _descriptor_with_out_port() -> ToolDescriptor:
    """A binary descriptor whose single operation takes ``src`` (real input)
    and ``out_path`` (direction=output), with no declared op.outputs."""
    op = Operation(
        name="compile",
        inputs=[
            Port(name="src", type=TypeAnnotation(BaseType.FILE)),
            Port(name="out_path", type=TypeAnnotation(BaseType.FILE), direction="output"),
        ],
        outputs=[],
        args_map=["--out", {"param": "out_path"}, {"param": "src"}],
    )
    return ToolDescriptor(
        name="stub_compiler",
        display_name="Stub Compiler",
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
    return DescriptorTool(descriptor or _descriptor_with_out_port(), _StubEnvRegistry())


# ---------------------------------------------------------------------------
# _port_from_dict reads direction
# ---------------------------------------------------------------------------


def test_port_from_dict_reads_direction_output():
    port = _port_from_dict(
        {
            "name": "out_path",
            "type": {"base": "file", "subtype": None},
            "direction": "output",
        }
    )
    assert port.direction == "output"


def test_port_from_dict_defaults_direction_to_input_when_absent():
    port = _port_from_dict(
        {
            "name": "src",
            "type": {"base": "file", "subtype": None},
        }
    )
    assert port.direction == "input"


# ---------------------------------------------------------------------------
# _execute_operation surfaces direction=output input as output
# ---------------------------------------------------------------------------


def test_execute_operation_surfaces_output_direction_input_in_result():
    """The bound value of a direction=output input port must appear in the
    returned outputs dict so downstream nodes can reference it."""
    tool = _make_tool()

    # Stub _run to avoid a real subprocess — return the canonical shape.
    fake_result = {
        "success": True,
        "returncode": 0,
        "stdout": "compiled\n",
        "stderr": "",
        "command": ["python", "--out", "/tmp/bundle.js", "/tmp/src.js"],
    }
    with patch.object(tool, "_run", return_value=fake_result) as mock_run:
        result = tool.execute(
            inputs={
                "operation": "compile",
                "src": "/tmp/src.js",
                "out_path": "/tmp/bundle.js",
            },
            context=SimpleNamespace(
                work_dir="/tmp", task_id="t1", env={}, process_holder={}
            ),
        )

    # _run was called once with the args_map-built command.
    mock_run.assert_called_once()
    built_command = mock_run.call_args[0][0]
    assert "--out" in built_command
    assert "/tmp/bundle.js" in built_command

    # Tool's stdout-parsed fields are preserved.
    assert result["success"] is True
    assert result["returncode"] == 0
    assert "compiled" in result["stdout"]

    # The output-direction input port is surfaced as an output.
    assert result["out_path"] == "/tmp/bundle.js"


def test_execute_operation_does_not_overwrite_real_output_with_input_value():
    """If the tool already produced a real output value (e.g. parsed from
    stdout) under the same name as a direction=output input, the real
    value wins — output-direction inputs only ADD missing keys."""
    tool = _make_tool()

    # Pretend the tool already wrote `out_path` into its result dict.
    fake_result = {
        "success": True,
        "returncode": 0,
        "stdout": "",
        "stderr": "",
        "out_path": "/real/derived/path.js",  # real tool output
    }
    with patch.object(tool, "_run", return_value=fake_result):
        result = tool.execute(
            inputs={
                "operation": "compile",
                "src": "/tmp/src.js",
                "out_path": "/user/supplied/path.js",  # user-supplied input
            },
            context=SimpleNamespace(
                work_dir="/tmp", task_id="t1", env={}, process_holder={}
            ),
        )

    # The real output is preserved — setdefault semantics.
    assert result["out_path"] == "/real/derived/path.js"


def test_execute_operation_skips_missing_output_direction_input():
    """An optional direction=output input that wasn't bound is not surfaced
    (no KeyError, no spurious None in outputs)."""
    op = Operation(
        name="compile",
        inputs=[
            Port(name="src", type=TypeAnnotation(BaseType.FILE)),
            Port(
                name="out_path",
                type=TypeAnnotation(BaseType.FILE),
                required=False,
                direction="output",
            ),
        ],
        outputs=[],
        args_map=["--in", {"param": "src"}],
    )
    descriptor = ToolDescriptor(
        name="stub_compiler",
        display_name="Stub Compiler",
        type="binary",
        path=sys.executable,
        env_deps=[],
        validate={},
        version={},
        inputs=[],
        outputs=[],
        operations=[op],
    )
    tool = _make_tool(descriptor)

    fake_result = {"success": True, "returncode": 0, "stdout": "", "stderr": ""}
    with patch.object(tool, "_run", return_value=fake_result):
        result = tool.execute(
            inputs={"operation": "compile", "src": "/tmp/src.js"},
            context=SimpleNamespace(
                work_dir="/tmp", task_id="t1", env={}, process_holder={}
            ),
        )

    assert "out_path" not in result
    assert result["success"] is True


# ---------------------------------------------------------------------------
# workflow_handler._operations_payload mirrors direction=output inputs
# ---------------------------------------------------------------------------


def test_operations_payload_mirrors_output_direction_inputs_to_outputs():
    """``workflow.list_tools`` should expose direction=output input ports
    on the outputs side too, so the editor renders them as declared
    outputs without forcing the descriptor author to redeclare them."""
    from app.handlers.workflow_handler import _operations_payload

    tool = _make_tool()
    payload = _operations_payload(tool)

    assert len(payload) == 1
    op = payload[0]
    assert op["name"] == "compile"

    input_names = [p["name"] for p in op["inputs"]]
    output_names = [p["name"] for p in op["outputs"]]
    assert input_names == ["src", "out_path"]
    # out_path is mirrored from inputs (direction=output) into outputs.
    assert "out_path" in output_names


def test_operations_payload_dedupes_when_input_output_share_a_name():
    """If the descriptor already declares a same-named output port, the
    mirror must not duplicate it."""
    from app.handlers.workflow_handler import _operations_payload

    # Operation declares out_path on BOTH inputs (direction=output) and outputs.
    op = Operation(
        name="compile",
        inputs=[
            Port(name="out_path", type=TypeAnnotation(BaseType.FILE), direction="output"),
        ],
        outputs=[Port(name="out_path", type=TypeAnnotation(BaseType.FILE))],
        args_map=[],
    )
    descriptor = ToolDescriptor(
        name="stub_compiler",
        display_name="Stub Compiler",
        type="binary",
        path=sys.executable,
        env_deps=[],
        validate={},
        version={},
        inputs=[],
        outputs=[],
        operations=[op],
    )
    tool = _make_tool(descriptor)
    payload = _operations_payload(tool)

    output_names = [p["name"] for p in payload[0]["outputs"]]
    assert output_names.count("out_path") == 1, "mirror duplicated an existing output"
