"""Contract tests for stale traffic-capture recovery.

``_ACTIVE`` is process memory; the device-side wiring is not. A backend that
is killed while a capture runs (Windows: the Electron main process
TerminateProcesses it) leaves the device with ``global http_proxy
127.0.0.1:<port>`` pointing at a proxy that no longer exists — the device is
offline. These tests lock the registry that makes the NEXT backend start able
to heal that, without touching a real device, adb or the real cache dir.
"""
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from app.automation import traffic  # noqa: E402


class _FakeProc:
    """Just enough Popen for ``_terminate`` / ``stop_capture``."""

    def __init__(self, pid=4242):
        self.pid = pid
        self.terminated = False

    def poll(self):
        return 0  # already exited -> _terminate() is a no-op

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.terminated = True


@pytest.fixture
def adb_calls(monkeypatch, tmp_path):
    """Redirect the cache dir and capture every adb argv."""
    cache = tmp_path / "cache"
    monkeypatch.setenv("BT_CACHE_DIR", str(cache))
    calls = []

    def fake_run_adb(device_id, args, *a, **kw):
        calls.append((device_id, tuple(args)))
        return {"returncode": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(traffic, "run_adb", fake_run_adb)
    monkeypatch.setattr(traffic, "_free_port", lambda port: True)
    return calls


def _registry_file(tmp_path):
    return tmp_path / "cache" / traffic._REGISTRY_NAME


def _seed_registry(tmp_path, entries):
    path = _registry_file(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# registry lifecycle
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_missing_registry_is_not_an_error(self, adb_calls, tmp_path):
        assert not _registry_file(tmp_path).exists()
        out = traffic.recover_stale_capture()
        assert out == {"success": True, "restored": []}
        assert adb_calls == []

    def test_read_probe_does_not_create_the_cache_dir(self, monkeypatch, tmp_path):
        """A pure read must not have a mkdir side effect (review finding M2)."""
        cache = tmp_path / "not-created"
        monkeypatch.setenv("BT_CACHE_DIR", str(cache))
        monkeypatch.setattr(
            traffic, "run_adb",
            lambda *a, **kw: pytest.fail("must not touch adb"),
        )
        traffic.recover_stale_capture()
        assert not cache.exists()

    def test_corrupt_registry_is_ignored(self, monkeypatch, tmp_path):
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / traffic._REGISTRY_NAME).write_text("{not json", encoding="utf-8")
        monkeypatch.setenv("BT_CACHE_DIR", str(cache))
        assert traffic.recover_stale_capture() == {"success": True, "restored": []}

    def test_stop_capture_clears_the_registry(self, adb_calls, tmp_path):
        """The normal exit path must consume the registry, not leave it."""
        jsonl = tmp_path / "run" / "traffic.jsonl"
        jsonl.parent.mkdir(parents=True)
        jsonl.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")

        traffic._ACTIVE["emulator-5554"] = {
            "proc": _FakeProc(), "log_fh": io.StringIO(), "port": 18888,
            "jsonl": str(jsonl), "log": str(jsonl) + ".log",
        }
        traffic._write_registry()
        assert _registry_file(tmp_path).exists()

        try:
            out = traffic.stop_capture("emulator-5554")
        finally:
            traffic._ACTIVE.pop("emulator-5554", None)

        assert out["requests"] == 2
        assert out["proxy_restored"] is True
        assert not _registry_file(tmp_path).exists()
        devices = [c[0] for c in adb_calls]
        assert devices == ["emulator-5554", "emulator-5554"]
        assert adb_calls[0][1] == ("shell", "settings", "put", "global", "http_proxy", ":0")
        assert adb_calls[1][1] == ("reverse", "--remove", "tcp:18888")


# ---------------------------------------------------------------------------
# recovery
# ---------------------------------------------------------------------------

class TestRecoverStaleCapture:
    def test_restores_every_stale_device_and_consumes_the_registry(self, adb_calls, tmp_path):
        _seed_registry(tmp_path, {
            "emulator-5554": {"port": 18888, "jsonl": "x", "pid": 1},
            "emulator-5556": {"port": 18889, "jsonl": "y", "pid": 2},
        })

        out = traffic.recover_stale_capture()

        assert out["success"] is True
        assert {r["device_id"] for r in out["restored"]} == {"emulator-5554", "emulator-5556"}
        assert all(r["proxy_restored"] and r["reverse_removed"] for r in out["restored"])
        assert all(r["port_freed"] is True for r in out["restored"])
        # Every device got the proxy reset + its reverse entry removed.
        for dev, port in (("emulator-5554", 18888), ("emulator-5556", 18889)):
            assert (dev, ("shell", "settings", "put", "global", "http_proxy", ":0")) in adb_calls
            assert (dev, ("reverse", "--remove", f"tcp:{port}")) in adb_calls
        # Consumed: a second start must not re-run the same recovery.
        assert not _registry_file(tmp_path).exists()
        assert traffic.recover_stale_capture() == {"success": True, "restored": []}

    def test_filtered_recovery_keeps_the_other_entries(self, adb_calls, tmp_path):
        _seed_registry(tmp_path, {
            "emulator-5554": {"port": 18888, "jsonl": "x", "pid": 1},
            "emulator-5556": {"port": 18889, "jsonl": "y", "pid": 2},
        })

        out = traffic.recover_stale_capture("emulator-5556")

        assert [r["device_id"] for r in out["restored"]] == ["emulator-5556"]
        assert [c[0] for c in adb_calls] == ["emulator-5556", "emulator-5556"]
        remaining = json.loads(_registry_file(tmp_path).read_text(encoding="utf-8"))
        assert list(remaining) == ["emulator-5554"]

    def test_live_capture_is_never_touched(self, adb_calls, tmp_path):
        _seed_registry(tmp_path, {
            "emulator-5554": {"port": 18888, "jsonl": "x", "pid": 1},   # stale
            "emulator-5556": {"port": 18889, "jsonl": "y", "pid": 2},   # live here
        })
        traffic._ACTIVE["emulator-5556"] = {"port": 18889, "jsonl": "y"}
        try:
            out = traffic.recover_stale_capture()
        finally:
            traffic._ACTIVE.pop("emulator-5556", None)

        assert [r["device_id"] for r in out["restored"]] == ["emulator-5554"]
        assert [c[0] for c in adb_calls] == ["emulator-5554", "emulator-5554"]
        # The live entry survives for the next recovery / graceful stop.
        remaining = json.loads(_registry_file(tmp_path).read_text(encoding="utf-8"))
        assert list(remaining) == ["emulator-5556"]

    def test_port_of_a_live_capture_is_not_freed(self, monkeypatch, tmp_path):
        """A stale entry must never make us kill the mitmdump we are using."""
        monkeypatch.setenv("BT_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setattr(
            traffic, "run_adb",
            lambda device_id, args, *a, **kw: {"returncode": 0, "stdout": "", "stderr": ""},
        )
        freed = []
        monkeypatch.setattr(traffic, "_free_port", lambda port: freed.append(port) or True)
        _seed_registry(tmp_path, {"emulator-5554": {"port": 18888, "jsonl": "x", "pid": 1}})
        traffic._ACTIVE["emulator-5556"] = {"port": 18888, "jsonl": "y"}
        try:
            out = traffic.recover_stale_capture()
        finally:
            traffic._ACTIVE.pop("emulator-5556", None)

        assert freed == []
        assert out["restored"][0]["port_freed"] is None

    def test_offline_device_is_reported_not_raised(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BT_CACHE_DIR", str(tmp_path / "cache"))

        def boom(device_id, args, *a, **kw):
            raise OSError("device offline")

        monkeypatch.setattr(traffic, "run_adb", boom)
        monkeypatch.setattr(traffic, "_free_port", lambda port: True)
        _seed_registry(tmp_path, {"gone-1234": {"port": 18888, "jsonl": "x", "pid": 1}})

        out = traffic.recover_stale_capture()

        assert out["success"] is True
        rec = out["restored"][0]
        assert rec["proxy_restored"] is False
        assert "device offline" in rec["error"]
        # Still consumed: an unplugged device must not loop forever.
        assert not _registry_file(tmp_path).exists()

    def test_entry_without_port_only_restores_the_proxy(self, adb_calls, tmp_path):
        _seed_registry(tmp_path, {"emulator-5554": {"jsonl": "x"}})

        out = traffic.recover_stale_capture()

        assert out["restored"][0]["port_freed"] is None
        assert len(adb_calls) == 1
        assert adb_calls[0][1][:4] == ("shell", "settings", "put", "global")

    def test_malformed_entry_is_tolerated(self, adb_calls, tmp_path):
        _seed_registry(tmp_path, {"emulator-5554": "not-a-dict"})

        out = traffic.recover_stale_capture()

        assert out["restored"][0]["proxy_restored"] is True
        assert out["restored"][0]["port_freed"] is None
