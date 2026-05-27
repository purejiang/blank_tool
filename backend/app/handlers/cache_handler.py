#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cache and output directory management handlers.
"""

import os
import shutil

from app.utils.logger import Logger
from app.utils.env import get_env, resolve_path, get_output_dir
from app.common.exceptions import ToolException

logger = Logger.get_logger("CacheHandler")


def _cache_root():
    cache_dir = get_env("BT_CACHE_DIR", "./cache")
    return resolve_path(cache_dir)


def _output_root():
    return get_output_dir()


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


def cache_info(params, stream_handler):
    cache_root = _cache_root()
    output_root = _output_root()

    try:
        cache_size, cache_files = _get_dir_size(cache_root)
        output_size, output_files = _get_dir_size(output_root)

        return {
            "cache": {
                "path": cache_root,
                "size": cache_size,
                "files": cache_files,
            },
            "output": {
                "path": output_root,
                "size": output_size,
                "files": output_files,
            },
            "total": {
                "size": cache_size + output_size,
                "files": cache_files + output_files,
            },
        }
    except Exception as e:
        logger.error(f"Failed to get cache info: {e}")
        raise


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
        except Exception:
            pass
    return True


def cache_clear(params, stream_handler):
    root = _cache_root()
    try:
        _clear_directory(root)
        return {"path": root, "size": 0, "files": 0}
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise


def output_clear(params, stream_handler):
    root = _output_root()
    try:
        _clear_directory(root)
        return {"path": root, "size": 0, "files": 0}
    except Exception as e:
        logger.error(f"Failed to clear output: {e}")
        raise


def storage_clear(params, stream_handler):
    target = params.get("target", "all")

    cleared_paths = []

    try:
        if target in ["all", "cache"]:
            cache_root = _cache_root()
            if _clear_directory(cache_root):
                cleared_paths.append(cache_root)

        if target in ["all", "output"]:
            output_root = _output_root()
            if _clear_directory(output_root):
                cleared_paths.append(output_root)

        return {"success": True, "cleared_paths": cleared_paths}
    except Exception as e:
        logger.error(f"Failed to clear storage: {e}")
        raise


API_MAP = {
    "cache.get_info": cache_info,
    "cache.info": cache_info,
    "cache.clear": cache_clear,
    "output.clear": output_clear,
    "storage.clear": storage_clear,
}
