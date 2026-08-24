"""Descriptor validation contract tests (Wave 2).

Edge cases for ``ToolDescriptor`` / ``load_descriptor`` / ``DescriptorTool``:
malformed JSON, missing fields, unknown types, env_dep resolution failures,
path rules (absolute vs relative-to-runtime), and per-platform dicts.
"""

import json
import os
import sys
from types import SimpleNamespace

import pytest

from app.tools.descriptor_tool import (
    DescriptorTool,
    ToolDescriptor,
    _select_platform_path,
    load_descriptor,
)


class _StubEnvRegistry:
    """resolve(name) -> {binary_path} ("" when the env is missing)."""

    def __init__(self, binary_by_dep=None):
        self._bins = dict(binary_by_dep or {})

    def resolve(self, name):
        return SimpleNamespace(binary_path=self._bins.get(name, ""))


def _write_json(tmp_path, data, filename="tool.json"):
    path = tmp_path / filename
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def _minimal_json(**overrides):
    data = {
        "name": "demo",
        "display_name": "Demo",
        "type": "binary",
        "path": "bin/demo",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# load_descriptor failures
# ---------------------------------------------------------------------------

def test_load_descriptor_malformed_json_raises_value_error(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ nope", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_descriptor(str(path))


@pytest.mark.parametrize("field", ["name", "display_name", "type", "path"])
def test_load_descriptor_missing_required_field_raises_naming_field(tmp_path, field):
    data = _minimal_json()
    del data[field]
    with pytest.raises(ValueError, match=f"missing required field: '{field}'"):
        load_descriptor(_write_json(tmp_path, data))


def test_descriptor_unknown_type_value_raises_value_error():
    with pytest.raises(ValueError, match="invalid tool type"):
        ToolDescriptor(
            name="x", display_name="X", type="binary_unknown", path="/bin/x",
            env_deps=[], validate={}, version={}, inputs=[], outputs=[],
        )


# ---------------------------------------------------------------------------
# ToolDescriptor path/type validation
# ---------------------------------------------------------------------------

def test_empty_path_dict_raises_value_error():
    with pytest.raises(ValueError, match="path"):
        ToolDescriptor(
            name="x", display_name="X", type="binary", path={},
            env_deps=[], validate={}, version={}, inputs=[], outputs=[],
        )


def test_per_platform_type_dict_validates_all_values():
    with pytest.raises(ValueError, match="invalid tool type"):
        ToolDescriptor(
            name="x", display_name="X",
            type={"win": "java_jar", "mac": "binary", "linux": "not_a_type"},
            path="/bin/x", env_deps=[], validate={}, version={},
            inputs=[], outputs=[],
        )


def test_non_snake_case_port_name_raises_value_error(tmp_path):
    data = _minimal_json(inputs=[{"name": "BadName", "type": "text"}])
    with pytest.raises(ValueError, match="port name must match"):
        load_descriptor(_write_json(tmp_path, data))


def test_tool_name_not_snake_case_is_accepted():
    # DOCUMENTED GAP: ToolDescriptor only requires a non-empty ``name``; the
    # snake_case rule is enforced on *port* names (Port.__post_init__), not on
    # the tool name. Asserting current behavior so a future schema change to
    # snake_case tool names fails this test loudly.
    descriptor = ToolDescriptor(
        name="Apktool", display_name="Apktool", type="binary", path="/bin/a",
        env_deps=[], validate={}, version={}, inputs=[], outputs=[],
    )
    assert descriptor.name == "Apktool"


# ---------------------------------------------------------------------------
# env_dep resolution
# ---------------------------------------------------------------------------

def test_env_dep_referencing_nonexistent_environment_is_invalid_not_crash():
    descriptor = ToolDescriptor(
        name="ghost", display_name="Ghost", type="binary", path="/bin/ghost",
        env_deps=["ghost_env"], validate={}, version={}, inputs=[], outputs=[],
    )
    tool = DescriptorTool(descriptor, _StubEnvRegistry({"ghost_env": ""}))
    assert tool.is_valid is False
    assert tool._env_resolutions == {"ghost_env": ""}


# ---------------------------------------------------------------------------
# path resolution (absolute vs relative-to-runtime)
# ---------------------------------------------------------------------------

def test_absolute_path_outside_runtime_is_allowed_as_is():
    descriptor = ToolDescriptor(
        name="py", display_name="Py", type="binary", path=sys.executable,
        env_deps=[], validate={}, version={}, inputs=[], outputs=[],
    )
    tool = DescriptorTool(descriptor, _StubEnvRegistry())
    # sys.executable lives outside runtime/ — absolute paths are trusted as-is.
    assert tool.tool_path == os.path.normpath(sys.executable)


def test_relative_path_resolves_against_runtime_dir():
    descriptor = ToolDescriptor(
        name="rel", display_name="Rel", type="binary", path="vendor/tool.exe",
        env_deps=[], validate={}, version={}, inputs=[], outputs=[],
    )
    tool = DescriptorTool(descriptor, _StubEnvRegistry())
    assert os.path.isabs(tool.tool_path)
    assert tool.tool_path.endswith(os.path.join("vendor", "tool.exe"))
    # Binary does not exist at the resolved location -> invalid but no crash.
    assert tool.is_valid is False


# ---------------------------------------------------------------------------
# per-platform dicts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("system", "path_dict", "expected"),
    [
        # current platform's key absent -> first usable entry (win/mac/linux)
        ("Linux", {"win": "w.exe", "mac": "m.exe"}, "w.exe"),
        ("Windows", {"mac": "m.exe", "linux": "l.exe"}, "m.exe"),
        ("Windows", {"win": "w.exe", "mac": "m.exe"}, "w.exe"),
        ("Darwin", {"win": "w.exe", "mac": "m.exe", "linux": "l.exe"}, "m.exe"),
    ],
)
def test_cross_platform_path_missing_current_platform_falls_back(
    monkeypatch, system, path_dict, expected
):
    monkeypatch.setattr("app.tools.descriptor_tool.platform.system", lambda: system)
    assert _select_platform_path(path_dict) == expected


def test_per_platform_path_dict_with_no_usable_entry_raises():
    with pytest.raises(ValueError, match="no usable entry"):
        _select_platform_path({"win": "", "mac": "", "linux": ""})
