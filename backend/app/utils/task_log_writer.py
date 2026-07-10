#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Per-task log writer with thread safety, buffering, and soft size cap.

Separate from the global Logger — this is a simple file appender that lives
alongside each task's working directory.  Uses per-task buffering to reduce
file operations: lines are accumulated in memory and flushed to disk in
batches (every ``_BUFFER_FLUSH_SIZE`` lines) instead of open→write→close
for every single line.

The size cap check is also deferred to batch flush time.
"""

import os
import sys
import threading

from app.utils.env import get_task_subdir

#: Upper bound before truncation kicks in (bytes).
_SIZE_CAP = 50 * 1024 * 1024

#: Number of bytes to keep from the *end* of the file when truncating.
_TAIL_SIZE = 20 * 1024 * 1024

#: Flush buffer to disk every N lines (per task).
_BUFFER_FLUSH_SIZE = 100

#: Per-task line buffers — keyed by ``task_id``.
_per_task_buffers: dict[str, list[str]] = {}

#: Per-task buffer locks — keyed by ``task_id``.
_per_task_buffer_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_buffer_lock(task_id: str) -> threading.Lock:
    """Return (creating if needed) the ``threading.Lock`` for *task_id*."""
    with _locks_lock:
        if task_id not in _per_task_buffer_locks:
            _per_task_buffer_locks[task_id] = threading.Lock()
        return _per_task_buffer_locks[task_id]


def append_task_log(task_id: str, line: str) -> None:
    """
    Append *line* to the in-memory buffer for *task_id*.

    Directory structure is created automatically via ``get_task_subdir``.
    The line is *not* written to disk immediately — it is held in a per-task
    buffer and flushed in batches (every :data:`_BUFFER_FLUSH_SIZE` lines).
    Call :func:`flush_task_log` or :func:`cleanup_task_log` to force a flush.

    This function never raises — on failure it writes a message to *stderr*.
    """
    try:
        lock = _get_buffer_lock(task_id)
        with lock:
            if task_id not in _per_task_buffers:
                _per_task_buffers[task_id] = []
            _per_task_buffers[task_id].append(line)
            if len(_per_task_buffers[task_id]) >= _BUFFER_FLUSH_SIZE:
                _flush_buffer(task_id)
    except Exception:
        print(
            f"[task_log_writer] Failed to buffer log for task {task_id}",
            file=sys.stderr,
        )


def _flush_buffer(task_id: str) -> None:
    """
    Write all buffered lines for *task_id* to disk and clear the buffer.

    Must be called while holding the buffer lock for *task_id*.
    """
    try:
        logs_dir = get_task_subdir(task_id, "logs")
        path = os.path.join(logs_dir, "task_exec.log")
        lines = _per_task_buffers.get(task_id, [])
        if not lines:
            return

        with open(path, "a", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")

        _per_task_buffers[task_id] = []

        # Size check only after batch flush
        size = os.path.getsize(path)
        if size > _SIZE_CAP:
            _truncate_to_tail(path, size)
    except Exception:
        print(
            f"[task_log_writer] Failed to flush log for task {task_id}",
            file=sys.stderr,
        )


def flush_task_log(task_id: str) -> None:
    """Explicitly flush buffered log lines to disk."""
    try:
        lock = _get_buffer_lock(task_id)
        with lock:
            _flush_buffer(task_id)
    except Exception:
        print(
            f"[task_log_writer] Failed to flush log for task {task_id}",
            file=sys.stderr,
        )


def cleanup_task_log(task_id: str) -> None:
    """Flush remaining buffer and remove buffer/lock entries for *task_id*."""
    flush_task_log(task_id)
    with _locks_lock:
        _per_task_buffers.pop(task_id, None)
        _per_task_buffer_locks.pop(task_id, None)


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
