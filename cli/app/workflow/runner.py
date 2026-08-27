#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared workflow execution helper.

``run_workflow`` centralizes the execution boilerplate that
``workflow.execute`` and ``template.execute`` previously duplicated verbatim:
build the :class:`WorkflowStreamHandler` (when a task id + stream callback are
available), assemble the :class:`ExecutionContext`, run the
:class:`WorkflowEngine`, and return the ``{success, outputs, node_results,
error}`` wire shape.  Definition *loading* stays in the caller (file path vs
template store).

Every top-level run is recorded into the run-history store
(:mod:`app.history.store`) on a best-effort basis: a recording failure is
logged and never affects the run's result.  Only top-level runs are
recorded — nested sub-workflow executions go through the engine directly
and are visible in the parent's ``node_results``.
"""

import logging
import time
from datetime import datetime

from app.workflow.engine import ExecutionContext, WorkflowEngine
from app.workflow.streaming import WorkflowStreamHandler

logger = logging.getLogger(__name__)


def run_workflow(definition, params, stream_handler, task_id):
    """Run a workflow definition, returning the standard result dict.

    Params:
        definition: an already-loaded :class:`WorkflowDefinition`.
        params: handler params; ``inputs`` and ``work_dir`` are consumed here.
        stream_handler: plain callable receiving event dicts (streaming).
        task_id: optional task identifier; used as the workflow_id on
            streamed events when present.

    Returns:
        ``{"success", "outputs", "node_results", "error"}``.
    """
    inputs = params.get("inputs") or {}
    engine = WorkflowEngine()
    started_at = datetime.now().isoformat()
    start = time.perf_counter()

    # The engine passes ``context.stream_handler`` straight through to the
    # builtin tools (``ToolContext.stream_handler``), so it must stay a plain
    # callable that receives event dicts.  The WorkflowStreamHandler is a
    # separate emit-API wrapper around that callback: create it when a task id
    # + callback are available so the terminal workflow event is emitted with
    # the workflow_id metadata.
    workflow_stream = None
    if task_id and stream_handler:
        workflow_stream = WorkflowStreamHandler(
            workflow_id=task_id, callback=stream_handler, task_log_id=task_id
        )

    context = ExecutionContext(
        work_dir=params.get("work_dir", "."),
        task_id=task_id,
        stream_handler=stream_handler,
        workflow_stream=workflow_stream,
    )

    result = engine.execute(definition, inputs, context)

    payload = {
        "success": result.success,
        "outputs": result.outputs,
        "node_results": result.node_results,
        "error": result.error,
    }
    record_history(definition, params, task_id, inputs, result, started_at, start)
    return payload


def record_history(definition, params, task_id, inputs, result, started_at, start):
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
                "error": result.error,
            }
        )
    except Exception:
        logger.warning("failed to record run history", exc_info=True)
