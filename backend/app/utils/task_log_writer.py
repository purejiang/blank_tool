#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Per-task log writer with thread safety and a soft size cap.

Separate from the global Logger — this is a simple file appender that lives
alongside each task's working directory. Lines are written to disk
immediately (no in-memory buffering), so they survive a hard kill of the app
mid-task.  A per-task lock guards concurrent writers, and a size cap keeps
individual log files bounded.
"""

import os
import sys
import threading

from app.utils.env import get_task_subdir

#: Upper bound before truncation kicks in (bytes).
_SIZE_CAP = 50 * 1024 * 1024

#: Number of bytes to keep from the *end* of the file when truncating.
_TAIL_SIZE = 20 * 1024 * 1024

#: Per-task write locks — keyed by ``task_id``.
_per_task_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_lock(task_id: str) -> threading.Lock:
    """Return (creating if needed) the ``threading.Lock`` for *task_id*."""
    with _locks_lock:
        if task_id not in _per_task_locks:
            _per_task_locks[task_id] = threading.Lock()
        return _per_task_locks[task_id]


def append_task_log(task_id: str, line: str) -> None:
    """
    Append *line* to the per-task log file on disk immediately.

    Thread-safe per task.  The file is created on first write and the size cap
    is enforced after every write.  This function never raises — on failure it
    writes a message to *stderr*.
    """
    try:
        lock = _get_lock(task_id)
        with lock:
            logs_dir = get_task_subdir(task_id, "logs")
            path = os.path.join(logs_dir, "task_exec.log")
            os.makedirs(logs_dir, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            size = os.path.getsize(path)
            if size > _SIZE_CAP:
                _truncate_to_tail(path, size)
    except Exception:
        print(
            f"[task_log_writer] Failed to write log for task {task_id}",
            file=sys.stderr,
        )


def flush_task_log(task_id: str) -> None:
    """
    Compatibility shim — lines are written to disk immediately, so there is
    nothing to flush.  Kept for callers that used the old buffered writer.
    """
    _ = task_id


def cleanup_task_log(task_id: str) -> None:
    """Release the per-task lock entry (and any leftover state) for *task_id*."""
    with _locks_lock:
        _per_task_locks.pop(task_id, None)


def _truncate_to_tail(path: str, current_size: int) -> None:
    """
    Keep only the last ``_TAIL_SIZE`` bytes of the file at *path*.

    Opens the file in binary read-write mode, seeks to the keep-offset,
    reads the tail, rewinds to the beginning, overwrites, and truncates.
    """
    try:
        keep_from = max(0, current_size - _TAIL_SIZE)
        with open(path, "rb+") as f:
            f.seek(keep_from)
            tail = f.read()
            f.seek(0)
            f.write(tail)
            f.truncate()
    except Exception:
        print(
            f"[task_log_writer] Failed to truncate {path}",
            file=sys.stderr,
        )
