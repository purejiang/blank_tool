"""
Contract tests for Install handler API methods.
"""
import json


class TestInstallApk:
    def test_missing_apk_path_returns_error(self, api_handler):
        request = {"id": 31, "method": "device.install_apk", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 31
        result = data["result"]
        assert result["type"] == "error"

    def test_missing_device_id_returns_error(self, api_handler):
        request = {
            "id": 32,
            "method": "device.install_apk",
            "params": {"apk_path": "/nonexistent/test.apk"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestInstallApks:
    def test_missing_apks_path_returns_error(self, api_handler):
        request = {"id": 33, "method": "device.install_apks", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestResponseShape:
    METHODS = ["device.install_apk", "device.install_apks"]

    def test_all_methods_produce_valid_response_shape(self, api_handler):
        for method in self.METHODS:
            request = {"id": 300, "method": method, "params": {}}
            resp = api_handler.handle_request(request)
            data = json.loads(resp) if isinstance(resp, str) else resp
            assert "id" in data, f"{method}: missing id"
            assert "result" in data, f"{method}: missing result"
            assert "finished" in data, f"{method}: missing finished"
