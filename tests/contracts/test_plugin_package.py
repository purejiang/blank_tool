"""
Contract tests for plugin package import/export (zip bundles).

Covers: manifest-at-root and folder-wrapped zips, zip-slip rejection,
overwrite confirmation flow, legacy flat .py export, and reload after
import.
"""
import io
import json
import os
import textwrap
import zipfile

import pytest

from app.plugins.manager import PluginManager
from app.handlers.plugin_package_handler import import_plugin, export_plugin


@pytest.fixture()
def isolated_mgr(tmp_path, monkeypatch):
    """A PluginManager scanned from tmp builtin/user dirs, fresh instance."""
    import app.plugins.manager as m

    user = tmp_path / "user"
    user.mkdir()
    monkeypatch.setenv("BT_PLUGINS_DIR", str(user))
    monkeypatch.setattr(m.PluginManager, "_instance", None)

    mgr = m.PluginManager()
    mgr.builtin_dir = str(tmp_path / "builtin")
    os.makedirs(mgr.builtin_dir, exist_ok=True)
    mgr.user_dir = str(user)
    mgr.load_plugins()
    yield mgr
    monkeypatch.setattr(m.PluginManager, "_instance", None)


def _make_zip(path, manifest, files=None, wrap_dir=None):
    """Build a plugin zip. ``wrap_dir`` puts everything under one folder."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        entry = wrap_dir or ""
        zf.writestr(entry + "manifest.json", json.dumps(manifest, ensure_ascii=False))
        zf.writestr(
            entry + manifest.get("entry", "main.py"),
            textwrap.dedent('''
                DESCRIPTION = "from module"
                def run(context, **params):
                    return {"ok": True}
            '''),
        )
        for name, content in (files or {}).items():
            zf.writestr(entry + name, content)
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return path


class TestImport:
    def test_import_root_manifest(self, isolated_mgr, tmp_path):
        zip_path = _make_zip(str(tmp_path / "p.zip"), {"id": "demo", "version": "1.2.3"})
        result = import_plugin({"zip_path": zip_path}, None)
        assert isinstance(result, list)
        demo = [p for p in result if p["name"] == "demo"][0]
        assert demo["version"] == "1.2.3"
        assert os.path.isfile(os.path.join(isolated_mgr.user_dir, "demo", "main.py"))
        # module attr from manifest, runnable
        assert isolated_mgr.get_plugin("demo").run.__name__ == "run"

    def test_import_exposes_manifest_display_name(self, isolated_mgr, tmp_path):
        """manifest.name 只是显示名，导入结果里以 display_name 出现，id 不变。"""
        zip_path = _make_zip(str(tmp_path / "p.zip"), {"id": "demo2", "name": "演示包"})
        result = import_plugin({"zip_path": zip_path}, None)
        demo = [p for p in result if p["name"] == "demo2"][0]
        assert demo["display_name"] == "演示包"
        assert demo["name"] == "demo2"

    def test_import_folder_wrapped(self, isolated_mgr, tmp_path):
        zip_path = _make_zip(
            str(tmp_path / "p.zip"),
            {"id": "wrapped", "version": "0.2.0", "description": "wrapped desc"},
            files={"ui/index.html": "<h1>hi</h1>"},
            wrap_dir="wrapped-1.0.0/",
        )
        result = import_plugin({"zip_path": zip_path}, None)
        assert "wrapped" in [p["name"] for p in result]
        assert os.path.isfile(
            os.path.join(isolated_mgr.user_dir, "wrapped", "ui", "index.html")
        )

    def test_import_needs_overwrite_then_overwrite(self, isolated_mgr, tmp_path):
        zip_path = _make_zip(str(tmp_path / "p.zip"), {"id": "dup"})
        import_plugin({"zip_path": zip_path}, None)
        marker = os.path.join(isolated_mgr.user_dir, "dup", "marker.txt")
        with open(marker, "w", encoding="utf-8") as f:
            f.write("old")
        first = import_plugin({"zip_path": zip_path}, None)
        assert first == {"needs_overwrite": True, "id": "dup"}
        second = import_plugin({"zip_path": zip_path, "overwrite": True}, None)
        assert isinstance(second, list)
        assert not os.path.exists(marker)  # old files wiped

    def test_import_rejects_zip_slip(self, isolated_mgr, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"id": "evil"}))
            zf.writestr("main.py", "def run(context, **params):\n    return {}\n")
            zf.writestr("../escape.py", "x = 1")
        zip_path = tmp_path / "evil.zip"
        zip_path.write_bytes(buf.getvalue())
        with pytest.raises(Exception, match="非法压缩包路径"):
            import_plugin({"zip_path": str(zip_path)}, None)
        assert not os.path.exists(os.path.join(isolated_mgr.user_dir, "..", "escape.py"))

    def test_import_rejects_missing_entry(self, isolated_mgr, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"id": "noentry", "entry": "gone.py"}))
        zip_path = tmp_path / "noentry.zip"
        zip_path.write_bytes(buf.getvalue())
        with pytest.raises(Exception, match="入口文件不存在"):
            import_plugin({"zip_path": str(zip_path)}, None)

    def test_import_rejects_bad_id(self, isolated_mgr, tmp_path):
        zip_path = _make_zip(str(tmp_path / "p.zip"), {"id": "../evil"})
        with pytest.raises(Exception, match="id"):
            import_plugin({"zip_path": zip_path}, None)

    def test_import_missing_zip_raises(self, isolated_mgr):
        with pytest.raises(Exception, match="压缩包不存在"):
            import_plugin({"zip_path": "Z:/no/such/file.zip"}, None)


class TestExport:
    def test_export_package_dir(self, isolated_mgr, tmp_path):
        _make_zip(str(tmp_path / "p.zip"),
                  {"id": "demo", "version": "1.0.0", "description": "d"},
                  files={"ui/index.html": "<b>x</b>"})
        import_plugin({"zip_path": str(tmp_path / "p.zip")}, None)
        out = str(tmp_path / "out.zip")
        res = export_plugin({"name": "demo", "target_path": out}, None)
        assert res["path"] == out
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            assert "manifest.json" in names and "main.py" in names
            assert "ui/index.html" in names

    def test_export_legacy_flat_py_gets_manifest(self, isolated_mgr, tmp_path):
        with open(os.path.join(isolated_mgr.user_dir, "flat.py"), "w", encoding="utf-8") as f:
            f.write(textwrap.dedent('''
                VERSION = "3.1.4"
                AUTHOR = "someone"
                def run(context, **params):
                    return {}
            '''))
        isolated_mgr.load_plugins()
        out = str(tmp_path / "flat_out.zip")
        export_plugin({"name": "flat", "target_path": out}, None)
        with zipfile.ZipFile(out) as zf:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            assert manifest["id"] == "flat"
            assert manifest["version"] == "3.1.4"
            assert zf.read("main.py").decode("utf-8").count("def run") == 1

    def test_export_unknown_plugin_raises(self, isolated_mgr, tmp_path):
        with pytest.raises(Exception, match="未找到"):
            export_plugin({"name": "ghost", "target_path": str(tmp_path / "x.zip")}, None)


class TestManagerPackageLoading:
    def test_directory_plugin_with_manifest(self, isolated_mgr):
        pkg = os.path.join(isolated_mgr.user_dir, "pkgdemo")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "pkgdemo", "version": "2.0.0", "author": "a",
                       "description": "pkg desc",
                       "params": [{"key": "x", "type": "number"}]}, f)
        with open(os.path.join(pkg, "main.py"), "w", encoding="utf-8") as f:
            f.write("def run(context, **params):\n    return {}\n")
        isolated_mgr.load_plugins()
        info = [p for p in isolated_mgr.get_all_plugins() if p["name"] == "pkgdemo"][0]
        assert info["version"] == "2.0.0"
        assert info["description"] == "pkg desc"
        assert info["params"] == [{"key": "x", "type": "number"}]
        assert isolated_mgr.plugin_paths["pkgdemo"] == pkg

    def test_ui_path_exposed_in_list(self, isolated_mgr):
        pkg = os.path.join(isolated_mgr.user_dir, "uiplug")
        ui_dir = os.path.join(pkg, "ui")
        os.makedirs(ui_dir)
        with open(os.path.join(pkg, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "uiplug", "ui": "ui/index.html"}, f)
        with open(os.path.join(pkg, "main.py"), "w", encoding="utf-8") as f:
            f.write("def run(context, **params):\n    return {}\n")
        with open(os.path.join(ui_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write("<h1>ui</h1>")
        isolated_mgr.load_plugins()
        info = [p for p in isolated_mgr.get_all_plugins() if p["name"] == "uiplug"][0]
        assert info["ui_path"] == os.path.join(pkg, "ui", "index.html")

    def test_dir_without_manifest_is_ignored(self, isolated_mgr):
        os.makedirs(os.path.join(isolated_mgr.user_dir, "just_a_folder"))
        isolated_mgr.load_plugins()  # must not raise
        assert isolated_mgr.get_plugin("just_a_folder") is None

    def test_manifest_name_is_display_only(self, isolated_mgr):
        """manifest.name 不进 sys.modules/查找键：只能用 id 寻址。"""
        pkg = os.path.join(isolated_mgr.user_dir, "named")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "named", "name": "漂亮名字", "entry": "main.py"}, f)
        with open(os.path.join(pkg, "main.py"), "w", encoding="utf-8") as f:
            f.write("def run(context, **params):\n    return {}\n")
        isolated_mgr.load_plugins()
        info = [p for p in isolated_mgr.get_all_plugins() if p["name"] == "named"][0]
        assert info["display_name"] == "漂亮名字"
        assert isolated_mgr.get_plugin("named") is not None
        assert isolated_mgr.get_plugin("漂亮名字") is None

    def test_module_attrs_win_over_manifest(self, isolated_mgr):
        pkg = os.path.join(isolated_mgr.user_dir, "both")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "both", "version": "1.0.0"}, f)
        with open(os.path.join(pkg, "main.py"), "w", encoding="utf-8") as f:
            f.write('VERSION = "9.9.9-module"\ndef run(context, **params):\n    return {}\n')
        isolated_mgr.load_plugins()
        assert isolated_mgr.get_plugin("both").VERSION == "9.9.9-module"
