#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shipped-native plugin registering the CORE ``text.grep`` builtin tool.

``text.replace`` lives in the EXTENDED pack (``app.plugins.builtin.text_ext``).
"""

from app.plugins.builtin._common import _register
from app.tools.builtin.text_tools import TextGrep


def apply(ctx, config=None):
    """Register the core ``text.*`` builtin as a shipped-native plugin tool."""
    _register(ctx, TextGrep())
