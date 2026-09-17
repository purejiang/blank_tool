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
        task_id: Optional task identifier for logging.
        run_id: Identifier of the enclosing workflow run — the key the
            :class:`~app.common.task_manager.TaskManager` registers and the
            key :meth:`cancelled` queries.  ``None`` outside a workflow run.
        run_dir: Per-run artifact directory (``<output_dir>/runs/<run_id>``);
            tools that persist engine-level files write here, never into
            ``work_dir`` (which may be a source tree or the template store).
            Empty string when it could not be prepared.
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
        current_node_path: Path of the currently executing node from the run
            root (``"a"`` at the top level, ``"sub/a"`` one level down).
            Child node ids are prefixed with it so nested events stay
            unambiguous.
        process_holder: Dict the command executors store their ``Popen`` in,
            so cancellation can terminate a running subprocess.
        cancel_check: Zero-argument callable returning True once the run has
            been cancelled; long-running tools poll it.
    """

    work_dir: str
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    run_dir: str = ""
    env: Dict[str, str] = field(default_factory=dict)
    stream_handler: Optional[Callable[[dict], None]] = None
    template_store: Optional[Any] = None
    engine: Optional[Any] = None
    nesting_depth: int = 0
    in_progress_templates: frozenset = field(default_factory=frozenset)
    current_node_path: Optional[str] = None
    process_holder: Optional[Dict[str, Any]] = None
    cancel_check: Optional[Callable[[], bool]] = None

    def cancelled(self) -> bool:
        """Return True when the enclosing run has been cancelled."""
        if self.cancel_check is None:
            return False
        try:
            return bool(self.cancel_check())
        except Exception:
            return False


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
