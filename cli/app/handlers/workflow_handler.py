#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workflow IPC handlers — the whole workflow domain.

Exposes the workflow engine, the validator and the saved-workflow library to
the renderer over the existing ``call-backend-api`` JSON-RPC channel — no new
IPC channels (Metis #4).  The module-level ``API_MAP`` is auto-discovered by
:class:`app.api_handler.ApiHandler`, so these seven methods need no
registration code elsewhere:

- ``workflow.execute``  (@streaming)  run a workflow — either a saved one
  (by ``id``/``name``) or a definition supplied inline (``definition``) or as a
  file (``path``) — streaming node/terminal events to the renderer via the
  existing ``stream-event`` channel (the main process forwards ``result.type``
  dicts generically);
- ``workflow.validate``  statically validate a definition against the tool
  registry, returning a list of findings;
- ``workflow.save``      persist a definition in the saved-workflow library
  (create or overwrite by id), returning the id;
- ``workflow.load``      load a saved definition as JSON plus its wrapper
  metadata;
- ``workflow.list``      list metadata for every saved workflow;
- ``workflow.delete``    remove a saved workflow;
- ``workflow.import_path``  import workflow JSON file(s) from a file or
  directory path (e.g. ``examples/workflows/``).

Identity:
    A saved workflow is identified by an auto-generated ``wf-…`` id which is
    also its file name; its display name lives inside the definition and is
    free-form.  Every method accepts an ``id`` or a ``name`` (``id`` wins) so
    references written before ids existed keep working.

Storage lives in a lazily-created module singleton
:class:`app.workflow.store.FileWorkflowStore` (writable dir resolved from
``BT_WORKFLOWS_DIR``, falling back to ``<output_dir>/workflows``) so handlers
share one store per process without import-time side effects.
"""

import os

from app.common.decorators import logs_errors, streaming
from app.common.exceptions import ToolException
from app.workflow.definition import WorkflowDefinition
from app.workflow.runner import run_workflow
from app.workflow.store import (
    AmbiguousWorkflowNameError,
    FileWorkflowStore,
    WorkflowNotFoundError,
)
from app.workflow.validation import validate_workflow

_store = None


def _get_store() -> FileWorkflowStore:
    """Return the process-wide :class:`FileWorkflowStore`, creating it lazily.

    The store resolves its writable workflows directory on construction
    (``BT_WORKFLOWS_DIR`` or ``<output_dir>/workflows``) and runs the one-time
    legacy migrations there; creating it on first use keeps module import free
    of filesystem side effects.
    """
    global _store
    if _store is None:
        _store = FileWorkflowStore()
    return _store


def _resolve_id(params: dict) -> str:
    """Resolve the ``id``/``name`` params to a stored workflow id.

    ``id`` wins over ``name`` so a caller that knows the id never pays for a
    name scan.  Raises :class:`ToolException` when neither is given, when
    nothing matches, or when a name matches several workflows.
    """
    workflow_id = params.get("id")
    if workflow_id:
        store = _get_store()
        try:
            resolved = store.resolve(workflow_id)
        except AmbiguousWorkflowNameError as exc:
            raise ToolException(str(exc)) from None
        if resolved is None:
            raise ToolException(f"workflow not found: {workflow_id!r}")
        return resolved

    name = params.get("name")
    if not name:
        raise ToolException("missing 'id' or 'name' field")
    store = _get_store()
    try:
        resolved = store.resolve(name)
    except AmbiguousWorkflowNameError as exc:
        raise ToolException(str(exc)) from None
    if resolved is None:
        raise ToolException(f"workflow not found: {name!r}")
    return resolved


@logs_errors("WorkflowHandler")
def handle_save(params, stream_handler):
    """Persist a workflow definition (create or overwrite).

    Params:
        id: optional id to overwrite; omitted means "create a new workflow".
        name: display name (free-form — it no longer has to be path-safe,
            because it is no longer the file name).
        definition: dict accepted by :meth:`WorkflowDefinition.from_dict`.
        description: optional human-facing explanation.
        tags: optional list of free-form keywords.

    The top-level ``name`` is authoritative: it is injected into the definition
    before validation, so a caller cannot save a definition whose stored name
    disagrees with the name it sent.

    Returns:
        ``{"saved": True, "id": <id>, "name": <name>}``.
    """
    name = params.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ToolException("Missing 'name' field")

    raw_definition = params.get("definition") or {}
    if not isinstance(raw_definition, dict):
        raise ToolException("'definition' must be an object")
    definition = WorkflowDefinition.from_dict({**raw_definition, "name": name})

    metadata = {
        "description": params.get("description") or "",
        "tags": list(params.get("tags") or []),
    }
    requested_id = params.get("id")
    info = _get_store().save(definition, metadata, workflow_id=requested_id or None)
    return {"saved": True, "id": info.id, "name": info.name}


@logs_errors("WorkflowHandler")
def handle_load(params, stream_handler):
    """Load a saved workflow definition plus its wrapper metadata.

    Params:
        id: workflow id (preferred).
        name: display name to resolve (fallback).

    Returns:
        ``{"id": <str>, "name": <str>, "definition": <WorkflowDefinition.to_dict()>,
        "description": <str>, "tags": [<str>, ...],
        "created_at": <ISO-8601 str | None>,
        "updated_at": <ISO-8601 str | None>}``.

    Raises:
        ToolException: when neither reference is given, nothing matches, or a
            name matches several workflows.
    """
    workflow_id = _resolve_id(params)
    definition, metadata = _get_store().load_with_meta(workflow_id)
    return {
        "id": metadata.get("id") or workflow_id,
        "name": metadata.get("name") or definition.name,
        "definition": definition.to_dict(),
        "description": metadata.get("description") or "",
        "tags": list(metadata.get("tags") or []),
        "created_at": metadata.get("created_at"),
        "updated_at": metadata.get("updated_at"),
    }


@logs_errors("WorkflowHandler")
def handle_list(params, stream_handler):
    """List metadata for every saved workflow, sorted by display name.

    Returns:
        ``{"workflows": [{id, name, description, created_at, updated_at, tags,
        node_count}, ...]}``.  Corrupt/schema-invalid files are skipped by the
        store.
    """
    workflows = [
        {
            "id": info.id,
            "name": info.name,
            "description": info.description,
            "created_at": info.created_at,
            "updated_at": info.updated_at,
            "tags": info.tags,
            "node_count": info.node_count,
        }
        for info in _get_store().list()
    ]
    return {"workflows": workflows}


@logs_errors("WorkflowHandler")
def handle_delete(params, stream_handler):
    """Remove a saved workflow.

    Params:
        id: workflow id (preferred).
        name: display name to resolve (fallback).

    Returns:
        ``{"deleted": True, "id": <id>, "name": <name>}``.
    """
    workflow_id = _resolve_id(params)
    store = _get_store()
    definition, metadata = store.load_with_meta(workflow_id)
    store.delete(workflow_id)
    return {
        "deleted": True,
        "id": workflow_id,
        "name": metadata.get("name") or definition.name,
    }


def import_workflows_from_path(path: str, store=None) -> dict:
    """Import workflow JSON file(s) into the saved-workflow library.

    *path* may be a single ``.json`` workflow file or a directory (all
    ``*.json`` files inside are imported, sorted by name).  Each file is
    validated with :meth:`WorkflowDefinition.from_json_file` before saving;
    per-file failures are reported and do not stop the remaining files.

    Re-importing is idempotent: the display name comes from
    ``definition.name``, and when exactly one stored workflow already carries
    that name it is overwritten **keeping its id** (so task bindings and
    sub-workflow references survive a re-import).  A name that matches several
    workflows, or none, imports as a new workflow with a fresh id.

    Args:
        path: workflow JSON file or directory of workflow JSON files.
        store: a :class:`FileWorkflowStore`; defaults to the process-wide
            handler store (used by the ``workflow.import_path`` API).

    Returns:
        ``{"ok": bool, "imported": int, "failed": int,
        "results": [{file, status, id?, name?, reason?, renamed_from?}, ...]}``.
    """
    if store is None:
        store = _get_store()

    if os.path.isfile(path):
        files = [path]
    elif os.path.isdir(path):
        files = [
            os.path.join(path, f)
            for f in sorted(os.listdir(path))
            if f.endswith(".json")
            and os.path.isfile(os.path.join(path, f))
        ]
        if not files:
            raise ToolException(f"no *.json workflow files found in {path!r}")
    else:
        raise ToolException(f"path not found: {path!r}")

    results = []
    for fpath in files:
        fname = os.path.basename(fpath)
        stem = fname[: -len(".json")] if fname.endswith(".json") else fname
        try:
            definition = WorkflowDefinition.from_json_file(fpath)
        except ValueError as exc:
            results.append({"file": fname, "status": "failed",
                            "reason": str(exc)})
            continue

        existing_id = None
        try:
            existing_id = store.find_id_by_name(definition.name)
        except AmbiguousWorkflowNameError:
            # Several workflows already carry this name: importing as a new
            # one is the only answer that cannot overwrite the wrong file.
            existing_id = None

        info = store.save(definition, {}, workflow_id=existing_id)
        entry = {"file": fname, "id": info.id, "name": definition.name,
                 "status": "imported"}
        if stem != definition.name:
            entry["renamed_from"] = stem
        results.append(entry)

    failed = sum(1 for r in results if r["status"] == "failed")
    return {
        "ok": failed == 0,
        "imported": len(results) - failed,
        "failed": failed,
        "results": results,
    }


@logs_errors("WorkflowHandler")
def handle_import_path(params, stream_handler):
    """Import workflow(s) from a file or directory path.

    Params:
        path: a workflow JSON file or a directory of workflow JSON files
            (e.g. ``examples/workflows/android``).

    Returns:
        The import report from :func:`import_workflows_from_path`.
    """
    path = params.get("path")
    if not isinstance(path, str) or not path:
        raise ToolException("Missing 'path' field")
    return import_workflows_from_path(path)


def _load_inline_definition(params: dict):
    """Load a definition supplied inline (``definition``) or as a ``path``.

    ``path`` (a workflow JSON file on disk) takes precedence over an inline
    ``definition`` dict.

    Returns:
        ``(definition, source_dir)`` — ``source_dir`` is the folder the file
        was loaded from (``None`` for an inline definition), used as the run's
        working directory ahead of the run's artifact directory.
    """
    path = params.get("path")
    if path:
        return WorkflowDefinition.from_json_file(path), os.path.dirname(
            os.path.abspath(path)
        )
    if params.get("definition"):
        return WorkflowDefinition.from_dict(params["definition"]), None
    raise ToolException(
        "missing workflow reference: pass 'id'/'name', or 'definition'/'path'"
    )


@streaming
@logs_errors("WorkflowHandler")
def handle_execute(params, stream_handler):
    """Run a workflow, streaming node events when possible.

    Four mutually exclusive ways to name the workflow, tried in this order:

    - ``id``   — a saved workflow's storage id;
    - ``name`` — a saved workflow's display name;
    - ``definition`` — an inline definition (the editor's canvas);
    - ``path`` — a workflow JSON file on disk.

    The ``@streaming`` decorator runs this in a background thread (see
    ``app.api_handler.ApiHandler.stream_handler``); every dict passed to
    ``stream_handler`` is forwarded to the renderer over ``stream-event``.
    Execution boilerplate (stream handler, context, engine) lives in
    :func:`app.workflow.runner.run_workflow`.

    ``params["_run_id"]`` is injected by :class:`ApiHandler` and identifies
    the run for cancellation and event correlation.  When ``params`` carries no
    ``work_dir``, a file-loaded workflow uses its own folder and anything else
    uses the run's artifact directory (``$rundir``).
    """
    store = _get_store()
    workflow_id = ""
    source_dir = None

    ref = params.get("id") or params.get("name")
    if ref:
        try:
            resolved = store.resolve(ref)
        except AmbiguousWorkflowNameError as exc:
            raise ToolException(str(exc)) from None
        if resolved is None:
            raise ToolException(f"workflow not found: {ref!r}")
        workflow_id = resolved
        definition = store.load(workflow_id)
    else:
        definition, source_dir = _load_inline_definition(params)

    task_id = params.get("task_id")
    run_id = params.get("_run_id") or task_id
    return run_workflow(
        definition,
        params,
        stream_handler,
        task_id,
        run_id,
        source_dir=source_dir,
        workflow_id=workflow_id,
    )


@logs_errors("WorkflowHandler")
def handle_validate(params, stream_handler):
    """Statically validate a workflow definition against the tool registry.

    Params:
        definition: an inline definition dict (the editor's canvas).
        id / name: a saved workflow to validate instead.

    Returns ``{"errors": [...]}`` where each entry is
    ``{"node_id", "field", "message", "severity"}``; an empty list means the
    definition is valid.

    A structurally invalid definition (e.g. a broken linear chain — several
    entry nodes) is reported as a single workflow-level finding instead of
    raising: :meth:`WorkflowDefinition.from_dict` raises ``ValueError`` /
    ``TypeError``, and letting that escape turned every such request into a
    handler error, so callers only ever got an error message and could never
    list what was wrong.
    """
    try:
        if params.get("id") or params.get("name"):
            definition = _get_store().load(_resolve_id(params))
        else:
            definition = WorkflowDefinition.from_dict(params.get("definition") or {})
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "errors": [
                {
                    "node_id": None,
                    "field": "structure",
                    "message": str(exc),
                    "severity": "error",
                }
            ]
        }

    from app.tools.tool_manager import ToolManager

    errors = validate_workflow(definition, ToolManager.instance())
    return {
        "errors": [
            {
                "node_id": error.node_id,
                "field": error.field,
                "message": error.message,
                "severity": error.severity,
            }
            for error in errors
        ]
    }


API_MAP = {
    "workflow.execute": handle_execute,
    "workflow.validate": handle_validate,
    "workflow.save": handle_save,
    "workflow.load": handle_load,
    "workflow.list": handle_list,
    "workflow.delete": handle_delete,
    "workflow.import_path": handle_import_path,
}
