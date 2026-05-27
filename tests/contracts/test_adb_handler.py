"""
Contract tests for ADB handler API methods.

Verify request -> response shape matches protocol types.
"""
import json


class TestAdbDevices:
    def test_valid_request_returns_success_shape(self, api_handler):
        request = {"id": 1, "method": "adb.devices", "params": {}}
        response = api_handler.handle_request(request)

        assert response is not None
        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 1
        assert "result" in data
        assert data["finished"] is True

    def test_response_has_result_field(self, api_handler):
        request = {"id": "test-1", "method": "adb.devices", "params": {}}
        response = api_handler.handle_request(request)
        data = json.loads(response) if isinstance(response, str) else response
        assert "result" in data
        assert isinstance(data["result"], dict)


class TestAdbStopLogcat:
    def test_missing_process_id_returns_error(self, api_handler):
        request = {"id": 2, "method": "adb.stop_logcat", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 2
        assert data["finished"] is True
        # Should be an error response
        result = data["result"]
        assert result["type"] == "error"
        assert "message" in result["payload"]


class TestAdbExportLogcat:
    def test_missing_params_returns_error(self, api_handler):
        request = {"id": 3, "method": "adb.export_logcat", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 3
        result = data["result"]
        assert result["type"] == "error"


class TestDeviceInfo:
    def test_missing_device_id_returns_error(self, api_handler):
        request = {"id": 4, "method": "device.info", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 4
        result = data["result"]
        assert result["type"] == "error"
        assert "device_id" in result["payload"]["message"].lower() or "device" in result["payload"]["message"].lower()


class TestDeviceListApps:
    def test_missing_device_id_returns_error(self, api_handler):
        request = {"id": 5, "method": "device.list_apps", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 5
        result = data["result"]
        assert result["type"] == "error"


class TestDeviceShell:
    def test_missing_params_returns_error(self, api_handler):
        request = {"id": 6, "method": "device.shell", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestDeviceReboot:
    def test_missing_device_id_returns_error(self, api_handler):
        request = {"id": 7, "method": "device.reboot", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestDeviceExportApk:
    def test_missing_params_returns_error(self, api_handler):
        request = {"id": 8, "method": "device.export_apk", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestUnknownMethod:
    def test_returns_method_not_found(self, api_handler):
        request = {"id": 99, "method": "nonexistent.method", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 99
        result = data["result"]
        assert result["type"] == "error"
        assert "not found" in result["payload"]["message"].lower()
        assert result["payload"]["code"] == -32601  # METHOD_NOT_FOUND
