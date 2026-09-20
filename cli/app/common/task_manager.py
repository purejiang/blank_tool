#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Central run registry for cancellation support.

A *run* is one top-level workflow execution.  It is registered by the IPC
layer the moment its request is dispatched and unregistered when the handler
returns.  Entries are keyed by ``run_id`` (the JSON-RPC request id) so two
concurrent runs never clobber each other's registration; a ``task_id`` index
lets the UI cancel by the id it knows about.

Cancellation contract
---------------------
``cancel()`` marks the run cancelled and additionally SIGTERM's the
subprocess the run is currently executing (when one is attached via
:meth:`attach_process`), so a long tool call stops instead of running to
completion.  Workflow code observes cancellation through
:meth:`is_cancelled` at well-defined checkpoints.

A cancel that arrives *before* its run registers (the cancel request can be
dispatched concurrently with the execute request) is remembered as a
short-lived tombstone and consumed by the matching :meth:`register` call, so
a cancel is never silently lost.  A cancel naming a run that *recently
finished* is simply rejected — it must not poison the next run that happens
to reuse the same id.
"""

import threading
import time
from typing import Any, Dict, Optional, Set

from app.common import proc_tree
from app.utils.logger import Logger
from app.utils.task_log_writer import cleanup_task_log

#: How long a "cancel arrived before register" tombstone stays armed.
_TOMBSTONE_TTL_SECONDS = 10.0

#: How long a finished run id / task id is remembered, so a late cancel for
#: it is rejected instead of being treated as a cancel of a future run.
_SEEN_TTL_SECONDS = 60.0

#: How long a tree kill may take before the cancel path gives up on it.  The
#: cancel request is answered on the same thread, so this stays short.
_TERMINATE_GRACE_SECONDS = 2.0


class TaskManager:
    """Thread-safe singleton that tracks cancellable runs."""

    _instance: "TaskManager | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "TaskManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._tasks: Dict[str, Dict[str, Any]] = {}
                    cls._instance._by_task: Dict[str, Set[str]] = {}
                    cls._instance._tombstones: Dict[str, float] = {}
                    cls._instance._seen: Dict[str, float] = {}
                    cls._instance._tasks_lock = threading.Lock()
                    cls._instance._logger = Logger.get_logger("TaskManager")
        return cls._instance

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        run_id: str,
        task_id: str = "",
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        """Register *run_id* as an in-flight run.

        Re-registering an existing ``run_id`` resets its cancelled flag: the
        id now denotes a NEW run, and it must not inherit the previous run's
        cancellation.  A tombstone planted for this ``run_id`` or
        ``task_id`` (cancel-before-register) is consumed and turns the
        registration cancelled immediately.
        """
        if not run_id:
            return
        task_id = str(task_id or "")
        now = time.time()
        with self._tasks_lock:
            cancelled = self._consume_tombstone(run_id, now) or (
                self._consume_tombstone(task_id, now) if task_id else False
            )
            self._tasks[run_id] = {
                "task_id": task_id,
                "stop_event": stop_event,
                "holder": None,
                "cancelled": bool(cancelled),
                "entered_at": now,
            }
            if task_id:
                self._by_task.setdefault(task_id, set()).add(run_id)
        if cancelled:
            self._logger.info(f"Run {run_id}: pre-registration cancel honored")

    def unregister(self, run_id: str) -> None:
        """Remove *run_id* after completion and flush its buffered task log."""
        try:
            cleanup_task_log(run_id)
        except Exception:
            pass  # best-effort; log cleanup failure shouldn't block teardown
        now = time.time()
        with self._tasks_lock:
            entry = self._tasks.pop(run_id, None)
            task_id = (entry or {}).get("task_id", "")
            if task_id and task_id in self._by_task:
                self._by_task[task_id].discard(run_id)
                if not self._by_task[task_id]:
                    self._by_task.pop(task_id, None)
            self._seen[run_id] = now
            if task_id:
                self._seen[task_id] = now
            self._prune_expired(now)

    def attach_process(self, run_id: str, holder: Optional[dict]) -> None:
        """Attach (or clear, with ``None``) the subprocess holder of *run_id*.

        The holder is the dict a command executor stores its ``Popen`` in, so
        :meth:`cancel` can terminate a running tool instead of waiting for it.
        """
        if not run_id:
            return
        with self._tasks_lock:
            entry = self._tasks.get(run_id)
            if entry is not None:
                entry["holder"] = holder

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def cancel(self, target: str) -> bool:
        """Cancel a run and terminate its subprocess.

        Args:
            target: a ``run_id`` or a ``task_id``.  A ``task_id`` cancels
                every run currently registered under it.

        Returns:
            True when a run was cancelled OR a tombstone was armed for a run
            that has not registered yet; False when the target names a run
            that already finished / never existed.
        """
        if not target:
            return False
        target = str(target)
        now = time.time()
        holders: list = []
        found = False

        with self._tasks_lock:
            run_ids = [target] if target in self._tasks else []
            if not run_ids:
                run_ids = [
                    rid for rid in self._by_task.get(target, set())
                    if rid in self._tasks
                ]
            for rid in run_ids:
                entry = self._tasks[rid]
                if entry.get("cancelled"):
                    found = True
                    continue
                entry["cancelled"] = True
                found = True
                stop_event = entry.get("stop_event")
                if stop_event is not None:
                    holders.append(("event", stop_event))
                holder = entry.get("holder")
                if holder is not None:
                    holders.append(("process", holder))

            if not found:
                if self._seen.get(target, 0.0) + _SEEN_TTL_SECONDS > now:
                    # Recently finished: a late cancel, not a future run.
                    self._logger.info(
                        f"Cancel for {target}: already completed"
                    )
                    return False
                self._tombstones[target] = now
                self._prune_expired(now)
                self._logger.info(
                    f"Cancel for {target}: no run yet — tombstone armed"
                )
                return True

        self._logger.info(f"Cancel requested for {target}")
        for kind, payload in holders:
            if kind == "event":
                self._logger.info(f"Run {target}: setting stop_event")
                try:
                    payload.set()
                except Exception:
                    pass
            else:
                self._terminate(payload)
        return True

    def _terminate(self, holder: dict) -> None:
        """Mark the holder cancelled and kill its process tree, if any.

        The job object is the authoritative kill: it covers the whole tree
        (``cmd.exe`` plus the command it started), including grandchildren
        whose parent already exited.  Only when no job handle is present does
        this fall back to tree tools and finally to ``Popen.terminate()``.
        """
        holder["_cancel_pending"] = True
        if proc_tree.terminate_job_in(holder):
            self._logger.info(
                "Terminated the job object covering the run's process tree"
            )
            return
        process = holder.get("process")
        if process is None:
            return
        try:
            if process.poll() is None:
                self._logger.info(f"Terminating subprocess tree pid={process.pid}")
                if not proc_tree.terminate_tree(
                    process.pid, grace=_TERMINATE_GRACE_SECONDS
                ):
                    process.terminate()
        except Exception as exc:  # already gone / not a Popen
            self._logger.warning(f"Failed to terminate subprocess: {exc}")

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def is_cancelled(self, target: str) -> bool:
        """Return True when *target* (run id or task id) is cancelled.

        A still-armed tombstone counts as cancelled so a run that registers
        after the user clicked cancel aborts at its first checkpoint.
        """
        if not target:
            return False
        target = str(target)
        now = time.time()
        with self._tasks_lock:
            entry = self._tasks.get(target)
            if entry is not None:
                return bool(entry["cancelled"])
            for rid in self._by_task.get(target, set()):
                other = self._tasks.get(rid)
                if other is not None and other["cancelled"]:
                    return True
            return self._tombstone_active(target, now)

    def list_tasks(self) -> list:
        """Return a read-only snapshot of registered (in-flight) runs."""
        with self._tasks_lock:
            return [
                {
                    "run_id": run_id,
                    "task_id": info.get("task_id", ""),
                    "cancelled": bool(info.get("cancelled", False)),
                    "started_at": info.get("entered_at"),
                    "has_process": bool(
                        (info.get("holder") or {}).get("process")
                    ),
                }
                for run_id, info in self._tasks.items()
            ]

    # ------------------------------------------------------------------
    # Internal helpers (called with _tasks_lock held)
    # ------------------------------------------------------------------

    def _consume_tombstone(self, key: str, now: float) -> bool:
        """Pop a still-armed tombstone for *key*; True when one was armed."""
        planted = self._tombstones.pop(key, None)
        return planted is not None and planted + _TOMBSTONE_TTL_SECONDS > now

    def _tombstone_active(self, key: str, now: float) -> bool:
        planted = self._tombstones.get(key)
        return planted is not None and planted + _TOMBSTONE_TTL_SECONDS > now

    def _prune_expired(self, now: float) -> None:
        for key, planted in list(self._tombstones.items()):
            if planted + _TOMBSTONE_TTL_SECONDS <= now:
                self._tombstones.pop(key, None)
        for key, seen in list(self._seen.items()):
            if seen + _SEEN_TTL_SECONDS <= now:
                self._seen.pop(key, None)
