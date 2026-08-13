"""Tests for writable registry overlay dirs + persistence (T14).

T14 of the workflow-tool-env-management plan: ToolRegistry and
EnvironmentRegistry gain writable overlay directories under
<output_dir>/registry/ plus overrides.json persistence for custom
tool paths and env overrides.  Bundled directories stay read-only;
overlay wins by name.

Test strategy (Given/When/Then per test):
  (a) overlay tool descriptor discovered; overlay wins over bundled by name
  (b) set_custom_path persists to overrides.json and survives reload
  (c) malformed overlay descriptor file skipped with warning, not fatal
  (d) overlay env descriptor merges over bundled env
  (bonus) reset_custom_path removes entry from overrides.json
"""

import json
import logging
from pathlib import Path

import pytest


# ── Descriptor helpers ────────────────────────────────────────────────

def _make_tool_descriptor(
    name: str,
    display_name: str = "",
    *,
    tool_type: str = "binary",
    tool_path: str = "/fake/path",
) -> dict:
    """Create a minimal valid tool descriptor dict for JSON serialisation."""
    return {
        "name": name,
        "display_name": display_name or f"{name}-display",
        "type": tool_type,
        "path": tool_path,
        "env_deps": [],
        "validate": {},
        "version": {},
        "inputs": [],
        "outputs": [],
    }


def _make_env_descriptor(
    name: str,
    binary: str = "",
    *,
    env_var_override: str = "",
    search_paths: list | None = None,
    version_cmd: list | None = None,
    version_regex: str = "",
) -> dict:
    """Create a minimal valid environment descriptor dict for JSON serialisation."""
    return {
        "name": name,
        "display_name": f"{name}-display",
        "type": "custom",
        "binary": binary or f"{name}.exe",
        "env_var_override": env_var_override,
        "search_paths": search_paths or [],
        "version_cmd": version_cmd or [],
        "version_regex": version_regex,
    }


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def bundled_env_dir(tmp_path: Path) -> Path:
    """A bundled environments directory with one descriptor."""
    d = tmp_path / "bundled" / "environments"
    d.mkdir(parents=True)
    desc = _make_env_descriptor(
        "myenv", binary="bundled.exe",
        version_cmd=["--version"], version_regex=r"(\d+\.\d+)",
    )
    (d / "myenv.json").write_text(json.dumps(desc), encoding="utf-8")
    return d


# ═════════════════════════════════════════════════════════════════════
# (a) Overlay tool descriptor merges over bundled (overlay wins by name)
# ═════════════════════════════════════════════════════════════════════

def test_overlay_tool_descriptor_wins_over_bundled_by_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Given a bundled tool descriptor and an overlay descriptor with the
    same name but different fields, discovery loads the overlay version."""
    from app.tools.tool_manager import ToolRegistry

    # Arrange — bundled fixture: write into a temp dir that we'll redirect to
    bundled = tmp_path / "bundled" / "tools"
    bundled.mkdir(parents=True)
    bundled_desc = _make_tool_descriptor(
        "mytool", display_name="Bundled MyTool", tool_path="/bundled/path"
    )
    (bundled / "mytool.json").write_text(json.dumps(bundled_desc), encoding="utf-8")

    overlay_root = tmp_path / "overlay-root"
    overlay_tools = overlay_root / "tools"
    overlay_tools.mkdir(parents=True)
    overlay_desc = _make_tool_descriptor(
        "mytool", display_name="Overlay MyTool", tool_path="/overlay/path"
    )
    (overlay_tools / "mytool.json").write_text(json.dumps(overlay_desc), encoding="utf-8")

    # Monkey-patch Path.resolve so the bundled-dir resolution inside
    # _discover_descriptors points at our fixture.  The method computes:
    #   Path(__file__).resolve().parent.parent.parent / "registry" / "tools"
    # We need that to resolve to `bundled`.
    #
    # bundled = tmp_path/bundled/tools
    # We want Path().resolve().parent.parent.parent = tmp_path/bundled
    # So .parent.parent.parent.parent = tmp_path
    # So resolve() must return tmp_path/bundled/tools/dummy/dummy/dummy/tool_manager.py
    import pathlib

    original_resolve = pathlib.Path.resolve

    def _patched_resolve(self: pathlib.Path) -> pathlib.Path:
        result = original_resolve(self)
        name = getattr(self, "name", "")
        if name == "tool_manager.py" and "app" in str(self):
            # Redirect: parent → parent → parent = bundled → thus:
            # 4 levels up from tool_manager.py = bundled's parent → tmp_path/bundled
            return tmp_path / "bundled" / "d1" / "d2" / "d3" / "tool_manager.py"
        return result

    monkeypatch.setattr(pathlib.Path, "resolve", _patched_resolve, raising=False)

    registry = ToolRegistry(registry_overlay_dir=str(overlay_root))

    # Act
    registry.discover()

    # Then — overlay version wins (display_name + path from overlay)
    assert "mytool" in registry._descriptor_tools  # noqa: SLF001
    tool = registry._descriptor_tools["mytool"]  # noqa: SLF001
    # tool_path is resolved from the descriptor path "/overlay/path"
    # On Windows it's \overlay\path, on POSIX /overlay/path
    assert "overlay" in Path(tool.tool_path).parts, (
        f"Expected overlay in tool_path parts, got {tool.tool_path}"
    )


# ═════════════════════════════════════════════════════════════════════
# (b) set_custom_path survives registry reload via overrides.json
# ═════════════════════════════════════════════════════════════════════

def test_set_custom_path_persists_and_survives_reload(
    tmp_path: Path,
) -> None:
    """Given a tool registry with an overlay dir, setting a custom path
    writes overrides.json, and a fresh registry loads the persisted path."""
    from app.tools.tool_manager import ToolRegistry

    overlay_root = tmp_path / "overlay-root"
    overlay_root.mkdir(parents=True)

    # Arrange — first registry instance
    registry1 = ToolRegistry(registry_overlay_dir=str(overlay_root))
    # Inject a fake discovered class so get() works for custom-path resolution
    registry1._discovered["testtool"] = type(  # noqa: SLF001
        "FakeTool", (), {
            "__init__": lambda self, name, path, search_system: (
                setattr(self, "name", name)
                or setattr(self, "tool_path", path)
                or setattr(self, "is_valid", True)
                or setattr(self, "version", "1.0")
                or None
            ),
        },
    )

    # Act — set custom path
    result = registry1.set_custom_path("testtool", "/custom/path/to/testtool")
    assert result["path"] == "/custom/path/to/testtool"

    # Then — overrides.json was written
    overrides_file = overlay_root / "overrides.json"
    assert overrides_file.exists()
    data = json.loads(overrides_file.read_text(encoding="utf-8"))
    assert data.get("custom_paths", {}).get("testtool") == "/custom/path/to/testtool"

    # Arrange — second registry instance (same overlay dir)
    registry2 = ToolRegistry(registry_overlay_dir=str(overlay_root))

    # Then — custom path is loaded from overrides.json
    custom_paths = registry2.get_custom_paths()
    assert custom_paths.get("testtool") == "/custom/path/to/testtool"


# ═════════════════════════════════════════════════════════════════════
# (c) Malformed overlay descriptor file SKIPPED with warning, not fatal
# ═════════════════════════════════════════════════════════════════════

def test_malformed_overlay_descriptor_skipped_not_fatal(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Given an overlay dir with a broken JSON file and a valid one,
    discovery skips the broken file with a warning and loads the valid one."""
    from app.tools.tool_manager import ToolRegistry

    overlay_root = tmp_path / "overlay-root"
    overlay_tools = overlay_root / "tools"
    overlay_tools.mkdir(parents=True)

    # Arrange — broken + valid descriptors
    (overlay_tools / "broken.json").write_text("{not valid json", encoding="utf-8")
    valid_desc = _make_tool_descriptor("goodtool", tool_path="/good/path")
    (overlay_tools / "goodtool.json").write_text(json.dumps(valid_desc), encoding="utf-8")

    registry = ToolRegistry(registry_overlay_dir=str(overlay_root))

    # Act — discover; must not raise
    with caplog.at_level(logging.WARNING):
        registry.discover()

    # Then — broken file logged as warning
    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        "broken.json" in w or "skipping malformed" in w for w in warnings
    ), f"Expected warning about broken.json, got: {warnings}"

    # Then — valid file was loaded
    assert "goodtool" in registry._descriptor_tools  # noqa: SLF001


# ═════════════════════════════════════════════════════════════════════
# (d) Overlay env descriptor merges over bundled env
# ═════════════════════════════════════════════════════════════════════

def test_overlay_env_descriptor_wins_over_bundled(
    bundled_env_dir: Path, tmp_path: Path,
) -> None:
    """Given a bundled env descriptor and an overlay descriptor with the
    same name but different binary, discovery loads the overlay version."""
    from app.env.registry import EnvironmentRegistry

    # Arrange — write a conflicting overlay env descriptor
    overlay_envs = tmp_path / "overlay" / "environments"
    overlay_envs.mkdir(parents=True)
    overlay_desc = _make_env_descriptor(
        "myenv", binary="overlay.exe",
        version_cmd=["--version"], version_regex=r"(\d+\.\d+)",
    )
    (overlay_envs / "myenv.json").write_text(json.dumps(overlay_desc), encoding="utf-8")

    registry = EnvironmentRegistry()

    # Act — discover with both bundled and overlay dirs
    registry.discover(
        descriptor_dir=str(bundled_env_dir),
        overlay_descriptor_dir=str(overlay_envs),
    )

    # Then — the descriptor's binary should be the overlay one ("late-load wins")
    desc = registry._descriptors.get("myenv")
    assert desc is not None
    assert desc.binary == "overlay.exe"


# ═════════════════════════════════════════════════════════════════════
# (bonus) reset_custom_path removes from overrides.json
# ═════════════════════════════════════════════════════════════════════

def test_reset_custom_path_removes_from_overrides(
    tmp_path: Path,
) -> None:
    """Given a persisted custom path, reset removes it from overrides.json."""
    from app.tools.tool_manager import ToolRegistry

    overlay_root = tmp_path / "overlay-root"
    overlay_root.mkdir(parents=True)

    # Arrange — set a custom path that persists
    registry1 = ToolRegistry(registry_overlay_dir=str(overlay_root))
    registry1._discovered["testtool"] = type(  # noqa: SLF001
        "FakeTool", (), {
            "__init__": lambda self, name, path, search_system: (
                setattr(self, "name", name)
                or setattr(self, "tool_path", path)
                or setattr(self, "is_valid", True)
                or setattr(self, "version", "1.0")
                or None
            ),
        },
    )
    registry1.set_custom_path("testtool", "/custom/path")

    # Act — reset
    registry1.reset_custom_path("testtool")

    # Then — overrides.json no longer has the entry
    overrides_file = overlay_root / "overrides.json"
    data = json.loads(overrides_file.read_text(encoding="utf-8"))
    assert "testtool" not in data.get("custom_paths", {})

    # Then — fresh registry also has no custom path
    registry2 = ToolRegistry(registry_overlay_dir=str(overlay_root))
    assert "testtool" not in registry2.get_custom_paths()
