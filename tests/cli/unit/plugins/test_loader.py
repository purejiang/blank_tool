#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the plugin loader (app.plugins.loader)."""

import json
import logging
import sys

from app.plugins.loader import (
    PluginLoader,
    SHIPPED_MANIFEST,
    load_plugins,
    unmount_all,
)


def _write_module(tmp_path, name, body):
    """Write a single-file module ``name``.py under tmp_path."""
    (tmp_path / f"{name}.py").write_text(body, encoding="utf-8")


SHIPPED_MODULES = [entry["module"] for entry in SHIPPED_MANIFEST]


class _StubTools:
    """Stand-in registry exposing the plugin-tool seam shipped ``apply`` needs."""

    def __init__(self):
        self.registered = {}

    def get_kind(self, name):
        return self.registered.get(name)

    def register_tool(self, tool, kind):
        self.registered[tool.name] = kind
        return tool


class _StubCtx:
    """Minimal ctx supporting shipped ``apply`` (``.tools``/``.register_tool``)
    and user plugin ``apply`` (dict item assignment)."""

    def __init__(self):
        self.tools = _StubTools()
        self._data = {}

    def register_tool(self, tool, kind="native"):
        return self.tools.register_tool(tool, kind)

    def __setitem__(self, key, value):
        self._data[key] = value

    def __getitem__(self, key):
        return self._data[key]


def test_apply_called_once_with_config(tmp_path):
    calls = []
    _write_module(
        tmp_path,
        "cfgp",
        "def apply(ctx, config):\n"
        "    ctx['calls'].append(config)\n",
    )
    ctx = {"calls": calls}
    loader = PluginLoader(ctx=ctx)
    loaded = loader.load(
        [
            {
                "module": "cfgp",
                "path": str(tmp_path),
                "kind": "native",
                "config": {"k": 1},
            }
        ]
    )
    assert [p.module for p in loaded] == ["cfgp"]
    assert calls == [{"k": 1}]
    loader.unmount_all()


def test_broken_import_logs_warning_and_does_not_raise(tmp_path, caplog):
    _write_module(tmp_path, "broken", "raise RuntimeError('boom')\n")
    loader = PluginLoader(ctx={})
    with caplog.at_level(logging.WARNING, logger="app.plugins.loader"):
        loaded = loader.load(
            [{"module": "broken", "path": str(tmp_path), "kind": "native"}]
        )
    assert loaded == []
    assert any("failed to import" in r.message for r in caplog.records)
    assert any(r.exc_info for r in caplog.records)  # full traceback captured


def test_broken_apply_logs_warning_and_does_not_raise(tmp_path, caplog):
    _write_module(
        tmp_path,
        "bad_apply",
        "def apply(ctx, config):\n"
        "    raise ValueError('apply boom')\n",
    )
    loader = PluginLoader(ctx={})
    with caplog.at_level(logging.WARNING, logger="app.plugins.loader"):
        loaded = loader.load(
            [{"module": "bad_apply", "path": str(tmp_path), "kind": "native"}]
        )
    assert loaded == []
    assert any("failed to apply" in r.message for r in caplog.records)
    assert any(r.exc_info for r in caplog.records)


def test_broken_entry_does_not_stop_others(tmp_path):
    _write_module(
        tmp_path, "good", "def apply(ctx, config):\n    ctx['ok'] = True\n"
    )
    _write_module(tmp_path, "bad", "raise RuntimeError('nope')\n")
    ctx = {}
    loader = PluginLoader(ctx=ctx)
    loaded = loader.load(
        [
            {"module": "bad", "path": str(tmp_path), "kind": "native"},
            {"module": "good", "path": str(tmp_path), "kind": "native"},
        ]
    )
    assert [p.module for p in loaded] == ["good"]
    assert ctx["ok"] is True
    loader.unmount_all()


def test_apply_without_config_param_is_called(tmp_path):
    calls = []
    _write_module(
        tmp_path,
        "onearg",
        "def apply(ctx):\n"
        "    ctx['calls'].append('no-config')\n",
    )
    ctx = {"calls": calls}
    loader = PluginLoader(ctx=ctx)
    loader.load(
        [
            {
                "module": "onearg",
                "path": str(tmp_path),
                "kind": "native",
                "config": {"x": 1},
            }
        ]
    )
    assert calls == ["no-config"]
    loader.unmount_all()


def test_apply_varargs_fallback(tmp_path):
    calls = []
    _write_module(
        tmp_path,
        "varargs",
        "def apply(*args):\n"
        "    ctx = args[0]\n"
        "    ctx['calls'].append(len(args))\n",
    )
    ctx = {"calls": calls}
    loader = PluginLoader(ctx=ctx)
    loader.load(
        [
            {
                "module": "varargs",
                "path": str(tmp_path),
                "kind": "native",
                "config": {"x": 1},
            }
        ]
    )
    # *args signature → fallback tries apply(ctx, config) first → 2 args
    assert calls == [2]
    loader.unmount_all()


def test_unmount_all_calls_unmount_in_reverse_order(tmp_path):
    order = []
    for name in ("p_a", "p_b"):
        _write_module(
            tmp_path,
            name,
            "def apply(ctx):\n"
            "    pass\n"
            "\n"
            "def unmount(ctx):\n"
            f"    ctx['order'].append('{name}')\n",
        )
    ctx = {"order": order}
    loader = PluginLoader(ctx=ctx)
    loader.load(
        [
            {"module": "p_a", "path": str(tmp_path), "kind": "native"},
            {"module": "p_b", "path": str(tmp_path), "kind": "native"},
        ]
    )
    loader.unmount_all()
    assert order == ["p_b", "p_a"]


def test_unmount_all_keeps_shipped_native_resident(tmp_path):
    unmounted = []
    _write_module(
        tmp_path,
        "shipped",
        "def apply(ctx):\n"
        "    pass\n"
        "\n"
        "def unmount(ctx):\n"
        "    ctx['u'].append('shipped')\n",
    )
    _write_module(
        tmp_path,
        "nat",
        "def apply(ctx):\n"
        "    pass\n"
        "\n"
        "def unmount(ctx):\n"
        "    ctx['u'].append('nat')\n",
    )
    ctx = {"u": unmounted}
    loader = PluginLoader(ctx=ctx)
    loader.load(
        [
            {"module": "shipped", "path": str(tmp_path), "kind": "shipped-native"},
            {"module": "nat", "path": str(tmp_path), "kind": "native"},
        ]
    )
    loader.unmount_all()
    assert unmounted == ["nat"]  # shipped-native NOT unmounted


def test_reload_clears_module_cache_and_path(tmp_path):
    # Disable .pyc caching so the mutated source is re-read deterministically
    # (otherwise a same-mtime .pyc can serve stale bytecode on Windows).
    old_dont_write = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        _reload_roundtrip(tmp_path)
    finally:
        sys.dont_write_bytecode = old_dont_write


def _reload_roundtrip(tmp_path):
    mod_file = tmp_path / "reloadable.py"
    mod_file.write_text(
        "def apply(ctx):\n    ctx['v'] = 'old'\n", encoding="utf-8"
    )
    loader = PluginLoader(ctx={})
    loader.load(
        [{"module": "reloadable", "path": str(tmp_path), "kind": "native"}]
    )
    assert sys.modules["reloadable"] is not None

    # Mutate the plugin body, then unmount + reload.
    mod_file.write_text(
        "def apply(ctx):\n    ctx['v'] = 'new'\n", encoding="utf-8"
    )
    loader.unmount_all()
    assert "reloadable" not in sys.modules  # cache cleared
    assert str(tmp_path) not in sys.path  # path removed

    ctx = {}
    loader2 = PluginLoader(ctx=ctx)
    loader2.load(
        [{"module": "reloadable", "path": str(tmp_path), "kind": "native"}]
    )
    assert ctx["v"] == "new"  # NEW apply ran (stale cache would yield 'old')
    assert sys.path.count(str(tmp_path)) == 1  # no duplicate path entry
    loader2.unmount_all()


def test_unmount_does_not_remove_preexisting_path(tmp_path):
    _write_module(tmp_path, "pre_existing", "def apply(ctx):\n    pass\n")
    sys.path.insert(0, str(tmp_path))
    try:
        loader = PluginLoader(ctx={})
        loader.load(
            [
                {
                    "module": "pre_existing",
                    "path": str(tmp_path),
                    "kind": "native",
                }
            ]
        )
        assert sys.path.count(str(tmp_path)) == 2  # user's + loader's
        loader.unmount_all()
        # loader removed only its own entry; user's pre-existing entry remains
        assert sys.path.count(str(tmp_path)) == 1
    finally:
        while str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_invalid_kind_is_skipped(tmp_path, caplog):
    _write_module(tmp_path, "weird", "def apply(ctx):\n    pass\n")
    loader = PluginLoader(ctx={})
    with caplog.at_level(logging.WARNING, logger="app.plugins.loader"):
        loaded = loader.load(
            [{"module": "weird", "path": str(tmp_path), "kind": "bogus"}]
        )
    assert loaded == []
    assert any("invalid kind" in r.message for r in caplog.records)


def test_default_manifest_loads_shipped_when_no_sources(monkeypatch, tmp_path):
    monkeypatch.setenv("BT_SERVER_CONFIG", str(tmp_path / "nope.json"))
    monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path))
    loader = PluginLoader(ctx=_StubCtx())
    loaded = loader.load()
    assert [p.module for p in loaded] == SHIPPED_MODULES


def test_reads_plugins_from_server_config(monkeypatch, tmp_path):
    cfg = tmp_path / "server.config.json"
    cfg.write_text(
        json.dumps(
            {
                "plugins": [
                    {
                        "module": "cfg_plugin",
                        "path": str(tmp_path),
                        "kind": "native",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _write_module(
        tmp_path,
        "cfg_plugin",
        "def apply(ctx, config):\n    ctx['from'] = 'server'\n",
    )
    monkeypatch.setenv("BT_SERVER_CONFIG", str(cfg))
    monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path))
    ctx = _StubCtx()
    loader = PluginLoader(ctx=ctx)
    loaded = loader.load()
    assert [p.module for p in loaded] == SHIPPED_MODULES + ["cfg_plugin"]
    assert ctx["from"] == "server"
    loader.unmount_all()


def test_module_level_load_and_unmount(tmp_path):
    _write_module(
        tmp_path,
        "conv",
        "def apply(ctx, config):\n"
        "    ctx['v'] = config['v']\n"
        "\n"
        "def unmount(ctx):\n"
        "    ctx['unmounted'] = True\n",
    )
    ctx = {}
    loaded = load_plugins(
        ctx,
        [{"module": "conv", "path": str(tmp_path), "kind": "native", "config": {"v": 7}}],
    )
    assert len(loaded) == 1
    assert ctx["v"] == 7
    unmount_all()
    assert ctx["unmounted"] is True
    assert "conv" not in sys.modules
