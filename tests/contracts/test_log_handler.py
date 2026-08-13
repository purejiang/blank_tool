"""
Contract tests for the Log handler (``logs.tail``).

The handler reads the last N lines of the current backend log file.
It MUST NOT accept a path parameter — it reads exclusively from the
configured log directory via ``Logger``.
"""
import os
import tempfile

import pytest

from app.handlers.log_handler import handle_tail


def test_tail_returns_lines():
    """A file with known content returns the expected tail lines."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    ) as f:
        for i in range(10):
            f.write(f"line {i}\n")
        tmp_path = f.name

    try:
        from unittest.mock import patch

        with patch("app.handlers.log_handler.Logger.get_current_log_file", return_value=tmp_path):
            result = handle_tail({"lines": 3}, None)

        assert result["lines"] == ["line 7", "line 8", "line 9"]
        assert result["truncated"] is True
        assert result["log_path"] == tmp_path
        assert result["process"] == "backend"
    finally:
        os.unlink(tmp_path)


def test_tail_truncated():
    """When file has more lines than requested, truncated is True."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    ) as f:
        for i in range(500):
            f.write(f"entry_{i:04d}\n")
        tmp_path = f.name

    try:
        from unittest.mock import patch

        with patch("app.handlers.log_handler.Logger.get_current_log_file", return_value=tmp_path):
            result = handle_tail({"lines": 200}, None)

        assert result["truncated"] is True
        assert len(result["lines"]) == 200
        assert result["lines"][0] == "entry_0300"
        assert result["lines"][-1] == "entry_0499"
    finally:
        os.unlink(tmp_path)


def test_tail_not_truncated():
    """When file has fewer lines than requested, truncated is False."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    ) as f:
        f.write("only line\n")
        tmp_path = f.name

    try:
        from unittest.mock import patch

        with patch("app.handlers.log_handler.Logger.get_current_log_file", return_value=tmp_path):
            result = handle_tail({"lines": 50}, None)

        assert result["truncated"] is False
        assert result["lines"] == ["only line"]
    finally:
        os.unlink(tmp_path)


def test_tail_missing_file():
    """When the current log file does not exist, return empty."""
    from unittest.mock import patch

    with patch("app.handlers.log_handler.Logger.get_current_log_file", return_value="/nonexistent/backend-2025-01-01.log"):
        result = handle_tail({"lines": 100}, None)

    assert result["lines"] == []
    assert result["truncated"] is False
    assert result["log_path"] == "/nonexistent/backend-2025-01-01.log"
    assert result["process"] == "backend"


def test_tail_none_current():
    """When get_current_log_file returns None, return empty."""
    from unittest.mock import patch

    with patch("app.handlers.log_handler.Logger.get_current_log_file", return_value=None):
        result = handle_tail({"lines": 100}, None)

    assert result["lines"] == []
    assert result["truncated"] is False
    assert result["log_path"] == ""
    assert result["process"] == "backend"


def test_tail_default_lines():
    """Without lines param, default to 200."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    ) as f:
        for i in range(10):
            f.write(f"line {i}\n")
        tmp_path = f.name

    try:
        from unittest.mock import patch

        with patch("app.handlers.log_handler.Logger.get_current_log_file", return_value=tmp_path):
            result = handle_tail({}, None)

        assert result["truncated"] is False
        assert len(result["lines"]) == 10
    finally:
        os.unlink(tmp_path)


def test_tail_invalid_lines_param():
    """Non-numeric lines param defaults to 200."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    ) as f:
        f.write("single line\n")
        tmp_path = f.name

    try:
        from unittest.mock import patch

        with patch("app.handlers.log_handler.Logger.get_current_log_file", return_value=tmp_path):
            result = handle_tail({"lines": "not_a_number"}, None)

        # Still works — defaults to 200
        assert result["lines"] == ["single line"]
    finally:
        os.unlink(tmp_path)


def test_tail_empty_file():
    """An empty log file returns empty lines."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    ) as f:
        # write nothing
        tmp_path = f.name

    try:
        from unittest.mock import patch

        with patch("app.handlers.log_handler.Logger.get_current_log_file", return_value=tmp_path):
            result = handle_tail({"lines": 50}, None)

        assert result["lines"] == []
        assert result["truncated"] is False
    finally:
        os.unlink(tmp_path)


def test_tail_lines_max_clamped():
    """lines param exceeding 1000 is clamped to 1000."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    ) as f:
        for i in range(1200):
            f.write(f"line_{i}\n")
        tmp_path = f.name

    try:
        from unittest.mock import patch

        with patch("app.handlers.log_handler.Logger.get_current_log_file", return_value=tmp_path):
            result = handle_tail({"lines": 5000}, None)

        # Clamped to 1000
        assert len(result["lines"]) == 1000
        assert result["truncated"] is True
    finally:
        os.unlink(tmp_path)


def test_api_map_key():
    """Verify the API_MAP contains logs.tail."""
    from app.handlers.log_handler import API_MAP

    assert "logs.tail" in API_MAP
    assert callable(API_MAP["logs.tail"])
