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
  from :class:`ToolManager` plus the builtin workflow primitives (10 core
  by default; 13 extended opt-in via ``tools.atomic_extensions``);
- ``workflow.list_envs``   list every resolved environment from the
  :class:`EnvironmentRegistry`.
"""

from app.common.decorators import streaming
from app.common.exceptions import ToolException
from app.env.registry import get_env_registry
from app.tools.descriptor_tool import DescriptorTool
from app.tools.tool_manager import ToolManager
from app.workflow.definition import WorkflowDefinition
from app.workflow.runner import run_workflow
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
    Execution boilerplate (stream handler, context, engine) lives in
    :func:`app.workflow.runner.run_workflow`.
    """
    definition = _load_definition(params)
    task_id = params.get("task_id")
    return run_workflow(definition, params, stream_handler, task_id)


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
    ports (backend ``Port.to_dict`` always emits options/multi/direction).

    Input ports declared ``direction=output`` are mirrored into the
    ``outputs`` array (deduped by name) so the editor renders them as
    declared outputs — descriptor authors state the artifact port once
    (on the input side, where its value is bound) and the wire shape
    reflects it on both sides automatically.
    """
    descriptor = getattr(tool, "_descriptor", None)
    operations = getattr(descriptor, "operations", None) or []
    payload: list = []
    for operation in operations:
        inputs = [port.to_dict() for port in operation.inputs]
        outputs = [port.to_dict() for port in operation.outputs]
        # Mirror direction=output inputs into outputs (deduped by name).
        existing = {p["name"] for p in outputs}
        for port in operation.inputs:
            if (
                getattr(port, "direction", "input") == "output"
                and port.name not in existing
            ):
                outputs.append(port.to_dict())
                existing.add(port.name)
        payload.append(
            {
                "name": operation.name,
                "description": operation.description,
                "inputs": inputs,
                "outputs": outputs,
            }
        )
    return payload


def handle_list_tools(params, stream_handler):
    """List every registered tool from the unified registry.

    Every tool comes from :class:`ToolManager`'s shared registry: the
    shipped-native builtins (kind ``"shipped-native"`` — always valid, with
    their port contracts), native plugin tools (``"native"``), and descriptor
    tools (``"descriptor"``).  Each entry carries a ``kind`` and a
    ``description``; the legacy ``builtin`` boolean is ``True`` only for
    shipped-native so the renderer palette keeps grouping correctly until it
    migrates to ``kind`` (todo 16).  Descriptor tools that declare operations
    additionally expose them (T7).
    """
    tools = []
    tm = ToolManager.instance()
    registry = tm.get_registry()
    for name, tool in tm.get_all_tools().items():
        kind = registry.get_kind(name)
        if kind not in ("shipped-native", "native"):
            if isinstance(tool, DescriptorTool) or hasattr(tool, "_descriptor"):
                kind = "descriptor"

        if kind == "shipped-native":
            entry = {
                "name": name,
                "kind": "shipped-native",
                "is_valid": True,
                "version": "",
                "tool_path": "",
                "ports": tool.ports.to_dict(),
                "builtin": True,
                "description": tool.description,
            }
        elif kind == "native":
            entry = {
                "name": name,
                "kind": "native",
                "is_valid": getattr(tool, "is_valid", False),
                "version": getattr(tool, "version", ""),
                "tool_path": getattr(tool, "tool_path", ""),
                "builtin": False,
                "description": getattr(tool, "description", ""),
            }
            ports = getattr(tool, "ports", None)
            if ports is not None:
                entry["ports"] = ports.to_dict()
        elif kind == "descriptor":
            descriptor = getattr(tool, "_descriptor", None)
            entry = {
                "name": name,
                "kind": "descriptor",
                "is_valid": getattr(tool, "is_valid", False),
                "version": getattr(tool, "version", ""),
                "tool_path": getattr(tool, "tool_path", ""),
                "builtin": False,
                "description": (
                    getattr(descriptor, "description", "")
                    or getattr(descriptor, "display_name", "")
                ),
            }
            ports = getattr(tool, "ports", None)
            if ports is not None:
                entry["ports"] = ports.to_dict()
            operations = _operations_payload(tool)
            if operations:
                entry["operations"] = operations
        else:
            # Unknown kind (a discovered code-class BaseTool) — registry code
            # discovery is currently empty (only the excluded CommandTool), so
            # this branch is effectively unreachable; skip it to keep the wire
            # shape to the three documented kinds.
            continue

        tools.append(entry)
    return {"tools": tools}


def handle_list_envs(params, stream_handler):
    """List every resolved environment from the :class:`EnvironmentRegistry`."""
    registry = get_env_registry()
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
