#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Builtin flow-control tools for the workflow engine.

Two atomic flow primitives (flow.assert, flow.log), each a ``BuiltinTool``
subclass declaring its port contract and a stdlib-only ``execute``
implementation:

- ``flow.assert`` is the validation gate: workflows assert intermediate state
  (e.g. "file exists after download") before proceeding.  A falsy ``condition``
  raises :class:`ToolException` so the workflow engine's failure handler can
  decide what to do (fail/skip/retry).  The exception is deliberately *not*
  caught here — the engine owns failure routing.
- ``flow.log`` writes a message through the standard :mod:`logging` framework
  (child loggers inherit the handlers configured by the ``main.py`` bootstrap)
  and, when a task context is present, also appends a line to the per-task log.

No conditional branching is implemented here — the ``condition`` field of the
workflow schema is reserved for a future feature, not consumed by these tools.
"""

import json
import logging
import os

from app.common.exceptions import ToolException
from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.tools.builtin.base import BuiltinTool, ToolContext
from app.template.store import TemplateNotFoundError
from app.tools.builtin.workflow_tools import (
    MAX_NESTING_DEPTH,
    _make_namespaced_stream_handler,
)
from app.workflow.streaming import WorkflowStreamHandler
from app.utils.task_log_writer import append_task_log

logger = logging.getLogger(__name__)

_BOOLEAN = TypeAnnotation(BaseType.BOOLEAN)
_TEXT = TypeAnnotation(BaseType.TEXT)
_JSON = TypeAnnotation(BaseType.JSON)
_NUMBER = TypeAnnotation(BaseType.NUMBER)

#: Levels accepted by flow.log; anything else defaults to "info" (forgiving).
_VALID_LEVELS = frozenset({"debug", "info", "warning", "error", "critical"})

#: Default message used when a flow.assert failure carries no explicit one.
_DEFAULT_ASSERT_MESSAGE = "Assertion failed"


class FlowAssert(BuiltinTool):
    """Assert a condition is truthy; raise on failure.

    Acts as a validation gate between workflow steps.  When ``condition`` is
    falsy (``False``, ``None``, ``0``, ``""``, ``[]``, ...) a
    :class:`ToolException` is raised with the ``message`` so the workflow
    engine's ``on_failure`` handler can route the failure.  On success the
    tool returns ``{"passed": True}``.
    """

    name = "flow.assert"
    description = "Assert a condition is truthy; raises ToolException when falsy."

    ports = PortSet(
        inputs=[
            Port("condition", _BOOLEAN, required=True, description="Value to assert is truthy."),
            Port("message", _TEXT, required=False, description="Failure message (default 'Assertion failed')."),
        ],
        outputs=[
            Port("passed", _BOOLEAN, required=True, description="Always True when the assertion succeeds."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        condition = inputs.get("condition")
        if not condition:
            message = inputs.get("message") or _DEFAULT_ASSERT_MESSAGE
            raise ToolException(message)
        return {"passed": True}


class FlowLog(BuiltinTool):
    """Write a message to the application log and (optionally) the task log.

    The message is logged at the requested level via the standard
    :mod:`logging` framework.  When ``context.task_id`` is set, the same line
    is also appended to the per-task log through
    :func:`app.utils.task_log_writer.append_task_log`.  An unrecognized
    ``level`` falls back to ``"info"`` rather than raising.
    """

    name = "flow.log"
    description = "Write a message to the application log and the current task log."

    ports = PortSet(
        inputs=[
            Port("message", _TEXT, required=True, description="Message text to log."),
            Port("level", _TEXT, required=False, description="Log level (debug/info/warning/error/critical, default info)."),
        ],
        outputs=[
            Port("logged", _BOOLEAN, required=True, description="True when the message was logged."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        message = inputs["message"]
        level = inputs.get("level") or "info"
        if level not in _VALID_LEVELS:
            level = "info"
        level_num = getattr(logging, level.upper(), logging.INFO)
        logger.log(level_num, message)
        if context.task_id:
            append_task_log(context.task_id, f"[{level}] {message}")
        return {"logged": True}


class FlowForeach(BuiltinTool):
    """Execute a sub-workflow template once per item, collecting results.

    The loop primitive: ``items`` (a list) is iterated in order, and for each
    item the ``template`` is executed inline through the same engine, mirroring
    ``workflow.run`` (shared ``TemplateStore``, ``ExecutionContext`` inheritance,
    ``MAX_NESTING_DEPTH``/``in_progress_templates`` recursion guards, and
    per-iteration namespaced stream events).

    Child input construction:
        * ``inputs`` (dict) is merged as the base for every child run.
        * A dict item's keys are flattened into the child inputs (so
          ``$inputs.name`` / ``$inputs.md5`` resolve per entry), and the whole
          item is ALSO injected under ``item_key`` (``$inputs.<item_key>``).
        * A non-dict item is injected under ``item_key`` only.

    Per-item pass rule: an item FAILS when the child execution failed, OR when
    a successful child's outputs contain a falsy ``passed`` key.  A successful
    child WITHOUT a ``passed`` key counts as passed.  ``all_passed`` is
    ``failed_count == 0`` and feeds ``flow.assert`` for whole-run gating.
    """

    name = "flow.foreach"
    description = (
        "Execute a sub-workflow template once per list item, collecting "
        "per-item results; single-item failures are recorded and do not stop "
        "the loop."
    )

    ports = PortSet(
        inputs=[
            Port(
                "items",
                _JSON,
                required=True,
                description="List of items to iterate (dict items are flattened into child inputs).",
            ),
            Port(
                "template",
                _TEXT,
                required=True,
                description="Name of the sub-workflow template to run per item.",
            ),
            Port(
                "item_key",
                _TEXT,
                required=False,
                description="Key under which the whole item is injected (default 'item').",
            ),
            Port(
                "inputs",
                _JSON,
                required=False,
                description="Extra inputs merged into every child run (default {}).",
            ),
        ],
        outputs=[
            Port(
                "results",
                _JSON,
                required=True,
                description="Per-item results: [{'item', 'outputs', 'error'}].",
            ),
            Port("count", _NUMBER, required=True, description="Number of items iterated."),
            Port("passed_count", _NUMBER, required=True, description="Items that passed."),
            Port("failed_count", _NUMBER, required=True, description="Items that failed."),
            Port(
                "all_passed",
                _BOOLEAN,
                required=True,
                description="True when no item failed.",
            ),
            Port(
                "results_file",
                _TEXT,
                required=False,
                description="Path to a JSON file the loop wrote (results + summary), for subprocess consumers that cannot receive structured data via args_map.",
            ),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        items = inputs.get("items") or []

        # Normalize the mapping-table forms: a bare list passes through, a
        # ``{"entries": [...]}`` wrapper is unwrapped, and a single object is
        # wrapped into a one-item list (so ``$inputs.mapping`` may be any of
        # the three accepted shapes).
        if isinstance(items, dict):
            entries = items.get("entries")
            if isinstance(entries, list):
                items = entries
            else:
                items = [items]

        if isinstance(items, (str, bytes)):
            # Tolerate a JSON-encoded list passed as a string (e.g. an entry
            # point that stringified the mapping table); anything else is an
            # error.
            try:
                parsed = json.loads(items)
            except (ValueError, TypeError):
                raise ToolException(
                    "foreach 'items' must be a list, got a scalar"
                ) from None
            if isinstance(parsed, (dict, list)):
                items = parsed
            else:
                raise ToolException(
                    "foreach 'items' must be a list, got a scalar"
                )
            if isinstance(items, dict):
                entries = items.get("entries")
                items = entries if isinstance(entries, list) else [items]
        if not isinstance(items, list):
            raise ToolException(
                f"foreach 'items' must be a list, got {type(items).__name__}"
            )

        template_name = inputs.get("template")
        if not template_name:
            raise ToolException("foreach requires a 'template' name")
        item_key = inputs.get("item_key") or "item"
        extra = inputs.get("inputs") or {}
        if not isinstance(extra, dict):
            raise ToolException("foreach 'inputs' must be a dict")

        # ── recursion guards (mirror workflow.run) ────────────────────
        if template_name in context.in_progress_templates:
            raise ToolException(
                f"recursion detected: template {template_name!r} is "
                f"already executing (cycle in workflow composition)"
            )
        if context.nesting_depth >= MAX_NESTING_DEPTH:
            raise ToolException(
                f"maximum nesting depth ({MAX_NESTING_DEPTH}) exceeded — "
                f"sub-workflow chain is too deep"
            )

        template_store = context.template_store
        if template_store is None:
            raise ToolException(
                "template_store not available in execution context — "
                "cannot resolve sub-workflow template"
            )
        engine = context.engine
        if engine is None:
            raise ToolException(
                "engine not available in execution context — "
                "cannot execute sub-workflow inline"
            )

        try:
            child_definition = template_store.load(template_name)
        except TemplateNotFoundError:
            raise ToolException(
                f"template not found: {template_name!r}"
            ) from None

        from app.workflow.engine import ExecutionContext

        parent_wf_id = context.parent_workflow_id or "root"
        current_node_id = context.current_node_id or "unknown"

        results = []
        passed_count = 0
        failed_count = 0

        for index, item in enumerate(items):
            child_inputs = dict(extra)
            if isinstance(item, dict):
                child_inputs.update(item)
            child_inputs[item_key] = item

            namespace_prefix = f"{parent_wf_id}/{current_node_id}/{index}"
            namespaced_callback = _make_namespaced_stream_handler(
                context.stream_handler, namespace_prefix
            )
            child_stream = (
                WorkflowStreamHandler(
                    workflow_id=namespace_prefix,
                    callback=namespaced_callback,
                    task_log_id=context.task_id,
                )
                if context.stream_handler is not None or context.task_id
                else None
            )

            child_context = ExecutionContext(
                work_dir=context.work_dir,
                task_id=context.task_id,
                env=dict(context.env),
                stream_handler=context.stream_handler,
                workflow_stream=child_stream,
                template_store=template_store,
                engine=engine,
                nesting_depth=context.nesting_depth + 1,
                in_progress_templates=(
                    context.in_progress_templates | frozenset([template_name])
                ),
            )

            try:
                child_result = engine.execute(
                    child_definition, child_inputs, child_context
                )
            except Exception as exc:
                results.append({"item": item, "outputs": {}, "error": str(exc)})
                failed_count += 1
                continue

            child_outputs = (
                child_result.outputs
                if isinstance(child_result.outputs, dict)
                else {}
            )
            error = (
                None
                if child_result.success
                else (child_result.error or "unknown error")
            )

            passed = child_result.success
            if child_result.success and "passed" in child_outputs:
                passed = bool(child_outputs["passed"])

            if passed:
                passed_count += 1
            else:
                failed_count += 1

            results.append(
                {"item": item, "outputs": child_outputs, "error": error}
            )

        # ── Materialize results to a JSON file for subprocess consumers ─
        # Structured ``results`` cannot cross the subprocess boundary via
        # ``args_map`` (values are ``str()``-ified, not JSON-serialized), so
        # the loop also writes them to a JSON file and exposes its path.
        results_file = ""
        try:
            work_dir = context.work_dir or "."
            os.makedirs(work_dir, exist_ok=True)
            results_file = os.path.join(
                work_dir, f"foreach_{current_node_id}.json"
            )
            with open(results_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "count": len(items),
                        "passed_count": passed_count,
                        "failed_count": failed_count,
                        "all_passed": failed_count == 0,
                        "results": results,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as exc:
            logger.warning("foreach failed to write results_file: %s", exc)
            results_file = ""

        return {
            "results": results,
            "count": len(items),
            "passed_count": passed_count,
            "failed_count": failed_count,
            "all_passed": failed_count == 0,
            "results_file": results_file,
        }
