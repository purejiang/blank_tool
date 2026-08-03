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
    Tools resolve by name from the builtin registry (``_BUILTIN_TOOLS`` —
    ``file.read``, ``file.write``, ...) and the injected ``ToolManager``
    (descriptor/code tools).  Builtin tools run under the dict +
    :class:`ToolContext` contract.  Descriptor/code tools (``apktool``,
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

from app.common.base_executor import CommandExecutionContext
from app.common.exceptions import ToolException
from app.tools.builtin.base import BuiltinTool, ToolContext
from app.tools.builtin.exec_tools import CodeExec, ShellExec
from app.tools.builtin.file_tools import (
    FileCopy,
    FileDelete,
    FileHash,
    FileMove,
    FileRead,
    FileWrite,
)
from app.tools.builtin.flow_tools import FlowAssert, FlowLog
from app.tools.builtin.fs_tools import (
    ArchiveCreate,
    ArchiveExtract,
    DirCreate,
    DirDelete,
    DirList,
    TextGrep,
)
from app.tools.builtin.net_tools import NetDownload, NetRequest
from app.tools.tool_manager import ToolManager
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.expression import ExpressionEngine, ExpressionError, WorkflowContext

logger = logging.getLogger(__name__)

# Shared, stateless expression engine (safe across runs — see expression.py).
_EXPRESSION_ENGINE = ExpressionEngine()

# Builtin atomic tools by name.  These are NOT in ToolManager (which discovers
# descriptor/code tools); the engine consults this dict first when resolving a
# node's tool name.
_BUILTIN_TOOLS: Dict[str, BuiltinTool] = {
    "file.read": FileRead(),
    "file.write": FileWrite(),
    "file.copy": FileCopy(),
    "file.move": FileMove(),
    "file.delete": FileDelete(),
    "file.hash": FileHash(),
    "dir.list": DirList(),
    "dir.create": DirCreate(),
    "dir.delete": DirDelete(),
    "text.grep": TextGrep(),
    "archive.extract": ArchiveExtract(),
    "archive.create": ArchiveCreate(),
    "net.download": NetDownload(),
    "net.request": NetRequest(),
    "shell.exec": ShellExec(),
    "code.exec": CodeExec(),
    "flow.assert": FlowAssert(),
    "flow.log": FlowLog(),
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
    """

    work_dir: str
    task_id: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    stream_handler: Optional[Callable[[dict], None]] = None


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

            current = node_by_id.get(current.next)

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
        """Resolve a tool name to a tool object.

        Builtin primitives are checked first (``file.read``, ...); descriptor
        and code tools come from the injected ToolManager registry.  Returns
        None when the name is unknown to both sources.
        """
        builtin = _BUILTIN_TOOLS.get(tool_name)
        if builtin is not None:
            return builtin
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

    def _execute_tool(
        self,
        tool: Any,
        resolved_params: Dict[str, Any],
        context: ExecutionContext,
    ) -> tuple:
        """Run one tool, converting execution failures into error strings.

        Two execution contracts are dispatched by tool kind:

        - Builtin tools (``file.read``, ...) consume a params dict +
          :class:`ToolContext`; a ``ToolException`` or a result dict
          containing an ``"error"`` key is reported as a failure.
        - Descriptor/code tools (``apktool``, ``bundletool``, ...) consume a
          command list + :class:`CommandExecutionContext`.  The workflow
          template passes the arguments as ``params["args"]`` (a list, after
          expression resolution); the command list is extracted from it and
          handed to ``tool.execute(command, context)``.  The result dict
          (``success``/``returncode``/``stdout``/``stderr``) is converted to
          the standard node output shape, with a non-zero exit or explicit
          ``success: False`` reported as a failure so ``on_failure``
          semantics apply.
        - Anything else (neither builtin nor a command-list tool) raises
          :class:`NotImplementedError`.

        Returns:
            tuple: ``(outputs, error)`` — ``error`` is None on success.
        """
        if isinstance(tool, BuiltinTool):
            return self._execute_builtin_tool(tool, resolved_params, context)
        if callable(getattr(tool, "execute", None)):
            return self._execute_command_tool(tool, resolved_params, context)
        raise NotImplementedError(
            f"tool {getattr(tool, 'name', type(tool).__name__)!r} is not a "
            f"builtin tool and has no command-list execute contract"
        )

    def _execute_builtin_tool(
        self,
        tool: BuiltinTool,
        resolved_params: Dict[str, Any],
        context: ExecutionContext,
    ) -> tuple:
        """Run a builtin tool: params dict + :class:`ToolContext`.

        A ``ToolException`` raised by the tool, or a result dict containing
        an ``"error"`` key, is reported as a failure.

        Returns:
            tuple: ``(outputs, error)`` — ``error`` is None on success.
        """
        tool_context = ToolContext(
            work_dir=context.work_dir,
            task_id=context.task_id,
            env=dict(context.env),
            stream_handler=context.stream_handler,
        )
        try:
            outputs = tool.execute(resolved_params, tool_context)
        except ToolException as exc:
            return {}, exc.message
        if isinstance(outputs, dict) and outputs.get("error"):
            return {}, str(outputs["error"])
        return outputs, None

    def _execute_command_tool(
        self,
        tool: Any,
        resolved_params: Dict[str, Any],
        context: ExecutionContext,
    ) -> tuple:
        """Run a descriptor/code tool: ``params["args"]`` as a command list.

        Workflow templates declare descriptor/code tool arguments as
        ``params: {"args": [...]}``; after expression resolution ``args`` is
        the command list for ``tool.execute(command, context)``.  The result
        dict (``success``/``returncode``/``stdout``/``stderr``) is converted
        to the standard node output format; a non-zero exit or explicit
        ``success: False`` becomes an error so ``on_failure`` semantics
        (fail/skip/retry) apply.

        Returns:
            tuple: ``(outputs, error)`` — ``error`` is None on success.
        """
        command = resolved_params.get("args")
        if not isinstance(command, list):
            tool_name = getattr(tool, "name", type(tool).__name__)
            return {}, (
                f"tool {tool_name!r} requires params['args'] (a command "
                f"list) in workflows, got {type(command).__name__}"
            )

        command_context = CommandExecutionContext(
            cwd=context.work_dir,
            task_id=context.task_id,
            env=dict(context.env) or None,
            process_holder={},
        )
        try:
            result = tool.execute(list(command), command_context)
        except ToolException as exc:
            return {}, exc.message
        except Exception as exc:  # subprocess failures surface as error strings
            return {}, f"tool execution failed: {exc}"

        if not isinstance(result, dict):
            tool_name = getattr(tool, "name", type(tool).__name__)
            return {}, (
                f"tool {tool_name!r} returned a non-dict result: {result!r}"
            )

        success = result.get("success", True)
        returncode = result.get("returncode", 0)
        if success is False or returncode != 0:
            detail = (result.get("stderr") or result.get("stdout") or "").strip()
            tool_name = getattr(tool, "name", type(tool).__name__)
            message = f"tool {tool_name!r} failed (exit {returncode})"
            if detail:
                message += f": {detail}"
            return result, message
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
