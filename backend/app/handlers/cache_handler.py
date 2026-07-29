#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Storage directory management handlers.

Three top-level directories, each with independent lifecycle:
  - tasks/   user work products (signed APKs, decompiled sources)
  - output/  standalone exports
  - logs/    backend diagnostic logs (3-day rotation)
"""

import os
import shutil

from app.utils.logger import Logger
from app.utils.env import get_output_dir, get_tasks_root
from app.common.exceptions import ToolException
from app.common.decorators import logs_errors

logger = Logger.get_logger("StorageHandler")


def _tasks_root():
    return get_tasks_root()


def _output_root():
    return get_output_dir()


def _logs_root():
    d = Logger.get_log_directory()
    return str(d) if d else None


def _get_dir_size(path):
    total_size = 0
    total_files = 0
    if os.path.exists(path):
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total_size += os.path.getsize(fp)
                    total_files += 1
                except Exception:
                    pass
    return total_size, total_files


@logs_errors("StorageHandler")
def cache_info(params, stream_handler):
    tasks_root = _tasks_root()
    output_root = _output_root()
    logs_root = _logs_root()

    tasks_size, tasks_files = _get_dir_size(tasks_root)
    output_size, output_files = _get_dir_size(output_root)
    logs_size, logs_files = (_get_dir_size(logs_root) if logs_root else (0, 0))

    return {
        "tasks": {
            "path": tasks_root,
            "size": tasks_size,
            "files": tasks_files,
        },
        "output": {
            "path": output_root,
            "size": output_size,
            "files": output_files,
        },
        "logs": {
            "path": logs_root,
            "size": logs_size,
            "files": logs_files,
        },
        "total": {
            "size": tasks_size + output_size + logs_size,
            "files": tasks_files + output_files + logs_files,
        },
    }



def _clear_directory(path):
    if not os.path.exists(path):
        return False

    for entry in os.listdir(path):
        p = os.path.join(path, entry)
        try:
            if os.path.isfile(p) or os.path.islink(p):
                os.remove(p)
            elif os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Failed to remove entry '{p}': {e}")
    return True


@logs_errors("StorageHandler")
def output_clear(params, stream_handler):
    root = _output_root()
    _clear_directory(root)
    return {"path": root, "size": 0, "files": 0}


@logs_errors("StorageHandler")
def storage_clear(params, stream_handler):
    target = params.get("target", "all")

    cleared_paths = []

    if target in ["all", "tasks"]:
        tasks_root = _tasks_root()
        if _clear_directory(tasks_root):
            cleared_paths.append(tasks_root)

    if target in ["all", "output"]:
        output_root = _output_root()
        if _clear_directory(output_root):
            cleared_paths.append(output_root)

    if target in ["all", "logs"]:
        logs_root = _logs_root()
        if logs_root and _clear_directory(logs_root):
            cleared_paths.append(logs_root)

    return {"success": True, "cleared_paths": cleared_paths}


@logs_errors("StorageHandler")
def tasks_clear(params, stream_handler):
    root = _tasks_root()
    _clear_directory(root)
    return {"path": root, "size": 0, "files": 0}


@logs_errors("StorageHandler")
def logs_clear(params, stream_handler):
    root = _logs_root()
    if not root:
        raise ToolException("Log directory not available")
    _clear_directory(root)
    return {"path": root, "size": 0, "files": 0}


API_MAP = {
    "cache.get_info": cache_info,
    "cache.info": cache_info,
    "output.clear": output_clear,
    "tasks.clear": tasks_clear,
    "logs.clear": logs_clear,
    "storage.clear": storage_clear,
}
