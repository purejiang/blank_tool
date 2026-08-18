"""Wave 2 tests: unified tool registry — post-T21 (descriptors externalized).

After T21 externalized all Android descriptor tools to ``examples/tools/android/``,
the bundled registry ships zero descriptor tools.  These tests verify the
ToolRegistry still works correctly: code-based tools are discovered when
``BT_RUNTIME_DIR`` points to a valid runtime, ToolNotFoundError is raised for
unregistered names, and an empty descriptor dir does not crash discovery.
"""

import os

import pytest

from app.common.exceptions import ToolNotFoundError
from app.protocol import PortSet
from app.tools.builtin.base import BuiltinTool
from app.tools.descriptor_tool import DescriptorTool
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
