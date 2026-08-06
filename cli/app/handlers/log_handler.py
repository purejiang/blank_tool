#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Log-related handlers.

``logs.tail`` returns the last N lines of the current backend log file
without accepting any path parameter — it reads exclusively from the
configured log directory (``Logger.get_log_directory()``), eliminating
any path-traversal surface.
"""

import os

from app.utils.file_tail import tail_file
from app.utils.logger import Logger

logger = Logger.get_logger("LogHandler")


def handle_tail(params, stream_handler):
    """Return the last N lines of the current backend log file.

    params:
        lines (int, optional): number of lines to return, default 200, max 1000
    """
    try:
        lines_requested = int(params.get("lines", 200) or 200)
    except (TypeError, ValueError):
        lines_requested = 200
    lines_requested = max(1, min(lines_requested, 1000))

    current = Logger.get_current_log_file()

    if not current or not os.path.exists(current):
        return {
            "lines": [],
            "truncated": False,
            "log_path": str(current) if current else "",
            "process": "backend",
        }

    try:
        result = tail_file(current, lines_requested)
        return {
            "lines": result.lines,
            "truncated": result.truncated,
            "log_path": str(current),
            "process": "backend",
        }
    except Exception as e:
        logger.warning(f"Failed to read backend log: {e}")
        return {
            "lines": [],
            "truncated": False,
            "log_path": str(current),
            "error": str(e),
            "process": "backend",
        }


API_MAP = {
    "logs.tail": handle_tail,
}
