"""T4 gate — engine execution of descriptor tool operations.

Covers:
  (a) Happy: 1-node workflow using an operation-based descriptor tool with
      a stubbed echo command executor returns the declared typed outputs.
  (b) Failure: missing required operation input → node error string.
  (c) Failure: unknown operation name → node error string.
  (d) Backward compat: descriptor WITHOUT operations + raw params.args
      executes exactly as before.
"""

from typing import Any, Dict, List, Optional

import pytest

from app.common.exceptions import ToolException
from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.tools.descriptor_tool import Operation
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.engine import ExecutionContext, WorkflowEngine


# ── Stubs ────────────────────────────────────────────────────────────────
class _StubRegistry:
    """Minimal tool registry reusing the engine test pattern."""

    def __init__(self, tools=None):
        self._tools = dict(tools or {})

    def get_tool(self, name):
        return self._tools.get(name)


class _StubDescriptorTool:
    """DescriptorTool stub carrying operations + a controllable executor.

    The execute method accepts ``(inputs, context)`` — the unified
    ``ToolProtocol`` contract.  Internally it routes: operation path
    (builds command from args_map) or bare-args path (extracts args),
    then delegates to the injected ``_execute_fn(command, context)``.
    """

    def __init__(self, name, tool_path, descriptor, execute_fn=None):
        self.name = name
        self.tool_path = tool_path
        self._execute_fn = execute_fn or (lambda cmd, ctx: {
            "success": True, "returncode": 0,
            "stdout": "", "stderr": "", "command": " ".join(cmd),
        })
        self._descriptor = descriptor
        self.is_valid = True

    @property
    def ports(self):
        return PortSet(self._descriptor.inputs, self._descriptor.outputs)

    def execute(self, inputs, context):
        """Unified dispatch: operation path or bare-args path."""
        # Operation path
        operation_name = inputs.get("operation")
        if operation_name and self._descriptor.operations:
            op = None
            for candidate in self._descriptor.operations:
                if candidate.name == operation_name:
                    op = candidate
                    break
            if op is None:
                raise ToolException(
                    f"unknown operation {operation_name!r}"
                )
            # Validate inputs against operation-level ports
            if op.inputs:
                op_port_set = PortSet(list(op.inputs), list(op.outputs))
                validation_errors = op_port_set.validate_inputs(inputs)
                if validation_errors:
                    raise ToolException("; ".join(validation_errors))
            # Build command from args_map
            command = self._build_args(op.args_map, inputs)
            return self._execute_fn(command, context)

        # Bare-args path
        command_list = inputs.get("args")
        if isinstance(command_list, list):
            return self._execute_fn(command_list, context)

        raise ToolException(
            f"requires 'operation' or 'args' in inputs, "
            f"got keys: {list(inputs.keys())}"
        )

    @staticmethod
    def _build_args(args_map, inputs):
        """Build command list from args_map (matches DescriptorTool)."""
        command = []
        for entry in args_map:
            if isinstance(entry, str):
                command.append(entry)
            elif isinstance(entry, dict):
                if "param" in entry:
                    command.append(str(inputs.get(entry["param"], "")))
                elif "flag" in entry:
                    if inputs.get(entry["flag"], False):
                        command.append(str(entry["value"]))
        return command


def _port(name, base="text", required=True, **kwargs):
    return Port(
        name=name,
        type=TypeAnnotation(BaseType(base)),
        required=required,
        **kwargs,
    )


class _FakeDescriptor:
    """Minimal ToolDescriptor stub — avoids dataclass scope issues."""

    def __init__(self, name="echo_tool", operations=None, inputs=None, outputs=None):
        self.name = name
        self.display_name = name
        self.type = "binary"
        self.path = "echo"
        self.env_deps = []
        self.validate = {}
        self.version = {}
        self.inputs = inputs or []
        self.outputs = outputs or []
        self.sensitive_arg_patterns = []
        self.operations = operations or []


def _descriptor(name="echo_tool", operations=None, inputs=None, outputs=None):
    """Build a minimal ToolDescriptor-like stub."""
    return _FakeDescriptor(
        name=name,
        operations=operations or [],
        inputs=inputs or [],
        outputs=outputs or [],
    )


def _node(node_id, tool="echo_tool", **overrides):
    data = {"id": node_id, "tool": tool}
    data.update(overrides)
    return WorkflowNode(**data)


def _definition(nodes):
    return WorkflowDefinition(name="wf", nodes=nodes)


def _engine(registry=None):
    return WorkflowEngine(registry=registry if registry is not None else _StubRegistry())


def _context(tmp_path):
    return ExecutionContext(work_dir=str(tmp_path))


# ── Fixture helpers ──────────────────────────────────────────────────────
@pytest.fixture
def echo_execute():
    """Return an execute stub that echoes the command + fixed stdout."""
    def _execute(command, context):
        return {
            "success": True,
            "returncode": 0,
            "stdout": "echoed: " + " ".join(command),
            "stderr": "",
            "command": " ".join(command),
        }
    return _execute


# ── Tests ────────────────────────────────────────────────────────────────
class TestOperationExecutionHappy:
    """Happy path: operation-based descriptor tool execution."""

    def test_single_operation_node_executes_and_returns_typed_outputs(
        self, tmp_path, echo_execute
    ):
        """
        Given a descriptor tool with a 'greet' operation that takes
        one TEXT input 'name' and emits one TEXT output 'greeting',
        When the engine executes a node targeting that operation with
        bound input 'name'='world',
        Then outputs contain the stdout from the echo stub.
        """
        op = Operation(
            name="greet",
            description="Echo a greeting",
            inputs=[_port("name", "text", required=True)],
            outputs=[_port("greeting", "text")],
            args_map=["echo", {"param": "name"}],
        )
        desc = _descriptor(name="echo_tool", operations=[op])
        tool = _StubDescriptorTool("echo_tool", "echo", desc, execute_fn=echo_execute)

        nodes = [
            _node("greet", "echo_tool",
                  params={"operation": "greet", "name": "world"}),
        ]
        registry = _StubRegistry({"echo_tool": tool})
        result = _engine(registry).execute(
            _definition(nodes), {}, _context(tmp_path)
        )

        assert result.success is True
        assert result.error is None
        assert "greet" in result.node_results
        nr = result.node_results["greet"]
        assert nr["error"] is None
        # The outputs should contain the echo result
        assert "echoed:" in nr["outputs"].get("stdout", "")

    def test_operation_args_map_with_flag_placeholder(self, tmp_path):
        """
        Given an operation with args_map containing a flag placeholder
        that is only emitted when the bound boolean input is true,
        When the engine executes with the flag=true,
        Then the command includes the flag value.
        """
        op = Operation(
            name="list",
            inputs=[
                _port("target", "text", required=True),
                _port("verbose", "boolean", required=False),
            ],
            outputs=[_port("listing", "text")],
            args_map=["ls", {"param": "target"}, {"flag": "verbose", "value": "-v"}],
        )
        desc = _descriptor(name="list_tool", operations=[op])

        captured_cmd = [None]

        def _capture_cmd(command, context):
            captured_cmd[0] = list(command)
            return {"success": True, "returncode": 0,
                    "stdout": "dir listing", "stderr": "", "command": " ".join(command)}
        tool = _StubDescriptorTool("list_tool", "ls", desc, execute_fn=_capture_cmd)

        nodes = [
            _node("list", "list_tool",
                  params={"operation": "list", "target": "/tmp", "verbose": True}),
        ]
        registry = _StubRegistry({"list_tool": tool})
        result = _engine(registry).execute(
            _definition(nodes), {}, _context(tmp_path)
        )

        assert result.success is True
        # The command should include "ls", "/tmp", "-v"
        assert captured_cmd[0] is not None
        assert "ls" in captured_cmd[0]
        assert "/tmp" in captured_cmd[0]
        assert "-v" in captured_cmd[0]

    def test_operation_args_map_flag_false_omits_value(self, tmp_path):
        """
        When the flag boolean is false, the flag value is NOT emitted.
        """
        op = Operation(
            name="list",
            inputs=[
                _port("target", "text", required=True),
                _port("recursive", "boolean", required=False),
            ],
            outputs=[_port("listing", "text")],
            args_map=["ls", {"param": "target"}, {"flag": "recursive", "value": "-R"}],
        )
        desc = _descriptor(name="list_tool", operations=[op])

        captured_cmd = [None]

        def _capture_cmd(command, context):
            captured_cmd[0] = list(command)
            return {"success": True, "returncode": 0,
                    "stdout": "dir listing", "stderr": "", "command": " ".join(command)}
        tool = _StubDescriptorTool("list_tool", "ls", desc, execute_fn=_capture_cmd)

        nodes = [
            _node("list", "list_tool",
                  params={"operation": "list", "target": "/tmp", "recursive": False}),
        ]
        registry = _StubRegistry({"list_tool": tool})
        result = _engine(registry).execute(
            _definition(nodes), {}, _context(tmp_path)
        )

        assert result.success is True
        assert "-R" not in captured_cmd[0]


class TestOperationExecutionErrors:
    """Error paths: missing required inputs, unknown operation."""

    def test_missing_required_operation_input_returns_node_error_string(self, tmp_path):
        """
        When a required operation input is absent from node params,
        the engine must return a node error string (not crash).
        """
        op = Operation(
            name="greet",
            inputs=[_port("name", "text", required=True)],
            outputs=[_port("greeting", "text")],
            args_map=["echo", {"param": "name"}],
        )
        desc = _descriptor(name="echo_tool", operations=[op])
        tool = _StubDescriptorTool("echo_tool", "echo", desc)

        # Deliberately omit the required 'name' input
        nodes = [
            _node("greet", "echo_tool",
                  params={"operation": "greet"}),  # NO 'name'
        ]
        registry = _StubRegistry({"echo_tool": tool})
        result = _engine(registry).execute(
            _definition(nodes), {}, _context(tmp_path)
        )

        assert result.success is False
        assert "greet" in result.node_results
        nr = result.node_results["greet"]
        assert nr["error"] is not None
        assert "name" in nr["error"]  # error must name the missing port

    def test_unknown_operation_name_returns_node_error_string(self, tmp_path):
        """
        When params['operation'] names an operation that does not exist
        on the descriptor, the engine must return a node error string.
        """
        op = Operation(
            name="greet",
            inputs=[_port("name", "text")],
            outputs=[],
            args_map=["echo", {"param": "name"}],
        )
        desc = _descriptor(name="echo_tool", operations=[op])
        tool = _StubDescriptorTool("echo_tool", "echo", desc)

        nodes = [
            _node("bad", "echo_tool",
                  params={"operation": "nonexistent_op", "name": "world"}),
        ]
        registry = _StubRegistry({"echo_tool": tool})
        result = _engine(registry).execute(
            _definition(nodes), {}, _context(tmp_path)
        )

        assert result.success is False
        assert "bad" in result.node_results
        nr = result.node_results["bad"]
        assert nr["error"] is not None
        assert "nonexistent_op" in nr["error"] or "operation" in nr["error"].lower()


class TestBackwardCompat:
    """Descriptor tools WITHOUT operations must keep the raw params.args path."""

    def test_descriptor_without_operations_raw_args_executes(self, tmp_path):
        """
        Given a descriptor tool with NO operations,
        When a node uses raw `params.args` as a command list,
        Then the engine executes via the existing _execute_command_tool path.
        """
        captured_cmd = [None]

        def _capture_cmd(command, context):
            captured_cmd[0] = list(command)
            return {"success": True, "returncode": 0,
                    "stdout": "done", "stderr": "", "command": " ".join(command)}

        # Descriptor with NO operations
        desc = _descriptor(name="raw_tool", operations=[])
        tool = _StubDescriptorTool("raw_tool", "raw", desc, execute_fn=_capture_cmd)

        nodes = [
            _node("raw", "raw_tool",
                  params={"args": ["--version"]}),
        ]
        registry = _StubRegistry({"raw_tool": tool})
        result = _engine(registry).execute(
            _definition(nodes), {}, _context(tmp_path)
        )

        assert result.success is True
        assert captured_cmd[0] == ["--version"]

    def test_descriptor_with_operations_but_no_operation_param_falls_back_to_raw(
        self, tmp_path
    ):
        """
        When a descriptor HAS operations but the node params lack an
        'operation' key, the engine must fall back to the raw args path.
        """
        captured_cmd = [None]

        def _capture_cmd(command, context):
            captured_cmd[0] = list(command)
            return {"success": True, "returncode": 0,
                    "stdout": "done", "stderr": "", "command": " ".join(command)}

        op = Operation(
            name="greet",
            inputs=[_port("name", "text")],
            outputs=[],
            args_map=["echo", {"param": "name"}],
        )
        desc = _descriptor(name="echo_tool", operations=[op])
        tool = _StubDescriptorTool("echo_tool", "echo", desc, execute_fn=_capture_cmd)

        # Using raw args, NOT operation
        nodes = [
            _node("echo", "echo_tool",
                  params={"args": ["--help"]}),
        ]
        registry = _StubRegistry({"echo_tool": tool})
        result = _engine(registry).execute(
            _definition(nodes), {}, _context(tmp_path)
        )

        assert result.success is True
        assert captured_cmd[0] == ["--help"]
