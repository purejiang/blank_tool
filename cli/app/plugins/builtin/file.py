#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shipped-native plugin registering the two CORE ``file.*`` builtin tools.

``file.copy``/``file.move``/``file.delete``/``file.hash`` live in the EXTENDED
pack (``app.plugins.builtin.file_ext``), loaded only when enabled via
``server.config.json`` → ``tools.atomic_extensions``.
"""

from app.plugins.builtin._common import _register
from app.tools.builtin.file_tools import FileRead, FileWrite


def apply(ctx, config=None):
    """Register the core ``file.*`` builtins as shipped-native plugin tools."""
    for tool in (FileRead(), FileWrite()):
        _register(ctx, tool)
