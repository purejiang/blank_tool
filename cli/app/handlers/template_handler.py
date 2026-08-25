#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Template CRUD + execute IPC handlers.

Exposes workflow-template storage and execution to the renderer over the
existing ``call-backend-api`` JSON-RPC channel — no new IPC channels.  The
module-level ``API_MAP`` is auto-discovered by :class:`app.api_handler.ApiHandler`:

- ``template.save``    persist a :class:`WorkflowDefinition` under a name,
  with a description and tag list (create or overwrite);
- ``template.load``    load a saved definition as a JSON dict; raises
  :class:`TemplateNotFoundError` when the name is unknown;
- ``template.list``    list metadata for every stored template (name,
  description, timestamps, tags, node count);
- ``template.delete``  remove a stored template; raises
  :class:`TemplateNotFoundError` when the name is unknown;
- ``template.import_path``  import workflow JSON file(s) from a file or
  directory path into the store (e.g. from ``examples/workflows/``);
- ``template.execute`` (@streaming)  load a saved template and run it with the
  workflow engine, streaming node/terminal events to the renderer via the
  existing ``stream-event`` channel — mirrors ``workflow.execute`` except the
  definition comes from the template store instead of inline params.

Storage lives in a lazily-created module singleton
:class:`app.template.store.FileTemplateStore` (writable dir resolved from
``BT_TEMPLATES_DIR``, falling back to ``<output_dir>/templates``) so handlers
share one store per process without import-time side effects.
"""

import os

from app.common.decorators import logs_errors, streaming
from app.common.exceptions import ToolException
from app.template.store import FileTemplateStore, TemplateNotFoundError
from app.workflow.definition import WorkflowDefinition
from app.workflow.runner import run_workflow

_store = None


def _get_store() -> FileTemplateStore:
    """Return the process-wide :class:`FileTemplateStore`, creating it lazily.

    The store resolves its writable templates directory on construction
    (``BT_TEMPLATES_DIR`` or ``<output_dir>/templates``); creating it on first
    use keeps module import free of filesystem side effects.
    """
    global _store
    if _store is None:
        _store = FileTemplateStore()
    return _store


@logs_errors("TemplateHandler")
def handle_save(params, stream_handler):
    """Persist a workflow definition under ``name`` (create or overwrite).

    Params:
        name: template name (must be path-safe).
        definition: dict accepted by :meth:`WorkflowDefinition.from_dict`.
        description: optional human-facing explanation.
        tags: optional list of free-form keywords.

    Returns:
        ``{"saved": True, "name": <name>}``.
    """
    name = params.get("name")
    definition = WorkflowDefinition.from_dict(params.get("definition") or {})
    metadata = {
        "description": params.get("description") or "",
        "tags": list(params.get("tags") or []),
    }
    _get_store().save(name, definition, metadata)
    return {"saved": True, "name": name}


@logs_errors("TemplateHandler")
def handle_load(params, stream_handler):
    """Load a saved template definition as a JSON-able dict.

    Params:
        name: template name to load.

    Returns:
        ``{"definition": <WorkflowDefinition.to_dict()>}``.

    Raises:
        TemplateNotFoundError: if no template with *name* exists.
    """
    name = params.get("name")
    definition = _get_store().load(name)
    return {"definition": definition.to_dict()}


@logs_errors("TemplateHandler")
def handle_list(params, stream_handler):
    """List metadata for every stored template, sorted by name.

    Returns:
        ``{"templates": [{name, description, created_at, updated_at, tags,
        node_count}, ...]}``.  Corrupt/schema-invalid files are skipped by
        the store.
    """
    templates = [
        {
            "name": template.name,
            "description": template.description,
            "created_at": template.created_at,
            "updated_at": template.updated_at,
            "tags": template.tags,
            "node_count": template.node_count,
        }
        for template in _get_store().list()
    ]
    return {"templates": templates}


@logs_errors("TemplateHandler")
def handle_delete(params, stream_handler):
    """Remove the template stored under ``name``.

    Params:
        name: template name to delete.

    Returns:
        ``{"deleted": True, "name": <name>}``.

    Raises:
        TemplateNotFoundError: if no template with *name* exists.
    """
    name = params.get("name")
    _get_store().delete(name)
    return {"deleted": True, "name": name}


def import_templates_from_path(path: str, store=None) -> dict:
    """Import workflow JSON file(s) into the template store.

    *path* may be a single ``.json`` workflow file or a directory (all
    ``*.json`` files inside are imported, sorted by name).  Each file is
    validated with :meth:`WorkflowDefinition.from_json_file` before saving;
    per-file failures are reported and do not stop the remaining files.

    The template name comes from ``definition.name`` (the schema guarantees
    a non-empty name); when it differs from the file stem the entry carries
    ``renamed_from`` so callers can surface the discrepancy.

    Args:
        path: workflow JSON file or directory of workflow JSON files.
        store: a :class:`FileTemplateStore`; defaults to the process-wide
            handler store (used by the ``template.import_path`` API).

    Returns:
        ``{"ok": bool, "imported": int, "failed": int,
        "results": [{file, status, name?, reason?, renamed_from?}, ...]}``.
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
        store.save(definition.name, definition, {})
        entry = {"file": fname, "name": definition.name,
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


@logs_errors("TemplateHandler")
def handle_template_import_path(params, stream_handler):
    """Import workflow template(s) from a file or directory path.

    Params:
        path: a workflow JSON file or a directory of workflow JSON files
            (e.g. ``examples/workflows/android``).

    Returns:
        The import report from :func:`import_templates_from_path`.
    """
    path = params.get("path")
    if not isinstance(path, str) or not path:
        raise ToolException("Missing 'path' field")
    return import_templates_from_path(path)


@streaming
@logs_errors("TemplateHandler")
def handle_execute(params, stream_handler):
    """Run a saved template, streaming node events when possible.

    Mirrors ``workflow.execute``: the definition is loaded from the template
    store (by name) instead of from inline params.  The ``@streaming``
    decorator runs this in a background thread; every dict passed to
    ``stream_handler`` is forwarded to the renderer over ``stream-event``.

    Params:
        name: template name to load and run.
        inputs: workflow-level input values (``$inputs.<key>``).
        task_id: optional task identifier, forwarded to tools and used as the
            workflow_id on streamed events.
        work_dir: optional working directory (defaults to ".").

    Returns:
        Same shape as ``workflow.execute``:
        ``{"success", "outputs", "node_results", "error"}``.
    """
    name = params.get("name")
    task_id = params.get("task_id")
    definition = _get_store().load(name)
    return run_workflow(definition, params, stream_handler, task_id)


API_MAP = {
    "template.save": handle_save,
    "template.load": handle_load,
    "template.list": handle_list,
    "template.delete": handle_delete,
    "template.import_path": handle_template_import_path,
    "template.execute": handle_execute,
}
