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
- ``template.execute`` (@streaming)  load a saved template and run it with the
  workflow engine, streaming node/terminal events to the renderer via the
  existing ``stream-event`` channel — mirrors ``workflow.execute`` except the
  definition comes from the template store instead of inline params.

Storage lives in a lazily-created module singleton
:class:`app.template.store.FileTemplateStore` (writable dir resolved from
``BT_TEMPLATES_DIR``, falling back to ``<output_dir>/templates``) so handlers
share one store per process without import-time side effects.
"""

from app.common.decorators import logs_errors, streaming
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
    "template.execute": handle_execute,
}
