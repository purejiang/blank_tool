#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shipped-native plugin registering the three ``dir.*`` builtin tools."""

from app.plugins.builtin._common import _register
from app.tools.builtin.dir_tools import DirCreate, DirDelete, DirList


def apply(ctx, config=None):
    """Register the ``dir.*`` builtins as shipped-native plugin tools."""
    for tool in (DirList(), DirCreate(), DirDelete()):
        _register(ctx, tool)
