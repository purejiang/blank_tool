#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plugin listing and reload handlers.
"""

from app.common.decorators import logs_errors
from app.plugins import loader
from app.plugins.context import PluginContext
from app.utils.logger import Logger

logger = Logger.get_logger("PluginHandler")


@logs_errors("PluginHandler")
def list_plugins(params, stream_handler):
    """Return the currently-loaded plugins (module + kind + version)."""
    plugins = []
    for p in loader.loaded():
        plugins.append(
            {
                "module": p.module,
                "kind": p.kind,
                "version": getattr(p.module_obj, "__version__", ""),
            }
        )
    return {"plugins": plugins}


@logs_errors("PluginHandler")
def reload_plugins(params, stream_handler):
    """Unmount native plugins and re-load from the manifest sources.

    A plugin whose ``apply`` raises is skipped by the loader (warning logged),
    so this never raises for a single bad plugin.
    """
    loader.unmount_all()
    loader.load_plugins(PluginContext())
    return {"ok": True}


API_MAP = {
    "plugin.list": list_plugins,
    "plugin.reload": reload_plugins,
}
