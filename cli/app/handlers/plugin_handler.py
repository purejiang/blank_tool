#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plugin listing, add, delete, and reload handlers.
"""

import json
import os

from app.common.decorators import logs_errors
from app.common.exceptions import ToolException
from app.plugins import loader
from app.plugins.context import PluginContext
from app.env import get_output_dir
from app.utils.logger import Logger

logger = Logger.get_logger("PluginHandler")

#: Suffixes that mark a ``path`` as a script or binary (i.e. a descriptor
#: tool), NOT a native Python plugin package. ``plugin.add`` rejects these so
#: callers route them to ``tool.add`` instead.
_SCRIPT_SUFFIXES = (".exe", ".jar", ".js", ".sh", ".py")


def _plugins_file() -> str:
    """Return the writable user plugin manifest (``<output_dir>/plugins.json``)."""
    return os.path.join(get_output_dir(), "plugins.json")


def _read_plugins_config() -> list:
    """Return the user plugin manifest list, or ``[]`` when absent/malformed."""
    path = _plugins_file()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return []
    return raw if isinstance(raw, list) else []


def _write_plugins_config(plugins: list) -> None:
    """Write the user plugin manifest list to ``<output_dir>/plugins.json``."""
    path = _plugins_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plugins, f, ensure_ascii=False, indent=2)


def _serialize_plugins() -> list:
    """Serialize the currently-loaded plugins (module/kind/version/loaded/error).

    The loader does not record per-plugin import/apply errors (it logs and
    skips), so ``error`` is empty and ``loaded`` reflects membership in the
    loaded list.
    """
    plugins = []
    for p in loader.loaded():
        plugins.append(
            {
                "module": p.module,
                "kind": p.kind,
                "version": getattr(p.module_obj, "__version__", ""),
                "loaded": True,
                "error": "",
            }
        )
    return plugins


def _reload() -> None:
    """Unmount native plugins and re-load from the manifest sources."""
    loader.unmount_all()
    loader.load_plugins(PluginContext())


@logs_errors("PluginHandler")
def list_plugins(params, stream_handler):
    """Return the currently-loaded plugins (module + kind + version + status)."""
    return {"plugins": _serialize_plugins()}


@logs_errors("PluginHandler")
def add_plugin(params, stream_handler):
    """Add a native plugin manifest entry and reload.

    ``module`` is required. Optional ``path`` (a directory prepended to
    ``sys.path``) and ``config`` (passed through to ``apply``) are persisted
    to ``<output_dir>/plugins.json``. A ``path`` that is a script/binary
    (``.exe``/``.jar``/``.js``/``.sh``/``.py``) is rejected — those are
    descriptor tools, added via ``tool.add``.
    """
    module = params.get("module")
    if not isinstance(module, str) or not module:
        raise ToolException("Missing 'module' field")

    path = params.get("path")
    config = params.get("config")

    if isinstance(path, str) and path:
        if path.lower().endswith(_SCRIPT_SUFFIXES):
            raise ToolException("exe/jar/script tools are descriptors; use tool.add")

    if module in {entry["module"] for entry in loader.SHIPPED_MANIFEST}:
        raise ToolException(
            f"cannot add shipped plugin {module!r} as a user plugin "
            f"(shipped-native plugins are always loaded)"
        )

    plugins = _read_plugins_config()
    if any(isinstance(p, dict) and p.get("module") == module for p in plugins):
        raise ToolException(f"plugin {module!r} is already in the manifest")

    entry = {"module": module, "kind": "native"}
    if isinstance(path, str) and path:
        entry["path"] = path
    if config is not None:
        entry["config"] = config

    plugins.append(entry)
    _write_plugins_config(plugins)

    _reload()
    return {"plugins": _serialize_plugins()}


@logs_errors("PluginHandler")
def delete_plugin(params, stream_handler):
    """Remove a native plugin manifest entry and reload.

    Shipped-native builtins (:data:`loader.SHIPPED_MANIFEST`) cannot be
    deleted.
    """
    module = params.get("module")
    if not isinstance(module, str) or not module:
        raise ToolException("Missing 'module' field")

    shipped_modules = {entry["module"] for entry in loader.SHIPPED_MANIFEST}
    if module in shipped_modules:
        raise ToolException("cannot delete shipped plugin")

    plugins = _read_plugins_config()
    remaining = [
        p for p in plugins if not isinstance(p, dict) or p.get("module") != module
    ]
    _write_plugins_config(remaining)

    _reload()
    return {"plugins": _serialize_plugins()}


@logs_errors("PluginHandler")
def reload_plugins(params, stream_handler):
    """Unmount native plugins and re-load from the manifest sources.

    A plugin whose ``apply`` raises is skipped by the loader (warning logged),
    so this never raises for a single bad plugin.
    """
    _reload()
    return {"ok": True}


API_MAP = {
    "plugin.list": list_plugins,
    "plugin.add": add_plugin,
    "plugin.delete": delete_plugin,
    "plugin.reload": reload_plugins,
}
