#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Plugin manifest definitions and selection logic.

This module is the single source of truth for *what* plugins should load —
the shipped-native core, the opt-in extensions, and the user plugin sources
(``server.config.json`` ``plugins`` + ``<output_dir>/plugins.json``).  The
mechanical act of importing and ``apply``-ing entries lives in
``app.plugins.loader``; this file only decides the manifest contents.

Split out of ``loader.py`` so the loader stays focused on mechanics and the
manifest data/selection can be inspected and tested without spinning up a
:class:`~app.plugins.loader.PluginLoader`.
"""

import json
import os
from typing import List, Optional

from app.utils.paths import ROOT, resolve_path
from app.env import (
    ENV_BT_SERVER_CONFIG,
    get_env,
    get_output_dir,
)

_ALLOWED_KINDS = ("shipped-native", "native")

#: The CORE shipped-native builtin plugins, ALWAYS loaded at startup (before
#: any user ``native`` plugins from config).  The minimal universal base: the
#: four atomic tools (``file.read``/``file.write``, ``text.grep``,
#: ``exec.shell``) plus the four orchestration primitives
#: (``flow.assert``/``flow.log``/``flow.foreach``, ``workflow.run``).  Direct
#: import only — no directory scanning.
SHIPPED_MANIFEST = [
    {"module": "app.plugins.builtin.file", "kind": "shipped-native"},
    {"module": "app.plugins.builtin.text", "kind": "shipped-native"},
    {"module": "app.plugins.builtin.exec", "kind": "shipped-native"},
    {"module": "app.plugins.builtin.flow", "kind": "shipped-native"},
    {"module": "app.plugins.builtin.workflow", "kind": "shipped-native"},
]

#: The EXTENDED shipped-native builtin plugins — NOT loaded by default.  These
#: are the remaining atomic tools (``file.copy/move/delete/hash``, ``dir.*``,
#: ``archive.*``, ``text.replace``, ``net.*``, ``exec.code``), opt-in via
#: ``server.config.json`` → ``tools.atomic_extensions`` (a list of module
#: short names, or ``"*"`` for all).  They stay native ``BuiltinTool``
#: instances (no subprocess, streaming/path guards intact) — distinct from
#: external descriptor tools.
EXTENDED_MANIFEST = [
    {"module": "app.plugins.builtin.file_ext", "kind": "shipped-native"},
    {"module": "app.plugins.builtin.dir", "kind": "shipped-native"},
    {"module": "app.plugins.builtin.archive", "kind": "shipped-native"},
    {"module": "app.plugins.builtin.text_ext", "kind": "shipped-native"},
    {"module": "app.plugins.builtin.net", "kind": "shipped-native"},
    {"module": "app.plugins.builtin.exec_ext", "kind": "shipped-native"},
]


def _read_server_plugins() -> Optional[list]:
    """Return the ``plugins`` list from ``server.config.json``, or None.

    ``None`` means "no plugins section present" (file absent, malformed, or
    no ``plugins`` key) — the caller then falls back to the next source.
    """
    source_path = get_env(
        ENV_BT_SERVER_CONFIG, os.path.join(ROOT, "server.config.json")
    )
    resolved = resolve_path(source_path)
    if not resolved or not os.path.exists(resolved):
        return None
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    plugins = raw.get("plugins")
    return plugins if isinstance(plugins, list) else None


def _read_output_plugins() -> Optional[list]:
    """Return the list from ``<output_dir>/plugins.json``, or None if absent."""
    path = os.path.join(get_output_dir(), "plugins.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return None
    return raw if isinstance(raw, list) else None


def _read_server_atomic_extensions() -> list:
    """Return the enabled extension module names from ``server.config.json``.

    Reads ``tools.atomic_extensions`` — a list of extension module SHORT names
    (``file_ext``, ``dir``, ``archive``, ``text_ext``, ``net``, ``exec_ext``)
    or the string ``"*"`` meaning "all extensions".  An absent key, a missing/
    malformed config file, or a non-list value all resolve to ``[]`` (no
    extensions loaded — the lean core default).
    """
    source_path = get_env(
        ENV_BT_SERVER_CONFIG, os.path.join(ROOT, "server.config.json")
    )
    resolved = resolve_path(source_path)
    if not resolved or not os.path.exists(resolved):
        return []
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return []
    if not isinstance(raw, dict):
        return []
    tools = raw.get("tools")
    if not isinstance(tools, dict):
        return []
    extensions = tools.get("atomic_extensions")
    if isinstance(extensions, str):
        return ["*"] if extensions.strip() == "*" else (
            [extensions.strip()] if extensions.strip() else []
        )
    if isinstance(extensions, list):
        return [str(item).strip() for item in extensions if isinstance(item, str) and str(item).strip()]
    return []


def _selected_extended_manifest() -> list:
    """Return the ``EXTENDED_MANIFEST`` entries selected by config.

    ``"*"`` selects every extension module; otherwise each selected SHORT name
    is matched against the final module component of an ``EXTENDED_MANIFEST``
    entry (so ``file_ext`` → ``app.plugins.builtin.file_ext``).  Unknown names
    are ignored.  Returns ``[]`` when nothing is selected (lean core).
    """
    selected = _read_server_atomic_extensions()
    if not selected:
        return []
    by_short = {
        entry["module"].rsplit(".", 1)[-1]: entry for entry in EXTENDED_MANIFEST
    }
    result = []
    for short in selected:
        if short == "*":
            return list(EXTENDED_MANIFEST)
        entry = by_short.get(short)
        if entry is not None:
            result.append(entry)
    return result


def shipped_manifest_with_extensions() -> list:
    """Return the shipped-native manifest: core always, plus selected extensions.

    Used by :meth:`app.tools.tool_manager.ToolManager._load_shipped_plugins`
    so headless CLI + tests (which construct ``ToolManager`` without
    ``cli/main.py`` bootstrap) load the same core + extension set the backend
    would.
    """
    return SHIPPED_MANIFEST + _selected_extended_manifest()


def default_manifest() -> list:
    """Resolve the implicit manifest: shipped-native first, then user plugins.

    The shipped-native builtin plugins (:data:`SHIPPED_MANIFEST` plus any
    enabled :data:`EXTENDED_MANIFEST` entries) always load first, in addition
    to any user ``native`` plugins from config sources (``server.config.json``
    ``plugins`` then ``<output_dir>/plugins.json``, first present wins — an
    absent/empty user source contributes nothing).
    """
    user_plugins = _read_server_plugins()
    if user_plugins is None:
        user_plugins = _read_output_plugins()
    if user_plugins is None:
        user_plugins = []
    return shipped_manifest_with_extensions() + user_plugins
