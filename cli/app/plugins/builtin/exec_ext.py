#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EXTENDED shipped-native plugin: the non-core ``exec.code`` builtin tool.

Loaded only when ``server.config.json`` → ``tools.atomic_extensions`` selects
``exec_ext`` (or ``"*"``).  ``exec.code`` runs arbitrary Python in-process and
is intentionally kept OUT of the always-on core (the always-on execution
primitive is ``exec.shell``).
"""

from app.plugins.builtin._common import _register
from app.tools.builtin.exec_tools import CodeExec


def apply(ctx, config=None):
    """Register ``exec.code`` as a shipped-native plugin tool."""
    _register(ctx, CodeExec())
