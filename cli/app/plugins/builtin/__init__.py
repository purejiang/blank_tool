#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shipped-native builtin plugins.

Each module in this package registers a subset of the 23 builtin primitives
(from ``app.tools.builtin.*``) into the shared tool registry as kind
``"shipped-native"``.  The loader wires these in via
``app.plugins.loader.SHIPPED_MANIFEST`` so they are ALWAYS loaded at startup,
in addition to any user ``native`` plugins from config.
"""
