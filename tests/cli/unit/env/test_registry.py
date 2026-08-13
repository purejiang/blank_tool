"""Tests for cli/app/env/registry.py — EnvironmentRegistry."""

import json
import os

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
