"""
Contract tests for Cache handler API methods.
"""
import json


class TestCacheInfo:
    def test_valid_request_returns_success(self, api_handler):
        request = {"id": 51, "method": "cache.get_info", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 51
        assert "result" in data
        assert data["finished"] is True
        result = data["result"]
        assert result["type"] == "success"
        payload = result["payload"]
        assert "tasks" in payload
        assert "output" in payload
        assert "logs" in payload
        assert "total" in payload
        assert {"path", "size", "files"} <= set(payload["tasks"])
        assert {"path", "size", "files"} <= set(payload["output"])
        assert {"path", "size", "files"} <= set(payload["logs"])
        assert {"size", "files"} <= set(payload["total"])

    def test_cache_info_alias_works(self, api_handler):
        """cache.info should be the same as cache.get_info."""
        request = {"id": 52, "method": "cache.info", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 52
        result = data["result"]
        assert result["type"] == "success"
        payload = result["payload"]
        assert "tasks" in payload
        assert "output" in payload
        assert "logs" in payload
        assert "total" in payload


# cache.clear alias retired — storage.clear/output.clear/tasks.clear/logs.clear cover all use cases; zero renderer callers


class TestOutputClear:
    def test_valid_request_returns_success(self, api_handler):
        request = {"id": 54, "method": "output.clear", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 54
        result = data["result"]
        assert result["type"] == "success"


class TestStorageClear:
    def test_clear_all_returns_success(self, api_handler):
        request = {
            "id": 55,
            "method": "storage.clear",
            "params": {"target": "all"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 55
        result = data["result"]
        assert result["type"] == "success"
        payload = result["payload"]
        assert payload["success"] is True
        assert "cleared_paths" in payload

    def test_clear_cache_only_returns_success(self, api_handler):
        request = {
            "id": 56,
            "method": "storage.clear",
            "params": {"target": "cache"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "success"


class TestResponseShape:
    METHODS = [
        "cache.get_info",
        "cache.info",
        "output.clear",
        "storage.clear",
    ]

    def test_all_methods_produce_valid_response_shape(self, api_handler):
        for method in self.METHODS:
            request = {"id": 500, "method": method, "params": {}}
            resp = api_handler.handle_request(request)
            data = json.loads(resp) if isinstance(resp, str) else resp
            assert "id" in data, f"{method}: missing id"
            assert "result" in data, f"{method}: missing result"
            assert "finished" in data, f"{method}: missing finished"
