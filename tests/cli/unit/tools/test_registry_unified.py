"""Wave 2 tests: unified tool registry — post-T21 (descriptors externalized).

After T21 externalized all Android descriptor tools to ``examples/tools/android/``,
the bundled registry ships zero descriptor tools.  These tests verify the
ToolRegistry still works correctly: code-based tools are discovered when
``BT_RUNTIME_DIR`` points to a valid runtime, ToolNotFoundError is raised for
unregistered names, and an empty descriptor dir does not crash discovery.
"""

import json
import os
from pathlib import Path

import pytest

from app.common.exceptions import ToolNotFoundError
from app.protocol import PortSet
from app.tools.builtin.base import BuiltinTool
from app.tools.descriptor_tool import DescriptorTool, load_descriptor
from app.tools.tool_manager import ToolManager, ToolRegistry

_RUNTIME_ADB = os.path.join("runtime", "adb", "adb.exe")
_RUNTIME_APKTOOL = os.path.join("runtime", "apktool", "apktool.jar")

_RUNTIME_DIR = os.environ.get("BT_RUNTIME_DIR") or "."

_REQUIRES_RUNTIME = pytest.mark.skipif(
    not (
        os.path.isfile(_RUNTIME_ADB)
        and os.path.isfile(_RUNTIME_APKTOOL)
    ),
    reason="bundled runtime binaries not present",
)


def test_no_descriptor_tools_after_externalization():
    """T21: zero descriptor tools are bundled; ToolManager.get_tool returns None."""
    # apktool was previously a DescriptorTool from registry/tools/apktool.json.
    # After T21 moved those JSON files, the descriptor is gone.
    tool = ToolManager.instance().get_tool("apktool")
    # May be None (descriptor gone + code-class not discovered without runtime)
    # or an ApkTool code-class instance if BT_RUNTIME_DIR is valid.
    # The key invariant: it is NOT a DescriptorTool.
    if tool is not None:
        assert not isinstance(tool, DescriptorTool), (
            f"apktool should not be a DescriptorTool after T21, "
            f"got {type(tool).__name__}"
        )


def test_tool_not_found_for_unknown_name():
    """ToolNotFoundError is caught and returned as None by ToolManager.get_tool."""
    tool = ToolManager.instance().get_tool("definitely.not.a.tool")
    assert tool is None


def test_empty_descriptor_dir_no_crash():
    """T21: registry/tools/ is empty; discovery must not crash or hang."""
    # If ToolManager was already initialized in this session, calling
    # get_all_tools() must at least return something (possibly empty for
    # code tools if BT_RUNTIME_DIR is missing — that is fine, no crash).
    tools = ToolManager.instance().get_all_tools()
    # get_all_tools() returns a dict; the content depends on runtime
    # availability.  Just assert it's a dict (not an exception).
    assert isinstance(tools, dict)


@_REQUIRES_RUNTIME
@pytest.mark.skip(
    reason="ToolManager singleton may already be initialized without runtime "
    "from earlier tests. Run this test in isolation with BT_RUNTIME_DIR set "
    "before the first ToolManager.instance() call."
)
def test_code_tools_discovered_when_runtime_present():
    """When BT_RUNTIME_DIR points to valid runtime, code-based tools are found."""
    available = ToolManager.instance().get_available_tools()
    assert available, "expected at least one available tool with bundled runtime"
    for _name, tool in available.items():
        assert tool.is_valid is True
    # At minimum, adb should be available (it's a code class, not a descriptor)
    assert "adb" in available


# ── Wave 2 Task 5: plugin-tool registration ────────────────────────────────


def _make_builtin(name: str) -> BuiltinTool:
    """Build a minimal BuiltinTool instance carrying *name*."""
    cls = type(
        f"_FakeBuiltin_{name.replace('.', '_')}",
        (BuiltinTool,),
        {
            "name": name,
            "description": "fake plugin builtin",
            "ports": PortSet([], []),
            "execute": staticmethod(lambda inputs, context: {}),
        },
    )
    return cls()


@pytest.fixture
def registry(tmp_path):
    """A fresh, undiscovered ToolRegistry isolated from the real output dir."""
    return ToolRegistry(registry_overlay_dir=str(tmp_path))


def test_register_plugin_tool_list_get_kind(registry):
    tool = _make_builtin("file.read")
    returned = registry.register_plugin_tool("file.read", tool, "shipped-native")
    assert returned is tool
    assert "file.read" in registry.list_all()
    assert registry.get("file.read") is tool
    assert registry.get_kind("file.read") == "shipped-native"


def test_unregister_plugin_tool_removes_and_re_resolves(registry):
    tool = _make_builtin("file.read")
    registry.register_plugin_tool("file.read", tool, "shipped-native")
    # cache the instance so we also verify the cache is purged on unregister
    assert registry.get("file.read") is tool
    registry.unregister_plugin_tool("file.read")
    assert "file.read" not in registry.list_all()
    assert registry.get_kind("file.read") is None
    with pytest.raises(ToolNotFoundError):
        registry.get("file.read")


def test_register_plugin_tool_duplicate_raises(registry):
    registry.register_plugin_tool("file.read", _make_builtin("file.read"), "shipped-native")
    with pytest.raises(ValueError):
        registry.register_plugin_tool(
            "file.read", _make_builtin("file.read"), "shipped-native"
        )


def test_register_plugin_tool_invalid_kind_raises(registry):
    with pytest.raises(ValueError):
        registry.register_plugin_tool("file.read", _make_builtin("file.read"), "code")


def test_native_conflicts_with_descriptor(registry):
    registry._descriptor_tools["conflict.tool"] = object()
    with pytest.raises(ValueError):
        registry.register_plugin_tool(
            "conflict.tool", _make_builtin("conflict.tool"), "native"
        )


def test_native_conflicts_with_discovered_code(registry):
    registry._discovered["code.tool"] = object
    with pytest.raises(ValueError):
        registry.register_plugin_tool(
            "code.tool", _make_builtin("code.tool"), "native"
        )


def test_shipped_native_coexists_with_descriptor_and_wins(registry):
    registry._descriptor_tools["file.read"] = object()
    shipped = _make_builtin("file.read")
    # shipped-native is EXEMPT from descriptor name-conflict: no raise
    registry.register_plugin_tool("file.read", shipped, "shipped-native")
    # get() priority makes the shipped builtin win over the descriptor
    assert registry.get("file.read") is shipped


# ── Wave 2 Task 10: descriptor tools are kind="descriptor" ─────────────────

#: Minimal valid descriptor dict (same shape the tool page imports).
_DESCRIPTOR_JSON = {
    "name": "demo.descriptor",
    "display_name": "Demo Descriptor",
    "type": "binary",
    "path": "demo/bin",
    "env_deps": [],
    "validate": {},
    "version": {},
    "inputs": [],
    "outputs": [],
}


def test_descriptor_add_and_delete_kind(registry):
    """Wave 2 (todo 10): descriptors carry kind 'descriptor'.

    add_descriptor_file() -> re-discover -> get_kind(name) == "descriptor";
    delete_descriptor() -> re-discover clears the stale kind, so the name
    disappears from list_all() and get_kind returns None.
    """
    tool = registry.add_descriptor_file(dict(_DESCRIPTOR_JSON))
    name = tool.name
    assert name in registry.list_all()
    assert registry.get_kind(name) == "descriptor"

    registry.delete_descriptor(name)
    assert name not in registry.list_all()
    assert registry.get_kind(name) is None


def test_rediscover_preserves_plugin_kinds(registry):
    """Wave 2 (todo 10): re-discovering descriptors must not clobber
    native / shipped-native plugin kinds."""
    registry.register_plugin_tool("file.read", _make_builtin("file.read"), "shipped-native")
    registry.register_plugin_tool("net.request", _make_builtin("net.request"), "native")
    registry.add_descriptor_file(dict(_DESCRIPTOR_JSON))
    assert registry.get_kind("file.read") == "shipped-native"
    assert registry.get_kind("net.request") == "native"
    assert registry.get_kind("demo.descriptor") == "descriptor"


# ── Wave 2 Task 11: real descriptor import / delete regression ─────────────

#: Real Android descriptor shipped in examples/ (bundled registry ships none).
_EXAMPLES_ROOT = Path(__file__).resolve().parents[4] / "examples"
_EXAMPLES_ADB = _EXAMPLES_ROOT / "tools" / "android" / "adb.json"


def _import_example_adb(registry) -> str:
    """Import the real examples/tools/android/adb.json into *registry*
    (fresh overlay in tmp_path — never mutates the real output dir)."""
    assert _EXAMPLES_ADB.is_file(), f"missing example descriptor: {_EXAMPLES_ADB}"
    tool = registry.add_descriptor_file(
        json.loads(_EXAMPLES_ADB.read_text(encoding="utf-8"))
    )
    return tool.name


def test_descriptor_imported_from_examples_registers_kind_descriptor(registry):
    """Wave 2 (todo 11): importing a real examples/tools/android descriptor
    registers it with kind 'descriptor' and DescriptorTool semantics.

    adb may be valid or invalid depending on whether a runtime binary is
    reachable — assert the field is a bool consistent with DescriptorTool
    (version populated only when valid), not a hardcoded True.
    """
    descriptor = load_descriptor(str(_EXAMPLES_ADB))
    assert descriptor.name == "adb"

    name = _import_example_adb(registry)

    assert name in registry.list_all()
    assert registry.get_kind(name) == "descriptor"
    tool = registry.get(name)
    assert isinstance(tool, DescriptorTool)
    assert isinstance(tool.is_valid, bool)
    if not tool.is_valid:
        assert tool.version == ""


def test_descriptor_imported_from_examples_can_be_deleted(registry):
    """Wave 2 (todo 11): a real imported descriptor disappears from the
    registry after delete_descriptor — gone from list_all, kind cleared."""
    name = _import_example_adb(registry)
    assert name in registry.list_all()

    registry.delete_descriptor(name)

    assert name not in registry.list_all()
    assert registry.get_kind(name) is None


def test_delete_bundled_only_name_raises_value_error(registry):
    """Wave 2 (todo 11): deleting a bundled/code-only name (no overlay file)
    raises ValueError — mirrors tool_manager.py delete_descriptor."""
    with pytest.raises(ValueError, match="cannot be deleted"):
        registry.delete_descriptor("file.read")


# ── Wave 2 Task 9: core builtins resolve via the unified registry ─────────

#: The 10 CORE builtin primitive names (always shipped-native; the 13 extended
#: atomics are opt-in — covered by test_builtin_shipped.py::EXTENDED_NAMES).
_BUILTIN_NAMES = [
    # app.plugins.builtin.file (2)
    "file.read", "file.write",
    # app.plugins.builtin.text (1)
    "text.grep",
    # app.plugins.builtin.exec (1)
    "exec.shell",
    # app.plugins.builtin.flow (5)
    "flow.assert", "flow.log", "flow.foreach", "flow.branch", "flow.compare",
    # app.plugins.builtin.workflow (1)
    "workflow.run",
]


@pytest.mark.parametrize("name", _BUILTIN_NAMES)
def test_builtin_primitive_resolves_via_unified_registry(name):
    """Wave 2 (todo 9): every builtin resolves through ToolManager.get_tool().

    Locks the unified-registry path: ToolManager (NOT the deprecated
    ``_BUILTIN_TOOLS`` dict) is the resolution source for the shipped
    builtin primitives.  The shipped plugins are loaded once in
    ``ToolManager.__init__`` (todo 7), so the singleton already has them
    resident — no explicit manifest loading here, and they are NOT
    unregistered (process-resident).
    """
    tm = ToolManager.instance()
    tool = tm.get_tool(name)
    assert tool is not None, f"{name!r} must resolve via ToolManager.get_tool()"
    assert isinstance(tool, BuiltinTool), (
        f"{name!r} should be a BuiltinTool, got {type(tool).__name__}"
    )
    assert tool.name == name
    assert tm._registry.get_kind(name) == "shipped-native", (
        f"{name!r} must be kind 'shipped-native'"
    )
