#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Headless CLI entry point for the Blank Tool workflow system.

Provides five subcommands (``run``, ``list-tools``, ``list-envs``,
``validate``, ``list-templates``) that operate independently of the Electron
app — no stdin JSON-RPC pipe, no streaming IPC.  The CLI initializes logging
and config (the same setup ``main.bootstrap`` performs), then invokes the
workflow engine, validator, tool registry and environment registry directly.

The ``run`` subcommand is currently a stub (full implementation is a later
todo); it parses ``--input key=value`` pairs and reports what it *would* run.

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
from pathlib import Path
from typing import Dict, List, Optional

# Make the backend/ directory importable regardless of the working directory.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# ------------------------------------------------------------------
# Bootstrap (inlined from main.bootstrap)
# ------------------------------------------------------------------
#
# ``from main import bootstrap`` was tried first and FAILS: ``main`` imports
# ``app.api_handler``, whose ``from app.protocol import BackendResponse``
# breaks because the todo-1..3 ``app/protocol/`` package shadows the legacy
# ``app/protocol.py`` module (todo-8 learning, not fixed — out of scope).
# The bootstrap logic is therefore inlined here.  It does NOT read stdin
# (that only happens in ``main.main``'s JSON-RPC loop), so it is safe to run
# headless.  The legacy-download orphan warning from ``main.bootstrap`` is
# Electron-app UX and deliberately omitted.


def bootstrap() -> None:
    """Initialize dotenv, server config and logging for the CLI."""
    from app.utils.env import (
        get_env,
        load_dotenv,
        load_server_config,
        resolve_path,
    )
    from app.utils.logger import Logger

    dotenv_keys = load_dotenv()
    load_server_config(override_keys=dotenv_keys)

    log_dir = get_env("BT_LOG_DIR")
    if not log_dir:
        # Dev fallback: backend/logs/
        log_dir = str(Path(os.path.dirname(os.path.abspath(__file__))) / "logs")
    else:
        log_dir = resolve_path(log_dir)

    log_level = get_env("BT_LOG_LEVEL", "DEBUG")
    Logger.initialize(log_dir=log_dir, log_level=log_level)


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


def cmd_validate(path: str) -> int:
    """Validate a workflow definition file against the tool registry."""
    from app.tools.tool_manager import ToolManager
    from app.workflow.definition import WorkflowDefinition
    from app.workflow.validation import validate_workflow

    try:
        definition = WorkflowDefinition.from_json_file(path)
    except ValueError as exc:
        print(f"invalid workflow: {exc}", file=sys.stderr)
        return 1

    errors = validate_workflow(definition, ToolManager.instance())
    if not errors:
        print("valid")
        return 0

    for error in errors:
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


def cmd_run(
    target: str,
    raw_inputs: Optional[List[str]],
    task_id: Optional[str],
    json_output: bool,
) -> int:
    """Stub for the ``run`` subcommand (full implementation is a later todo).

    Parses ``--input key=value`` pairs and reports what the workflow run
    *would* do.
    """
    inputs = _parse_key_values(raw_inputs or [])
    info = {"target": target, "inputs": inputs, "task_id": task_id}
    if json_output:
        print(json.dumps({"would_run": info}, indent=2, ensure_ascii=False))
    else:
        print(f"would run: {target} with inputs {inputs}")
    return 0


def _parse_key_values(pairs: List[str]) -> Dict[str, str]:
    """Build a dict from ``key=value`` strings (split on the first ``=``).

    Values are kept as strings for now (type coercion is a later todo).
    Malformed entries are skipped with a warning.
    """
    result: Dict[str, str] = {}
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if not separator:
            print(
                f"warning: ignoring input {pair!r} (expected key=value)",
                file=sys.stderr,
            )
            continue
        result[key.strip()] = value.strip()
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

    # list-tools
    subparsers.add_parser("list-tools", help="List available tools")

    # list-envs
    subparsers.add_parser("list-envs", help="List resolved environments")

    # validate
    validate_parser = subparsers.add_parser("validate", help="Validate a workflow definition")
    validate_parser.add_argument("path", help="Path to workflow JSON file")

    # list-templates
    subparsers.add_parser("list-templates", help="List saved workflow templates")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Bootstrap, parse arguments and dispatch to a subcommand handler."""
    bootstrap()
    parser = _build_parser()
    args = parser.parse_args(argv)

    handlers = {
        "run": lambda: cmd_run(args.target, args.input, args.task_id, args.json),
        "list-tools": cmd_list_tools,
        "list-envs": cmd_list_envs,
        "validate": lambda: cmd_validate(args.path),
        "list-templates": cmd_list_templates,
    }

    try:
        return handlers[args.command]()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
