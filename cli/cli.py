#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Headless CLI entry point for the Blank Tool workflow system.

Provides nine subcommands (``run``, ``list-tools``, ``list-envs``,
``validate``, ``tool``, ``list-templates``, ``import-pack``,
``import-templates``, ``history``) that operate independently of the Electron
app — no stdin JSON-RPC pipe, no streaming IPC.  The CLI initializes logging
and config (the same setup ``main.bootstrap`` performs), then invokes the
workflow engine, validator, tool registry and environment registry directly.

The ``run`` subcommand resolves its target as a workflow JSON file or a
saved template name, parses ``--input key=value`` pairs (with basic type
coercion), executes the workflow through the engine while streaming node
events to the console, and prints the final result as JSON (``--json``) or
a human-readable summary.

Cancellation and interruption:
    Every ``run``/``tool`` invocation registers itself with
    :class:`~app.common.task_manager.TaskManager`, so the engine's
    cancellation checkpoints and the subprocess holder are live.  Ctrl+C
    (SIGINT) requests cancellation through a per-run ``threading.Event`` —
    the signal handler takes no locks, writes nothing but one line to stderr,
    and the run finishes as ``cancelled``.  A second Ctrl+C forces exit.
    ``--timeout SECONDS`` requests the same cancellation on a timer.

Exit codes (``run``): 0 success, 1 failure, 2 cancelled (note: argparse uses
2 for a usage error too), 124 timed out, 130 forced exit on a second
interrupt.

Usage (from the ``cli/`` directory):

    python cli.py --help
    python cli.py list-tools
    python cli.py list-envs
    python cli.py validate <workflow.json>
    python cli.py list-templates
    python cli.py run <workflow.json|template-name> --input key=value
    python cli.py run <workflow.json> --timeout 300 --run-id <32-hex>
    python cli.py import-pack examples/tools/android
    python cli.py import-templates examples/workflows/android
    python cli.py history [--limit 20]
    python cli.py history <run_id>
"""

import argparse
import contextlib
import json
import os
import re
import signal
import sys
import threading
import time
import uuid
from dataclasses import replace
from datetime import datetime
from typing import Any, Dict, List, Optional

# Make the cli/ directory importable regardless of the working directory.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Shared bootstrap (dotenv + server config + logging); import it from main
# rather than duplicating it here.
from main import bootstrap
from app.tools.result_normalizer import normalize_result


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
        if tm.get_kind(name) == "shipped-native":
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
    *,
    run_id: Optional[str] = None,
) -> int:
    """Invoke a single tool/operation headlessly and print the result.

    Registers a run identity first, so the tool's subprocess is cancellable
    (Ctrl+C kills it) exactly like a workflow node; then delegates to
    :func:`_cmd_tool_impl`.

    Returns 0 on success, non-zero on failure, 2 when cancelled.
    """
    run_id = run_id or uuid.uuid4().hex
    with _run_scope(run_id, None):
        return _cmd_tool_impl(
            name, operation, raw_inputs, json_output, tool_dirs, run_id
        )


def _cmd_tool_impl(
    name: str,
    operation: Optional[str],
    raw_inputs: Optional[List[str]],
    json_output: bool,
    tool_dirs: Optional[List[str]],
    run_id: str,
) -> int:
    """Execute one tool under an already-registered run identity."""
    from app.common.exceptions import WorkflowCancelled
    from app.common.task_manager import TaskManager
    from app.tools.builtin.base import BuiltinTool, ToolContext

    inputs = _parse_key_values(raw_inputs or [])

    def _tool_context() -> ToolContext:
        """Context carrying the run's holder + cancellation source."""
        return ToolContext(
            work_dir=os.getcwd(),
            run_id=run_id,
            process_holder={},
            cancel_check=lambda: TaskManager().is_cancelled(run_id),
        )

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
        tool_context = _tool_context()
        try:
            result = tool.execute(inputs, tool_context)
        except WorkflowCancelled:
            print("cancelled", file=sys.stderr)
            return 2
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

            tool_context = _tool_context()
            try:
                result = tool.execute(
                    {**inputs, "operation": operation}, tool_context
                )
            except WorkflowCancelled:
                print("cancelled", file=sys.stderr)
                return 2
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

            ok, message = normalize_result(result, name)
            if not ok:
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


def cmd_import_pack(path: str) -> int:
    """Import every tool descriptor in a directory (domain pack).

    Delegates to :meth:`ToolRegistry.import_descriptor_dir` (two-phase:
    pre-validate all, write all), prints a per-tool summary, and returns
    0 when every descriptor imported cleanly, 1 otherwise.
    """
    from app.tools.tool_manager import ToolManager

    registry = ToolManager.instance().get_registry()
    report = registry.import_descriptor_dir(path)

    if "error" in report:
        print(f"error: {report['error']}", file=sys.stderr)
        return 1

    rows = []
    for entry in report["results"]:
        note = entry.get("reason") or "; ".join(entry.get("warnings") or [])
        rows.append([entry["name"], entry["status"], note])
    _print_table(["name", "status", "note"], rows)
    print(
        f"imported: {report['imported']}, updated: {report['updated']}, "
        f"failed: {report['failed']}"
    )
    return 0 if report["ok"] else 1


def cmd_import_templates(path: str) -> int:
    """Import workflow JSON file(s) into the template store.

    Accepts a single workflow file or a directory of workflow JSON files
    (e.g. ``examples/workflows/android``).  Returns 0 when every file
    imported cleanly, 1 otherwise.
    """
    from app.handlers.template_handler import import_templates_from_path

    try:
        report = import_templates_from_path(path)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    rows = []
    for entry in report["results"]:
        note = entry.get("reason") or ""
        if entry.get("renamed_from"):
            note = f"name from definition; file stem {entry['renamed_from']!r}"
        rows.append(
            [entry.get("name") or entry["file"], entry["status"], note]
        )
    _print_table(["name", "status", "note"], rows)
    print(f"imported: {report['imported']}, failed: {report['failed']}")
    return 0 if report["ok"] else 1


def cmd_history(run_id: Optional[str], limit: int) -> int:
    """Show run history: a summary table, or one full record as JSON.

    ``history`` lists the newest runs (``--limit``, default 50);
    ``history <run_id>`` prints the full record as JSON.
    """
    from app.history import store as history_store

    if run_id:
        try:
            record = history_store.get_run(run_id)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if record is None:
            print(f"error: run not found: {run_id}", file=sys.stderr)
            return 1
        print(json.dumps(record, indent=2, ensure_ascii=False, default=str))
        return 0

    runs = history_store.list_runs(limit=limit)
    if not runs:
        print("no run history")
        return 0
    rows = [
        [
            (r.get("run_id") or "")[:8],
            r.get("workflow_name") or "",
            "yes" if r.get("success") else "no",
            str(r.get("duration_ms") or ""),
            r.get("started_at") or "",
        ]
        for r in runs
    ]
    _print_table(["run_id", "workflow", "success", "ms", "started_at"], rows)
    return 0


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
    "workflow_failed": "\033[31m",  # red
    "workflow_cancelled": "\033[33m",  # yellow
}
_RESET = "\033[0m"

#: node_completed carries the terminal status; a failed/cancelled node is not
#: a green line.
_STATUS_COLORS = {
    "failed": "\033[31m",  # red
    "cancelled": "\033[33m",  # yellow
    "skipped": "\033[33m",  # yellow
}


# ------------------------------------------------------------------
# Run identity, cancellation sources and interruption
# ------------------------------------------------------------------

#: History ids are uuid4 hex (see ``app.history.store``); a ``--run-id`` must
#: match so ``history <run_id>`` can resolve the record the run wrote.
_HISTORY_ID_RE = re.compile(r"^[0-9a-f]{32}$")

#: The run currently executing in this process — the only slot a signal
#: handler touches.  Keys: token, event, timed_out, run_id, task_log_id,
#: interrupts.
_ACTIVE_RUN: Dict[str, Any] = {}


def _write_stderr(text: str) -> None:
    """Write *text* to fd 2 without raising (safe inside a signal handler)."""
    try:
        os.write(2, text.encode("utf-8", errors="replace"))
    except Exception:
        pass


def _set_active_run(token, event, run_id, task_log_id) -> None:
    """Publish *event* as this process's cancellation source."""
    _ACTIVE_RUN.clear()
    _ACTIVE_RUN.update(
        {
            "token": token,
            "event": event,
            "timed_out": False,
            "run_id": run_id,
            "task_log_id": task_log_id,
            "interrupts": 0,
        }
    )


def _clear_active_run(token) -> None:
    """Retire the active-run slot when *token* is still the current one."""
    if _ACTIVE_RUN.get("token") is token:
        _ACTIVE_RUN.clear()


def _on_interrupt(signum, frame) -> None:
    """Handle SIGINT/SIGTERM: request cancellation, force exit on the second.

    Deliberately tiny and lock-free: taking ``TaskManager``'s lock or
    flushing the task log here can deadlock against the interrupted thread
    (which may already hold those locks).  Only ``Event.set()`` and
    ``os.write`` are used, so a forced exit may lose log lines still
    buffered in memory.
    """
    event = _ACTIVE_RUN.get("event")
    if event is None:
        _write_stderr("\ninterrupted\n")
        os._exit(130)
        return  # os._exit does not return; kept for defensiveness/tests
    if _ACTIVE_RUN.get("interrupts"):
        _write_stderr("\nforced exit\n")
        os._exit(130)
        return
    _ACTIVE_RUN["interrupts"] = 1
    _write_stderr("\ninterrupt: cancelling run (interrupt again to force exit)\n")
    event.set()


def _install_signal_handlers() -> None:
    """Install :func:`_on_interrupt` for SIGINT/SIGTERM when possible.

    ``signal.signal`` only works on the main thread, and SIGTERM is not
    catchable on Windows (``os.kill`` terminates the process outright).
    """
    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _on_interrupt)
        except (ValueError, OSError, RuntimeError):
            pass


def _fire_timeout(token, event, seconds: float) -> None:
    """``--timeout`` watchdog: cancel the run unless it already finished."""
    if _ACTIVE_RUN.get("token") is not token:
        return  # a late fire after completion must be inert
    _ACTIVE_RUN["timed_out"] = True
    _write_stderr(f"\nrun timeout after {seconds:g}s: cancelling\n")
    event.set()


def _sweep_live_children() -> None:
    """Cancel (and tree-kill) every run still registered with TaskManager.

    Insurance for the paths that leave ``main`` normally; a forced
    ``os._exit`` cannot run it.
    """
    try:
        from app.common.task_manager import TaskManager

        manager = TaskManager()
        for run in manager.list_tasks():
            try:
                manager.cancel(run.get("run_id") or "")
            except Exception:
                continue
    except Exception:
        pass


@contextlib.contextmanager
def _run_scope(run_id: str, task_id: Optional[str], event=None):
    """Register *run_id* for cancellation and mark it as the active run.

    Yields the per-run :class:`threading.Event` that the signal handler and
    the ``--timeout`` watchdog set.  ``honor_stop_event=True`` is what lets
    the engine observe that event through ``TaskManager.is_cancelled`` — the
    CLI's own cancellation path — without the handler ever taking a lock.
    """
    from app.common.task_manager import TaskManager

    manager = TaskManager()
    cancel_event = event if event is not None else threading.Event()
    token = object()
    manager.register(run_id, task_id or "", cancel_event, honor_stop_event=True)
    _set_active_run(token, cancel_event, run_id, task_id)
    try:
        yield cancel_event, token
    finally:
        manager.unregister(run_id)
        _clear_active_run(token)


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
    status=ok (123 ms)``.  When *use_color* is True the event tag is
    ANSI-colored (failed/skipped/cancelled nodes are not green).
    *stream* is the output target: stdout normally, stderr for ``--json`` so
    stdout stays a pure JSON document.
    """

    def _render(event: Dict[str, Any]) -> str:
        from app.workflow.streaming import render_event_line

        event_type = event.get("type") or "event"
        line = render_event_line(event)
        color = None
        if use_color:
            if event_type == "node_completed":
                color = _STATUS_COLORS.get(event.get("status"))
            if color is None:
                color = _EVENT_COLORS.get(event_type)
        if color:
            line = f"{color}{line}{_RESET}"
        return line

    def _handle_event(event: Dict[str, Any]) -> None:
        print(_render(event), file=stream)

    return _handle_event


def _resolve_definition(target: str):
    """Load the workflow definition for *target* and resolve its own directory.

    A ``.json`` suffix or an existing file path loads via
    :meth:`WorkflowDefinition.from_json_file`; anything else is treated as a
    template name resolved through :class:`FileTemplateStore`.

    Returns:
        ``(definition, work_dir)`` where *work_dir* is the workflow's own
        directory — the file's folder, or the template store's folder — or
        ``(None, None)`` after printing an error to stderr.
    """
    if target.endswith(".json") or os.path.isfile(target):
        try:
            from app.workflow.definition import WorkflowDefinition

            definition = WorkflowDefinition.from_json_file(target)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return None, None
        return definition, os.path.dirname(os.path.abspath(target))

    try:
        from app.template.store import FileTemplateStore, TemplateNotFoundError

        store = FileTemplateStore()
        return store.load(target), store.templates_dir
    except (TemplateNotFoundError, ValueError) as exc:
        print(f"error: template {target!r}: {exc}", file=sys.stderr)
        return None, None


def cmd_run(
    target: str,
    raw_inputs: Optional[List[str]],
    task_id: Optional[str],
    json_output: bool,
    tool_dirs: Optional[List[str]] = None,
    *,
    run_id: Optional[str] = None,
    timeout: Optional[float] = None,
    interrupt_event: Optional[threading.Event] = None,
) -> int:
    """Run a workflow from a JSON file or template name.

    Resolves *target*, parses and coerces ``--input key=value`` pairs,
    executes the workflow through :class:`WorkflowEngine`, streams node
    events to the console, and prints the final result as JSON (``--json``)
    or a human-readable summary.

    The run's working directory is the workflow's OWN directory (the file's
    folder, or the template store's folder), so relative paths and produced
    artifacts stay next to the workflow instead of landing in the process CWD.

    Args:
        run_id: the run identity (32-char hex).  It names ``$rundir``, is the
            key the run registers for cancellation under, and — when it has
            the history id format — becomes the history record id.  Defaults
            to a fresh ``uuid4().hex``, so concurrent CLI runs never share a
            run directory.
        timeout: whole-run wall-clock budget in seconds; on expiry the run is
            cancelled and 124 is returned.  ``None``/``0`` means no limit.
        interrupt_event: the per-run cancellation event the signal handler
            sets.  Defaults to a fresh event (used by in-process callers and
            tests that pre-set it to request cancellation).

    Returns 0 on success, 1 on failure, 2 when the run was cancelled and 124
    when it hit *timeout*.
    """
    from app.workflow.engine import ExecutionContext, WorkflowEngine, WorkflowResult
    from app.workflow.runner import record_history
    from app.workflow.streaming import WorkflowStreamHandler
    from app.utils.task_log_writer import cleanup_task_log

    definition, work_dir = _resolve_definition(target)
    if definition is None:
        return 1

    inputs = _parse_key_values(raw_inputs or [])
    started_at = datetime.now().isoformat()
    start = time.perf_counter()
    use_color = (not json_output) and sys.stdout.isatty()
    stream = sys.stderr if json_output else sys.stdout
    raw_stream_handler = _make_console_stream_handler(use_color, stream)

    run_id = run_id or uuid.uuid4().hex
    registry = (
        _augment_registry_with_tool_dirs(tool_dirs)
        if tool_dirs
        else None
    )

    with _run_scope(run_id, task_id, interrupt_event) as (cancel_event, token):
        workflow_stream = WorkflowStreamHandler(
            workflow_id=definition.name,
            callback=raw_stream_handler,
            run_id=run_id,
            task_log_id=task_id,
        )
        context = ExecutionContext(
            work_dir=work_dir or os.getcwd(),
            task_id=task_id,
            run_id=run_id,
            stream_handler=raw_stream_handler,
            workflow_stream=workflow_stream,
        )

        timer = None
        if timeout and timeout > 0:
            timer = threading.Timer(
                float(timeout), _fire_timeout, args=(token, cancel_event, float(timeout))
            )
            timer.daemon = True
            timer.start()

        try:
            try:
                result = WorkflowEngine(registry=registry).execute(
                    definition, inputs, context
                )
            except KeyboardInterrupt:
                # Only reachable when the SIGINT handler could not be
                # installed; treat it exactly like a requested cancel.
                result = WorkflowResult(
                    success=False,
                    outputs={},
                    node_results={},
                    error="run interrupted",
                    cancelled=True,
                )
            except BaseException as exc:  # noqa: BLE001 - never lose the record
                result = WorkflowResult(
                    success=False,
                    outputs={},
                    node_results={},
                    error=f"internal error: {exc}",
                )
                if json_output:
                    print(f"error: {exc}", file=sys.stderr)

            # A timeout only counts when the engine actually observed the
            # cancellation: a timer that fires after the run already
            # finished must not turn a success into a timeout.
            timed_out = bool(
                _ACTIVE_RUN.get("timed_out")
                and _ACTIVE_RUN.get("token") is token
                and result.cancelled
            )
            if timed_out:
                result = replace(
                    result,
                    success=False,
                    cancelled=True,
                    error=f"run timed out after {timeout:g}s",
                )

            # Every terminal path is recorded — success, failure, cancel,
            # timeout and internal error alike (best-effort).
            record_history(
                definition, {"path": target}, task_id, inputs, result,
                started_at, start,
                run_id=run_id if _HISTORY_ID_RE.match(run_id) else None,
            )

            if json_output:
                print(
                    json.dumps(
                        {
                            "success": result.success,
                            "status": result.status,
                            "cancelled": result.cancelled,
                            "timeout": timed_out,
                            "run_id": run_id,
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
                print(f"run_id: {run_id}")
                print(f"status: {result.status}")
                if result.outputs:
                    print(
                        "outputs: "
                        + json.dumps(result.outputs, indent=2, default=str, ensure_ascii=False)
                    )
                if result.error:
                    print(f"error: {result.error}")

            if timed_out:
                return 124
            # A cancelled run is neither success (0) nor a plain failure (1).
            return 0 if result.success else (2 if result.cancelled else 1)
        finally:
            if timer is not None:
                timer.cancel()
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
    run_parser = subparsers.add_parser(
        "run",
        help="Run a workflow from file or template",
        description=(
            "Run a workflow and stream node events.\n"
            "Exit codes: 0 success, 1 failure, 2 cancelled, 124 timed out, "
            "130 forced exit on a second Ctrl+C (argparse itself also exits 2 "
            "on a usage error)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run_parser.add_argument("target", help="Path to workflow JSON file or template name")
    run_parser.add_argument("--input", action="append", help="Input as key=value (repeatable)")
    run_parser.add_argument("--task-id", help="Task ID for logging")
    run_parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    run_parser.add_argument(
        "--tool-dir", action="append", default=None,
        help="Directory of *.json tool descriptors to load (repeatable)",
    )
    run_parser.add_argument(
        "--run-id", default=None,
        help=(
            "32-char lowercase hex run id: names the run directory "
            "($rundir) and the history record (default: random)"
        ),
    )
    run_parser.add_argument(
        "--timeout", type=float, default=None, metavar="SECONDS",
        help="Cancel the whole run after SECONDS (0 or omitted = no limit)",
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
    tool_parser.add_argument(
        "--run-id", default=None,
        help=(
            "32-char lowercase hex run id for this invocation "
            "(default: random); the tool is cancellable under it"
        ),
    )

    # list-templates
    subparsers.add_parser("list-templates", help="List saved workflow templates")

    # import-pack
    pack_parser = subparsers.add_parser(
        "import-pack",
        help="Import every tool descriptor in a directory (domain pack)",
    )
    pack_parser.add_argument(
        "path", help="Directory of *.json tool descriptors to import",
    )

    # import-templates
    tpl_parser = subparsers.add_parser(
        "import-templates",
        help="Import workflow JSON file(s) into the template store",
    )
    tpl_parser.add_argument(
        "path", help="Workflow JSON file or directory of workflow JSON files",
    )

    # history
    history_parser = subparsers.add_parser(
        "history", help="Show run history (list, or one record by run_id)"
    )
    history_parser.add_argument(
        "run_id", nargs="?", default=None,
        help="Show the full record for this run id (omit to list runs)",
    )
    history_parser.add_argument(
        "--limit", type=int, default=50,
        help="Max runs to list (default 50; 0 = no limit)",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Bootstrap, parse arguments and dispatch to a subcommand handler."""
    bootstrap()
    _install_signal_handlers()
    parser = _build_parser()
    args = parser.parse_args(argv)

    run_id = getattr(args, "run_id", None)
    if run_id and not _HISTORY_ID_RE.match(run_id):
        print(
            f"error: --run-id must be 32 lowercase hex characters, got {run_id!r}",
            file=sys.stderr,
        )
        return 1

    handlers = {
        "run": lambda: cmd_run(
            args.target, args.input, args.task_id, args.json, args.tool_dir,
            run_id=run_id, timeout=args.timeout,
        ),
        "list-tools": cmd_list_tools,
        "list-envs": cmd_list_envs,
        "validate": lambda: cmd_validate(args.path, args.tool_dir),
        "list-templates": cmd_list_templates,
        "import-pack": lambda: cmd_import_pack(args.path),
        "import-templates": lambda: cmd_import_templates(args.path),
        "history": lambda: cmd_history(args.run_id, args.limit),
        "tool": lambda: cmd_tool(
            args.name, args.operation, args.input, args.json, args.tool_dir,
            run_id=run_id,
        ),
    }

    try:
        return handlers[args.command]()
    except KeyboardInterrupt:
        # Belt-and-braces: _on_interrupt normally turns Ctrl+C into a
        # cancelled run (exit 2).  A KeyboardInterrupt raised before the
        # handler was installed must not print a traceback.
        print("interrupted", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        _sweep_live_children()


if __name__ == "__main__":
    sys.exit(main())
