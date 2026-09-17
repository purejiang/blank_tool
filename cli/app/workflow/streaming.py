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

    node_started        {type, run_id, workflow_id, node_id, tool}
    node_completed      {type, run_id, workflow_id, node_id, status,
                         duration_ms, attempts, error?}
    workflow_completed  {type, run_id, workflow_id, success}
    workflow_failed     {type, run_id, workflow_id, error}
    workflow_cancelled  {type, run_id, workflow_id}

Field semantics:
    ``run_id``
        Identifier of the TOP-LEVEL run.  Never rewritten by nesting, so a
        consumer can group every event of one run.
    ``workflow_id``
        Name of the workflow definition that emitted the event — the child
        template's name inside a nested execution.
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


def render_event_line(event: Dict[str, Any]) -> str:
    """Render a workflow event dict as a plain-text log line.

    Produces EXACTLY these formats:

    * ``[node_started] <node_id> (<tool>)``
    * ``[node_completed] <node_id> status=<status> (<duration_ms> ms)``
      plus `` error: <error>`` for a failed/skipped node
    * ``[workflow_completed] success=<bool>``
    * ``[workflow_failed] <error>``
    * ``[workflow_cancelled]`` (bare tag when message is empty)
    * Unknown types fall back to ``[<type>] <json dumps of event>``.
    """
    event_type = event.get("type") or "event"
    if event_type == NODE_STARTED:
        message = f"{event.get('node_id', '?')} ({event.get('tool', '')})"
    elif event_type == NODE_COMPLETED:
        message = (
            f"{event.get('node_id', '?')} "
            f"status={event.get('status', '?')} "
            f"({event.get('duration_ms', '?')} ms)"
        )
        if event.get("error"):
            message += f" error: {event['error']}"
    elif event_type == WORKFLOW_COMPLETED:
        message = f"success={event.get('success', '?')}"
    elif event_type == WORKFLOW_FAILED:
        message = str(event.get("error", ""))
    elif event_type == WORKFLOW_CANCELLED:
        message = ""
    else:
        message = json.dumps(event, default=str, ensure_ascii=False)
    return f"[{event_type}] {message}" if message else f"[{event_type}]"


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
        workflow_id: name of the workflow definition emitting the events.
        callback: downstream callable receiving each event dict; typically
            the IPC ``stream_handler``.  ``None`` disables emission.
        run_id: identifier of the top-level run carrying these events;
            defaults to ``workflow_id`` for a top-level run.
        task_log_id: when set, the handler tees event lines into the per-task
            log via :func:`append_task_log`.  Defaults to ``None``.
    """

    def __init__(
        self,
        workflow_id: str,
        callback: Optional[Callable[[dict], None]] = None,
        *,
        run_id: Optional[str] = None,
        task_log_id: Optional[str] = None,
    ) -> None:
        self.workflow_id = workflow_id
        self.run_id = run_id or workflow_id
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
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
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
