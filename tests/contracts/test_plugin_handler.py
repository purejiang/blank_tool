"""
Contract tests for the plugin handler (plugin.list / plugin.reload).
"""
import json
import logging

import pytest

from app.handlers import plugin_handler
from app.plugins import loader
from app.plugins.context import PluginContext


def _write_module(tmp_path, name, body):
    """Write a single-file module ``name``.py under tmp_path."""
    (tmp_path / f"{name}.py").write_text(body, encoding="utf-8")


def _write_server_config(tmp_path, plugins):
    """Write server.config.json with the given ``plugins`` list; return path."""
    cfg = tmp_path / "server.config.json"
    cfg.write_text(json.dumps({"plugins": plugins}), encoding="utf-8")
    return cfg


@pytest.fixture(autouse=True)
def _reset_default_loader():
    """Clear the module-level default loader before and after each test."""
    loader.unmount_all()
    yield
    loader.unmount_all()


class TestPluginList:
    def test_list_via_api_handler_returns_empty_shape(self, api_handler):
        request = {"id": 1, "method": "plugin.list", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 1
        result = data["result"]
        assert result["type"] == "success"
        assert isinstance(result["payload"]["plugins"], list)

    def test_list_reports_loaded_plugins(
        self, tmp_path, monkeypatch, mock_tool_manager,
    ):
        _write_module(
            tmp_path,
            "vplug",
            "__version__ = '1.2.3'\n"
            "def apply(ctx, config):\n"
            "    pass\n",
        )
        cfg = _write_server_config(
            tmp_path,
            [{"module": "vplug", "path": str(tmp_path), "kind": "native"}],
        )
        monkeypatch.setenv("BT_SERVER_CONFIG", str(cfg))
        monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path))

        loader.load_plugins(PluginContext())
        result = plugin_handler.list_plugins({}, None)

        # Shipped-native builtins are ALWAYS loaded first, then user plugins.
        by_module = {p["module"]: p for p in result["plugins"]}
        assert by_module["vplug"] == {
            "module": "vplug", "kind": "native", "version": "1.2.3",
        }
        assert sum(
            1 for p in result["plugins"] if p["kind"] == "shipped-native"
        ) == 8

    def test_list_uses_empty_version_when_absent(
        self, tmp_path, monkeypatch, mock_tool_manager,
    ):
        _write_module(tmp_path, "nover", "def apply(ctx, config):\n    pass\n")
        cfg = _write_server_config(
            tmp_path,
            [{"module": "nover", "path": str(tmp_path), "kind": "native"}],
        )
        monkeypatch.setenv("BT_SERVER_CONFIG", str(cfg))
        monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path))

        loader.load_plugins(PluginContext())
        result = plugin_handler.list_plugins({}, None)

        assert result["plugins"][0]["version"] == ""


class TestPluginReload:
    def test_reload_returns_ok_when_no_plugins(
        self, tmp_path, monkeypatch, mock_tool_manager,
    ):
        monkeypatch.setenv("BT_SERVER_CONFIG", str(tmp_path / "nope.json"))
        monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path))

        result = plugin_handler.reload_plugins({}, None)

        assert result == {"ok": True}

    def test_reload_unmounts_and_reloads_native(
        self, tmp_path, monkeypatch, mock_tool_manager,
    ):
        marker = tmp_path / "marker.txt"
        _write_module(
            tmp_path,
            "reloadable",
            "def apply(ctx, config):\n"
            f"    with open({str(marker)!r}, 'a') as f:\n"
            "        f.write('apply\\n')\n"
            "\n"
            "def unmount(ctx):\n"
            f"    with open({str(marker)!r}, 'a') as f:\n"
            "        f.write('unmount\\n')\n",
        )
        cfg = _write_server_config(
            tmp_path,
            [{"module": "reloadable", "path": str(tmp_path), "kind": "native"}],
        )
        monkeypatch.setenv("BT_SERVER_CONFIG", str(cfg))
        monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path))

        loader.load_plugins(PluginContext())
        result = plugin_handler.reload_plugins({}, None)

        assert result == {"ok": True}
        assert marker.read_text(encoding="utf-8") == "apply\nunmount\napply\n"

    def test_reload_survives_apply_failure(
        self, tmp_path, monkeypatch, mock_tool_manager, caplog,
    ):
        _write_module(
            tmp_path,
            "badapply",
            "def apply(ctx, config):\n    raise ValueError('apply boom')\n",
        )
        cfg = _write_server_config(
            tmp_path,
            [{"module": "badapply", "path": str(tmp_path), "kind": "native"}],
        )
        monkeypatch.setenv("BT_SERVER_CONFIG", str(cfg))
        monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path))

        with caplog.at_level(logging.WARNING, logger="app.plugins.loader"):
            result = plugin_handler.reload_plugins({}, None)

        assert result == {"ok": True}
        assert any("failed to apply" in r.message for r in caplog.records)
