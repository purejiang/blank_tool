"""
Contract tests for AAB handler API methods.
"""
import json
import time


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
        # Streaming handler returns stream_id immediately
        assert "stream_id" in data.get("result", {})
        assert data["finished"] is False

        # Wait for async stream thread to finish and capture error event
        for _ in range(50):
            if len(api_handler._captured) >= 2:
                break
            time.sleep(0.01)
        assert len(api_handler._captured) >= 2
        error_event = api_handler._captured[0]
        assert error_event["result"]["type"] == "error"

    def test_missing_device_id_returns_error(self, api_handler):
        request = {
            "id": 25,
            "method": "device.install_aab",
            "params": {"aab_path": "/nonexistent/test.aab"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        # Streaming handler returns stream_id immediately
        assert "stream_id" in data.get("result", {})
        assert data["finished"] is False

        # Wait for async stream thread to finish and capture error event
        for _ in range(50):
            if len(api_handler._captured) >= 2:
                break
            time.sleep(0.01)
        assert len(api_handler._captured) >= 2
        error_event = api_handler._captured[0]
        assert error_event["result"]["type"] == "error"
        assert "device" in error_event["result"]["payload"]["message"].lower()


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
