#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plugin loader — config-list + ``importlib`` with lifecycle (load + unmount).

Loads native Python plugins from a manifest (a list of dicts, one per
plugin) and hands each a :class:`~app.plugins.context.PluginContext` (or any
caller-supplied context object) via its ``apply`` entry point. Stdlib-only.

Manifest entries
----------------
Each entry is a dict:

* ``module`` (str, REQUIRED): dotted module name to import — a shipped
  ``app.plugins.builtin.*`` package or a third-party ``my_plugin``.
* ``path`` (str, optional): parent directory prepended to ``sys.path``
  before the import, so ``module`` is importable from there.
* ``config`` (any, optional): passed through to ``apply(ctx, config)``.
* ``kind`` (str, REQUIRED): ``"shipped-native"`` or ``"native"``.

Manifest sources (first present wins, else empty manifest):
the ``plugins`` section of ``server.config.json``, then
``<output_dir>/plugins.json``.

Lifecycle
---------
:meth:`PluginLoader.load` imports each entry in order and calls ``apply``.
A plugin whose import or ``apply`` raises is skipped (full traceback logged
at WARNING) and never stops the remaining entries. :meth:`PluginLoader.
unmount_all` tears down only ``native`` plugins (reverse load order): it
calls ``unmount(ctx)`` when defined, removes the ``sys.path`` entry this
loader inserted (membership-checked first — a user's pre-existing same-path
entry is left untouched), and pops the ``sys.modules`` ``module.*`` keys the
import added (before/after diff around the import).
"""

import importlib
import inspect
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any, List, Optional

from app.utils.env import (
    ENV_BT_SERVER_CONFIG,
    ROOT,
    get_env,
    get_output_dir,
    resolve_path,
)

logger = logging.getLogger(__name__)

_ALLOWED_KINDS = ("shipped-native", "native")


@dataclass
class LoadedPlugin:
    """Bookkeeping for one successfully loaded plugin.

    Attributes:
        module: the dotted module name (str) from the manifest.
        module_obj: the imported module object.
        path: the ``sys.path`` entry this loader inserted (``None`` when the
            manifest entry had no ``path``).
        kind: ``"shipped-native"`` or ``"native"``.
        added_module_keys: ``sys.modules`` keys (``module`` + ``module.*``)
            introduced by this plugin's import, for cache eviction on unmount.
    """

    module: str
    module_obj: Any
    path: Optional[str]
    kind: str
    added_module_keys: List[str] = field(default_factory=list)


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


def _default_manifest() -> list:
    """Resolve the implicit manifest from config sources, or ``[]``."""
    server = _read_server_plugins()
    if server is not None:
        return server
    output = _read_output_plugins()
    if output is not None:
        return output
    return []


def _invoke_apply(apply, ctx, config) -> Any:
    """Call ``apply`` adapting to whether it declares a ``config`` parameter.

    Trusts ``inspect.signature`` when it yields a definitive answer; falls
    back to "2-arg then 1-arg" (catching ``TypeError``) for signatures that
    cannot be inspected reliably — C extensions, builtins, or ``*args`` /
    ``**kwargs`` forms.
    """
    try:
        sig = inspect.signature(apply)
    except (TypeError, ValueError):
        sig = None

    if sig is not None:
        params = list(sig.parameters.values())
        has_config = "config" in sig.parameters
        has_var = any(
            p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in params
        )
        if has_config:
            return apply(ctx, config)
        if not has_var:
            return apply(ctx)
        # *args/**kwargs without an explicit config name: ambiguous → fall back.

    try:
        return apply(ctx, config)
    except TypeError:
        return apply(ctx)


class PluginLoader:
    """Stateful loader: loads a manifest and can tear down native plugins."""

    def __init__(self, ctx: Any = None) -> None:
        self._ctx = ctx
        self._loaded: List[LoadedPlugin] = []

    @property
    def loaded(self) -> List[LoadedPlugin]:
        """A copy of the currently-loaded plugin records."""
        return list(self._loaded)

    def load(self, manifest: Optional[list] = None) -> List[LoadedPlugin]:
        """Import and ``apply`` every manifest entry, in order.

        A ``None`` *manifest* resolves from config sources (server.config.json
        ``plugins`` then ``<output_dir>/plugins.json``); an absent/empty
        manifest is a no-op. Returns the loaded-plugin records.
        """
        entries = self._resolve_manifest(manifest)
        for entry in entries:
            self._load_entry(entry)
        return self.loaded

    def unmount_all(self) -> None:
        """Tear down only ``native`` plugins, in reverse load order.

        ``shipped-native`` plugins stay resident. For each unloaded plugin:
        ``unmount(ctx)`` is called if defined, the loader-inserted ``sys.path``
        entry is removed (membership-checked, first occurrence — a user's
        pre-existing same-path entry is left alone), and the ``sys.modules``
        ``module.*`` keys the import added are popped.
        """
        native = [p for p in self._loaded if p.kind == "native"]
        for plugin in reversed(native):
            self._unmount_one(plugin)
        self._loaded = [p for p in self._loaded if p.kind != "native"]

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _resolve_manifest(self, manifest: Optional[list]) -> list:
        if manifest is None:
            return _default_manifest()
        if not isinstance(manifest, list):
            logger.warning("plugin manifest is not a list; treating as empty")
            return []
        return manifest

    def _load_entry(self, entry: Any) -> None:
        if not isinstance(entry, dict):
            logger.warning("plugin manifest entry is not a dict; skipping: %r", entry)
            return

        module_name = entry.get("module")
        if not isinstance(module_name, str) or not module_name:
            logger.warning(
                "plugin manifest entry missing 'module'; skipping: %r", entry
            )
            return

        kind = entry.get("kind")
        if kind not in _ALLOWED_KINDS:
            logger.warning(
                "plugin %r has invalid kind %r; skipping", module_name, kind
            )
            return

        path = entry.get("path")
        if not isinstance(path, str) or not path:
            path = None
        config = entry.get("config")

        inserted_path = None
        if path is not None:
            sys.path.insert(0, path)
            inserted_path = path

        before = set(sys.modules)
        try:
            module_obj = importlib.import_module(module_name)
        except Exception:
            self._revert(path, module_name, before)
            logger.warning(
                "failed to import plugin %r", module_name, exc_info=True
            )
            return

        added = self._added_keys(module_name, before)
        try:
            apply = getattr(module_obj, "apply", None)
            if apply is None or not callable(apply):
                raise AttributeError("plugin module defines no callable apply")
            _invoke_apply(apply, self._ctx, config)
        except Exception:
            self._revert(path, module_name, before)
            logger.warning(
                "failed to apply plugin %r", module_name, exc_info=True
            )
            return

        self._loaded.append(
            LoadedPlugin(
                module=module_name,
                module_obj=module_obj,
                path=inserted_path,
                kind=kind,
                added_module_keys=added,
            )
        )

    def _unmount_one(self, plugin: LoadedPlugin) -> None:
        unmount = getattr(plugin.module_obj, "unmount", None)
        if callable(unmount):
            try:
                unmount(self._ctx)
            except Exception:
                logger.warning(
                    "plugin %r unmount raised", plugin.module, exc_info=True
                )

        # Remove the sys.path entry THIS loader inserted. We always insert at
        # index 0, so list.remove (first occurrence) pops ours and leaves any
        # user pre-existing same-path entry further down the list intact.
        if plugin.path is not None and plugin.path in sys.path:
            sys.path.remove(plugin.path)

        for key in plugin.added_module_keys:
            sys.modules.pop(key, None)

    @staticmethod
    def _added_keys(module_name: str, before: set) -> List[str]:
        """``sys.modules`` keys introduced since *before*, scoped to this module."""
        prefix = module_name + "."
        return [
            key
            for key in set(sys.modules) - before
            if key == module_name or key.startswith(prefix)
        ]

    def _revert(
        self, path: Optional[str], module_name: str, before: set
    ) -> None:
        """Undo a failed entry's side effects (path insert + module cache)."""
        if path is not None and path in sys.path:
            sys.path.remove(path)
        for key in self._added_keys(module_name, before):
            sys.modules.pop(key, None)


# ---------------------------------------------------------------------------
# Module-level convenience (cli/main.py wires these in todo 4).
# ---------------------------------------------------------------------------

_default_loader: Optional[PluginLoader] = None


def load_plugins(
    ctx: Any = None, manifest: Optional[list] = None
) -> List[LoadedPlugin]:
    """Build a loader, load *manifest*, and remember it for :func:`unmount_all`."""
    global _default_loader
    _default_loader = PluginLoader(ctx)
    return _default_loader.load(manifest)


def unmount_all() -> None:
    """Tear down the last loader created by :func:`load_plugins` (if any)."""
    global _default_loader
    if _default_loader is not None:
        _default_loader.unmount_all()
        _default_loader = None
