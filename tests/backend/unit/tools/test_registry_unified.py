"""Wave 2 tests: unified tool registry — code-based and descriptor-based tools
coexist under one ToolManager, with the descriptor-wins (except adb) rule.

These tests exercise the real singleton against the real bundled runtime
(adb.exe, apktool.jar, jre/...), which is present in this repo. They are
guarded so CI without the runtime stays green — the *priority* assertions
(which class wins) hold even when binaries are missing, only the
``get_available_tools`` content would differ.
"""

import os

import pytest

from app.tools.descriptor_tool import DescriptorTool
from app.tools.tool_manager import ToolManager

_RUNTIME_ADB = os.path.join("runtime", "adb", "adb.exe")
_RUNTIME_APKTOOL = os.path.join("runtime", "apktool", "apktool.jar")

_REQUIRES_RUNTIME = pytest.mark.skipif(
    not (
        os.path.isfile(_RUNTIME_ADB)
        and os.path.isfile(_RUNTIME_APKTOOL)
    ),
    reason="bundled runtime binaries not present",
)


def test_get_tool_apktool_returns_descriptor_tool():
    tool = ToolManager.instance().get_tool("apktool")
    assert isinstance(tool, DescriptorTool)
    assert tool.name == "apktool"


def test_get_tool_adb_returns_code_class():
    # adb is the streaming exception: its descriptor is shadowed by the code
    # class (_CODE_PRIORITY_NAMES) so logcat etc. keep working.
    tool = ToolManager.instance().get_tool("adb")
    assert tool is not None
    assert not isinstance(tool, DescriptorTool)
    assert type(tool).__name__ == "Adb"


def test_list_all_includes_code_and_descriptor_tools():
    tools = ToolManager.instance().get_all_tools()
    assert "adb" in tools  # code-based
    assert "apktool" in tools  # descriptor-based
    assert "bundletool" in tools  # descriptor-based
    assert isinstance(tools["apktool"], DescriptorTool)


@_REQUIRES_RUNTIME
def test_get_available_tools_returns_only_valid_tools():
    available = ToolManager.instance().get_available_tools()
    assert available, "expected at least one available tool with bundled runtime"
    for _name, tool in available.items():
        assert tool.is_valid is True
    assert "apktool" in available
    assert "adb" in available
