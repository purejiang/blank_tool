#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract tests for the automation run index, orphans and pruning.

Three behaviours are locked here:

1. ``summary.json`` is the history index and ``report.json`` remains the
   fallback — a run written before the index existed must still be listed
   (no history may disappear because of this optimisation).
2. A run the backend was killed in the middle of is VISIBLE as an orphan
   (``orphan: true``) and deletable — that is the only way the user can
   reclaim the space, because there is no report to show it in the UI.
3. A run that IS executing can never be deleted or pruned, and a rule-less
   prune request is refused (a stray call must not wipe the history).
"""

import json
import os
import time

import pytest

from app.automation import runstate
from app.handlers import automation_runs_handler as h


@pytest.fixture
def auto_root(tmp_path, monkeypatch):
    root = tmp_path / "auto_tasks"
    root.mkdir()
    monkeypatch.setenv("BT_AUTO_TASKS_DIR", str(root))
    runstate.reset()
    yield root
    runstate.reset()


def _run_dir(root, task_id):
    d = root / task_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_finished(root, task_id, *, started_at="2026-09-14T10:00:00",
                    with_summary=True, with_report=True, **fields):
    d = _run_dir(root, task_id)
    report = {
        "kind": "automation_run", "task_id": task_id, "device_id": "emulator-5554",
        "package_name": "com.demo", "started_at": started_at,
        "finished_at": "2026-09-14T10:00:10", "duration_ms": 10000,
        "success": True, "cancelled": False, "aborted_by_crash": False,
        "total": 3, "passed": 3, "failed": 0, "steps": [], "logs": [],
        "screenshots": ["a.png", "b.png"], "run_dir": str(d),
    }
    report.update(fields)
    if with_report:
        (d / "report.json").write_text(json.dumps(report), encoding="utf-8")
    if with_summary:
        summary = {k: report.get(k) for k in h.SUMMARY_KEYS}
        summary.update(status="finished", screenshot_count=2)
        (d / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return d, report


def _write_interrupted(root, task_id, *, with_report=False, files=1):
    """A run killed mid-flight: `running` summary (or nothing) + artifacts."""
    d = _run_dir(root, task_id)
    (d / "screenshots").mkdir(exist_ok=True)
    for i in range(files):
        (d / "screenshots" / f"step-{i}.png").write_bytes(b"x" * 100)
    if not with_report:
        summary = {
            "kind": "automation_run", "task_id": task_id, "device_id": "emulator-5554",
            "package_name": "com.demo", "started_at": "2026-09-14T09:00:00",
            "started_ts": time.time() - 3600, "run_dir": str(d),
            "total": 5, "screenshots": [], "status": "running", "screenshot_count": 0,
        }
        (d / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return d


def _ids(res):
    return [r["task_id"] for r in res["runs"]]


def test_prune_runs_is_registered():
    from app.handlers.automation_runs_handler import API_MAP, handle_prune_runs
    assert API_MAP["automation.prune_runs"] is handle_prune_runs
    assert API_MAP["automation.list_runs"] is h.handle_list_runs


# --------------------------------------------------------------- listing --

class TestListRuns:
    def test_empty_root(self, auto_root):
        assert h.handle_list_runs({}, None) == {
            "success": True, "runs": [], "total": 0, "orphans": 0,
        }

    def test_empty_root_on_a_fresh_install(self, auto_root):
        # `get_auto_tasks_root()` creates the root on demand, so a first run
        # against an empty install must be a clean empty list, not an error.
        assert h.handle_list_runs({}, None) == {
            "success": True, "runs": [], "total": 0, "orphans": 0,
        }

    def test_indexed_run_is_listed_from_summary(self, auto_root):
        _write_finished(auto_root, "t-1")
        res = h.handle_list_runs({}, None)
        assert res["success"] is True and res["total"] == 1
        run = res["runs"][0]
        assert run["task_id"] == "t-1"
        assert run["status"] == "finished"
        assert run["orphan"] is False and run["interrupted"] is False
        assert run["screenshot_count"] == 2
        assert run["passed"] == 3
        assert "steps" not in run and "logs" not in run  # summary only

    def test_legacy_report_without_index_still_lists(self, auto_root):
        """Runs written before summary.json existed must not disappear."""
        _write_finished(auto_root, "t-legacy", with_summary=False)
        res = h.handle_list_runs({}, None)
        assert _ids(res) == ["t-legacy"]
        assert res["runs"][0]["status"] == "finished"
        assert res["runs"][0]["screenshot_count"] == 2

    def test_corrupt_index_falls_back_to_report(self, auto_root):
        d, _ = _write_finished(auto_root, "t-broken")
        (d / "summary.json").write_text("{not json", encoding="utf-8")
        res = h.handle_list_runs({}, None)
        assert _ids(res) == ["t-broken"]
        assert res["runs"][0]["status"] == "finished"

    def test_newest_first(self, auto_root):
        _write_finished(auto_root, "t-old", started_at="2026-01-01T00:00:00")
        _write_finished(auto_root, "t-new", started_at="2026-09-14T00:00:00")
        assert _ids(h.handle_list_runs({}, None)) == ["t-new", "t-old"]

    def test_empty_leftover_dir_is_not_listed(self, auto_root):
        _run_dir(auto_root, "t-empty")
        res = h.handle_list_runs({}, None)
        assert res["runs"] == [] and res["total"] == 0

    def test_files_are_not_listed(self, auto_root):
        (auto_root / "stray.txt").write_text("x", encoding="utf-8")
        assert h.handle_list_runs({}, None)["runs"] == []


# -------------------------------------------------------------- orphans --

class TestOrphans:
    def test_interrupted_run_is_visible_and_sized(self, auto_root):
        _write_interrupted(auto_root, "t-dead", files=3)
        res = h.handle_list_runs({}, None)
        assert res["orphans"] == 1
        run = res["runs"][0]
        assert run["task_id"] == "t-dead"
        assert run["orphan"] is True and run["interrupted"] is True
        assert run["running"] is False
        # The whole leftover directory is what deleting it reclaims, so the
        # size covers the artifacts AND the stale index file.
        assert run["size"] >= 300
        assert run["files"] == 4  # 3 screenshots + summary.json
        assert run["started_at"] == "2026-09-14T09:00:00"
        assert run["status"] == "interrupted"

    def test_directory_without_any_index_is_an_orphan(self, auto_root):
        _write_interrupted(auto_root, "t-bare")
        (auto_root / "t-bare" / "summary.json").unlink()
        res = h.handle_list_runs({}, None)
        assert res["orphans"] == 1
        assert res["runs"][0]["status"] == "interrupted"

    def test_killed_between_report_and_index_is_finished(self, auto_root):
        """report.json landed, the summary rewrite did not: trust the report."""
        _write_finished(auto_root, "t-half", with_summary=False)
        d = auto_root / "t-half"
        summary = {"kind": "automation_run", "task_id": "t-half", "status": "running"}
        (d / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        res = h.handle_list_runs({}, None)
        assert res["orphans"] == 0
        run = res["runs"][0]
        assert run["status"] == "finished" and run["success"] is True
        assert run["passed"] == 3  # from report.json, not the stub summary

    def test_live_run_is_running_not_orphan(self, auto_root):
        d = _write_interrupted(auto_root, "t-live")
        runstate.mark_started("t-live", str(d))
        run = h.handle_list_runs({}, None)["runs"][0]
        assert run["running"] is True
        assert run["orphan"] is False and run["interrupted"] is False
        assert run["status"] == "running"
        # …and it stops being an orphan listing the moment it deregisters.
        runstate.mark_finished("t-live")
        assert h.handle_list_runs({}, None)["runs"][0]["status"] == "interrupted"


# --------------------------------------------------------------- delete --

class TestDeleteRun:
    def test_deletes_a_finished_run_and_reports_the_size(self, auto_root):
        d, _ = _write_finished(auto_root, "t-1")
        res = h.handle_delete_run({"task_id": "t-1"}, None)
        assert res["deleted"] is True
        assert res["size"] > 0
        assert not d.exists()

    def test_deletes_an_orphan_without_a_report(self, auto_root):
        """REGRESSION: orphans used to be undeletable (no report.json)."""
        d = _write_interrupted(auto_root, "t-dead")
        res = h.handle_delete_run({"task_id": "t-dead"}, None)
        assert res["deleted"] is True
        assert not d.exists()

    def test_refuses_while_the_run_executes(self, auto_root):
        d = _write_interrupted(auto_root, "t-live")
        runstate.mark_started("t-live", str(d))
        res = h.handle_delete_run({"task_id": "t-live"}, None)
        assert res["deleted"] is False
        assert "executing" in res["error"]
        assert d.exists()

    def test_missing_dir(self, auto_root):
        res = h.handle_delete_run({"task_id": "nope"}, None)
        assert res["deleted"] is False and res["error"] == "run dir not found"

    def test_rejects_traversal(self, auto_root):
        for bad in ("../etc", "a/b", "..", ""):
            assert h.handle_delete_run({"task_id": bad}, None)["deleted"] is False


# ---------------------------------------------------------------- prune --

class TestPruneRuns:
    def test_no_rule_is_refused(self, auto_root):
        _write_finished(auto_root, "t-1")
        res = h.handle_prune_runs({}, None)
        assert res["success"] is False
        assert "no pruning rule" in res["error"]
        assert (auto_root / "t-1").exists()

    def test_keep_last_deletes_the_older_runs(self, auto_root):
        _write_finished(auto_root, "t-1", started_at="2026-01-01T00:00:00")
        _write_finished(auto_root, "t-2", started_at="2026-02-01T00:00:00")
        _write_finished(auto_root, "t-3", started_at="2026-03-01T00:00:00")
        res = h.handle_prune_runs({"keep_last": 1}, None)
        assert res["success"] is True
        assert res["deleted_count"] == 2
        assert sorted(d["task_id"] for d in res["deleted"]) == ["t-1", "t-2"]
        assert res["freed_bytes"] > 0
        assert (auto_root / "t-3").exists()
        assert not (auto_root / "t-1").exists()
        assert _ids(h.handle_list_runs({}, None)) == ["t-3"]

    def test_keep_last_zero_with_orphans_only_clears_orphans(self, auto_root):
        _write_finished(auto_root, "t-1")
        _write_interrupted(auto_root, "t-dead")
        res = h.handle_prune_runs({"orphans_only": True, "keep_last": 0}, None)
        assert res["deleted_count"] == 1
        assert res["deleted"][0]["task_id"] == "t-dead"
        assert res["deleted"][0]["orphan"] is True
        assert (auto_root / "t-1").exists()

    def test_older_than_days(self, auto_root):
        d, _ = _write_finished(auto_root, "t-old")
        (d / "summary.json").write_text(json.dumps({
            "kind": "automation_run", "task_id": "t-old", "status": "finished",
            "started_at": "2026-01-01T00:00:00", "started_ts": time.time() - 86400 * 30,
        }), encoding="utf-8")
        _write_finished(auto_root, "t-new")
        res = h.handle_prune_runs({"older_than_days": 7}, None)
        assert [d["task_id"] for d in res["deleted"]] == ["t-old"]
        assert (auto_root / "t-new").exists()

    def test_orphans_without_a_start_time_use_mtime(self, auto_root):
        d = _write_interrupted(auto_root, "t-bare")
        (d / "summary.json").unlink()
        old = time.time() - 86400 * 30
        os.utime(d, (old, old))
        res = h.handle_prune_runs({"older_than_days": 7}, None)
        assert [x["task_id"] for x in res["deleted"]] == ["t-bare"]

    def test_dry_run_deletes_nothing(self, auto_root):
        _write_finished(auto_root, "t-1", started_at="2026-01-01T00:00:00")
        _write_finished(auto_root, "t-2", started_at="2026-02-01T00:00:00")
        res = h.handle_prune_runs({"keep_last": 1, "dry_run": True}, None)
        assert res["success"] is True and res["dry_run"] is True
        assert res["deleted_count"] == 1
        assert res["freed_bytes"] == 0
        assert (auto_root / "t-1").exists() and (auto_root / "t-2").exists()

    def test_never_deletes_a_running_run(self, auto_root):
        d = _write_interrupted(auto_root, "t-live")
        runstate.mark_started("t-live", str(d))
        res = h.handle_prune_runs({"orphans_only": True}, None)
        assert res["deleted_count"] == 0
        assert res["skipped_active"] == 1
        assert d.exists()

    def test_keep_last_protects_the_newest_even_when_old(self, auto_root):
        """keep_last counts ALL runs, not just the filtered candidates."""
        d, _ = _write_finished(auto_root, "t-new")
        old = time.time() - 86400 * 30
        os.utime(d, (old, old))
        res = h.handle_prune_runs({"keep_last": 1, "older_than_days": 1}, None)
        assert res["deleted_count"] == 0
        assert d.exists()

    def test_invalid_arguments(self, auto_root):
        assert h.handle_prune_runs({"keep_last": "abc"}, None)["success"] is False
        assert h.handle_prune_runs({"older_than_days": -1}, None)["success"] is False
        assert h.handle_prune_runs({"older_than_days": "x"}, None)["success"] is False

    def test_kept_counts_every_surviving_run(self, auto_root):
        _write_finished(auto_root, "t-1", started_at="2026-01-01T00:00:00")
        _write_finished(auto_root, "t-2", started_at="2026-02-01T00:00:00")
        res = h.handle_prune_runs({"keep_last": 1}, None)
        assert res["kept"] == 1
        assert res["errors"] == [] and res["error_count"] == 0


# ------------------------------------------------------- read_run bounds --

class TestReadRunBounds:
    def _with_logs_and_traffic(self, root, task_id, logs, records):
        d, report = _write_finished(root, task_id, logs=logs)
        jsonl = d / "traffic" / "t.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with open(jsonl, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")
        report["traffic_log"] = str(jsonl)
        (d / "report.json").write_text(json.dumps(report), encoding="utf-8")
        return d

    def test_log_limit_keeps_the_tail(self, auto_root):
        logs = [{"ts": i, "text": f"line {i}"} for i in range(10)]
        self._with_logs_and_traffic(auto_root, "t-1", logs, [])
        rep = h.handle_read_run({"task_id": "t-1", "log_limit": 3}, None)["report"]
        assert [entry["text"] for entry in rep["logs"]] == ["line 7", "line 8", "line 9"]
        assert rep["log_total"] == 10
        assert rep["logs_truncated"] is True

    def test_default_keeps_everything_under_the_cap(self, auto_root):
        logs = [{"ts": i, "text": f"line {i}"} for i in range(10)]
        self._with_logs_and_traffic(auto_root, "t-1", logs, [])
        rep = h.handle_read_run({"task_id": "t-1"}, None)["report"]
        assert len(rep["logs"]) == 10
        assert rep["logs_truncated"] is False and rep["logs_included"] is True

    def test_include_logs_false_omits_them(self, auto_root):
        logs = [{"ts": i, "text": f"line {i}"} for i in range(10)]
        self._with_logs_and_traffic(auto_root, "t-1", logs, [])
        rep = h.handle_read_run(
            {"task_id": "t-1", "include_logs": False}, None)["report"]
        assert rep["logs"] == []
        assert rep["logs_included"] is False
        assert rep["log_total"] == 10

    def test_log_limit_zero_means_unlimited(self, auto_root):
        logs = [{"ts": i, "text": f"line {i}"} for i in range(7)]
        self._with_logs_and_traffic(auto_root, "t-1", logs, [])
        rep = h.handle_read_run({"task_id": "t-1", "log_limit": 0}, None)["report"]
        assert len(rep["logs"]) == 7

    def test_traffic_limit_still_applies(self, auto_root):
        records = [{"ts": i, "method": "GET", "url": f"https://x/{i}"} for i in range(5)]
        self._with_logs_and_traffic(auto_root, "t-1", [], records)
        rep = h.handle_read_run(
            {"task_id": "t-1", "traffic_limit": 2}, None)["report"]
        assert len(rep["traffic"]) == 2
        assert rep["traffic_total"] == 5
        assert rep["traffic_truncated"] is True


class TestTrafficScanBudget:
    def test_read_traffic_stops_at_the_byte_budget(self, tmp_path):
        path = tmp_path / "big.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for i in range(500):
                f.write(json.dumps({"ts": i, "method": "GET", "url": "u" * 200}) + "\n")
        out = h._read_traffic(str(path), 1000, max_bytes=4096)
        assert out["scan_limited"] is True
        assert out["truncated"] is True
        assert 0 < len(out["entries"]) < 500

    def test_export_reader_has_its_own_default(self, tmp_path):
        path = tmp_path / "small.jsonl"
        path.write_text('{"ts":1,"method":"GET","url":"a"}\n', encoding="utf-8")
        out = h._read_traffic_full(str(path), 10)
        assert out["entries"][0]["url"] == "a"
        assert out["scan_limited"] is False
