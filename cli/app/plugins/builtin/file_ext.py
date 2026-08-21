#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EXTENDED shipped-native plugin: the four non-core ``file.*`` builtin tools.

Loaded only when ``server.config.json`` → ``tools.atomic_extensions`` selects
``file_ext`` (or ``"*"``).  These are native ``BuiltinTool`` instances (no
subprocess, no descriptor) — the "atomic tool extensions" tier, distinct from
external descriptor tools.
"""

from app.plugins.builtin._common import _register
from app.tools.builtin.file_tools import FileCopy, FileDelete, FileHash, FileMove


def apply(ctx, config=None):
    """Register the extended ``file.*`` builtins as shipped-native plugin tools."""
    for tool in (FileCopy(), FileMove(), FileDelete(), FileHash()):
        _register(ctx, tool)
