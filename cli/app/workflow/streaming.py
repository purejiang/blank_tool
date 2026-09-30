#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workflow streaming events and cancellation.

This module defines the event schema a workflow engine emits while executing
nodes, plus :class:`WorkflowStreamHandler` — a thin wrapper around the
existing ``stream_handler`` callback (the IPC callback that forwards events
to the renderer).  It deliberately adds NO new IPC channel: events are
delivered over the existing ``stream-event`` channel.  The main process
routes on ``result.type`` (see ``src/main/ipc/commandHandlers.ts``); workflow
event types are NOT in the logcat ``channelMap``, so they fall through to the
generic ``streamEvent`` branch.  On the wire the *routing* key is
``stream_id`` (the request id set by ``ApiHandler.stream_handler``).

Event schema (dicts passed to the stream callback)::

    node_started        {type, ts, run_id, workflow_id, workflow_name, node_id, tool}
    node_completed      {type, ts, run_id, workflow_id, workflow_name, node_id,
                         status, duration_ms, attempts, error?}
    log                 {type, ts, run_id?, workflow_id?, workflow_name?, level,
                         message, node_id}
    workflow_completed  {type, ts, run_id, workflow_id, workflow_name, success}
    workflow_failed     {type, ts, run_id, workflow_id, workflow_name, error}
    workflow_cancelled  {type, ts, run_id, workflow_id, workflow_name}

Field semantics:
    ``run_id``
        Identifier of the TOP-LEVEL run.  Never rewritten by nesting, so a
        consumer can group every event of one run.
    ``workflow_id``
        Storage id of the saved workflow that emitted the event
        (``wf-…``), or ``""`` when the definition did not come from the store
        (an inline definition, a bare ``.json`` file, a CLI file target).
        Inside a nested execution it identifies the CHILD workflow.  This is
        NOT a run identity — use ``run_id`` (or ``task_id`` on the renderer
        side) for that.
    ``workflow_name``
        Display name of the workflow definition that emitted the event (the
        child's name when nested).  Always present, so it is what log lines
        and node-path namespacing use.
    ``node_id``
        Path of the node from the run root (``"convert"`` at the top level,
        ``"loop/0/step"`` inside a ``flow.foreach`` body).  Path segments are
        added by the nesting primitives, never by the event layer, so a
        consumer can split on ``/`` and get the real nesting chain.
    ``status``
        One of ``ok`` / ``failed`` / ``skipped`` / ``cancelled``.  Exactly one
        ``node_completed`` is emitted per node, including skipped ones —
        consumers never have to infer a terminal state.

Cancellation is cooperative: the engine calls :func:`is_cancelled` at its
checkpoints (before each node, before each retry, during retry backoff), and
long-running tools poll it through ``ToolContext.cancel_check``.
"""

import json
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from app.utils.task_log_writer import append_task_log

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

NODE_STARTED = "node_started"
"""A node is about to execute.  Payload: ``{node_id, tool}``."""

NODE_COMPLETED = "node_completed"
"""A node reached a terminal state.  Payload: ``{node_id, status,
duration_ms, attempts, error?}``."""

LOG = "log"
"""A tool-level log line, for the renderer's live run log.

Payload: ``{level, message, node_id}``.  Emitted by tools that produce their
own progress messages — ``flow.log`` today.  It is NOT a substitute for the
per-task log: the emitting tool still writes the same line through
``task_log_writer``, so the live view and ``task.read_log`` agree.  Consumers
that do not know the type can ignore it (it is not a terminal event)."""

WORKFLOW_COMPLETED = "workflow_completed"
"""The whole workflow finished.  Payload: ``{success}``."""

WORKFLOW_FAILED = "workflow_failed"
"""The workflow aborted on a node error.  Payload: ``{error}``."""

WORKFLOW_CANCELLED = "workflow_cancelled"
"""The workflow was cancelled.  No extra payload."""

# ---------------------------------------------------------------------------
# TaskManager bridge (guarded so the module imports even without it)
# ---------------------------------------------------------------------------

try:
    from app.common.task_manager import TaskManager
except ImportError:  # TaskManager unavailable — is_cancelled() reports False
    TaskManager = None  # type: ignore[assignment]


def now_time_str() -> str:
    """Local ``HH:MM:SS`` timestamp stamped onto every event / log line."""
    return datetime.now().strftime("%H:%M:%S")


def render_event_line(event: Dict[str, Any]) -> str:
    """Render a workflow event dict as a plain-text log line.

    Every line is prefixed with the event's emission time (``ts`` field,
    falling back to ``now()`` when absent):

    * ``[12:00:01] [node_started] <node_id> (<tool>)``
    * ``[12:00:02] [node_completed] <node_id> status=<status> (<duration_ms> ms)``
      plus ``, attempts=<N>`` inside the parens when a node needed retries,
      plus `` error: <error>`` for a failed node
    * ``[12:00:03] [workflow_completed] success=<bool>``
    * ``[12:00:04] [workflow_failed] <error>``
    * ``[12:00:05] [workflow_cancelled]`` (bare tag when message is empty)
    * ``[12:00:06] [log] [<node_id> ] [<level>] <message>`` — tool-level lines
      (``flow.log``); the node segment is present only when the event knows
      which node emitted it
    * Unknown types fall back to ``[<type>] <json dumps of event>``.
    """
    event_type = event.get("type") or "event"
    if event_type == NODE_STARTED:
        message = f"{event.get('node_id', '?')} ({event.get('tool', '')})"
    elif event_type == NODE_COMPLETED:
        duration = f"{event.get('duration_ms', '?')} ms"
        attempts = event.get("attempts", 1)
        if isinstance(attempts, int) and attempts > 1:
            duration += f", attempts={attempts}"
        message = (
            f"{event.get('node_id', '?')} "
            f"status={event.get('status', '?')} "
            f"({duration})"
        )
        if event.get("error"):
            message += f" error: {event['error']}"
    elif event_type == LOG:
        node = event.get("node_id") or ""
        node_part = f"{node} " if node else ""
        message = f"{node_part}[{event.get('level', 'info')}] {event.get('message', '')}"
    elif event_type == WORKFLOW_COMPLETED:
        message = f"success={event.get('success', '?')}"
    elif event_type == WORKFLOW_FAILED:
        message = str(event.get("error", ""))
    elif event_type == WORKFLOW_CANCELLED:
        message = ""
    else:
        message = json.dumps(event, default=str, ensure_ascii=False)
    ts = str(event.get("ts") or now_time_str())
    return f"[{ts}] [{event_type}] {message}" if message else f"[{ts}] [{event_type}]"


class WorkflowStreamHandler:
    """Emits workflow streaming events through a downstream callback.

    Wraps the ``stream_handler`` callback supplied by the IPC layer — the
    same callback the ``@streaming`` handlers receive (see
    ``app/common/decorators.py`` and ``app/api_handler.py``).  Each
    ``emit_*`` method builds the event dict documented in the module
    docstring and forwards it to the callback.  If the callback is ``None``
    every emit is a silent no-op, so a non-streaming execution context can
    reuse this handler unchanged.

    Args:
        workflow_name: display name of the workflow definition emitting the
            events (the child's name inside a nested execution).
        callback: downstream callable receiving each event dict; typically
            the IPC ``stream_handler``.  ``None`` disables emission.
        workflow_id: storage id of the saved workflow emitting the events, or
            ``""`` when the definition did not come from the store.
        run_id: identifier of the top-level run carrying these events;
            defaults to ``workflow_id``, else ``workflow_name``, for a
            top-level run.
        task_log_id: when set, the handler tees event lines into the per-task
            log via :func:`append_task_log`.  Defaults to ``None``.
    """

    def __init__(
        self,
        workflow_name: str,
        callback: Optional[Callable[[dict], None]] = None,
        *,
        workflow_id: str = "",
        run_id: Optional[str] = None,
        task_log_id: Optional[str] = None,
    ) -> None:
        self.workflow_name = workflow_name
        self.workflow_id = workflow_id
        self.run_id = run_id or workflow_id or workflow_name
        self._callback = callback
        self.task_log_id = task_log_id

    def _wire(self, event_type: str, **fields: Any) -> None:
        """Build the standard event dict, tee to task log, then forward to
        the callback.

        The tee runs BEFORE the callback-None early return so logging works
        without a stream callback.
        """
        event: Dict[str, Any] = {
            "type": event_type,
            "ts": now_time_str(),
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
        }
        event.update(fields)

        if self.task_log_id is not None:
            append_task_log(self.task_log_id, render_event_line(event))

        if self._callback is None:
            return
        self._callback(event)

    def emit_node_started(self, node_id: str, tool: str) -> None:
        """Emit ``node_started``: the engine is about to run ``tool``."""
        self._wire(NODE_STARTED, node_id=node_id, tool=tool)

    def emit_node_completed(
        self,
        node_id: str,
        status: str,
        duration_ms: int,
        *,
        error: Optional[str] = None,
        attempts: int = 1,
    ) -> None:
        """Emit ``node_completed``: the node's single terminal event."""
        fields: Dict[str, Any] = {
            "node_id": node_id,
            "status": status,
            "duration_ms": duration_ms,
            "attempts": attempts,
        }
        if error:
            fields["error"] = error
        self._wire(NODE_COMPLETED, **fields)

    def emit_workflow_completed(self, success: bool) -> None:
        """Emit ``workflow_completed``: the whole workflow finished."""
        self._wire(WORKFLOW_COMPLETED, success=success)

    def emit_workflow_failed(self, error: str) -> None:
        """Emit ``workflow_failed``: the workflow aborted on a node error."""
        self._wire(WORKFLOW_FAILED, error=error)

    def emit_workflow_cancelled(self) -> None:
        """Emit ``workflow_cancelled`` after a cancellation."""
        self._wire(WORKFLOW_CANCELLED)


def is_cancelled(target: str) -> bool:
    """Return True if *target* (a run id or task id) has been cancelled.

    Delegates to :meth:`TaskManager.is_cancelled` — the same registry the
    streaming handlers register with.  Returns ``False`` when the run was
    never registered or when ``TaskManager`` is unavailable, so a missing
    registry never raises from a hot polling path.
    """
    if TaskManager is None:
        return False
    try:
        return TaskManager().is_cancelled(target)
    except Exception:
        return False
