#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Headless CLI entry point for the Blank Tool workflow system.

Provides five subcommands (``run``, ``list-tools``, ``list-envs``,
``validate``, ``list-templates``) that operate independently of the Electron
app — no stdin JSON-RPC pipe, no streaming IPC.  The CLI initializes logging
and config (the same setup ``main.bootstrap`` performs), then invokes the
workflow engine, validator, tool registry and environment registry directly.

The ``run`` subcommand resolves its target as a workflow JSON file or a
saved template name, parses ``--input key=value`` pairs (with basic type
coercion), executes the workflow through the engine while streaming node
events to the console, and prints the final result as JSON (``--json``) or
a human-readable summary.

Usage (from the ``backend/`` directory):

    python cli.py --help
    python cli.py list-tools
    python cli.py list-envs
    python cli.py validate <workflow.json>
    python cli.py list-templates
    python cli.py run <workflow.json|template-name> --input key=value
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

# Make the backend/ directory importable regardless of the working directory.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Shared bootstrap (dotenv + server config + logging); import it from main
# rather than duplicating it here.
from main import bootstrap


# ------------------------------------------------------------------
# Table rendering
# ------------------------------------------------------------------


def _print_table(headers: List[str], rows: List[List[str]]) -> None:
    """Print an aligned, fixed-width text table to stdout."""
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def _line(values: List[str]) -> str:
        return "  ".join(value.ljust(widths[i]) for i, value in enumerate(values))

    print(_line(headers))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print(_line(row))


# ------------------------------------------------------------------
# Subcommand handlers
# ------------------------------------------------------------------


def cmd_list_tools() -> int:
    """List every registered tool (descriptor/code + builtin primitives)."""
    from app.tools.tool_manager import ToolManager
    from app.workflow.engine import _BUILTIN_TOOLS

    rows: List[List[str]] = []
    tm = ToolManager.instance()
    for name, tool in tm.get_all_tools().items():
        tool_type = getattr(tool, "type", None) or type(tool).__name__
        rows.append(
            [
                name,
                tool_type,
                "yes" if getattr(tool, "is_valid", False) else "no",
                getattr(tool, "version", "") or "",
            ]
        )
    for name in sorted(_BUILTIN_TOOLS):
        rows.append([name, "builtin", "yes", ""])

    _print_table(["name", "type", "is_valid", "version"], rows)
    return 0


def cmd_list_envs() -> int:
    """List every resolved environment (java, python, node, ...)."""
    from app.env.registry import EnvironmentRegistry

    registry = EnvironmentRegistry()
    registry.discover()
    rows: List[List[str]] = []
    for env in registry.list_all():
        rows.append(
            [
                env.name,
                "yes" if env.is_valid else "no",
                env.version or "",
                env.binary_path or "",
            ]
        )

    _print_table(["name", "is_valid", "version", "binary_path"], rows)
    return 0


def _augment_registry_with_tool_dirs(
    tool_dirs: List[str],
) -> "ToolManager":
    """Load descriptor tools from *tool_dirs* into an augmented registry.

    Each *tool_dirs* entry is a directory of ``*.json`` tool descriptors.
    Malformed files are skipped with a warning.  The returned registry
    exposes the same ``get_tool(name)`` interface as :class:`ToolManager`,
    with descriptor tools overriding same-named entries from the base
    singleton.  When no descriptors are loaded the base singleton is
    returned unchanged.
    """
    from app.tools.tool_manager import ToolManager
    from app.tools.descriptor_tool import DescriptorTool, load_descriptor
    from app.env.registry import EnvironmentRegistry

    base = ToolManager.instance()
    env_registry = EnvironmentRegistry()
    descriptor_tools: Dict[str, Any] = {}

    for tool_dir in tool_dirs:
        if not os.path.isdir(tool_dir):
            print(
                f"warning: --tool-dir is not a directory: {tool_dir}",
                file=sys.stderr,
            )
            continue
        for fname in sorted(os.listdir(tool_dir)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(tool_dir, fname)
            try:
                desc = load_descriptor(fpath)
            except ValueError as exc:
                print(
                    f"warning: skipping malformed descriptor {fpath}: {exc}",
                    file=sys.stderr,
                )
                continue
            try:
                tool = DescriptorTool(desc, env_registry)
            except Exception as exc:
                print(
                    f"warning: skipping descriptor {fpath}: {exc}",
                    file=sys.stderr,
                )
                continue
            descriptor_tools[desc.name] = tool

    if not descriptor_tools:
        return base

    # Thin composite — validate_workflow / WorkflowEngine only call get_tool().
    class _AugmentedRegistry:
        def get_tool(self, name: str):
            if name in descriptor_tools:
                return descriptor_tools[name]
            return base.get_tool(name)

    return _AugmentedRegistry()


def cmd_validate(path: str, tool_dirs: Optional[List[str]] = None) -> int:
    """Validate a workflow definition file against the tool registry."""
    from app.tools.tool_manager import ToolManager
    from app.workflow.definition import WorkflowDefinition
    from app.workflow.validation import validate_workflow

    try:
        definition = WorkflowDefinition.from_json_file(path)
    except ValueError as exc:
        print(f"invalid workflow: {exc}", file=sys.stderr)
        return 1

    registry = (
        _augment_registry_with_tool_dirs(tool_dirs)
        if tool_dirs
        else ToolManager.instance()
    )
    errors = validate_workflow(definition, registry)
    real_errors = [e for e in errors if e.severity == "error"]
    warn_entries = [e for e in errors if e.severity != "error"]

    for w in warn_entries:
        node = w.node_id if w.node_id is not None else "-"
        print(f"[{w.severity}] node={node} field={w.field}: {w.message}")

    if not real_errors:
        print("valid")
        return 0

    for error in real_errors:
        node = error.node_id if error.node_id is not None else "-"
        print(f"[{error.severity}] node={node} field={error.field}: {error.message}")
    return 1


def cmd_list_templates() -> int:
    """List saved workflow templates.

    The template store (a later todo) may not exist yet; degrade gracefully
    with a message instead of crashing.
    """
    try:
        from app.template.store import FileTemplateStore
    except ImportError:
        print("template system not available")
        return 0

    try:
        store = FileTemplateStore()
        templates = store.list()
    except Exception as exc:
        print(f"error listing templates: {exc}", file=sys.stderr)
        return 1

    for template in templates:
        print(getattr(template, "name", template))
    return 0


# ------------------------------------------------------------------
# Workflow run (console streaming)
# ------------------------------------------------------------------

_EVENT_COLORS = {
    "node_started": "\033[36m",  # cyan
    "node_completed": "\033[32m",  # green
    "workflow_completed": "\033[32m",  # green
    "node_failed": "\033[31m",  # red
    "workflow_failed": "\033[31m",  # red
}
_RESET = "\033[0m"


def _coerce_input_value(value: str) -> Any:
    """Coerce a raw ``--input`` value to a typed Python value.

    ``true``/``false`` (case-insensitive) become bools, integer and float
    literals become numbers, everything else stays a string.
    """
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _make_console_stream_handler(use_color: bool, stream):
    """Build a callback that renders workflow event dicts as console lines.

    The returned callable receives event dicts (``{"type": ..., ...}``) and
    prints one human-readable line per event, e.g. ``[node_completed] convert
    (123 ms)``.  When *use_color* is True the event tag is ANSI-colored.
    *stream* is the output target: stdout normally, stderr for ``--json`` so
    stdout stays a pure JSON document.
    """

    def _render(event: Dict[str, Any]) -> str:
        event_type = event.get("type") or "event"
        if event_type == "node_started":
            message = f"{event.get('node_id', '?')} ({event.get('tool', '')})"
        elif event_type == "node_completed":
            message = (
                f"{event.get('node_id', '?')} ({event.get('duration_ms', '?')} ms)"
            )
        elif event_type == "node_failed":
            message = f"{event.get('node_id', '?')}: {event.get('error', '')}"
        elif event_type == "node_output":
            message = (
                f"{event.get('node_id', '?')}: "
                f"{json.dumps(event.get('data', {}), default=str, ensure_ascii=False)}"
            )
        elif event_type == "workflow_completed":
            message = f"success={event.get('success', '?')}"
        elif event_type == "workflow_failed":
            message = str(event.get("error", ""))
        else:
            message = json.dumps(event, default=str, ensure_ascii=False)
        line = f"[{event_type}] {message}" if message else f"[{event_type}]"
        if use_color and event_type in _EVENT_COLORS:
            line = f"{_EVENT_COLORS[event_type]}{line}{_RESET}"
        return line

    def _handle_event(event: Dict[str, Any]) -> None:
        print(_render(event), file=stream)

    return _handle_event


def _resolve_definition(target: str) -> Optional["WorkflowDefinition"]:
    """Load the workflow definition for *target*.

    A ``.json`` suffix or an existing file path loads via
    :meth:`WorkflowDefinition.from_json_file`; anything else is treated as a
    template name resolved through :class:`FileTemplateStore`.  Returns the
    definition, or None after printing an error to stderr.
    """
    if target.endswith(".json") or os.path.isfile(target):
        try:
            from app.workflow.definition import WorkflowDefinition

            return WorkflowDefinition.from_json_file(target)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return None

    try:
        from app.template.store import FileTemplateStore, TemplateNotFoundError

        return FileTemplateStore().load(target)
    except (TemplateNotFoundError, ValueError) as exc:
        print(f"error: template {target!r}: {exc}", file=sys.stderr)
        return None


def cmd_run(
    target: str,
    raw_inputs: Optional[List[str]],
    task_id: Optional[str],
    json_output: bool,
    tool_dirs: Optional[List[str]] = None,
) -> int:
    """Run a workflow from a JSON file or template name.

    Resolves *target*, parses and coerces ``--input key=value`` pairs,
    executes the workflow through :class:`WorkflowEngine`, streams node
    events to the console, and prints the final result as JSON (``--json``)
    or a human-readable summary.  Returns 0 on success, 1 on failure.
    """
    from app.workflow.engine import ExecutionContext, WorkflowEngine
    from app.workflow.streaming import WorkflowStreamHandler

    definition = _resolve_definition(target)
    if definition is None:
        return 1

    inputs = _parse_key_values(raw_inputs or [])
    use_color = (not json_output) and sys.stdout.isatty()
    stream = sys.stderr if json_output else sys.stdout
    raw_stream_handler = _make_console_stream_handler(use_color, stream)
    workflow_stream = WorkflowStreamHandler(
        workflow_id=task_id or "cli", callback=raw_stream_handler
    )

    context = ExecutionContext(
        work_dir=os.getcwd(),
        task_id=task_id,
        stream_handler=raw_stream_handler,
        workflow_stream=workflow_stream,
    )

    registry = (
        _augment_registry_with_tool_dirs(tool_dirs)
        if tool_dirs
        else None
    )
    try:
        result = WorkflowEngine(registry=registry).execute(definition, inputs, context)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if json_output:
        print(
            json.dumps(
                {
                    "success": result.success,
                    "outputs": result.outputs,
                    "node_results": result.node_results,
                    "error": result.error,
                },
                indent=2,
                default=str,
                ensure_ascii=False,
            )
        )
    else:
        print(f"success: {result.success}")
        if result.outputs:
            print(
                "outputs: "
                + json.dumps(result.outputs, indent=2, default=str, ensure_ascii=False)
            )
        if result.error:
            print(f"error: {result.error}")

    return 0 if result.success else 1


def _parse_key_values(pairs: List[str]) -> Dict[str, Any]:
    """Build a dict from ``key=value`` strings (split on the first ``=``).

    Values are type-coerced via :func:`_coerce_input_value` (bool / number /
    string).  Malformed entries are skipped with a warning.
    """
    result: Dict[str, Any] = {}
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if not separator:
            print(
                f"warning: ignoring input {pair!r} (expected key=value)",
                file=sys.stderr,
            )
            continue
        result[key.strip()] = _coerce_input_value(value.strip())
    return result


# ------------------------------------------------------------------
# Argument parsing and dispatch
# ------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blank-tool-cli",
        description="Blank Tool workflow CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    run_parser = subparsers.add_parser("run", help="Run a workflow from file or template")
    run_parser.add_argument("target", help="Path to workflow JSON file or template name")
    run_parser.add_argument("--input", action="append", help="Input as key=value (repeatable)")
    run_parser.add_argument("--task-id", help="Task ID for logging")
    run_parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    run_parser.add_argument(
        "--tool-dir", action="append", default=None,
        help="Directory of *.json tool descriptors to load (repeatable)",
    )

    # list-tools
    subparsers.add_parser("list-tools", help="List available tools")

    # list-envs
    subparsers.add_parser("list-envs", help="List resolved environments")

    # validate
    validate_parser = subparsers.add_parser("validate", help="Validate a workflow definition")
    validate_parser.add_argument("path", help="Path to workflow JSON file")
    validate_parser.add_argument(
        "--tool-dir", action="append", default=None,
        help="Directory of *.json tool descriptors to load (repeatable)",
    )

    # list-templates
    subparsers.add_parser("list-templates", help="List saved workflow templates")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Bootstrap, parse arguments and dispatch to a subcommand handler."""
    bootstrap()
    parser = _build_parser()
    args = parser.parse_args(argv)

    handlers = {
        "run": lambda: cmd_run(args.target, args.input, args.task_id, args.json, args.tool_dir),
        "list-tools": cmd_list_tools,
        "list-envs": cmd_list_envs,
        "validate": lambda: cmd_validate(args.path, args.tool_dir),
        "list-templates": cmd_list_templates,
    }

    try:
        return handlers[args.command]()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
