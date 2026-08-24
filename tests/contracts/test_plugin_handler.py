"""
Contract tests for the plugin handler (plugin.list / add / delete / reload).
"""
import json
import logging

import pytest

from app.common.exceptions import ToolException
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
        # Only the 5 CORE shipped plugins load by default (the extended set is
        # opt-in via server.config.json tools.atomic_extensions, and the config
        # written above selects none).
        by_module = {p["module"]: p for p in result["plugins"]}
        assert by_module["vplug"] == {
            "module": "vplug", "kind": "native", "version": "1.2.3",
            "loaded": True, "error": "",
        }
        assert sum(
            1 for p in result["plugins"] if p["kind"] == "shipped-native"
        ) == 5

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


class TestPluginAdd:
    def test_add_writes_manifest_and_reloads(
        self, tmp_path, monkeypatch, mock_tool_manager,
    ):
        _write_module(
            tmp_path,
            "addplug",
            "__version__ = '9.9.9'\n"
            "def apply(ctx, config):\n"
            "    pass\n",
        )
        monkeypatch.setenv("BT_SERVER_CONFIG", str(tmp_path / "nope.json"))
        monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path))

        result = plugin_handler.add_plugin(
            {"module": "addplug", "path": str(tmp_path)}, None
        )

        by_module = {p["module"]: p for p in result["plugins"]}
        assert by_module["addplug"] == {
            "module": "addplug", "kind": "native", "version": "9.9.9",
            "loaded": True, "error": "",
        }

        manifest_path = tmp_path / "plugins.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest == [
            {"module": "addplug", "path": str(tmp_path), "kind": "native"},
        ]

    def test_add_persists_optional_config(
        self, tmp_path, monkeypatch, mock_tool_manager,
    ):
        _write_module(tmp_path, "cfgplug", "def apply(ctx, config):\n    pass\n")
        monkeypatch.setenv("BT_SERVER_CONFIG", str(tmp_path / "nope.json"))
        monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path))

        plugin_handler.add_plugin(
            {"module": "cfgplug", "path": str(tmp_path), "config": {"k": "v"}},
            None,
        )

        manifest = json.loads(
            (tmp_path / "plugins.json").read_text(encoding="utf-8")
        )
        assert manifest == [
            {
                "module": "cfgplug",
                "path": str(tmp_path),
                "config": {"k": "v"},
                "kind": "native",
            },
        ]

    @pytest.mark.parametrize("suffix", [".exe", ".jar", ".js", ".sh", ".py"])
    def test_add_rejects_script_or_binary_path(
        self, tmp_path, monkeypatch, mock_tool_manager, suffix,
    ):
        monkeypatch.setenv("BT_SERVER_CONFIG", str(tmp_path / "nope.json"))
        monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path))

        with pytest.raises(ToolException, match="use tool.add"):
            plugin_handler.add_plugin(
                {"module": "sometool", "path": f"C:/tools/tool{suffix}"}, None
            )

    def test_add_requires_module(
        self, tmp_path, monkeypatch, mock_tool_manager,
    ):
        monkeypatch.setenv("BT_SERVER_CONFIG", str(tmp_path / "nope.json"))
        monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path))

        with pytest.raises(ToolException, match="module"):
            plugin_handler.add_plugin({}, None)


class TestPluginDelete:
    def test_delete_removes_manifest_entry_and_reloads(
        self, tmp_path, monkeypatch, mock_tool_manager,
    ):
        _write_module(
            tmp_path,
            "delplug",
            "def apply(ctx, config):\n    pass\n",
        )
        monkeypatch.setenv("BT_SERVER_CONFIG", str(tmp_path / "nope.json"))
        monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path))

        plugin_handler.add_plugin(
            {"module": "delplug", "path": str(tmp_path)}, None
        )
        result = plugin_handler.delete_plugin({"module": "delplug"}, None)

        by_module = {p["module"] for p in result["plugins"]}
        assert "delplug" not in by_module

        manifest = json.loads(
            (tmp_path / "plugins.json").read_text(encoding="utf-8")
        )
        assert manifest == []

    def test_delete_rejects_shipped_plugin(
        self, tmp_path, monkeypatch, mock_tool_manager,
    ):
        monkeypatch.setenv("BT_SERVER_CONFIG", str(tmp_path / "nope.json"))
        monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path))

        with pytest.raises(ToolException, match="cannot delete shipped plugin"):
            plugin_handler.delete_plugin(
                {"module": "app.plugins.builtin.file"}, None
            )

    def test_delete_requires_module(
        self, tmp_path, monkeypatch, mock_tool_manager,
    ):
        monkeypatch.setenv("BT_SERVER_CONFIG", str(tmp_path / "nope.json"))
        monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path))

        with pytest.raises(ToolException, match="module"):
            plugin_handler.delete_plugin({}, None)


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
