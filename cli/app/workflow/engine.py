#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Linear workflow executor.

Walks a :class:`WorkflowDefinition`'s nodes in linear chain order (following
``node.next`` from the entry node): resolve each node's params via the
:class:`ExpressionEngine`, validate them against the tool's ports, execute
the tool, and record per-node results.  ``on_failure`` is ``"fail"`` (stop)
or ``"skip"`` (continue past the node); ``node.retry`` re-executes a failing
node up to N extra times, backing off exponentially — before retry ``n`` the
engine waits ``min(2^(n-1), 30)`` seconds, slept in short cancellation-aware
slices.

Cancellation:
    A run is cancelled through :class:`~app.common.task_manager.TaskManager`
    (keyed by the run id the IPC layer registered).  The engine checks it
    before every node, before every retry, and while backing off; a cancelled
    run is reported as ``WorkflowResult(cancelled=True)`` — neither a success
    nor a failure — and never burns a retry.  Tools observe cancellation
    through ``ToolContext.cancel_check`` and the subprocess holder; a
    ``WorkflowCancelled`` raised by nested composition propagates here.

Failure classification:
    A tool failure consumes the retry budget.  A *non-retryable* failure —
    cancellation, an unknown tool, a missing required input, or a
    :class:`NonRetryableToolError` (e.g. ``flow.assert``) — does not: the next
    attempt would see exactly the same input and fail the same way.

Tool dispatch:
    Tools resolve by name exclusively from the injected ``ToolManager``.
    Every tool — builtin primitive, descriptor tool, or code tool — runs
    under the same ``tool.execute(resolved_params, tool_context)`` contract.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from app.common.exceptions import (
    NonRetryableToolError,
    ToolException,
    WorkflowCancelled,
)
from app.protocol import BaseType
from app.tools.builtin.base import BuiltinTool, ToolContext
from app.tools.result_normalizer import normalize_result
from app.tools.tool_manager import ToolManager
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.expression import ExpressionEngine, ExpressionError, WorkflowContext
from app.workflow.output_limit import shrink_outputs
from app.workflow.streaming import WorkflowStreamHandler, is_cancelled

logger = logging.getLogger(__name__)

# Shared, stateless expression engine (safe across runs — see expression.py).
_EXPRESSION_ENGINE = ExpressionEngine()

#: Node status values reported on ``node_completed``.
STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_CANCELLED = "cancelled"


def _join_path(prefix: str, node_id: str) -> str:
    """Return the run-root-relative path of *node_id* under *prefix*."""
    return f"{prefix}/{node_id}" if prefix else node_id


def _instrument_stream_handler(
    callback: Optional[Callable[[dict], None]],
    run_id: Optional[str],
    workflow_id: str,
    node_path: Optional[str],
) -> Optional[Callable[[dict], None]]:
    """Wrap a raw tool stream callback so nested output stays attributable.

    Tool-level streaming payloads are tool-specific dicts; the wrapper only
    *fills in* ``run_id`` / ``workflow_id`` / ``node_id`` when the payload is
    a dict and does not already carry them, so nested tool output can be
    traced back to the node that produced it.
    """
    if callback is None:
        return None

    def wrapper(event):
        if isinstance(event, dict):
            event = dict(event)
            event.setdefault("run_id", run_id)
            event.setdefault("workflow_id", workflow_id)
            if node_path is not None:
                event.setdefault("node_id", node_path)
        callback(event)

    return wrapper


@dataclass
class ExecutionContext:
    """Execution environment for a single workflow run.

    Attributes:
        work_dir: working directory; relative tool paths resolve against it.
        task_id: optional task identifier, forwarded to tools for logging.
        run_id: identifier of the TOP-LEVEL run; the cancellation key and the
            ``run_id`` stamped on every streamed event.  Inherited unchanged
            by nested executions.
        env: environment variables exposed to tools and ``$env.*`` expressions.
        stream_handler: optional callback receiving tool-level stream dicts;
            forwarded to builtin tools for streaming output.
        workflow_stream: optional ``WorkflowStreamHandler`` for emitting node
            lifecycle events.
        template_store: optional ``TemplateStore`` for resolving sub-workflow
            template names (used by ``workflow.run``).  Defaults to
            ``FileTemplateStore`` when not injected.
        engine: reference to the ``WorkflowEngine`` executing this workflow;
            set automatically at the top of ``execute()`` so nested
            ``workflow.run`` calls can pass it to child executions.
        nesting_depth: current depth in sub-workflow chains (0 for top-level).
        in_progress_templates: immutable set of template names currently on
            the execution call stack for cycle detection.
        node_path_prefix: path of the parent node from the run root; child
            node paths are prefixed with it (empty for a top-level run).
        current_node_path: run-root-relative path of the node being executed;
            set by the engine loop before each node runs.
        run_dir: per-run artifact directory (``<output_dir>/runs/<run_id>``),
            created once at the top of ``execute()`` and inherited unchanged by
            nested executions.  Exposed to params as ``$rundir``; engines never
            write run artifacts into ``work_dir``.
    """

    work_dir: str
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    run_dir: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    stream_handler: Optional[Callable[[dict], None]] = None
    workflow_stream: Optional[WorkflowStreamHandler] = None
    template_store: Optional[Any] = None
    engine: Optional[Any] = None
    nesting_depth: int = 0
    in_progress_templates: frozenset = field(default_factory=frozenset)
    node_path_prefix: str = ""
    current_node_path: Optional[str] = None

    def cancel_key(self) -> str:
        """Return the identity cancellation is queried by."""
        return self.run_id or self.task_id or ""

    def cancelled(self) -> bool:
        """Return True when this run has been cancelled."""
        return is_cancelled(self.cancel_key())


@dataclass
class WorkflowResult:
    """Outcome of one workflow execution.

    Attributes:
        success: True when every executed node completed without a terminal
            failure (``on_failure``-skipped nodes still allow success).
        outputs: outputs of the final executed node.
        node_results: per-node results keyed by node path, each shaped
            ``{"outputs": {...}, "error": Optional[str], "duration_ms": int,
            "status": str, "attempts": int}``.  Recorded here for the wire and
            for history, so large string values are truncated — the untruncated
            values stay available to ``$nodes.*`` expressions during the run.
        error: overall error message on failure, else None.
        cancelled: True when the run was cancelled; a cancelled run is neither
            a success nor a failure.
    """

    success: bool
    outputs: Dict[str, Any]
    node_results: Dict[str, Dict[str, Any]]
    error: Optional[str] = None
    cancelled: bool = False

    @property
    def status(self) -> str:
        """One of ``"succeeded"`` / ``"failed"`` / ``"cancelled"``."""
        if self.cancelled:
            return "cancelled"
        return "succeeded" if self.success else "failed"


@dataclass
class _NodeRun:
    """Outcome of one node's full retry sequence."""

    outputs: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    attempts: int = 1
    retryable: bool = True
    cancelled: bool = False


class WorkflowEngine:
    """Executes linear workflows defined by :class:`WorkflowDefinition`.

    Stateless between runs — a single instance executes many definitions.
    """

    def __init__(self, registry: Optional[ToolManager] = None) -> None:
        """Initialize the engine.

        Args:
            registry: tool registry for tool lookup.  Defaults to
                :meth:`ToolManager.instance` when not provided.
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
            NotImplementedError: if a node references a tool with no usable
                ``execute(inputs, context)`` contract.
        """
        # Ensure template_store and engine are available for nested
        # workflow.run calls.  A template store that cannot be prepared
        # (unwritable dir) only disables sub-workflow nodes — it must not
        # fail the whole run.
        if context.template_store is None:
            context.template_store = self._make_template_store()
        if context.engine is None:
            context.engine = self
        if context.run_dir is None:
            context.run_dir = self._prepare_run_dir(context)

        workflow_context = WorkflowContext(
            inputs=dict(inputs),
            nodes={},
            env=dict(context.env),
            workdir=context.work_dir,
            rundir=context.run_dir or "",
        )
        node_results: Dict[str, Dict[str, Any]] = {}
        node_by_id: Dict[str, WorkflowNode] = {
            node.id: node for node in definition.nodes
        }

        current = self._find_entry(definition, node_by_id)
        final_outputs: Dict[str, Any] = {}

        while current is not None:
            # Between-node cancellation check
            if context.cancelled():
                return self._cancel_result(node_results, context)

            node_path = _join_path(context.node_path_prefix, current.id)
            context.current_node_path = node_path

            if context.workflow_stream is not None:
                context.workflow_stream.emit_node_started(node_path, current.tool)

            start = time.perf_counter()
            try:
                resolved_params = self._expr.resolve_params(
                    current.params, workflow_context
                )
            except ExpressionError as exc:
                outcome = _NodeRun(
                    error=f"failed to resolve params: {exc}", retryable=False
                )
            else:
                outcome = self._run_node(current, resolved_params, context)

            duration_ms = int((time.perf_counter() - start) * 1000)

            if outcome.cancelled:
                node_results[node_path] = {
                    "outputs": {},
                    "error": None,
                    "duration_ms": duration_ms,
                    "status": STATUS_CANCELLED,
                    "attempts": outcome.attempts,
                }
                return self._cancel_result(node_results, context)

            # Terminal failure: on_failure "fail" (default) or an exhausted
            # retry budget.  Record the node then stop the workflow.
            if outcome.error is not None and current.on_failure != "skip":
                node_results[node_path] = {
                    "outputs": {},
                    "error": outcome.error,
                    "duration_ms": duration_ms,
                    "status": STATUS_FAILED,
                    "attempts": outcome.attempts,
                }
                if context.workflow_stream is not None:
                    context.workflow_stream.emit_node_completed(
                        node_path, STATUS_FAILED, duration_ms,
                        error=outcome.error, attempts=outcome.attempts,
                    )
                    context.workflow_stream.emit_workflow_failed(
                        f"node {current.id!r} failed: {outcome.error}"
                    )
                return WorkflowResult(
                    success=False,
                    outputs={},
                    node_results=node_results,
                    error=f"node {current.id!r} failed: {outcome.error}",
                )

            outputs = outcome.outputs
            status = STATUS_OK
            if outcome.error is not None:  # on_failure == "skip"
                logger.warning(
                    "node %s failed (on_failure=skip, continuing): %s",
                    current.id,
                    outcome.error,
                )
                outputs = {}
                status = STATUS_SKIPPED

            node_results[node_path] = {
                "outputs": shrink_outputs(outputs),
                "error": outcome.error,
                "duration_ms": duration_ms,
                "status": status,
                "attempts": outcome.attempts,
            }
            # Expressions resolve against the UNtruncated values.
            workflow_context.nodes[current.id] = {
                "outputs": outputs,
                "params": resolved_params,
            }
            final_outputs = outputs

            # Exactly one terminal event per node — including skipped nodes,
            # which would otherwise look like they are still running.
            if context.workflow_stream is not None:
                context.workflow_stream.emit_node_completed(
                    node_path, status, duration_ms,
                    error=outcome.error, attempts=outcome.attempts,
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

    @staticmethod
    def _make_template_store() -> Optional[Any]:
        """Build the default template store, or None when unavailable.

        The store creates its directory on construction; a read-only or
        missing output dir must not abort a run that never touches a template.
        Sub-workflow nodes then fail with the engine's existing clear
        ``template_store not available`` error.
        """
        try:
            from app.template.store import FileTemplateStore

            return FileTemplateStore()
        except Exception as exc:
            logger.warning(
                "template store unavailable (%s); sub-workflow nodes will fail",
                exc,
            )
            return None

    @staticmethod
    def _prepare_run_dir(context: ExecutionContext) -> str:
        """Create (once per run) the artifact directory for this run.

        Returns ``""`` when the directory cannot be prepared — an unwritable
        output dir must not fail the run; ``$rundir`` then resolves to an empty
        string and tools fall back to their own behaviour.
        """
        try:
            from app.workflow.rundir import run_dir_for

            return run_dir_for(context.cancel_key() or "adhoc")
        except Exception as exc:
            logger.warning(
                "run artifact dir unavailable (%s); $rundir is empty", exc
            )
            return ""

    def _cancel_result(
        self,
        node_results: Dict[str, Dict[str, Any]],
        context: Optional[ExecutionContext] = None,
    ) -> WorkflowResult:
        """Build the cancelled result and emit the terminal event."""
        if context is not None and context.workflow_stream is not None:
            context.workflow_stream.emit_workflow_cancelled()
        return WorkflowResult(
            success=False,
            outputs={},
            node_results=node_results,
            error="workflow cancelled",
            cancelled=True,
        )

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
    ) -> _NodeRun:
        """Execute one node with retry semantics.

        The retry budget is ``node.retry`` (extra attempts after the first).
        A non-retryable failure returns immediately without consuming it, and
        so does a cancellation — checked before the first attempt, before
        every retry, after every backoff sleep, and again before a terminal
        failure is reported (a killed tool surfaces as a plain non-zero exit,
        which must not be mistaken for a real failure).  Only the LAST
        attempt's outputs are ever reported: a failed attempt's partial
        outputs are discarded so a retry cannot leak half-finished state
        downstream.
        """
        max_retries = node.retry if node.retry > 0 else 0
        tool = self._lookup_tool(node.tool)

        if tool is not None:
            for warning in self._check_runtime_types(resolved_params, tool):
                logger.debug("runtime type mismatch: %s", warning)

        attempts = 0
        while True:
            if context.cancelled():
                return _NodeRun(attempts=attempts, cancelled=True)

            attempt = self._attempt_node(tool, node.tool, resolved_params, context)
            attempts += 1
            attempt.attempts = attempts

            if attempt.cancelled:
                return attempt
            if attempt.error is None:
                return attempt
            if not attempt.retryable or attempts > max_retries:
                # A tool killed by cancellation reports a non-zero exit code or
                # a generic error; without this check the run would be filed as
                # ``workflow_failed`` instead of ``cancelled``.
                if context.cancelled():
                    return _NodeRun(attempts=attempts, cancelled=True)
                return attempt
            # Check before announcing the retry: a cancelled run must not
            # look like it is about to retry.
            if context.cancelled():
                return _NodeRun(attempts=attempts, cancelled=True)

            logger.warning(
                "node %s failed: %s; retrying (%d/%d)",
                node.id,
                attempt.error,
                attempts,
                max_retries,
            )
            self._sleep_before_retry(attempts, context)
            if context.cancelled():
                return _NodeRun(attempts=attempts, cancelled=True)

    # ── retry backoff ────────────────────────────────────────────────
    # Retries wait with a fixed exponential policy (not configurable — a
    # per-node backoff field would not survive a canvas round-trip, since
    # the renderer serializer only passes a fixed set of advanced node
    # fields through).

    #: Upper bound for a single retry backoff, in seconds.
    _RETRY_BACKOFF_CAP_SECONDS = 30
    #: Cancellation poll interval while backing off, in seconds.
    _RETRY_SLEEP_SLICE_SECONDS = 0.5

    @staticmethod
    def _retry_delay(attempt: int) -> float:
        """Backoff before retry *attempt* (1-indexed): min(2^(n-1), cap)."""
        return min(
            float(2 ** (attempt - 1)),
            float(WorkflowEngine._RETRY_BACKOFF_CAP_SECONDS),
        )

    def _sleep_before_retry(self, attempt: int, context: "ExecutionContext") -> None:
        """Sleep the backoff for retry *attempt*, cancellation-aware.

        The delay is slept in short slices that poll cancellation, so a cancel
        is honored within a slice instead of after the full backoff.  The
        caller re-checks cancellation after this returns and aborts the retry
        — this method never decides to retry on its own.
        """
        deadline = time.monotonic() + self._retry_delay(attempt)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            if context.cancelled():
                return
            time.sleep(min(self._RETRY_SLEEP_SLICE_SECONDS, remaining))

    def _attempt_node(
        self,
        tool: Optional[Any],
        tool_name: str,
        resolved_params: Dict[str, Any],
        context: ExecutionContext,
    ) -> _NodeRun:
        """One full attempt at a node: validate -> execute.

        Returns:
            _NodeRun: ``retryable`` is False for failures a retry cannot fix.
        """
        if tool is None:
            return _NodeRun(error=f"tool not found: {tool_name}", retryable=False)

        validation_errors = self._validate_inputs(tool, resolved_params)
        if validation_errors:
            # The same inputs will be invalid on the next attempt.
            return _NodeRun(
                error="; ".join(validation_errors), retryable=False
            )

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
        presence check (missing required inputs) is the only validation at
        runtime — matching ``PortSet.validate_inputs``.
        """
        if isinstance(tool, BuiltinTool):
            return tool.validate(resolved_params)
        ports = getattr(tool, "ports", None)
        if ports is not None:
            return ports.validate_inputs(resolved_params)
        return []

    def _check_runtime_types(self, inputs: dict, tool: Any) -> list:
        """Check provided input values against the tool's declared base types.

        Warning-only (D7): a mismatch is reported for logging but never blocks
        execution — the engine historically accepted loosely typed values and
        existing workflows depend on that.  Subtype is advisory and
        deliberately ignored here.

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
    ) -> _NodeRun:
        """Run one tool via the unified ``tool.execute(inputs, context)`` contract.

        The engine builds the ``ToolContext`` for this node — including the
        subprocess holder (registered with ``TaskManager`` so cancellation can
        terminate a running command) and the cancellation callback.

        Error handling:
        - ``WorkflowCancelled`` (raised by nested composition) marks the node
          cancelled rather than failed.
        - ``NonRetryableToolError`` is reported with ``retryable=False``.
        - A ``ToolException`` is reported as a retryable failure string.
        - Descriptor/code tools return ``{success, returncode, ...}``; a
          non-zero exit or ``success: False`` becomes a retryable error.
        - Builtin tools return output-port-keyed dicts; an ``"error"`` key is
          reported as a retryable failure.
        """
        if not callable(getattr(tool, "execute", None)):
            raise NotImplementedError(
                f"tool {getattr(tool, 'name', type(tool).__name__)!r} has no "
                f"execute(inputs, context) contract"
            )

        holder: Dict[str, Any] = {}
        run_id = context.run_id or ""
        if run_id:
            self._attach_process(run_id, holder)

        workflow_id = self._workflow_id(context)
        tool_context = ToolContext(
            work_dir=context.work_dir,
            task_id=context.task_id,
            run_id=context.run_id,
            run_dir=context.run_dir or "",
            env=dict(context.env),
            stream_handler=_instrument_stream_handler(
                context.stream_handler,
                context.run_id,
                workflow_id,
                context.current_node_path,
            ),
            template_store=context.template_store,
            engine=context.engine or self,
            nesting_depth=context.nesting_depth,
            in_progress_templates=context.in_progress_templates,
            current_node_path=context.current_node_path,
            process_holder=holder,
            cancel_check=context.cancelled,
        )
        try:
            result = tool.execute(resolved_params, tool_context)
        except WorkflowCancelled:
            return _NodeRun(error=None, cancelled=True, retryable=False)
        except NonRetryableToolError as exc:
            return _NodeRun(error=exc.message, retryable=False)
        except ToolException as exc:
            return _NodeRun(error=exc.message)
        except Exception as exc:
            return _NodeRun(error=f"tool execution failed: {exc}")
        finally:
            if run_id:
                self._attach_process(run_id, None)

        if not isinstance(result, dict):
            tool_name = getattr(tool, "name", type(tool).__name__)
            return _NodeRun(
                error=f"tool {tool_name!r} returned a non-dict result: {result!r}"
            )

        # Descriptor/code tool result shape: {success, returncode, ...}
        if "success" in result and "returncode" in result:
            tool_name = getattr(tool, "name", type(tool).__name__)
            ok, message = normalize_result(result, tool_name)
            if not ok:
                return _NodeRun(outputs=result, error=message)
            return _NodeRun(outputs=result)

        # Builtin tool error convention: {"error": "..."}
        if result.get("error"):
            return _NodeRun(outputs={}, error=str(result["error"]))

        return _NodeRun(outputs=result)

    @staticmethod
    def _attach_process(run_id: str, holder: Optional[dict]) -> None:
        """Register/clear a node's subprocess holder with the TaskManager."""
        try:
            from app.common.task_manager import TaskManager

            TaskManager().attach_process(run_id, holder)
        except Exception:  # never let bookkeeping break a node
            logger.debug("failed to attach process holder", exc_info=True)

    @staticmethod
    def _workflow_id(context: ExecutionContext) -> str:
        """Return the workflow name stamped on this layer's tool stream events.

        Duck-typed on purpose: any stream handler object without a
        ``workflow_id`` still works, it just cannot name the layer.
        """
        return getattr(context.workflow_stream, "workflow_id", "root") or "root"
