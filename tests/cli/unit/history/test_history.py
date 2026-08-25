"""Tests: run-history store + history.* handlers.

Covers the store contract (record / list / get / delete / clear, retention
pruning, disabled switch, corrupt-file tolerance, run-id path safety) and
the handler surface (``history.list/get/delete/clear``).  Every test points
``BT_OUTPUT_DIR`` (and ``BT_SERVER_CONFIG`` where config matters) at
``tmp_path`` so no real output directory is touched.
"""

import json
import os
import time
from pathlib import Path

import pytest

from app.common.exceptions import ToolException
from app.handlers.history_handler import (
    history_clear,
    history_delete,
    history_get,
    history_list,
)
from app.history import store as history_store


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    """Isolate the history dir under tmp_path via BT_OUTPUT_DIR."""
    out = tmp_path / "output"
    monkeypatch.setenv("BT_OUTPUT_DIR", str(out))
    # No server.config.json in play unless a test writes one.
    monkeypatch.setenv("BT_SERVER_CONFIG", str(tmp_path / "nope.json"))
    return out


def _record(name="wf", success=True, error=None, **extra):
    record = {
        "run_id": history_store.new_run_id(),
        "workflow_name": name,
        "source": "test",
        "started_at": "2026-08-24T10:00:00",
        "ended_at": "2026-08-24T10:00:01",
        "duration_ms": 1000,
        "inputs": {"a": 1},
        "node_results": {"n1": {"outputs": {}, "error": None,
                                "duration_ms": 5}},
        "success": success,
        "error": error,
    }
    record.update(extra)
    return record


def _write_config(tmp_path, monkeypatch, section):
    cfg = tmp_path / "server.config.json"
    cfg.write_text(json.dumps({"history": section}), encoding="utf-8")
    monkeypatch.setenv("BT_SERVER_CONFIG", str(cfg))


class TestRecordAndQuery:
    def test_record_then_get_roundtrip(self, output_dir):
        record = _record()
        run_id = history_store.record_run(record)

        loaded = history_store.get_run(run_id)
        assert loaded["run_id"] == run_id
        assert loaded["workflow_name"] == "wf"
        assert loaded["node_results"]["n1"]["duration_ms"] == 5

    def test_list_newest_first_with_summaries(self, output_dir):
        ids = []
        for name in ("first", "second", "third"):
            ids.append(history_store.record_run(_record(name)))
            # Distinct mtimes so ordering is deterministic.
            time.sleep(0.02)

        runs = history_store.list_runs()
        assert [r["workflow_name"] for r in runs] == ["third", "second", "first"]
        # Summary projection: no heavy keys.
        assert "node_results" not in runs[0]
        assert "inputs" not in runs[0]

    def test_list_limit_and_offset(self, output_dir):
        for _ in range(5):
            history_store.record_run(_record())
            time.sleep(0.01)

        assert len(history_store.list_runs(limit=2)) == 2
        assert len(history_store.list_runs(limit=0)) == 5
        assert len(history_store.list_runs(limit=2, offset=4)) == 1

    def test_get_unknown_run_returns_none(self, output_dir):
        assert history_store.get_run(history_store.new_run_id()) is None

    def test_get_malformed_run_id_raises(self, output_dir):
        with pytest.raises(ValueError):
            history_store.get_run("../../etc/passwd")

    def test_delete_run(self, output_dir):
        run_id = history_store.record_run(_record())
        assert history_store.delete_run(run_id) is True
        assert history_store.get_run(run_id) is None
        assert history_store.delete_run(run_id) is False

    def test_clear_runs(self, output_dir):
        for _ in range(3):
            history_store.record_run(_record())
        assert history_store.clear_runs() == 3
        assert history_store.list_runs() == []

    def test_corrupt_file_is_skipped_in_list(self, output_dir):
        history_store.record_run(_record("good"))
        bad = output_dir / "history" / "bad.json"
        bad.write_text("{not json", encoding="utf-8")

        runs = history_store.list_runs()
        assert [r["workflow_name"] for r in runs] == ["good"]


class TestRetentionAndSwitch:
    def test_max_runs_prunes_oldest(self, output_dir, tmp_path, monkeypatch):
        _write_config(tmp_path, monkeypatch, {"max_runs": 3})
        ids = []
        for _ in range(5):
            ids.append(history_store.record_run(_record()))
            time.sleep(0.02)

        history_dir = output_dir / "history"
        remaining = sorted(p.name for p in history_dir.glob("*.json"))
        assert len(remaining) == 3
        # The two oldest run ids are gone.
        assert history_store.get_run(ids[0]) is None
        assert history_store.get_run(ids[1]) is None
        assert history_store.get_run(ids[-1]) is not None

    def test_disabled_switch_skips_writes(self, output_dir, tmp_path, monkeypatch):
        _write_config(tmp_path, monkeypatch, {"enabled": False})
        assert history_store.record_run(_record()) is None
        assert history_store.list_runs() == []


class TestHandlers:
    def test_history_list(self, output_dir):
        history_store.record_run(_record("one"))
        result = history_list({}, None)
        assert len(result["runs"]) == 1
        assert result["runs"][0]["workflow_name"] == "one"

    def test_history_get(self, output_dir):
        run_id = history_store.record_run(_record())
        result = history_get({"run_id": run_id}, None)
        assert result["run"]["run_id"] == run_id

    def test_history_get_unknown_raises(self, output_dir):
        with pytest.raises(ToolException, match="run not found"):
            history_get({"run_id": history_store.new_run_id()}, None)

    def test_history_get_missing_param_raises(self, output_dir):
        with pytest.raises(ToolException, match="run_id"):
            history_get({}, None)

    def test_history_delete(self, output_dir):
        run_id = history_store.record_run(_record())
        assert history_delete({"run_id": run_id}, None) == {"deleted": run_id}
        with pytest.raises(ToolException, match="run not found"):
            history_delete({"run_id": run_id}, None)

    def test_history_clear(self, output_dir):
        history_store.record_run(_record())
        history_store.record_run(_record())
        assert history_clear({}, None) == {"cleared": 2}
