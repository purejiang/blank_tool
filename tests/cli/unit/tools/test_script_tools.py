"""T17: Script-based tools — import python_script/node_script/shell_script descriptors,
execute them via the operations model with env gating.
"""

import json
import os
import sys
from pathlib import Path

import pytest

from app.common.base_executor import CommandExecutionContext
from app.tools.builtin.base import ToolContext
from app.env.registry import EnvironmentRegistry
from app.tools.descriptor_tool import DescriptorTool, ToolDescriptor, load_descriptor, Operation
from app.common.exceptions import ToolException
from app.protocol import BaseType, Port, TypeAnnotation
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.engine import ExecutionContext, WorkflowEngine, WorkflowResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _port(name: str, base: str = "text", required: bool = True) -> Port:
    """Build a typed Port with the given base type name."""
    return Port(
        name=name,
        type=TypeAnnotation(BaseType(base)),
        required=required,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _real_env_registry() -> EnvironmentRegistry:
    """A real EnvironmentRegistry discovering bundled python/node/java envs."""
    reg = EnvironmentRegistry()
    reg.discover()
    return reg


def _make_python_script_descriptor(
    script_path: str, *, name: str = "test_py", env_deps=None, **overrides
) -> ToolDescriptor:
    """Build a python_script descriptor pointing at *script_path*."""
    if env_deps is None:
        env_deps = ["python"]
    data = {
        "name": name,
        "display_name": f"Test {name}",
        "type": "python_script",
        "path": script_path,
        "env_deps": env_deps,
        "validate": {},
        "version": {},
        "inputs": [],
        "outputs": [],
    }
    data.update(overrides)
    return ToolDescriptor(**data)


def _make_node_script_descriptor(
    script_path: str, *, name: str = "test_node", **overrides
) -> ToolDescriptor:
    """Build a node_script descriptor."""
    data = {
        "name": name,
        "display_name": f"Test {name}",
        "type": "node_script",
        "path": script_path,
        "env_deps": ["node"],
        "validate": {},
        "version": {},
        "inputs": [],
        "outputs": [],
    }
    data.update(overrides)
    return ToolDescriptor(**data)


def _make_shell_script_descriptor(
    script_path: str, *, name: str = "test_shell", **overrides
) -> ToolDescriptor:
    """Build a shell_script descriptor."""
    data = {
        "name": name,
        "display_name": f"Test {name}",
        "type": "shell_script",
        "path": script_path,
        "env_deps": [],
        "validate": {},
        "version": {},
        "inputs": [],
        "outputs": [],
    }
    data.update(overrides)
    return ToolDescriptor(**data)


# ---------------------------------------------------------------------------
# (a) python_script with real interpreter — execute via operations
# ---------------------------------------------------------------------------

def test_python_script_descriptor_constructs_with_real_env():
    """A python_script descriptor with env_deps=['python'] resolves and is_valid."""
    script = os.path.join(os.path.dirname(__file__), "__nonexistent__.py")
    desc = _make_python_script_descriptor(script)
    tool = DescriptorTool(desc, _real_env_registry())
    # Script file doesn't exist, but env resolves → tool_path is set
    assert tool.name == "test_py"
    assert "python" in tool.get_env_resolutions()
    assert tool.get_env_resolutions()["python"] != ""


def test_python_script_execute_real(tmp_path):
    """Execute a real python script via a python_script DescriptorTool.

    Writes a tiny script that JSON-dumps sys.argv, then asserts stdout
    contains the expected arguments.
    """
    script = tmp_path / "hello.py"
    script.write_text(
        "import json, sys\n"
        "print(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )

    desc = _make_python_script_descriptor(str(script))
    tool = DescriptorTool(desc, _real_env_registry())
    assert tool.is_valid is True

    result = tool.execute({"args": ["--flag", "value"]}, ToolContext(work_dir=os.getcwd()))
    assert result["success"] is True
    assert result["returncode"] == 0
    parsed = json.loads(result["stdout"].strip())
    assert parsed == ["--flag", "value"]


def test_python_script_execute_via_operations(tmp_path):
    """python_script descriptor with an operation that echoes input → output."""
    script = tmp_path / "greet.py"
    script.write_text(
        'import json, sys\n'
        'name = sys.argv[-1] if len(sys.argv) > 1 else "world"\n'
        'print(json.dumps({"greeting": f"hello {name}"}))\n',
        encoding="utf-8",
    )

    desc_data = {
        "name": "greeter",
        "display_name": "Greeter",
        "type": "python_script",
        "path": str(script),
        "env_deps": ["python"],
        "validate": {},
        "version": {},
        "inputs": [
            {"name": "name", "type": "text", "required": True},
        ],
        "outputs": [
            {"name": "stdout", "type": "text"},
            {"name": "stderr", "type": "text"},
            {"name": "returncode", "type": "number"},
            {"name": "success", "type": "boolean"},
        ],
        "operations": [
            {
                "name": "greet",
                "description": "Greet a person by name",
                "inputs": [
                    {"name": "name", "type": "text", "required": True},
                ],
                "outputs": [
                    {"name": "result", "type": "text"},
                ],
                "args_map": [
                    {"param": "name"},
                ],
            }
        ],
    }

    desc = ToolDescriptor(**desc_data)
    tool = DescriptorTool(desc, _real_env_registry())
    assert tool.is_valid is True

    result = tool.execute({"args": ["alice"]}, ToolContext(work_dir=os.getcwd()))
    assert result["success"] is True
    assert result["returncode"] == 0
    parsed = json.loads(result["stdout"].strip())
    assert parsed["greeting"] == "hello alice"


def test_python_script_command_starts_with_resolved_interpreter(tmp_path):
    """Verify the built command list uses the resolved python interpreter path."""
    script = tmp_path / "cmd_test.py"
    script.write_text("pass\n", encoding="utf-8")

    reg = _real_env_registry()
    desc = _make_python_script_descriptor(str(script))
    tool = DescriptorTool(desc, reg)

    resolved = reg.resolve("python")
    assert resolved.binary_path, "python env must resolve on this machine"

    command = tool._build_command(["--test"])
    assert command[0] == resolved.binary_path, (
        f"Expected interpreter {resolved.binary_path!r}, got {command[0]!r}"
    )
    assert command[1] == str(script)
    assert command[2:] == ["--test"]


# ---------------------------------------------------------------------------
# (b) Unresolvable env → execution blocked, no process spawned
# ---------------------------------------------------------------------------

def test_python_script_unresolved_env_blocks_execution(tmp_path):
    """A python_script with a fake env_dep raises ToolException at execution.

    env_deps=['python'] but the env registry has no 'python' descriptor →
    the required interpreter env is not available.
    """
    script = tmp_path / "never_run.py"
    script.write_text("print('should never run')\n", encoding="utf-8")

    # EnvironmentRegistry with NO descriptors loaded (empty)
    empty_reg = EnvironmentRegistry()

    desc = _make_python_script_descriptor(str(script), env_deps=["python"])
    tool = DescriptorTool(desc, empty_reg)

    # tool.is_valid should be False (env unresolved)
    assert tool.is_valid is False, "tool must be invalid when env_dep unresolves"

    # But the CRITICAL test: calling execute() MUST block
    with pytest.raises(ToolException) as exc_info:
        tool.execute({"args": ["--arg"]}, ToolContext(work_dir=os.getcwd()))

    message = str(exc_info.value)
    assert "python" in message.lower(), (
        f"Error must name the missing environment, got: {message}"
    )
    assert "available" in message.lower() or "resolved" in message.lower(), (
        f"Error must say 'not available', got: {message}"
    )


def test_fake_env_name_blocks_execution_no_spawn(tmp_path):
    """Descriptor with env_deps=['totally_fake_env'] — execution blocked.

    Uses a real registry (which won't have 'totally_fake_env') —
    the key assertion: execute() raises BEFORE any subprocess spawn.
    The error names the missing required env 'python' (because a
    python_script needs a resolved 'python' env_dep, which was NOT
    declared in env_deps — 'totally_fake_env' is irrelevant to the
    interpreter resolution).
    """
    script = tmp_path / "never_run.py"
    script.write_text(
        "import sys; sys.exit(42)\n",  # would produce exit 42 if ever run
        encoding="utf-8",
    )

    desc = _make_python_script_descriptor(
        str(script), env_deps=["totally_fake_env"]
    )
    tool = DescriptorTool(desc, _real_env_registry())
    assert tool.is_valid is False

    with pytest.raises(ToolException) as exc_info:
        tool.execute({"args": ["x"]}, ToolContext(work_dir=os.getcwd()))

    message = str(exc_info.value)
    assert "python" in message.lower(), (
        f"Error must name the missing required env, got: {message}"
    )
    assert "available" in message.lower() or "resolved" in message.lower(), (
        f"Error must say 'not available', got: {message}"
    )


# ---------------------------------------------------------------------------
# (c) node_script descriptor constructs with real registry
# ---------------------------------------------------------------------------

def test_node_script_descriptor_constructs_with_real_env(tmp_path):
    """node_script descriptor with env_deps=['node'] → is_valid when node exists."""
    script = tmp_path / "hello.js"
    script.write_text(
        'const args = JSON.stringify(process.argv.slice(2));\n'
        'console.log(args);\n',
        encoding="utf-8",
    )

    desc = _make_node_script_descriptor(str(script))
    tool = DescriptorTool(desc, _real_env_registry())
    assert tool.is_valid is True
    envs = tool.get_env_resolutions()
    assert "node" in envs
    assert envs["node"] != ""


def test_node_script_execute_real(tmp_path):
    """Execute a real node script via a node_script DescriptorTool."""
    script = tmp_path / "args.js"
    script.write_text(
        'process.stdout.write(JSON.stringify(process.argv.slice(2)));\n',
        encoding="utf-8",
    )

    desc = _make_node_script_descriptor(str(script))
    tool = DescriptorTool(desc, _real_env_registry())
    assert tool.is_valid is True

    result = tool.execute({"args": ["--flag", "value"]}, ToolContext(work_dir=os.getcwd()))
    assert result["success"] is True
    assert result["returncode"] == 0
    parsed = json.loads(result["stdout"].strip())
    assert parsed == ["--flag", "value"]


def test_node_script_command_starts_with_resolved_interpreter(tmp_path):
    """Verify the built command list uses the resolved node interpreter path."""
    script = tmp_path / "cmd_test.js"
    script.write_text("// nothing\n", encoding="utf-8")

    reg = _real_env_registry()
    desc = _make_node_script_descriptor(str(script))
    tool = DescriptorTool(desc, reg)

    resolved = reg.resolve("node")
    assert resolved.binary_path, "node env must resolve on this machine"

    command = tool._build_command(["--test"])
    assert command[0] == resolved.binary_path, (
        f"Expected node {resolved.binary_path!r}, got {command[0]!r}"
    )
    assert command[1] == str(script)
    assert command[2:] == ["--test"]


# ---------------------------------------------------------------------------
# (d) Engine e2e: workflow with script tool operation
# ---------------------------------------------------------------------------

def test_engine_e2e_python_script_workflow(tmp_path):
    """A 1-node workflow using a python_script tool's operation executes and returns typed outputs."""
    script = tmp_path / "adder.py"
    script.write_text(
        'import json, sys\n'
        'a = int(sys.argv[1])\n'
        'b = int(sys.argv[2])\n'
        'print(json.dumps({"sum": a + b}))\n',
        encoding="utf-8",
    )

    desc = ToolDescriptor(
        name="adder",
        display_name="Adder",
        type="python_script",
        path=str(script),
        env_deps=["python"],
        validate={},
        version={},
        inputs=[
            _port("a", "number", True),
            _port("b", "number", True),
        ],
        outputs=[
            _port("stdout", "text"),
            _port("stderr", "text"),
            _port("returncode", "number"),
            _port("success", "boolean"),
        ],
        operations=[
            Operation(
                name="add",
                description="Add two numbers",
                inputs=[_port("a", "number", True), _port("b", "number", True)],
                outputs=[_port("result", "text")],
                args_map=[{"param": "a"}, {"param": "b"}],
            )
        ],
    )

    tool = DescriptorTool(desc, _real_env_registry())
    assert tool.is_valid is True

    # Use the T5 _Registry-class pattern for the engine
    class _Registry:
        def get_tool(self, name):
            return tool if name == "adder" else None

    node = WorkflowNode(
        id="add_numbers",
        tool="adder",
        params={"operation": "add", "a": 3, "b": 4},
    )
    definition = WorkflowDefinition(
        name="test_adder",
        description="",
        version="1.0",
        nodes=[node],
        inputs=[],
        outputs=[],
    )

    engine = WorkflowEngine(registry=_Registry())
    ctx = ExecutionContext(work_dir=str(tmp_path))
    result = engine.execute(definition, {}, ctx)

    assert isinstance(result, WorkflowResult)
    assert result.success, f"Workflow failed: {result.error}"
    assert "stdout" in result.outputs
    parsed = json.loads(result.outputs["stdout"].strip())
    assert parsed["sum"] == 7


# ---------------------------------------------------------------------------
# shell_script descriptor construction
# ---------------------------------------------------------------------------

def test_shell_script_descriptor_constructs(tmp_path):
    """A shell_script descriptor constructs correctly.

    On Windows: expects cmd.exe as interpreter.
    """
    import platform

    script = tmp_path / "test.bat"
    script.write_text("@echo off\r\necho hello\r\n", encoding="utf-8")

    desc = _make_shell_script_descriptor(str(script))
    tool = DescriptorTool(desc, _real_env_registry())
    assert tool.name == "test_shell"
    # shell_script on Windows resolves to cmd.exe
    if platform.system() == "Windows":
        command = tool._build_command(["/c"])
        interpreter = os.path.basename(command[0])
        assert "cmd" in interpreter.lower(), (
            f"shell_script on Windows must wrap in cmd.exe, got {command[0]!r}"
        )


# ---------------------------------------------------------------------------
# descriptor load_descriptor with source_dir path resolution
# ---------------------------------------------------------------------------

def test_load_descriptor_relative_script_path_resolves_from_source_dir(tmp_path):
    """When loading a descriptor from a directory, relative script paths
    resolve against the descriptor's source directory.
    """
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    script = scripts_dir / "tool.py"
    script.write_text("print('ok')\n", encoding="utf-8")

    desc_file = tmp_path / "adder.json"
    desc_file.write_text(
        json.dumps({
            "name": "adder",
            "display_name": "Adder",
            "type": "python_script",
            "path": "scripts/tool.py",
            "env_deps": ["python"],
            "validate": {},
            "version": {},
            "inputs": [],
            "outputs": [],
        }),
        encoding="utf-8",
    )

    # load_descriptor stores source_dir
    descriptor = load_descriptor(str(desc_file))
    assert descriptor.path == "scripts/tool.py"

    # Construct with source_dir from the descriptor file
    tool = DescriptorTool(
        descriptor, _real_env_registry(), source_dir=str(tmp_path)
    )
    assert tool.is_valid is True
    # tool_path must resolve to the absolute path
    assert os.path.isabs(tool.tool_path)
    assert tool.tool_path.endswith("tool.py")
