#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tool listing, version, and search-mode handlers.
"""

import os

from app.tools.tool_manager import ToolManager
from app.tools.descriptor_tool import DescriptorTool
from app.common.exceptions import ToolNotFoundError, ToolException
from app.common.decorators import logs_errors
from app.utils.logger import Logger

logger = Logger.get_logger("ToolHandler")


def _get_manager() -> ToolManager:
    """Return the process-wide :class:`ToolManager`.

    Resolved per call rather than captured in a module-level global: a global
    would freeze whichever instance existed when this module was first
    imported, which makes handler behaviour depend on import order (and breaks
    callers that patch the singleton, e.g. the contract-test mock).
    """
    return ToolManager.instance()


def _get_registry():
    """Return the underlying ToolRegistry (for tests to patch)."""
    return _get_manager().get_registry()


def _source_for(mgr: ToolManager, name: str, path: str):
    # ``_default_tool_path`` always returns "" (no bundled binary path is
    # derived from a tool name anymore), so the "builtin" branch is dead:
    # a tool is on a custom/system path ("system") or unresolved ("none").
    return "system" if path else "none"


@logs_errors("ToolHandler")
def get_tools(params, stream_handler):
    tool_name = params.get("tool_name")
    refresh = bool(params.get("refresh", False))

    if refresh:
        _get_manager().refresh_tools()
    if tool_name:
        tool = _get_manager().get_tool(tool_name)
        if not tool:
            raise ToolNotFoundError(tool_name)
        info = {
            "name": tool_name,
            "is_valid": bool(getattr(tool, "is_valid", False)),
            "version": getattr(tool, "version", ""),
            "path": getattr(tool, "tool_path", ""),
        }
        info["source"] = _source_for(_get_manager(), tool_name, info["path"])
        info["status"] = "available" if info["is_valid"] else "unavailable"
        # WP3 #14: descriptor tools expose their declared environment deps.
        descriptor = getattr(tool, "_descriptor", None)
        env_deps = getattr(descriptor, "env_deps", None)
        if isinstance(env_deps, (list, tuple)):
            info["env_deps"] = list(env_deps)
        return info
    report = {}
    for name, tool in _get_manager().get_all_tools().items():
        item = {
            "is_valid": bool(getattr(tool, "is_valid", False)),
            "version": getattr(tool, "version", ""),
            "path": getattr(tool, "tool_path", ""),
        }
        item["source"] = _source_for(_get_manager(), name, item["path"])
        item["status"] = "available" if item["is_valid"] else "unavailable"
        report[name] = item
    return report


@logs_errors("ToolHandler")
def tool_version(params, stream_handler):
    tool_name = params.get("tool_name")
    if not tool_name:
        raise ToolException("Missing 'tool_name' field")
    tool = _get_manager().get_tool(tool_name)
    if not tool or not getattr(tool, "is_valid", False):
        raise ToolNotFoundError(tool_name)
    return {"version": getattr(tool, "version", "")}


@logs_errors("ToolHandler")
def set_search_mode(params, stream_handler):
    enabled = bool(params.get("system_search", False))
    if enabled:
        os.environ["BT_SEARCH_SYSTEM_TOOLS"] = "1"
    else:
        if "BT_SEARCH_SYSTEM_TOOLS" in os.environ:
            del os.environ["BT_SEARCH_SYSTEM_TOOLS"]
    _get_manager().refresh_tools()
    return {"system_search": enabled}


@logs_errors("ToolHandler")
def set_custom_path(params, stream_handler):
    """Set a custom path for a specific tool."""
    tool_name = params.get("tool_name", "")
    path = params.get("path", "")

    if not tool_name:
        raise ToolException("Missing tool_name")

    try:
        result = _get_manager().set_custom_path(tool_name, path)
        return result
    except ToolNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Failed to set custom path for {tool_name}: {e}")
        raise ToolException(str(e))


@logs_errors("ToolHandler")
def reset_custom_path(params, stream_handler):
    """Reset a tool to its default path."""
    tool_name = params.get("tool_name", "")

    if not tool_name:
        raise ToolException("Missing tool_name")

    try:
        result = _get_manager().reset_custom_path(tool_name)
        return result
    except ToolNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Failed to reset custom path for {tool_name}: {e}")
        raise ToolException(str(e))


def get_custom_paths(params, stream_handler):
    """Get all custom tool path overrides."""
    return _get_manager().get_custom_paths()


@logs_errors("ToolHandler")
def handle_tool_add(params, stream_handler):
    """Add a tool descriptor to the writable overlay registry.

    Raises:
        ToolException: on a missing/invalid ``descriptor`` or when the
            descriptor fails validation (WP0 #7: no more ``{"error"}``
            payload reported as success).
    """
    descriptor = params.get("descriptor")
    if not isinstance(descriptor, dict):
        raise ToolException("Missing or invalid 'descriptor' field")

    try:
        registry = _get_registry()
        tool = registry.add_descriptor_file(descriptor)
        return {
            "name": tool.name,
            "is_valid": getattr(tool, "is_valid", False),
            "path": getattr(tool, "tool_path", ""),
        }
    except ValueError as e:
        raise ToolException(str(e)) from e


@logs_errors("ToolHandler")
def handle_tool_delete(params, stream_handler):
    """Remove a tool descriptor from the writable overlay registry.

    Raises:
        ToolException: on a missing ``name``, or when *name* has no overlay
            descriptor (bundled tools are protected).
    """
    name = params.get("name", "")
    if not name:
        raise ToolException("Missing 'name' field")

    try:
        registry = _get_registry()
        registry.delete_descriptor(name)
        return {"deleted": name}
    except ValueError as e:
        raise ToolException(str(e)) from e


@logs_errors("ToolHandler")
def handle_tool_import_pack(params, stream_handler):
    """Import a tool pack: a directory, a single ``*.json``, or a ``*.zip``.

    Params:
        path: a directory of tool descriptor JSON files (e.g.
            ``examples/tools/android``) — the directory IS the pack, no
            manifest file is required — a single descriptor file, or a zip
            archive whose descriptors sit in the archive root.

    The UI's one import entry point funnels all three shapes here so the
    caller does not have to pre-classify the user's pick.

    Returns the registry's two-phase import report:
    ``{"ok", "imported", "updated", "failed", "results": [...]}``.
    """
    path = params.get("path")
    if not isinstance(path, str) or not path:
        raise ToolException("Missing 'path' field")
    return _get_registry().import_pack(path)


def _operations_payload(tool) -> list:
    """Serialize a descriptor tool's operations for the workflow editor (T7).

    Returns ``[]`` for non-descriptor tools (builtins) and descriptors
    without operations, so the ``tool.list`` wire shape only gains the additive
    ``operations`` key when it is meaningful.  Each entry is
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


@logs_errors("ToolHandler")
def handle_tool_list(params, stream_handler):
    """List every registered tool from the unified registry.

    This is the *catalog* projection the workflow editor's palette and the
    tools page read (it carries ports / operations / ``env_deps``); the
    registry view with per-tool ``status`` is ``tool.get_tools``.

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
            # WP3 #14: descriptor tools declare the environments they need.
            env_deps = getattr(descriptor, "env_deps", None)
            entry["env_deps"] = (
                list(env_deps) if isinstance(env_deps, (list, tuple)) else []
            )
        else:
            # Unknown kind (a discovered code-class BaseTool) — registry code
            # discovery is currently empty (only the excluded CommandTool), so
            # this branch is effectively unreachable; skip it to keep the wire
            # shape to the three documented kinds.
            continue

        tools.append(entry)
    return {"tools": tools}


API_MAP = {
    "tool.version": tool_version,
    "tool.get_tools": get_tools,
    "tool.list": handle_tool_list,
    "tool.set_search_mode": set_search_mode,
    "tool.set_custom_path": set_custom_path,
    "tool.reset_custom_path": reset_custom_path,
    "tool.get_custom_paths": get_custom_paths,
    "tool.add": handle_tool_add,
    "tool.delete": handle_tool_delete,
    "tool.import_pack": handle_tool_import_pack,
}
