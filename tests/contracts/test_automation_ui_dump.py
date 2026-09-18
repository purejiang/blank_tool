#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract tests for ``app.automation.elements.ui_dump``.

`ui_dump` is the picker's data source (device dump → pull → local XML). Its
retry loop used to compare a single attempt's cost against an always-false
expression (``time.time() + timeout_ms/1000.0 < 0``), so:
  * ``timeout_ms`` was dead, and
  * the retry count was the only thing bounding the call.
These tests pin the real budget, the retry-once behaviour and the cleanup of
both temp files (a leftover local file per failed poll would grow the output
directory without bound).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from app.automation import elements  # noqa: E402

XML = '<?xml version="1.0"?><hierarchy><node text="ok" /></hierarchy>'


class FakeAdb:
    """Scripted ``run_adb``: per-call results + a call log."""

    def __init__(self, dump_rc=0, pull_rc=0, xml=XML, on_dump=None):
        self.dump_rc = dump_rc
        self.pull_rc = pull_rc
        self.xml = xml
        self.calls = []
        self.on_dump = on_dump

    def __call__(self, device_id, args, *a, **k):
        self.calls.append(list(args))
        if "uiautomator" in args:
            if self.on_dump:
                self.on_dump(len([c for c in self.calls if "uiautomator" in c]))
            return {"returncode": self.dump_rc, "stdout": "", "stderr": "dump failed"}
        if args[:1] == ["pull"]:
            dest = args[2]
            if self.pull_rc == 0:
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(self.xml)
            return {"returncode": self.pull_rc, "stdout": "", "stderr": "pull failed"}
        return {"returncode": 0, "stdout": "", "stderr": ""}

    def count(self, kind):
        if kind == "dump":
            return len([c for c in self.calls if "uiautomator" in c])
        if kind == "pull":
            return len([c for c in self.calls if c[:1] == ["pull"]])
        return len([c for c in self.calls if c[:2] == ["shell", "rm"]])


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    d = tmp_path / "out"
    monkeypatch.setattr(elements, "get_output_dir", lambda: str(d))
    return d


def _install(monkeypatch, adb):
    monkeypatch.setattr(elements, "run_adb", adb)
    return adb


class TestUiDump:
    def test_returns_the_xml_on_the_first_attempt(self, monkeypatch, out_dir):
        adb = _install(monkeypatch, FakeAdb())
        ok, xml = elements.ui_dump("emulator-5554")
        assert ok is True and xml == XML
        assert adb.count("dump") == 1
        assert adb.count("pull") == 1
        # the DEVICE temp file is removed even though the success path returns
        # from inside the try (it used to be left on /sdcard, one per pick)
        assert adb.count("rm") >= 1
        # and no local temp file survives
        ui_dir = out_dir / "ui"
        assert not ui_dir.is_dir() or os.listdir(ui_dir) == []

    def test_retries_once_when_the_dump_fails(self, monkeypatch, out_dir):
        adb = FakeAdb()
        state = {"n": 0}

        def on_dump(n):
            state["n"] = n
            adb.dump_rc = 1 if n == 1 else 0

        adb.on_dump = on_dump
        _install(monkeypatch, adb)

        ok, xml = elements.ui_dump("dev", retries=1)
        assert (ok, xml) == (True, XML)
        assert adb.count("dump") == 2

    def test_reports_the_last_error_when_every_attempt_fails(self, monkeypatch, out_dir):
        adb = _install(monkeypatch, FakeAdb(dump_rc=1))
        ok, err = elements.ui_dump("dev", retries=1)
        assert ok is False
        assert "dump failed" in err
        assert adb.count("dump") == 2          # retried once
        assert adb.count("pull") == 0

    def test_empty_xml_is_a_failure_and_retries(self, monkeypatch, out_dir):
        adb = _install(monkeypatch, FakeAdb(xml="   \n"))
        ok, err = elements.ui_dump("dev", retries=1)
        assert ok is False
        assert "empty ui xml" in err
        assert adb.count("pull") == 2

    def test_pull_failure_reports_the_pull_error(self, monkeypatch, out_dir):
        adb = _install(monkeypatch, FakeAdb(pull_rc=1))
        ok, err = elements.ui_dump("dev", retries=0)
        assert ok is False
        assert "pull failed" in err
        assert adb.count("pull") == 1

    def test_timeout_budget_stops_the_retries(self, monkeypatch, out_dir):
        """timeout_ms is a budget for the WHOLE call, not a per-attempt cost.

        With a zero budget the first failed attempt must end the loop instead
        of burning the full retry count.
        """
        adb = _install(monkeypatch, FakeAdb(dump_rc=1))
        ok, _err = elements.ui_dump("dev", timeout_ms=0, retries=5)
        assert ok is False
        assert adb.count("dump") == 1, "a spent budget must stop the retry loop"

    def test_a_healthy_budget_still_retries(self, monkeypatch, out_dir):
        adb = _install(monkeypatch, FakeAdb(dump_rc=1))
        elements.ui_dump("dev", timeout_ms=60000, retries=2)
        assert adb.count("dump") == 3          # first + 2 retries

    @pytest.mark.parametrize("retries", [0, -1, None])
    def test_at_least_one_attempt_always_runs(self, monkeypatch, out_dir, retries):
        adb = _install(monkeypatch, FakeAdb())
        if retries is None:
            ok, xml = elements.ui_dump("dev")
        else:
            ok, xml = elements.ui_dump("dev", retries=retries)
        assert (ok, xml) == (True, XML)
        assert adb.count("dump") == 1

    def test_local_temp_file_is_removed_even_on_pull_failure(self, monkeypatch, out_dir):
        _install(monkeypatch, FakeAdb(pull_rc=1))
        elements.ui_dump("dev", retries=0)
        ui_dir = out_dir / "ui"
        leftovers = os.listdir(ui_dir) if ui_dir.is_dir() else []
        assert leftovers == [], f"temp ui files left behind: {leftovers}"

    def test_remote_temp_name_is_unique_per_call(self, monkeypatch, out_dir):
        """A fixed remote name would make two concurrent dumps overwrite each
        other's file on the device."""
        seen = []

        def record(device_id, args, *a, **k):
            if "uiautomator" in args:
                seen.append(args[args.index("dump") + 2])
            if args[:1] == ["pull"]:
                with open(args[2], "w", encoding="utf-8") as f:
                    f.write(XML)
            return {"returncode": 0, "stdout": "", "stderr": ""}

        _install(monkeypatch, record)
        elements.ui_dump("dev")
        elements.ui_dump("dev")
        assert len(seen) == 2 and seen[0] != seen[1]
