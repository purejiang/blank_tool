"""Tests: ToolRegistry.import_descriptor_dir (two-phase domain pack import).

Covers the bulk-import contract used by ``tool.import_pack`` and
``cli.py import-pack``:

- happy path: every descriptor in a directory is imported and reported
  ``added``; a second import of the same pack reports ``updated``;
- two-phase semantics: a single malformed descriptor aborts the whole
  import with ZERO writes (valid entries are reported ``skipped``);
- unusable inputs (missing dir, dir without *.json) return a top-level
  ``error`` and write nothing;
- script-type descriptors keep the self-containment behavior (script file
  copied into ``<overlay>/scripts/<name>/``, path rewritten);
- non-blocking warnings: an unresolvable env dep does not fail the import
  but surfaces in the entry's ``warnings``.

Every test constructs the registry with an explicit ``registry_overlay_dir``
under ``tmp_path`` so no real overlay is touched.
"""

import json
import sys
from pathlib import Path

import pytest

from app.tools.tool_manager import ToolRegistry


def _descriptor(name, **overrides):
    """A minimal valid descriptor dict; sys.executable always exists."""
    base = {
        "name": name,
        "display_name": name,
        "type": "binary",
        "path": sys.executable,
        "env_deps": [],
        "validate": {},
        "version": {},
        "inputs": [],
        "outputs": [],
    }
    base.update(overrides)
    return base


def _write_json(dir_path: Path, name: str, data) -> Path:
    path = dir_path / f"{name}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def registry(tmp_path):
    return ToolRegistry(registry_overlay_dir=str(tmp_path / "registry"))


@pytest.fixture
def pack_dir(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    return pack


class TestImportDescriptorDir:
    def test_imports_every_descriptor_as_added(self, registry, pack_dir):
        _write_json(pack_dir, "alpha", _descriptor("alpha"))
        _write_json(pack_dir, "beta", _descriptor("beta"))

        report = registry.import_descriptor_dir(str(pack_dir))

        assert report["ok"] is True
        assert report["imported"] == 2
        assert report["updated"] == 0
        assert report["failed"] == 0
        by_name = {r["name"]: r for r in report["results"]}
        assert set(by_name) == {"alpha", "beta"}
        assert all(r["status"] == "added" for r in by_name.values())
        # Tools are resolvable from the registry after import.
        assert registry.get("alpha").name == "alpha"
        assert registry.get("beta").name == "beta"

    def test_reimport_reports_updated(self, registry, pack_dir):
        _write_json(pack_dir, "alpha", _descriptor("alpha"))
        first = registry.import_descriptor_dir(str(pack_dir))
        assert first["results"][0]["status"] == "added"

        second = registry.import_descriptor_dir(str(pack_dir))
        assert second["ok"] is True
        assert second["updated"] == 1
        assert second["results"][0]["status"] == "updated"

    def test_one_bad_descriptor_aborts_with_zero_writes(
        self, registry, pack_dir
    ):
        _write_json(pack_dir, "good", _descriptor("good"))
        _write_json(pack_dir, "bad", {"name": "bad"})  # missing fields

        report = registry.import_descriptor_dir(str(pack_dir))

        assert report["ok"] is False
        assert report["failed"] == 1
        by_name = {r["name"]: r for r in report["results"]}
        assert by_name["bad"]["status"] == "failed"
        assert "bad.json" in by_name["bad"]["reason"]
        assert by_name["good"]["status"] == "skipped"
        # Zero writes: no overlay descriptor was produced for anyone.
        overlay_tools = (
            Path(registry._registry_overlay_dir) / "tools"
        )
        assert not overlay_tools.exists() or not list(
            overlay_tools.glob("*.json")
        )

    def test_missing_directory_returns_error(self, registry, tmp_path):
        report = registry.import_descriptor_dir(str(tmp_path / "nope"))
        assert report["ok"] is False
        assert "error" in report
        assert report["results"] == []

    def test_directory_without_descriptors_returns_error(
        self, registry, pack_dir
    ):
        report = registry.import_descriptor_dir(str(pack_dir))
        assert report["ok"] is False
        assert "no *.json" in report["error"]

    def test_script_tool_is_self_contained_after_import(
        self, registry, pack_dir, tmp_path
    ):
        script = tmp_path / "hello.py"
        script.write_text("print('{}')\n", encoding="utf-8")
        _write_json(
            pack_dir,
            "scripty",
            _descriptor("scripty", type="python_script", path=str(script)),
        )

        report = registry.import_descriptor_dir(str(pack_dir))

        assert report["ok"] is True
        tool = registry.get("scripty")
        # The descriptor path was rewritten into the overlay scripts dir,
        # and the copied script file actually exists there.
        assert "scripts" in tool.tool_path
        assert Path(tool.tool_path).is_file()
        assert Path(tool.tool_path).read_text(encoding="utf-8") == "print('{}')\n"

    def test_unresolved_env_dep_warns_but_does_not_fail(
        self, registry, pack_dir
    ):
        _write_json(
            pack_dir,
            "needy",
            _descriptor("needy", env_deps=["definitely_missing_env"]),
        )

        report = registry.import_descriptor_dir(str(pack_dir))

        assert report["ok"] is True
        entry = report["results"][0]
        assert entry["status"] == "added"
        assert any(
            "definitely_missing_env" in warning
            for warning in entry.get("warnings", [])
        )
