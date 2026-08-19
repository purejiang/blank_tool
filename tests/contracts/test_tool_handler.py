"""
Contract tests for Tool handler API methods.
"""
import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Descriptor helpers
# ---------------------------------------------------------------------------

def _make_tool_descriptor_dict(
    name: str,
    *,
    display_name: str = "",
    tool_type: str = "binary",
    tool_path: str = "/fake/path",
) -> dict:
    """Minimal valid tool descriptor dict."""
    return {
        "name": name,
        "display_name": display_name or f"{name}-display",
        "type": tool_type,
        "path": tool_path,
        "env_deps": [],
        "validate": {},
        "version": {},
        "inputs": [],
        "outputs": [],
    }


# ---------------------------------------------------------------------------
# Fixture for tool CRUD tests (real overlay dir)
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_tool_overlay(tmp_path: Path) -> str:
    """Create a temp registry overlay dir with tools/ subdirectory."""
    root = tmp_path / "registry"
    tools_dir = root / "tools"
    tools_dir.mkdir(parents=True)
    return str(root)


class TestGetTools:
    def test_no_params_returns_success(self, api_handler):
        request = {"id": 41, "method": "tool.get_tools", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 41
        assert "result" in data
        assert data["finished"] is True
        # Result should be a dict of tool_name -> tool_info
        result = data["result"]
        assert result["type"] == "success"

    def test_with_refresh_returns_success(self, api_handler):
        request = {
            "id": 42,
            "method": "tool.get_tools",
            "params": {"refresh": True},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 42
        result = data["result"]
        assert result["type"] == "success"

    def test_specific_tool_name_returns_success(self, api_handler):
        request = {
            "id": 43,
            "method": "tool.get_tools",
            "params": {"tool_name": "adb"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 43
        result = data["result"]
        assert result["type"] == "success"
        payload = result["payload"]
        assert payload["name"] == "adb"

    def test_missing_tool_returns_error(self, api_handler):
        request = {
            "id": 44,
            "method": "tool.get_tools",
            "params": {"tool_name": "nonexistent"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestToolVersion:
    def test_valid_request_returns_success(self, api_handler):
        request = {
            "id": 45,
            "method": "tool.version",
            "params": {"tool_name": "mock_tool"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 45
        assert "result" in data
        assert data["finished"] is True
        result = data["result"]
        assert result["type"] == "success"
        assert "version" in result["payload"]

    def test_missing_tool_name_returns_error(self, api_handler):
        request = {"id": 451, "method": "tool.version", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"

    def test_unknown_tool_name_returns_error(self, api_handler):
        request = {
            "id": 452,
            "method": "tool.version",
            "params": {"tool_name": "nonexistent"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestSetSearchMode:
    def test_valid_request_returns_success(self, api_handler):
        request = {
            "id": 46,
            "method": "tool.set_search_mode",
            "params": {"system_search": True},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 46
        result = data["result"]
        assert result["type"] == "success"
        assert result["payload"]["system_search"] is True


class TestResponseShape:
    METHODS = ["tool.get_tools", "tool.version", "tool.set_search_mode"]

    def test_all_methods_produce_valid_response_shape(self, api_handler):
        for method in self.METHODS:
            params = {"system_search": True} if method == "tool.set_search_mode" else {}
            request = {"id": 400, "method": method, "params": params}
            resp = api_handler.handle_request(request)
            data = json.loads(resp) if isinstance(resp, str) else resp
            assert "id" in data, f"{method}: missing id"
            assert "result" in data, f"{method}: missing result"
            assert "finished" in data, f"{method}: missing finished"


# ---------------------------------------------------------------------------
# tool.add / tool.delete (T15)
# ---------------------------------------------------------------------------

class TestToolAdd:
    def test_add_valid_descriptor_succeeds_and_file_lands_in_overlay(
        self, temp_tool_overlay, monkeypatch,
    ):
        """tool.add with a valid descriptor JSON writes the file to
        overlay tools/ and the tool appears in the registry immediately."""
        from app.tools.tool_manager import ToolRegistry

        registry = ToolRegistry(registry_overlay_dir=temp_tool_overlay)
        registry._initialized = True  # skip code-class scan

        monkeypatch.setattr(
            "app.handlers.tool_handler._get_registry",
            lambda: registry,
        )

        from app.handlers import tool_handler

        desc = _make_tool_descriptor_dict("my_tool", tool_path="/fake/my_tool")
        result = tool_handler.handle_tool_add({"descriptor": desc}, None)

        assert "error" not in result, f"tool.add should succeed, got: {result}"
        assert result.get("name") == "my_tool"

        # File written to overlay
        overlay_file = Path(temp_tool_overlay) / "tools" / "my_tool.json"
        assert overlay_file.exists(), f"Expected {overlay_file}"

        # Tool appears in registry listing
        names = registry.list_all()
        assert "my_tool" in names

    def test_add_invalid_descriptor_returns_error_no_file(
        self, temp_tool_overlay, monkeypatch,
    ):
        """Invalid descriptor JSON returns a clean error, no partial file."""
        from app.tools.tool_manager import ToolRegistry

        registry = ToolRegistry(registry_overlay_dir=temp_tool_overlay)
        registry._initialized = True

        monkeypatch.setattr(
            "app.handlers.tool_handler._get_registry",
            lambda: registry,
        )

        from app.handlers import tool_handler

        bad_desc = {"name": "bad_tool"}  # missing required fields
        result = tool_handler.handle_tool_add({"descriptor": bad_desc}, None)

        assert "error" in result, f"Expected error, got: {result}"

        # No file written
        overlay_file = Path(temp_tool_overlay) / "tools" / "bad_tool.json"
        assert not overlay_file.exists(), (
            "Invalid descriptor should not leave a partial file"
        )


class TestToolDelete:
    def test_delete_overlay_tool_removes_it(
        self, temp_tool_overlay, monkeypatch,
    ):
        """tool.delete removes ONLY the overlay copy."""
        from app.tools.tool_manager import ToolRegistry

        registry = ToolRegistry(registry_overlay_dir=temp_tool_overlay)
        registry._initialized = True

        monkeypatch.setattr(
            "app.handlers.tool_handler._get_registry",
            lambda: registry,
        )

        from app.handlers import tool_handler

        # Add first
        desc = _make_tool_descriptor_dict("to_delete", tool_path="/fake/del")
        tool_handler.handle_tool_add({"descriptor": desc}, None)

        assert "to_delete" in registry.list_all()

        # Delete
        result = tool_handler.handle_tool_delete({"name": "to_delete"}, None)
        assert "error" not in result, f"Delete should succeed, got: {result}"

        # No longer listed
        assert "to_delete" not in registry.list_all()

        # File removed
        overlay_file = Path(temp_tool_overlay) / "tools" / "to_delete.json"
        assert not overlay_file.exists()

    def test_delete_nonexistent_or_non_overlay_returns_error(
        self, temp_tool_overlay, monkeypatch,
    ):
        """Deleting a name with no overlay descriptor returns a clean error."""
        from app.tools.tool_manager import ToolRegistry

        registry = ToolRegistry(registry_overlay_dir=temp_tool_overlay)
        registry._initialized = True

        monkeypatch.setattr(
            "app.handlers.tool_handler._get_registry",
            lambda: registry,
        )

        from app.handlers import tool_handler

        # 'adb' has no overlay file — should be refused
        result = tool_handler.handle_tool_delete({"name": "adb"}, None)
        assert "error" in result, f"Expected error for non-overlay tool, got: {result}"
