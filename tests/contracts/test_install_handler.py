"""
Contract tests for Install handler API methods.

``device.install_apk`` / ``device.install_apks`` are ``@streaming`` handlers:
``handle_request`` returns a stream handle immediately and the real outcome —
success or failure — arrives afterwards as a stream event. Parameter
validation therefore cannot be observed in the JSON-RPC reply; these tests
assert the actual contract, including that failures keep their error code.
"""
import json

from app.protocol import ErrorCode


def _init(handler, request):
    """Dispatch a streaming request and return its init response."""
    resp = handler.handle_request(request)
    return json.loads(resp) if isinstance(resp, str) else resp


def _first_error(events):
    errors = [e for e in events if e.get("type") == "error"]
    assert errors, f"expected an error event, got {events!r}"
    return errors[0]


class TestInstallApk:
    def test_missing_apk_path_returns_error(self, api_handler, stream_events):
        data = _init(api_handler, {"id": 31, "method": "device.install_apk", "params": {}})
        assert data["id"] == 31
        assert data["finished"] is False
        assert data["result"]["stream_id"]

        error = _first_error(stream_events())
        assert error["payload"]["code"] == ErrorCode.TOOL_ERROR
        assert "apk_path" in error["payload"]["message"]

    def test_missing_device_id_returns_error(self, api_handler, stream_events):
        data = _init(api_handler, {
            "id": 32,
            "method": "device.install_apk",
            "params": {"apk_path": "/nonexistent/test.apk"},
        })
        assert data["result"]["stream_id"]

        error = _first_error(stream_events())
        assert error["payload"]["code"] == ErrorCode.TOOL_ERROR
        assert "device_id" in error["payload"]["message"]


class TestInstallApks:
    def test_missing_apks_path_returns_error(self, api_handler, stream_events):
        data = _init(api_handler, {"id": 33, "method": "device.install_apks", "params": {}})
        assert data["result"]["stream_id"]

        error = _first_error(stream_events())
        assert error["payload"]["code"] == ErrorCode.TOOL_ERROR
        assert "apks_path" in error["payload"]["message"]


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
