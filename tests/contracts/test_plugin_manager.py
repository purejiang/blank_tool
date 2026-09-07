"""
Contract tests for PluginManager plugin discovery.

Regression: ``plugins_dir`` previously resolved to ``backend/plugins/``
(empty); the actual plugins live next to ``manager.py`` in
``backend/app/plugins/`` — so ``adb_auto`` was never loaded and every
``plugin.run {"name": "adb_auto"}`` failed with "插件未找到".
"""
import pytest

from app.plugins.manager import PluginManager


class TestPluginDiscovery:
    def test_plugins_dir_points_at_app_plugins(self):
        import os
        mgr = PluginManager.instance()
        expected = os.path.dirname(os.path.abspath(
            __import__("app.plugins.manager", fromlist=["PluginManager"]).__file__
        ))
        assert mgr.plugins_dir == expected
        # adb_auto.py actually sits there
        assert os.path.isfile(os.path.join(mgr.plugins_dir, "adb_auto.py"))

    def test_adb_auto_plugin_is_loaded(self):
        mgr = PluginManager.instance()
        plugin = mgr.get_plugin("adb_auto")
        assert plugin is not None, "adb_auto must be discoverable after the path fix"
        assert callable(getattr(plugin, "run", None))

    def test_framework_files_are_not_treated_as_plugins(self):
        mgr = PluginManager.instance()
        assert mgr.get_plugin("manager") is None
        assert mgr.get_plugin("context") is None

    def test_list_plugins_contains_adb_auto(self):
        names = [p["name"] for p in PluginManager.instance().get_all_plugins()]
        assert "adb_auto" in names

    def test_run_unknown_plugin_raises(self):
        mgr = PluginManager.instance()
        with pytest.raises(Exception, match="未找到"):
            mgr.run_plugin("__definitely_missing__", {})
