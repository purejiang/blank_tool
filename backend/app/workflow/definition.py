#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workflow definition model.

A :class:`WorkflowDefinition` is the *schema* of a workflow — the data that
describes which tools run, in what order, with what parameters.  It is
decoupled from execution (the engine, a later module) so workflows can be
saved, loaded, and validated as plain JSON.

Linear mode rule:
    ``node.next`` is the SOLE source of truth for control flow.  ``edges``
    is reserved for a future DAG mode and MUST be an empty list here; a
    non-empty ``edges`` list (or one combined with ``next`` pointers) raises
    :class:`ValueError`.

DAG-ready schema:
    ``condition``, ``on_success`` and ``type`` are STORED but NOT evaluated
    by the linear executor (reserved for future branching).  The ``condition``
    field is deliberately NOT rejected — forward compatibility means a
    workflow written for a future DAG mode still loads and validates today.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.protocol import Port

# Valid failure-handling modes for a node.  "fail" stops the workflow;
# "skip" continues past the failed node; "retry:N" retries the node up to
# N times before giving up.
_VALID_FAILURE_MODES = frozenset({"fail", "skip"})


@dataclass
class WorkflowNode:
    """One step in a workflow.

    Attributes:
        id: unique node identifier (referenced by other nodes' ``next``).
        type: node type, reserved for future DAG mode ("step", "branch",
            ...).  Currently only "step" is meaningful.
        tool: name of the tool to invoke, e.g. "bundletool" or "file.read".
        params: parameters passed to the tool when the node executes.
        next: id of the next node in the linear chain; None means this is
            the last node.
        on_success: reserved for future DAG mode (which node to run on
            success).  Stored but unused by the linear executor.
        on_failure: failure handling: "fail" (default, stops the workflow),
            "skip" (continue with the next node), or "retry:N".
        condition: stored but NOT evaluated in linear mode; reserved for
            future branching.
        retry: number of retries on failure (0 = no retry).  Only used when
            ``on_failure`` is "retry:N".
    """

    id: str
    type: str = "step"
    tool: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    next: Optional[str] = None
    on_success: Optional[str] = None
    on_failure: str = "fail"
    condition: Optional[str] = None
    retry: int = 0

    def __post_init__(self) -> None:
        """Validate the node after construction."""
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("node id must be a non-empty string")
        if not isinstance(self.tool, str) or not self.tool:
            raise ValueError(f"node {self.id!r}: tool must be a non-empty string")
        if self.on_failure not in _VALID_FAILURE_MODES and not (
            self.on_failure.startswith("retry:")
        ):
            raise ValueError(
                f"node {self.id!r}: invalid on_failure {self.on_failure!r}: "
                f"must be 'fail', 'skip', or 'retry:N'"
            )

    def to_dict(self) -> dict:
        """Serialize this node to a JSON-able dict."""
        return {
            "id": self.id,
            "type": self.type,
            "tool": self.tool,
            "params": dict(self.params),
            "next": self.next,
            "on_success": self.on_success,
            "on_failure": self.on_failure,
            "condition": self.condition,
            "retry": self.retry,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowNode":
        """Reconstruct a WorkflowNode from a dict produced by :meth:`to_dict`."""
        return cls(
            id=data["id"],
            type=data.get("type", "step"),
            tool=data.get("tool", ""),
            params=dict(data.get("params", {})),
            next=data.get("next"),
            on_success=data.get("on_success"),
            on_failure=data.get("on_failure", "fail"),
            condition=data.get("condition"),
            retry=int(data.get("retry", 0)),
        )


@dataclass
class WorkflowDefinition:
    """Schema of a linear workflow.

    Attributes:
        name: unique workflow name, e.g. "aab-install".
        version: semantic version of the workflow schema, e.g. "1.0".
        description: human-facing explanation of what the workflow does.
        inputs: workflow-level input ports (values the caller must provide).
        outputs: workflow-level output ports (values the workflow produces).
        nodes: the steps of the workflow, linked by their ``next`` pointers.
        edges: RESERVED for future DAG mode; MUST be an empty list in linear
            mode.  A non-empty list raises :class:`ValueError`.
    """

    name: str
    version: str = "1.0"
    description: str = ""
    inputs: List[Port] = field(default_factory=list)
    outputs: List[Port] = field(default_factory=list)
    nodes: List[WorkflowNode] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate the definition after construction.

        Validation rules (linear mode):
          1. edges must be an empty list (reserved for future DAG mode).
          2. node ids must be unique.
          3. every ``node.next`` must reference an existing node id.
          4. the linear chain must have exactly one entry node (a node with
             no incoming ``next`` reference from another node).
          5. following ``next`` pointers from the entry must not revisit a
             node (no cycles).
        """
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("workflow name must be a non-empty string")

        if not isinstance(self.edges, list):
            raise ValueError("edges must be a list (empty in linear mode)")
        if self.edges:
            raise ValueError("edges must be empty in linear mode")

        node_ids: Dict[str, WorkflowNode] = {}
        for node in self.nodes:
            if not isinstance(node, WorkflowNode):
                raise TypeError(
                    f"workflow {self.name!r}: nodes must be WorkflowNode, "
                    f"got {type(node).__name__}"
                )
            if node.id in node_ids:
                raise ValueError(
                    f"duplicate node id: {node.id!r} (defined in "
                    f"{node_ids[node.id]!r} and {node!r})"
                )
            node_ids[node.id] = node

        if not self.nodes:
            return

        for node in self.nodes:
            if node.next is not None and node.next not in node_ids:
                raise ValueError(
                    f"node {node.id!r} references unknown next node {node.next!r}"
                )

        # Entry node: a node no other node points to via `next`.
        referenced = {node.next for node in self.nodes if node.next is not None}
        entry_nodes = [node.id for node in self.nodes if node.id not in referenced]
        if len(entry_nodes) != 1:
            raise ValueError(
                f"linear workflow {self.name!r} must have exactly one entry "
                f"node (no incoming `next` reference), got {entry_nodes!r}"
            )

        # Cycle detection: follow `next` from the entry; revisiting a node
        # means the chain loops.
        seen: set = set()
        cursor: Optional[str] = entry_nodes[0]
        while cursor is not None:
            if cursor in seen:
                raise ValueError(
                    f"cycle detected in workflow {self.name!r}: node "
                    f"{cursor!r} is visited twice following `next`"
                )
            seen.add(cursor)
            cursor = node_ids[cursor].next

    def to_dict(self) -> dict:
        """Serialize this definition to a JSON-able dict."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "inputs": [port.to_dict() for port in self.inputs],
            "outputs": [port.to_dict() for port in self.outputs],
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [dict(edge) for edge in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowDefinition":
        """Reconstruct a WorkflowDefinition from a dict produced by :meth:`to_dict`.

        Args:
            data: dict with (at least) a "name" key.  Missing or invalid
                fields raise :class:`ValueError` / :class:`TypeError` naming
                the offending field.

        Returns:
            A validated :class:`WorkflowDefinition`.

        Raises:
            ValueError: if a required field is missing, or validation fails
                (including non-empty ``edges``).
        """
        if not isinstance(data, dict):
            raise ValueError(
                f"workflow data must be a dict, got {type(data).__name__}"
            )
        if "name" not in data:
            raise ValueError("missing required field: 'name'")

        try:
            return cls(
                name=data["name"],
                version=data.get("version", "1.0"),
                description=data.get("description", ""),
                inputs=[Port.from_dict(port) for port in data.get("inputs", [])],
                outputs=[Port.from_dict(port) for port in data.get("outputs", [])],
                nodes=[
                    WorkflowNode.from_dict(node) for node in data.get("nodes", [])
                ],
                edges=[dict(edge) for edge in data.get("edges", [])],
            )
        except (TypeError, ValueError) as exc:
            # __post_init__ already raised a descriptive ValueError; pass it
            # through.  TypeErrors (e.g. a non-list edges) get wrapped.
            if isinstance(exc, ValueError):
                raise
            raise ValueError(f"invalid workflow field: {exc}") from exc

    def to_json_file(self, path: str) -> None:
        """Write this definition to a UTF-8 JSON file on disk.

        Args:
            path: filesystem path to write to (parent dirs must exist).

        Raises:
            OSError: if the file cannot be written.
        """
        file_path = Path(path)
        file_path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def from_json_file(cls, path: str) -> "WorkflowDefinition":
        """Load a definition from a UTF-8 JSON file on disk.

        Args:
            path: filesystem path to the workflow JSON file.

        Returns:
            A validated :class:`WorkflowDefinition`.

        Raises:
            ValueError: if the file cannot be read, is not valid JSON, or
                does not contain a valid workflow dict.
        """
        file_path = Path(path)
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ValueError(f"workflow file not found: {path}") from None
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid JSON in workflow file {path}: {exc}"
            ) from exc
        return cls.from_dict(raw)
