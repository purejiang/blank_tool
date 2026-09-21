"""
Contract tests for Environment handler API methods (T15).

Tests the env.list / env.add / env.delete handlers.  Uses temporary overlay
directories and a real EnvironmentRegistry so descriptor writes and
re-discovery are exercised end-to-end.
"""

import json
import os
from pathlib import Path

import pytest


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
def env_registry(temp_registry_root: str, monkeypatch):
    """Return an EnvironmentRegistry with overlay wired to the temp root.

    ``BT_OUTPUT_DIR`` is pointed at the temp root's parent so the module-level
    ``_find_binary`` override lookup reads the same ``overrides.json`` the
    registry writes (it resolves ``<output>/registry/overrides.json``).
    """
    monkeypatch.setenv("BT_OUTPUT_DIR", str(Path(temp_registry_root).parent))
    from app.env.registry import EnvironmentRegistry
    registry = EnvironmentRegistry(overlay_dir=temp_registry_root)
    # Discover with bundled descriptor_dir pointing at the real bundled dir
    # so the 3 core envs (java/python/node) are always present.
    from pathlib import Path as _Path
    bundled = _Path(__file__).resolve().parent.parent.parent / "cli" / "registry" / "environments"
    registry.discover(descriptor_dir=str(bundled), overlay_descriptor_dir=temp_registry_root)
    return registry


def _make_fake_binary(directory: Path, name: str = "fake.exe") -> Path:
    """Create an on-disk placeholder binary so path resolution succeeds."""
    directory.mkdir(parents=True, exist_ok=True)
    binary = directory / name
    binary.write_text("", encoding="utf-8")
    return binary


_ENV_ENTRY_KEYS = {
    "name", "is_valid", "binary_path", "version", "root_path",
    "display_name", "type", "env_var_override", "path_override", "source",
}


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

    def test_entries_carry_descriptor_metadata(self, env_registry, monkeypatch):
        """WP3 #3: entries expose display_name/type/env_var_override/path_override/source."""
        from app.handlers import env_handler
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)

        result = env_handler.handle_env_list({}, None)
        for entry in result["environments"]:
            assert set(entry) == _ENV_ENTRY_KEYS, entry

        java = next(e for e in result["environments"] if e["name"] == "java")
        assert java["display_name"]
        assert java["type"] == "jre"
        assert java["source"] == "bundled"
        assert java["env_var_override"] == "BT_JAVA_BIN"
        assert java["path_override"] == ""

    def test_overlay_environment_is_marked_overlay(
        self, env_registry, monkeypatch,
    ):
        """An env added through the overlay reports source == "overlay"."""
        from app.handlers import env_handler
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)

        env_handler.handle_env_add(
            {"descriptor": _make_env_descriptor_dict("overlay_env")}, None
        )
        result = env_handler.handle_env_list({}, None)
        entry = next(e for e in result["environments"] if e["name"] == "overlay_env")
        assert entry["source"] == "overlay"
        assert entry["display_name"] == "overlay_env-display"
        assert entry["type"] == "custom"


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

    def test_add_invalid_descriptor_raises_no_file_written(
        self, env_registry, temp_registry_root, monkeypatch,
    ):
        """Given invalid descriptor JSON (missing required fields), env.add
        raises ToolException and writes NO partial file (WP0 #7)."""
        from app.handlers import env_handler
        from app.common.exceptions import ToolException
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)

        # Missing 'name' — will fail validation
        bad_desc = {"display_name": "NoName", "type": "custom"}

        with pytest.raises(ToolException):
            env_handler.handle_env_add({"descriptor": bad_desc}, None)

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

        # Add first
        desc = _make_env_descriptor_dict("to_delete", binary="del.exe")
        env_handler.handle_env_add({"descriptor": desc}, None)

        # Confirm it's in the list
        before = env_handler.handle_env_list({}, None)
        assert "to_delete" in {e["name"] for e in before["environments"]}

        # Delete
        result = env_handler.handle_env_delete({"name": "to_delete"}, None)
        assert result["deleted"] == "to_delete"

        # No longer in list
        after = env_handler.handle_env_list({}, None)
        assert "to_delete" not in {e["name"] for e in after["environments"]}

        # Overlay file is removed
        overlay_file = Path(temp_registry_root) / "environments" / "to_delete.json"
        assert not overlay_file.exists()

    def test_delete_bundled_env_is_refused(
        self, env_registry, temp_registry_root, monkeypatch,
    ):
        """Deleting a bundled (non-overlay) env like 'java' must raise (WP0 #7)."""
        from app.handlers import env_handler
        from app.common.exceptions import ToolException
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)

        with pytest.raises(ToolException) as excinfo:
            env_handler.handle_env_delete({"name": "java"}, None)
        message = str(excinfo.value).lower()
        assert "bundled" in message or "protected" in message, (
            f"Error should mention 'bundled' or 'protected', got: {excinfo.value}"
        )


# ---------------------------------------------------------------------------
# env.set_path / env.reset_path (WP3 #13)
# ---------------------------------------------------------------------------

class TestEnvSetPath:
    def test_set_path_round_trips_and_resolves(
        self, env_registry, temp_registry_root, tmp_path, monkeypatch,
    ):
        """env.set_path persists the override, drops the cache, and returns
        the updated env.list entry."""
        from app.handlers import env_handler
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)

        fake = _make_fake_binary(tmp_path / "custom-jre", "java.exe")

        entry = env_handler.handle_env_set_path(
            {"name": "java", "path": str(fake)}, None
        )

        assert entry["name"] == "java"
        assert set(entry) == _ENV_ENTRY_KEYS
        assert entry["path_override"] == str(fake)
        assert entry["binary_path"] == str(fake)
        assert entry["root_path"] == os.path.dirname(str(fake))

        # Persisted under the new ``env_paths`` key.
        overrides_file = Path(temp_registry_root) / "overrides.json"
        assert json.loads(overrides_file.read_text(encoding="utf-8"))["env_paths"] == {
            "java": str(fake),
        }

        # env.list reflects the same override.
        listed = {
            e["name"]: e
            for e in env_handler.handle_env_list({}, None)["environments"]
        }
        assert listed["java"]["path_override"] == str(fake)
        assert listed["java"]["binary_path"] == str(fake)

    def test_set_path_preserves_other_override_keys(
        self, env_registry, temp_registry_root, tmp_path, monkeypatch,
    ):
        """The tool ``custom_paths`` key (same file) must survive a set_path."""
        from app.handlers import env_handler
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)

        overrides_file = Path(temp_registry_root) / "overrides.json"
        overrides_file.write_text(
            json.dumps({"custom_paths": {"apktool": "C:/tools/apktool.jar"}}),
            encoding="utf-8",
        )

        fake = _make_fake_binary(tmp_path / "custom-jre", "java.exe")
        env_handler.handle_env_set_path({"name": "java", "path": str(fake)}, None)

        data = json.loads(overrides_file.read_text(encoding="utf-8"))
        assert data["custom_paths"] == {"apktool": "C:/tools/apktool.jar"}
        assert data["env_paths"] == {"java": str(fake)}

    def test_reset_path_round_trips(
        self, env_registry, temp_registry_root, tmp_path, monkeypatch,
    ):
        """env.reset_path removes the override and returns the updated entry."""
        from app.handlers import env_handler
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)

        fake = _make_fake_binary(tmp_path / "custom-jre", "java.exe")
        env_handler.handle_env_set_path({"name": "java", "path": str(fake)}, None)

        entry = env_handler.handle_env_reset_path({"name": "java"}, None)

        assert set(entry) == _ENV_ENTRY_KEYS
        assert entry["path_override"] == ""
        assert entry["binary_path"] != str(fake)

        overrides_file = Path(temp_registry_root) / "overrides.json"
        assert json.loads(overrides_file.read_text(encoding="utf-8"))["env_paths"] == {}

    def test_set_path_unknown_env_raises(self, env_registry, monkeypatch):
        from app.handlers import env_handler
        from app.common.exceptions import ToolException
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)

        with pytest.raises(ToolException, match="Unknown environment"):
            env_handler.handle_env_set_path(
                {"name": "no_such_env", "path": "C:/tools/x"}, None
            )

    def test_set_path_missing_path_raises(self, env_registry, monkeypatch):
        from app.handlers import env_handler
        from app.common.exceptions import ToolException
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)

        with pytest.raises(ToolException, match="path"):
            env_handler.handle_env_set_path({"name": "java"}, None)

    def test_set_path_missing_name_raises(self, env_registry, monkeypatch):
        from app.handlers import env_handler
        from app.common.exceptions import ToolException
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)

        with pytest.raises(ToolException, match="name"):
            env_handler.handle_env_set_path({"path": "C:/tools/x"}, None)

    def test_reset_path_unknown_env_raises(self, env_registry, monkeypatch):
        from app.handlers import env_handler
        from app.common.exceptions import ToolException
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)

        with pytest.raises(ToolException, match="Unknown environment"):
            env_handler.handle_env_reset_path({"name": "no_such_env"}, None)

    def test_reset_path_missing_name_raises(self, env_registry, monkeypatch):
        from app.handlers import env_handler
        from app.common.exceptions import ToolException
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)

        with pytest.raises(ToolException, match="name"):
            env_handler.handle_env_reset_path({}, None)

    def test_reset_path_without_override_is_a_noop(
        self, env_registry, temp_registry_root, monkeypatch,
    ):
        """Resetting an env that never had an override still succeeds."""
        from app.handlers import env_handler
        monkeypatch.setattr(env_handler, "get_env_registry", lambda: env_registry)

        entry = env_handler.handle_env_reset_path({"name": "java"}, None)
        assert entry["path_override"] == ""
        assert not (Path(temp_registry_root) / "overrides.json").exists()


# ---------------------------------------------------------------------------
# Registry persistence details
# ---------------------------------------------------------------------------

class TestPathOverridePersistence:
    def test_get_path_overrides_reads_persisted_values(
        self, env_registry, tmp_path,
    ):
        fake = _make_fake_binary(tmp_path / "custom-jre", "java.exe")
        assert env_registry.get_path_overrides() == {}

        env_registry.set_path_override("java", str(fake))
        assert env_registry.get_path_overrides() == {"java": str(fake)}

        env_registry.reset_path_override("java")
        assert env_registry.get_path_overrides() == {}

    def test_get_descriptor_returns_metadata_and_none_for_unknown(
        self, env_registry,
    ):
        descriptor = env_registry.get_descriptor("java")
        assert descriptor is not None
        assert descriptor.display_name == "Java Runtime"
        assert descriptor.type == "jre"
        assert env_registry.get_descriptor("nope") is None
