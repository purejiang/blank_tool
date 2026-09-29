#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task-definition CRUD + execute IPC handlers.

A **task definition** is a saved workflow name plus the input values to run it
with (see :mod:`app.task.store`) — the object the renderer's task pages and the
headless CLI's ``run --task`` both operate on.  Exposed over the existing
``call-backend-api`` JSON-RPC channel (no new IPC channels); the module-level
``API_MAP`` is auto-discovered by :class:`app.api_handler.ApiHandler`:

- ``task.list``     every stored task definition, plus ``workflow_exists``;
- ``task.get``      one task definition by name;
- ``task.save``     create/overwrite a task definition (the bound workflow must
  exist, so a task can always be executed right after it is saved);
- ``task.delete``   remove one task definition, together with the run artifacts
  that definition produced (its run records stay in history);
- ``task.execute``  (@streaming)  run the bound workflow with the saved inputs.

⚠️ Key-name note: ``task.list`` used to report the IN-FLIGHT runs registered with
:class:`~app.common.task_manager.TaskManager`; that listing is now ``run.list``
(see :mod:`app.handlers.task_handler`).  The remaining ``task.*`` keys that take
a ``task_id`` (``task.read_log`` / ``task.append_log`` / ``task.delete_task_dir``
/ ``task.delete_output``) are keyed by a **run identity**, not by a task
definition name — they are deliberately left untouched here.

Execution semantics (mirrors ``template.execute``):

- the definition comes from the template store by the task's ``workflow`` name,
  so editing the workflow keeps every task on the current graph;
- inputs are merged shallowly — saved values are the defaults, values passed to
  ``task.execute`` override them (the saved task is never rewritten by a run);
- the working directory is ``work_dir`` from the request, else the task's saved
  ``work_dir``, else the workflow's own directory;
- the run is recorded with ``task_name`` so run history can be filtered per
  task, while ``source`` stays the workflow name.
"""

import os

from app.common.decorators import logs_errors, streaming
from app.common.exceptions import ToolException
from app.handlers.task_handler import handle_delete_output
from app.history import store as history_store
from app.task.store import FileTaskStore, TaskNotFoundError
from app.template.store import FileTemplateStore, TemplateNotFoundError
from app.utils.logger import Logger
from app.workflow.runner import run_workflow
from app.workflow.rundir import runs_root, safe_slug

logger = Logger.get_logger("TaskDefHandler")

#: Process-wide stores, created lazily (keeps module import free of filesystem
#: side effects and lets tests point both at a ``tmp_path``).
_task_store = None
_template_store = None


def _get_task_store() -> FileTaskStore:
    """Return the process-wide :class:`FileTaskStore`, creating it lazily."""
    global _task_store
    if _task_store is None:
        _task_store = FileTaskStore()
    return _task_store


def _get_template_store() -> FileTemplateStore:
    """Return the template store used to resolve/execute a task's workflow.

    A separate instance from ``app.handlers.template_handler._store`` — both
    resolve the same directory (``BT_TEMPLATES_DIR`` → ``<output>/templates``)
    and the store holds no state beyond that path.
    """
    global _template_store
    if _template_store is None:
        _template_store = FileTemplateStore()
    return _template_store


def _require_name(params: dict) -> str:
    name = params.get("name")
    if not isinstance(name, str) or not name:
        raise ToolException("Missing 'name' field")
    return name


def _workflow_exists(workflow: str) -> bool:
    """Whether *workflow* is a stored template name.

    Raises:
        ToolException: the name could never be a template name (path
            separators / ``..``), which the template store rejects outright.
    """
    try:
        return _get_template_store().exists(workflow)
    except ValueError as exc:
        raise ToolException(f"invalid workflow name: {workflow!r}") from exc


@logs_errors("TaskDefHandler")
def task_list(params, stream_handler):
    """Return every stored task definition (sorted by name).

    Returns:
        ``{"tasks": [{name, workflow, workflow_exists, inputs, input_count,
        has_work_dir, description, created_at, updated_at}, ...]}``.  ``inputs``
        is included so a list UI can show a summary and run a task without a
        second round-trip; ``workflow_exists = false`` marks a task whose bound
        workflow was renamed or deleted (the task is kept, never dropped).
    """
    task_store = _get_task_store()
    tasks = []
    for info in task_store.list():
        tasks.append(
            {
                **info.to_dict(),
                "workflow_exists": _workflow_exists(info.workflow),
                "input_count": len(info.inputs),
                "has_work_dir": bool(info.work_dir),
            }
        )
    return {"tasks": tasks}


@logs_errors("TaskDefHandler")
def task_get(params, stream_handler):
    """Return one task definition.

    Params:
        name: task name.

    Returns:
        ``{"task": {...}, "workflow_exists": <bool>}``.

    Raises:
        ToolException: the name is missing, unknown, or the file is invalid.
    """
    name = _require_name(params)
    try:
        info = _get_task_store().load(name)
    except TaskNotFoundError as exc:
        raise ToolException(f"task not found: {name}") from exc
    except ValueError as exc:
        raise ToolException(str(exc)) from exc
    return {
        "task": info.to_dict(),
        "workflow_exists": _workflow_exists(info.workflow),
    }


@logs_errors("TaskDefHandler")
def task_save(params, stream_handler):
    """Create or overwrite a task definition.

    Params:
        name: task name (must be path-safe).
        workflow: name of a SAVED template to run (must exist).
        inputs: optional object of input values, stored as given.
        work_dir: optional working directory (``""`` = workflow's own dir).
        description: optional human-facing one-liner.

    Returns:
        ``{"saved": True, "name": <name>}``.

    Raises:
        ToolException: missing/blank ``workflow``, unknown workflow, non-object
            ``inputs``, or an unsafe task name.
    """
    name = _require_name(params)
    workflow = params.get("workflow")
    if not isinstance(workflow, str) or not workflow.strip():
        raise ToolException("Missing 'workflow' field")

    inputs = params.get("inputs")
    if inputs is not None and not isinstance(inputs, dict):
        raise ToolException("'inputs' must be an object")

    work_dir = params.get("work_dir") or ""
    description = params.get("description") or ""

    if not _workflow_exists(workflow):
        raise ToolException(f"workflow not found: {workflow}")

    try:
        _get_task_store().save(
            name, workflow, inputs or {}, work_dir, description
        )
    except ValueError as exc:
        raise ToolException(str(exc)) from exc
    return {"saved": True, "name": name}


def _run_artifact_paths(task_name: str) -> list:
    """Collect the artifact directories of every recorded run of *task_name*.

    ``run_dir`` (``<output_dir>/runs/<run-id>``) is taken from the history
    summary when present; otherwise it is re-derived from the run id the same
    way :func:`app.workflow.rundir.run_dir_for` does.
    """
    try:
        records = history_store.list_runs(limit=0)
    except Exception as exc:  # defensive: history must never block a delete
        logger.warning(f"task.delete: cannot list runs for '{task_name}': {exc}")
        return []

    paths = []
    for record in records:
        if not isinstance(record, dict) or record.get("task_name") != task_name:
            continue
        run_dir = record.get("run_dir")
        if isinstance(run_dir, str) and run_dir.strip():
            paths.append(run_dir.strip())
            continue
        run_id = record.get("run_id")
        if isinstance(run_id, str) and run_id:
            paths.append(os.path.join(runs_root(), safe_slug(run_id)))
    return paths


def _purge_run_artifacts(task_name: str) -> int:
    """Best-effort delete of *task_name*'s run artifacts; returns how many went.

    Deleting a task therefore deletes the files it produced — the behavior the
    removed ``autoDeleteOutputOnTaskRemove`` setting used to (never actually)
    toggle.  Run *records* are deliberately kept: history has its own retention
    policy and its own "clear" action in the run-records UI.

    Every path is containment-checked against the output dir by
    ``task.delete_output`` (paths reach us from history files, not from the
    caller).  Failures are logged, never raised: an undeletable folder must not
    leave the task definition behind.
    """
    paths = _run_artifact_paths(task_name)
    if not paths:
        return 0

    try:
        result = handle_delete_output({"paths": paths}, None)
    except Exception as exc:  # defensive: deletion is best-effort
        logger.warning(f"task.delete: cannot purge artifacts of '{task_name}': {exc}")
        return 0

    for failure in result.get("failed") or []:
        logger.warning(
            f"task.delete: could not remove '{failure.get('path')}': "
            f"{failure.get('error')}"
        )
    return len(result.get("deleted") or [])


@logs_errors("TaskDefHandler")
def task_delete(params, stream_handler):
    """Remove one task definition and the run artifacts it produced.

    Params:
        name: task name.

    Returns:
        ``{"deleted": True, "name": <name>}``.

    Raises:
        ToolException: the name is missing, unknown, or unsafe.

    The task's run *records* are deliberately kept (history is pruned by its own
    retention policy and cleared from the run-records UI), but the artifacts
    those runs wrote under the output directory are removed along with the
    definition — deleting a task deletes its files by default.
    """
    name = _require_name(params)
    try:
        _get_task_store().delete(name)
    except TaskNotFoundError as exc:
        raise ToolException(f"task not found: {name}") from exc
    except ValueError as exc:
        raise ToolException(str(exc)) from exc
    _purge_run_artifacts(name)
    return {"deleted": True, "name": name}


@streaming
@logs_errors("TaskDefHandler")
def task_execute(params, stream_handler):
    """Run a task's workflow with its saved inputs, streaming node events.

    The ``@streaming`` decorator runs this in a background thread; every dict
    passed to ``stream_handler`` is forwarded to the renderer over
    ``stream-event``.

    Params:
        name: task name to load and run.
        inputs: optional per-run overrides, merged shallowly over the saved
            values (saved values act as defaults).
        task_id: optional run identifier, forwarded to tools and used as the
            workflow_id on streamed events (NOT derived from the task name, so
            the same task can run concurrently).
        work_dir: optional working directory override.

    Returns:
        Same shape as ``workflow.execute``:
        ``{"success", "status", "cancelled", "outputs", "node_results",
        "error", "run_dir"}``.

    Raises:
        ToolException: unknown task, unknown/renamed bound workflow, non-object
            ``inputs``.
    """
    name = _require_name(params)
    try:
        info = _get_task_store().load(name)
    except TaskNotFoundError as exc:
        raise ToolException(f"task not found: {name}") from exc
    except ValueError as exc:
        raise ToolException(str(exc)) from exc

    template_store = _get_template_store()
    try:
        definition = template_store.load(info.workflow)
    except TemplateNotFoundError as exc:
        raise ToolException(f"workflow not found: {info.workflow}") from exc
    except ValueError as exc:
        raise ToolException(f"workflow {info.workflow!r}: {exc}") from exc

    overrides = params.get("inputs")
    if overrides is not None and not isinstance(overrides, dict):
        raise ToolException("'inputs' must be an object")

    inputs = {**info.inputs, **(overrides or {})}
    task_id = params.get("task_id")
    run_id = params.get("_run_id") or task_id

    # ``name`` in the run params is the WORKFLOW name: the history ``source``
    # field keeps meaning "template name / file path / inline", and the task
    # identity travels separately as ``task_name``.
    run_params = {
        "name": info.workflow,
        "inputs": inputs,
        "work_dir": params.get("work_dir") or info.work_dir,
    }
    return run_workflow(
        definition,
        run_params,
        stream_handler,
        task_id,
        run_id,
        source_dir=getattr(template_store, "templates_dir", None),
        task_name=info.name,
    )


API_MAP = {
    "task.list": task_list,
    "task.get": task_get,
    "task.save": task_save,
    "task.delete": task_delete,
    "task.execute": task_execute,
}
