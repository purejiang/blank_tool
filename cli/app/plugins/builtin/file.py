#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shipped-native plugin registering the six ``file.*`` builtin tools."""

from app.plugins.builtin._common import _register
from app.tools.builtin.file_tools import (
    FileCopy,
    FileDelete,
    FileHash,
    FileMove,
    FileRead,
    FileWrite,
)


def apply(ctx, config=None):
    """Register the ``file.*`` builtins as shipped-native plugin tools."""
    for tool in (
        FileRead(),
        FileWrite(),
        FileCopy(),
        FileMove(),
        FileDelete(),
        FileHash(),
    ):
        _register(ctx, tool)
