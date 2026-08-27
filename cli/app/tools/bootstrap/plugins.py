"""Plugin bootstrap: register shipped-native builtin plugins into the shared registry.

This is the single extension point for "which plugins load at startup".  The
deferred import of plugin context / loader avoids a top-level circular import
(``app.plugins.context`` imports ``ToolManager``).  A loader failure must not
prevent ``ToolManager`` construction, so errors are logged, not raised.
"""

import logging
from typing import Optional

from app.utils.logger import Logger

_logger = Logger.get_logger("plugin_bootstrap")


def bootstrap_shipped_plugins() -> None:
    """Register the shipped-native builtin plugins into the shared ToolManager registry.

    ``PluginContext()`` binds the process-wide ``ToolManager.instance().get_registry()``
    singleton, so tools registered here are visible to the workflow engine.
    """
    try:
        from app.plugins.context import PluginContext
        from app.plugins.loader import (
            load_plugins,
            shipped_manifest_with_extensions,
        )

        load_plugins(
            PluginContext(), manifest=shipped_manifest_with_extensions()
        )
    except Exception:
        _logger.warning(
            "failed to load shipped-native builtin plugins", exc_info=True
        )
