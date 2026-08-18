#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PluginContext — kernel service seam handed to plugins.

A plugin-lifetime object (distinct from the per-execution
:class:`app.tools.builtin.base.ToolContext`) exposing the three kernel
services a plugin may touch:

* ``tools``  — the unified tool registry (the process-wide
  ``ToolManager.instance()._registry`` singleton, NOT a fresh
  :class:`ToolRegistry` — the workflow engine reads the same registry, so a
  fresh instance would be a "ghost registry" the engine never sees).
* ``env``    — the process-wide environment registry
  (:func:`app.env.registry.get_env_registry`).
* ``events`` — an in-process :class:`~app.plugins.events.EventBus` for
  plugin eventing, defaulting to a fresh bus per context.

``register_tool`` stages a plugin tool into the shared registry (Wave 1
stopgap — see the method docstring); ``emit``/``on`` delegate straight to
``self.events``.
"""

from typing import Any, Callable, Dict, Optional

from app.tools.tool_manager import ToolManager
from app.env.registry import get_env_registry
from app.plugins.events import EventBus


class PluginContext:
    """Service seam exposing kernel services to a plugin.

    Attributes:
        tools: The shared :class:`ToolRegistry` (bound to the singleton
            ``ToolManager.instance()._registry``).
        env: The process-wide :class:`EnvironmentRegistry`.
        events: The :class:`EventBus` this plugin emits on / subscribes to.
        _plugin_tools: Wave 1 staging dict of ``name -> (tool, kind)`` for
            tools registered before the registry grows its own plugin-tool
            API (Wave 2). Always kept in sync with ``tools._tools``.
    """

    def __init__(self, events: Optional[EventBus] = None) -> None:
        # CRITICAL: bind the shared singleton, never a fresh ToolRegistry().
        # The engine constructs at engine.py:161 via ToolManager.instance(),
        # so plugins MUST write into this same registry to be seen by it.
        self.tools = ToolManager.instance()._registry
        self.env = get_env_registry()
        self.events: EventBus = events if events is not None else EventBus()
        self._plugin_tools: Dict[str, Any] = {}

    def register_tool(self, tool: Any, kind: str = "native") -> Any:
        """Register *tool* into the shared tool registry under ``tool.name``.

        Delegates to the registry's ``register_plugin_tool(name, tool, kind)``
        (Wave 2). Until that method exists (Wave 1) the tool is staged in
        ``self._plugin_tools`` AND written into the shared registry's
        ``_tools`` instance cache — the registry's ``get()`` consults
        ``_tools`` first, so the tool becomes immediately visible to the
        engine. The stopgap is superseded by Wave 2's native ``_plugin_tools``
        dict on the registry.

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
        register = getattr(self.tools, "register_plugin_tool", None)
        if callable(register):
            return register(name, tool, kind)
        self._plugin_tools[name] = (tool, kind)
        self.tools._tools[name] = tool
        return tool

    def emit(self, event: str, payload: object = None) -> None:
        """Dispatch *payload* to every handler subscribed to *event*."""
        self.events.emit(event, payload)

    def on(self, event: str, handler: Callable[[object], None]) -> None:
        """Subscribe *handler* to *event* (delegates to ``events.subscribe``)."""
        self.events.subscribe(event, handler)
