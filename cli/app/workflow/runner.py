#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared workflow execution helper.

``run_workflow`` centralizes the execution boilerplate that
``workflow.execute`` and ``template.execute`` previously duplicated verbatim:
build the :class:`WorkflowStreamHandler` (when a task id / run id and a stream
callback are available), assemble the :class:`ExecutionContext`, run the
:class:`WorkflowEngine`, and return the ``{success, status, cancelled, outputs,
node_results, error}`` wire shape.  Definition *loading* stays in the caller
(file path vs template store).

The run identity passed in as ``run_id`` is what the IPC layer registered for
cancellation; it is stamped on every streamed event and on the history record.

Every top-level run is recorded into the run-history store
(:mod:`app.history.store`) on a best-effort basis: a recording failure is
logged and never affects the run's result.  Only top-level runs are
recorded — nested sub-workflow executions go through the engine directly
and are visible in the parent's ``node_results``.
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

from app.workflow.engine import ExecutionContext, WorkflowEngine
from app.workflow.output_limit import shrink_outputs
from app.workflow.streaming import WorkflowStreamHandler

logger = logging.getLogger(__name__)


def run_workflow(definition, params, stream_handler, task_id, run_id=None):
    """Run a workflow definition, returning the standard result dict.

    Params:
        definition: an already-loaded :class:`WorkflowDefinition`.
        params: handler params; ``inputs`` and ``work_dir`` are consumed here.
        stream_handler: plain callable receiving event dicts (streaming).
        task_id: optional task identifier; used as the history ``task_id``.
        run_id: optional run identifier (the IPC request id) — the
            cancellation key and the ``run_id`` on streamed events.  Falls
            back to ``task_id`` when absent.

    Returns:
        ``{"success", "status", "cancelled", "outputs", "node_results",
        "error"}``.
    """
    inputs = params.get("inputs") or {}
    engine = WorkflowEngine()
    started_at = datetime.now().isoformat()
    start = time.perf_counter()
    identity = run_id or task_id or ""

    # The engine passes ``context.stream_handler`` straight through to the
    # builtin tools (``ToolContext.stream_handler``), so it must stay a plain
    # callable that receives event dicts.  The WorkflowStreamHandler is a
    # separate emit-API wrapper around that callback: create it whenever there
    # is a run identity (task-log tee) or a callback (wire events).
    workflow_stream = None
    if identity and (task_id or stream_handler):
        workflow_stream = WorkflowStreamHandler(
            workflow_id=getattr(definition, "name", "") or identity,
            callback=stream_handler,
            run_id=identity,
            task_log_id=task_id or identity,
        )

    context = ExecutionContext(
        work_dir=params.get("work_dir", "."),
        task_id=task_id,
        run_id=identity,
        stream_handler=stream_handler,
        workflow_stream=workflow_stream,
    )

    result = engine.execute(definition, inputs, context)

    payload: Dict[str, Any] = {
        "success": result.success,
        "status": result.status,
        "cancelled": result.cancelled,
        # The wire/history copy is size-bounded; the in-memory result keeps the
        # full values for callers that need them.
        "outputs": shrink_outputs(result.outputs),
        "node_results": result.node_results,
        "error": result.error,
    }
    _record_history(definition, params, task_id, inputs, result, started_at, start)
    return payload


def _record_history(definition, params, task_id, inputs, result, started_at, start):
    """Best-effort history write — a recording failure never fails the run."""
    try:
        from app.history import store as history_store

        history_store.record_run(
            {
                "run_id": history_store.new_run_id(),
                "task_id": task_id,
                "workflow_name": getattr(definition, "name", ""),
                "source": params.get("name") or params.get("path") or "inline",
                "started_at": started_at,
                "ended_at": datetime.now().isoformat(),
                "duration_ms": int((time.perf_counter() - start) * 1000),
                "inputs": inputs,
                "node_results": result.node_results,
                "success": result.success,
                "status": result.status,
                "cancelled": result.cancelled,
                "error": result.error,
            }
        )
    except Exception:
        logger.warning("failed to record run history", exc_info=True)
