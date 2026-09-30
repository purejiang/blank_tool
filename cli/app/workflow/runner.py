#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared workflow execution helper.

``run_workflow`` centralizes the execution boilerplate that
``workflow.execute`` and the saved-workflow run path previously duplicated
verbatim: build the :class:`WorkflowStreamHandler` (when a task id / run id and
a stream callback are available), assemble the :class:`ExecutionContext`, run
the :class:`WorkflowEngine`, and return the ``{success, status, cancelled,
outputs, node_results, error, run_dir}`` wire shape.  Definition *loading*
stays in the caller (file path vs workflow store).

The run identity passed in as ``run_id`` is what the IPC layer registered for
cancellation; it is stamped on every streamed event and on the history record
as ``exec_run_id`` — the history *file* id stays a uuid4 hex, so the two
identities are linked by that field instead of being conflated.  ``run_dir``
carries the per-run artifact directory (``<output_dir>/runs/<slug>``) so a
consumer can open it without re-deriving the slug; it is also the default
working directory for a saved workflow, which has no source tree of its own.

Every top-level run is recorded into the run-history store
(:mod:`app.history.store`) on a best-effort basis: a recording failure is
logged and never affects the run's result.  Only top-level runs are
recorded — nested sub-workflow executions go through the engine directly
and are visible in the parent's ``node_results``.
"""

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

from app.workflow.definition import normalize_node_defaults
from app.workflow.engine import ExecutionContext, WorkflowEngine
from app.workflow.output_limit import shrink_outputs
from app.workflow.rundir import prepare_run_dir
from app.workflow.streaming import WorkflowStreamHandler

logger = logging.getLogger(__name__)


def run_workflow(
    definition, params, stream_handler, task_id, run_id=None, source_dir=None,
    task_name="", task_def_id="", workflow_id="",
):
    """Run a workflow definition, returning the standard result dict.

    Params:
        definition: an already-loaded :class:`WorkflowDefinition`.
        params: handler params; ``inputs``, ``work_dir`` and ``node_defaults``
            are consumed here.
        stream_handler: plain callable receiving event dicts (streaming).
        task_id: optional task identifier; used as the history ``task_id``.
        run_id: optional run identifier (the IPC request id) — the
            cancellation key and the ``run_id`` on streamed events.  Falls
            back to ``task_id`` when absent.
        source_dir: directory the definition came from when it is a real
            source tree — the folder of a workflow ``.json`` file.  It is the
            second choice for the run's working directory (after an explicit
            ``work_dir``).  Saved-workflow runs pass ``None``: the store
            directory is not a source tree, so those runs fall through to the
            per-run artifact directory instead of writing relative outputs
            into the workflow library.
        task_name: optional display name of the saved task definition this run
            belongs to (``task.execute``), recorded on the history record as
            ``task_name`` so run history can be filtered per task.  Empty for
            template / inline / CLI runs.
        task_def_id: optional storage id of that task definition, recorded as
            ``task_def_id`` so a renamed task can still be matched to the
            artifacts it produced.
        workflow_id: optional storage id of the saved workflow being run
            (``""`` for an inline definition or a bare file).  Stamped on
            streamed events as ``workflow_id`` and recorded in history.

    ``params["node_defaults"]`` (``{"on_failure", "retry"}``) is the run-level
    fallback for nodes that did not pin their own failure handling — see
    :func:`app.workflow.definition.normalize_node_defaults`.  UI callers send
    it from the user's node settings; CLI callers omit it and get the built-in
    ``fail`` / ``0``.

    Returns:
        ``{"success", "status", "cancelled", "outputs", "node_results",
        "error", "run_dir"}``.  ``run_dir`` is the per-run artifact directory;
        it is ``""`` when that directory could not be prepared (unwritable
        output dir), so consumers must tolerate the empty string.
    """
    inputs = params.get("inputs") or {}
    # Nodes that do not pin `on_failure` / `retry` inherit these.  Normalized
    # here so a malformed UI payload degrades to "no defaults" rather than
    # reaching the engine.
    node_defaults = normalize_node_defaults(params.get("node_defaults"))
    engine = WorkflowEngine()
    started_at = datetime.now().isoformat()
    start = time.perf_counter()
    identity = run_id or task_id or ""

    # The run's artifact directory is prepared up front because it doubles as
    # the default working directory: a saved workflow has no source tree, so
    # relative paths it produces belong in $rundir rather than in the workflow
    # library.  ``prepare_run_dir`` never raises — an unwritable output dir
    # yields "" and the run still proceeds.
    run_dir = prepare_run_dir(identity)

    # The stored workflow this run came from (``""`` for an inline definition
    # or a bare file).  Streamed events carry it as ``workflow_id``; the
    # definition's display name travels separately as ``workflow_name``.

    # The engine passes ``context.stream_handler`` straight through to the
    # builtin tools (``ToolContext.stream_handler``), so it must stay a plain
    # callable that receives event dicts.  The WorkflowStreamHandler is a
    # separate emit-API wrapper around that callback: create it whenever there
    # is a run identity (task-log tee) or a callback (wire events).
    workflow_stream = None
    if identity and (task_id or stream_handler):
        workflow_stream = WorkflowStreamHandler(
            workflow_name=getattr(definition, "name", "") or identity,
            workflow_id=workflow_id,
            callback=stream_handler,
            run_id=identity,
            task_log_id=task_id or identity,
        )

    context = ExecutionContext(
        # An explicit work_dir always wins; then a file-loaded workflow's own
        # directory; otherwise the run's artifact directory, so artifacts never
        # land in the process CWD (nor in the workflow store).
        work_dir=params.get("work_dir") or source_dir or run_dir or ".",
        task_id=task_id,
        run_id=identity,
        run_dir=run_dir,
        # $env.<name> resolves against this mapping. It used to default to an
        # empty dict, which made every $env.* reference fail with "missing key";
        # the backend process environment is the documented source.
        env=dict(os.environ),
        stream_handler=stream_handler,
        workflow_stream=workflow_stream,
        node_defaults=node_defaults,
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
        # ``""`` means "no artifact directory for this run".
        "run_dir": context.run_dir or "",
    }
    record_history(
        definition,
        params,
        task_id,
        inputs,
        result,
        started_at,
        start,
        run_dir=context.run_dir or "",
        exec_run_id=identity,
        task_name=task_name,
        task_def_id=task_def_id,
        workflow_id=workflow_id,
        node_defaults=node_defaults,
    )
    return payload


def record_history(
    definition,
    params,
    task_id,
    inputs,
    result,
    started_at,
    start,
    run_id=None,
    run_dir="",
    exec_run_id="",
    task_name="",
    task_def_id="",
    workflow_id="",
    node_defaults=None,
):
    """Best-effort history write — a recording failure never fails the run.

    Args:
        run_id: optional explicit record id (a uuid4 hex string).  The CLI
            passes the run identity it used for ``$rundir``, so a run's
            artifact directory and its history record share one id.  When
            omitted (the IPC path) a fresh id is generated.
        run_dir: per-run artifact directory; ``""`` when it could not be
            prepared.
        exec_run_id: the run identity the caller used for cancellation /
            ``$rundir``.  The IPC request id (``1700000000000-0.1234``) is
            NOT a valid history file id, so it is recorded here instead;
            falls back to the record id, then the task id.
        task_name: display name of the saved task definition this run belongs
            to, or ``""`` for template / inline / CLI runs.  Written as
            ``null`` in that case so records read back uniformly
            (``record.get("task_name") is None``).
        task_def_id: storage id of that task definition, or ``""``.  Renaming a
            task does not change its id, so this — not ``task_name`` — is what
            artifact cleanup matches on.
        workflow_id: storage id of the saved workflow that ran, or ``""`` for
            an inline definition / bare file.
        node_defaults: the run-level node defaults actually applied to nodes
            that did not pin their own failure handling (``{}`` when none).
            Recorded so a run can be explained after the fact: with "follow the
            system defaults" nodes, the saved definition alone does not say
            which values were in effect.
    """
    try:
        from app.history import store as history_store

        history_store.record_run(
            {
                "run_id": run_id or history_store.new_run_id(),
                "exec_run_id": exec_run_id or run_id or task_id,
                "task_id": task_id,
                "task_name": task_name or None,
                "task_def_id": task_def_id or None,
                "workflow_id": workflow_id or None,
                "workflow_name": getattr(definition, "name", ""),
                "source": params.get("name") or params.get("path") or "inline",
                "run_dir": run_dir,
                "started_at": started_at,
                "ended_at": datetime.now().isoformat(),
                "duration_ms": int((time.perf_counter() - start) * 1000),
                "inputs": inputs,
                "node_defaults": dict(node_defaults or {}),
                "node_results": result.node_results,
                "success": result.success,
                "status": result.status,
                "cancelled": result.cancelled,
                "error": result.error,
            }
        )
    except Exception:
        logger.warning("failed to record run history", exc_info=True)
