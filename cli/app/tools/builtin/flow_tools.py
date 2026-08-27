#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Builtin flow-control tools for the workflow engine.

Atomic flow primitives, each a ``BuiltinTool`` subclass declaring its port
contract and a stdlib-only ``execute`` implementation:

- ``flow.assert`` is the validation gate: workflows assert intermediate state
  (e.g. "file exists after download") before proceeding.  A falsy ``condition``
  raises :class:`ToolException` so the workflow engine's failure handler can
  decide what to do (fail/skip/retry).  The exception is deliberately *not*
  caught here — the engine owns failure routing.
- ``flow.log`` writes a message through the standard :mod:`logging` framework
  (child loggers inherit the handlers configured by the ``main.py`` bootstrap)
  and, when a task context is present, also appends a line to the per-task log.
- ``flow.foreach`` executes a sub-workflow template once per list item.
- ``flow.branch`` is the if/else primitive: a truthy ``condition`` runs
  ``true_template``, a falsy one runs ``false_template`` (optional; absent
  means no-op).  Branching is realized through sub-workflow composition (the
  shared :func:`app.tools.builtin.workflow_tools.run_child_template`
  helper), NOT by consuming the workflow schema's reserved ``condition``
  field — that field stays parked for a future DAG mode.
- ``flow.compare`` produces the booleans branches consume: ``{a, b, op}`` →
  ``{"result": bool}`` (numbers compare numerically, everything else as
  strings).
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
    run_child_template,
)
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

            try:
                child_result = run_child_template(
                    template_name,
                    child_inputs,
                    context,
                    namespace_prefix,
                    child_definition=child_definition,
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


class FlowBranch(BuiltinTool):
    """Conditionally execute one of two sub-workflow templates (if/else).

    A truthy ``condition`` runs ``true_template``; a falsy one runs
    ``false_template`` when given, otherwise the node is a successful no-op
    (``executed=False``) — which doubles as a "conditional skip".  The chosen
    template is executed inline through the shared
    :func:`~app.tools.builtin.workflow_tools.run_child_template` helper, so
    recursion guards (cycle + ``MAX_NESTING_DEPTH``) and namespaced nested
    events behave exactly like ``workflow.run`` / ``flow.foreach``.

    Branching is composition, not engine surgery: the workflow schema's
    reserved ``condition`` field stays untouched (it is parked for a future
    DAG mode), and the linear chain keeps a single ``next`` pointer — this
    node simply delegates to one of two sub-workflows at runtime.

    ``condition`` uses Python truthiness (same convention as
    ``flow.assert``); pair it with ``flow.compare`` or a boolean tool output
    (e.g. ``$nodes.check.outputs.passed``) to produce the value.
    """

    name = "flow.branch"
    description = (
        "Conditionally execute one of two sub-workflow templates: truthy "
        "condition runs true_template, falsy runs false_template (optional; "
        "absent means no-op)."
    )

    ports = PortSet(
        inputs=[
            Port(
                "condition",
                _BOOLEAN,
                required=True,
                description="Branch selector; truthy runs true_template, falsy runs false_template.",
            ),
            Port(
                "true_template",
                _TEXT,
                required=True,
                description="Sub-workflow template to run when condition is truthy.",
            ),
            Port(
                "false_template",
                _TEXT,
                required=False,
                description="Sub-workflow template to run when condition is falsy (omit for no-op).",
            ),
            Port(
                "inputs",
                _JSON,
                required=False,
                description="Inputs passed to the chosen child workflow as $inputs.* (default {}).",
            ),
        ],
        outputs=[
            Port(
                "executed",
                _BOOLEAN,
                required=True,
                description="True when a branch template actually ran.",
            ),
            Port(
                "template",
                _TEXT,
                required=True,
                description="Name of the template that ran (empty string when no-op).",
            ),
            Port(
                "outputs",
                _JSON,
                required=True,
                description="The chosen child workflow's outputs ({} when no-op).",
            ),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        condition = inputs.get("condition")
        true_template = inputs.get("true_template")
        false_template = inputs.get("false_template") or ""
        chosen = true_template if condition else false_template

        if not chosen:
            return {"executed": False, "template": "", "outputs": {}}

        parent_wf_id = context.parent_workflow_id or "root"
        current_node_id = context.current_node_id or "unknown"
        namespace_prefix = f"{parent_wf_id}/{current_node_id}"

        child_result = run_child_template(
            chosen, inputs.get("inputs") or {}, context, namespace_prefix
        )

        if not child_result.success:
            raise ToolException(
                f"branch template {chosen!r} failed: "
                f"{child_result.error or 'unknown error'}"
            )

        return {
            "executed": True,
            "template": chosen,
            "outputs": (
                child_result.outputs
                if isinstance(child_result.outputs, dict)
                else {}
            ),
        }


#: Operators accepted by flow.compare.
_COMPARE_OPS = (
    "eq", "ne", "lt", "le", "gt", "ge", "contains", "starts_with", "ends_with",
)


def _coerce_compare_pair(a, b):
    """Coerce (a, b) for comparison: numeric pair when BOTH are real numbers
    (bools excluded), otherwise a string pair (``str()`` of each side)."""
    numeric = (
        isinstance(a, (int, float))
        and not isinstance(a, bool)
        and isinstance(b, (int, float))
        and not isinstance(b, bool)
    )
    return (a, b) if numeric else (str(a), str(b))


class FlowCompare(BuiltinTool):
    """Compare two values and return a boolean — the branch-condition producer.

    ``op`` is one of ``eq`` / ``ne`` / ``lt`` / ``le`` / ``gt`` / ``ge`` /
    ``contains`` / ``starts_with`` / ``ends_with`` (default ``eq``).  When
    both operands are numbers the comparison is numeric; anything else
    compares as strings (so ``5`` vs ``"5"`` is ``eq`` — handy when a CLI
    ``--input`` coerced one side).  Ordering on mixed types is lexicographic.

    The expression engine deliberately has no comparison operators (its
    documented MVP boundary), so conditions for ``flow.branch`` /
    ``flow.assert`` are produced by atomic tools like this one instead.
    """

    name = "flow.compare"
    description = (
        "Compare two values with an operator (eq/ne/lt/le/gt/ge/contains/"
        "starts_with/ends_with) and return a boolean result."
    )

    ports = PortSet(
        inputs=[
            Port(
                "a",
                _JSON,
                required=True,
                description="Left operand (number or string).",
            ),
            Port(
                "b",
                _JSON,
                required=True,
                description="Right operand (number or string).",
            ),
            Port(
                "op",
                _TEXT,
                required=False,
                description=(
                    "Operator: eq (default) / ne / lt / le / gt / ge / "
                    "contains / starts_with / ends_with."
                ),
            ),
        ],
        outputs=[
            Port(
                "result",
                _BOOLEAN,
                required=True,
                description="Comparison outcome.",
            ),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        op = inputs.get("op") or "eq"
        if op not in _COMPARE_OPS:
            raise ToolException(
                f"unknown op {op!r}; must be one of {', '.join(_COMPARE_OPS)}"
            )
        a, b = _coerce_compare_pair(inputs.get("a"), inputs.get("b"))

        if op == "eq":
            result = a == b
        elif op == "ne":
            result = a != b
        elif op == "lt":
            result = a < b
        elif op == "le":
            result = a <= b
        elif op == "gt":
            result = a > b
        elif op == "ge":
            result = a >= b
        elif op == "contains":
            result = b in a
        elif op == "starts_with":
            result = a.startswith(b)
        else:  # ends_with
            result = a.endswith(b)

        return {"result": result}
