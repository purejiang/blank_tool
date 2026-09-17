#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Typed business exceptions for the backend.
"""


class ToolException(Exception):
    """Base exception for tool execution errors."""

    def __init__(self, message: str, code: int = -32001):
        super().__init__(message)
        self.code = code
        self.message = message


class TimeoutException(ToolException):
    """Raised when tool execution exceeds the timeout."""

    def __init__(self, message: str = "Tool execution timed out"):
        super().__init__(message, code=-32000)


class ToolNotFoundError(ToolException):
    """Raised when a requested tool is not found."""

    def __init__(self, tool_name: str):
        super().__init__(f"Tool not found: {tool_name}", code=-32002)


class NonRetryableToolError(ToolException):
    """Raised when retrying the tool cannot possibly change the outcome.

    The workflow engine treats this like any other node failure EXCEPT that
    it never consumes the node's retry budget: the input/state the tool
    rejected will be identical on the next attempt (a failed assertion, a
    malformed parameter, a missing prerequisite), so retrying only wastes
    time and re-runs side effects.
    """


class WorkflowCancelled(Exception):
    """Control-flow signal: the current run was cancelled.

    Raised — not returned — so it can unwind through nested sub-workflow
    composition (``workflow.run`` / ``flow.foreach`` / ``flow.branch``)
    without being mistaken for a node failure.  The workflow engine catches
    it and turns it into ``WorkflowResult(cancelled=True)``: a cancelled run
    is neither a success nor a failure.
    """

    def __init__(self, message: str = "workflow cancelled"):
        super().__init__(message)
        self.message = message
