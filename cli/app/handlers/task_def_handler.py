#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task-definition CRUD + execute IPC handlers.

A **task definition** is a saved workflow plus the input values to run it with
(see :mod:`app.task.store`) — the object the renderer's task pages and the
headless CLI's ``run --task`` both operate on.  Exposed over the existing
``call-backend-api`` JSON-RPC channel (no new IPC channels); the module-level
``API_MAP`` is auto-discovered by :class:`app.api_handler.ApiHandler`:

- ``task.list``     every stored task definition, plus ``workflow_exists``;
- ``task.get``      one task definition by id or name;
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
definition — they are deliberately left untouched here.

Identity:
    A task definition carries an auto-generated ``tk-…`` id (its file name) and
    a free-form display name; both ``task.get`` / ``task.delete`` /
    ``task.execute`` accept ``id`` or ``name``.  The workflow it runs is bound
    by ``workflow_id`` (stable across renames), with the saved ``workflow``
    display name as a fallback for tasks written before ids existed.

Execution semantics (mirrors the saved-workflow path of ``workflow.execute``):

- the definition comes from the workflow store by the task's bound id, so
  editing the workflow keeps every task on the current graph;
- inputs are merged shallowly — saved values are the defaults, values passed to
  ``task.execute`` override them (the saved task is never rewritten by a run);
- the working directory is ``work_dir`` from the request, else the task's saved
  ``work_dir``, else the run's artifact directory;
- the run is recorded with ``task_name`` / ``task_def_id`` so run history can be
  filtered per task, while ``source`` stays the workflow name.
"""

import os

from app.common.decorators import logs_errors, streaming
from app.common.exceptions import ToolException
from app.handlers.task_handler import handle_delete_output
from app.history import store as history_store
from app.task.store import (
    AmbiguousTaskNameError,
    FileTaskStore,
    TaskDefinitionInfo,
    TaskNotFoundError,
)
from app.utils.logger import Logger
from app.workflow.runner import run_workflow
from app.workflow.rundir import runs_root, safe_slug
from app.workflow.store import (
    AmbiguousWorkflowNameError,
    FileWorkflowStore,
    WorkflowNotFoundError,
)

logger = Logger.get_logger("TaskDefHandler")

#: Process-wide stores, created lazily (keeps module import free of filesystem
#: side effects and lets tests point both at a ``tmp_path``).
_task_store = None
_workflow_store = None

#: Whether the one-time ``workflow_id`` backfill already ran in this process.
_backfilled = False


def _get_task_store() -> FileTaskStore:
    """Return the process-wide :class:`FileTaskStore`, creating it lazily.

    Construction also migrates pre-id task files to ``tk-…`` names and — once
    per process — backfills ``workflow_id`` on tasks that only bound their
    workflow by display name, so those bindings survive a workflow rename too.
    """
    global _task_store, _backfilled
    if _task_store is None:
        _task_store = FileTaskStore()
    if not _backfilled:
        _backfilled = True
        try:
            _task_store.backfill_workflow_ids(_resolve_workflow_name)
        except Exception:  # never let a one-time backfill break a request
            logger.warning("workflow_id backfill failed", exc_info=True)
    return _task_store


def _get_workflow_store() -> FileWorkflowStore:
    """Return the workflow store used to resolve/execute a task's workflow.

    A separate instance from ``app.handlers.workflow_handler._store`` — both
    resolve the same directory (``BT_WORKFLOWS_DIR`` → ``<output>/workflows``)
    and the store holds no state beyond that path.
    """
    global _workflow_store
    if _workflow_store is None:
        _workflow_store = FileWorkflowStore()
    return _workflow_store


def _resolve_workflow_name(name: str):
    """Map a workflow display name to its id (``None`` when unknown)."""
    return _get_workflow_store().find_id_by_name(name)


def _resolve_task_id(params: dict, *, required: bool = True) -> str:
    """Resolve the ``id``/``name`` params to a stored task id.

    ``id`` wins over ``name``.  Raises :class:`ToolException` when neither is
    given (and *required*), when nothing matches, or when a name matches
    several tasks.
    """
    task_id = params.get("id")
    ref = task_id or params.get("name")
    if not ref:
        if required:
            raise ToolException("Missing 'id' or 'name' field")
        return ""
    try:
        resolved = _get_task_store().resolve(ref)
    except AmbiguousTaskNameError as exc:
        raise ToolException(str(exc)) from exc
    if resolved is None:
        raise ToolException(f"task not found: {ref}")
    return resolved


def _workflow_status(info: TaskDefinitionInfo):
    """Return ``(exists, display_name)`` for the workflow a task binds.

    The binding is ``workflow_id`` when the task has one (stable across
    renames); otherwise the saved display name is resolved, which is how tasks
    written before ids existed keep working.  A workflow that cannot be read
    (deleted, or a corrupt file) reports ``exists=False`` rather than raising,
    so one broken binding cannot break the whole task list.
    """
    ref = info.workflow_id or info.workflow
    if not ref:
        return False, info.workflow
    try:
        definition, metadata = _get_workflow_store().load_with_meta(ref)
    except (
        WorkflowNotFoundError,
        AmbiguousWorkflowNameError,
        ValueError,
        OSError,
    ):
        return False, info.workflow
    return True, (metadata.get("name") or definition.name or info.workflow)


def _serialize(info: TaskDefinitionInfo) -> dict:
    """Wire shape for one task definition, with the live workflow name filled in.

    The storage id is added here rather than in
    :meth:`TaskDefinitionInfo.to_dict` (which is also the on-disk shape): the
    id is the file name, so writing it into the file would be redundant.
    """
    exists, workflow_name = _workflow_status(info)
    payload = {"id": info.id, **info.to_dict()}
    payload["workflow"] = workflow_name
    payload["workflow_exists"] = exists
    return payload


@logs_errors("TaskDefHandler")
def task_list(params, stream_handler):
    """Return every stored task definition (sorted by display name).

    Returns:
        ``{"tasks": [{id, name, workflow, workflow_id, workflow_exists, inputs,
        input_count, has_work_dir, description, created_at, updated_at}, ...]}``.
        ``inputs`` is included so a list UI can show a summary and run a task
        without a second round-trip; ``workflow_exists = false`` marks a task
        whose bound workflow was deleted (the task is kept, never dropped).
    """
    task_store = _get_task_store()
    tasks = []
    for info in task_store.list():
        tasks.append(
            {
                **_serialize(info),
                "input_count": len(info.inputs),
                "has_work_dir": bool(info.work_dir),
            }
        )
    return {"tasks": tasks}


@logs_errors("TaskDefHandler")
def task_get(params, stream_handler):
    """Return one task definition.

    Params:
        id: task id (preferred).
        name: task display name (fallback).

    Returns:
        ``{"task": {...}, "workflow_exists": <bool>}``.

    Raises:
        ToolException: the reference is missing, unknown, or the file is invalid.
    """
    task_id = _resolve_task_id(params)
    try:
        info = _get_task_store().load(task_id)
    except TaskNotFoundError as exc:
        raise ToolException(f"task not found: {task_id}") from exc
    except ValueError as exc:
        raise ToolException(str(exc)) from exc
    payload = _serialize(info)
    return {"task": payload, "workflow_exists": payload["workflow_exists"]}


@logs_errors("TaskDefHandler")
def task_save(params, stream_handler):
    """Create or overwrite a task definition.

    Params:
        id: optional task id to overwrite; omitted means "create a new task".
        name: task display name (free-form; may repeat).
        workflow_id: id of a SAVED workflow to run (preferred binding).
        workflow: display name of a SAVED workflow (fallback binding; resolved
            to its id when it matches exactly one workflow).
        inputs: optional object of input values, stored as given.
        work_dir: optional working directory (``""`` = the run's artifact dir).
        description: optional human-facing one-liner.

    Returns:
        ``{"saved": True, "id": <id>, "name": <name>}``.

    Raises:
        ToolException: missing/blank name, missing or unknown workflow binding,
            non-object ``inputs``, or an ambiguous workflow name.
    """
    name = params.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ToolException("Missing 'name' field")

    inputs = params.get("inputs")
    if inputs is not None and not isinstance(inputs, dict):
        raise ToolException("'inputs' must be an object")

    work_dir = params.get("work_dir") or ""
    description = params.get("description") or ""

    workflow_store = _get_workflow_store()
    workflow_id = params.get("workflow_id")
    workflow_name = ""
    if workflow_id:
        try:
            definition, metadata = workflow_store.load_with_meta(workflow_id)
        except WorkflowNotFoundError as exc:
            raise ToolException(f"workflow not found: {workflow_id}") from exc
        except (AmbiguousWorkflowNameError, ValueError) as exc:
            raise ToolException(f"workflow {workflow_id!r}: {exc}") from exc
        workflow_name = metadata.get("name") or definition.name
    else:
        workflow = params.get("workflow")
        if not isinstance(workflow, str) or not workflow.strip():
            raise ToolException("Missing 'workflow_id' or 'workflow' field")
        try:
            definition, metadata = workflow_store.load_with_meta(workflow)
        except WorkflowNotFoundError as exc:
            raise ToolException(f"workflow not found: {workflow}") from exc
        except AmbiguousWorkflowNameError as exc:
            raise ToolException(str(exc)) from exc
        except ValueError as exc:
            raise ToolException(f"workflow {workflow!r}: {exc}") from exc
        workflow_id = metadata.get("id") or None
        workflow_name = metadata.get("name") or definition.name

    try:
        info = _get_task_store().save(
            name,
            workflow_name,
            inputs or {},
            work_dir,
            description,
            workflow_id=workflow_id,
            task_id=params.get("id") or None,
        )
    except ValueError as exc:
        raise ToolException(str(exc)) from exc
    return {"saved": True, "id": info.id, "name": info.name}


def _run_artifact_paths(task_id: str, task_name: str) -> list:
    """Collect the artifact directories of every recorded run of a task.

    Records are matched on ``task_def_id`` (the task's storage id) so renaming
    a task does not orphan the files it produced; records written before ids
    existed carry no id and fall back to the ``task_name`` they stored.

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
        if not isinstance(record, dict):
            continue
        record_id = record.get("task_def_id")
        if record_id:
            if record_id != task_id:
                continue
        elif record.get("task_name") != task_name:
            continue
        run_dir = record.get("run_dir")
        if isinstance(run_dir, str) and run_dir.strip():
            paths.append(run_dir.strip())
            continue
        run_id = record.get("run_id")
        if isinstance(run_id, str) and run_id:
            paths.append(os.path.join(runs_root(), safe_slug(run_id)))
    return paths


def _purge_run_artifacts(task_id: str, task_name: str) -> int:
    """Best-effort delete of a task's run artifacts; returns how many went.

    Deleting a task therefore deletes the files it produced — the behavior the
    removed ``autoDeleteOutputOnTaskRemove`` setting used to (never actually)
    toggle.  Run *records* are deliberately kept: history has its own retention
    policy and its own "clear" action in the run-records UI.

    Every path is containment-checked against the output dir by
    ``task.delete_output`` (paths reach us from history files, not from the
    caller).  Failures are logged, never raised: an undeletable folder must not
    leave the task definition behind.
    """
    paths = _run_artifact_paths(task_id, task_name)
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
        id: task id (preferred).
        name: task display name (fallback).

    Returns:
        ``{"deleted": True, "id": <id>, "name": <name>}``.

    Raises:
        ToolException: the reference is missing, unknown, or ambiguous.

    The task's run *records* are deliberately kept (history is pruned by its own
    retention policy and cleared from the run-records UI), but the artifacts
    those runs wrote under the output directory are removed along with the
    definition — deleting a task deletes its files by default.
    """
    task_id = _resolve_task_id(params)
    try:
        info = _get_task_store().load(task_id)
    except TaskNotFoundError as exc:
        raise ToolException(f"task not found: {task_id}") from exc
    except ValueError as exc:
        raise ToolException(str(exc)) from exc
    try:
        _get_task_store().delete(task_id)
    except TaskNotFoundError as exc:
        raise ToolException(f"task not found: {task_id}") from exc
    _purge_run_artifacts(task_id, info.name)
    return {"deleted": True, "id": info.id, "name": info.name}


@streaming
@logs_errors("TaskDefHandler")
def task_execute(params, stream_handler):
    """Run a task's workflow with its saved inputs, streaming node events.

    The ``@streaming`` decorator runs this in a background thread; every dict
    passed to ``stream_handler`` is forwarded to the renderer over
    ``stream-event``.

    Params:
        id: task id to load and run (preferred).
        name: task display name (fallback).
        inputs: optional per-run overrides, merged shallowly over the saved
            values (saved values act as defaults).
        task_id: optional run identifier, forwarded to tools and used as the
            run identity on streamed events (NOT derived from the task name, so
            the same task can run concurrently).
        work_dir: optional working directory override.

    Returns:
        Same shape as the saved-workflow path of ``workflow.execute``:
        ``{"success", "status", "cancelled", "outputs", "node_results",
        "error", "run_dir"}``.

    Raises:
        ToolException: unknown task, unknown/deleted bound workflow, non-object
            ``inputs``.
    """
    task_id_ref = _resolve_task_id(params)
    try:
        info = _get_task_store().load(task_id_ref)
    except TaskNotFoundError as exc:
        raise ToolException(f"task not found: {task_id_ref}") from exc
    except ValueError as exc:
        raise ToolException(str(exc)) from exc

    workflow_store = _get_workflow_store()
    binding = info.workflow_id or info.workflow
    try:
        definition, metadata = workflow_store.load_with_meta(binding)
    except WorkflowNotFoundError as exc:
        raise ToolException(f"workflow not found: {info.workflow}") from exc
    except AmbiguousWorkflowNameError as exc:
        raise ToolException(str(exc)) from exc
    except ValueError as exc:
        raise ToolException(f"workflow {info.workflow!r}: {exc}") from exc

    workflow_id = metadata.get("id") or info.workflow_id or ""
    workflow_name = metadata.get("name") or info.workflow

    overrides = params.get("inputs")
    if overrides is not None and not isinstance(overrides, dict):
        raise ToolException("'inputs' must be an object")

    inputs = {**info.inputs, **(overrides or {})}
    task_id = params.get("task_id")
    run_id = params.get("_run_id") or task_id

    # ``name`` in the run params is the WORKFLOW name: the history ``source``
    # field keeps meaning "workflow name / file path / inline", and the task
    # identity travels separately as ``task_name`` / ``task_def_id``.
    # ``source_dir`` stays None so the run's working directory falls through to
    # the per-run artifact directory instead of the workflow library.
    run_params = {
        "name": workflow_name,
        "inputs": inputs,
        "work_dir": params.get("work_dir") or info.work_dir,
    }
    return run_workflow(
        definition,
        run_params,
        stream_handler,
        task_id,
        run_id,
        task_name=info.name,
        task_def_id=info.id,
        workflow_id=workflow_id,
    )


API_MAP = {
    "task.list": task_list,
    "task.get": task_get,
    "task.save": task_save,
    "task.delete": task_delete,
    "task.execute": task_execute,
}
