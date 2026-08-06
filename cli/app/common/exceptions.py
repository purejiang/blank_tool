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
