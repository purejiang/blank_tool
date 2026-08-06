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
"""

from app.workflow.engine import ExecutionContext, WorkflowEngine
from app.workflow.streaming import WorkflowStreamHandler


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

    return {
        "success": result.success,
        "outputs": result.outputs,
        "node_results": result.node_results,
        "error": result.error,
    }
