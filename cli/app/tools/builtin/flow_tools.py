#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Builtin flow-control tools for the workflow engine.

Two atomic flow primitives (flow.assert, flow.log), each a ``BuiltinTool``
subclass declaring its port contract and a stdlib-only ``execute``
implementation:

- ``flow.assert`` is the validation gate: workflows assert intermediate state
  (e.g. "file exists after download") before proceeding.  A falsy ``condition``
  raises :class:`ToolException` so the workflow engine's failure handler can
  decide what to do (fail/skip/retry).  The exception is deliberately *not*
  caught here — the engine owns failure routing.
- ``flow.log`` writes a message through the standard :mod:`logging` framework
  (child loggers inherit the handlers configured by the ``main.py`` bootstrap)
  and, when a task context is present, also appends a line to the per-task log.

No conditional branching is implemented here — the ``condition`` field of the
workflow schema is reserved for a future feature, not consumed by these tools.
"""

import logging

from app.common.exceptions import ToolException
from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.tools.builtin.base import BuiltinTool, ToolContext
from app.utils.task_log_writer import append_task_log

logger = logging.getLogger(__name__)

_BOOLEAN = TypeAnnotation(BaseType.BOOLEAN)
_TEXT = TypeAnnotation(BaseType.TEXT)

#: Levels accepted by flow.log; anything else defaults to "info" (forgiving).
_VALID_LEVELS = frozenset({"debug", "info", "warning", "error", "critical"})

#: Default message used when a flow.assert failure carries no explicit one.
_DEFAULT_ASSERT_MESSAGE = "Assertion failed"


class FlowAssert(BuiltinTool):
    """Assert a condition is truthy; raise on failure.

    Acts as a validation gate between workflow steps.  When ``condition`` is
    falsy (``False``, ``None``, ``0``, ``""``, ``[]``, ...) a
    :class:`ToolException` is raised with the ``message`` so the workflow
    engine's ``on_failure`` handler can route the failure.  On success the
    tool returns ``{"passed": True}``.
    """

    name = "flow.assert"
    description = "Assert a condition is truthy; raises ToolException when falsy."

    ports = PortSet(
        inputs=[
            Port("condition", _BOOLEAN, required=True, description="Value to assert is truthy."),
            Port("message", _TEXT, required=False, description="Failure message (default 'Assertion failed')."),
        ],
        outputs=[
            Port("passed", _BOOLEAN, required=True, description="Always True when the assertion succeeds."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        condition = inputs.get("condition")
        if not condition:
            message = inputs.get("message") or _DEFAULT_ASSERT_MESSAGE
            raise ToolException(message)
        return {"passed": True}


class FlowLog(BuiltinTool):
    """Write a message to the application log and (optionally) the task log.

    The message is logged at the requested level via the standard
    :mod:`logging` framework.  When ``context.task_id`` is set, the same line
    is also appended to the per-task log through
    :func:`app.utils.task_log_writer.append_task_log`.  An unrecognized
    ``level`` falls back to ``"info"`` rather than raising.
    """

    name = "flow.log"
    description = "Write a message to the application log and the current task log."

    ports = PortSet(
        inputs=[
            Port("message", _TEXT, required=True, description="Message text to log."),
            Port("level", _TEXT, required=False, description="Log level (debug/info/warning/error/critical, default info)."),
        ],
        outputs=[
            Port("logged", _BOOLEAN, required=True, description="True when the message was logged."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        message = inputs["message"]
        level = inputs.get("level") or "info"
        if level not in _VALID_LEVELS:
            level = "info"
        level_num = getattr(logging, level.upper(), logging.INFO)
        logger.log(level_num, message)
        if context.task_id:
            append_task_log(context.task_id, f"[{level}] {message}")
        return {"logged": True}
