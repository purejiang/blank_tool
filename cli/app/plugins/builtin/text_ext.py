#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EXTENDED shipped-native plugin: the non-core ``text.replace`` builtin tool.

Loaded only when ``server.config.json`` → ``tools.atomic_extensions`` selects
``text_ext`` (or ``"*"``).
"""

from app.plugins.builtin._common import _register
from app.tools.builtin.text_tools import TextReplace


def apply(ctx, config=None):
    """Register ``text.replace`` as a shipped-native plugin tool."""
    _register(ctx, TextReplace())
