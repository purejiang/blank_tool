"""
Contract tests for APK handler API methods.
"""
import json


class TestApkAnalyze:
    def test_missing_apk_path_returns_error(self, api_handler):
        request = {"id": 11, "method": "apk.analyze", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 11
        result = data["result"]
        assert result["type"] == "error"

    def test_nonexistent_apk_path_returns_error(self, api_handler):
        request = {
            "id": 12,
            "method": "apk.analyze",
            "params": {"apk_path": "/nonexistent/path/test.apk"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 12
        assert data["finished"] is True
        result = data["result"]
        assert result["type"] == "error"


class TestApkGetInfo:
    def test_missing_apk_path_returns_error(self, api_handler):
        request = {"id": 13, "method": "apk.getInfo", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestApkDecompile:
    def test_missing_file_path_returns_error(self, api_handler):
        request = {"id": 14, "method": "apk.decompile", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestApkRecompile:
    def test_missing_project_path_returns_error(self, api_handler):
        request = {"id": 15, "method": "apk.recompile", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestApkSign:
    def test_missing_apk_path_returns_error(self, api_handler):
        request = {"id": 16, "method": "apk.sign", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestApkGetProgress:
    def test_valid_request_returns_success(self, api_handler):
        request = {
            "id": 17,
            "method": "apk.get_progress",
            "params": {"task_id": "task-1", "output_dir": "/tmp"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 17
        assert "result" in data
        assert data["finished"] is True


class TestApkCancelTask:
    def test_valid_request_returns_response(self, api_handler):
        request = {
            "id": 18,
            "method": "apk.cancel_task",
            "params": {"task_id": "task-1"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 18
        assert "result" in data
        assert data["finished"] is True


class TestResponseShape:
    """Verify all APK handler methods produce protocol-compliant responses."""

    METHODS = [
        "apk.analyze",
        "apk.getInfo",
        "apk.decompile",
        "apk.recompile",
        "apk.sign",
        "apk.get_progress",
        "apk.cancel_task",
    ]

    def test_all_methods_produce_valid_response_shape(self, api_handler):
        """Each registered method must return id, result, finished."""
        for method in self.METHODS:
            request = {"id": 100, "method": method, "params": {}}
            resp = api_handler.handle_request(request)
            data = json.loads(resp) if isinstance(resp, str) else resp
            assert "id" in data, f"{method}: missing id"
            assert "result" in data, f"{method}: missing result"
            assert "finished" in data, f"{method}: missing finished"
