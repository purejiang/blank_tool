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
            "installed", "ready", "lib_path", "python_mismatch", "ca_cert_exists",
        }
        assert isinstance(payload["installed"], bool)
        assert isinstance(payload["ready"], bool)
        assert isinstance(payload["lib_path"], str) and payload["lib_path"]
        assert payload["python_mismatch"] is None or isinstance(
            payload["python_mismatch"], str
        )
        assert isinstance(payload["ca_cert_exists"], bool)

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

    def test_probe_creates_no_directories(self, api_handler, monkeypatch, tmp_path):
        """The status probe is a pure read: it must not create the conf dir.

        A pytest run has no BT_RUNTIME_DIR, so a mkdir side effect here would
        litter the CWD with ``mitmproxy/conf/`` (review finding M2).
        """
        import os

        import app.automation.traffic as traffic
        monkeypatch.setattr(traffic, "get_runtime_dir", lambda: str(tmp_path))

        data = _call(api_handler, "automation.traffic_status", {}, 78)
        payload = data["result"]["payload"]
        # Probe works with the conf dir entirely absent.
        assert payload["ca_cert_exists"] is False
        # And it created nothing.
        assert not os.path.isdir(os.path.join(str(tmp_path), "mitmproxy", "conf"))


class TestAnyCaptureActive:
    def test_reflects_active_capture_map(self, monkeypatch):
        import app.automation.traffic as traffic

        monkeypatch.setattr(traffic, "_ACTIVE", {})
        assert traffic.any_capture_active() is False

        monkeypatch.setattr(traffic, "_ACTIVE", {"emulator-5554": {"port": 18888}})
        assert traffic.any_capture_active() is True


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


class TestInstallCa:
    """automation.install_ca — non-streaming wrapper around traffic.install_ca.

    The handler preflights the local cert through THIS module's ``ca_cert_path``
    alias (review M5): patching ``mod.ca_cert_path`` must reach the preflight —
    patching the traffic impl alone cannot.
    """

    def test_install_ca_missing_device_id_returns_error(self, api_handler):
        data = _call(api_handler, "automation.install_ca", {}, 81)
        assert data["id"] == 81
        assert data["finished"] is True
        assert data["result"]["type"] == "error"
        assert data["result"]["payload"]["message"] == "device_id is required"

    def test_install_ca_blank_device_id_returns_error(self, api_handler):
        data = _call(api_handler, "automation.install_ca", {"device_id": "  "}, 82)
        assert data["result"]["type"] == "error"
        assert data["result"]["payload"]["message"] == "device_id is required"

    def test_install_ca_missing_cert_file_returns_error(self, api_handler, monkeypatch, tmp_path):
        import app.handlers.automation_handler as mod

        monkeypatch.setattr(mod, "ca_cert_path", lambda: str(tmp_path / "nope.pem"))
        data = _call(
            api_handler, "automation.install_ca", {"device_id": "emulator-5554"}, 83
        )
        assert data["result"]["type"] == "error"
        message = data["result"]["payload"]["message"]
        assert "run one capture first" in message

    def test_install_ca_delegates_to_traffic_impl(self, api_handler, monkeypatch, tmp_path):
        import app.handlers.automation_handler as mod

        cert = tmp_path / "mitmproxy-ca-cert.pem"
        cert.write_bytes(b"-----BEGIN CERTIFICATE-----")
        monkeypatch.setattr(mod, "ca_cert_path", lambda: str(cert))

        captured = {}

        def fake_impl(device_id):
            captured["device_id"] = device_id
            return {"success": True, "already_installed": False}

        monkeypatch.setattr(mod, "install_ca_impl", fake_impl)

        data = _call(
            api_handler, "automation.install_ca", {"device_id": "emulator-5554"}, 84
        )
        assert captured["device_id"] == "emulator-5554"
        result = data["result"]
        assert result["type"] == "success"
        # Exact passthrough — the traffic impl's payload shape, verbatim.
        assert result["payload"] == {"success": True, "already_installed": False}

    def test_install_ca_ignores_unknown_extra_params(self, api_handler, monkeypatch, tmp_path):
        """malformed_input probe: unknown extras must not break the handler."""
        import app.handlers.automation_handler as mod

        cert = tmp_path / "mitmproxy-ca-cert.pem"
        cert.write_bytes(b"-----BEGIN CERTIFICATE-----")
        monkeypatch.setattr(mod, "ca_cert_path", lambda: str(cert))
        monkeypatch.setattr(
            mod, "install_ca_impl",
            lambda device_id: {"success": True, "already_installed": True},
        )

        data = _call(
            api_handler,
            "automation.install_ca",
            {"device_id": "emulator-5554", "unknown": 1, "foo": {"bar": 2}},
            85,
        )
        assert data["result"]["type"] == "success"


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
