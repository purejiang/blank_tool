"""T23 gate — prove DescriptorTool executes binary/java_jar descriptors WITHOUT
importing any of the 7 Android tool classes (aapt, adb, apksigner, apktool,
bundletool, jarsigner, zipalign).

The test:
  1. Loads a binary descriptor from a fixture (sys.executable — always present).
  2. Loads a java_jar descriptor from examples/tools/android/apktool.json
     (the .jar path is fake; the command is stubbed so it never runs).
  3. Asserts the sys.modules keys do NOT include any of the 7 tool modules.
  4. Asserts DescriptorTool._build_command resolves the tool_path and
     interpreter (python/java) correctly via the stub registry.
"""

import os
import sys

import pytest

from app.tools.descriptor_tool import DescriptorTool, ToolDescriptor, load_descriptor
from app.common.base_executor import CommandExecutionContext

# ── Verify ZERO Android tool classes are imported ─────────────────────────
_ANDROID_MODULES = {
    "app.tools.aapt",
    "app.tools.adb",
    "app.tools.apksigner",
    "app.tools.apktool",
    "app.tools.bundletool",
    "app.tools.jarsigner",
    "app.tools.zipalign",
}

_loaded_android = _ANDROID_MODULES & set(sys.modules.keys())
assert not _loaded_android, (
    f"DescriptorTool standalone test loaded Android tool modules: {_loaded_android}"
)


# ── Stub helpers ─────────────────────────────────────────────────────────
class StubEnvRegistry:
    """Minimal env registry for stubbing java/python/node resolution."""

    def __init__(self, binary_by_dep=None):
        self._bins = dict(binary_by_dep or {})

    def resolve(self, name):
        from types import SimpleNamespace
        return SimpleNamespace(binary_path=self._bins.get(name, ""))


def _make_binary_descriptor(**overrides) -> ToolDescriptor:
    data = {
        "name": "stub_tool",
        "display_name": "Stub Tool",
        "type": "binary",
        "path": sys.executable,
        "env_deps": [],
        "validate": {},
        "version": {},
        "inputs": [],
        "outputs": [],
    }
    data.update(overrides)
    return ToolDescriptor(**data)


# ── Tests ────────────────────────────────────────────────────────────────
class TestDescriptorStandaloneBinary:
    """Binary-type descriptor — no interpreter needed, just tool_path."""

    def test_build_command_returns_tool_path_plus_args(self):
        desc = _make_binary_descriptor()
        tool = DescriptorTool(desc, StubEnvRegistry())
        cmd = tool._build_command(["--version"])
        assert cmd[0] == sys.executable
        assert "--version" in cmd

    def test_execute_runs_command_via_executor(self):
        desc = _make_binary_descriptor()
        tool = DescriptorTool(desc, StubEnvRegistry())
        result = tool.execute(["-c", "print('ok')"])
        assert result.get("returncode") == 0
        assert "ok" in (result.get("stdout") or "")

    def test_validate_checks_binary_exists(self):
        desc = _make_binary_descriptor(
            validate={"cmd": ["--version"], "expect_returncode": 0}
        )
        tool = DescriptorTool(desc, StubEnvRegistry())
        assert tool.is_valid is True


class TestDescriptorStandaloneJavaJar:
    """java_jar descriptor — needs java interpreter from env registry."""

    def test_build_command_prepends_java_jar(self):
        desc = _make_binary_descriptor(
            name="apktool",
            type="java_jar",
            path=r"C:\fake\apktool.jar",
            env_deps=["java"],
        )
        registry = StubEnvRegistry({"java": r"C:\fake\java.exe"})
        tool = DescriptorTool(desc, registry)
        cmd = tool._build_command(["d", "-f", "app.apk"])
        assert cmd[0] == r"C:\fake\java.exe"
        assert cmd[1] == "-jar"
        assert cmd[2] == r"C:\fake\apktool.jar"
        assert "d" in cmd
        assert "-f" in cmd

    def test_java_jar_can_be_constructed_even_without_real_java(self):
        """Construction succeeds; is_valid is False because binary missing."""
        desc = _make_binary_descriptor(
            name="apktool",
            type="java_jar",
            path=r"/nonexistent/apktool.jar",
            env_deps=["java"],
        )
        registry = StubEnvRegistry()  # no java
        tool = DescriptorTool(desc, registry)
        assert tool.is_valid is False  # binary doesn't exist
        assert tool.name == "apktool"


class TestDescriptorStandaloneLoadFromExamples:
    """Load real descriptor JSONs from examples/ and construct DescriptorTool."""

    EXAMPLES_DIR = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "examples", "tools", "android"
    )

    def test_load_apktool_descriptor_from_examples(self):
        path = os.path.join(self.EXAMPLES_DIR, "apktool.json")
        if not os.path.exists(path):
            pytest.skip("apktool.json not in examples (T21 may have moved it)")
        desc = load_descriptor(path)
        assert desc.name == "apktool"
        assert desc.type in ("java_jar",) or (
            isinstance(desc.type, dict) and "java_jar" in desc.type.values()
        )

    def test_construct_apktool_from_descriptor(self):
        path = os.path.join(self.EXAMPLES_DIR, "apktool.json")
        if not os.path.exists(path):
            pytest.skip("apktool.json not in examples")
        desc = load_descriptor(path)
        registry = StubEnvRegistry({"java": sys.executable})  # fake java
        tool = DescriptorTool(desc, registry)
        # Should construct successfully even though the binary doesn't exist
        assert tool.name == "apktool"
        # is_valid may be True or False depending on whether the binary exists
        # — the key point is that construction succeeded without importing
        # any Android tool class.

    def test_get_java_path_falls_back_to_utils_env(self):
        desc = _make_binary_descriptor(
            name="bundletool",
            type="java_jar",
            path=r"/fake/bundletool.jar",
            env_deps=["java"],
        )
        registry = StubEnvRegistry()  # no java resolved
        tool = DescriptorTool(desc, registry)
        java_path = tool.get_java_path()
        # Falls back to app.utils.env.get_java_bin() — should return a string
        assert isinstance(java_path, str)
        assert len(java_path) > 0
