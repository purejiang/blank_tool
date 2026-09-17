#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shipped-native plugin registering the CORE ``exec.shell`` builtin tool.

``exec.code`` lives in the EXTENDED pack (``app.plugins.builtin.exec_ext``).
"""

from app.plugins.builtin._common import _register
from app.tools.builtin.exec_tools import ShellExec


def apply(ctx, config=None):
    """Register ``exec.shell`` as a shipped-native plugin tool."""
    _register(ctx, ShellExec())
