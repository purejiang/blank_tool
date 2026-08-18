#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests: the 20 builtin primitives register as shipped-native plugins."""

from app.plugins.context import PluginContext
from app.plugins.loader import SHIPPED_MANIFEST, load_plugins

#: The 20 builtin primitive names, grouped by their shipped plugin module.
NAMES = [
    # app.plugins.builtin.file (6)
    "file.read", "file.write", "file.copy", "file.move", "file.delete",
    "file.hash",
    # app.plugins.builtin.dir (3)
    "dir.list", "dir.create", "dir.delete",
    # app.plugins.builtin.archive (2)
    "archive.extract", "archive.create",
    # app.plugins.builtin.text (2)
    "text.grep", "text.replace",
    # app.plugins.builtin.net (2)
    "net.download", "net.request",
    # app.plugins.builtin.exec (2)
    "shell.exec", "code.exec",
    # app.plugins.builtin.flow (2)
    "flow.assert", "flow.log",
    # app.plugins.builtin.workflow (1)
    "workflow.run",
]


def test_shipped_manifest_covers_8_modules():
    assert len(SHIPPED_MANIFEST) == 8
    assert all(entry["kind"] == "shipped-native" for entry in SHIPPED_MANIFEST)
    assert [entry["module"] for entry in SHIPPED_MANIFEST] == [
        "app.plugins.builtin.file",
        "app.plugins.builtin.dir",
        "app.plugins.builtin.archive",
        "app.plugins.builtin.text",
        "app.plugins.builtin.net",
        "app.plugins.builtin.exec",
        "app.plugins.builtin.flow",
        "app.plugins.builtin.workflow",
    ]


def test_all_20_builtins_registered_as_shipped_native():
    ctx = PluginContext()
    try:
        load_plugins(ctx, manifest=SHIPPED_MANIFEST)
        all_names = ctx.tools.list_all()
        for name in NAMES:
            assert name in all_names, f"{name!r} missing from list_all()"
            assert ctx.tools.get_kind(name) == "shipped-native"
            assert ctx.tools.get(name).name == name
        assert len(NAMES) == 20
    finally:
        # The registry is a process-wide singleton — fully unregister so the
        # 20 shipped tools do not leak into other tests.
        for name in NAMES:
            ctx.tools.unregister_plugin_tool(name)


def test_reload_is_idempotent():
    """Re-running apply on resident shipped-native tools must not raise."""
    ctx = PluginContext()
    try:
        load_plugins(ctx, manifest=SHIPPED_MANIFEST)
        # Second load re-runs every apply() against the already-resident
        # shipped-native tools; _register must skip them (reviewer rule R2).
        load_plugins(ctx, manifest=SHIPPED_MANIFEST)
        for name in NAMES:
            assert ctx.tools.get_kind(name) == "shipped-native"
    finally:
        for name in NAMES:
            ctx.tools.unregister_plugin_tool(name)
