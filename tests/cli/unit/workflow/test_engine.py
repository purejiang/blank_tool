"""Wave 3 tests: WorkflowEngine linear execution.

Covers 2/3-node linear workflows driving real builtin tools (file.write,
file.read, flow.assert, flow.log), expression resolution in node params
($inputs.* and $nodes.<id>.outputs.*), on_failure semantics (fail / skip /
retry:N), and the condition-field guard.  A stub registry is injected so no
real ToolManager discovery (or bundled binaries) is needed.
"""

import logging

import pytest

from app.common.exceptions import ToolException, ToolNotFoundError
from app.plugins.loader import SHIPPED_MANIFEST, load_plugins
from app.protocol import PortSet
from app.tools.builtin.base import BuiltinTool
from app.tools.tool_manager import ToolRegistry
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.engine import ExecutionContext, WorkflowEngine


class _StubRegistry:
    """Minimal tool registry: get_tool(name) -> tool object or None."""

    def __init__(self, tools=None):
        self._tools = dict(tools or {})

    def get_tool(self, name):
        return self._tools.get(name)


class _RegistryAdapter:
    """Wrap a ToolRegistry to expose ``get_tool`` + the plugin ``apply`` seam.

    The engine resolves tools via ``get_tool(name)``; the shipped plugins'
    ``apply`` calls ``ctx.register_tool(tool, kind=...)`` and reads
    ``ctx.tools.get_kind``.  ``get_tool`` maps the registry's
    ``ToolNotFoundError`` to None (matching ``ToolManager.get_tool``).
    """

    def __init__(self, registry):
        self.tools = registry

    def get_tool(self, name):
        try:
            return self.tools.get(name)
        except ToolNotFoundError:
            return None

    def register_tool(self, tool, kind="native"):
        return self.tools.register_plugin_tool(tool.name, tool, kind)


class _FlakyTool(BuiltinTool):
    """Builtin stub that fails the first N attempts, then succeeds."""

    name = "flaky.tool"
    description = "stub tool that fails before succeeding"
    ports = PortSet(inputs=[], outputs=[])

    def __init__(self, failures=1):
        self.failures = failures
        self.attempts = 0

    def execute(self, inputs, context):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise ToolException("flaky boom")
        return {"ok": True, "attempts": self.attempts}


class _DescriptorStub:
    """Descriptor-shaped tool (command-list contract, NOT a BuiltinTool)."""

    name = "desc.tool"

    def __init__(self):
        self.ports = PortSet(inputs=[], outputs=[])

    def execute(self, inputs, context):
        return {"success": True, "returncode": 0, "stdout": "desc-ok"}


class _NativePluginStub(BuiltinTool):
    """Native-plugin BuiltinTool registered via register_plugin_tool(kind="native")."""

    name = "native.tool"
    description = "native plugin stub"
    ports = PortSet(inputs=[], outputs=[])

    def execute(self, inputs, context):
        return {"native": True}


def _node(node_id, tool="file.write", **overrides) -> WorkflowNode:
    data = {"id": node_id, "tool": tool}
    data.update(overrides)
    return WorkflowNode(**data)


def _definition(nodes) -> WorkflowDefinition:
    return WorkflowDefinition(name="wf", nodes=nodes)


def _build_shipped_registry(overlay_dir):
    """Build a real (undiscovered) ToolRegistry with the 23 shipped builtins.

    Loads ``SHIPPED_MANIFEST`` via ``load_plugins`` with an adapter exposing
    the plugin ``apply`` seam (``register_tool`` + ``tools.get_kind``), then
    returns the adapter so the engine can resolve tools via ``get_tool``.
    """
    registry = ToolRegistry(registry_overlay_dir=overlay_dir)
    adapter = _RegistryAdapter(registry)
    load_plugins(adapter, manifest=SHIPPED_MANIFEST)
    return adapter


def _shipped_registry(tmp_path):
    """Fresh shipped registry for tests that mutate it (no cross-test leak)."""
    return _build_shipped_registry(str(tmp_path))


_DEFAULT_REGISTRY = None


def _default_registry():
    """Module-cached shipped registry used when a test passes no registry.

    The engine now resolves tools exclusively via ``registry.get_tool``, so the
    default registry must actually provide the 23 builtins (as shipped-native
    plugin tools).  Cached: builtins are stateless and rebuilding per test is
    wasteful.
    """
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        import tempfile

        _DEFAULT_REGISTRY = _build_shipped_registry(
            tempfile.mkdtemp(prefix="wf-engine-")
        )
    return _DEFAULT_REGISTRY


def _engine(registry=None) -> WorkflowEngine:
    return WorkflowEngine(
        registry=registry if registry is not None else _default_registry()
    )


def _context(tmp_path, **overrides) -> ExecutionContext:
    data = {"work_dir": str(tmp_path)}
    data.update(overrides)
    return ExecutionContext(**data)


def _write_read_nodes(message="hello"):
    return [
        _node("write", "file.write", next="read",
              params={"path": "out.txt", "content": "$inputs.message"}),
        _node("read", "file.read", params={"path": "$nodes.write.outputs.path"}),
    ]


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_2_node_file_write_read_succeeds(tmp_path):
    result = _engine().execute(
        _definition(_write_read_nodes()),
        {"message": "hello"},
        _context(tmp_path),
    )
    assert result.success is True
    assert result.error is None
    assert set(result.node_results) == {"write", "read"}
    assert result.node_results["write"]["error"] is None
    assert result.node_results["read"]["error"] is None
    assert result.outputs["content"] == "hello"
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "hello"


def test_expression_resolution_from_inputs(tmp_path):
    result = _engine().execute(
        _definition(_write_read_nodes()),
        {"message": "from-input"},
        _context(tmp_path),
    )
    assert result.success is True
    assert result.node_results["write"]["outputs"]["path"].endswith("out.txt")


def test_expression_resolution_from_upstream_outputs(tmp_path):
    # read.path comes from $nodes.write.outputs.path — resolved at runtime.
    result = _engine().execute(
        _definition(_write_read_nodes()),
        {"message": "hi"},
        _context(tmp_path),
    )
    assert result.success is True
    assert result.outputs["content"] == "hi"


def test_3_node_linear_workflow_completes_in_order(tmp_path):
    nodes = [
        _node("write", "file.write", next="read",
              params={"path": "out.txt", "content": "$inputs.message"}),
        _node("read", "file.read", next="log",
              params={"path": "$nodes.write.outputs.path"}),
        _node("log", "flow.log", params={"message": "$nodes.read.outputs.content"}),
    ]
    result = _engine().execute(_definition(nodes), {"message": "x"}, _context(tmp_path))
    assert result.success is True
    assert set(result.node_results) == {"write", "read", "log"}
    assert result.outputs == {"logged": True}


def test_flow_assert_condition_true_passes(tmp_path):
    nodes = [_node("check", "flow.assert", params={"condition": True})]
    result = _engine().execute(_definition(nodes), {}, _context(tmp_path))
    assert result.success is True
    assert result.outputs == {"passed": True}


def test_flow_log_writes_without_failing(tmp_path):
    nodes = [_node("log", "flow.log", params={"message": "hi", "level": "warning"})]
    result = _engine().execute(_definition(nodes), {}, _context(tmp_path))
    assert result.success is True
    assert result.node_results["log"]["error"] is None


def test_empty_workflow_succeeds(tmp_path):
    result = _engine().execute(_definition([]), {}, _context(tmp_path))
    assert result.success is True
    assert result.outputs == {}
    assert result.node_results == {}


# ---------------------------------------------------------------------------
# on_failure semantics
# ---------------------------------------------------------------------------

def test_on_failure_fail_stops_on_tool_exception(tmp_path):
    nodes = [
        _node("check", "flow.assert", next="write",
              params={"condition": False, "message": "boom"}),
        _node("write", "file.write", params={"path": "never.txt", "content": "x"}),
    ]
    result = _engine().execute(_definition(nodes), {}, _context(tmp_path))
    assert result.success is False
    assert "boom" in result.error
    assert set(result.node_results) == {"check"}  # downstream never ran
    assert not (tmp_path / "never.txt").exists()


def test_on_failure_skip_continues_past_failure(tmp_path):
    nodes = [
        _node("check", "flow.assert", next="write", on_failure="skip",
              params={"condition": False, "message": "boom"}),
        _node("write", "file.write", params={"path": "done.txt", "content": "x"}),
    ]
    result = _engine().execute(_definition(nodes), {}, _context(tmp_path))
    assert result.success is True
    assert result.node_results["check"]["error"] is not None
    assert "boom" in result.node_results["check"]["error"]
    assert result.node_results["check"]["outputs"] == {}  # skipped -> empty
    assert "write" in result.node_results
    assert (tmp_path / "done.txt").exists()


def test_retry_reexecutes_failing_node(tmp_path):
    flaky = _FlakyTool(failures=1)
    nodes = [_node("flaky", "flaky.tool", on_failure="retry:1")]
    result = _engine(registry=_StubRegistry({"flaky.tool": flaky})).execute(
        _definition(nodes), {}, _context(tmp_path)
    )
    assert result.success is True
    assert flaky.attempts == 2  # first attempt fails, retry succeeds
    assert result.outputs == {"ok": True, "attempts": 2}


def test_retry_exhausted_fails_workflow(tmp_path):
    flaky = _FlakyTool(failures=3)
    nodes = [_node("flaky", "flaky.tool", on_failure="retry:1")]
    result = _engine(registry=_StubRegistry({"flaky.tool": flaky})).execute(
        _definition(nodes), {}, _context(tmp_path)
    )
    assert result.success is False
    assert flaky.attempts == 2  # initial + one retry, then give up
    assert "flaky boom" in result.error


def test_retry_int_applies_regardless_of_on_failure(tmp_path):
    # node.retry drives retries even when on_failure is "fail" (docstring
    # previously claimed retry was only used with on_failure="retry:N").
    flaky = _FlakyTool(failures=3)
    nodes = [_node("flaky", "flaky.tool", on_failure="fail", retry=5)]
    result = _engine(registry=_StubRegistry({"flaky.tool": flaky})).execute(
        _definition(nodes), {}, _context(tmp_path)
    )
    assert result.success is True
    assert flaky.attempts == 4  # 3 failures absorbed by retry budget, 4th wins


def test_retry_n_string_backward_compat(tmp_path, caplog):
    # on_failure="retry:3" still works (3 retries) and logs a deprecation.
    flaky = _FlakyTool(failures=3)
    nodes = [_node("flaky", "flaky.tool", on_failure="retry:3", retry=0)]
    with caplog.at_level(logging.WARNING, logger="app.workflow.engine"):
        result = _engine(registry=_StubRegistry({"flaky.tool": flaky})).execute(
            _definition(nodes), {}, _context(tmp_path)
        )
    assert result.success is True
    assert flaky.attempts == 4  # 3 failures + 1 success
    assert any("deprecated" in rec.message for rec in caplog.records)


def test_retry_n_string_takes_precedence_over_int(tmp_path, caplog):
    # N in "retry:N" wins over node.retry; 4 failures exceed budget of 3.
    flaky = _FlakyTool(failures=4)
    nodes = [_node("flaky", "flaky.tool", on_failure="retry:3", retry=5)]
    with caplog.at_level(logging.WARNING, logger="app.workflow.engine"):
        result = _engine(registry=_StubRegistry({"flaky.tool": flaky})).execute(
            _definition(nodes), {}, _context(tmp_path)
        )
    assert result.success is False
    assert flaky.attempts == 4  # initial + 3 retries, then give up (not 6)
    assert "flaky boom" in result.error
    assert any("deprecated" in rec.message for rec in caplog.records)


def test_error_in_middle_with_fail_stops_downstream(tmp_path):
    nodes = [
        _node("w1", "file.write", next="check",
              params={"path": "a.txt", "content": "x"}),
        _node("check", "flow.assert", next="w2",
              params={"condition": False, "message": "mid-boom"}),
        _node("w2", "file.write", params={"path": "b.txt", "content": "y"}),
    ]
    result = _engine().execute(_definition(nodes), {}, _context(tmp_path))
    assert result.success is False
    assert set(result.node_results) == {"w1", "check"}  # w2 never ran
    assert "mid-boom" in result.error


def test_expression_resolution_failure_routes_through_on_failure(tmp_path):
    nodes = [
        _node("write", "file.write", next="read",
              params={"path": "out.txt", "content": "$inputs.missing"}),
        _node("read", "file.read", params={"path": "$nodes.write.outputs.path"}),
    ]
    result = _engine().execute(_definition(nodes), {}, _context(tmp_path))
    assert result.success is False
    assert "failed to resolve params" in result.error
    assert "read" not in result.node_results


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def test_condition_field_raises_not_implemented(tmp_path):
    nodes = [_node("a", "flow.log", condition="inputs.x > 0", params={"message": "hi"})]
    with pytest.raises(NotImplementedError, match="conditional branches"):
        _engine().execute(_definition(nodes), {}, _context(tmp_path))


def test_unknown_tool_fails_workflow(tmp_path):
    nodes = [_node("a", "does.not.exist")]
    result = _engine().execute(_definition(nodes), {}, _context(tmp_path))
    assert result.success is False
    assert "tool not found: does.not.exist" in result.error


def test_descriptor_tool_raises_not_implemented(tmp_path):
    class _LegacyTool:
        name = "legacy.tool"
        is_valid = True

    nodes = [_node("a", "legacy.tool")]
    engine = _engine(registry=_StubRegistry({"legacy.tool": _LegacyTool()}))
    with pytest.raises(NotImplementedError, match="has no execute"):
        engine.execute(_definition(nodes), {}, _context(tmp_path))


# ---------------------------------------------------------------------------
# Unified-registry resolution (todo 7): builtin / descriptor / native plugin
# ---------------------------------------------------------------------------

def test_builtin_descriptor_native_each_in_linear_workflow(tmp_path):
    """Each tool kind resolves through the registry in its own linear workflow."""
    registry = _shipped_registry(tmp_path)
    engine = _engine(registry=registry)

    # 1. builtin (shipped-native plugin tool) resolves through the registry.
    result = engine.execute(
        _definition(_write_read_nodes()), {"message": "hi"}, _context(tmp_path)
    )
    assert result.success is True
    assert result.outputs["content"] == "hi"

    # 2. descriptor tool (command-list contract) resolves via _descriptor_tools.
    registry.tools._descriptor_tools["desc.tool"] = _DescriptorStub()
    result = engine.execute(
        _definition([_node("d", "desc.tool", params={"args": ["x"]})]),
        {},
        _context(tmp_path),
    )
    assert result.success is True
    assert result.outputs == {"success": True, "returncode": 0, "stdout": "desc-ok"}

    # 3. native plugin tool (BuiltinTool) resolves via _plugin_tools.
    registry.tools.register_plugin_tool("native.tool", _NativePluginStub(), "native")
    result = engine.execute(
        _definition([_node("n", "native.tool")]), {}, _context(tmp_path)
    )
    assert result.success is True
    assert result.outputs == {"native": True}


def test_shipped_builtin_wins_over_same_name_descriptor(tmp_path):
    """A same-name ``file.read`` descriptor must NOT shadow the shipped builtin."""
    registry = _shipped_registry(tmp_path)
    fake = _DescriptorStub()
    fake.name = "file.read"
    registry.tools._descriptor_tools["file.read"] = fake

    from app.tools.builtin.file_tools import FileRead

    # get() priority: shipped-native plugin tool beats the descriptor.
    assert isinstance(registry.get_tool("file.read"), FileRead)

    result = _engine(registry=registry).execute(
        _definition(_write_read_nodes()),
        {"message": "shadow-test"},
        _context(tmp_path),
    )
    assert result.success is True
    assert result.outputs["content"] == "shadow-test"
