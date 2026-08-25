#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sub-workflow composition builtin (workflow.run).

Provides the ``workflow.run`` node that loads and executes another workflow
template inline, acting as a composition primitive.  The child workflow's
outputs are returned as the node's outputs, making the underlying template
usable as a reusable sub-flow.

Recursion guard (CRITICAL):
    The builtin carries two cross-execution safeguards against unbounded
    recursion:

    * ``MAX_NESTING_DEPTH`` (10) — the engine tracks nesting depth in the
      execution context; a ``workflow.run`` call at the limit raises a
      ``ToolException`` with a clear error message.
    * ``in_progress_templates`` — a frozenset of template names currently on
      the call stack, propagated through the execution context.  A
      ``workflow.run`` call referencing a template already in this set (direct
      self-reference or mutual cycle A↔B) raises a ``ToolException`` naming
      the cycle.

    Both guards travel through ``ExecutionContext`` → ``ToolContext``, not
    module-level globals, so concurrent workflows are isolated.

Namespaced nested events:
    Child node events carry a ``workflow_id`` and ``node_id`` prefixed
    ``<parent_workflow_id>/<current_node_id>`` so the top-level UI can
    ignore them and only display the parent workflow's nodes.  The prefixing
    is done by wrapping the stream callback; if no stream callback is
    available, child events are silently dropped.
"""

from app.common.exceptions import ToolException
from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.tools.builtin.base import BuiltinTool, ToolContext
from app.template.store import TemplateNotFoundError, TemplateStore
from app.workflow.streaming import WorkflowStreamHandler

_TEXT = TypeAnnotation(BaseType.TEXT)
_JSON = TypeAnnotation(BaseType.JSON)

#: Maximum allowed nesting depth for sub-workflow chains.  Exceeding this
#: depth raises a ``ToolException`` with a descriptive error.
MAX_NESTING_DEPTH = 10


def _make_namespaced_stream_handler(parent_callback, namespace_prefix):
    """Wrap a stream callback so nested event IDs are prefixed.

    When *parent_callback* is ``None``, returns ``None`` (child events are
    silently dropped).  Otherwise returns a wrapper that intercepts every
    event dict, copying it and prefixing ``workflow_id`` and ``node_id``
    with ``namespace_prefix`` before forwarding to the parent callback.

    Example::
        parent wf_id="task-1", node_id="sub_1"
        → namespace_prefix = "task-1/sub_1"
        → child wf_id="child" becomes "task-1/sub_1/child"
        → child node_id="w" becomes "task-1/sub_1/w"
    """
    if parent_callback is None:
        return None

    def wrapper(event):
        prefixed = dict(event)
        if "workflow_id" in prefixed:
            prefixed["workflow_id"] = (
                f"{namespace_prefix}/{prefixed['workflow_id']}"
            )
        if "node_id" in prefixed:
            prefixed["node_id"] = f"{namespace_prefix}/{prefixed['node_id']}"
        parent_callback(prefixed)

    return wrapper


def _run_child_template(
    template_name,
    child_inputs,
    context,
    namespace_prefix,
    child_definition=None,
):
    """Shared child-workflow execution for workflow.run / flow.foreach / flow.branch.

    Applies the two recursion guards (cycle via ``in_progress_templates``,
    depth via ``MAX_NESTING_DEPTH``), resolves the template store and engine
    from *context*, loads the definition (unless *child_definition* is
    supplied — ``flow.foreach`` pre-loads once so an unknown template fails
    fast before its loop), builds the namespaced child stream and the child
    :class:`ExecutionContext`, and runs the child through the same engine.

    Args:
        template_name: template name (used for guards, loading and events).
        child_inputs: input dict passed to the child as ``$inputs.*``.
        context: the current :class:`ToolContext`.
        namespace_prefix: event id prefix (``<parent_wf_id>/<node_id>[/i]``).
        child_definition: optional pre-loaded definition; when given, the
            template store lookup is skipped.

    Returns:
        The child's ``WorkflowResult``.

    Raises:
        ToolException: on guard violation, missing store/engine, or an
            unknown template.
    """
    # ── recursion guard: cycle detection ─────────────────────────────
    if template_name in context.in_progress_templates:
        raise ToolException(
            f"recursion detected: template {template_name!r} is "
            f"already executing (cycle in workflow composition)"
        )

    # ── recursion guard: depth limit ─────────────────────────────────
    if context.nesting_depth >= MAX_NESTING_DEPTH:
        raise ToolException(
            f"maximum nesting depth ({MAX_NESTING_DEPTH}) exceeded — "
            f"sub-workflow chain is too deep"
        )

    # ── resolve the template store ───────────────────────────────────
    template_store: TemplateStore | None = context.template_store
    if template_store is None:
        raise ToolException(
            "template_store not available in execution context — "
            "cannot resolve sub-workflow template"
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
            child_definition = template_store.load(template_name)
        except TemplateNotFoundError:
            raise ToolException(
                f"template not found: {template_name!r}"
            ) from None

    # ── build the namespaced stream for nested events ────────────────
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

    # ── build the child execution context ────────────────────────────
    from app.workflow.engine import ExecutionContext

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

    # ── execute the child inline ─────────────────────────────────────
    return engine.execute(child_definition, child_inputs, child_context)


class WorkflowRun(BuiltinTool):
    """Execute another workflow template inline and return its outputs.

    The builtin reads ``template`` (name) from resolved inputs, loads the
    definition from the template store carried in the execution context,
    executes it through the same ``WorkflowEngine`` instance with a child
    ``ExecutionContext`` that inherits the work dir, env, and nesting guards,
    and returns ``{"outputs": child_result.outputs}``.

    On success the node's ``outputs`` key holds a dict of the child
    workflow's declared outputs.  On failure (load error, recursion, depth
    overflow, or child workflow error) a ``ToolException`` is raised with
    a message that the engine reports as a node failure.
    """

    name = "workflow.run"
    description = (
        "Execute another workflow template inline and return its outputs "
        "as the node outputs.  Bounded nesting depth and cycle detection "
        "prevent unbounded recursion."
    )

    ports = PortSet(
        inputs=[
            Port(
                "template",
                _TEXT,
                required=True,
                description="Name of the workflow template to execute (loaded from the template store).",
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
            context: the extended ToolContext carrying the template store,
                engine reference, nesting depth, in-progress set, and
                stream handler.

        Returns:
            ``{"outputs": <child_workflow_outputs>}`` on success.

        Raises:
            ToolException: on any guard violation, template not found, or
                child workflow failure.
        """
        template_name: str = inputs["template"]
        child_workflow_inputs: dict = inputs.get("inputs") or {}

        parent_wf_id = context.parent_workflow_id or "root"
        current_node_id = context.current_node_id or "unknown"
        namespace_prefix = f"{parent_wf_id}/{current_node_id}"

        child_result = _run_child_template(
            template_name, child_workflow_inputs, context, namespace_prefix
        )

        if not child_result.success:
            raise ToolException(
                f"child workflow {template_name!r} failed: "
                f"{child_result.error or 'unknown error'}"
            )

        return {"outputs": child_result.outputs}
