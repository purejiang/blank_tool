#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Low-level adb runner shared by every automation module."""

from typing import Any, Dict, List

from app.tools.tool_manager import ToolManager
from app.common.base_executor import CommandExecutionContext
from app.common.exceptions import ToolNotFoundError
from app.utils.logger import Logger

logger = Logger.get_logger("AutomationAdb")


def run_adb(device_id: str, args: List[str], capture: bool = True) -> Dict[str, Any]:
    """Run ``adb -s <device_id> <args>`` and return the raw result dict."""
    mgr = ToolManager.instance()
    adb = mgr.get_tool("adb")
    if not adb or not getattr(adb, "is_valid", False):
        raise ToolNotFoundError("adb")
    ctx = CommandExecutionContext(capture_output=capture, log_output=False)
    return adb.execute(["-s", device_id] + list(args), ctx)
