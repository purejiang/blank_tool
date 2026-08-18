#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shipped-native plugin registering the ``workflow.run`` builtin tool."""

from app.plugins.builtin._common import _register
from app.tools.builtin.workflow_tools import WorkflowRun


def apply(ctx, config=None):
    """Register ``workflow.run`` as a shipped-native plugin tool."""
    _register(ctx, WorkflowRun())
