#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workflow streaming events and between-node cancellation.

This module defines the event schema a workflow engine emits while executing
nodes, plus :class:`WorkflowStreamHandler` — a thin wrapper around the
existing ``stream_handler`` callback (the IPC callback that forwards events
to the renderer).  It deliberately adds NO new IPC channel: events are
delivered over the existing ``stream-event`` channel.  The main process
routes on ``result.type`` (see ``src/main/ipc/commandHandlers.ts``); workflow
event types (``node_started``, ``node_completed``, ...) are NOT in the logcat
``channelMap``, so they fall through to the generic ``streamEvent`` branch at
line 109.  On the wire the *routing* key is ``stream_id`` (the request id set
by ``ApiHandler.stream_handler``); ``workflow_id`` in each payload is
metadata the renderer uses to correlate events back to a workflow
(``TaskStreamService`` subscribes via ``onStreamEvent`` and matches on
``stream_id``).

Event schema (dicts passed to the stream callback)::

    node_started        {type, workflow_id, node_id, tool}
    node_output         {type, workflow_id, node_id, data}
    node_completed      {type, workflow_id, node_id, duration_ms}
    node_failed         {type, workflow_id, node_id, error}
    workflow_completed  {type, workflow_id, success}
    workflow_failed     {type, workflow_id, error}
    workflow_cancelled  {type, workflow_id}

Cancellation is BETWEEN nodes only (MVP): before starting each node the
engine calls :func:`is_cancelled`, which delegates to ``TaskManager`` (the
same registry the streaming/blocking handlers register with).  A cancelled
workflow stops before the next node rather than interrupting a node
mid-execution.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

NODE_STARTED = "node_started"
"""A node is about to execute.  Payload: ``{node_id, tool}``."""

NODE_OUTPUT = "node_output"
"""A node produced intermediate output.  Payload: ``{node_id, data}``."""

NODE_COMPLETED = "node_completed"
"""A node finished successfully.  Payload: ``{node_id, duration_ms}``."""

NODE_FAILED = "node_failed"
"""A node failed.  Payload: ``{node_id, error}``."""

WORKFLOW_COMPLETED = "workflow_completed"
"""The whole workflow finished.  Payload: ``{success}``."""

WORKFLOW_FAILED = "workflow_failed"
"""The workflow aborted on an error.  Payload: ``{error}``."""

WORKFLOW_CANCELLED = "workflow_cancelled"
"""The workflow was cancelled between nodes.  No extra payload."""

# ---------------------------------------------------------------------------
# TaskManager bridge (guarded so the module imports even without it)
# ---------------------------------------------------------------------------

try:
    from app.common.task_manager import TaskManager
except ImportError:  # TaskManager unavailable — is_cancelled() reports False
    TaskManager = None  # type: ignore[assignment]


@dataclass
class WorkflowEvent:
    """Typed representation of one workflow streaming event.

    Attributes:
        type: one of the module-level event-type constants
            (``NODE_STARTED``, ``NODE_OUTPUT``, ...).
        workflow_id: identifier of the workflow the event belongs to.
        node_id: id of the node the event refers to; ``None`` for
            workflow-level events (``workflow_completed`` / ``workflow_failed``
            / ``workflow_cancelled``).
        data: free-form payload.  For ``node_output`` this is the
            intermediate tool output dict.  The :class:`WorkflowStreamHandler`
            emit methods place their event-specific fields (``tool``,
            ``success``, ...) at the TOP level of the wire dict per the
            schema in the module docstring; this ``data`` bucket exists for
            programmatic event construction.
        duration_ms: node execution duration in milliseconds (``node_completed``).
        error: human-readable error message (``node_failed`` / ``workflow_failed``).

    :meth:`to_dict` keeps ``data`` nested under its own key — the flat
    schema-exact dicts documented in the module docstring are built by
    :class:`WorkflowStreamHandler`.
    """

    type: str
    workflow_id: str
    node_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-able dict, omitting unset optional fields."""
        event: Dict[str, Any] = {
            "type": self.type,
            "workflow_id": self.workflow_id,
        }
        for name in ("node_id", "data", "duration_ms", "error"):
            value = getattr(self, name)
            if value is not None:
                event[name] = value
        return event


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
        workflow_id: identifier of the workflow these events belong to
            (also the ``task_id`` the engine registers with TaskManager).
        callback: downstream callable receiving each event dict; typically
            the IPC ``stream_handler``.  ``None`` disables emission.
    """

    def __init__(
        self,
        workflow_id: str,
        callback: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self.workflow_id = workflow_id
        self._callback = callback

    def _wire(self, event_type: str, **fields: Any) -> None:
        """Build the standard event dict and forward it to the callback.

        No-op (silent) when no callback was provided.
        """
        if self._callback is None:
            return
        event: Dict[str, Any] = {
            "type": event_type,
            "workflow_id": self.workflow_id,
        }
        event.update(fields)
        self._callback(event)

    def emit_node_started(self, node_id: str, tool: str) -> None:
        """Emit ``node_started``: the engine is about to run ``tool``."""
        self._wire(NODE_STARTED, node_id=node_id, tool=tool)

    def emit_node_output(self, node_id: str, data: dict) -> None:
        """Emit ``node_output``: intermediate output produced by a node."""
        self._wire(NODE_OUTPUT, node_id=node_id, data=data)

    def emit_node_completed(self, node_id: str, duration_ms: int) -> None:
        """Emit ``node_completed`` after a node finishes successfully."""
        self._wire(NODE_COMPLETED, node_id=node_id, duration_ms=duration_ms)

    def emit_node_failed(self, node_id: str, error: str) -> None:
        """Emit ``node_failed`` after a node raises or returns an error."""
        self._wire(NODE_FAILED, node_id=node_id, error=error)

    def emit_workflow_completed(self, success: bool) -> None:
        """Emit ``workflow_completed``: the whole workflow finished."""
        self._wire(WORKFLOW_COMPLETED, success=success)

    def emit_workflow_failed(self, error: str) -> None:
        """Emit ``workflow_failed``: the workflow aborted on an error."""
        self._wire(WORKFLOW_FAILED, error=error)

    def emit_workflow_cancelled(self) -> None:
        """Emit ``workflow_cancelled`` after a between-node cancel."""
        self._wire(WORKFLOW_CANCELLED)


def is_cancelled(workflow_id: str) -> bool:
    """Return True if the workflow has been cancelled.

    Between-node cancellation check for the workflow engine: delegates to
    :meth:`TaskManager.is_cancelled` — the same registry the streaming /
    blocking handlers register with.  Returns ``False`` when the workflow
    was never registered (``TaskManager`` returns False for unknown tasks)
    or when ``TaskManager`` is unavailable, so a missing registry never
    raises from a hot polling path.
    """
    if TaskManager is None:
        return False
    try:
        return TaskManager().is_cancelled(workflow_id)
    except Exception:
        return False
