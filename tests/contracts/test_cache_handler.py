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
        assert "cache" in payload
        assert "output" in payload
        assert "tasks" in payload
        assert "total" in payload

    def test_cache_info_alias_works(self, api_handler):
        """cache.info should be the same as cache.get_info."""
        request = {"id": 52, "method": "cache.info", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 52
        result = data["result"]
        assert result["type"] == "success"
        payload = result["payload"]
        assert "cache" in payload
        assert "output" in payload
        assert "tasks" in payload


class TestCacheClear:
    def test_valid_request_returns_success(self, api_handler):
        request = {"id": 53, "method": "cache.clear", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 53
        result = data["result"]
        assert result["type"] == "success"
        payload = result["payload"]
        assert "path" in payload
        assert "size" in payload


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
        "cache.clear",
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
