#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests: the shipped-native builtin primitives register in two tiers.

CORE (always loaded): 8 tools across 5 modules — four atomic tools plus the
four orchestration primitives.  EXTENDED (opt-in via ``tools.atomic_extensions``):
13 atomic tools across 6 modules.  Both register as ``shipped-native``.
"""

import json

from app.plugins.context import PluginContext
from app.plugins.loader import (
    EXTENDED_MANIFEST,
    SHIPPED_MANIFEST,
    load_plugins,
    shipped_manifest_with_extensions,
)
from app.plugins.manifest import _selected_extended_manifest

#: The 10 CORE primitive names, grouped by module.
CORE_NAMES = [
    # app.plugins.builtin.file (2)
    "file.read", "file.write",
    # app.plugins.builtin.text (1)
    "text.grep",
    # app.plugins.builtin.exec (1)
    "exec.shell",
    # app.plugins.builtin.flow (5)
    "flow.assert", "flow.log", "flow.foreach", "flow.branch", "flow.compare",
    # app.plugins.builtin.workflow (1)
    "workflow.run",
]

#: The 13 EXTENDED primitive names, grouped by module.
EXTENDED_NAMES = [
    # app.plugins.builtin.file_ext (4)
    "file.copy", "file.move", "file.delete", "file.hash",
    # app.plugins.builtin.dir (3)
    "dir.list", "dir.create", "dir.delete",
    # app.plugins.builtin.archive (2)
    "archive.extract", "archive.create",
    # app.plugins.builtin.text_ext (1)
    "text.replace",
    # app.plugins.builtin.net (2)
    "net.download", "net.request",
    # app.plugins.builtin.exec_ext (1)
    "exec.code",
]


def test_shipped_manifest_is_5_core_modules():
    assert len(SHIPPED_MANIFEST) == 5
    assert all(entry["kind"] == "shipped-native" for entry in SHIPPED_MANIFEST)
    assert [entry["module"] for entry in SHIPPED_MANIFEST] == [
        "app.plugins.builtin.file",
        "app.plugins.builtin.text",
        "app.plugins.builtin.exec",
        "app.plugins.builtin.flow",
        "app.plugins.builtin.workflow",
    ]


def test_extended_manifest_is_6_modules():
    assert len(EXTENDED_MANIFEST) == 6
    assert all(entry["kind"] == "shipped-native" for entry in EXTENDED_MANIFEST)
    assert [entry["module"].rsplit(".", 1)[-1] for entry in EXTENDED_MANIFEST] == [
        "file_ext", "dir", "archive", "text_ext", "net", "exec_ext",
    ]


def test_all_10_core_registered_as_shipped_native():
    ctx = PluginContext()
    load_plugins(ctx, manifest=SHIPPED_MANIFEST)
    for name in CORE_NAMES:
        assert name in ctx.tools.list_all(), f"{name!r} missing from list_all()"
        assert ctx.tools.get_kind(name) == "shipped-native"
        assert ctx.tools.get(name).name == name
    assert len(CORE_NAMES) == 10


def test_all_13_extended_registered_as_shipped_native():
    ctx = PluginContext()
    load_plugins(ctx, manifest=EXTENDED_MANIFEST)
    for name in EXTENDED_NAMES:
        assert name in ctx.tools.list_all(), f"{name!r} missing from list_all()"
        assert ctx.tools.get_kind(name) == "shipped-native"
        assert ctx.tools.get(name).name == name
    assert len(EXTENDED_NAMES) == 13


def test_reload_is_idempotent():
    """Re-running apply on resident shipped-native tools must not raise."""
    ctx = PluginContext()
    load_plugins(ctx, manifest=SHIPPED_MANIFEST)
    # Second load re-runs every apply() against the already-resident
    # shipped-native tools; _register must skip them (reviewer rule R2).
    load_plugins(ctx, manifest=SHIPPED_MANIFEST)
    for name in CORE_NAMES:
        assert ctx.tools.get_kind(name) == "shipped-native"


# ── config-driven extension selection ──────────────────────────────────────

def _write_config(tmp_path, atomic_extensions):
    cfg = tmp_path / "server.config.json"
    cfg.write_text(
        json.dumps({"tools": {"atomic_extensions": atomic_extensions}}),
        encoding="utf-8",
    )
    return str(cfg)


def test_selected_extended_empty_without_config(monkeypatch, tmp_path):
    monkeypatch.setenv("BT_SERVER_CONFIG", str(tmp_path / "nope.json"))
    assert _selected_extended_manifest() == []


def test_selected_extended_star_selects_all(monkeypatch, tmp_path):
    monkeypatch.setenv("BT_SERVER_CONFIG", _write_config(tmp_path, "*"))
    assert _selected_extended_manifest() == EXTENDED_MANIFEST


def test_selected_extended_subset(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "BT_SERVER_CONFIG", _write_config(tmp_path, ["file_ext", "net"])
    )
    selected = _selected_extended_manifest()
    assert [e["module"].rsplit(".", 1)[-1] for e in selected] == [
        "file_ext", "net"
    ]


def test_selected_extended_ignores_unknown_names(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "BT_SERVER_CONFIG", _write_config(tmp_path, ["file_ext", "bogus"])
    )
    selected = _selected_extended_manifest()
    assert [e["module"].rsplit(".", 1)[-1] for e in selected] == ["file_ext"]


def test_shipped_manifest_with_extensions_defaults_to_core(monkeypatch, tmp_path):
    monkeypatch.setenv("BT_SERVER_CONFIG", str(tmp_path / "nope.json"))
    manifest = shipped_manifest_with_extensions()
    assert [e["module"] for e in manifest] == [
        e["module"] for e in SHIPPED_MANIFEST
    ]


def test_shipped_manifest_with_extensions_star(monkeypatch, tmp_path):
    monkeypatch.setenv("BT_SERVER_CONFIG", _write_config(tmp_path, "*"))
    manifest = shipped_manifest_with_extensions()
    assert manifest == SHIPPED_MANIFEST + EXTENDED_MANIFEST
