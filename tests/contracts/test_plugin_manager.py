"""
Contract tests for the plugin framework (post-automation-extraction).

World: plugins are EXTERNAL .py files for outside tools (jadx, scrapy, ...).
Builtin examples live in ``app/plugins/builtin/``; user plugins live in
``BT_PLUGINS_DIR`` (scanned FIRST, so same-name user plugins override
builtin ones). ``adb_auto`` is no longer a plugin — automation runs go
through the dedicated ``automation.run`` handler.
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
    def test_builtin_examples_are_loaded(self):
        mgr = PluginManager.instance()
        names = [p["name"] for p in mgr.get_all_plugins()]
        assert "hello" in names
        assert "jadx_decompile" in names

    def test_real_builtin_dir_has_examples(self):
        mgr = PluginManager.instance()
        assert os.path.isfile(os.path.join(mgr.builtin_dir, "hello.py"))

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
    def test_params_declared(self):
        mgr = PluginManager.instance()
        hello = [p for p in mgr.get_all_plugins() if p["name"] == "hello"][0]
        assert hello["description"]
        assert hello["version"]
        assert isinstance(hello.get("params"), list)
        keys = [p_["key"] for p_ in hello["params"]]
        assert "name" in keys

    def test_no_params_key_when_undeclared(self, isolated_mgr):
        _write_plugin(isolated_mgr.user_dir, "bare", '''
            def run(context, **params):
                return {}
        ''')
        isolated_mgr.load_plugins()
        bare = [p for p in isolated_mgr.get_all_plugins() if p["name"] == "bare"][0]
        assert "params" not in bare


class TestRun:
    def test_run_hello(self):
        mgr = PluginManager.instance()
        events = []
        result = mgr.run_plugin("hello", {"name": "contract"}, lambda e: events.append(e))
        assert result["message"] == "Hello, contract!"
        types = [e["type"] for e in events]
        assert "complete" in types
        # log payloads stay bare strings prefixed with the plugin name
        logs = [e["payload"] for e in events if e["type"] == "log"]
        assert all(isinstance(x, str) and x.startswith("[hello]") for x in logs)

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
