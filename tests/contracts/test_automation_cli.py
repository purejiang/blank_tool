#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contract tests for the automation CLI (standalone entry, no GUI).

The CLI wraps ``app/automation/orchestrator.run`` with a stdout-printing
StreamContext — these tests lock the pieces that don't need a device:
output formatting, adb resolution precedence, steps-file validation and
single-device auto-detection.
"""
import json
import os

import pytest

from app.automation.cli import CliStreamContext, detect_single_device, load_steps, resolve_adb


class TestCliStreamContext:
    def _capture(self, events, capsys):
        ctx = CliStreamContext("automation")
        for e in events:
            ctx._emit(e)
        return capsys.readouterr().out

    def test_log_line_has_timestamp_prefix(self, capsys):
        out = self._capture([{"type": "log", "payload": "[automation] hi"}], capsys)
        assert "[automation] hi" in out
        import re
        assert re.search(r"\[\d{2}:\d{2}:\d{2}\]", out)

    def test_step_lines_show_ok_and_fail(self, capsys):
        out = self._capture([
            {"type": "step_start", "payload": {"index": 1, "action": "tap"}},
            {"type": "step", "payload": {"index": 1, "action": "tap", "ok": True, "duration_ms": 12, "message": ""}},
            {"type": "step", "payload": {"index": 2, "action": "assert", "ok": False, "duration_ms": 3, "message": "not found"}},
        ], capsys)
        assert "-> #1 tap" in out
        assert "OK" in out and "FAIL" in out
        assert "not found" in out

    def test_complete_prints_summary_and_report_path(self, capsys):
        out = self._capture([{
            "type": "complete",
            "payload": {"success": True, "passed": 3, "failed": 0, "total": 3, "run_dir": "D:/runs/t1"},
        }], capsys)
        assert "SUCCESS" in out
        assert "3 passed / 0 failed" in out
        assert os.path.join("D:", "runs", "t1", "report.json") in out or "report.json" in out

    def test_error_goes_to_stderr(self, capsys):
        ctx = CliStreamContext("automation")
        ctx._emit({"type": "error", "payload": "boom"})
        err = capsys.readouterr().err
        assert "boom" in err
        assert capsys.readouterr().out == ""


class TestResolveAdb:
    @staticmethod
    def _stub_tool_manager(monkeypatch, reject=None):
        """Stub ToolManager: set_custom_path just records (no -version
        validation, which would try to exec a fake binary). ``reject``
        is an optional predicate marking candidates as unusable."""
        import app.automation.cli as cli
        recorded = {}

        class FakeTM:
            @classmethod
            def instance(cls):
                return cls

            @classmethod
            def set_custom_path(cls, name, path):
                if reject and reject(path):
                    raise OSError("[WinError 193] not a valid Win32 application")
                recorded[name] = path

        monkeypatch.setattr(cli, "ToolManager", FakeTM)
        return recorded

    def test_explicit_path_wins(self, tmp_path, monkeypatch):
        recorded = self._stub_tool_manager(monkeypatch)
        fake = tmp_path / "adb_custom.exe"
        fake.write_text("")
        monkeypatch.setenv("BT_TOOL_ADB", str(tmp_path / "env_adb.exe"))
        resolved = resolve_adb(str(fake))
        assert resolved == str(fake)
        # injected into ToolManager so run_adb picks it up
        assert recorded.get("adb") == str(fake)

    def test_env_override_before_runtime_and_path(self, tmp_path, monkeypatch):
        recorded = self._stub_tool_manager(monkeypatch)
        fake = tmp_path / "env_adb.exe"
        fake.write_text("")
        monkeypatch.setenv("BT_TOOL_ADB", str(fake))
        assert resolve_adb(None) == str(fake)
        assert recorded.get("adb") == str(fake)

    def test_invalid_candidate_falls_through(self, tmp_path, monkeypatch):
        """A candidate that exists but fails validation (-version) must be
        skipped in favor of the next one."""
        bad = tmp_path / "not_an_executable.exe"
        bad.write_text("")
        good = tmp_path / "good_adb.exe"
        good.write_text("")
        monkeypatch.setenv("BT_TOOL_ADB", str(good))
        recorded = self._stub_tool_manager(
            monkeypatch, reject=lambda p: str(p) == str(bad)
        )
        assert resolve_adb(str(bad)) == str(good)
        assert recorded.get("adb") == str(good)

    def test_missing_everywhere_raises_systemexit(self, tmp_path, monkeypatch):
        import shutil as shutil_mod
        self._stub_tool_manager(monkeypatch)
        monkeypatch.delenv("BT_TOOL_ADB", raising=False)
        monkeypatch.setattr(shutil_mod, "which", lambda name: None)
        # runtime/adb/adb.exe exists in the repo — neutralize by pointing
        # BT_RUNTIME_DIR at an empty tmp dir
        empty = tmp_path / "runtime"
        empty.mkdir()
        monkeypatch.setenv("BT_RUNTIME_DIR", str(empty))
        with pytest.raises(SystemExit, match="找不到 adb"):
            resolve_adb(None)


class TestLoadSteps:
    def test_missing_file_exits(self):
        with pytest.raises(SystemExit, match="步骤文件不存在"):
            load_steps("no/such/file.json")

    def test_invalid_json_exits(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        with pytest.raises(SystemExit, match="解析失败"):
            load_steps(str(p))

    def test_non_array_exits(self, tmp_path):
        p = tmp_path / "obj.json"
        p.write_text('{"steps": []}', encoding="utf-8")
        with pytest.raises(SystemExit, match="JSON 数组"):
            load_steps(str(p))

    def test_valid_array_roundtrip(self, tmp_path):
        p = tmp_path / "ok.json"
        p.write_text(json.dumps([{"action": "wait", "mode": "time", "seconds": 1}]), encoding="utf-8")
        steps = load_steps(str(p))
        assert steps[0]["action"] == "wait"


class TestDetectSingleDevice:
    def _fake_run(self, serials):
        import subprocess as sp
        lines = "\n".join(
            ["List of devices attached"] + [f"{s}\tdevice" for s in serials] + [""]
        )
        def fake_run(*a, **kw):
            return type("R", (), {"stdout": lines})()
        return fake_run

    def test_single_device_selected(self, tmp_path, monkeypatch):
        adb = tmp_path / "adb.exe"
        adb.write_text("")
        import app.automation.cli as cli
        monkeypatch.setattr(cli.subprocess, "run", self._fake_run(["EMU1"]))
        assert detect_single_device(str(adb)) == "EMU1"

    def test_no_device_exits(self, tmp_path, monkeypatch):
        adb = tmp_path / "adb.exe"
        adb.write_text("")
        import app.automation.cli as cli
        monkeypatch.setattr(cli.subprocess, "run", self._fake_run([]))
        with pytest.raises(SystemExit, match="没有检测到在线设备"):
            detect_single_device(str(adb))

    def test_multiple_devices_exits_listing_them(self, tmp_path, monkeypatch):
        adb = tmp_path / "adb.exe"
        adb.write_text("")
        import app.automation.cli as cli
        monkeypatch.setattr(cli.subprocess, "run", self._fake_run(["A1", "B2"]))
        with pytest.raises(SystemExit, match="A1"):
            detect_single_device(str(adb))
