"""Tests: ToolRegistry pack import (two-phase domain pack import).

Covers the bulk-import contract used by ``tool.import_pack`` and
``cli.py import-pack``:

- happy path: every descriptor in a directory is imported and reported
  ``added``; a second import of the same pack reports ``updated``;
- two-phase semantics: a single malformed descriptor aborts the whole
  import with ZERO writes (valid entries are reported ``skipped``);
- unusable inputs (missing dir, dir without *.json) raise ``ToolException``
  and write nothing (WP0 #7: no more top-level ``error`` payload);
- script-type descriptors keep the self-containment behavior (script file
  copied into ``<overlay>/scripts/<name>/``, path rewritten) — with relative
  ``path`` values resolved against the **pack directory**, not the CWD;
- non-blocking warnings: an unresolvable env dep does not fail the import
  but surfaces in the entry's ``warnings``;
- ``import_pack`` dispatch: directory / single ``*.json`` / ``*.zip``
  (descriptors in the archive root only, zip-slip members skipped).

Every test constructs the registry with an explicit ``registry_overlay_dir``
under ``tmp_path`` so no real overlay is touched.
"""

import json
import sys
import zipfile
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

    def test_missing_directory_raises(self, registry, tmp_path):
        from app.common.exceptions import ToolException

        with pytest.raises(ToolException, match="not a directory"):
            registry.import_descriptor_dir(str(tmp_path / "nope"))

    def test_directory_without_descriptors_raises(
        self, registry, pack_dir
    ):
        from app.common.exceptions import ToolException

        with pytest.raises(ToolException, match=r"no \*\.json"):
            registry.import_descriptor_dir(str(pack_dir))

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


class TestImportPackDispatch:
    """``import_pack`` takes a directory, a single ``*.json`` or a ``*.zip``."""

    @staticmethod
    def _script_pack(pack_dir, *, declared_path, script_rel):
        """Write a python_script descriptor + its script file under *pack_dir*."""
        script = pack_dir / script_rel
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("print('{}')\n", encoding="utf-8")
        _write_json(
            pack_dir,
            "scripty",
            _descriptor("scripty", type="python_script", path=declared_path),
        )
        return script

    def test_script_path_resolves_against_the_pack_dir(self, registry, pack_dir):
        """Regression: a pack-relative script path must reach the overlay.

        ``examples/tools/android/apk-audit.json`` declares
        ``apk-audit/apk_audit.py`` — relative to the pack it lives in.
        Resolving that against the backend's CWD (the old behavior) never
        matched, so the script was never copied and all five script-typed
        tools of that pack imported as ``is_valid: false``.
        """
        self._script_pack(
            pack_dir, declared_path="scripty/run.py", script_rel="scripty/run.py"
        )

        report = registry.import_pack(str(pack_dir))

        assert report["ok"] is True
        assert report["imported"] == 1
        tool = registry.get("scripty")
        assert tool.is_valid is True
        assert "scripts" in tool.tool_path
        assert Path(tool.tool_path).is_file()
        # Self-contained: the written overlay descriptor points at the copy.
        overlay_json = json.loads(
            (
                Path(registry._registry_overlay_dir) / "tools" / "scripty.json"
            ).read_text(encoding="utf-8")
        )
        assert overlay_json["path"] == tool.tool_path

    def test_basename_only_path_falls_back_to_the_pack_tree(
        self, registry, pack_dir
    ):
        """A bare ``run.py`` is matched when the pack keeps it in a subdir."""
        self._script_pack(
            pack_dir, declared_path="run.py", script_rel="scripty/run.py"
        )

        report = registry.import_pack(str(pack_dir))

        assert report["ok"] is True
        assert registry.get("scripty").is_valid is True

    def test_ambiguous_basename_is_not_guessed(self, registry, pack_dir):
        """Two same-named scripts: no copy, and the report explains why."""
        self._script_pack(pack_dir, declared_path="run.py", script_rel="a/run.py")
        other = pack_dir / "b"
        other.mkdir()
        (other / "run.py").write_text("print('{}')\n", encoding="utf-8")

        report = registry.import_pack(str(pack_dir))

        assert registry.get("scripty").is_valid is False
        assert any(
            "not found" in warning
            for warning in report["results"][0].get("warnings", [])
        )

    def test_single_descriptor_file_is_imported(self, registry, pack_dir):
        self._script_pack(pack_dir, declared_path="run.py", script_rel="run.py")

        report = registry.import_pack(str(pack_dir / "scripty.json"))

        assert report["ok"] is True
        assert report["imported"] == 1
        assert registry.get("scripty").is_valid is True

    def test_zip_with_root_descriptors_is_imported(self, registry, tmp_path):
        archive = tmp_path / "pack.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr(
                "scripty.json",
                json.dumps(
                    _descriptor(
                        "scripty", type="python_script", path="scripty/run.py"
                    )
                ),
            )
            zf.writestr("scripty/run.py", "print('{}')\n")
            zf.writestr("binary.json", json.dumps(_descriptor("binary")))

        report = registry.import_pack(str(archive))

        assert report["ok"] is True
        assert report["imported"] == 2
        tool = registry.get("scripty")
        assert tool.is_valid is True
        assert Path(tool.tool_path).is_file()

    def test_zip_with_a_wrapping_folder_is_rejected(self, registry, tmp_path):
        """Only the archive root is a pack — a single wrapper dir is not."""
        from app.common.exceptions import ToolException

        archive = tmp_path / "wrapped.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("android/adb.json", json.dumps(_descriptor("adb")))

        with pytest.raises(ToolException, match="at the root of"):
            registry.import_pack(str(archive))

    def test_unsafe_zip_members_are_skipped(self, registry, tmp_path):
        """Zip-slip: ``..`` / absolute members never land outside the root."""
        archive = tmp_path / "evil.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("ok.txt", "ok")
            zf.writestr("../escape.txt", "nope")
            zf.writestr("/abs.txt", "nope")

        dest = tmp_path / "out"
        dest.mkdir()
        registry._extract_zip(str(archive), str(dest))

        assert (dest / "ok.txt").read_text(encoding="utf-8") == "ok"
        assert not (tmp_path / "escape.txt").exists()

    def test_unsupported_extension_raises(self, registry, tmp_path):
        from app.common.exceptions import ToolException

        bad = tmp_path / "notes.txt"
        bad.write_text("nope", encoding="utf-8")

        with pytest.raises(ToolException, match="unsupported tool pack"):
            registry.import_pack(str(bad))

    def test_missing_path_raises(self, registry, tmp_path):
        from app.common.exceptions import ToolException

        with pytest.raises(ToolException, match="does not exist"):
            registry.import_pack(str(tmp_path / "nope"))
