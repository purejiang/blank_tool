#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shipped-native plugin registering the two ``text.*`` builtin tools."""

from app.plugins.builtin._common import _register
from app.tools.builtin.text_tools import TextGrep, TextReplace


def apply(ctx, config=None):
    """Register the ``text.*`` builtins as shipped-native plugin tools."""
    for tool in (TextGrep(), TextReplace()):
        _register(ctx, tool)
