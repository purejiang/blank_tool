#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helper for the shipped-native builtin plugin modules.

Exposes :func:`_register`, the single idempotent-registration seam used by
every ``app.plugins.builtin.*`` module's ``apply``.  Because ``plugin.reload``
re-runs ``apply`` while shipped-native plugins stay resident (reviewer rule
R2), re-registering a name that is already present would otherwise trip
``ToolRegistry.register_plugin_tool``'s "already registered" ValueError —
so registration is skipped when the tool is already registered with kind
``"shipped-native"``.
"""


def _register(ctx, tool):
    """Register *tool* as ``shipped-native``, idempotently (reload-safe).

    Args:
        ctx: the :class:`~app.plugins.context.PluginContext` handed to
            ``apply`` (anything exposing ``tools`` + ``register_tool``).
        tool: a ``BuiltinTool`` instance to register.

    Returns:
        The registered *tool* (or the already-resident instance when the
        name is already present as ``"shipped-native"``).
    """
    get_kind = getattr(ctx.tools, "get_kind", None)
    if callable(get_kind) and get_kind(tool.name) == "shipped-native":
        return tool
    return ctx.register_tool(tool, kind="shipped-native")
