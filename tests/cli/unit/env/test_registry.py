"""Tests for cli/app/env/registry.py — EnvironmentRegistry."""

import json
import os
from pathlib import Path

import pytest

from app.env.registry import EnvironmentRegistry

# The bundled JRE shipped with the app (runtime/jre/bin/java.exe at project
# root). The registry's _runtime_dir() falls back to the project-root runtime/.
_BUNDLED_JRE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "runtime", "jre", "bin", "java.exe"
    )
)
_JRE_BUNDLED = os.path.isfile(_BUNDLED_JRE)


# ---------------------------------------------------------------------------
# Path-override helpers (WP3 #13)
# ---------------------------------------------------------------------------

def _write_env_descriptor(dir_path: Path, name: str = "ovr_env", **fields) -> None:
    """Write a minimal environment descriptor JSON into *dir_path*."""
    data = {
        "name": name,
        "display_name": "Override Env",
        "type": "custom",
        "binary": "ovrtool.exe",
        "version_cmd": [],
        "version_regex": r"(\d+\.\d+)",
        "search_paths": [],
    }
    data.update(fields)
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


def _touch_binary(dir_path: Path, name: str = "ovrtool.exe") -> str:
    """Create a placeholder binary on disk and return its absolute path."""
    dir_path.mkdir(parents=True, exist_ok=True)
    binary = dir_path / name
    binary.write_text("", encoding="utf-8")
    return str(binary)


def _make_registry(tmp_path: Path, monkeypatch, **fields) -> EnvironmentRegistry:
    """Build a registry whose overlay root is ``<BT_OUTPUT_DIR>/registry``.

    ``BT_OUTPUT_DIR`` is set so the module-level ``_find_binary`` override
    lookup (which resolves ``<output>/registry/overrides.json``) reads the same
    file the registry writes.
    """
    monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path))
    env_dir = tmp_path / "envs"
    _write_env_descriptor(env_dir, **fields)
    registry = EnvironmentRegistry(overlay_dir=str(tmp_path / "registry"))
    registry.discover(descriptor_dir=str(env_dir))
    return registry


def test_registry_constructs_empty():
    registry = EnvironmentRegistry()
    assert registry.list_all() == []


def test_discover_missing_directory_is_noop(tmp_path):
    registry = EnvironmentRegistry()
    registry.discover(str(tmp_path / "does-not-exist"))
    assert registry.list_all() == []


def test_discover_real_descriptor_dir_finds_three_environments():
    registry = EnvironmentRegistry()
    registry.discover()
    names = {resolved.name for resolved in registry.list_all()}
    assert names == {"java", "python", "node"}


def test_resolve_unknown_name_returns_invalid_gracefully():
    registry = EnvironmentRegistry()
    resolved = registry.resolve("nonexistent")
    assert resolved.name == "nonexistent"
    assert resolved.is_valid is False
    assert resolved.binary_path == ""
    assert resolved.root_path == ""
    assert resolved.version == ""


@pytest.mark.skipif(
    not _JRE_BUNDLED, reason="bundled JRE runtime (runtime/jre/bin/java.exe) not present"
)
def test_resolve_java_finds_bundled_jre():
    registry = EnvironmentRegistry()
    registry.discover()
    resolved = registry.resolve("java")
    assert resolved.is_valid is True
    assert resolved.binary_path.lower().endswith("java.exe")
    assert resolved.root_path != ""
    assert resolved.version != ""


def test_refresh_clears_resolution_cache():
    registry = EnvironmentRegistry()
    first = registry.resolve("nonexistent")
    second = registry.resolve("nonexistent")
    assert first is second  # cached until refresh

    registry.refresh()
    third = registry.resolve("nonexistent")
    assert third is not first
    assert third.is_valid is False


def test_discover_skips_malformed_descriptor_without_crashing(tmp_path):
    bad_dir = tmp_path / "bad-envs"
    bad_dir.mkdir()
    (bad_dir / "broken.json").write_text("{ not json", encoding="utf-8")

    registry = EnvironmentRegistry()
    registry.discover(str(bad_dir))  # must not raise
    assert registry.list_all() == []


def test_discover_skips_malformed_but_keeps_valid_ones(tmp_path):
    env_dir = tmp_path / "envs"
    env_dir.mkdir()
    (env_dir / "broken.json").write_text('{"name": "broken"', encoding="utf-8")
    valid = {
        "name": "custom_tool",
        "display_name": "Custom Tool",
        "type": "custom",
        "binary": "tool.exe",
        "version_cmd": ["--version"],
        "version_regex": r"v(\d+\.\d+)",
        "search_paths": [],
    }
    (env_dir / "custom.json").write_text(json.dumps(valid), encoding="utf-8")

    registry = EnvironmentRegistry()
    registry.discover(str(env_dir))
    resolved = registry.resolve("custom_tool")
    # Malformed file skipped; valid one discovered (unresolved, no binary on disk).
    assert resolved.name == "custom_tool"
    assert resolved.is_valid is False


# ---------------------------------------------------------------------------
# Path overrides (WP3 #13): env_paths sits between env_var_override and the
# runtime search paths.
# ---------------------------------------------------------------------------

def test_path_override_beats_runtime_system_env_and_path(tmp_path, monkeypatch):
    runtime_bin = _touch_binary(tmp_path / "runtime" / "ovrtool")
    home_bin = _touch_binary(tmp_path / "java_home")
    path_bin = _touch_binary(tmp_path / "pathdir")
    override_bin = _touch_binary(tmp_path / "override_dir")

    monkeypatch.setenv("BT_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("JAVA_HOME", str(tmp_path / "java_home"))
    monkeypatch.setenv(
        "PATH", str(tmp_path / "pathdir") + os.pathsep + os.environ.get("PATH", "")
    )

    registry = _make_registry(
        tmp_path, monkeypatch, type="jre", search_paths=["ovrtool"]
    )

    # Baseline (no override): the bundled runtime wins over JAVA_HOME and PATH.
    baseline = registry.resolve("ovr_env")
    assert baseline.binary_path == runtime_bin
    assert baseline.root_path == str(tmp_path / "runtime" / "ovrtool")
    assert home_bin != baseline.binary_path
    assert path_bin != baseline.binary_path

    registry.set_path_override("ovr_env", str(tmp_path / "override_dir"))
    registry.refresh()

    resolved = registry.resolve("ovr_env")
    assert resolved.binary_path == override_bin
    assert resolved.root_path == str(tmp_path / "override_dir")


def test_env_var_override_still_beats_path_override(tmp_path, monkeypatch):
    env_bin = _touch_binary(tmp_path / "env_dir")
    override_bin = _touch_binary(tmp_path / "override_dir")
    monkeypatch.setenv("BT_OVR_ENV_BIN", env_bin)

    registry = _make_registry(
        tmp_path, monkeypatch, env_var_override="BT_OVR_ENV_BIN"
    )
    registry.set_path_override("ovr_env", str(tmp_path / "override_dir"))
    registry.refresh()

    resolved = registry.resolve("ovr_env")
    assert resolved.binary_path == env_bin
    assert resolved.root_path == str(tmp_path / "env_dir")
    assert resolved.binary_path != override_bin


def test_file_override_is_used_directly(tmp_path, monkeypatch):
    file_bin = _touch_binary(tmp_path / "somewhere", "ovrtool.exe")

    registry = _make_registry(tmp_path, monkeypatch)
    registry.set_path_override("ovr_env", file_bin)
    registry.refresh()

    resolved = registry.resolve("ovr_env")
    assert resolved.binary_path == file_bin
    assert resolved.root_path == str(tmp_path / "somewhere")


def test_directory_override_probes_root_then_bin(tmp_path, monkeypatch):
    root_style = tmp_path / "root_style"
    _touch_binary(root_style)  # <dir>/ovrtool.exe

    registry = _make_registry(tmp_path, monkeypatch)
    registry.set_path_override("ovr_env", str(root_style))
    registry.refresh()
    resolved = registry.resolve("ovr_env")
    assert resolved.binary_path == str(root_style / "ovrtool.exe")
    assert resolved.root_path == str(root_style)

    bin_style = tmp_path / "bin_style"
    _touch_binary(bin_style / "bin")  # <dir>/bin/ovrtool.exe

    registry.set_path_override("ovr_env", str(bin_style))
    registry.refresh()
    resolved = registry.resolve("ovr_env")
    assert resolved.binary_path == str(bin_style / "bin" / "ovrtool.exe")
    assert resolved.root_path == str(bin_style)


def test_unresolvable_override_falls_through_to_runtime(tmp_path, monkeypatch):
    runtime_bin = _touch_binary(tmp_path / "runtime" / "ovrtool")
    monkeypatch.setenv("BT_RUNTIME_DIR", str(tmp_path / "runtime"))

    registry = _make_registry(tmp_path, monkeypatch, search_paths=["ovrtool"])
    registry.set_path_override("ovr_env", str(tmp_path / "missing" / "nope.exe"))
    registry.refresh()

    assert registry.resolve("ovr_env").binary_path == runtime_bin


def test_override_takes_effect_only_after_refresh(tmp_path, monkeypatch):
    runtime_bin = _touch_binary(tmp_path / "runtime" / "ovrtool")
    override_bin = _touch_binary(tmp_path / "override_dir")
    monkeypatch.setenv("BT_RUNTIME_DIR", str(tmp_path / "runtime"))

    registry = _make_registry(tmp_path, monkeypatch, search_paths=["ovrtool"])
    first = registry.resolve("ovr_env")
    assert first.binary_path == runtime_bin

    # The resolution cache still serves the stale result until refresh().
    registry.set_path_override("ovr_env", str(override_bin))
    assert registry.resolve("ovr_env") is first

    registry.refresh()
    assert registry.resolve("ovr_env").binary_path == override_bin


def test_get_descriptor_exposes_metadata(tmp_path, monkeypatch):
    registry = _make_registry(tmp_path, monkeypatch)

    descriptor = registry.get_descriptor("ovr_env")
    assert descriptor is not None
    assert descriptor.name == "ovr_env"
    assert descriptor.display_name == "Override Env"
    assert descriptor.type == "custom"
    assert registry.get_descriptor("missing_env") is None
