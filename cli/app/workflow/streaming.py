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

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from app.utils.task_log_writer import append_task_log

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


#: Node-level lifecycle event types (used by the tee namespacing rule).
_NODE_LIFECYCLE_TYPES = frozenset({NODE_STARTED, NODE_COMPLETED, NODE_FAILED})


def render_event_line(event: Dict[str, Any]) -> str:
    """Render a workflow event dict as a plain-text log line.

    Produces EXACTLY these formats (mirroring the CLI console format):

    * ``[node_started] <node_id> (<tool>)``
    * ``[node_completed] <node_id> (<duration_ms> ms)``
    * ``[node_failed] <node_id>: <error>``
    * ``[node_output] <node_id>: <json data>``
    * ``[workflow_completed] success=<bool>``
    * ``[workflow_failed] <error>``
    * ``[workflow_cancelled]`` (bare tag when message is empty)
    * Unknown types fall back to ``[<type>] <json dumps of event>``.

    The ``if message else`` bare-tag rule from cli.py:501 is preserved.
    """
    event_type = event.get("type") or "event"
    if event_type == NODE_STARTED:
        message = f"{event.get('node_id', '?')} ({event.get('tool', '')})"
    elif event_type == NODE_COMPLETED:
        message = (
            f"{event.get('node_id', '?')} ({event.get('duration_ms', '?')} ms)"
        )
    elif event_type == NODE_FAILED:
        message = f"{event.get('node_id', '?')}: {event.get('error', '')}"
    elif event_type == NODE_OUTPUT:
        message = (
            f"{event.get('node_id', '?')}: "
            f"{json.dumps(event.get('data', {}), default=str, ensure_ascii=False)}"
        )
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
        workflow_id: identifier of the workflow these events belong to
            (also the ``task_id`` the engine registers with TaskManager).
        callback: downstream callable receiving each event dict; typically
            the IPC ``stream_handler``.  ``None`` disables emission.
        task_log_id: when set, the handler tees lifecycle event lines into
            the per-task log via :func:`append_task_log`.  ``node_output``
            is NEVER written to the task log.  Defaults to ``None``.
    """

    def __init__(
        self,
        workflow_id: str,
        callback: Optional[Callable[[dict], None]] = None,
        *,
        task_log_id: Optional[str] = None,
    ) -> None:
        self.workflow_id = workflow_id
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
            "workflow_id": self.workflow_id,
        }
        event.update(fields)

        # -- task-log tee (before callback-None guard) -----------------
        if self.task_log_id is not None and event_type != NODE_OUTPUT:
            render_copy = dict(event)  # shallow copy for rendering
            # Namespacing rule: prefix node_id with workflow_id for child
            # handlers whose workflow_id differs from task_log_id.
            if (
                event_type in _NODE_LIFECYCLE_TYPES
                and self.workflow_id != self.task_log_id
            ):
                render_copy["node_id"] = (
                    f"{self.workflow_id}/{event.get('node_id', '?')}"
                )
            append_task_log(self.task_log_id, render_event_line(render_copy))

        if self._callback is None:
            return
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
