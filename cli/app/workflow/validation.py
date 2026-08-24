#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static validation of workflow definitions.

Validation runs before execution, so it can only rely on the static data in
a :class:`WorkflowDefinition` plus the tool registry:

1. every ``node.tool`` name exists in the registry;
2. every required input port of the tool is provided in ``node.params``
   (values that are, or contain, expression templates such as ``$inputs.x``
   are treated as potentially resolvable at runtime, hence present — only
   params that are missing entirely are flagged);
3. the output port types of upstream nodes are base-type compatible with the
   input port types of downstream nodes, for connections expressed as
   ``$nodes.<id>.outputs.<port>`` references (best-effort — a connection
   whose referenced node, port or tool cannot be resolved is reported when
   the reference is dangling, otherwise skipped, never guessed);
4. the linear chain has no orphan nodes (every node reachable from the entry);
5. an entry node exists (defensive — ``WorkflowDefinition.__post_init__``
   already enforces exactly one entry);
6. reserved DAG-mode fields: ``condition`` is an error (the linear executor
   raises NotImplementedError on it at runtime) and ``on_success`` is a
   warning (stored but silently ignored).

Findings are returned as :class:`ValidationError` objects; an empty list
means the workflow is valid.  Warnings are informational — a workflow with
warnings can still run.

Limitations (documented per plan):
  - Expression syntax is NOT validated (that is the expression engine's
    runtime job).  ``$...`` values are only inspected to find node-output
    references for the type-compatibility check.
  - Tool-specific parameter values are NOT validated; only presence of
    required inputs is checked.
  - ``$inputs.x`` (workflow-level input) references are not type-checked
    against node input ports — only node-to-node connections are.
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from app.protocol import PortSet, TypeAnnotation
from app.workflow.definition import WorkflowDefinition

if TYPE_CHECKING:
    from app.tools.tool_manager import ToolManager

# Expression referencing another node's output port, e.g.
# "$nodes.convert.outputs.apks_path".  The node id is captured as any run of
# non-dot characters; ids containing dots cannot be disambiguated and are
# therefore not matched (best-effort).
_NODE_OUTPUT_REF = re.compile(r"\$nodes\.([^.]+)\.outputs\.([a-z][a-z0-9_]*)")


@dataclass
class ValidationError:
    """A single finding from :func:`validate_workflow`.

    Attributes:
        node_id: id of the offending node; None for workflow-level findings
            (e.g. a missing entry node).
        field: which check produced the finding — "tool", "params",
            "port_compatibility", "connectivity", or "structure".
        message: human-readable description of the problem.
        severity: "error" (the workflow must be fixed) or "warning"
            (informational; the workflow can still run).
    """

    node_id: Optional[str]
    field: str
    message: str
    severity: str = "error"


def validate_workflow(
    definition: WorkflowDefinition, registry: "ToolManager"
) -> List[ValidationError]:
    """Validate a workflow definition against the tool registry.

    Args:
        definition: the workflow schema to validate.
        registry: a tool registry exposing ``get_tool(name)`` returning the
            tool (with a ``ports`` :class:`PortSet` attribute/property) or
            None when the tool is unknown.

    Returns:
        list: all findings as :class:`ValidationError`; empty means valid.
            Errors must be fixed; warnings are informational.
    """
    errors: List[ValidationError] = []
    if not definition.nodes:
        return errors  # empty workflow is trivially valid

    # Resolve each node's tool once; a missing tool short-circuits the port
    # checks (checks 2/3) for that node but not the connectivity checks.
    tools: dict = {}
    for node in definition.nodes:
        tool = registry.get_tool(node.tool)
        tools[node.id] = tool
        if tool is None:
            errors.append(
                ValidationError(
                    node_id=node.id,
                    field="tool",
                    message=f"tool not found: {node.tool}",
                    severity="error",
                )
            )

    # Reserved DAG-mode fields.  ``condition`` and ``on_success`` are stored
    # for forward compatibility but the linear executor does not honor them:
    # ``condition`` raises NotImplementedError mid-run (engine.py), so it is
    # rejected here at validation time; ``on_success`` is silently ignored by
    # the engine, so it is surfaced as a warning only.
    for node in definition.nodes:
        if node.condition is not None:
            errors.append(
                ValidationError(
                    node_id=node.id,
                    field="structure",
                    message=(
                        "condition is reserved for future DAG mode and not "
                        "supported in linear mode; remove the field or set to null"
                    ),
                    severity="error",
                )
            )
        if node.on_success is not None:
            errors.append(
                ValidationError(
                    node_id=node.id,
                    field="structure",
                    message=(
                        "on_success is reserved for future DAG mode and "
                        "silently ignored in linear mode"
                    ),
                    severity="warning",
                )
            )

    # Check 2 — required input presence.  validate_inputs is presence-only,
    # so an expression-valued param still satisfies its required port; only
    # params that are missing entirely are flagged.  Legacy tools without a
    # port contract are skipped (cannot be checked).
    for node in definition.nodes:
        tool = tools[node.id]
        if tool is None:
            continue
        ports = getattr(tool, "ports", None)
        if ports is None:
            continue
        for err in ports.validate_inputs(node.params):
            errors.append(
                ValidationError(
                    node_id=node.id, field="params", message=err, severity="error"
                )
            )

    # Check 3 — port type compatibility along expression-referenced
    # connections (base-type check; subtype advisory and ignored).
    errors.extend(_check_port_compatibility(definition, tools))

    # Check 5 — entry node exists.  Defensive: __post_init__ raises on a
    # missing entry, so this only fires for hand-built definitions.
    referenced = {node.next for node in definition.nodes if node.next is not None}
    entry_nodes = [node.id for node in definition.nodes if node.id not in referenced]
    if not entry_nodes:
        errors.append(
            ValidationError(
                node_id=None,
                field="structure",
                message="no entry node (cycle or missing start)",
                severity="error",
            )
        )

    # Check 4 — linear connectivity: every node must be reachable from the
    # entry by following ``next``.  Skipped when there is no entry (already
    # reported above — flagging every node as an orphan would be noise).
    if entry_nodes:
        reachable = _reachable_nodes(definition, entry_nodes[0])
        for node in definition.nodes:
            if node.id not in reachable:
                errors.append(
                    ValidationError(
                        node_id=node.id,
                        field="connectivity",
                        message="orphan node not reachable from entry",
                        severity="error",
                    )
                )

    return errors


def _check_port_compatibility(
    definition: WorkflowDefinition, tools: dict
) -> List[ValidationError]:
    """Best-effort base-type check of ``$nodes.<id>.outputs.<port>`` refs.

    For every such reference found in a node's params, the referenced node's
    output port type is compared against the referencing node's input port
    type.  A dangling reference to an unknown node is an error; a reference
    whose type cannot be determined on either side is skipped; an
    incompatible base type is a warning (expression resolution at runtime
    might transform the value).
    """
    errors: List[ValidationError] = []
    by_id = {node.id: node for node in definition.nodes}

    for node in definition.nodes:
        tool = tools.get(node.id)
        if tool is None:
            continue
        ports = getattr(tool, "ports", None)
        if ports is None:
            continue
        for input_name, value in node.params.items():
            for ref in _NODE_OUTPUT_REF.finditer(str(value)):
                ref_node_id, ref_port_name = ref.group(1), ref.group(2)
                ref_node = by_id.get(ref_node_id)
                if ref_node is None:
                    errors.append(
                        ValidationError(
                            node_id=node.id,
                            field="port_compatibility",
                            message=(
                                f"reference to unknown node {ref_node_id!r} "
                                f"in param {input_name!r}"
                            ),
                            severity="error",
                        )
                    )
                    continue
                downstream_type = _port_annotation(ports, input_name, "inputs")
                upstream_type = _node_output_annotation(
                    by_id, tools, ref_node, ref_port_name
                )
                if downstream_type is None or upstream_type is None:
                    continue  # cannot determine the connection — skip
                if not TypeAnnotation.is_compatible(upstream_type, downstream_type):
                    errors.append(
                        ValidationError(
                            node_id=node.id,
                            field="port_compatibility",
                            message=(
                                f"type mismatch: {ref_node_id}.outputs."
                                f"{ref_port_name} ({upstream_type.base.value}) -> "
                                f"{node.id}.inputs.{input_name} "
                                f"({downstream_type.base.value})"
                            ),
                            severity="warning",
                        )
                    )
    return errors


def _node_output_annotation(
    by_id: dict, tools: dict, node, port_name: str
) -> Optional[TypeAnnotation]:
    """Return the type of a node's output port, or None when unknowable."""
    ref_tool = tools.get(node.id)
    if ref_tool is None:
        return None
    ref_ports = getattr(ref_tool, "ports", None)
    if ref_ports is None:
        return None
    return _port_annotation(ref_ports, port_name, "outputs")


def _port_annotation(
    ports: PortSet, name: str, role: str
) -> Optional[TypeAnnotation]:
    """Return the TypeAnnotation of a port by name, or None if unknown."""
    entries = ports.inputs if role == "inputs" else ports.outputs
    for port in entries:
        if port.name == name:
            return port.type
    return None


def _reachable_nodes(definition: WorkflowDefinition, entry_id: str) -> set:
    """Return ids of every node reachable by following ``next`` from the entry.

    Iterative walk with a visited set, so cyclic ``next`` pointers cannot
    loop forever (defensive — ``__post_init__`` already rejects cycles).
    """
    by_id = {node.id: node for node in definition.nodes}
    reachable: set = set()
    stack = [entry_id]
    while stack:
        node_id = stack.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        nxt = by_id[node_id].next
        if nxt is not None and nxt in by_id:
            stack.append(nxt)
    return reachable
