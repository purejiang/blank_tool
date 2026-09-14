"""
Contract tests for the plugin framework (post-automation-extraction).

World: plugins are EXTERNAL .py files for outside tools (jadx, scrcpy, ...).
They live in the user plugin dir ``BT_PLUGINS_DIR`` (scanned FIRST) or in the
app-side ``app/plugins/builtin/`` dir, which now ships **empty** — no example
plugins are bundled. Same-name user plugins override builtin ones.
``adb_auto`` is no longer a plugin — automation runs go through the
dedicated ``automation.run`` handler.
"""
import os
import sys
import textwrap

import pytest

from app.plugins.manager import PluginManager


@pytest.fixture()
def isolated_mgr(tmp_path, monkeypatch):
    """A PluginManager scanned from tmp builtin/user dirs, fresh instance."""
    import importlib
    import app.plugins.manager as m

    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    builtin.mkdir()
    user.mkdir()
    monkeypatch.setenv("BT_PLUGINS_DIR", str(user))

    # rebuild the singleton with the tmp dirs
    m.PluginManager._instance = None
    mgr = m.PluginManager()
    mgr.builtin_dir = str(builtin)
    mgr.user_dir = str(user)
    mgr.load_plugins()
    yield mgr
    m.PluginManager._instance = None


def _write_plugin(directory, name, body):
    path = os.path.join(directory, f"{name}.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(body))
    return path


class TestDiscovery:
    def test_builtin_dir_ships_no_examples(self):
        """内建目录不带任何示例插件（只由 _ensure_dirs 建出空目录）。"""
        mgr = PluginManager.instance()
        assert os.path.isdir(mgr.builtin_dir)
        assert [f for f in os.listdir(mgr.builtin_dir) if f.endswith(".py")] == []

    def test_user_dir_discovered_after_reload(self, isolated_mgr):
        _write_plugin(isolated_mgr.user_dir, "my_tool", '''
            DESCRIPTION = "user plugin"
            def run(context, **params):
                return {"ok": True}
        ''')
        isolated_mgr.load_plugins()
        names = [p["name"] for p in isolated_mgr.get_all_plugins()]
        assert "my_tool" in names

    def test_user_overrides_builtin(self, isolated_mgr):
        _write_plugin(isolated_mgr.builtin_dir, "dup", '''
            VERSION = "0.0.1-builtin"
            def run(context, **params):
                return {}
        ''')
        _write_plugin(isolated_mgr.user_dir, "dup", '''
            VERSION = "9.9.9-user"
            def run(context, **params):
                return {}
        ''')
        isolated_mgr.load_plugins()
        dup = isolated_mgr.get_plugin("dup")
        assert dup.VERSION == "9.9.9-user"

    def test_framework_files_are_not_plugins(self):
        mgr = PluginManager.instance()
        assert mgr.get_plugin("manager") is None
        assert mgr.get_plugin("context") is None

    def test_broken_plugin_does_not_crash_load(self, isolated_mgr):
        _write_plugin(isolated_mgr.user_dir, "broken", '''
            import nonexistent_module_xyz  # noqa — import error at load time
        ''')
        _write_plugin(isolated_mgr.user_dir, "no_run_fn", '''
            DESCRIPTION = "has no run()"
        ''')
        isolated_mgr.load_plugins()  # must not raise
        assert isolated_mgr.get_plugin("broken") is None
        assert isolated_mgr.get_plugin("no_run_fn") is None


class TestMetadata:
    def test_params_declared(self, isolated_mgr):
        pkg = os.path.join(isolated_mgr.user_dir, "withparams")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "manifest.json"), "w", encoding="utf-8") as f:
            f.write('{"id": "withparams", "entry": "main.py", "version": "1.2.3", '
                    '"description": "demo", "params": [{"key": "apk_path", "type": "string"}]}')
        with open(os.path.join(pkg, "main.py"), "w", encoding="utf-8") as f:
            f.write("def run(context, **params):\n    return {}\n")
        isolated_mgr.load_plugins()
        info = [p for p in isolated_mgr.get_all_plugins() if p["name"] == "withparams"][0]
        assert info["description"] == "demo"
        assert info["version"] == "1.2.3"
        keys = [x["key"] for x in info["params"]]
        assert "apk_path" in keys

    def test_no_params_key_when_undeclared(self, isolated_mgr):
        _write_plugin(isolated_mgr.user_dir, "bare", '''
            def run(context, **params):
                return {}
        ''')
        isolated_mgr.load_plugins()
        bare = [p for p in isolated_mgr.get_all_plugins() if p["name"] == "bare"][0]
        assert "params" not in bare

    def test_display_name_defaults_to_id(self, isolated_mgr):
        """无 manifest.name：display_name 回退成 id（平铺 .py 与包目录都一样）。"""
        _write_plugin(isolated_mgr.user_dir, "flatname", '''
            def run(context, **params):
                return {}
        ''')
        pkg = os.path.join(isolated_mgr.user_dir, "pkgname")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "manifest.json"), "w", encoding="utf-8") as f:
            f.write('{"id": "pkgname", "entry": "main.py"}')
        with open(os.path.join(pkg, "main.py"), "w", encoding="utf-8") as f:
            f.write("def run(context, **params):\n    return {}\n")
        isolated_mgr.load_plugins()
        infos = {p["name"]: p for p in isolated_mgr.get_all_plugins()}
        assert infos["flatname"]["display_name"] == "flatname"
        assert infos["pkgname"]["display_name"] == "pkgname"


class TestRun:
    def test_run_emits_complete_and_prefixed_logs(self, isolated_mgr):
        """运行一个插件：返回 payload、发且只发一个 complete、日志是带前缀的裸字符串。"""
        _write_plugin(isolated_mgr.user_dir, "greeter", '''
            def run(context, who="world", **params):
                context.log(f"greeting {who}")
                return context.finish({"message": f"Hi, {who}!"})
        ''')
        isolated_mgr.load_plugins()
        events = []
        result = isolated_mgr.run_plugin("greeter", {"who": "contract"},
                                         lambda e: events.append(e))
        assert result["message"] == "Hi, contract!"
        types = [e["type"] for e in events]
        assert "complete" in types
        # log payloads stay bare strings prefixed with the plugin name
        logs = [e["payload"] for e in events if e["type"] == "log"]
        assert all(isinstance(x, str) and x.startswith("[greeter]") for x in logs)

    def test_run_unknown_plugin_raises(self):
        mgr = PluginManager.instance()
        with pytest.raises(Exception, match="未找到"):
            mgr.run_plugin("__definitely_missing__", {})

    def test_params_form_reaches_plugin(self, isolated_mgr):
        _write_plugin(isolated_mgr.user_dir, "echo", '''
            def run(context, value=0, **params):
                context.complete({"value": value})
                return {"value": value}
        ''')
        isolated_mgr.load_plugins()
        events = []
        result = isolated_mgr.run_plugin("echo", {"value": 41}, lambda e: events.append(e))
        assert result["value"] == 41
        types = [e["type"] for e in events]
        assert "complete" in types


class TestDelete:
    def test_delete_flat_user_plugin(self, isolated_mgr):
        _write_plugin(isolated_mgr.user_dir, "tmpdel", '''
            def run(context, **params):
                return {}
        ''')
        isolated_mgr.load_plugins()
        assert isolated_mgr.get_plugin("tmpdel") is not None

        remaining = isolated_mgr.delete_plugin("tmpdel")
        assert "tmpdel" not in [p["name"] for p in remaining]
        assert isolated_mgr.get_plugin("tmpdel") is None
        assert not os.path.exists(os.path.join(isolated_mgr.user_dir, "tmpdel.py"))

    def test_delete_package_dir(self, isolated_mgr):
        pkg = os.path.join(isolated_mgr.user_dir, "pkgdel")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "manifest.json"), "w", encoding="utf-8") as f:
            f.write('{"id": "pkgdel", "entry": "main.py"}')
        with open(os.path.join(pkg, "main.py"), "w", encoding="utf-8") as f:
            f.write("def run(context, **params):\n    return {}\n")
        isolated_mgr.load_plugins()
        assert isolated_mgr.get_plugin("pkgdel") is not None

        isolated_mgr.delete_plugin("pkgdel")
        assert isolated_mgr.get_plugin("pkgdel") is None
        assert not os.path.exists(pkg)

    def test_delete_builtin_plugin(self, isolated_mgr):
        _write_plugin(isolated_mgr.builtin_dir, "bdlt", '''
            def run(context, **params):
                return {}
        ''')
        isolated_mgr.load_plugins()
        bdlt = [p for p in isolated_mgr.get_all_plugins() if p["name"] == "bdlt"][0]
        assert bdlt["builtin"] is True

        isolated_mgr.delete_plugin("bdlt")
        assert isolated_mgr.get_plugin("bdlt") is None
        assert not os.path.exists(os.path.join(isolated_mgr.builtin_dir, "bdlt.py"))

    def test_delete_unknown_plugin_raises(self, isolated_mgr):
        with pytest.raises(Exception, match="未找到"):
            isolated_mgr.delete_plugin("__definitely_missing__")

    def test_builtin_flag_distinguishes_scan_roots(self, isolated_mgr):
        _write_plugin(isolated_mgr.user_dir, "userplug", '''
            def run(context, **params):
                return {}
        ''')
        _write_plugin(isolated_mgr.builtin_dir, "appplug", '''
            def run(context, **params):
                return {}
        ''')
        isolated_mgr.load_plugins()
        infos = {p["name"]: p for p in isolated_mgr.get_all_plugins()}
        assert infos["userplug"]["builtin"] is False
        assert infos["appplug"]["builtin"] is True
