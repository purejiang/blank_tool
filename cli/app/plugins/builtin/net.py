#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shipped-native plugin registering the two ``net.*`` builtin tools."""

from app.plugins.builtin._common import _register
from app.tools.builtin.net_tools import NetDownload, NetRequest


def apply(ctx, config=None):
    """Register the ``net.*`` builtins as shipped-native plugin tools."""
    for tool in (NetDownload(), NetRequest()):
        _register(ctx, tool)
