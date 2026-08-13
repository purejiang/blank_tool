"""
Contract tests for Environment handler API methods (T15).

Tests the env.list / env.add / env.delete / env.set_custom / env.reset_custom
handlers.  Uses temporary overlay directories and a real EnvironmentRegistry
so descriptor writes and re-discovery are exercised end-to-end.
"""

import json
import os
from pathlib import Path

import pytest

from app.env.overrides_store import OverridesStore


# ---------------------------------------------------------------------------
# Descriptor helpers
# ---------------------------------------------------------------------------

def _make_env_descriptor_dict(
    name: str,
    *,
    binary: str = "",
    display_name: str = "",
    env_type: str = "custom",
    version_cmd: list = None,
    version_regex: str = "",
    search_paths: list = None,
) -> dict:
    """Minimal valid environment descriptor dict."""
    return {
        "name": name,
        "display_name": display_name or f"{name}-display",
        "type": env_type,
        "binary": binary or f"{name}.exe",
        "version_cmd": version_cmd or [],
        "version_regex": version_regex,
        "search_paths": search_paths or [],
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_registry_root(tmp_path: Path) -> str:
    """Create a temp output-dir-like registry root with environments/ subdir."""
    root = tmp_path / "registry"
    env_dir = root / "environments"
    env_dir.mkdir(parents=True)
    return str(root)


@pytest.fixture
def env_registry(temp_registry_root: str):
    """Return an EnvironmentRegistry with overlay wired to the temp root."""
    from app.env.registry import EnvironmentRegistry
    registry = EnvironmentRegistry(overlay_dir=temp_registry_root)
    # Discover with bundled descriptor_dir pointing at the real bundled dir
    # so the 3 core envs (java/python/node) are always present.
    from pathlib import Path as _Path
    bundled = _Path(__file__).resolve().parent.parent.parent / "cli" / "registry" / "environments"
    registry.discover(descriptor_dir=str(bundled), overlay_descriptor_dir=temp_registry_root)
    return registry


# ---------------------------------------------------------------------------
# env.list
# ---------------------------------------------------------------------------

class TestEnvList:
    def test_returns_bundled_envs(self, env_registry, monkeypatch):
        """env.list returns at least the 3 bundled environments (java, python, node)."""
        from app.handlers import env_handler
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)

        result = env_handler.handle_env_list({}, None)
        assert "environments" in result
        envs = result["environments"]
        names = {e["name"] for e in envs}
        assert names >= {"java", "python", "node"}, (
            f"Expected java/python/node in env list, got: {names}"
        )


# ---------------------------------------------------------------------------
# env.add
# ---------------------------------------------------------------------------

class TestEnvAdd:
    def test_add_valid_descriptor_succeeds_and_appears_in_list(
        self, env_registry, temp_registry_root, monkeypatch,
    ):
        """Given a valid env descriptor, env.add writes it to the overlay,
        and env.list immediately reflects the new env."""
        from app.handlers import env_handler
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)
        monkeypatch.setattr(env_handler, "OverridesStore", lambda: OverridesStore(root_dir=temp_registry_root))

        desc = _make_env_descriptor_dict(
            "my_custom_env", binary="mybin.exe",
            version_cmd=["--version"], version_regex=r"(\d+\.\d+)",
        )

        result = env_handler.handle_env_add({"descriptor": desc}, None)

        # Should return success with the env name
        assert isinstance(result, dict)
        assert result.get("name") == "my_custom_env", f"Unexpected result: {result}"

        # Descriptor file written to overlay
        overlay_file = Path(temp_registry_root) / "environments" / "my_custom_env.json"
        assert overlay_file.exists(), f"Expected overlay file at {overlay_file}"

        # Re-discovery happened — env appears in list
        listed = env_handler.handle_env_list({}, None)
        env_names = {e["name"] for e in listed["environments"]}
        assert "my_custom_env" in env_names

    def test_add_invalid_descriptor_returns_error_no_file_written(
        self, env_registry, temp_registry_root, monkeypatch,
    ):
        """Given invalid descriptor JSON (missing required fields), env.add
        returns an error and writes NO partial file."""
        from app.handlers import env_handler
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)
        monkeypatch.setattr(env_handler, "OverridesStore", lambda: OverridesStore(root_dir=temp_registry_root))

        # Missing 'name' — will fail validation
        bad_desc = {"display_name": "NoName", "type": "custom"}

        result = env_handler.handle_env_add({"descriptor": bad_desc}, None)

        assert "error" in result, f"Expected error in result, got: {result}"

        # No file should have been written (the overlay environments dir
        # should only contain files from previous successful tests, if any)
        overlay_env_dir = Path(temp_registry_root) / "environments"
        for f in overlay_env_dir.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            # The descriptor name should not exist
            assert data.get("name") != "", (
                f"Unexpected file written: {f.name} with content {data}"
            )


# ---------------------------------------------------------------------------
# env.delete
# ---------------------------------------------------------------------------

class TestEnvDelete:
    def test_delete_overlay_env_removes_it(
        self, env_registry, temp_registry_root, monkeypatch,
    ):
        """Given an overlay env was added, env.delete removes it and
        env.list no longer shows it."""
        from app.handlers import env_handler
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)
        monkeypatch.setattr(env_handler, "OverridesStore", lambda: OverridesStore(root_dir=temp_registry_root))

        # Add first
        desc = _make_env_descriptor_dict("to_delete", binary="del.exe")
        env_handler.handle_env_add({"descriptor": desc}, None)

        # Confirm it's in the list
        before = env_handler.handle_env_list({}, None)
        assert "to_delete" in {e["name"] for e in before["environments"]}

        # Delete
        result = env_handler.handle_env_delete({"name": "to_delete"}, None)
        assert "error" not in result, f"Delete should succeed, got: {result}"

        # No longer in list
        after = env_handler.handle_env_list({}, None)
        assert "to_delete" not in {e["name"] for e in after["environments"]}

        # Overlay file is removed
        overlay_file = Path(temp_registry_root) / "environments" / "to_delete.json"
        assert not overlay_file.exists()

    def test_delete_bundled_env_is_refused(
        self, env_registry, temp_registry_root, monkeypatch,
    ):
        """Deleting a bundled (non-overlay) env like 'java' must return an error."""
        from app.handlers import env_handler
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)
        monkeypatch.setattr(env_handler, "OverridesStore", lambda: OverridesStore(root_dir=temp_registry_root))

        result = env_handler.handle_env_delete({"name": "java"}, None)
        assert "error" in result, (
            f"Expected error when deleting bundled env, got: {result}"
        )
        assert "bundled" in str(result).lower() or "protected" in str(result).lower(), (
            f"Error should mention 'bundled' or 'protected', got: {result}"
        )


# ---------------------------------------------------------------------------
# env.set_custom / env.reset_custom
# ---------------------------------------------------------------------------

class TestEnvOverrides:
    def test_set_custom_persists_and_is_readable(
        self, env_registry, temp_registry_root, monkeypatch,
    ):
        """env.set_custom persists an override that survives a re-read."""
        from app.handlers import env_handler
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)
        monkeypatch.setattr(env_handler, "OverridesStore", lambda: OverridesStore(root_dir=temp_registry_root))

        overrides = {"env_var": "MY_VAR", "path": "/custom/path"}
        result = env_handler.handle_env_set_custom(
            {"name": "python", "overrides": overrides}, None,
        )
        assert "error" not in result, f"set_custom should succeed, got: {result}"

        # Verify the overrides.json has the entry
        overrides_file = Path(temp_registry_root) / "overrides.json"
        assert overrides_file.exists()
        data = json.loads(overrides_file.read_text(encoding="utf-8"))
        env_overrides = data.get("env_overrides", {})
        assert "python" in env_overrides
        assert env_overrides["python"]["env_var"] == "MY_VAR"

    def test_reset_custom_removes_override(
        self, env_registry, temp_registry_root, monkeypatch,
    ):
        """env.reset_custom removes a previously set override."""
        from app.handlers import env_handler
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)
        monkeypatch.setattr(env_handler, "OverridesStore", lambda: OverridesStore(root_dir=temp_registry_root))

        # Set first
        env_handler.handle_env_set_custom(
            {"name": "python", "overrides": {"path": "/tmp"}}, None,
        )

        # Reset
        result = env_handler.handle_env_reset_custom({"name": "python"}, None)
        assert "error" not in result, f"reset_custom should succeed, got: {result}"

        # Verify overrides.json no longer has the entry
        overrides_file = Path(temp_registry_root) / "overrides.json"
        data = json.loads(overrides_file.read_text(encoding="utf-8"))
        env_overrides = data.get("env_overrides", {})
        assert "python" not in env_overrides
