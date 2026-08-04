#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Builtin tool base class.

A ``BuiltinTool`` is an atomic workflow primitive: a named operation with a
declared port contract (``ports``) and an ``execute`` implementation.  The
workflow engine discovers tools by name, validates inputs against the port
set, then invokes ``execute`` with a :class:`ToolContext` carrying execution
environment details.

The concrete tools (file.read, file.write, ...) subclass this class and only
supply ``name``, ``description``, ``ports`` and an ``execute`` body — all
shared behavior (validation) lives here.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, Dict, List, Optional

from app.protocol import PortSet


@dataclass
class ToolContext:
    """Execution environment handed to a tool's ``execute`` method.

    Attributes:
        work_dir: Working directory for the tool execution.
        task_id: Optional task identifier for logging/cancellation.
        env: Environment variables for the tool execution.
        stream_handler: Optional callback receiving ``{"type": ..., ...}``
            dicts for streaming output (e.g. logcat lines, progress).
        template_store: Optional template store for resolving sub-workflow
            template names (used by ``workflow.run``).
        engine: Optional reference to the WorkflowEngine for inline child
            workflow execution (used by ``workflow.run``).
        nesting_depth: Current nesting depth in sub-workflow chains (0 for
            top-level, incrementing by 1 per nested ``workflow.run``).
        in_progress_templates: Immutable set of template names currently
            on the call stack — a template already in this set when a
            ``workflow.run`` node executes signals a recursion cycle.
        current_node_id: The id of the currently executing node (set by
            the engine before each node's execution).
        parent_workflow_id: The workflow_id of the parent workflow stream
            (if any), used to namespace nested workflow events.
    """

    work_dir: str
    task_id: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    stream_handler: Optional[Callable[[dict], None]] = None
    template_store: Optional[Any] = None
    engine: Optional[Any] = None
    nesting_depth: int = 0
    in_progress_templates: frozenset = field(default_factory=frozenset)
    current_node_id: Optional[str] = None
    parent_workflow_id: Optional[str] = None


class BuiltinTool(ABC):
    """Abstract base class for the built-in atomic workflow tools.

    Subclasses must set the class-level ``name``, ``description`` and
    ``ports`` attributes and implement :meth:`execute`.

    Attributes:
        name: Unique tool identifier (e.g. ``"file.read"``).
        description: Human-facing summary of what the tool does.
        ports: The declared input/output port contract used for validation.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    ports: ClassVar[PortSet]

    @abstractmethod
    def execute(self, inputs: dict, context: ToolContext) -> dict:
        """Run the tool against ``inputs`` under ``context``.

        Args:
            inputs: The provided input values keyed by input port name.
            context: Execution environment (work dir, env, streaming).

        Returns:
            dict: Output values keyed by output port name.
        """
        raise NotImplementedError

    def validate(self, inputs: dict) -> List[str]:
        """Validate ``inputs`` against the declared port set.

        Returns:
            list: Error strings for missing required inputs; empty when valid.
        """
        return self.ports.validate_inputs(inputs)
