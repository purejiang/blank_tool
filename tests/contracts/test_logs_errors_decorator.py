"""
Contract tests for logs_errors decorator (T12).

Verifies:
- Generic Exception → logged with prefix + re-raised
- ToolException → NOT logged, re-raised directly (controlled flow)
- ToolNotFoundError → NOT logged, re-raised directly (controlled flow)
- Composition with @streaming preserves is_streaming attribute
"""
import logging

import pytest

from app.common.decorators import logs_errors, streaming
from app.common.exceptions import ToolException, ToolNotFoundError


def test_logs_errors_logs_and_reraises_generic_exception(caplog):
    """Generic Exception must be logged at the configured level and re-raised."""

    @logs_errors("TestHandler")
    def handler(params, stream_handler):
        raise ValueError("boom")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValueError, match="boom"):
            handler({}, None)

    assert any(
        "TestHandler" in r.message and "boom" in r.message
        for r in caplog.records
    ), f"Expected 'TestHandler: boom' in logs, got: {[r.message for r in caplog.records]}"


def test_logs_errors_does_not_log_tool_exception(caplog):
    """ToolException (controlled flow) must be re-raised WITHOUT logging."""

    @logs_errors("TestHandler")
    def handler(params, stream_handler):
        raise ToolException("controlled error")

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ToolException, match="controlled error"):
            handler({}, None)

    assert not any(
        "TestHandler" in r.message for r in caplog.records
    ), f"Expected no log lines, got: {[r.message for r in caplog.records]}"


def test_logs_errors_tool_not_found_error_no_log(caplog):
    """ToolNotFoundError (controlled flow) must be re-raised WITHOUT logging."""

    @logs_errors("TestHandler")
    def handler(params, stream_handler):
        raise ToolNotFoundError("adb")

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ToolNotFoundError):
            handler({}, None)

    assert not any(
        "TestHandler" in r.message for r in caplog.records
    ), f"Expected no log lines, got: {[r.message for r in caplog.records]}"


def test_logs_errors_composes_with_streaming():
    """When composed with @streaming outermost, is_streaming must be preserved."""

    @streaming
    @logs_errors("TestHandler")
    def handler(params, stream_handler):
        return "ok"

    assert hasattr(handler, "is_streaming"), "is_streaming attribute missing"
    assert handler.is_streaming is True
    assert handler({}, None) == "ok"
