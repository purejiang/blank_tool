#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Storage directory management handlers.

Three top-level directories, each with independent lifecycle:
  - tasks/   user work products (signed APKs, decompiled sources)
  - output/  standalone exports
  - logs/    backend diagnostic logs (3-day rotation)

``output/`` also hosts five *managed* subdirectories whose contents are user
data, not cache: ``templates/`` (saved workflows), ``task_defs/`` (saved task
definitions — a workflow plus the inputs to run it with), ``history/`` (run
records), ``runs/`` (per-run artifacts) and ``registry/`` (user tool/env
overrides), plus the ``plugins.json`` user plugin manifest.  Bulk clears
(``output.clear``, ``storage.clear {target:"all"|"output"}``) skip them by
default; ``include_managed: true`` restores the old wipe-everything behaviour,
and ``target:"templates"|"task_defs"|"history"|"runs"|"registry"`` clears
exactly one of them on purpose.
"""

import os
import shutil

from app.utils.logger import Logger
from app.env import get_output_dir, get_tasks_root
from app.common.exceptions import ToolException
from app.common.decorators import logs_errors

logger = Logger.get_logger("StorageHandler")

#: ``output/`` subdirectories holding user data — never wiped implicitly.
#: ``task_defs`` holds saved task definitions (see ``app.task.store``); wiping
#: it would silently drop every reusable execution configuration.
_MANAGED_SUBDIRS = ("templates", "task_defs", "history", "runs", "registry")

#: ``output/`` plain files holding user data — the user plugin manifest lives
#: there (see ``app.plugins.manifest``); wiping it would silently drop the user
#: plugin registrations, so bulk clears skip it too.
_PROTECTED_FILES = ("plugins.json",)

#: ``storage.clear`` targets that address exactly one managed subdirectory
#: (``registry`` and ``task_defs`` are included so the blocks
#: ``cache.info.managed`` advertises can actually be cleared on purpose — they
#: stay excluded from bulk clears).  Both are high-risk: ``registry`` drops
#: custom tool/env paths and imported descriptors, ``task_defs`` drops every
#: saved task definition.
_MANAGED_TARGETS = ("templates", "task_defs", "history", "runs", "registry")


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


def _managed_dir(name: str) -> str:
    return os.path.join(_output_root(), name)

def _dir_block(path):
    size, files = _get_dir_size(path)
    return {"path": path, "size": size, "files": files}


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
        # Managed subdirs of output/ — user data, reported separately so the UI
        # can show (and deliberately clear) them one by one.
        "managed": {
            name: _dir_block(_managed_dir(name)) for name in _MANAGED_SUBDIRS
        },
    }



def _clear_directory(path, exclude=()):
    """Remove every entry of *path*, skipping the names in *exclude*.

    The directory itself is kept. Returns ``False`` when *path* is missing.
    """
    if not os.path.exists(path):
        return False

    excluded = set(exclude)
    for entry in os.listdir(path):
        if entry in excluded:
            continue
        p = os.path.join(path, entry)
        try:
            if os.path.isfile(p) or os.path.islink(p):
                os.remove(p)
            elif os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Failed to remove entry '{p}': {e}")
    return True


def _clear_and_report(root, exclude=()):
    """Clear a directory and report the standard cache-clear result shape."""
    _clear_directory(root, exclude=exclude)
    return {"path": root, "size": 0, "files": 0}


@logs_errors("StorageHandler")
def output_clear(params, stream_handler):
    # Both the managed subdirs and the user plugin manifest are user data, not
    # cache: clearing "output" must not silently drop saved workflows, run
    # history/artifacts, registry overlays or plugin registrations.
    return _clear_and_report(
        _output_root(), exclude=_MANAGED_SUBDIRS + _PROTECTED_FILES
    )


@logs_errors("StorageHandler")
def storage_clear(params, stream_handler):
    target = params.get("target", "all")
    # Escape hatch: restore the pre-WP4 wipe-everything behaviour.
    include_managed = params.get("include_managed") is True
    managed_exclude = () if include_managed else (_MANAGED_SUBDIRS + _PROTECTED_FILES)

    cleared_paths = []

    if target in ["all", "tasks"]:
        tasks_root = _tasks_root()
        if _clear_directory(tasks_root):
            cleared_paths.append(tasks_root)

    if target in ["all", "output"]:
        output_root = _output_root()
        if _clear_directory(output_root, exclude=managed_exclude):
            cleared_paths.append(output_root)

    if target in ["all", "logs"]:
        logs_root = _logs_root()
        if logs_root and _clear_directory(logs_root):
            cleared_paths.append(logs_root)

    if target in _MANAGED_TARGETS:
        managed_root = _managed_dir(target)
        if _clear_directory(managed_root):
            cleared_paths.append(managed_root)

    return {"success": True, "cleared_paths": cleared_paths}


@logs_errors("StorageHandler")
def tasks_clear(params, stream_handler):
    return _clear_and_report(_tasks_root())


@logs_errors("StorageHandler")
def logs_clear(params, stream_handler):
    root = _logs_root()
    if not root:
        raise ToolException("Log directory not available")
    return _clear_and_report(root)


API_MAP = {
    "cache.get_info": cache_info,
    "cache.info": cache_info,
    "output.clear": output_clear,
    "tasks.clear": tasks_clear,
    "logs.clear": logs_clear,
    "storage.clear": storage_clear,
}
