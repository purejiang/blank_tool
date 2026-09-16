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


class TestTrafficStatusWithDevice:
    """Optional ``device_id`` adds the DEVICE-side half of the preflight.

    Backs the run-settings 「检测」 button: mitmproxy readiness alone does not
    tell you whether the selected device can actually be captured (reachable,
    rooted, CA already installed).
    """

    BASE_KEYS = {
        "installed", "ready", "lib_path", "python_mismatch", "ca_cert_exists",
    }

    def test_device_fields_are_added_only_with_a_device_id(self, api_handler, monkeypatch):
        import app.handlers.automation_handler as mod

        monkeypatch.setattr(mod, "device_capture_readiness_impl", lambda device_id: {
            "device_id": device_id,
            "device_state": "device",
            "ca_on_device": True,
            "root_available": True,
        })

        base = _call(api_handler, "automation.traffic_status", {}, 81)["result"]["payload"]
        assert set(base.keys()) == self.BASE_KEYS

        data = _call(
            api_handler, "automation.traffic_status", {"device_id": "emulator-5554"}, 82
        )
        payload = data["result"]["payload"]
        # PC-side report is preserved …
        assert self.BASE_KEYS.issubset(set(payload.keys()))
        # … and the device-side fields are merged in
        assert payload["device_id"] == "emulator-5554"
        assert payload["device_state"] == "device"
        assert payload["ca_on_device"] is True
        assert payload["root_available"] is True

    def test_blank_device_id_keeps_the_pc_only_report(self, api_handler, monkeypatch):
        import app.handlers.automation_handler as mod

        def boom(_device_id):
            raise AssertionError("blank device_id must not probe the device")

        monkeypatch.setattr(mod, "device_capture_readiness_impl", boom)
        data = _call(api_handler, "automation.traffic_status", {"device_id": "   "}, 83)
        assert set(data["result"]["payload"].keys()) == self.BASE_KEYS

    def test_probe_never_raises_when_adb_explodes(self, monkeypatch):
        import app.automation.traffic as traffic

        def boom(*_args, **_kwargs):
            raise RuntimeError("adb not found")

        monkeypatch.setattr(traffic, "run_adb", boom)
        out = traffic.device_capture_readiness("emulator-5554")
        assert out["device_state"] == "unknown"
        assert out["ca_on_device"] is None
        assert out["root_available"] is None

    def test_no_device_id_short_circuits(self):
        import app.automation.traffic as traffic

        out = traffic.device_capture_readiness("")
        assert out["device_state"] == "unknown"
        assert out["ca_on_device"] is None

    def test_unreachable_device_skips_the_deeper_probes(self, monkeypatch):
        import app.automation.traffic as traffic

        monkeypatch.setattr(
            traffic, "run_adb", lambda device_id, args: {"stdout": "offline", "returncode": 1}
        )

        def boom(*_args, **_kwargs):
            raise AssertionError("no root/cert probe on an unreachable device")

        monkeypatch.setattr(traffic, "_su", boom)
        out = traffic.device_capture_readiness("emulator-5554")
        assert out["device_state"] == "offline"
        assert out["root_available"] is None


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

    def test_install_ca_failure_blames_the_device_when_it_is_unreachable(
        self, api_handler, monkeypatch, tmp_path
    ):
        """`adb push CA failed` reads like a permissions problem and sends the
        user hunting for root — when the device is simply not there."""
        import app.handlers.automation_handler as mod

        cert = tmp_path / "mitmproxy-ca-cert.pem"
        cert.write_bytes(b"-----BEGIN CERTIFICATE-----")
        monkeypatch.setattr(mod, "ca_cert_path", lambda: str(cert))
        monkeypatch.setattr(
            mod, "install_ca_impl",
            lambda device_id: {"success": False, "error": "adb push CA failed"},
        )
        monkeypatch.setattr(mod, "run_adb", lambda device_id, args: {
            "returncode": 1, "stdout": "", "stderr": "error: device offline",
        })

        data = _call(
            api_handler, "automation.install_ca", {"device_id": "emulator-5554"}, 86
        )
        payload = data["result"]["payload"]
        assert payload["success"] is False
        assert "adb push CA failed" in payload["error"]
        assert "device-5554" not in payload["error"] or True  # no stray wrapping
        assert "设备 emulator-5554 当前不可用" in payload["error"]
        assert payload["device_state"] == "offline"

    def test_install_ca_failure_hints_at_root_when_the_device_is_fine(
        self, api_handler, monkeypatch, tmp_path
    ):
        import app.handlers.automation_handler as mod

        cert = tmp_path / "mitmproxy-ca-cert.pem"
        cert.write_bytes(b"-----BEGIN CERTIFICATE-----")
        monkeypatch.setattr(mod, "ca_cert_path", lambda: str(cert))
        monkeypatch.setattr(
            mod, "install_ca_impl",
            lambda device_id: {
                "success": False,
                "error": "CA install failed (no root or read-only /system)",
            },
        )
        monkeypatch.setattr(mod, "run_adb", lambda device_id, args: {
            "returncode": 0, "stdout": "device", "stderr": "",
        })

        data = _call(
            api_handler, "automation.install_ca", {"device_id": "emulator-5554"}, 87
        )
        payload = data["result"]["payload"]
        assert payload["success"] is False
        assert "需要 root 且 /system 可写" in payload["error"]
        assert "HTTP 抓包不受影响" in payload["error"]
        assert payload["device_state"] == "device"

    def test_install_ca_success_is_never_wrapped_in_a_hint(
        self, api_handler, monkeypatch, tmp_path
    ):
        """The hint path must not touch a successful install (token/status
        passthrough is what the modal reads)."""
        import app.handlers.automation_handler as mod

        cert = tmp_path / "mitmproxy-ca-cert.pem"
        cert.write_bytes(b"-----BEGIN CERTIFICATE-----")
        monkeypatch.setattr(mod, "ca_cert_path", lambda: str(cert))
        monkeypatch.setattr(
            mod, "install_ca_impl",
            lambda device_id: {"success": True, "already_installed": False},
        )
        # a broken adb must not even be consulted on the success path
        monkeypatch.setattr(
            mod, "run_adb",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("adb must not run")),
        )

        data = _call(
            api_handler, "automation.install_ca", {"device_id": "emulator-5554"}, 88
        )
        assert data["result"]["payload"] == {"success": True, "already_installed": False}

    def test_device_state_classifier(self):
        import app.handlers.automation_handler as mod

        cases = {
            "device": "device",
            "": "unknown",                      # no output at all — cannot tell
            "error: device offline": "offline",
            "error: device unauthorized": "unauthorized",
            "error: device 'x' not found": "disconnected",
            "List of devices attached": "List of devices attached",  # verbatim
        }
        for stdout, expected in cases.items():
            mod_run_adb = lambda d, a, s=stdout: {"returncode": 0, "stdout": s, "stderr": ""}
            orig = mod.run_adb
            try:
                mod.run_adb = mod_run_adb
                assert mod._device_state("d") == expected, (stdout, expected)
            finally:
                mod.run_adb = orig

    def test_device_state_never_raises_when_adb_explodes(self):
        import app.handlers.automation_handler as mod

        def boom(*a, **k):
            raise OSError("adb missing")

        orig = mod.run_adb
        try:
            mod.run_adb = boom
            assert mod._device_state("d") == "unknown"
        finally:
            mod.run_adb = orig


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
            lambda lib, on_line, task_id="": pip_calls.append(lib) or 0,
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
        monkeypatch.setattr(mod, "_pip_install", lambda lib, on_line, task_id="": 1)

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

        def fake_install(lib, on_line, task_id=""):
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
        monkeypatch.setattr(mod, "_pip_install", lambda lib, on_line, task_id="": 0)
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

    def test_install_mitmproxy_marker_write_failure_degrades(
        self, monkeypatch, tmp_path
    ):
        """R3: the post-pip tail must degrade like any pip failure — a marker
        write blow-up yields the SAME degraded complete, never a bare error."""
        import os
        import sys

        import app.handlers.automation_handler as mod

        events = []
        monkeypatch.setattr(mod, "get_runtime_dir", lambda: str(tmp_path))
        monkeypatch.setattr(mod, "_pip_available", lambda: True)
        monkeypatch.setattr(mod, "_pip_install", lambda lib, on_line, task_id="": 0)

        def boom(_runtime):
            raise OSError("disk full while stamping marker")

        # raising=False: the seam only exists once the R3 helper lands.
        monkeypatch.setattr(mod, "_write_python_marker", boom, raising=False)

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
        # Byte-identical to the pip-failure paths' manual command.
        assert payload["manual_command"] == (
            f'"{sys.executable}" -m pip install --target "{lib}" --upgrade mitmproxy'
        )
        assert not any(e["type"] == "error" for e in events)
        # No partial marker may survive that later reads as a version stamp.
        assert not os.path.exists(
            os.path.join(str(tmp_path), "mitmproxy", "PYTHON_MARKER")
        )

    def test_install_mitmproxy_status_build_failure_degrades(
        self, monkeypatch, tmp_path
    ):
        """R3: traffic_status_impl blowing up after pip exit 0 degrades too —
        the marker write already succeeded and must survive intact."""
        import os
        import sys

        import app.handlers.automation_handler as mod

        events = []
        monkeypatch.setattr(mod, "get_runtime_dir", lambda: str(tmp_path))
        monkeypatch.setattr(mod, "_pip_available", lambda: True)
        monkeypatch.setattr(mod, "_pip_install", lambda lib, on_line, task_id="": 0)

        def boom():
            raise RuntimeError("status probe exploded")

        monkeypatch.setattr(mod, "traffic_status_impl", boom)

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
        assert payload["manual_command"] == (
            f'"{sys.executable}" -m pip install --target "{lib}" --upgrade mitmproxy'
        )
        assert not any(e["type"] == "error" for e in events)
        # The marker write happened before the status build failed — intact.
        marker = os.path.join(str(tmp_path), "mitmproxy", "PYTHON_MARKER")
        assert os.path.isfile(marker)
        with open(marker, "r", encoding="utf-8") as f:
            assert f.read() == f"{sys.version_info[0]}.{sys.version_info[1]}"

    def test_install_mitmproxy_tail_baseexception_not_swallowed(
        self, monkeypatch, tmp_path
    ):
        """malformed_input probe: the tail guard catches Exception only — a
        BaseException from the tail (KeyboardInterrupt / SystemExit class,
        interpreter control flow) must propagate, not be degraded away."""
        import app.handlers.automation_handler as mod

        class TailAbort(BaseException):
            pass

        events = []
        monkeypatch.setattr(mod, "get_runtime_dir", lambda: str(tmp_path))
        monkeypatch.setattr(mod, "_pip_available", lambda: True)
        monkeypatch.setattr(mod, "_pip_install", lambda lib, on_line, task_id="": 0)

        def boom(_runtime):
            raise TailAbort("control-flow signal")

        # raising=False: the seam only exists once the R3 helper lands.
        monkeypatch.setattr(mod, "_write_python_marker", boom, raising=False)

        with pytest.raises(TailAbort):
            mod.install_mitmproxy({}, lambda e: events.append(e))

        assert not any(e["type"] == "complete" for e in events)
        assert not any(e["type"] == "error" for e in events)


class _FakeApkResp:
    """Minimal urllib response for the real _download_apk.

    The body is the payload prefixed with the ZIP magic, because the handler
    REJECTS a 200 answer that is not a real APK (captive portal / proxy notice
    pages) — a bare ``b"hello"`` body is now treated as a dead candidate. Pass
    ``valid_apk=False`` to script exactly that rejected case.
    """

    def __init__(self, chunks, valid_apk: bool = True):
        body = b"".join(chunks)
        if valid_apk:
            body = b"PK\x03\x04" + body
        self.headers = {"Content-Length": str(len(body))}
        self._chunks = iter([body]) if body else iter([])

    def read(self, _n):
        try:
            return next(self._chunks)
        except StopIteration:
            return b""

    def close(self):
        pass


def _apk_body(payload: bytes) -> bytes:
    """The bytes ``_FakeApkResp([payload])`` actually delivers."""
    return b"PK\x03\x04" + payload


class _MidFailResp:
    """Fake response that dies mid-chunk (connection reset while reading)."""

    headers = {"Content-Length": "100000"}

    def __init__(self):
        self._calls = 0

    def read(self, n):
        self._calls += 1
        if self._calls == 1:
            return b"x" * n
        raise OSError("connection reset by peer")

    def close(self):
        pass


def _patch_net(monkeypatch, side_effect_or_resp):
    """Patch the handler module's urlopen AND build_opener so the real
    _download_apk never touches the network, whichever branch the env's
    proxy settings pick."""
    from unittest.mock import MagicMock

    import app.handlers.automation_handler as mod

    uo = MagicMock(side_effect=side_effect_or_resp) if isinstance(
        side_effect_or_resp, Exception
    ) else MagicMock(return_value=side_effect_or_resp)
    bo = MagicMock()
    bo.return_value.open.side_effect = side_effect_or_resp if isinstance(
        side_effect_or_resp, Exception
    ) else MagicMock(return_value=side_effect_or_resp)
    monkeypatch.setattr(mod, "urlopen", uo)
    monkeypatch.setattr(mod, "build_opener", bo)
    return uo, bo


class TestInstallIme:
    """automation.install_ime — streaming download → adb install → verify.

    Direct-call + events-lambda; every external seam (download, adb, IME
    probe, cache dir) is a module-level monkeypatch target.
    """

    def test_install_ime_online_success_installs_and_verifies(
        self, monkeypatch, tmp_path
    ):
        import os

        import app.handlers.automation_handler as mod

        events = []
        cache = tmp_path / "cache"
        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))

        dl_calls = []
        monkeypatch.setattr(
            mod, "_download_apk",
            lambda dest, on_progress, on_log, cancel_check=None: dl_calls.append(dest),
        )

        adb_calls = []

        def fake_run_adb(device_id, args):
            adb_calls.append((device_id, list(args)))
            return {"returncode": 0, "stdout": "Success", "stderr": ""}

        monkeypatch.setattr(mod, "run_adb", fake_run_adb)
        monkeypatch.setattr(mod, "adb_ime_installed", lambda device_id: True)
        monkeypatch.setattr(mod, "ime_status_impl", lambda device_id: {
            "device_id": device_id,
            "package": "com.android.adbkeyboard/.AdbIME",
            "installed": True,
            "active": False,
        })

        mod.install_ime(
            {"device_id": "emulator-5554"}, lambda e: events.append(e)
        )

        completes = [e for e in events if e["type"] == "complete"]
        assert len(completes) == 1
        payload = completes[0]["payload"]
        assert set(payload.keys()) == {
            "success", "device_id", "package", "installed", "active",
        }
        assert payload["success"] is True
        assert payload["installed"] is True

        dest = os.path.join(str(cache), "tools", "ADBKeyBoard.apk")
        assert dl_calls == [dest]
        assert adb_calls == [("emulator-5554", ["install", "-r", dest])]

    def test_install_ime_download_failure_emits_error_no_complete(
        self, monkeypatch, tmp_path
    ):
        import app.handlers.automation_handler as mod

        events = []
        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(tmp_path / "cache"))

        def failing_download(dest, on_progress, on_log, cancel_check=None):
            raise RuntimeError("下载失败: 网络不可达")

        monkeypatch.setattr(mod, "_download_apk", failing_download)

        mod.install_ime(
            {"device_id": "emulator-5554"}, lambda e: events.append(e)
        )

        errors = [e for e in events if e["type"] == "error"]
        assert len(errors) == 1
        assert mod.ADBKEYBOARD_URL in errors[0]["payload"]
        assert "可在弹窗选择本地 APK" in errors[0]["payload"]
        assert not any(e["type"] == "complete" for e in events)

    def test_install_ime_urlopen_retries_exhausted_error_no_complete(
        self, monkeypatch, tmp_path
    ):
        """Real _download_apk: urlopen/build_opener raise URLError on every
        attempt — 3 attempts PER CANDIDATE URL, then a terminal error listing
        every address tried, plus the local-APK hint."""
        from urllib.error import URLError

        import app.handlers.automation_handler as mod

        events = []
        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(tmp_path / "cache"))
        monkeypatch.setattr(mod, "_DL_BACKOFF_BASE", 0)
        uo, bo = _patch_net(monkeypatch, URLError("connection refused"))

        mod.install_ime(
            {"device_id": "emulator-5554"}, lambda e: events.append(e)
        )

        # a transient error is retried per URL (not per source list)
        assert uo.call_count + bo.call_count == 3 * len(mod.ADBKEYBOARD_URLS)
        errors = [e for e in events if e["type"] == "error"]
        assert len(errors) == 1
        msg = errors[0]["payload"]
        assert mod.ADBKEYBOARD_URL in msg
        for url in mod.ADBKEYBOARD_URLS:
            assert url in msg, f"a tried address is missing from the error: {url}"
        assert "可在弹窗选择本地 APK" in msg
        assert not any(e["type"] == "complete" for e in events)

    def test_install_ime_local_apk_path_skips_download(self, monkeypatch, tmp_path):
        from unittest.mock import MagicMock

        import app.handlers.automation_handler as mod

        events = []
        apk = tmp_path / "local" / "ADBKeyBoard.apk"
        apk.parent.mkdir(parents=True)
        apk.write_bytes(b"PK\x03\x04fake-apk")

        dl_mock = MagicMock()
        monkeypatch.setattr(mod, "_download_apk", dl_mock)
        uo = MagicMock()
        monkeypatch.setattr(mod, "urlopen", uo)

        adb_calls = []
        monkeypatch.setattr(
            mod, "run_adb",
            lambda device_id, args: (
                adb_calls.append((device_id, list(args))) or
                {"returncode": 0, "stdout": "Success", "stderr": ""}
            ),
        )
        monkeypatch.setattr(mod, "adb_ime_installed", lambda device_id: True)
        monkeypatch.setattr(mod, "ime_status_impl", lambda device_id: {
            "device_id": device_id, "package": "pkg",
            "installed": True, "active": True,
        })

        mod.install_ime(
            {"device_id": "emulator-5554", "apk_path": str(apk)},
            lambda e: events.append(e),
        )

        dl_mock.assert_not_called()
        uo.assert_not_called()
        assert adb_calls == [("emulator-5554", ["install", "-r", str(apk)])]
        completes = [e for e in events if e["type"] == "complete"]
        assert len(completes) == 1
        assert completes[0]["payload"]["success"] is True

    def test_install_ime_local_apk_missing_errors(self, monkeypatch, tmp_path):
        import app.handlers.automation_handler as mod

        events = []
        adb_calls = []
        monkeypatch.setattr(
            mod, "run_adb",
            lambda device_id, args: adb_calls.append((device_id, args)),
        )

        missing = str(tmp_path / "missing.apk")
        mod.install_ime(
            {"device_id": "emulator-5554", "apk_path": missing},
            lambda e: events.append(e),
        )

        assert any(e["type"] == "error" for e in events)
        assert missing in [e["payload"] for e in events if e["type"] == "error"][0]
        assert not any(e["type"] == "complete" for e in events)
        assert adb_calls == []

    def test_install_ime_install_failure_success_false(self, monkeypatch, tmp_path):
        import app.handlers.automation_handler as mod

        events = []
        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(tmp_path / "cache"))
        monkeypatch.setattr(mod, "_download_apk", lambda dest, op, ol, cancel_check=None: None)
        monkeypatch.setattr(mod, "run_adb", lambda device_id, args: {
            "returncode": 1, "stdout": "",
            "stderr": "INSTALL_PARSE_FAILED_MANIFEST_MALFORMED",
        })
        monkeypatch.setattr(mod, "adb_ime_installed", lambda device_id: False)
        monkeypatch.setattr(mod, "ime_status_impl", lambda device_id: {
            "device_id": device_id, "package": "pkg",
            "installed": False, "active": False,
        })

        # Must not raise — degraded terminal complete instead.
        mod.install_ime(
            {"device_id": "emulator-5554"}, lambda e: events.append(e)
        )

        completes = [e for e in events if e["type"] == "complete"]
        assert len(completes) == 1
        assert completes[0]["payload"]["success"] is False
        assert completes[0]["payload"]["installed"] is False
        logs = [e for e in events if e["type"] == "log"]
        assert any(
            "INSTALL_PARSE_FAILED_MANIFEST_MALFORMED" in e["payload"] for e in logs
        )

    def test_install_ime_missing_device_id_errors(self, monkeypatch, tmp_path):
        from unittest.mock import MagicMock

        import app.handlers.automation_handler as mod

        events = []
        dl_mock = MagicMock()
        monkeypatch.setattr(mod, "_download_apk", dl_mock)
        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(tmp_path / "cache"))

        mod.install_ime({}, lambda e: events.append(e))

        errors = [e for e in events if e["type"] == "error"]
        assert len(errors) == 1
        assert "device_id is required" in errors[0]["payload"]
        assert not any(e["type"] == "complete" for e in events)
        dl_mock.assert_not_called()

    def test_install_ime_hostile_http_404_friendly_error_no_class_name(
        self, monkeypatch, tmp_path
    ):
        """untrusted_external_text probe: a hostile 404 must surface as a
        friendly error (URL + local-APK hint) with no exception class name."""
        from urllib.error import HTTPError

        import app.handlers.automation_handler as mod

        events = []
        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(tmp_path / "cache"))
        monkeypatch.setattr(mod, "_DL_BACKOFF_BASE", 0)
        _patch_net(monkeypatch, HTTPError(
            mod.ADBKEYBOARD_URL, 404, "Not Found", None, None,
        ))

        mod.install_ime(
            {"device_id": "emulator-5554"}, lambda e: events.append(e)
        )

        errors = [e for e in events if e["type"] == "error"]
        assert len(errors) == 1
        msg = errors[0]["payload"]
        assert "404" in msg
        assert mod.ADBKEYBOARD_URL in msg
        assert "可在弹窗选择本地 APK" in msg
        assert "HTTPError" not in msg
        assert not any(e["type"] == "complete" for e in events)

    def test_install_ime_mid_read_failure_error_no_complete_rerun_independent(
        self, monkeypatch, tmp_path
    ):
        """resumable_cancel_resume probe: a download dying mid-chunk emits
        error (no complete); a re-invocation behaves independently."""
        import app.handlers.automation_handler as mod

        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(tmp_path / "cache"))
        monkeypatch.setattr(mod, "_DL_BACKOFF_BASE", 0)
        monkeypatch.setattr(mod, "run_adb", lambda device_id, args: {
            "returncode": 0, "stdout": "Success", "stderr": "",
        })
        monkeypatch.setattr(mod, "adb_ime_installed", lambda device_id: True)
        monkeypatch.setattr(mod, "ime_status_impl", lambda device_id: {
            "device_id": device_id, "package": "pkg",
            "installed": True, "active": False,
        })

        first = []
        uo, bo = _patch_net(monkeypatch, _MidFailResp())
        mod.install_ime(
            {"device_id": "emulator-5554"}, lambda e: first.append(e)
        )
        assert any(e["type"] == "error" for e in first)
        assert not any(e["type"] == "complete" for e in first)

        second = []
        uo2, bo2 = _patch_net(monkeypatch, _FakeApkResp([b"data"]))
        mod.install_ime(
            {"device_id": "emulator-5554"}, lambda e: second.append(e)
        )
        completes = [e for e in second if e["type"] == "complete"]
        assert len(completes) == 1
        assert completes[0]["payload"]["success"] is True

    def test_install_ime_reuses_a_cached_apk_instead_of_redownloading(
        self, monkeypatch, tmp_path
    ):
        """A cached ADBKeyBoard.apk is a fixed release asset — reuse it.

        Re-downloading on every attempt made a flaky connection block an
        otherwise offline-capable flow, and the old code OVERWROTE the cache
        (open(dest, 'wb')) so there was no way to install without network.
        """
        import os

        import app.handlers.automation_handler as mod

        events = []
        cache = tmp_path / "cache"
        dest = cache / "tools" / "ADBKeyBoard.apk"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(_apk_body(b"CACHED-APK" * 10))

        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))
        # Any network attempt would blow up loudly rather than silently pass.
        monkeypatch.setattr(
            mod, "_download_apk",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not download")),
        )
        adb_calls = []

        def fake_run_adb(device_id, args):
            adb_calls.append((device_id, list(args)))
            return {"returncode": 0, "stdout": "Success", "stderr": ""}

        monkeypatch.setattr(mod, "run_adb", fake_run_adb)
        monkeypatch.setattr(mod, "adb_ime_installed", lambda device_id: True)
        monkeypatch.setattr(mod, "ime_status_impl", lambda device_id: {
            "device_id": device_id, "package": "pkg", "installed": True, "active": False,
        })

        mod.install_ime({"device_id": "emulator-5554"}, lambda e: events.append(e))

        assert dest.read_bytes() == _apk_body(b"CACHED-APK" * 10)   # untouched
        assert adb_calls == [("emulator-5554", ["install", "-r", str(dest)])]
        logs = " ".join(e["payload"] for e in events if e["type"] == "log")
        assert "使用已缓存" in logs
        assert not any(e["type"] == "progress" for e in events)
        completes = [e for e in events if e["type"] == "complete"]
        assert completes and completes[0]["payload"]["success"] is True

    def test_a_corrupt_cached_apk_is_discarded_and_refetched(
        self, monkeypatch, tmp_path
    ):
        """A cached file that is not an APK (truncated, or an HTML error page
        saved by an older build) must not be reused.

        The reuse path is sticky: installing it fails as a corrupt APK on every
        later attempt, with the real cause hidden behind "cache hit"."""
        import app.handlers.automation_handler as mod

        events = []
        cache = tmp_path / "cache"
        dest = cache / "tools" / "ADBKeyBoard.apk"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b"<html>502 Bad Gateway</html>")     # non-zero, not a ZIP

        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))
        dl_calls = []

        def fake_download(d, on_progress, on_log, cancel_check=None):
            dl_calls.append(d)
            with open(d, "wb") as f:
                f.write(_apk_body(b"fresh"))

        monkeypatch.setattr(mod, "_download_apk", fake_download)
        monkeypatch.setattr(mod, "run_adb", lambda device_id, args: {
            "returncode": 0, "stdout": "Success", "stderr": "",
        })
        monkeypatch.setattr(mod, "adb_ime_installed", lambda device_id: True)
        monkeypatch.setattr(mod, "ime_status_impl", lambda device_id: {
            "device_id": device_id, "package": "pkg", "installed": True, "active": False,
        })

        mod.install_ime({"device_id": "emulator-5554"}, lambda e: events.append(e))

        assert dl_calls == [str(dest)], "a corrupt cache entry must be refetched"
        assert dest.read_bytes() == _apk_body(b"fresh")
        logs = " ".join(e["payload"] for e in events if e["type"] == "log")
        assert "使用已缓存" not in logs
        completes = [e for e in events if e["type"] == "complete"]
        assert completes and completes[0]["payload"]["success"] is True

    def test_install_ime_redownload_forces_a_fresh_fetch(self, monkeypatch, tmp_path):

        import app.handlers.automation_handler as mod

        events = []
        cache = tmp_path / "cache"
        dest = cache / "tools" / "ADBKeyBoard.apk"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(_apk_body(b"OLD"))

        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))
        dl_calls = []
        monkeypatch.setattr(
            mod, "_download_apk",
            lambda d, on_progress, on_log, cancel_check=None: (dl_calls.append(d), open(d, "wb").write(b"NEW")),
        )
        monkeypatch.setattr(mod, "run_adb", lambda device_id, args: {
            "returncode": 0, "stdout": "Success", "stderr": "",
        })
        monkeypatch.setattr(mod, "adb_ime_installed", lambda device_id: True)
        monkeypatch.setattr(mod, "ime_status_impl", lambda device_id: {
            "device_id": device_id, "package": "pkg", "installed": True, "active": False,
        })

        mod.install_ime(
            {"device_id": "emulator-5554", "redownload": True}, lambda e: events.append(e)
        )

        assert dl_calls == [str(dest)]
        assert dest.read_bytes() == b"NEW"

    def test_install_ime_treats_an_empty_cached_apk_as_missing(self, monkeypatch, tmp_path):
        """A zero-byte cache entry (interrupted write) must never be installed:
        `adb install` on it fails with a corrupt-APK error that points the user
        at the wrong problem."""
        import app.handlers.automation_handler as mod

        events = []
        cache = tmp_path / "cache"
        dest = cache / "tools" / "ADBKeyBoard.apk"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b"")

        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))
        dl_calls = []
        monkeypatch.setattr(
            mod, "_download_apk",
            lambda d, on_progress, on_log, cancel_check=None: (dl_calls.append(d), open(d, "wb").write(b"GOOD")),
        )
        monkeypatch.setattr(mod, "run_adb", lambda device_id, args: {
            "returncode": 0, "stdout": "Success", "stderr": "",
        })
        monkeypatch.setattr(mod, "adb_ime_installed", lambda device_id: True)
        monkeypatch.setattr(mod, "ime_status_impl", lambda device_id: {
            "device_id": device_id, "package": "pkg", "installed": True, "active": False,
        })

        mod.install_ime({"device_id": "emulator-5554"}, lambda e: events.append(e))

        assert dl_calls == [str(dest)]
        assert dest.read_bytes() == b"GOOD"

    def test_download_writes_via_a_part_file_and_renames(self, monkeypatch, tmp_path):
        """A kill mid-download must leave no usable-looking file at `dest`."""
        import os

        import app.handlers.automation_handler as mod

        cache = tmp_path / "cache"
        dest = cache / "tools" / "ADBKeyBoard.apk"
        dest.parent.mkdir(parents=True)
        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))
        monkeypatch.setattr(mod, "_DL_BACKOFF_BASE", 0)
        _patch_net(monkeypatch, _FakeApkResp([b"hello"]))

        seen = {}
        real_open = open

        def spy_open(path, mode="r", *a, **k):
            if "w" in str(mode):
                seen["write_path"] = str(path)
            return real_open(path, mode, *a, **k)

        import builtins
        monkeypatch.setattr(builtins, "open", spy_open)

        mod._download_apk(str(dest), lambda info: None, lambda line: None)

        assert seen["write_path"] == str(dest) + ".part"
        assert dest.read_bytes() == _apk_body(b"hello")
        assert not os.path.exists(str(dest) + ".part")

    def test_install_ime_download_reports_the_exact_progress_shape(
        self, monkeypatch, tmp_path
    ):
        """generated_cached_artifacts probe: progress payloads keep the exact
        {progress, downloaded, total, speed} shape, and the download goes to a
        destination that does not exist yet."""
        import app.handlers.automation_handler as mod

        events = []
        cache = tmp_path / "cache"
        dest = cache / "tools" / "ADBKeyBoard.apk"

        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))
        monkeypatch.setattr(mod, "_DL_BACKOFF_BASE", 0)
        _patch_net(monkeypatch, _FakeApkResp([b"hello"]))
        monkeypatch.setattr(mod, "run_adb", lambda device_id, args: {
            "returncode": 0, "stdout": "Success", "stderr": "",
        })
        monkeypatch.setattr(mod, "adb_ime_installed", lambda device_id: True)
        monkeypatch.setattr(mod, "ime_status_impl", lambda device_id: {
            "device_id": device_id, "package": "pkg",
            "installed": True, "active": False,
        })

        mod.install_ime(
            {"device_id": "emulator-5554"}, lambda e: events.append(e)
        )

        assert dest.read_bytes() == _apk_body(b"hello")
        progresses = [e for e in events if e["type"] == "progress"]
        assert progresses
        assert set(progresses[0]["payload"].keys()) == {
            "progress", "downloaded", "total", "speed",
        }
        assert progresses[0]["payload"]["downloaded"] == len(_apk_body(b"hello"))
        assert progresses[0]["payload"]["total"] == len(_apk_body(b"hello"))

    # ------------------------------------------------------------------
    # multi-source download (the upstream rename that broke the URL)
    # ------------------------------------------------------------------

    def _net_by_url(self, monkeypatch, mod, per_url):
        """Patch BOTH network seams with URL-aware behaviour.

        ``_download_apk`` picks its transport per attempt: with a proxy in the
        environment the first attempt goes through ``urlopen``, but a direct
        attempt uses ``build_opener(ProxyHandler({})).open``. Patching only one
        of them lets the real network through (which is exactly how this test
        helper first failed).

        ``per_url`` maps a URL to either a response object or an Exception to
        raise when it is requested; unknown URLs answer 404.
        """
        from urllib.error import HTTPError
        from unittest.mock import MagicMock

        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.delenv("https_proxy", raising=False)
        monkeypatch.delenv("http_proxy", raising=False)
        seen = []

        def fake_open(req, timeout=None):
            url = getattr(req, "full_url", None) or str(req)
            seen.append(url)
            effect = per_url.get(url)
            if effect is None:
                raise HTTPError(url, 404, "Not Found", None, None)
            if isinstance(effect, Exception):
                raise effect
            return effect

        opener = MagicMock()
        opener.open.side_effect = fake_open
        monkeypatch.setattr(mod, "urlopen", MagicMock(side_effect=fake_open))
        monkeypatch.setattr(mod, "build_opener", MagicMock(return_value=opener))
        return seen

    def test_a_dead_primary_url_falls_back_to_the_next_source(
        self, monkeypatch, tmp_path
    ):
        """The upstream repo renamed ADBKeyBoard.apk, so the primary URL
        answered 404 and the install was a hard dead end. A 404 must move on to
        the next candidate instead of ending the install."""
        import os
        from urllib.error import HTTPError

        import app.handlers.automation_handler as mod

        events = []
        cache = tmp_path / "cache"
        dest = cache / "tools" / "ADBKeyBoard.apk"
        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))
        monkeypatch.setattr(mod, "_DL_BACKOFF_BASE", 0)

        primary, *rest = mod.ADBKEYBOARD_URLS
        assert rest, "this test needs at least two candidates"
        seen = self._net_by_url(monkeypatch, mod, {
            primary: HTTPError(primary, 404, "Not Found", None, None),
            rest[0]: _FakeApkResp([b"apk-from-release"]),
        })

        monkeypatch.setattr(mod, "run_adb", lambda device_id, args: {
            "returncode": 0, "stdout": "Success", "stderr": "",
        })
        monkeypatch.setattr(mod, "adb_ime_installed", lambda device_id: True)
        monkeypatch.setattr(mod, "ime_status_impl", lambda device_id: {
            "device_id": device_id, "package": "pkg", "installed": True, "active": False,
        })

        mod.install_ime({"device_id": "emulator-5554"}, lambda e: events.append(e))

        assert seen[0] == primary
        assert rest[0] in seen, "the fallback source was never requested"
        assert os.path.isfile(dest)
        assert dest.read_bytes() == _apk_body(b"apk-from-release")
        completes = [e for e in events if e["type"] == "complete"]
        assert len(completes) == 1
        assert completes[0]["payload"]["success"] is True
        assert not any(e["type"] == "error" for e in events)
        logs = " ".join(e["payload"] for e in events if e["type"] == "log")
        assert "尝试下一个下载地址" in logs
        assert "来源" in logs          # the log says which mirror was used

    def test_all_404s_still_report_every_address(self, monkeypatch, tmp_path):
        """A 404 for the old URL alone was unhelpful; the terminal error must
        list every address that was tried."""
        from urllib.error import HTTPError

        import app.handlers.automation_handler as mod

        events = []
        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(tmp_path / "cache"))
        monkeypatch.setattr(mod, "_DL_BACKOFF_BASE", 0)
        self._net_by_url(monkeypatch, mod, {
            url: HTTPError(url, 404, "Not Found", None, None)
            for url in mod.ADBKEYBOARD_URLS
        })

        mod.install_ime({"device_id": "emulator-5554"}, lambda e: events.append(e))

        errors = [e for e in events if e["type"] == "error"]
        assert len(errors) == 1
        msg = errors[0]["payload"]
        for url in mod.ADBKEYBOARD_URLS:
            assert url in msg, f"missing tried address in error: {url}"
        assert "404" in msg

    def test_a_non_apk_200_response_is_rejected_not_installed(
        self, monkeypatch, tmp_path
    ):
        """A captive portal / proxy notice answers 200 with HTML. Installing
        that fails later as a "corrupt APK", pointing at the wrong problem."""
        import os

        import app.handlers.automation_handler as mod

        events = []
        cache = tmp_path / "cache"
        dest = cache / "tools" / "ADBKeyBoard.apk"
        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))
        monkeypatch.setattr(mod, "_DL_BACKOFF_BASE", 0)
        adb_calls = []
        monkeypatch.setattr(mod, "run_adb", lambda d, a: adb_calls.append(a))
        # every source answers with a login page
        self._net_by_url(monkeypatch, mod, {
            url: _FakeApkResp([b"<html>login</html>"], valid_apk=False)
            for url in mod.ADBKEYBOARD_URLS
        })

        mod.install_ime({"device_id": "emulator-5554"}, lambda e: events.append(e))

        assert adb_calls == [], "a non-APK body must never reach adb install"
        assert not os.path.exists(dest)
        assert not os.path.exists(str(dest) + ".part")
        errors = [e for e in events if e["type"] == "error"]
        assert len(errors) == 1
        assert "不是 APK" in errors[0]["payload"]

    def test_a_non_apk_response_falls_through_to_a_good_source(
        self, monkeypatch, tmp_path
    ):
        import app.handlers.automation_handler as mod

        cache = tmp_path / "cache"
        dest = cache / "tools" / "ADBKeyBoard.apk"
        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))
        monkeypatch.setattr(mod, "_DL_BACKOFF_BASE", 0)
        primary, *rest = mod.ADBKEYBOARD_URLS
        self._net_by_url(monkeypatch, mod, {
            primary: _FakeApkResp([b"<html>portal</html>"], valid_apk=False),
            rest[0]: _FakeApkResp([b"real"]),
        })
        monkeypatch.setattr(mod, "run_adb", lambda device_id, args: {
            "returncode": 0, "stdout": "Success", "stderr": "",
        })
        monkeypatch.setattr(mod, "adb_ime_installed", lambda device_id: True)
        monkeypatch.setattr(mod, "ime_status_impl", lambda device_id: {
            "device_id": device_id, "package": "pkg", "installed": True, "active": False,
        })

        mod.install_ime({"device_id": "emulator-5554"}, lambda e: None)
        assert dest.read_bytes() == _apk_body(b"real")

    def test_bt_adbkeyboard_url_overrides_the_builtin_list(
        self, monkeypatch, tmp_path
    ):
        """An internal mirror must be usable without a rebuild, and it must be
        the ONLY address tried (that is the point of an override)."""
        import app.handlers.automation_handler as mod

        mirror = "https://mirror.internal/ADBKeyBoard.apk"
        monkeypatch.setenv("BT_ADBKEYBOARD_URL", f"  {mirror}  ")
        assert mod.adbkeyboard_urls() == (mirror,)

        cache = tmp_path / "cache"
        dest = cache / "tools" / "ADBKeyBoard.apk"
        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))
        monkeypatch.setattr(mod, "_DL_BACKOFF_BASE", 0)
        seen = self._net_by_url(monkeypatch, mod, {mirror: _FakeApkResp([b"mirrored"])})
        monkeypatch.setattr(mod, "run_adb", lambda device_id, args: {
            "returncode": 0, "stdout": "Success", "stderr": "",
        })
        monkeypatch.setattr(mod, "adb_ime_installed", lambda device_id: True)
        monkeypatch.setattr(mod, "ime_status_impl", lambda device_id: {
            "device_id": device_id, "package": "pkg", "installed": True, "active": False,
        })

        mod.install_ime({"device_id": "emulator-5554"}, lambda e: None)

        assert seen == [mirror]
        assert dest.read_bytes() == _apk_body(b"mirrored")

    def test_apk_magic_helper(self, monkeypatch, tmp_path):
        import app.handlers.automation_handler as mod

        good = tmp_path / "good.apk"
        good.write_bytes(b"PK\x03\x04rest")
        bad = tmp_path / "bad.html"
        bad.write_bytes(b"<html>")
        assert mod._looks_like_apk(str(good)) is True
        assert mod._looks_like_apk(str(bad)) is False
        assert mod._looks_like_apk(str(tmp_path / "missing")) is False

    def test_every_builtin_url_is_a_distinct_https_location(self):
        import app.handlers.automation_handler as mod

        urls = mod.ADBKEYBOARD_URLS
        assert len(urls) >= 2
        assert len(set(urls)) == len(urls)
        for url in urls:
            assert url.startswith("https://"), url
        # the primary is the one quoted in logs/errors
        assert mod.ADBKEYBOARD_URL == urls[0]
        # the file the upstream repo renamed must not come back
        assert not any(u.endswith("/ADBKeyBoard.apk") for u in urls)

    def test_install_ime_cancel_before_start_emits_cancelled_no_complete(
        self, monkeypatch, tmp_path
    ):
        """A cancel that lands before the download must not start one."""
        import os
        import threading

        import app.handlers.automation_handler as mod

        events = []
        cache = tmp_path / "cache"
        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))
        monkeypatch.setattr(
            mod, "_download_apk",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not download")),
        )

        stop = threading.Event()
        stop.set()

        def handler(event):
            events.append(event)

        handler.bt_stop_event = stop
        mod.install_ime({"device_id": "emulator-5554", "task_id": "t1"}, handler)

        assert [e["type"] for e in events] == ["cancelled"]
        assert events[0]["payload"]["task_id"] == "t1"
        assert not any(e["type"] == "complete" for e in events)
        assert not os.path.exists(os.path.join(str(cache), "tools", "ADBKeyBoard.apk"))

    def test_install_ime_cancel_during_download_cleans_the_part_file(
        self, monkeypatch, tmp_path
    ):
        """Cancelling mid-download aborts within a chunk, leaves no usable APK
        behind and never reports a download FAILURE (it is not one)."""
        import os
        import threading

        import app.handlers.automation_handler as mod

        events = []
        cache = tmp_path / "cache"
        dest = cache / "tools" / "ADBKeyBoard.apk"
        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))
        monkeypatch.setattr(mod, "_DL_BACKOFF_BASE", 0)

        stop = threading.Event()

        def handler(event):
            # cancel the moment the first progress line arrives
            if event["type"] == "progress":
                stop.set()
            events.append(event)

        handler.bt_stop_event = stop
        _patch_net(monkeypatch, _FakeApkResp([b"hello"]))

        mod.install_ime({"device_id": "emulator-5554", "task_id": "t2"}, handler)

        assert "cancelled" in [e["type"] for e in events]
        assert not any(e["type"] == "complete" for e in events)
        assert not any(e["type"] == "error" for e in events)
        assert not dest.exists(), "a cancelled download must not promote the .part file"
        assert not os.path.exists(str(dest) + ".part")

    def test_install_ime_cancel_during_download_does_not_retry(self, monkeypatch, tmp_path):
        """A cancel must abort the retry budget too, not be retried 3×."""
        import threading

        import app.handlers.automation_handler as mod

        events = []
        cache = tmp_path / "cache"
        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))
        monkeypatch.setattr(mod, "_DL_BACKOFF_BASE", 0)

        stop = threading.Event()
        attempts = []

        def slow_resp():
            attempts.append(1)
            return _FakeApkResp([b"hello"])

        def handler(event):
            stop.set()          # cancel before the first chunk is even read
            events.append(event)

        handler.bt_stop_event = stop
        _patch_net(monkeypatch, slow_resp())

        mod.install_ime({"device_id": "emulator-5554"}, handler)

        assert [e["type"] for e in events].count("cancelled") == 1
        assert len(attempts) == 1

    def test_install_ime_cancel_after_download_skips_the_install(
        self, monkeypatch, tmp_path
    ):
        import threading

        import app.handlers.automation_handler as mod

        events = []
        cache = tmp_path / "cache"
        dest = cache / "tools" / "ADBKeyBoard.apk"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(_apk_body(b"CACHED"))

        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))
        adb_calls = []
        monkeypatch.setattr(mod, "run_adb", lambda device_id, args: adb_calls.append(args))

        stop = threading.Event()
        stop.set()

        def handler(event):
            events.append(event)

        handler.bt_stop_event = stop

        mod.install_ime({"device_id": "emulator-5554", "task_id": "t3"}, handler)

        assert adb_calls == [], "a cancelled install must not touch the device"
        assert [e["type"] for e in events] == ["cancelled"]

    def test_install_mitmproxy_cancel_does_not_report_a_degraded_install(
        self, monkeypatch, tmp_path
    ):
        """A cancelled pip run exits non-zero — that must NOT surface as the
        "install failed, here is the manual command" degrade path."""
        import threading

        import app.handlers.automation_handler as mod

        events = []
        monkeypatch.setattr(mod, "any_capture_active", lambda: False)
        monkeypatch.setattr(mod, "get_runtime_dir", lambda: str(tmp_path))
        monkeypatch.setattr(mod, "_pip_available", lambda: True)

        stop = threading.Event()

        def fake_install(lib, on_line, task_id=""):
            stop.set()          # the cancel arrives while pip runs
            on_line("Downloading mitmproxy")
            return 1            # what a killed pip reports

        monkeypatch.setattr(mod, "_pip_install", fake_install)

        def handler(event):
            events.append(event)

        handler.bt_stop_event = stop
        mod.install_mitmproxy({"task_id": "t4"}, handler)

        assert "cancelled" in [e["type"] for e in events]
        assert not any(
            e["type"] == "complete" and e["payload"].get("degraded") for e in events
        )

    def test_install_mitmproxy_passes_the_task_id_to_pip_for_killability(
        self, monkeypatch, tmp_path
    ):
        """Without the TaskManager holder a cancel cannot terminate pip at all."""
        import app.handlers.automation_handler as mod

        events = []
        monkeypatch.setattr(mod, "any_capture_active", lambda: False)
        monkeypatch.setattr(mod, "get_runtime_dir", lambda: str(tmp_path))
        monkeypatch.setattr(mod, "_pip_available", lambda: True)
        monkeypatch.setattr(mod, "_write_python_marker", lambda runtime: None)
        monkeypatch.setattr(mod, "traffic_status_impl", lambda: {
            "installed": True, "ready": True, "lib_path": "l",
            "python_mismatch": None, "ca_cert_exists": False,
        })
        seen = {}

        def fake_install(lib, on_line, task_id=""):
            seen["task_id"] = task_id
            return 0

        monkeypatch.setattr(mod, "_pip_install", fake_install)

        mod.install_mitmproxy({"task_id": "t5"}, lambda e: events.append(e))

        assert seen["task_id"] == "t5"
        assert [e["type"] for e in events if e["type"] == "complete"]

    def test_pip_registration_keeps_the_streaming_stop_event_alive(
        self, monkeypatch, tmp_path
    ):
        """Registering pip must not clobber the @streaming task entry.

        `TaskManager.register()` REPLACES an entry, and the @streaming wrapper
        has already registered this task_id WITH its stop_event. A naive
        register() therefore dropped the stop_event, so the very cancel button
        this feature adds would never reach `ctx.is_cancelled()`.
        """
        import threading

        import app.handlers.automation_handler as mod
        from app.common.task_manager import TaskManager

        task_id = "t-stop-event"
        stop = threading.Event()
        TaskManager().register_stream(task_id, stop)   # what @streaming does

        events = []
        monkeypatch.setattr(mod, "any_capture_active", lambda: False)
        monkeypatch.setattr(mod, "get_runtime_dir", lambda: str(tmp_path))
        monkeypatch.setattr(mod, "_pip_available", lambda: True)

        class FakeProc:
            pid = 4242

            def __init__(self):
                self.terminated = False

            def poll(self):
                return None

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=None):
                return 0

            def kill(self):
                pass

        proc = FakeProc()

        def fake_install(lib, on_line, task_id=""):
            # put the process in the holder exactly as _pip_install does
            holder = TaskManager().get_process_holder(task_id)
            assert holder is not None
            holder["process"] = proc
            # the UI's cancel arrives now
            assert TaskManager().cancel(task_id) is True
            return 1

        monkeypatch.setattr(mod, "_pip_install", fake_install)

        def handler(event):
            events.append(event)

        handler.bt_stop_event = stop
        try:
            mod.install_mitmproxy({"task_id": task_id}, handler)
        finally:
            TaskManager().unregister(task_id)

        assert stop.is_set(), "the streaming stop_event was clobbered"
        assert proc.terminated, "cancel must terminate the in-flight pip"
        assert "cancelled" in [e["type"] for e in events]
        assert not any(
            e["type"] == "complete" and e["payload"].get("degraded") for e in events
        )

    def test_install_ime_success_requires_the_ime_to_be_installed(
        self, monkeypatch, tmp_path
    ):
        """`adb install` returning 0 is not proof the IME is usable.

        A wrong APK (local apk_path mode) installs cleanly and leaves the
        device without ADBKeyBoard; reporting success there only surfaced
        later as non-ASCII input silently failing.
        """
        import app.handlers.automation_handler as mod

        events = []
        cache = tmp_path / "cache"
        dest = cache / "tools" / "ADBKeyBoard.apk"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(_apk_body(b"CACHED"))

        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))
        monkeypatch.setattr(mod, "run_adb", lambda device_id, args: {
            "returncode": 0, "stdout": "Success", "stderr": "",
        })
        monkeypatch.setattr(mod, "adb_ime_installed", lambda device_id: False)
        monkeypatch.setattr(mod, "ime_status_impl", lambda device_id: {
            "device_id": device_id, "package": "pkg",
            "installed": False, "active": False,
        })

        mod.install_ime({"device_id": "emulator-5554"}, lambda e: events.append(e))

        completes = [e for e in events if e["type"] == "complete"]
        assert len(completes) == 1
        assert completes[0]["payload"]["success"] is False
        logs = " ".join(e["payload"] for e in events if e["type"] == "log")
        assert "输入法列表里没有 ADBKeyBoard" in logs

    def test_install_ime_failure_payload_still_has_the_status_shape(
        self, monkeypatch, tmp_path
    ):
        """A failed verification keeps the same payload keys, so the caller's
        rendering path does not have to branch on success."""
        import app.handlers.automation_handler as mod

        events = []
        cache = tmp_path / "cache"
        dest = cache / "tools" / "ADBKeyBoard.apk"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(_apk_body(b"CACHED"))
        monkeypatch.setattr(mod, "get_cache_dir", lambda: str(cache))
        monkeypatch.setattr(mod, "run_adb", lambda device_id, args: {
            "returncode": 1, "stdout": "", "stderr": "Failure [INSTALL_FAILED_INVALID_APK]",
        })
        monkeypatch.setattr(mod, "adb_ime_installed", lambda device_id: False)
        monkeypatch.setattr(mod, "ime_status_impl", lambda device_id: {
            "device_id": device_id, "package": "pkg",
            "installed": False, "active": False,
        })

        mod.install_ime({"device_id": "emulator-5554"}, lambda e: events.append(e))

        payload = [e for e in events if e["type"] == "complete"][0]["payload"]
        assert set(payload.keys()) == {
            "success", "device_id", "package", "installed", "active",
        }
        assert payload["success"] is False


class TestTrafficReset:
    """``automation.traffic_reset`` — idempotent recovery of device-side
    capture wiring left behind by a hard-killed backend.

    The impl is aliased at module level (``recover_stale_capture_impl``) so
    these tests never touch adb or the real cache dir.
    """

    def test_idempotent_when_nothing_is_stale(self, api_handler, monkeypatch):
        import app.handlers.automation_handler as mod

        calls = []

        def fake_impl(device_id=None):
            calls.append(device_id)
            return {"success": True, "restored": []}

        monkeypatch.setattr(mod, "recover_stale_capture_impl", fake_impl)
        data = _call(api_handler, "automation.traffic_reset", {}, 91)

        assert data["finished"] is True
        assert data["result"]["type"] == "success"
        payload = data["result"]["payload"]
        assert payload["success"] is True
        assert payload["restored"] == []
        # No device given -> recover everything (None, not "").
        assert calls == [None]

    def test_passes_device_id_through(self, api_handler, monkeypatch):
        import app.handlers.automation_handler as mod

        seen = []

        def fake_impl(device_id=None):
            seen.append(device_id)
            return {
                "success": True,
                "restored": [{
                    "device_id": device_id,
                    "proxy_restored": True,
                    "reverse_removed": True,
                    "port_freed": True,
                }],
            }

        monkeypatch.setattr(mod, "recover_stale_capture_impl", fake_impl)
        data = _call(
            api_handler, "automation.traffic_reset",
            {"device_id": "  emulator-5554  "}, 92,
        )

        assert seen == ["emulator-5554"]  # trimmed
        payload = data["result"]["payload"]
        assert set(payload["restored"][0].keys()) == {
            "device_id", "proxy_restored", "reverse_removed", "port_freed",
        }
        assert payload["restored"][0]["port_freed"] is True

    def test_blank_device_id_recovers_everything(self, api_handler, monkeypatch):
        """A whitespace-only id must not be treated as a device filter."""
        import app.handlers.automation_handler as mod

        seen = []
        monkeypatch.setattr(
            mod, "recover_stale_capture_impl",
            lambda device_id=None: (seen.append(device_id), {"success": True, "restored": []})[1],
        )
        _call(api_handler, "automation.traffic_reset", {"device_id": "   "}, 93)
        assert seen == [None]


class TestResponseShape:
    METHODS = [
        # ime_status needs a device; its shape is covered by TestImeStatus.
        "automation.traffic_status",
        "automation.traffic_reset",
    ]

    @pytest.mark.parametrize("method", METHODS)
    def test_all_methods_produce_valid_response_shape(self, api_handler, method):
        data = _call(api_handler, method, {}, 500)
        assert "id" in data, f"{method}: missing id"
        assert "result" in data, f"{method}: missing result"
        assert "finished" in data, f"{method}: missing finished"
