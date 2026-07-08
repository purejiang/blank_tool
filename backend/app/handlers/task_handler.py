#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task-related handlers.

``task.delete_output`` best-effort deletes output files/folders. Every path is
containment-checked against ``get_output_dir()`` before any filesystem write,
because ``paths`` originate from renderer localStorage which is user/devtools
editable and therefore untrusted.
"""

import os
import shutil

from app.utils.env import get_output_dir
from app.utils.logger import Logger

logger = Logger.get_logger("TaskHandler")


def _is_inside_output(real_path, output_root):
    """Return True only if ``real_path`` is contained within ``output_root``.

    Uses ``os.path.commonpath`` which raises ValueError when the paths live on
    different drives (Windows) or mix absolute/relative — any such case is
    treated as "outside" (reject).
    """
    try:
        return os.path.commonpath([real_path, output_root]) == output_root
    except ValueError:
        return False


def handle_delete_output(params, stream_handler):
    paths = params.get("paths", []) or []
    output_root = os.path.realpath(get_output_dir())

    deleted = []
    failed = []

    for path in paths:
        if not path or not str(path).strip():
            continue

        real = os.path.realpath(path)

        if not _is_inside_output(real, output_root):
            logger.warning(f"Refusing to delete path outside output dir: {path}")
            failed.append({"path": path, "error": "outside output dir"})
            continue

        # Idempotent: a missing path is a no-op success.
        if not os.path.exists(real):
            deleted.append(real)
            continue

        try:
            if os.path.isfile(real):
                os.remove(real)
            elif os.path.isdir(real):
                shutil.rmtree(real, ignore_errors=True)
            deleted.append(real)
        except OSError as e:
            logger.warning(f"Failed to delete output path '{real}': {e}")
            failed.append({"path": path, "error": str(e)})

    return {"deleted": deleted, "failed": failed}


API_MAP = {
    "task.delete_output": handle_delete_output,
}
