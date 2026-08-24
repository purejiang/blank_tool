#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Headless CLI entry point for the Blank Tool workflow system.

Provides six subcommands (``run``, ``list-tools``, ``list-envs``,
``validate``, ``tool``, ``list-templates``) that operate independently of the Electron
app — no stdin JSON-RPC pipe, no streaming IPC.  The CLI initializes logging
and config (the same setup ``main.bootstrap`` performs), then invokes the
workflow engine, validator, tool registry and environment registry directly.

The ``run`` subcommand resolves its target as a workflow JSON file or a
saved template name, parses ``--input key=value`` pairs (with basic type
coercion), executes the workflow through the engine while streaming node
events to the console, and prints the final result as JSON (``--json``) or
a human-readable summary.

Usage (from the ``cli/`` directory):

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

# Make the cli/ directory importable regardless of the working directory.
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

    rows: List[List[str]] = []
    tm = ToolManager.instance()
    for name, tool in tm.get_all_tools().items():
        if tm._registry.get_kind(name) == "shipped-native":
            rows.append([name, "builtin", "yes", ""])
        else:
            tool_type = getattr(tool, "type", None) or type(tool).__name__
            rows.append(
                [
                    name,
                    tool_type,
                    "yes" if getattr(tool, "is_valid", False) else "no",
                    getattr(tool, "version", "") or "",
                ]
            )

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
    env_registry.discover()
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
                tool = DescriptorTool(desc, env_registry, source_dir=tool_dir)
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


def cmd_tool(
    name: str,
    operation: Optional[str],
    raw_inputs: Optional[List[str]],
    json_output: bool,
    tool_dirs: Optional[List[str]] = None,
) -> int:
    """Invoke a single tool/operation headlessly and print the result.

    Resolves *name* as a builtin tool or a descriptor tool (loaded via
    ``--tool-dir``), parses ``--input key=value`` pairs, executes the
    tool or operation, and prints the result as JSON (``--json``) or a
    human-readable summary.  Returns 0 on success, non-zero on failure.
    """
    from app.tools.builtin.base import BuiltinTool, ToolContext

    inputs = _parse_key_values(raw_inputs or [])

    # ── 1. Resolve the tool ──────────────────────────────────────────
    tool: Any = None
    registry = (
        _augment_registry_with_tool_dirs(tool_dirs)
        if tool_dirs
        else None
    )
    if registry is not None:
        tool = registry.get_tool(name)
    if tool is None:
        from app.tools.tool_manager import ToolManager
        tool = ToolManager.instance().get_tool(name)

    if tool is None:
        print(f"error: unknown tool {name!r}", file=sys.stderr)
        return 1

    # ── 2. Execute ───────────────────────────────────────────────────
    if isinstance(tool, BuiltinTool):
        tool_context = ToolContext(work_dir=os.getcwd())
        try:
            result = tool.execute(inputs, tool_context)
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if isinstance(result, dict) and result.get("error"):
            print(f"error: {result['error']}", file=sys.stderr)
            return 1
    elif callable(getattr(tool, "execute", None)):
        descriptor = getattr(tool, "_descriptor", None)

        if operation:
            # ── Operation execution path ─────────────────────────────
            if descriptor is None:
                print(
                    f"error: tool {name!r} does not support operations",
                    file=sys.stderr,
                )
                return 1

            op = _find_operation(descriptor, operation)
            if op is None:
                available = [o.name for o in (descriptor.operations or [])]
                hint = ""
                if available:
                    hint = f" (available: {', '.join(available)})"
                print(
                    f"error: unknown operation {operation!r} "
                    f"for tool {name!r}{hint}",
                    file=sys.stderr,
                )
                return 1

            # Validate inputs against operation ports
            if op.inputs:
                from app.protocol import PortSet
                op_port_set = PortSet(list(op.inputs), list(op.outputs))
                validation_errors = op_port_set.validate_inputs(inputs)
                if validation_errors:
                    for err in validation_errors:
                        print(f"error: {err}", file=sys.stderr)
                    return 1

            tool_context = ToolContext(work_dir=os.getcwd())
            try:
                result = tool.execute(
                    {**inputs, "operation": operation}, tool_context
                )
            except Exception as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1

            if not isinstance(result, dict):
                print(
                    f"error: tool {name!r} returned non-dict result: "
                    f"{result!r}",
                    file=sys.stderr,
                )
                return 1

            success = result.get("success", True)
            returncode = result.get("returncode", 0)
            if success is False or returncode != 0:
                detail = (
                    result.get("stderr") or result.get("stdout") or ""
                ).strip()
                message = f"tool {name!r} failed (exit {returncode})"
                if detail:
                    message += f": {detail}"
                print(f"error: {message}", file=sys.stderr)
                return 1
        else:
            # ── No operation specified ───────────────────────────────
            if descriptor and descriptor.operations:
                available = [o.name for o in descriptor.operations]
                print(
                    f"error: tool {name!r} requires an operation; "
                    f"available: {', '.join(available)}. "
                    f"Usage: cli.py tool {name} <operation> --input ...",
                    file=sys.stderr,
                )
                return 1
            # Descriptor without operations / code-based tool:
            # instruct the user to use `run` with a workflow.
            print(
                f"error: tool {name!r} has no operations; "
                f"use `cli.py run <workflow>` to execute it",
                file=sys.stderr,
            )
            return 1
    else:
        print(
            f"error: tool {name!r} is neither a builtin nor an "
            f"executable descriptor tool",
            file=sys.stderr,
        )
        return 1

    # ── 3. Print result ──────────────────────────────────────────────
    if json_output:
        print(
            json.dumps(result, indent=2, default=str, ensure_ascii=False)
        )
    else:
        _print_result_summary(name, result)
    return 0


def _find_operation(descriptor: Any, operation_name: str) -> Any:
    """Look up *operation_name* in *descriptor.operations*."""
    if descriptor is None:
        return None
    for candidate in getattr(descriptor, "operations", []) or []:
        if candidate.name == operation_name:
            return candidate
    return None


def _print_result_summary(tool_name: str, result: dict) -> None:
    """Print a human-readable summary of *result* for *tool_name*."""
    print(f"tool: {tool_name}")
    for key, value in sorted(result.items()):
        val_str = json.dumps(value, default=str, ensure_ascii=False)
        if len(val_str) > 120:
            val_str = val_str[:117] + "..."
        print(f"  {key}: {val_str}")


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
    "workflow_cancelled": "\033[33m",  # yellow
}
_RESET = "\033[0m"


def _coerce_input_value(value: str) -> Any:
    """Coerce a raw ``--input`` value to a typed Python value.

    ``true``/``false`` (case-insensitive) become bools, integer and float
    literals become numbers, a value starting with ``[``/``{`` is parsed as
    JSON (arrays/objects for structured inputs like a mapping table), and
    everything else stays a string.
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
    if value[:1] in ("[", "{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
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
        from app.workflow.streaming import render_event_line

        event_type = event.get("type") or "event"
        line = render_event_line(event)
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
    from app.utils.task_log_writer import cleanup_task_log

    definition = _resolve_definition(target)
    if definition is None:
        return 1

    inputs = _parse_key_values(raw_inputs or [])
    use_color = (not json_output) and sys.stdout.isatty()
    stream = sys.stderr if json_output else sys.stdout
    raw_stream_handler = _make_console_stream_handler(use_color, stream)
    workflow_stream = WorkflowStreamHandler(
        workflow_id=task_id or "cli", callback=raw_stream_handler,
        task_log_id=task_id,
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
    finally:
        if task_id:
            cleanup_task_log(task_id)


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

    # tool
    tool_parser = subparsers.add_parser("tool", help="Invoke a tool or operation headlessly")
    tool_parser.add_argument("name", help="Tool name (e.g. flow.log, apktool)")
    tool_parser.add_argument(
        "operation", nargs="?", default=None,
        help="Operation name (required for descriptor tools with operations)",
    )
    tool_parser.add_argument(
        "--input", action="append", default=None,
        help="Input as key=value (repeatable)",
    )
    tool_parser.add_argument(
        "--json", action="store_true", default=False,
        help="Machine-readable JSON output",
    )
    tool_parser.add_argument(
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
        "tool": lambda: cmd_tool(
            args.name, args.operation, args.input, args.json, args.tool_dir
        ),
    }

    try:
        return handlers[args.command]()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
