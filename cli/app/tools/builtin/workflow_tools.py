#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sub-workflow composition builtin (workflow.run).

Provides the ``workflow.run`` node that loads and executes another saved
workflow inline, acting as a composition primitive.  The child workflow's
outputs are returned as the node's outputs, making the underlying workflow
usable as a reusable sub-flow.

Recursion guard (CRITICAL):
    The builtin carries two cross-execution safeguards against unbounded
    recursion:

    * ``MAX_NESTING_DEPTH`` (10) — the engine tracks nesting depth in the
      execution context; a ``workflow.run`` call at the limit raises a
      ``ToolException`` with a clear error message.
    * ``in_progress_workflow_ids`` — a frozenset of workflow **ids** currently
      on the call stack, propagated through the execution context.  A
      ``workflow.run`` call referencing a workflow already in this set (direct
      self-reference or mutual cycle A↔B) raises a ``ToolException`` naming the
      cycle.  The guard keys on the storage id rather than on the display name
      because names are free-form and may repeat: two distinct workflows can
      share a name, and a name-keyed guard would report a bogus cycle (or miss
      a real one) for them.

    Both guards travel through ``ExecutionContext`` → ``ToolContext``, not
    module-level globals, so concurrent workflows are isolated.

Nested events:
    A child execution inherits the parent's ``run_id`` and emits its own
    ``workflow_id`` (the child's storage id) / ``workflow_name`` (its display
    name) and its nodes under the parent node's path
    (``<parent_node_path>/<child_node_id>``), so the top level can attribute
    every event without parsing prefixes out of the workflow name.  With no
    stream callback available, child events are silently dropped.
"""

from app.common.exceptions import ToolException, WorkflowCancelled
from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.tools.builtin.base import BuiltinTool, ToolContext
from app.workflow.store import (
    AmbiguousWorkflowNameError,
    WorkflowNotFoundError,
    WorkflowStore,
)
from app.workflow.streaming import WorkflowStreamHandler

_TEXT = TypeAnnotation(BaseType.TEXT)
_JSON = TypeAnnotation(BaseType.JSON)

#: Maximum allowed nesting depth for sub-workflow chains.  Exceeding this
#: depth raises a ``ToolException`` with a descriptive error.
MAX_NESTING_DEPTH = 10


def run_child_workflow(
    workflow_ref,
    child_inputs,
    context,
    node_path_prefix,
    child_definition=None,
    workflow_id=None,
):
    """Shared child-workflow execution for workflow.run / flow.foreach / flow.branch.

    Applies the two recursion guards (cycle via ``in_progress_workflow_ids``,
    depth via ``MAX_NESTING_DEPTH``), resolves the workflow store and engine
    from *context*, loads the definition (unless *child_definition* is
    supplied — ``flow.foreach`` pre-loads once so an unknown workflow fails
    fast before its loop), builds the child stream and the child
    :class:`ExecutionContext`, and runs the child through the same engine.

    Args:
        workflow_ref: a workflow id, or a display name to resolve.  Resolved
            to an id up front so the cycle guard keys on identity.
        child_inputs: input dict passed to the child as ``$inputs.*``.
        context: the current :class:`ToolContext`.
        node_path_prefix: path under which the child's nodes are reported
            (``<parent_node_path>`` for ``workflow.run``/``flow.branch``,
            ``<parent_node_path>/<index>`` per ``flow.foreach`` item).
        child_definition: optional pre-loaded definition; when given, the
            store lookup is skipped.
        workflow_id: optional pre-resolved id, so a caller that already
            resolved the reference does not pay for a second directory scan.

    Returns:
        The child's ``WorkflowResult``.

    Raises:
        ToolException: on guard violation, missing store/engine, or an
            unknown/ambiguous workflow reference.
    """
    # ── recursion guard: depth limit ─────────────────────────────────
    if context.nesting_depth >= MAX_NESTING_DEPTH:
        raise ToolException(
            f"maximum nesting depth ({MAX_NESTING_DEPTH}) exceeded — "
            f"sub-workflow chain is too deep"
        )

    # ── resolve the workflow store ───────────────────────────────────
    workflow_store: WorkflowStore | None = context.workflow_store
    if workflow_store is None:
        raise ToolException(
            "workflow_store not available in execution context — "
            "cannot resolve sub-workflow"
        )

    # ── resolve the reference to a stable id (cycle guard identity) ───
    if workflow_id is None:
        try:
            workflow_id = workflow_store.resolve(workflow_ref)
        except AmbiguousWorkflowNameError as exc:
            raise ToolException(str(exc)) from None
        if workflow_id is None:
            raise ToolException(f"workflow not found: {workflow_ref!r}")

    # ── recursion guard: cycle detection ─────────────────────────────
    if workflow_id in context.in_progress_workflow_ids:
        raise ToolException(
            f"recursion detected: workflow {workflow_id!r} is "
            f"already executing (cycle in workflow composition)"
        )

    # ── resolve the engine ───────────────────────────────────────────
    engine = context.engine
    if engine is None:
        raise ToolException(
            "engine not available in execution context — "
            "cannot execute sub-workflow inline"
        )

    # ── load the child definition (unless pre-loaded) ────────────────
    if child_definition is None:
        try:
            child_definition = workflow_store.load(workflow_id)
        except WorkflowNotFoundError:
            raise ToolException(
                f"workflow not found: {workflow_ref!r}"
            ) from None

    # ── build the child stream (node ids are already absolute paths) ──
    child_name = getattr(child_definition, "name", None) or workflow_ref
    child_stream = (
        WorkflowStreamHandler(
            workflow_name=child_name,
            workflow_id=workflow_id,
            callback=context.stream_handler,
            run_id=context.run_id,
            task_log_id=context.task_id,
        )
        if context.stream_handler is not None or context.task_id
        else None
    )

    # ── build the child execution context ────────────────────────────
    from app.workflow.engine import ExecutionContext

    child_context = ExecutionContext(
        work_dir=context.work_dir,
        task_id=context.task_id,
        run_id=context.run_id,
        # Every nesting level shares the top-level run's artifact directory.
        run_dir=context.run_dir,
        env=dict(context.env),
        stream_handler=context.stream_handler,
        workflow_stream=child_stream,
        workflow_store=workflow_store,
        engine=engine,
        nesting_depth=context.nesting_depth + 1,
        in_progress_workflow_ids=(
            context.in_progress_workflow_ids | frozenset([workflow_id])
        ),
        node_path_prefix=node_path_prefix or "",
        # Behaviour defaults travel with the run: a sub-workflow's nodes that
        # did not pin their own failure handling inherit the same values the
        # parent run was started with.
        node_defaults=dict(context.node_defaults),
    )

    # ── execute the child inline ─────────────────────────────────────
    return engine.execute(child_definition, child_inputs, child_context)


class WorkflowRun(BuiltinTool):
    """Execute another saved workflow inline and return its outputs.

    The builtin reads the ``template`` input (a workflow id, or a display
    name to resolve) from resolved inputs, loads the definition from the
    workflow store carried in the execution context, executes it through the
    same ``WorkflowEngine`` instance with a child ``ExecutionContext`` that
    inherits the work dir, env, and nesting guards, and returns
    ``{"outputs": child_result.outputs}``.

    On success the node's ``outputs`` key holds a dict of the child
    workflow's declared outputs.  A cancelled child raises
    :class:`~app.common.exceptions.WorkflowCancelled` so the cancellation
    reaches the top level instead of being reported as a node failure; any
    other failure (load error, recursion, depth overflow, child workflow
    error) raises a ``ToolException``.
    """

    name = "workflow.run"
    description = (
        "Execute another saved workflow inline and return its outputs "
        "as the node outputs.  Bounded nesting depth and cycle detection "
        "prevent unbounded recursion."
    )

    ports = PortSet(
        inputs=[
            # The port is named ``template`` for backward compatibility with
            # every workflow graph saved before the vocabulary cleanup —
            # renaming it would invalidate their ``params``.  It now takes a
            # workflow id, or a display name to resolve.
            Port(
                "template",
                _TEXT,
                required=True,
                description="Workflow to execute, by id or name (resolved from the saved workflow library).",
            ),
            Port(
                "inputs",
                _JSON,
                required=False,
                description="Input values passed to the child workflow as $inputs.* (default {}).",
            ),
        ],
        outputs=[
            Port(
                "outputs",
                _JSON,
                required=True,
                description="The child workflow's declared outputs (the WorkflowResult.outputs dict).",
            ),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        """Run the child workflow inline under the current engine.

        Args:
            inputs: resolved params — ``template`` (str, required) and
                ``inputs`` (dict, default {}).
            context: the extended ToolContext carrying the workflow store,
                engine reference, nesting depth, in-progress id set, and
                stream handler.

        Returns:
            ``{"outputs": <child_workflow_outputs>}`` on success.

        Raises:
            WorkflowCancelled: when the child run was cancelled.
            ToolException: on any guard violation, unknown workflow, or
                child workflow failure.
        """
        workflow_ref: str = inputs["template"]
        child_workflow_inputs: dict = inputs.get("inputs") or {}

        node_path_prefix = context.current_node_path or "unknown"

        child_result = run_child_workflow(
            workflow_ref, child_workflow_inputs, context, node_path_prefix
        )

        if child_result.cancelled:
            raise WorkflowCancelled()
        if not child_result.success:
            raise ToolException(
                f"child workflow {workflow_ref!r} failed: "
                f"{child_result.error or 'unknown error'}"
            )

        return {"outputs": child_result.outputs}
