#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plugin listing, execution, and reload handlers.
"""

from app.plugins.manager import PluginManager
from app.utils.logger import Logger
from app.common.exceptions import ToolException

logger = Logger.get_logger("PluginHandler")
manager = PluginManager.instance()


def list_plugins(params, stream_handler):
    """Get all plugin list."""
    try:
        return manager.get_all_plugins()
    except Exception as e:
        logger.error(f"Failed to list plugins: {e}")
        raise


def run_plugin(params, stream_handler):
    """Run a specified plugin."""
    plugin_name = params.get("name")
    plugin_params = params.get("params", {})

    if not plugin_name:
        raise ToolException("Plugin name not specified")

    try:
        return manager.run_plugin(plugin_name, plugin_params, stream_handler)
    except Exception as e:
        raise


def reload_plugins(params, stream_handler):
    """Reload all plugins."""
    try:
        manager.load_plugins()
        return manager.get_all_plugins()
    except Exception as e:
        logger.error(f"Failed to reload plugins: {e}")
        raise


API_MAP = {
    "plugin.list": list_plugins,
    "plugin.run": run_plugin,
    "plugin.reload": reload_plugins,
}
