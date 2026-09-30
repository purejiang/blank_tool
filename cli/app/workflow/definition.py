#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workflow definition model.

A :class:`WorkflowDefinition` is the *schema* of a workflow — the data that
describes which tools run, in what order, with what parameters.  It is
decoupled from execution (the engine, a later module) so workflows can be
saved, loaded, and validated as plain JSON.

Control flow:
    ``node.next`` is the SOLE source of truth.  Branching is expressed with
    the ``flow.branch`` / ``flow.compare`` tools (composition), not with a
    node-level ``condition`` field — so the schema carries no dead fields that
    would fail halfway through a run.

Failure handling:
    ``on_failure`` is ``"fail"`` (stop the workflow) or ``"skip"`` (continue
    past the node); ``retry`` is the number of extra attempts.

    Both fields are OPTIONAL and default to ``None``, which means "inherit the
    run-level default" (``node_defaults`` on the execute request, see
    :func:`normalize_node_defaults`).  An explicit value — including the
    explicit ``"fail"`` / ``0`` that older files always carried — always wins
    over the inherited default, so pre-existing workflows keep their exact
    behaviour.  Keeping "unset" distinguishable from "explicitly fail" is what
    lets the editor store a node that follows the user's global defaults
    without pinning today's values into the file.

Display name:
    ``label`` is a purely cosmetic node name.  It is never used for control
    flow (that is ``id``), never referenced by expressions, and may be absent.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.protocol import Port

# Valid failure-handling modes for a node.  "fail" stops the workflow;
# "skip" continues past the failed node.
_VALID_FAILURE_MODES = frozenset({"fail", "skip"})

#: Built-in fallbacks used when neither the node nor the run defaults say
#: anything.  Equal to the historical hard-coded behaviour.
DEFAULT_ON_FAILURE = "fail"
DEFAULT_RETRY = 0


def normalize_label(raw: Any) -> Optional[str]:
    """Return *raw* as a trimmed non-empty node label, or ``None``.

    Non-strings, blanks and whitespace-only values all mean "no label" — the
    consumers then fall back to the tool name.
    """
    if not isinstance(raw, str):
        return None
    label = raw.strip()
    return label or None


def normalize_node_defaults(raw: Any) -> Dict[str, Any]:
    """Normalize a ``node_defaults`` run parameter into a clean dict.

    Accepts ``{"on_failure": "fail"|"skip", "retry": <non-negative int>}`` and
    silently drops anything else (unknown keys, wrong types, invalid modes,
    negative or boolean retry counts).  A malformed payload therefore degrades
    to "no defaults" instead of failing the run — the caller is a UI layer, not
    a trusted schema validator.
    """
    if not isinstance(raw, dict):
        return {}
    defaults: Dict[str, Any] = {}
    mode = raw.get("on_failure")
    if isinstance(mode, str) and mode in _VALID_FAILURE_MODES:
        defaults["on_failure"] = mode
    retry = raw.get("retry")
    if retry is not None and not isinstance(retry, bool):
        try:
            parsed = int(retry)
        except (TypeError, ValueError):
            parsed = -1
        if parsed >= 0:
            defaults["retry"] = parsed
    return defaults


def _parse_optional_retry(raw: Any, node_id: Any) -> Optional[int]:
    """Parse a wire ``retry`` value into ``None`` or a non-negative int.

    ``None``/absent means "inherit".  Bools are rejected explicitly (``bool``
    is an ``int`` subclass, so ``True`` would otherwise become ``1``), and
    non-integral or negative values raise the same descriptive ``ValueError``
    the dataclass raises for hand-built nodes.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ValueError(
            f"node {node_id!r}: invalid retry {raw!r}: "
            f"must be a non-negative integer or None (inherit)"
        )
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        raise ValueError(
            f"node {node_id!r}: invalid retry {raw!r}: "
            f"must be a non-negative integer or None (inherit)"
        ) from None
    if isinstance(raw, float) and not raw.is_integer():
        raise ValueError(
            f"node {node_id!r}: invalid retry {raw!r}: "
            f"must be a non-negative integer or None (inherit)"
        )
    return parsed


@dataclass
class WorkflowNode:
    """One step in a workflow.

    Attributes:
        id: unique node identifier (referenced by other nodes' ``next``).
        type: node type ("step"); informational, kept for editors.
        tool: name of the tool to invoke, e.g. "bundletool" or "file.read".
        params: parameters passed to the tool when the node executes.
        next: id of the next node in the linear chain; None means this is
            the last node.
        label: optional display name (cosmetic only; never referenced).
        on_failure: failure handling — "fail" (stop the workflow), "skip"
            (continue with the next node), or None to inherit the run-level
            default.
        retry: number of EXTRA attempts on failure (0 = no retry); None to
            inherit the run-level default.
    """

    id: str
    type: str = "step"
    tool: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    next: Optional[str] = None
    label: Optional[str] = None
    on_failure: Optional[str] = None
    retry: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate the node after construction."""
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("node id must be a non-empty string")
        if not isinstance(self.tool, str) or not self.tool:
            raise ValueError(f"node {self.id!r}: tool must be a non-empty string")
        self.label = normalize_label(self.label)
        if self.on_failure is not None and self.on_failure not in _VALID_FAILURE_MODES:
            raise ValueError(
                f"node {self.id!r}: invalid on_failure {self.on_failure!r}: "
                f"must be 'fail', 'skip' or None (inherit)"
            )
        if self.retry is not None:
            # bool is a subclass of int: True must not sneak in as retry=1.
            if isinstance(self.retry, bool) or not isinstance(self.retry, int):
                raise ValueError(
                    f"node {self.id!r}: invalid retry {self.retry!r}: "
                    f"must be a non-negative integer or None (inherit)"
                )
            if self.retry < 0:
                raise ValueError(
                    f"node {self.id!r}: invalid retry {self.retry!r}: "
                    f"must be a non-negative integer or None (inherit)"
                )

    def to_dict(self) -> dict:
        """Serialize this node to a JSON-able dict."""
        return {
            "id": self.id,
            "type": self.type,
            "tool": self.tool,
            "params": dict(self.params),
            "next": self.next,
            "label": self.label,
            "on_failure": self.on_failure,
            "retry": self.retry,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowNode":
        """Reconstruct a WorkflowNode from a dict produced by :meth:`to_dict`.

        A missing OR ``null`` ``on_failure``/``retry`` means "inherit the
        run-level default".  Files written before those fields became optional
        always carried explicit values, so they keep their behaviour.
        """
        return cls(
            id=data["id"],
            type=data.get("type", "step"),
            tool=data.get("tool", ""),
            params=dict(data.get("params", {})),
            next=data.get("next"),
            label=data.get("label"),
            on_failure=data.get("on_failure"),
            retry=_parse_optional_retry(data.get("retry"), data.get("id")),
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
    """

    name: str
    version: str = "1.0"
    description: str = ""
    inputs: List[Port] = field(default_factory=list)
    outputs: List[Port] = field(default_factory=list)
    nodes: List[WorkflowNode] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate the definition after construction.

        Validation rules:
          1. node ids must be unique.
          2. every ``node.next`` must reference an existing node id.
          3. the chain must have exactly one entry node (a node with no
             incoming ``next`` reference from another node).
          4. following ``next`` pointers from the entry must not revisit a
             node (no cycles).
        """
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("workflow name must be a non-empty string")

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
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowDefinition":
        """Reconstruct a WorkflowDefinition from a dict produced by :meth:`to_dict`.

        Unknown keys (including fields from older schema revisions such as
        ``edges`` / ``condition``) are ignored, so stale editor output still
        loads.

        Args:
            data: dict with (at least) a "name" key.  Missing or invalid
                fields raise :class:`ValueError` / :class:`TypeError` naming
                the offending field.

        Returns:
            A validated :class:`WorkflowDefinition`.

        Raises:
            ValueError: if a required field is missing, or validation fails.
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
            )
        except (TypeError, ValueError) as exc:
            # __post_init__ already raised a descriptive ValueError; pass it
            # through.  TypeErrors (e.g. a non-list nodes) get wrapped.
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
