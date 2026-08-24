#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PluginContext — kernel service seam handed to plugins.

A plugin-lifetime object (distinct from the per-execution
:class:`app.tools.builtin.base.ToolContext`) exposing the two kernel
services a plugin may touch:

* ``tools``  — the unified tool registry (the process-wide
  ``ToolManager.instance()._registry`` singleton, NOT a fresh
  :class:`ToolRegistry` — the workflow engine reads the same registry, so a
  fresh instance would be a "ghost registry" the engine never sees).
* ``env``    — the process-wide environment registry
  (:func:`app.env.registry.get_env_registry`).

``register_tool`` delegates straight to the shared registry's
``register_plugin_tool`` (the real plugin-tool registration path).
"""

from typing import Any

from app.tools.tool_manager import ToolManager
from app.env.registry import get_env_registry


class PluginContext:
    """Service seam exposing kernel services to a plugin.

    Attributes:
        tools: The shared :class:`ToolRegistry` (bound to the singleton
            ``ToolManager.instance()._registry``).
        env: The process-wide :class:`EnvironmentRegistry`.
    """

    def __init__(self) -> None:
        # CRITICAL: bind the shared singleton, never a fresh ToolRegistry().
        # The engine constructs at engine.py:161 via ToolManager.instance(),
        # so plugins MUST write into this same registry to be seen by it.
        self.tools = ToolManager.instance()._registry
        self.env = get_env_registry()

    def register_tool(self, tool: Any, kind: str = "native") -> Any:
        """Register *tool* into the shared tool registry under ``tool.name``.

        Delegates to the registry's ``register_plugin_tool(name, tool, kind)``.

        Raises:
            ValueError: if *tool* has no non-empty string ``name`` attribute,
                or if the registry rejects the registration (e.g. invalid
                kind / name conflict).
        """
        name = getattr(tool, "name", None)
        if not isinstance(name, str) or not name:
            raise ValueError(
                "plugin tool must expose a non-empty string `name` attribute"
            )
        return self.tools.register_plugin_tool(name, tool, kind)
