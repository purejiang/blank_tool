#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Linear workflow executor (MVP).

Walks a :class:`WorkflowDefinition`'s nodes in linear chain order (following
``node.next`` from the entry node): resolve each node's params via the
:class:`ExpressionEngine`, validate them against the tool's ports, execute
the tool, and record per-node results.  ``on_failure`` is ``"fail"`` (stop),
``"skip"`` (continue past the node), or ``"retry:N"`` (re-execute up to ``N``
times before giving up).

Tool dispatch:
    Tools resolve by name exclusively from the injected ``ToolManager``
    (whose shared registry holds the builtin primitives as ``shipped-native``
    plugin tools, plus descriptor/code tools).  Builtin tools run under the
    dict + :class:`ToolContext` contract.  Descriptor/code tools (``apktool``,
    ``bundletool``, ...) run under the command-list contract: the workflow
    template declares their arguments as ``params: {"args": [...]}``, and
    after expression resolution ``args`` is extracted and passed as the
    command list to ``tool.execute(command, context)``; the returned
    ``{success, returncode, stdout, stderr}`` dict is normalized into the
    node output shape with a non-zero exit surfaced as a node error.

Unsupported in linear mode:
    Nodes with a ``condition`` field are NOT executed (raise
    :class:`NotImplementedError`; stored for future DAG mode).  No parallel
    execution, no state persistence.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from app.common.exceptions import ToolException
from app.protocol import BaseType, PortSet
from app.tools.builtin.base import BuiltinTool, ToolContext
from app.tools.builtin.exec_tools import ShellExec
from app.tools.builtin.file_tools import FileRead, FileWrite
from app.tools.builtin.flow_tools import FlowAssert, FlowForeach, FlowLog
from app.tools.builtin.text_tools import TextGrep
from app.tools.builtin.workflow_tools import WorkflowRun
from app.tools.tool_manager import ToolManager
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.expression import ExpressionEngine, ExpressionError, WorkflowContext
from app.workflow.streaming import WorkflowStreamHandler, is_cancelled

logger = logging.getLogger(__name__)

# Shared, stateless expression engine (safe across runs — see expression.py).
_EXPRESSION_ENGINE = ExpressionEngine()

# Builtin atomic tools by name (DEPRECATED backward-compat shim).  These are
# now registered as shipped-native plugin tools in the shared registry (see
# ``app.plugins.builtin.*``) and resolved via the injected registry —
# ``_lookup_tool`` no longer consults this dict.  It is retained ONLY for the
# pre-existing dirty ``cli/cli.py`` (its ``list-tools``/``tool`` commands still
# iterate it) and will be removed once ``cli.py`` is migrated to the registry.
_BUILTIN_TOOLS: Dict[str, BuiltinTool] = {
    "file.read": FileRead(),
    "file.write": FileWrite(),
    "text.grep": TextGrep(),
    "shell.exec": ShellExec(),
    "flow.assert": FlowAssert(),
    "flow.log": FlowLog(),
    "flow.foreach": FlowForeach(),
    "workflow.run": WorkflowRun(),
}


@dataclass
class ExecutionContext:
    """Execution environment for a single workflow run.

    Attributes:
        work_dir: working directory; relative tool paths resolve against it.
        task_id: optional task identifier, forwarded to tools for logging
            and cancellation.
        env: environment variables exposed to tools and ``$env.*`` expressions.
        stream_handler: optional callback receiving ``{"type": ..., ...}``
            dicts; forwarded to builtin tools for streaming output.
        workflow_stream: optional ``WorkflowStreamHandler`` for emitting
            node lifecycle events via T11 streaming.
        template_store: optional ``TemplateStore`` for resolving sub-workflow
            template names (used by ``workflow.run``).  Defaults to
            ``FileTemplateStore`` when not injected.
        engine: reference to the ``WorkflowEngine`` instance executing this
            workflow; set automatically at the top of ``execute()`` so nested
            ``workflow.run`` calls can pass it to child executions.
        nesting_depth: current depth in sub-workflow chains (0 for top-level).
        in_progress_templates: immutable set of template names currently on
            the execution call stack for cycle detection.
        current_node_id: id of the node currently being executed; set by
            the engine loop before each node runs.
    """

    work_dir: str
    task_id: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    stream_handler: Optional[Callable[[dict], None]] = None
    workflow_stream: Optional[WorkflowStreamHandler] = None
    template_store: Optional[Any] = None
    engine: Optional[Any] = None
    nesting_depth: int = 0
    in_progress_templates: frozenset = field(default_factory=frozenset)
    current_node_id: Optional[str] = None


@dataclass
class WorkflowResult:
    """Outcome of one workflow execution.

    Attributes:
        success: True when every executed node completed without a terminal
            failure (``on_failure``-skipped nodes still allow success).
        outputs: outputs of the final executed node.
        node_results: per-node results keyed by node id, each shaped
            ``{"outputs": {...}, "error": Optional[str], "duration_ms": int}``.
        error: overall error message on failure, else None.
    """

    success: bool
    outputs: Dict[str, Any]
    node_results: Dict[str, Dict[str, Any]]
    error: Optional[str] = None


class WorkflowEngine:
    """Executes linear workflows defined by :class:`WorkflowDefinition`.

    Stateless between runs — a single instance executes many definitions.
    """

    def __init__(self, registry: Optional[ToolManager] = None) -> None:
        """Initialize the engine.

        Args:
            registry: tool registry for descriptor/code tool lookup.
                Defaults to :meth:`ToolManager.instance()` when not provided.
        """
        self._registry = registry if registry is not None else ToolManager.instance()
        self._expr = _EXPRESSION_ENGINE

    def execute(
        self,
        definition: WorkflowDefinition,
        inputs: dict,
        context: ExecutionContext,
    ) -> WorkflowResult:
        """Execute a workflow definition.

        Walks the linear chain from the entry node.  For each node: resolve
        params against the accumulated :class:`WorkflowContext`, look up the
        tool, validate inputs against the tool's ports, execute it, record the
        outputs, then apply ``on_failure`` semantics on error.

        Args:
            definition: the workflow to run (a valid linear definition).
            inputs: workflow-level input values (``$inputs.<key>``).
            context: execution environment (work dir, env, streaming).

        Returns:
            A :class:`WorkflowResult` summarizing the run.

        Raises:
            NotImplementedError: if any node carries a ``condition`` field
                (no branching in linear mode), or if a node references a
                tool that is neither a builtin primitive nor a command-list
                tool (no usable execute contract).
        """
        # Ensure template_store and engine are available for nested
        # workflow.run calls.  Set once so callers don't need to wire them.
        if context.template_store is None:
            from app.template.store import FileTemplateStore

            context.template_store = FileTemplateStore()
        if context.engine is None:
            context.engine = self

        workflow_context = WorkflowContext(
            inputs=dict(inputs),
            nodes={},
            env=dict(context.env),
            workdir=context.work_dir,
        )
        node_results: Dict[str, Dict[str, Any]] = {}
        node_by_id: Dict[str, WorkflowNode] = {
            node.id: node for node in definition.nodes
        }

        current = self._find_entry(definition, node_by_id)
        final_outputs: Dict[str, Any] = {}

        while current is not None:
            if current.condition is not None:
                raise NotImplementedError(
                    f"conditional branches not yet supported: node "
                    f"{current.id!r} declares a 'condition' field"
                )

            # Between-node cancellation check
            if is_cancelled(context.task_id or ""):
                if context.workflow_stream is not None:
                    context.workflow_stream.emit_workflow_cancelled()
                return WorkflowResult(
                    success=False,
                    outputs={},
                    node_results=node_results,
                    error="workflow cancelled",
                )

            # Real-time node lifecycle event: node_started before execution.
            context.current_node_id = current.id
            if context.workflow_stream is not None:
                context.workflow_stream.emit_node_started(
                    current.id, current.tool
                )

            start = time.perf_counter()
            outputs: Dict[str, Any] = {}
            error: Optional[str] = None

            try:
                resolved_params = self._expr.resolve_params(
                    current.params, workflow_context
                )
            except ExpressionError as exc:
                error = f"failed to resolve params: {exc}"
                resolved_params = dict(current.params)
            else:
                outputs, error = self._run_node(
                    current, resolved_params, context
                )

            duration_ms = int((time.perf_counter() - start) * 1000)

            # Terminal failure: on_failure "fail" (default) or an exhausted
            # "retry:N".  Record the node then stop the workflow.
            if error is not None and current.on_failure != "skip":
                node_results[current.id] = {
                    "outputs": {},
                    "error": error,
                    "duration_ms": duration_ms,
                }
                if context.workflow_stream is not None:
                    context.workflow_stream.emit_node_failed(
                        current.id, error
                    )
                    context.workflow_stream.emit_workflow_failed(
                        f"node {current.id!r} failed: {error}"
                    )
                return WorkflowResult(
                    success=False,
                    outputs={},
                    node_results=node_results,
                    error=f"node {current.id!r} failed: {error}",
                )

            if error is not None:  # on_failure == "skip"
                logger.warning(
                    "node %s failed (on_failure=skip, continuing): %s",
                    current.id,
                    error,
                )
                if context.workflow_stream is not None:
                    context.workflow_stream.emit_node_failed(
                        current.id, error
                    )
                outputs = {}

            node_results[current.id] = {
                "outputs": outputs,
                "error": error,
                "duration_ms": duration_ms,
            }
            workflow_context.nodes[current.id] = {
                "outputs": outputs,
                "params": resolved_params,
            }
            final_outputs = outputs

            # Emit node_completed when the node finished without a terminal
            # failure (skip failures count as "completed" for flow purposes).
            if error is None and context.workflow_stream is not None:
                context.workflow_stream.emit_node_completed(
                    current.id, duration_ms
                )

            current = node_by_id.get(current.next)

        # Emit workflow_completed after the final node finishes successfully.
        if context.workflow_stream is not None:
            context.workflow_stream.emit_workflow_completed(True)

        return WorkflowResult(
            success=True,
            outputs=final_outputs,
            node_results=node_results,
        )

    # ------------------------------------------------------------------
    # Node execution helpers
    # ------------------------------------------------------------------

    def _find_entry(
        self, definition: WorkflowDefinition, node_by_id: Dict[str, WorkflowNode]
    ) -> Optional[WorkflowNode]:
        """Return the entry node — the one no other node references via ``next``.

        ``WorkflowDefinition.__post_init__`` guarantees exactly one entry node
        (or zero for an empty workflow); this mirrors that rule for the walk.
        """
        referenced = {
            node.next for node in definition.nodes if node.next is not None
        }
        for node in definition.nodes:
            if node.id not in referenced:
                return node
        return None

    def _run_node(
        self,
        node: WorkflowNode,
        resolved_params: Dict[str, Any],
        context: ExecutionContext,
    ) -> tuple:
        """Execute one node with retry semantics.

        The retry budget comes from ``on_failure="retry:N"`` when present,
        otherwise from ``node.retry``.  Every retry re-attempts the full node
        (lookup, validation, execution).

        Returns:
            tuple: ``(outputs, error)`` — ``error`` is None on success and a
                message string on failure after all retries are exhausted.
        """
        if node.on_failure.startswith("retry:"):
            logger.warning(
                "on_failure=%r is deprecated; use the node.retry int "
                "field instead (node: %s)",
                node.on_failure,
                node.id,
            )
            max_retries = self._parse_retry(node.on_failure)
        else:
            max_retries = node.retry if node.retry > 0 else 0

        attempt = 0
        while True:
            outputs, error = self._attempt_node(node, resolved_params, context)
            if error is None:
                return outputs, None
            attempt += 1
            if attempt > max_retries:
                return outputs, error
            logger.warning(
                "node %s failed: %s; retrying (%d/%d)",
                node.id,
                error,
                attempt,
                max_retries,
            )

    def _attempt_node(
        self,
        node: WorkflowNode,
        resolved_params: Dict[str, Any],
        context: ExecutionContext,
    ) -> tuple:
        """One full attempt at a node: lookup -> validate -> execute.

        Returns:
            tuple: ``(outputs, error)``.
        """
        tool = self._lookup_tool(node.tool)
        if tool is None:
            return {}, f"tool not found: {node.tool}"

        validation_errors = self._validate_inputs(tool, resolved_params)
        if validation_errors:
            return {}, "; ".join(validation_errors)

        return self._execute_tool(tool, resolved_params, context)

    def _lookup_tool(self, tool_name: str) -> Optional[Any]:
        """Resolve a tool name to a tool object via the unified registry.

        All tools — builtin primitives (registered as ``shipped-native`` plugin
        tools), descriptor tools, and code tools — resolve exclusively through
        ``self._registry.get_tool``.  ``get_tool``'s priority (shipped-native
        > descriptor > code) makes a builtin win over a same-name descriptor.
        Returns None when the name is unknown.
        """
        if self._registry is not None:
            return self._registry.get_tool(tool_name)
        return None

    def _validate_inputs(self, tool: Any, resolved_params: Dict[str, Any]) -> list:
        """Validate resolved params against the tool's port set.

        Builtin tools expose ``validate``; other tools expose ``ports``.  The
        presence check (missing required inputs) is the only validation for
        the MVP — matching ``PortSet.validate_inputs``.
        """
        if isinstance(tool, BuiltinTool):
            return tool.validate(resolved_params)
        ports = getattr(tool, "ports", None)
        if ports is not None:
            return ports.validate_inputs(resolved_params)
        return []

    def _check_runtime_types(self, inputs: dict, tool: Any) -> list:
        """Check provided input values against the tool's declared base types.

        Warning-only (D7): a mismatch is reported to the caller for logging
        but never blocks execution — the engine historically accepted loosely
        typed values and existing workflows depend on that.  Subtype is
        advisory and deliberately ignored here.

        Tools without a ``ports`` attribute (e.g. code-tool stubs) skip the
        check entirely.

        Returns:
            list: warning strings for each type mismatch; empty when all good.
        """
        ports = getattr(tool, "ports", None)
        if ports is None:
            return []
        warnings = []
        for port in ports.inputs:
            if port.name not in inputs:
                continue
            if not self._matches_base_type(port.type.base, inputs[port.name]):
                warnings.append(
                    f"input {port.name!r} expected {port.type.base.value}, "
                    f"got {type(inputs[port.name]).__name__}: "
                    f"{inputs[port.name]!r}"
                )
        return warnings

    @staticmethod
    def _matches_base_type(base: BaseType, value: Any) -> bool:
        """Return True when ``value`` is acceptable for the base type.

        bool is a subclass of int in Python, so NUMBER must reject bools
        explicitly.  JSON accepts dict/list (native) or str (serialized).
        FILE / DIRECTORY / TEXT all map to str.
        """
        if base is BaseType.NUMBER:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if base is BaseType.BOOLEAN:
            return isinstance(value, bool)
        if base is BaseType.JSON:
            return isinstance(value, (dict, list, str))
        return isinstance(value, str)

    def _execute_tool(
        self,
        tool: Any,
        resolved_params: Dict[str, Any],
        context: ExecutionContext,
    ) -> tuple:
        """Run one tool via the unified ``tool.execute(inputs, context)`` contract.

        All tool types (builtin, descriptor, code) accept a params dict and
        :class:`ToolContext` as their single entry point.  The engine builds
        one ``ToolContext`` from the run's ``ExecutionContext`` and calls
        ``tool.execute(resolved_params, tool_context)`` uniformly.

        Tools that do not expose a callable ``execute`` raise
        :class:`NotImplementedError` (preserving the pre-unification contract).

        Error handling:
        - A ``ToolException`` raised by the tool is reported as a failure
          string.
        - Descriptor/code tools return ``{success, returncode, ...}`` shape;
          a non-zero exit or ``success: False`` is converted to an error
          string so ``on_failure`` semantics apply.
        - Builtin tools return output-port-keyed dicts; an ``"error"`` key
          is reported as failure.

        Returns:
            tuple: ``(outputs, error)`` — ``error`` is None on success.
        """
        if not callable(getattr(tool, "execute", None)):
            raise NotImplementedError(
                f"tool {getattr(tool, 'name', type(tool).__name__)!r} has no "
                f"execute(inputs, context) contract"
            )

        for warning in self._check_runtime_types(resolved_params, tool):
            logger.warning("runtime type mismatch: %s", warning)

        tool_context = ToolContext(
            work_dir=context.work_dir,
            task_id=context.task_id,
            env=dict(context.env),
            stream_handler=context.stream_handler,
            template_store=context.template_store,
            engine=context.engine or self,
            nesting_depth=context.nesting_depth,
            in_progress_templates=context.in_progress_templates,
            current_node_id=context.current_node_id,
            parent_workflow_id=(
                getattr(context.workflow_stream, "workflow_id", None)
                if context.workflow_stream is not None
                else None
            ),
        )
        try:
            result = tool.execute(resolved_params, tool_context)
        except ToolException as exc:
            return {}, exc.message
        except Exception as exc:
            return {}, f"tool execution failed: {exc}"

        if not isinstance(result, dict):
            tool_name = getattr(tool, "name", type(tool).__name__)
            return {}, (
                f"tool {tool_name!r} returned a non-dict result: {result!r}"
            )

        # Descriptor/code tool result shape: {success, returncode, ...}
        if "success" in result and "returncode" in result:
            success = result.get("success", True)
            returncode = result.get("returncode", 0)
            if success is False or returncode != 0:
                detail = (
                    result.get("stderr") or result.get("stdout") or ""
                ).strip()
                tool_name = getattr(tool, "name", type(tool).__name__)
                message = f"tool {tool_name!r} failed (exit {returncode})"
                if detail:
                    message += f": {detail}"
                return result, message
            return result, None

        # Builtin tool error convention: {"error": "..."}
        if result.get("error"):
            return {}, str(result["error"])

        return result, None

    def _parse_retry(self, on_failure: str) -> int:
        """Parse the ``N`` in an ``on_failure="retry:N"`` value.

        The definition model validates the ``retry:`` prefix but not the
        numeric count; a malformed count is treated as "no retry" with a
        warning.
        """
        try:
            return max(0, int(on_failure.split(":", 1)[1]))
        except (IndexError, ValueError):
            logger.warning(
                "malformed retry count in on_failure=%r; treating as no retry",
                on_failure,
            )
            return 0
