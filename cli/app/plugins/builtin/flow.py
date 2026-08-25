#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shipped-native plugin registering the five ``flow.*`` builtin tools."""

from app.plugins.builtin._common import _register
from app.tools.builtin.flow_tools import (
    FlowAssert,
    FlowBranch,
    FlowCompare,
    FlowForeach,
    FlowLog,
)


def apply(ctx, config=None):
    """Register the ``flow.*`` builtins as shipped-native plugin tools."""
    for tool in (
        FlowAssert(),
        FlowLog(),
        FlowForeach(),
        FlowBranch(),
        FlowCompare(),
    ):
        _register(ctx, tool)
