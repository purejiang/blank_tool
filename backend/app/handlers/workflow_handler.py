#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workflow IPC handlers.

Exposes the workflow engine, validator, tool registry and environment
registry to the renderer over the existing ``call-backend-api`` JSON-RPC
channel — no new IPC channels (Metis #4).  The module-level ``API_MAP`` is
auto-discovered by :class:`app.api_handler.ApiHandler`, so these four methods
need no registration code elsewhere:

- ``workflow.execute``   (@streaming)  run a workflow definition, streaming
  node/terminal events to the renderer via the existing ``stream-event``
  channel (the main process forwards ``result.type`` dicts generically);
- ``workflow.validate``  statically validate a workflow definition against
  the tool registry, returning a list of findings;
- ``workflow.list_tools``  list every registered tool — descriptor/code tools
  from :class:`ToolManager` plus the 18 builtin workflow primitives;
- ``workflow.list_envs``   list every resolved environment from the
  :class:`EnvironmentRegistry`.
"""

from app.common.decorators import streaming
from app.common.exceptions import ToolException
from app.env.registry import EnvironmentRegistry
from app.tools.tool_manager import ToolManager
from app.workflow.definition import WorkflowDefinition
from app.workflow.engine import ExecutionContext, WorkflowEngine, _BUILTIN_TOOLS
from app.workflow.streaming import WorkflowStreamHandler
from app.workflow.validation import validate_workflow


def _load_definition(params: dict) -> WorkflowDefinition:
    """Load the workflow definition from params.

    ``path`` (a workflow JSON file on disk) takes precedence over an inline
    ``definition`` dict.  Raises :class:`ToolException` when neither is given.
    """
    if params.get("path"):
        return WorkflowDefinition.from_json_file(params["path"])
    if params.get("definition"):
        return WorkflowDefinition.from_dict(params["definition"])
    raise ToolException("missing definition or path")


@streaming
def handle_execute(params, stream_handler):
    """Run a workflow definition, streaming node events when possible.

    The ``@streaming`` decorator runs this in a background thread (see
    ``app.api_handler.ApiHandler.stream_handler``); every dict passed to
    ``stream_handler`` is forwarded to the renderer over ``stream-event``.
    """
    definition = _load_definition(params)
    inputs = params.get("inputs") or {}
    task_id = params.get("task_id")
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


def handle_validate(params, stream_handler):
    """Statically validate a workflow definition against the tool registry.

    Returns ``{"errors": [...]}`` where each entry is
    ``{"node_id", "field", "message", "severity"}``; an empty list means the
    definition is valid.
    """
    definition = WorkflowDefinition.from_dict(params["definition"])
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


def _operations_payload(tool) -> list:
    """Serialize a descriptor tool's operations for the workflow editor (T7).

    Returns ``[]`` for non-descriptor tools (builtins) and descriptors
    without operations, so the ``workflow.list_tools`` wire shape only gains
    the additive ``operations`` key when it is meaningful.  Each entry is
    ``{"name", "description", "inputs", "outputs"}`` with PortJSON-compatible
    ports (backend ``Port.to_dict`` always emits options/multi).
    """
    descriptor = getattr(tool, "_descriptor", None)
    operations = getattr(descriptor, "operations", None) or []
    return [
        {
            "name": operation.name,
            "description": operation.description,
            "inputs": [port.to_dict() for port in operation.inputs],
            "outputs": [port.to_dict() for port in operation.outputs],
        }
        for operation in operations
    ]


def handle_list_tools(params, stream_handler):
    """List every registered tool.

    Descriptor/code tools come from :class:`ToolManager` (with their runtime
    state); the 18 builtin workflow primitives come from the engine's
    ``_BUILTIN_TOOLS`` registry (always valid, with their port contracts).
    Descriptor tools that declare operations additionally expose them (T7).
    """
    tools = []
    tm = ToolManager.instance()
    for name, tool in tm.get_all_tools().items():
        entry = {
            "name": name,
            "is_valid": getattr(tool, "is_valid", False),
            "version": getattr(tool, "version", ""),
            "tool_path": getattr(tool, "tool_path", ""),
        }
        operations = _operations_payload(tool)
        if operations:
            entry["operations"] = operations
        tools.append(entry)
    for name, tool in _BUILTIN_TOOLS.items():
        tools.append(
            {
                "name": name,
                "is_valid": True,
                "version": "",
                "tool_path": "",
                "ports": tool.ports.to_dict(),
                "builtin": True,
            }
        )
    return {"tools": tools}


def handle_list_envs(params, stream_handler):
    """List every resolved environment from the :class:`EnvironmentRegistry`."""
    registry = EnvironmentRegistry()
    registry.discover()
    envs = registry.list_all()
    return {
        "environments": [
            {
                "name": env.name,
                "is_valid": env.is_valid,
                "binary_path": env.binary_path,
                "version": env.version,
                "root_path": env.root_path,
            }
            for env in envs
        ]
    }


API_MAP = {
    "workflow.execute": handle_execute,
    "workflow.validate": handle_validate,
    "workflow.list_tools": handle_list_tools,
    "workflow.list_envs": handle_list_envs,
}
