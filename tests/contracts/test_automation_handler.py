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


class TestInstallMitmproxy:
    """automation.install_mitmproxy — streaming pip install + full degrade.

    Direct-call style (test_download_handler pattern): the ``@streaming``
    wrapper runs synchronously, so a plain events-lambda collects everything.
    All seams are module-level so monkeypatching never touches the real
    runtime dir or a real pip.
    """

    def test_install_mitmproxy_refuses_while_capture_active(self, monkeypatch):
        import app.handlers.automation_handler as mod

        events = []
        monkeypatch.setattr(mod, "any_capture_active", lambda: True)
        pip_calls = []
        monkeypatch.setattr(
            mod, "_pip_install",
            lambda lib, on_line: pip_calls.append(lib) or 0,
        )

        mod.install_mitmproxy({}, lambda e: events.append(e))

        assert events[0]["type"] == "error"
        # Message must tell the user to stop the running capture first.
        assert "请先停止运行中的抓包再安装" in events[0]["payload"]
        assert not any(e["type"] == "complete" for e in events)
        assert pip_calls == [], "no install may be attempted during a capture"

    def test_install_mitmproxy_errors_when_runtime_dir_missing(self, monkeypatch):
        import app.handlers.automation_handler as mod

        events = []
        monkeypatch.setattr(mod, "get_runtime_dir", lambda: "")
        monkeypatch.setattr(mod, "_pip_available", lambda: False)

        mod.install_mitmproxy({}, lambda e: events.append(e))

        assert any(e["type"] == "error" for e in events)
        assert not any(e["type"] == "complete" for e in events)

    def test_install_mitmproxy_pip_probe_failure_degrades_with_manual_command(
        self, monkeypatch, tmp_path
    ):
        import os
        import sys

        import app.handlers.automation_handler as mod

        events = []
        monkeypatch.setattr(mod, "get_runtime_dir", lambda: str(tmp_path))
        monkeypatch.setattr(mod, "_pip_available", lambda: False)

        mod.install_mitmproxy({}, lambda e: events.append(e))

        completes = [e for e in events if e["type"] == "complete"]
        assert len(completes) == 1
        payload = completes[0]["payload"]
        assert set(payload.keys()) == {
            "success", "degraded", "manual_command", "lib_path", "python_bin",
        }
        assert payload["success"] is False
        assert payload["degraded"] is True
        lib = os.path.join(str(tmp_path), "mitmproxy", "lib")
        expected = f'"{sys.executable}" -m pip install --target "{lib}" --upgrade mitmproxy'
        assert payload["manual_command"] == expected
        assert payload["lib_path"] == lib
        assert payload["python_bin"] == sys.executable

    def test_install_mitmproxy_pip_install_failure_degrades(self, monkeypatch, tmp_path):
        import os
        import sys

        import app.handlers.automation_handler as mod

        events = []
        monkeypatch.setattr(mod, "get_runtime_dir", lambda: str(tmp_path))
        monkeypatch.setattr(mod, "_pip_available", lambda: True)
        monkeypatch.setattr(mod, "_pip_install", lambda lib, on_line: 1)

        mod.install_mitmproxy({}, lambda e: events.append(e))

        completes = [e for e in events if e["type"] == "complete"]
        assert len(completes) == 1
        payload = completes[0]["payload"]
        assert payload["success"] is False
        assert payload["degraded"] is True
        assert set(payload.keys()) == {
            "success", "degraded", "manual_command", "lib_path", "python_bin",
        }
        lib = os.path.join(str(tmp_path), "mitmproxy", "lib")
        assert payload["manual_command"] == (
            f'"{sys.executable}" -m pip install --target "{lib}" --upgrade mitmproxy'
        )

    def test_install_mitmproxy_success_writes_marker_and_reports_status(
        self, monkeypatch, tmp_path
    ):
        import os
        import sys

        import app.handlers.automation_handler as mod

        events = []
        monkeypatch.setattr(mod, "get_runtime_dir", lambda: str(tmp_path))
        monkeypatch.setattr(mod, "_pip_available", lambda: True)

        pip_calls = {}

        def fake_install(lib, on_line):
            pip_calls["lib"] = lib
            on_line("Collecting mitmproxy")
            on_line("Successfully installed mitmproxy-10.4.2")
            return 0

        monkeypatch.setattr(mod, "_pip_install", fake_install)
        monkeypatch.setattr(mod, "traffic_status_impl", lambda: {
            "installed": True,
            "ready": True,
            "lib_path": os.path.join(str(tmp_path), "mitmproxy", "lib"),
            "python_mismatch": None,
            "ca_cert_exists": False,
        })

        mod.install_mitmproxy({}, lambda e: events.append(e))

        completes = [e for e in events if e["type"] == "complete"]
        assert len(completes) == 1
        payload = completes[0]["payload"]
        assert set(payload.keys()) == {
            "success", "installed", "ready", "lib_path",
            "python_mismatch", "ca_cert_exists",
        }
        assert payload["success"] is True
        assert payload["installed"] is True
        assert payload["ready"] is True

        marker = os.path.join(str(tmp_path), "mitmproxy", "PYTHON_MARKER")
        assert os.path.isfile(marker)
        with open(marker, "r", encoding="utf-8") as f:
            assert f.read() == f"{sys.version_info[0]}.{sys.version_info[1]}"

        assert pip_calls["lib"] == os.path.join(str(tmp_path), "mitmproxy", "lib")
        logs = [e for e in events if e["type"] == "log"]
        assert any("Successfully installed" in e["payload"] for e in logs)

    def test_install_mitmproxy_pip_probe_timeout_returns_false(self, monkeypatch):
        """hung_long_commands probe: a hanging/raising pip probe must yield
        False (degraded path) instead of hanging or crashing."""
        import subprocess

        import app.handlers.automation_handler as mod

        def raise_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="pip --version", timeout=30)

        monkeypatch.setattr(subprocess, "Popen", raise_timeout)
        assert mod._pip_available() is False

    def test_install_mitmproxy_overwrites_stale_marker(self, monkeypatch, tmp_path):
        """stale_state probe: a rerun after a prior (foreign) install rewrites
        the marker instead of leaving stale content behind."""
        import os
        import sys

        import app.handlers.automation_handler as mod

        marker = tmp_path / "mitmproxy" / "PYTHON_MARKER"
        marker.parent.mkdir(parents=True)
        marker.write_text("9.9-stale", encoding="utf-8")

        monkeypatch.setattr(mod, "get_runtime_dir", lambda: str(tmp_path))
        monkeypatch.setattr(mod, "_pip_available", lambda: True)
        monkeypatch.setattr(mod, "_pip_install", lambda lib, on_line: 0)
        monkeypatch.setattr(mod, "traffic_status_impl", lambda: {
            "installed": True, "ready": True, "lib_path": "x",
            "python_mismatch": None, "ca_cert_exists": False,
        })

        mod.install_mitmproxy({}, lambda e: None)

        assert marker.read_text(encoding="utf-8") == (
            f"{sys.version_info[0]}.{sys.version_info[1]}"
        )

    def test_install_mitmproxy_repeat_call_single_terminal_complete(
        self, monkeypatch, tmp_path
    ):
        """repeated_interruptions probe: two successive calls each produce
        exactly one terminal complete event — no double terminal."""
        import app.handlers.automation_handler as mod

        monkeypatch.setattr(mod, "get_runtime_dir", lambda: str(tmp_path))
        monkeypatch.setattr(mod, "_pip_available", lambda: False)

        events_one, events_two = [], []
        mod.install_mitmproxy({}, lambda e: events_one.append(e))
        mod.install_mitmproxy({}, lambda e: events_two.append(e))

        for events in (events_one, events_two):
            terminals = [e for e in events if e["type"] in ("complete", "error")]
            assert len(terminals) == 1
            assert terminals[0]["type"] == "complete"

    def test_install_mitmproxy_empty_and_extra_params_degrade_normally(
        self, monkeypatch, tmp_path
    ):
        """malformed_input probe: empty params, missing device_id and unknown
        extras are all ignored — the handler degrades normally, no crash."""
        import app.handlers.automation_handler as mod

        monkeypatch.setattr(mod, "get_runtime_dir", lambda: str(tmp_path))
        monkeypatch.setattr(mod, "_pip_available", lambda: False)

        for params in ({}, {"device_id": "emulator-5554"}, {
            "device_id": "emulator-5554", "apk_path": 123,
            "unknown": {"x": 1},
        }):
            events = []
            mod.install_mitmproxy(params, lambda e: events.append(e))
            terminals = [e for e in events if e["type"] in ("complete", "error")]
            assert len(terminals) == 1
            assert terminals[0]["type"] == "complete"
            assert terminals[0]["payload"]["degraded"] is True


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
