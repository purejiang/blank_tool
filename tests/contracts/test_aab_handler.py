"""
Contract tests for AAB handler API methods.
"""
import json


class TestAabSign:
    def test_missing_aab_path_returns_error(self, api_handler):
        request = {"id": 21, "method": "aab.sign", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 21
        result = data["result"]
        assert result["type"] == "error"

    def test_missing_keystore_returns_error(self, api_handler):
        request = {
            "id": 22,
            "method": "aab.sign",
            "params": {"aab_path": "/nonexistent/test.aab", "keystore": {}},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 22
        assert data["finished"] is True
        result = data["result"]
        assert result["type"] == "error"


class TestConvertAabToApks:
    def test_missing_aab_path_returns_error(self, api_handler):
        request = {"id": 23, "method": "device.convert_aab_to_apks", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestInstallAab:
    def test_missing_params_returns_error(self, api_handler):
        request = {"id": 24, "method": "device.install_aab", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"

    def test_missing_device_id_returns_error(self, api_handler):
        request = {
            "id": 25,
            "method": "device.install_aab",
            "params": {"aab_path": "/nonexistent/test.aab"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"
        assert "device" in result["payload"]["message"].lower()


class TestResponseShape:
    METHODS = ["aab.sign", "device.convert_aab_to_apks", "device.install_aab"]

    def test_all_methods_produce_valid_response_shape(self, api_handler):
        for method in self.METHODS:
            request = {"id": 200, "method": method, "params": {}}
            resp = api_handler.handle_request(request)
            data = json.loads(resp) if isinstance(resp, str) else resp
            assert "id" in data, f"{method}: missing id"
            assert "result" in data, f"{method}: missing result"
            assert "finished" in data, f"{method}: missing finished"
