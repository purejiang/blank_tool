#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Typed business exceptions for the backend.

Error codes live in :class:`app.protocol.ErrorCode` only — never re-hardcode
the numeric values here, so the JSON-RPC layer, the handlers and the
``@streaming`` error channel all speak the same codes.
"""

from app.protocol import ErrorCode


class ToolException(Exception):
    """Base exception for tool execution errors."""

    def __init__(self, message: str, code: int = ErrorCode.TOOL_ERROR):
        super().__init__(message)
        self.code = code
        self.message = message


class TimeoutException(ToolException):
    """Raised when tool execution exceeds the timeout."""

    def __init__(self, message: str = "Tool execution timed out"):
        super().__init__(message, code=ErrorCode.TIMEOUT)


class ToolNotFoundError(ToolException):
    """Raised when a requested tool is not found."""

    def __init__(self, tool_name: str):
        super().__init__(f"Tool not found: {tool_name}", code=ErrorCode.TOOL_NOT_FOUND)


class ValidationException(ToolException):
    """Raised when request parameters are missing or malformed.

    Kept distinct from ``ToolException`` so the renderer can tell "you passed
    bad input" (recoverable, user-facing) from "the tool blew up".
    """

    def __init__(self, message: str):
        super().__init__(message, code=ErrorCode.INVALID_PARAMS)


def error_payload(exc: BaseException) -> dict:
    """Build a streaming ``error`` event that preserves the typed error code.

    Handlers that catch their own exceptions must emit through this helper
    instead of hand-rolling ``{"type": "error", "payload": {"message": ...}}``,
    which silently dropped ``code`` and made every failure look identical to
    the renderer. Untyped exceptions degrade to ``INTERNAL_ERROR``.
    """
    code = getattr(exc, "code", ErrorCode.INTERNAL_ERROR)
    message = getattr(exc, "message", None) or str(exc)
    return {"type": "error", "payload": {"code": code, "message": message}}
