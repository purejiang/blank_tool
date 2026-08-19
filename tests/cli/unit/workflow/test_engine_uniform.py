"""Regression test (plugin-ecosystem todo 14): uniform tool-execution contract.

The three tool kinds must execute through the SAME engine path:

1. a builtin primitive (registered as a shipped-native plugin tool) —
   ``file.write`` -> ``file.read`` on real builtins;
2. a descriptor stub (command-list contract, NOT a ``BuiltinTool``, whose
   ``execute(inputs, context)`` returns a dict) registered into the registry;
3. a native plugin stub (``BuiltinTool`` registered via
   ``register_plugin_tool(..., kind="native")``).

"Same engine path" means: resolution exclusively via ``registry.get_tool``,
validation via ``_validate_inputs``, execution via the uniform
``tool.execute(inputs, ToolContext)`` call, and — crucially — failure
normalization into node errors so ``on_failure`` / ``retry`` semantics apply
identically to every kind (never an uncaught exception).

Every test builds a FRESH ``ToolRegistry`` (via the ``registry`` fixture) so
the stubs registered here never leak across tests; the singleton
``ToolManager.instance()`` is never touched.

Helpers mirror ``tests/cli/unit/workflow/test_engine.py`` so this file stays
self-contained (no ``__init__.py`` makes cross-test-module imports fragile).
"""

import pytest

from app.common.exceptions import ToolException, ToolNotFoundError
from app.plugins.loader import SHIPPED_MANIFEST, load_plugins
from app.protocol import PortSet
from app.tools.builtin.base import BuiltinTool
from app.tools.tool_manager import ToolRegistry
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.engine import ExecutionContext, WorkflowEngine


# ---------------------------------------------------------------------------
# Shared helpers (mirrored from test_engine.py)
# ---------------------------------------------------------------------------

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


class _DescriptorStub:
    """Descriptor-shaped tool (command-list contract, NOT a BuiltinTool)."""

    name = "desc.tool"

    def __init__(self):
        self.ports = PortSet(inputs=[], outputs=[])

    def execute(self, inputs, context):
        return {"success": True, "returncode": 0, "stdout": "desc-ok"}


class _FailingDescriptorStub(_DescriptorStub):
    """Descriptor stub whose env dependency is missing (command fails)."""

    name = "desc.fail"

    def execute(self, inputs, context):
        return {
            "success": False,
            "returncode": 1,
            "stderr": "environment 'fake-env' not found or invalid",
        }


class _FlakyDescriptorStub(_DescriptorStub):
    """Descriptor stub that reports failure the first N attempts, then succeeds."""

    name = "desc.flaky"

    def __init__(self, failures=1):
        super().__init__()
        self.failures = failures
        self.attempts = 0

    def execute(self, inputs, context):
        self.attempts += 1
        if self.attempts <= self.failures:
            return {
                "success": False,
                "returncode": 1,
                "stderr": "transient descriptor failure",
            }
        return {"success": True, "returncode": 0, "stdout": "desc-retry-ok"}


class _NativePluginStub(BuiltinTool):
    """Native-plugin BuiltinTool registered via register_plugin_tool(kind="native")."""

    name = "native.tool"
    description = "native plugin stub"
    ports = PortSet(inputs=[], outputs=[])

    def execute(self, inputs, context):
        return {"native": True}


class _FailingNativeStub(_NativePluginStub):
    """Native plugin stub that always raises ToolException."""

    name = "native.fail"

    def execute(self, inputs, context):
        raise ToolException("native boom: missing runtime")


class _FlakyNativeStub(_NativePluginStub):
    """Native plugin stub that raises the first N attempts, then succeeds."""

    name = "native.flaky"

    def __init__(self, failures=1):
        self.failures = failures
        self.attempts = 0

    def execute(self, inputs, context):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise ToolException("transient native failure")
        return {"native": True, "attempts": self.attempts}


class _FlakyBuiltinStub(BuiltinTool):
    """Builtin stub that raises the first N attempts, then succeeds.

    Registered as a plugin tool with kind="shipped-native" — mirroring how the
    shipped primitives sit in the registry.  The kind only affects name-conflict
    resolution, NOT the execution path, so the retry semantics asserted here are
    the same ones the real builtins see.
    """

    name = "builtin.flaky"
    description = "flaky builtin stub"
    ports = PortSet(inputs=[], outputs=[])

    def __init__(self, failures=1):
        self.failures = failures
        self.attempts = 0

    def execute(self, inputs, context):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise ToolException("transient builtin failure")
        return {"ok": True, "attempts": self.attempts}


def _node(node_id, tool, **overrides) -> WorkflowNode:
    data = {"id": node_id, "tool": tool}
    data.update(overrides)
    return WorkflowNode(**data)


def _definition(nodes) -> WorkflowDefinition:
    return WorkflowDefinition(name="wf", nodes=nodes)


def _engine(registry) -> WorkflowEngine:
    return WorkflowEngine(registry=registry)


def _context(tmp_path, **overrides) -> ExecutionContext:
    data = {"work_dir": str(tmp_path)}
    data.update(overrides)
    return ExecutionContext(**data)


def _build_shipped_registry(overlay_dir):
    """Build a real (undiscovered) ToolRegistry with the 20 shipped builtins.

    Loads ``SHIPPED_MANIFEST`` via ``load_plugins`` with an adapter exposing
    the plugin ``apply`` seam, then returns the adapter so the engine can
    resolve tools via ``get_tool``.
    """
    registry = ToolRegistry(registry_overlay_dir=overlay_dir)
    adapter = _RegistryAdapter(registry)
    load_plugins(adapter, manifest=SHIPPED_MANIFEST)
    return adapter


def _register_descriptor(registry, stub):
    """Register a descriptor stub into the registry's descriptor slot.

    Descriptor tools are not plugin tools: they live in ``_descriptor_tools``
    (the same slot real descriptor discovery populates), which ``get()``
    consults after plugin tools.  The engine only sees ``get_tool(name)``.
    """
    registry.tools._descriptor_tools[stub.name] = stub


def _write_read_nodes(message="hello"):
    return [
        _node("write", "file.write", next="read",
              params={"path": "out.txt", "content": "$inputs.message"}),
        _node("read", "file.read", params={"path": "$nodes.write.outputs.path"}),
    ]


@pytest.fixture
def registry(tmp_path):
    """Fresh shipped registry (real ToolRegistry, never the singleton)."""
    return _build_shipped_registry(str(tmp_path))


# ---------------------------------------------------------------------------
# One linear workflow per tool kind: same engine path, same success contract
# ---------------------------------------------------------------------------

def test_builtin_write_read_runs_through_registry(registry, tmp_path):
    result = _engine(registry).execute(
        _definition(_write_read_nodes()), {"message": "hello"}, _context(tmp_path)
    )
    assert result.success is True
    assert result.error is None
    assert result.outputs["content"] == "hello"
    assert "size" in result.outputs
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "hello"


def test_descriptor_stub_runs_through_registry(registry, tmp_path):
    _register_descriptor(registry, _DescriptorStub())
    result = _engine(registry).execute(
        _definition([_node("d", "desc.tool", params={"args": ["x"]})]),
        {},
        _context(tmp_path),
    )
    assert result.success is True
    assert result.error is None
    # Command-list contract dict is passed through as the node outputs.
    assert result.outputs == {
        "success": True, "returncode": 0, "stdout": "desc-ok",
    }


def test_native_plugin_stub_runs_through_registry(registry, tmp_path):
    registry.register_tool(_NativePluginStub(), kind="native")
    result = _engine(registry).execute(
        _definition([_node("n", "native.tool")]), {}, _context(tmp_path)
    )
    assert result.success is True
    assert result.error is None
    assert result.outputs == {"native": True}


# ---------------------------------------------------------------------------
# Failure normalization: every kind fails into a node error, never an
# uncaught exception (on_failure="fail" is the default).
# ---------------------------------------------------------------------------

def _setup_builtin_failure(registry):
    # Real builtin error convention: {"error": ...} dict from file.read.
    node = _node("read", "file.read", params={"path": "missing.txt"})
    return node, "file not found"


def _setup_descriptor_failure(registry):
    _register_descriptor(registry, _FailingDescriptorStub())
    node = _node("d", "desc.fail", params={"args": []})
    return node, "environment 'fake-env'"


def _setup_native_failure(registry):
    registry.register_tool(_FailingNativeStub(), kind="native")
    node = _node("n", "native.fail")
    return node, "native boom"


@pytest.mark.parametrize(
    "setup",
    [_setup_builtin_failure, _setup_descriptor_failure, _setup_native_failure],
)
def test_failure_normalized_to_node_error(registry, tmp_path, setup):
    node, expected = setup(registry)
    result = _engine(registry).execute(_definition([node]), {}, _context(tmp_path))

    assert result.success is False
    assert isinstance(result.error, str) and result.error
    assert result.outputs == {}

    node_result = result.node_results[node.id]
    assert node_result["outputs"] == {}
    assert isinstance(node_result["error"], str) and node_result["error"]
    assert expected in node_result["error"]


# ---------------------------------------------------------------------------
# on_failure="skip": every kind skips past its failure and the workflow still
# succeeds with the error recorded on the node.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "setup",
    [_setup_builtin_failure, _setup_descriptor_failure, _setup_native_failure],
)
def test_on_failure_skip_continues_across_kinds(registry, tmp_path, setup):
    node, expected = setup(registry)
    node.on_failure = "skip"
    result = _engine(registry).execute(_definition([node]), {}, _context(tmp_path))

    assert result.success is True
    assert result.error is None
    node_result = result.node_results[node.id]
    assert node_result["outputs"] == {}
    assert isinstance(node_result["error"], str)
    assert expected in node_result["error"]


# ---------------------------------------------------------------------------
# Retry: retry=1 recovers a transient failure for every kind.
# ---------------------------------------------------------------------------

def _setup_builtin_retry(registry):
    stub = _FlakyBuiltinStub(failures=1)
    registry.register_tool(stub, kind="shipped-native")
    return stub, _node("r", "builtin.flaky", retry=1), {"ok": True, "attempts": 2}


def _setup_descriptor_retry(registry):
    stub = _FlakyDescriptorStub(failures=1)
    _register_descriptor(registry, stub)
    node = _node("r", "desc.flaky", params={"args": []}, retry=1)
    return stub, node, {"success": True, "returncode": 0, "stdout": "desc-retry-ok"}


def _setup_native_retry(registry):
    stub = _FlakyNativeStub(failures=1)
    registry.register_tool(stub, kind="native")
    return stub, _node("r", "native.flaky", retry=1), {
        "native": True, "attempts": 2,
    }


@pytest.mark.parametrize(
    "setup",
    [_setup_builtin_retry, _setup_descriptor_retry, _setup_native_retry],
)
def test_retry_recovers_across_kinds(registry, tmp_path, setup):
    stub, node, expected_outputs = setup(registry)
    result = _engine(registry).execute(_definition([node]), {}, _context(tmp_path))

    assert result.success is True
    assert result.error is None
    assert stub.attempts == 2  # first attempt fails, retry=1 succeeds
    assert result.outputs == expected_outputs
