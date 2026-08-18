#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shipped-native plugin registering the two exec builtin tools.

Registers ``shell.exec`` and ``code.exec`` (from
``app.tools.builtin.exec_tools``).
"""

from app.plugins.builtin._common import _register
from app.tools.builtin.exec_tools import CodeExec, ShellExec


def apply(ctx, config=None):
    """Register ``shell.exec`` and ``code.exec`` as shipped-native tools."""
    for tool in (ShellExec(), CodeExec()):
        _register(ctx, tool)
