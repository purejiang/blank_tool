#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Central task registry for cancellation support.

Streaming operations register a stop_event that the handler loop checks
periodically; cancel() signals that event so the handler exits early.
"""

import threading
import time
from typing import Any

from app.utils.logger import Logger
from app.utils.task_log_writer import cleanup_task_log


class TaskManager:
    """Thread-safe singleton that tracks cancellable tasks."""

    _instance: "TaskManager | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "TaskManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._tasks: dict[str, dict[str, Any]] = {}
                    cls._instance._tasks_lock = threading.Lock()
                    cls._instance._logger = Logger.get_logger("TaskManager")
        return cls._instance

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_stream(self, task_id: str, stop_event: threading.Event) -> None:
        """Register a streaming task so stop_event can be set on cancel.

        If the task_id was already registered, the stop_event is added to
        the existing entry.
        """
        with self._tasks_lock:
            if task_id in self._tasks:
                self._tasks[task_id]["stop_event"] = stop_event
            else:
                self._tasks[task_id] = {
                    "stop_event": stop_event,
                    "cancelled": False,
                    "entered_at": time.time(),
                }

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def cancel(self, task_id: str) -> bool:
        """Cancel a running task: signal its stop_event.

        Returns True if the task was found and cancelled, False if it had
        already completed / didn't exist.
        """
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if not task:
                self._logger.info(f"Task {task_id}: cancel called but task not found")
                return False
            task["cancelled"] = True

        self._logger.info(f"Task {task_id}: cancel requested")

        # Signal streaming operations via stop_event
        stop_event: threading.Event | None = task.get("stop_event")
        if stop_event:
            self._logger.info(f"Task {task_id}: setting stop_event")
            stop_event.set()

        # Keep the entry with cancelled=True so is_cancelled() still
        # returns True when the handler thread checks it.  The handler's
        # finally block will call unregister() to pop it.
        return True

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def is_cancelled(self, task_id: str) -> bool:
        """Return True if cancel() has been called for this task.

        Streaming handlers call this in their read loop to decide whether
        to exit early.
        """
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            return task["cancelled"] if task else False

    def unregister(self, task_id: str) -> None:
        """Cleanly remove a task entry after successful completion.
        
        Also flushes any pending buffered log lines to disk via
        :func:`~app.utils.task_log_writer.cleanup_task_log`.
        """
        try:
            cleanup_task_log(task_id)
        except Exception:
            pass  # best-effort; log cleanup failure shouldn't block task teardown
        with self._tasks_lock:
            self._tasks.pop(task_id, None)

    def list_tasks(self) -> list[dict]:
        """Return a read-only snapshot of registered tasks.

        Must NOT expose process_holder (contains Popen — not serializable).
        """
        with self._tasks_lock:
            snapshot = []
            for task_id, info in self._tasks.items():
                snapshot.append({
                    "task_id": task_id,
                    "type": "streaming" if info.get("stop_event") else "blocking",
                    "started_at": info.get("entered_at"),
                    "cancelled": info.get("cancelled", False),
                    "has_process": bool(info.get("process_holder", {}).get("process")),
                })
            return snapshot
