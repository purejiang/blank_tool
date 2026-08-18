#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the plugin kernel's PluginContext service seam."""

import pytest

from app.env.registry import get_env_registry
from app.plugins.context import PluginContext
from app.plugins.events import EventBus
from app.tools.tool_manager import ToolManager


class FakeTool:
    """Minimal stand-in for a plugin tool: only needs a ``name``."""

    def __init__(self, name):
        self.name = name


def test_context_binds_shared_singletons():
    """tools must be the SHARED registry (not a fresh ToolRegistry())."""
    ctx = PluginContext()
    assert ctx.tools is ToolManager.instance()._registry
    assert ctx.env is get_env_registry()
    assert isinstance(ctx.events, EventBus)


def test_register_tool_is_visible_via_shared_registry():
    """A registered plugin tool is reachable through the shared registry."""
    ctx = PluginContext()
    tool = FakeTool("plugin.fake_tool")
    try:
        ctx.register_tool(tool, kind="native")
        assert ctx.tools.get("plugin.fake_tool") is tool
    finally:
        # Cleanup: the registry is a process-wide singleton shared by the
        # whole pytest session — fully unregister (not just cache-pop) so the
        # fake tool does not leak into other tests via _plugin_tools/_kinds.
        ctx.tools.unregister_plugin_tool("plugin.fake_tool")


def test_register_tool_requires_non_empty_name():
    ctx = PluginContext()
    with pytest.raises(ValueError):
        ctx.register_tool(object(), kind="code")


def test_emit_and_on_delegate_to_events():
    ctx = PluginContext()
    received = []

    ctx.on("plugin.event", lambda payload: received.append(payload))
    ctx.emit("plugin.event", {"n": 1})

    assert received == [{"n": 1}]


def test_absent_service_raises_attribute_error():
    """Accessing a missing service fails loudly, never returns silent None."""
    ctx = PluginContext()
    with pytest.raises(AttributeError):
        ctx.nonexistent_service
