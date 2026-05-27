"""
Contract tests for Tool handler API methods.
"""
import json


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
        request = {"id": 45, "method": "tool.version", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 45
        assert "result" in data
        assert data["finished"] is True
        result = data["result"]
        assert result["type"] == "success"
        assert "version" in result["payload"]


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
