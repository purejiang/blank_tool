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
from typing import Callable, ClassVar, Dict, List, Optional

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
    """

    work_dir: str
    task_id: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    stream_handler: Optional[Callable[[dict], None]] = None


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
