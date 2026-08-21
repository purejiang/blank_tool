"""T5 gate — migrate APK-chain tools/workflows to typed operations.

Tests:
  (a) Each of the 5 migrated workflows loads + operation nodes resolve
      their operations against the loaded descriptors.
  (b) decompile workflow executes end-to-end with a stubbed command executor
      and asserts the stubbed executor receives the same effective argv as
      the old raw path produced.
  (c) A workflow node referencing a non-existent operation produces an error
      naming the operation.
"""

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.tools.descriptor_tool import DescriptorTool, ToolDescriptor, load_descriptor, Operation
from app.tools.tool_manager import ToolRegistry
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.engine import ExecutionContext, WorkflowEngine


# ── Paths ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
EXAMPLES_TOOLS_DIR = ROOT / "examples" / "tools" / "android"
EXAMPLES_WF_DIR = ROOT / "examples" / "workflows" / "android"

MIGRATED_WORKFLOWS = [
    "decompile",
    "recompile",
    "sign",
    "download-install",
    "aab-install",
]


# ── Fixtures ──────────────────────────────────────────────────────────────
@pytest.fixture
def android_tools_dir():
    """Path to examples/tools/android."""
    assert EXAMPLES_TOOLS_DIR.is_dir(), f"examples tools dir not found: {EXAMPLES_TOOLS_DIR}"
    return EXAMPLES_TOOLS_DIR


@pytest.fixture
def registry_with_android_tools(android_tools_dir, tmp_path):
    """ToolRegistry injected with overlay pointing at examples/tools/android.

    Descriptors are NOT bundled — tests inject the dir via ToolRegistry's
    registry_overlay_dir (T14 injection seam).  Each tool is loaded via
    load_descriptor + DescriptorTool construction with a stub env registry.
    """
    # Copy all tool descriptors from examples to an overlay layout
    registry_root = tmp_path / "registry"
    overlay_tools = registry_root / "tools"
    overlay_tools.mkdir(parents=True)
    for src in sorted(android_tools_dir.glob("*.json")):
        shutil.copy2(str(src), str(overlay_tools / src.name))

    registry = ToolRegistry(registry_overlay_dir=str(registry_root))
    registry.discover()
    return registry


class StubEnvRegistry:
    """Minimal env registry for stubbing java/python resolution.

    Returns fake binary paths so DescriptorTool construction succeeds
    even without real binaries present.
    """

    def __init__(self, binary_by_dep=None):
        self._bins = dict(binary_by_dep or {})

    def resolve(self, name):
        from types import SimpleNamespace
        return SimpleNamespace(binary_path=self._bins.get(name, os.path.join("fake", name)))


def _load_descriptor_tool(json_path: str, env_registry=None) -> "DescriptorTool":
    """Load a descriptor from JSON and construct a DescriptorTool.

    Uses a stub env registry so construction succeeds without real binaries.
    """
    if env_registry is None:
        env_registry = StubEnvRegistry({"java": "fake-java", "python": "fake-python", "node": "fake-node"})
    descriptor = load_descriptor(json_path)
    return DescriptorTool(descriptor, env_registry)


class StubDescriptorToolForOp:
    """DescriptorTool-like stub carrying operations + controllable executor.

    Mirrors the test_engine_operations.py pattern: injectable execute_fn
    captures the command for assertion, and _descriptor exposes operations.
    Implements the unified ``execute(inputs, context)`` ToolProtocol contract.
    """

    def __init__(self, descriptor: ToolDescriptor, execute_fn=None):
        self.name = descriptor.name
        self.tool_path = "fake-path"
        self._descriptor = descriptor
        self._execute_fn = execute_fn or (lambda cmd, ctx: {
            "success": True, "returncode": 0,
            "stdout": "", "stderr": "", "command": " ".join(cmd),
        })
        self.is_valid = True

    @property
    def ports(self):
        return PortSet(self._descriptor.inputs, self._descriptor.outputs)

    def execute(self, inputs, context):
        """Unified dispatch: operation path or bare-args path."""
        from app.common.base_executor import CommandExecutionContext
        cmd_context = CommandExecutionContext(
            cwd=getattr(context, "work_dir", getattr(context, "cwd", "")),
            task_id=getattr(context, "task_id", ""),
            env=getattr(context, "env", None),
            process_holder={},
        )

        operation_name = inputs.get("operation")
        if operation_name and self._descriptor.operations:
            op = None
            for candidate in self._descriptor.operations:
                if candidate.name == operation_name:
                    op = candidate
                    break
            if op is None:
                from app.common.exceptions import ToolException
                raise ToolException(
                    f"unknown operation {operation_name!r}"
                )
            command = []
            for entry in op.args_map:
                if isinstance(entry, str):
                    command.append(entry)
                elif isinstance(entry, dict):
                    if "param" in entry:
                        command.append(str(inputs.get(entry["param"], "")))
                    elif "flag" in entry:
                        if inputs.get(entry["flag"], False):
                            command.append(str(entry["value"]))
            return self._execute_fn(command, cmd_context)

        command_list = inputs.get("args")
        if isinstance(command_list, list):
            return self._execute_fn(command_list, cmd_context)

        from app.common.exceptions import ToolException
        raise ToolException(
            f"tool {self.name!r} requires either 'operation' or 'args' "
            f"in inputs, got keys: {list(inputs.keys())}"
        )


def _make_engine_with_tools(descriptor_dir: str, tool_names: list):
    """Build a WorkflowEngine with stubbed descriptor tools loaded from files.

    Each tool in *tool_names* is loaded from ``<descriptor_dir>/<name>.json``
    and wrapped in a StubDescriptorToolForOp with a controllable execute_fn.
    The returned tuple is (engine, execute_fns_by_tool_name) so tests can
    capture / assert on the commands the engine built.
    """
    tools: Dict[str, Any] = {}
    execute_fns: Dict[str, Any] = {}
    env_reg = StubEnvRegistry({"java": "fake-java", "python": "fake-python", "node": "fake-node"})

    for name in tool_names:
        desc = load_descriptor(str(Path(descriptor_dir) / f"{name}.json"))
        captured_cmd: List[List[str]] = []

        def _make_execute(captured):
            def _exec(cmd, ctx):
                captured.append(list(cmd))
                return {"success": True, "returncode": 0,
                        "stdout": "ok", "stderr": "", "command": " ".join(cmd)}
            return _exec

        exe_fn = _make_execute(captured_cmd)
        tools[name] = StubDescriptorToolForOp(desc, execute_fn=exe_fn)
        execute_fns[name] = (captured_cmd, exe_fn)

    class _Registry:
        def get_tool(self, name):
            return tools.get(name)
    return WorkflowEngine(registry=_Registry()), execute_fns


def _load_wf(name: str) -> WorkflowDefinition:
    path = EXAMPLES_WF_DIR / f"{name}.json"
    return WorkflowDefinition.from_json_file(str(path))


# ═══════════════════════════════════════════════════════════════════════════
# (a) Each migrated workflow loads + operation nodes resolve their operations
# ═══════════════════════════════════════════════════════════════════════════

class TestWorkflowLoadsAndResolvesOperations:
    """Each migrated workflow must have its operation nodes resolve against
    the loaded descriptors.  The engine's _get_descriptor + operation lookup
    are exercised for every node carrying an 'operation' param."""

    @pytest.mark.parametrize("wf_name", MIGRATED_WORKFLOWS)
    def test_workflow_loads_with_valid_definition(self, wf_name):
        """Given a migrated workflow JSON file,
        it must load as a valid WorkflowDefinition without errors."""
        definition = _load_wf(wf_name)
        assert definition.name == wf_name
        assert len(definition.nodes) > 0

    @pytest.mark.parametrize("wf_name", MIGRATED_WORKFLOWS)
    def test_operation_nodes_reference_known_operations(self, wf_name):
        """Given a migrated workflow,
        every node with an 'operation' param must reference an operation
        that exists on the tool's descriptor."""
        definition = _load_wf(wf_name)
        engine, _ = _make_engine_with_tools(str(EXAMPLES_TOOLS_DIR),
                                            self._tools_for(wf_name))

        for node in definition.nodes:
            if "operation" not in node.params:
                continue  # builtin nodes (net.download) don't use operations
            op_name = node.params["operation"]
            tool = engine._lookup_tool(node.tool)
            assert tool is not None, f"tool {node.tool!r} not found for workflow {wf_name}"
            descriptor = tool._descriptor
            assert descriptor is not None, f"no descriptor for {node.tool!r} in {wf_name}"
            ops = descriptor.operations
            op_found = any(op.name == op_name for op in ops)
            assert op_found, (
                f"operation {op_name!r} not found in tool {node.tool!r} "
                f"(workflow {wf_name!r}, node {node.id!r}). "
                f"Available: {[o.name for o in ops]}"
            )

    @pytest.mark.parametrize("wf_name", MIGRATED_WORKFLOWS)
    def test_workflow_inputs_outputs_contract_unchanged(self, wf_name):
        """The workflow-level inputs/outputs declarations must stay
        byte-identical in names, types, and required-ness.

        We validate against a hard-coded reference derived from the
        original pre-migration definitions.
        """
        definition = _load_wf(wf_name)
        ref = _REFERENCE_CONTRACTS[wf_name]

        # Inputs
        actual_inputs = {(p.name, p.type.base.value, p.type.subtype, p.required)
                         for p in definition.inputs}
        assert actual_inputs == ref["inputs"], (
            f"inputs contract changed for {wf_name!r}")

        # Outputs
        actual_outputs = {(p.name, p.type.base.value, p.type.subtype, p.required)
                          for p in definition.outputs}
        assert actual_outputs == ref["outputs"], (
            f"outputs contract changed for {wf_name!r}")

    # -- tool name map per workflow --
    @staticmethod
    def _tools_for(wf_name: str) -> list:
        mapping = {
            "decompile": ["apktool"],
            "recompile": ["apktool"],
            "sign": ["zipalign", "apksigner"],
            "download-install": ["adb"],
            "aab-install": ["bundletool"],
        }
        return mapping.get(wf_name, [])


# ── Reference contract snapshot (pre-migration inputs/outputs) ────────────
_REFERENCE_CONTRACTS = {
    "decompile": {
        "inputs": {
            ("apk_path", "file", "apk", True),
            ("output_dir", "directory", None, True),
        },
        "outputs": {
            ("output_dir", "directory", None, True),
        },
    },
    "recompile": {
        "inputs": {
            ("source_dir", "directory", None, True),
            ("output_apk", "file", "apk", True),
        },
        "outputs": {
            ("output_apk", "file", "apk", True),
        },
    },
    "sign": {
        "inputs": {
            ("apk_path", "file", "apk", True),
            ("keystore", "json", None, True),
        },
        "outputs": {
            ("signed_apk", "file", "apk", True),
        },
    },
    "download-install": {
        "inputs": {
            ("url", "text", None, True),
            ("device_id", "text", None, True),
        },
        "outputs": {
            ("path", "file", None, True),
        },
    },
    "aab-install": {
        "inputs": {
            ("aab_path", "file", "aab", True),
            ("device_id", "text", None, True),
            ("keystore", "json", None, False),
        },
        "outputs": {
            ("apks_path", "file", "apks", True),
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# (b) decompile E2E with stubbed executor — same argv as old raw path
# ═══════════════════════════════════════════════════════════════════════════

class TestDecompileEndToEnd:
    """End-to-end execution of the migrated decompile workflow with a
    stubbed command executor."""

    def test_decompile_e2e_success(self, tmp_path):
        """
        Given the migrated decompile workflow and a stub apktool,
        When the engine executes with apk_path='test.apk', output_dir='/out',
        Then the stubbed executor receives the correct command and
        the workflow completes successfully.
        """
        definition = _load_wf("decompile")

        captured_cmd: List[List[str]] = []

        def _capture(cmd, ctx):
            captured_cmd.append(list(cmd))
            return {"success": True, "returncode": 0,
                    "stdout": "decompiled", "stderr": "", "command": " ".join(cmd)}

        desc = load_descriptor(str(EXAMPLES_TOOLS_DIR / "apktool.json"))
        tool = StubDescriptorToolForOp(desc, execute_fn=_capture)

        class _Reg:
            def get_tool(self, name):
                return tool if name == "apktool" else None

        engine = WorkflowEngine(registry=_Reg())
        ctx = ExecutionContext(work_dir=str(tmp_path))

        result = engine.execute(definition, {
            "apk_path": "test.apk",
            "output_dir": "/out",
        }, ctx)

        assert result.success is True
        assert result.error is None
        assert len(captured_cmd) == 1

        cmd = captured_cmd[0]
        # The old raw-args path produced:
        #   apktool d test.apk --force -o /out
        # The migrated operation must produce the same effective argv.
        # apktool decode uses short form 'd' (matching apktool d <apk> -o <out>).
        assert "d" in cmd, f"expected 'd' in command, got {cmd}"
        assert "test.apk" in cmd, f"expected 'test.apk' in command, got {cmd}"
        assert "/out" in cmd, f"expected '/out' in command, got {cmd}"
        assert "-o" in cmd, f"expected '-o' in command, got {cmd}"
        assert "--force" in cmd, f"expected '--force' in command, got {cmd}"

        # Verify the output is recorded in node_results
        assert "decompile" in result.node_results
        nr = result.node_results["decompile"]
        assert nr["error"] is None

    def test_decompile_e2e_passes_output_dir_through(self, tmp_path):
        """
        output_dir is a REQUIRED input on the current decompile.json; the
        engine must resolve the bound value and the operation command must
        carry it through.  We pass output_dir='auto_out' and assert it
        appears verbatim in the captured argv.
        """
        definition = _load_wf("decompile")

        captured_cmd: List[List[str]] = []

        def _capture(cmd, ctx):
            captured_cmd.append(list(cmd))
            return {"success": True, "returncode": 0,
                    "stdout": "ok", "stderr": "", "command": " ".join(cmd)}

        desc = load_descriptor(str(EXAMPLES_TOOLS_DIR / "apktool.json"))
        tool = StubDescriptorToolForOp(desc, execute_fn=_capture)

        class _Reg:
            def get_tool(self, name):
                return tool if name == "apktool" else None

        engine = WorkflowEngine(registry=_Reg())
        ctx = ExecutionContext(work_dir=str(tmp_path))

        result = engine.execute(definition, {
            "apk_path": "app.apk",
            "output_dir": "auto_out",
        }, ctx)

        assert result.success is True
        assert len(captured_cmd) == 1
        assert "d" in captured_cmd[0]
        assert "app.apk" in captured_cmd[0]
        assert "auto_out" in captured_cmd[0]


# ═══════════════════════════════════════════════════════════════════════════
# (c) Bad operation reference produces error naming the operation
# ═══════════════════════════════════════════════════════════════════════════

class TestBadOperationReference:
    """A workflow node referencing a non-existent operation must produce
    a validation or execution error naming the operation."""

    def test_nonexistent_operation_produces_error_naming_it(self, tmp_path):
        """
        Given a descriptor tool with known operations,
        When the engine executes a node targeting an operation that does
        NOT exist on the tool,
        Then the engine returns a failure with an error message that
        includes the name of the bad operation.
        """
        desc = load_descriptor(str(EXAMPLES_TOOLS_DIR / "apktool.json"))
        tool = StubDescriptorToolForOp(desc)

        nodes = [
            WorkflowNode(
                id="bad",
                tool="apktool",
                params={
                    "operation": "nonexistent_decode",
                    "apk_path": "test.apk",
                    "output_dir": "/out",
                },
                next=None,
            ),
        ]
        definition = WorkflowDefinition(name="bad-wf", nodes=nodes)

        class _Reg:
            def get_tool(self, name):
                return tool if name == "apktool" else None

        engine = WorkflowEngine(registry=_Reg())
        ctx = ExecutionContext(work_dir=str(tmp_path))

        result = engine.execute(definition, {}, ctx)

        assert result.success is False
        # The error must name the nonexistent operation
        error_text = result.error or ""
        assert "nonexistent_decode" in error_text, (
            f"Expected error to name 'nonexistent_decode', got: {error_text}"
        )
