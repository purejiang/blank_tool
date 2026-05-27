"""
Shared fixtures for backend contract tests.

Mock strategy:
- Monkey-patch ``ToolManager.get_tool`` to return a MagicMock that satisfies
  ``is_valid`` and ``tool_path`` checks so handler functions can execute without
  real tools on disk.
- Provide an ``api_handler`` fixture that captures ``send_response`` output.
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch

# Ensure backend package is importable
backend_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


# ---------------------------------------------------------------------------
# Tool mocks
# ---------------------------------------------------------------------------

def _make_tool_mock(name: str = "mock_tool") -> MagicMock:
    """Return a MagicMock that looks like a valid, healthy tool."""
    tool = MagicMock()
    tool.name = name
    tool.is_valid = True
    tool.tool_path = f"/fake/path/{name}"
    tool.version = "1.0.0"
    return tool


def _make_tool_manager() -> MagicMock:
    """Return a MagicMock that acts like a ToolManager with a working get_tool."""
    mgr = MagicMock()
    mgr.get_tool.return_value = _make_tool_mock()

    # Also handle dictionary-style key errors gracefully
    def _get_tool_side_effect(tool_name):
        if tool_name in ("nonexistent", "missing"):
            return None
        return _make_tool_mock(tool_name)

    mgr.get_tool.side_effect = _get_tool_side_effect
    mgr.instance.return_value = mgr
    return mgr


@pytest.fixture
def mock_tool_manager() -> MagicMock:
    """A ToolManager mock that returns valid tools for known names."""
    mgr = _make_tool_manager()

    # Patch the instance() classmethod globally so ALL handlers see the mock
    with patch("app.tools.tool_manager.ToolManager.instance", return_value=mgr):
        yield mgr


# ---------------------------------------------------------------------------
# ApiHandler fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def api_handler(mock_tool_manager):
    """API handler with mocked tool manager and captured responses."""
    from app.api_handler import ApiHandler

    responses = []

    def capture_response(data: dict):
        responses.append(data)

    handler = ApiHandler(send_response=capture_response)
    # Attach helpers for test assertions
    handler._captured = responses  # type: ignore[attr-defined]
    return handler
