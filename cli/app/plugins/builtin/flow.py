#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shipped-native plugin registering the two ``flow.*`` builtin tools."""

from app.plugins.builtin._common import _register
from app.tools.builtin.flow_tools import FlowAssert, FlowLog


def apply(ctx, config=None):
    """Register the ``flow.*`` builtins as shipped-native plugin tools."""
    for tool in (FlowAssert(), FlowLog()):
        _register(ctx, tool)
