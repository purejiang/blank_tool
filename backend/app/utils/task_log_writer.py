#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Per-task log writer with thread safety and soft size cap.

Separate from the global Logger — this is a simple file appender that lives
alongside each task's working directory.  Uses a per-task ``threading.Lock``
so different tasks can write concurrently while the same task serializes.

After every append the file size is checked.  If it exceeds 50 MB the tail
20 MB is kept and the rest discarded.
"""

import os
import sys
import threading

from app.utils.env import get_task_subdir

#: Upper bound before truncation kicks in (bytes).
_SIZE_CAP = 50 * 1024 * 1024

#: Number of bytes to keep from the *end* of the file when truncating.
_TAIL_SIZE = 20 * 1024 * 1024

#: Per-task locks — keyed by ``task_id``.
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
    Append *line* (plus a trailing newline) to ``Tasks/<task_id>/logs/task.log``.

    Directory structure is created automatically via ``get_task_subdir``.
    If the file exceeds 50 MB after the write its tail 20 MB is preserved.

    This function never raises — on failure it writes a message to *stderr*.
    """
    try:
        logs_dir = get_task_subdir(task_id, "logs")
        path = os.path.join(logs_dir, "task_exec.log")

        lock = _get_lock(task_id)
        with lock:
            # Append the line
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

            # Soft size cap
            size = os.path.getsize(path)
            if size > _SIZE_CAP:
                _truncate_to_tail(path, size)
    except Exception:
        print(
            f"[task_log_writer] Failed to append log for task {task_id}",
            file=sys.stderr,
        )


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
