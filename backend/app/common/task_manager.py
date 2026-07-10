#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Central task registry for cancellation support.

Blocking operations (apktool, jarsigner) register a process_holder so the
subprocess can be killed on cancel. Streaming operations register a
stop_event that the handler loop checks periodically.
"""

import os
import shutil
import subprocess
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

    def register(
        self,
        task_id: str,
        process_holder: dict | None = None,
        cleanup_paths: list[str] | None = None,
    ) -> None:
        """Register a blocking task so it can be killed on cancel."""
        with self._tasks_lock:
            self._tasks[task_id] = {
                "process_holder": process_holder if process_holder is not None else {},
                "cleanup_paths": cleanup_paths or [],
                "stop_event": None,
                "cancelled": False,
            }
        self._logger.info(
            f"Task {task_id}: registered (holder_id={id(process_holder) if process_holder is not None else 'none'})"
        )

    def register_stream(self, task_id: str, stop_event: threading.Event) -> None:
        """Register a streaming task so stop_event can be set on cancel.

        If the task_id was already registered (e.g. by a blocking pre-step),
        the stop_event is added to the existing entry.
        """
        with self._tasks_lock:
            if task_id in self._tasks:
                self._tasks[task_id]["stop_event"] = stop_event
            else:
                self._tasks[task_id] = {
                    "process_holder": {},
                    "cleanup_paths": [],
                    "stop_event": stop_event,
                    "cancelled": False,
                }

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def cancel(self, task_id: str) -> bool:
        """Cancel a running task: signal stop, kill process, clean up files.

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

        # 1. Signal streaming operations via stop_event
        stop_event: threading.Event | None = task.get("stop_event")
        if stop_event:
            self._logger.info(f"Task {task_id}: setting stop_event")
            stop_event.set()

        # 2. Kill subprocess for blocking operations (if one exists)
        holder: dict = task.get("process_holder", {})
        proc: subprocess.Popen | None = holder.get("process") if holder else None

        if proc is None and holder and not stop_event:
            # Blocking op — process might not be spawned yet. Wait briefly.
            self._logger.info(
                f"Task {task_id}: process not spawned yet, waiting up to 2s"
            )
            deadline = time.time() + 2.0
            while proc is None and time.time() < deadline:
                time.sleep(0.05)
                proc = holder.get("process")

        if proc is not None and proc.poll() is None:
            self._logger.info(f"Task {task_id}: terminating PID {proc.pid}")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._logger.warning(
                    f"Task {task_id}: graceful terminate timed out, force-killing"
                )
                proc.kill()
                proc.wait()
            self._logger.info(f"Task {task_id}: process terminated")
        elif proc is None and holder and not stop_event:
            # Still no process for blocking op — mark pending cancel
            self._logger.warning(
                f"Task {task_id}: process still not available after 2s, "
                f"setting _cancel_pending flag"
            )
            holder["_cancel_pending"] = True
        elif proc is not None:
            self._logger.info(
                f"Task {task_id}: process already exited (rc={proc.poll()})"
            )

        # 3. Clean up partial output files
        for path in task.get("cleanup_paths", []):
            if not path or not os.path.exists(path):
                continue
            try:
                if os.path.isfile(path) or os.path.islink(path):
                    os.remove(path)
                    self._logger.info(f"Task {task_id}: removed partial file {path}")
                elif os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                    self._logger.info(f"Task {task_id}: removed partial dir {path}")
            except OSError as e:
                self._logger.warning(
                    f"Task {task_id}: cleanup failed for {path}: {e}"
                )

        # Keep the entry with cancelled=True so is_cancelled() still
        # returns True when the handler thread checks it after the kill.
        # The handler's finally block will call unregister() to pop it.
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
