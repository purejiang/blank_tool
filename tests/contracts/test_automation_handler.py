"""
Contract tests for Automation handler read-only capability probes.

``automation.traffic_status`` (mitmproxy, PC side) and
``automation.ime_status`` (ADBKeyBoard, device side) back the settings
page's capability card and the automation page's preflight hints.
"""
import json

import pytest


def _call(api_handler, method, params, req_id):
    request = {"id": req_id, "method": method, "params": params}
    response = api_handler.handle_request(request)
    return json.loads(response) if isinstance(response, str) else response


class TestTrafficStatus:
    def test_returns_capability_report(self, api_handler):
        data = _call(api_handler, "automation.traffic_status", {}, 71)
        assert data["id"] == 71
        assert data["finished"] is True
        result = data["result"]
        assert result["type"] == "success"
        payload = result["payload"]
        # Exact contract the renderer's AutomationService types against.
        assert set(payload.keys()) == {
            "installed", "ready", "lib_path", "python_mismatch",
        }
        assert isinstance(payload["installed"], bool)
        assert isinstance(payload["ready"], bool)
        assert isinstance(payload["lib_path"], str) and payload["lib_path"]
        assert payload["python_mismatch"] is None or isinstance(
            payload["python_mismatch"], str
        )

    def test_ready_consistent_with_components(self, api_handler):
        """ready == installed AND no python mismatch (UI hints key off this)."""
        data = _call(api_handler, "automation.traffic_status", {}, 72)
        payload = data["result"]["payload"]
        assert payload["ready"] == (
            payload["installed"] and payload["python_mismatch"] is None
        )

    def test_ignores_params(self, api_handler):
        data = _call(api_handler, "automation.traffic_status", {"x": 1}, 73)
        assert data["result"]["type"] == "success"


class TestImeStatus:
    def test_missing_device_id_returns_error(self, api_handler):
        data = _call(api_handler, "automation.ime_status", {}, 74)
        assert data["id"] == 74
        assert data["finished"] is True
        assert data["result"]["type"] == "error"

    def test_blank_device_id_returns_error(self, api_handler):
        data = _call(api_handler, "automation.ime_status", {"device_id": "  "}, 75)
        assert data["result"]["type"] == "error"

    def test_probes_requested_device(self, api_handler, monkeypatch):
        captured = {}

        def fake_impl(device_id):
            captured["device_id"] = device_id
            return {
                "device_id": device_id,
                "package": "com.android.adbkeyboard/.AdbIME",
                "installed": True,
                "active": False,
            }

        # Patch the handler module's alias — API_MAP holds the wrapper, the
        # wrapper resolves the impl by module global at call time.
        import app.handlers.automation_handler as mod
        monkeypatch.setattr(mod, "ime_status_impl", fake_impl)

        data = _call(
            api_handler, "automation.ime_status", {"device_id": "emulator-5554"}, 76
        )
        assert captured["device_id"] == "emulator-5554"
        result = data["result"]
        assert result["type"] == "success"
        payload = result["payload"]
        assert set(payload.keys()) == {
            "device_id", "package", "installed", "active",
        }
        assert payload["device_id"] == "emulator-5554"
        assert payload["installed"] is True
        assert payload["active"] is False

    def test_impl_error_surfaces_as_error_response(self, api_handler, monkeypatch):
        import app.handlers.automation_handler as mod

        def boom(_device_id):
            raise RuntimeError("adb not found")

        monkeypatch.setattr(mod, "ime_status_impl", boom)
        data = _call(
            api_handler, "automation.ime_status", {"device_id": "emulator-5554"}, 77
        )
        assert data["result"]["type"] == "error"


class TestResponseShape:
    METHODS = [
        "automation.traffic_status",
        # ime_status needs a device; shape is covered by TestImeStatus.
    ]

    @pytest.mark.parametrize("method", METHODS)
    def test_all_methods_produce_valid_response_shape(self, api_handler, method):
        data = _call(api_handler, method, {}, 500)
        assert "id" in data, f"{method}: missing id"
        assert "result" in data, f"{method}: missing result"
        assert "finished" in data, f"{method}: missing finished"
