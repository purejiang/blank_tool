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

    def test_list_offset_beyond_the_end_returns_nothing(self, output_dir):
        for _ in range(3):
            history_store.record_run(_record())
            time.sleep(0.01)

        assert history_store.list_runs(offset=99) == []

    def test_list_parses_only_the_requested_window(self, output_dir, monkeypatch):
        """A big history dir must not be fully parsed just to list one page.

        The ordering comes from ``os.stat`` alone; only the window handed back
        to the caller is read from disk.
        """
        for index in range(6):
            history_store.record_run(_record(f"wf-{index}"))
            time.sleep(0.02)

        read_paths = []
        real_read = history_store._read

        def counting_read(path):
            read_paths.append(path)
            return real_read(path)

        monkeypatch.setattr(history_store, "_read", counting_read)

        runs = history_store.list_runs(limit=2, offset=1)

        assert [run["workflow_name"] for run in runs] == ["wf-4", "wf-3"]
        assert len(read_paths) == 2, (
            f"list_runs parsed {len(read_paths)} files for a 2-run window"
        )

    def test_list_breaks_mtime_ties_by_file_name(self, output_dir):
        """Equal mtimes are ordered by file name so the listing is deterministic."""
        first = history_store.record_run(_record("tie-a"))
        second = history_store.record_run(_record("tie-b"))

        history_dir = output_dir / "history"
        stamp = time.time()
        os.utime(history_dir / f"{first}.json", (stamp, stamp))
        os.utime(history_dir / f"{second}.json", (stamp, stamp))

        listed = [run["run_id"] for run in history_store.list_runs()]
        # Same mtime → ascending "<run_id>.json" name order.
        assert listed == sorted([first, second])

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

    def test_max_bytes_prunes_oldest_until_under_the_cap(
        self, output_dir, tmp_path, monkeypatch
    ):
        """The byte cap bounds one huge run, not just the run count."""
        history_dir = output_dir / "history"
        first = history_store.record_run(_record())
        record_size = (history_dir / f"{first}.json").stat().st_size
        assert record_size > 0

        # Cap the directory at (roughly) a single record.
        _write_config(tmp_path, monkeypatch, {"max_bytes": record_size})

        ids = [first]
        for _ in range(4):
            ids.append(history_store.record_run(_record()))
            # Distinct mtimes so "oldest" is deterministic.
            time.sleep(0.02)

        remaining = sorted(path.name for path in history_dir.glob("*.json"))
        assert remaining == [f"{ids[-1]}.json"], (
            f"byte cap kept {remaining}, expected only the newest record"
        )
        assert history_store.get_run(ids[-2]) is None
        assert history_store.get_run(ids[-1]) is not None

    def test_max_bytes_zero_prunes_every_record(
        self, output_dir, tmp_path, monkeypatch
    ):
        _write_config(tmp_path, monkeypatch, {"max_bytes": 0})
        history_store.record_run(_record())
        history_store.record_run(_record())

        history_dir = output_dir / "history"
        assert list(history_dir.glob("*.json")) == []

    def test_count_cap_still_applies_with_a_large_byte_cap(
        self, output_dir, tmp_path, monkeypatch
    ):
        _write_config(
            tmp_path, monkeypatch, {"max_runs": 2, "max_bytes": 10**9}
        )
        for _ in range(4):
            history_store.record_run(_record())
            time.sleep(0.02)

        assert len(history_store.list_runs()) == 2


class TestOrphanTmpSweep:
    def test_stale_orphan_tmp_is_swept_fresh_one_is_kept(self, output_dir):
        history_dir = output_dir / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        stale = history_dir / "stale.json.tmp"
        fresh = history_dir / "fresh.json.tmp"
        stale.write_text("{}", encoding="utf-8")
        fresh.write_text("{}", encoding="utf-8")
        old = time.time() - 3600
        os.utime(stale, (old, old))

        # Any write triggers the sweep (record_run -> _prune).
        history_store.record_run(_record())

        assert not stale.exists(), "an abandoned tmp file must be swept"
        assert fresh.exists(), "a young tmp file may still be in flight"

    def test_clear_runs_removes_orphan_tmp_files(self, output_dir):
        run_id = history_store.record_run(_record())
        history_dir = output_dir / "history"
        orphan = history_dir / "orphan.json.tmp"
        orphan.write_text("{}", encoding="utf-8")

        assert history_store.clear_runs() == 2

        assert not orphan.exists()
        assert history_store.get_run(run_id) is None
        assert sorted(path.name for path in history_dir.iterdir()) == []

    def test_list_runs_ignores_tmp_files(self, output_dir):
        history_store.record_run(_record("real"))
        (output_dir / "history" / "pending.json.tmp").write_text(
            "{}", encoding="utf-8"
        )

        assert [run["workflow_name"] for run in history_store.list_runs()] == ["real"]


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
