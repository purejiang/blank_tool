#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run-scoped task handlers.

Everything in this module is keyed by a **run identity** (``task_id`` = the
JSON-RPC request id / CLI task id), not by a task-definition name: per-run logs,
per-run working directories and their outputs.  Task *definitions* — the saved
"workflow + inputs" objects — live in :mod:`app.handlers.task_def_handler`.

``task.delete_output`` best-effort deletes output files/folders. Every path is
containment-checked against ``get_output_dir()`` before any filesystem write,
because ``paths`` originate from renderer localStorage which is user/devtools
editable and therefore untrusted.

``run.list`` reports the in-flight runs registered with
:class:`~app.common.task_manager.TaskManager`; terminal runs live in the
history store (``app.history.store``).  It was previously published as
``task.list`` — renamed when ``task.*`` was given to the task-definition entity.
"""

import os
import shutil

from app.common.task_manager import TaskManager
from app.env import get_output_dir, get_task_dir, get_tasks_root
from app.utils.file_tail import tail_bytes
from app.utils.logger import Logger
from app.utils.task_log_writer import append_task_log

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


def handle_read_log(params, stream_handler):
    task_id = params.get("task_id", "")
    if not task_id:
        return {"content": "", "truncated": False, "size": 0, "log_path": ""}

    try:
        log_path = os.path.join(get_task_dir(task_id), "logs", "task_exec.log")
    except ValueError as e:
        logger.warning(f"Invalid task_id for read_log: {e}")
        return {"content": "", "truncated": False, "size": 0, "error": str(e), "log_path": ""}

    if not os.path.exists(log_path):
        return {"content": "", "truncated": False, "size": 0, "log_path": log_path}

    try:
        tail_bytes_param = params.get("tail_bytes")
        max_bytes = None
        if tail_bytes_param is not None and isinstance(tail_bytes_param, (int, float)) and tail_bytes_param > 0:
            max_bytes = int(tail_bytes_param)
        result = tail_bytes(log_path, max_bytes)

        return {"content": result.content, "truncated": result.truncated, "size": result.size, "log_path": result.log_path}
    except Exception as e:
        logger.warning(f"Failed to read task log '{log_path}': {e}")
        return {"content": "", "truncated": False, "size": 0, "error": str(e), "log_path": log_path}


def handle_append_log(params, stream_handler):
    task_id = params.get("task_id", "")
    line = params.get("line", "")
    if not task_id or not line:
        return {"written": False}
    append_task_log(str(task_id), line)
    return {"written": True}


def handle_delete_task_dir(params, stream_handler):
    task_id = params.get("task_id", "")
    if not task_id:
        return {"deleted": False, "path": "", "error": "empty task_id"}

    try:
        path = get_task_dir(task_id)
    except ValueError as e:
        logger.warning(f"Invalid task_id for delete_task_dir: {e}")
        return {"deleted": False, "path": str(task_id), "error": str(e)}
    real_path = os.path.realpath(path)
    tasks_root = os.path.realpath(get_tasks_root())

    if not _is_inside_output(real_path, tasks_root):
        logger.warning(f"Refusing to delete task dir outside tasks dir: {path}")
        return {"deleted": False, "path": path, "error": "outside tasks dir"}

    try:
        shutil.rmtree(real_path, ignore_errors=True)
        return {"deleted": True, "path": path}
    except Exception as e:
        logger.warning(f"Failed to delete task dir '{real_path}': {e}")
        return {"deleted": False, "path": path, "error": str(e)}


def handle_list_runs(params, stream_handler):
    """Return a snapshot of all registered (in-flight) runs.

    Registered with :class:`TaskManager` under a **run identity** (the JSON-RPC
    request id), so this lists what is running right now — terminal runs live
    in the history store instead.  Named ``run.list``: ``task.*`` belongs to the
    task-definition entity (see :mod:`app.handlers.task_def_handler`).
    """
    return {"runs": TaskManager().list_tasks()}


def handle_cancel_request(params, stream_handler):
    """Cancel a task by request_id. Returns {cancelled: bool}."""
    request_id = str(params.get("request_id") or params.get("task_id") or "")
    if not request_id:
        return {"cancelled": False, "message": "Missing request_id"}
    cancelled = TaskManager().cancel(request_id)
    if cancelled:
        return {"cancelled": True, "task_id": request_id}
    return {"cancelled": False, "task_id": request_id, "message": "Task not found or already completed"}


API_MAP = {
    "task.delete_output": handle_delete_output,
    "task.read_log": handle_read_log,
    "task.append_log": handle_append_log,
    "task.delete_task_dir": handle_delete_task_dir,
    "run.list": handle_list_runs,
    "request.cancel": handle_cancel_request,
}
