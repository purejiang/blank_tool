#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workflow expression engine.

Resolves ``$``-prefixed references inside workflow params.  Two forms exist:

Whole-value expression
    A string that starts with ``$`` and is ONE expression, e.g.
    ``"$inputs.aab_path"`` or ``"$nodes.convert.outputs.apks_path |
    basename"``.  The resolved value keeps its own type (a number stays a
    number, a dict stays a dict), which is what binding a value to a typed
    port needs.  ``$$`` at the start escapes to a literal ``$``.

Interpolation
    Any string containing ``${...}`` substitutes each occurrence, e.g.
    ``"found ${nodes.scan.outputs.count} matches in ${inputs.target}"``.
    A string that is exactly one ``${...}`` (nothing around it) keeps the
    expression's own type, so ``"${inputs.count}"`` behaves like
    ``"$inputs.count"``.  Inside surrounding text the value is rendered as
    text: strings as-is, ``true``/``false`` for booleans, an empty string for
    ``null``, and compact JSON for objects/arrays.  Write ``$${`` for a
    literal ``${`` (needed for shell snippets such as ``${HOME}``).

    Every expression — whole-value or interpolated — supports the same
    dot-notation paths and pipes (``basename``, ``dirname``,
    ``default:<value>``) and the same security rules; see below.

Security model (Oracle review #8):
    The engine NEVER uses ``getattr``, ``eval`` or ``exec``.  All user-
    controlled traversal is dict access (``mapping[key]``) starting from a
    FIXED dispatch table that maps the five context roots (``inputs``,
    ``nodes``, ``env``, ``workdir``, ``rundir``) to their resolver functions —
    an unknown root is an error, never an attribute probe.  Every path
    component matching ``^_`` (dunder / private names) is rejected with
    :class:`ExpressionError`.  Pipe transforms likewise dispatch through a
    FIXED table; an unknown pipe name raises :class:`ExpressionError` rather
    than dispatching dynamically.
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

# Any path component matching this is rejected as dunder / private access.
_DUNDER_RE = re.compile(r"^_")

# Fixed set of node result sections reachable through ``$nodes.<id>.<section>``.
_NODE_SECTIONS = frozenset({"outputs", "params"})

#: Interpolation markers.
_INTERP_OPEN = "${"
_ESCAPED_INTERP_OPEN = "$${"


def _to_text(value: Any) -> str:
    """Render a resolved value as text for string interpolation."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, default=str)


class ExpressionError(Exception):
    """Raised when a template cannot be resolved safely.

    Triggered by dunder / private key access, an unknown pipe name, an
    unresolvable reference (missing key / node / section), or a malformed
    template.  The message always names the offending component.
    """


@dataclass
class WorkflowContext:
    """Values available to expressions during a workflow run.

    Attributes:
        inputs: workflow-level input values, keyed by input name.
        nodes: per-node results, shaped
            ``{node_id: {"outputs": {...}, "params": {...}}}``.  ``outputs``
            holds values produced by the node; ``params`` holds the resolved
            parameters the node was executed with.
        env: environment variables, keyed by name.
        workdir: working directory for the workflow run — where relative input
            paths resolve.
        rundir: per-run artifact directory (``<output_dir>/runs/<run_id>``),
            the place to write outputs; empty when it could not be prepared.
    """

    inputs: Dict[str, Any] = field(default_factory=dict)
    nodes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    env: Dict[str, str] = field(default_factory=dict)
    workdir: str = ""
    rundir: str = ""


class ExpressionEngine:
    """Resolves ``$``-expressions against a :class:`WorkflowContext`.

    The engine holds no mutable state beyond the fixed dispatch tables built
    in :meth:`__init__`, so a single instance can be shared across workflow
    runs.  Resolution is strict: malformed paths, dunder components, unknown
    roots and unknown pipes all raise :class:`ExpressionError` with a message
    naming the offending component.
    """

    def __init__(self) -> None:
        """Build the fixed dispatch tables.

        ``_roots`` maps the five allowed context roots to their resolver
        methods; ``_pipes`` maps the three built-in transforms to their
        implementations.  Both are plain dicts of bound methods — there is
        no dynamic lookup, so any name outside these tables fails loudly
        instead of resolving against an arbitrary attribute.
        """
        self._roots: Dict[str, Any] = {
            "inputs": self._resolve_inputs,
            "nodes": self._resolve_nodes,
            "env": self._resolve_env,
            "workdir": self._resolve_workdir,
            "rundir": self._resolve_rundir,
        }
        self._pipes: Dict[str, Any] = {
            "basename": self._pipe_basename,
            "dirname": self._pipe_dirname,
            "default": self._pipe_default,
        }

    def resolve(self, template: Any, context: WorkflowContext) -> Any:
        """Resolve a single template to a concrete value.

        Args:
            template: the value to resolve.  Non-strings and strings without
                any ``$`` pass through unchanged; a string containing ``${``
                is interpolated; a string starting with ``$`` is treated as
                one whole-value expression (``$$`` escapes a leading ``$``).
            context: the values available for resolution.

        Returns:
            The resolved value (typed for a whole-value expression, text for
            an interpolated string).

        Raises:
            ExpressionError: on dunder access, unknown pipe, unresolvable
                reference, or a malformed template.
        """
        if not isinstance(template, str):
            return template
        if _INTERP_OPEN in template:
            return self._interpolate(template, context)
        if template.startswith("$$"):
            return template[1:]  # Escape: strip one $, return rest as literal
        if not template.startswith("$"):
            return template

        try:
            return self._resolve_expression(template[1:], context)
        except ExpressionError as exc:
            if " " in template:
                raise ExpressionError(
                    f"{exc} (a value starting with '$' must be one whole "
                    f"expression; to embed a value in a longer text use "
                    f"'${{...}}')"
                ) from None
            raise

    def _resolve_expression(self, expression: str, context: WorkflowContext) -> Any:
        """Resolve one dot-notation expression, applying any ``| pipe`` tail."""
        segments = expression.split(" | ")
        value = self._resolve_path(segments[0], context)
        for pipe in segments[1:]:
            value = self._apply_pipe(pipe, value)
        return value

    def _interpolate(self, template: str, context: WorkflowContext) -> Any:
        """Substitute every ``${...}`` in *template*.

        A template that is exactly one interpolation (nothing before or after
        it) returns the expression's own typed value; otherwise the values are
        rendered as text.  ``$${`` yields a literal ``${``.
        """
        if template.startswith(_INTERP_OPEN) and template.endswith("}"):
            closing = template.find("}", len(_INTERP_OPEN))
            if closing == len(template) - 1:
                return self._resolve_interpolation(
                    template[len(_INTERP_OPEN):closing], template, context
                )

        pieces: List[str] = []
        index = 0
        length = len(template)
        while index < length:
            if template.startswith(_ESCAPED_INTERP_OPEN, index):
                pieces.append(_INTERP_OPEN)
                index += len(_ESCAPED_INTERP_OPEN)
            elif template.startswith(_INTERP_OPEN, index):
                closing = template.find("}", index + len(_INTERP_OPEN))
                if closing == -1:
                    raise ExpressionError(
                        f"malformed interpolation: unterminated '${{' in "
                        f"{template!r}"
                    )
                value = self._resolve_interpolation(
                    template[index + len(_INTERP_OPEN):closing], template, context
                )
                pieces.append(_to_text(value))
                index = closing + 1
            else:
                pieces.append(template[index])
                index += 1
        return "".join(pieces)

    def _resolve_interpolation(
        self, body: str, template: str, context: WorkflowContext
    ) -> Any:
        """Resolve the body of one ``${...}`` occurrence."""
        body = body.strip()
        if not body:
            raise ExpressionError(
                f"malformed interpolation: empty expression in {template!r}"
            )
        try:
            return self._resolve_expression(body, context)
        except ExpressionError as exc:
            raise ExpressionError(
                f"{exc} (in interpolation '${{{body}}}' of {template!r}; "
                f"write '$${{' for a literal '${{')"
            ) from None

    def resolve_params(
        self, params: Dict[str, Any], context: WorkflowContext
    ) -> Dict[str, Any]:
        """Resolve every value in a params dict, recursing into nesting.

        Args:
            params: a parameter dict whose string values may be
                ``$``-expressions.  Not mutated.
            context: the values available for resolution.

        Returns:
            A new dict with the same keys; string values are resolved via
            :meth:`resolve`, nested dicts and lists are recursed into, and
            all other values pass through unchanged.
        """
        return {
            key: self._resolve_value(value, context)
            for key, value in params.items()
        }

    def _resolve_value(self, value: Any, context: WorkflowContext) -> Any:
        """Resolve one value, recursing into dicts and lists."""
        if isinstance(value, str):
            return self.resolve(value, context)
        if isinstance(value, dict):
            return {
                key: self._resolve_value(item, context)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._resolve_value(item, context) for item in value]
        return value

    def _resolve_path(self, path_part: str, context: WorkflowContext) -> Any:
        """Resolve a dot-notation path against the fixed root table.

        Dunder / private components (``^_``) are rejected before any
        traversal happens, so a crafted key can never reach an attribute.
        """
        if not path_part:
            raise ExpressionError("malformed expression: empty path")
        parts = path_part.split(".")
        for part in parts:
            if _DUNDER_RE.match(part):
                raise ExpressionError(f"dunder access rejected: {part}")
        resolver = self._roots.get(parts[0])
        if resolver is None:
            raise ExpressionError(
                f"unresolvable reference: {path_part} "
                f"(unknown root '{parts[0]}')"
            )
        return resolver(parts[1:], context, path_part)

    def _resolve_inputs(
        self, rest: List[str], context: WorkflowContext, path: str
    ) -> Any:
        """Resolve ``$inputs.<key>`` via dict access on ``context.inputs``."""
        if len(rest) != 1:
            raise ExpressionError(
                f"malformed expression: {path} (expected $inputs.<key>)"
            )
        key = rest[0]
        try:
            return context.inputs[key]
        except KeyError:
            raise ExpressionError(
                f"unresolvable reference: {path} (missing key: '{key}')"
            ) from None

    def _resolve_env(
        self, rest: List[str], context: WorkflowContext, path: str
    ) -> Any:
        """Resolve ``$env.<key>`` via dict access on ``context.env``."""
        if len(rest) != 1:
            raise ExpressionError(
                f"malformed expression: {path} (expected $env.<key>)"
            )
        key = rest[0]
        try:
            return context.env[key]
        except KeyError:
            raise ExpressionError(
                f"unresolvable reference: {path} (missing key: '{key}')"
            ) from None

    def _resolve_nodes(
        self, rest: List[str], context: WorkflowContext, path: str
    ) -> Any:
        """Resolve ``$nodes.<id>.outputs.<key>`` / ``$nodes.<id>.params.<key>``.

        Traverses ``context.nodes[node_id][section][key]`` — three dict
        accesses, no attribute lookup.  The section name is constrained to
        the fixed :data:`_NODE_SECTIONS` set before any access.
        """
        if len(rest) != 3:
            raise ExpressionError(
                f"malformed expression: {path} (expected "
                f"$nodes.<id>.outputs.<key> or $nodes.<id>.params.<key>)"
            )
        node_id, section, key = rest
        if section not in _NODE_SECTIONS:
            raise ExpressionError(
                f"malformed expression: {path} "
                f"(unknown node section '{section}')"
            )
        try:
            node = context.nodes[node_id]
        except KeyError:
            raise ExpressionError(
                f"unresolvable reference: {path} (missing node: '{node_id}')"
            ) from None
        if not isinstance(node, dict) or section not in node:
            raise ExpressionError(
                f"unresolvable reference: {path} (missing section "
                f"'{section}' on node '{node_id}')"
            )
        section_dict = node[section]
        if not isinstance(section_dict, dict):
            raise ExpressionError(
                f"unresolvable reference: {path} (section '{section}' "
                f"of node '{node_id}' is not a dict)"
            )
        try:
            return section_dict[key]
        except KeyError:
            raise ExpressionError(
                f"unresolvable reference: {path} (missing key: '{key}')"
            ) from None

    def _resolve_workdir(
        self, rest: List[str], context: WorkflowContext, path: str
    ) -> Any:
        """Resolve ``$workdir`` (no further keys allowed)."""
        if rest:
            raise ExpressionError(
                f"malformed expression: {path} "
                f"($workdir takes no further keys)"
            )
        return context.workdir

    def _resolve_rundir(
        self, rest: List[str], context: WorkflowContext, path: str
    ) -> Any:
        """Resolve ``$rundir`` — the per-run artifact directory."""
        if rest:
            raise ExpressionError(
                f"malformed expression: {path} "
                f"($rundir takes no further keys)"
            )
        return context.rundir

    def _apply_pipe(self, pipe: str, value: Any) -> Any:
        """Apply one pipe transform via the fixed pipe table."""
        name, _, arg = pipe.partition(":")
        if not name:
            raise ExpressionError("malformed expression: empty pipe")
        transform = self._pipes.get(name)
        if transform is None:
            raise ExpressionError(f"unknown pipe: {name}")
        return transform(value, arg)

    def _pipe_basename(self, value: Any, _arg: str) -> Any:
        """Return the final path component of ``value``."""
        if not isinstance(value, str):
            raise ExpressionError(
                f"pipe 'basename' requires a string value, "
                f"got {type(value).__name__}"
            )
        return os.path.basename(value)

    def _pipe_dirname(self, value: Any, _arg: str) -> Any:
        """Return the directory component of ``value``."""
        if not isinstance(value, str):
            raise ExpressionError(
                f"pipe 'dirname' requires a string value, "
                f"got {type(value).__name__}"
            )
        return os.path.dirname(value)

    def _pipe_default(self, value: Any, arg: str) -> Any:
        """Substitute ``arg`` (the literal after the colon) when ``value``
        is None or empty; otherwise keep ``value`` unchanged."""
        if value is None or value == "":
            return arg
        return value
