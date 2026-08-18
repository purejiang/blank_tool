#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shipped-native plugin registering the two ``archive.*`` builtin tools."""

from app.plugins.builtin._common import _register
from app.tools.builtin.archive_tools import ArchiveCreate, ArchiveExtract


def apply(ctx, config=None):
    """Register the ``archive.*`` builtins as shipped-native plugin tools."""
    for tool in (ArchiveExtract(), ArchiveCreate()):
        _register(ctx, tool)
