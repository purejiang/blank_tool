"""Tests: run_history recording hook in app.workflow.runner.run_workflow.

Covers: a top-level run lands in the history store with the full record
shape; the ``source`` field reflects template name vs file path vs inline;
and a recording failure NEVER changes the run's result.
"""

import json

import pytest

from app.history import store as history_store
from app.workflow.definition import WorkflowDefinition
from app.workflow.runner import run_workflow


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    out = tmp_path / "output"
    monkeypatch.setenv("BT_OUTPUT_DIR", str(out))
    monkeypatch.setenv("BT_SERVER_CONFIG", str(tmp_path / "nope.json"))
    return out


def _definition():
    return WorkflowDefinition.from_dict(
        {
            "name": "hist-wf",
            "nodes": [
                {
                    "id": "log",
                    "tool": "flow.log",
                    "params": {"message": "hi"},
                }
            ],
        }
    )


def test_run_is_recorded_with_full_shape(output_dir):
    result = run_workflow(
        _definition(), {"inputs": {"x": 1}, "path": "wf.json"}, None, "task-1"
    )
    assert result["success"] is True

    runs = history_store.list_runs()
    assert len(runs) == 1
    summary = runs[0]
    assert summary["workflow_name"] == "hist-wf"
    assert summary["source"] == "wf.json"
    assert summary["success"] is True
    assert summary["task_id"] == "task-1"

    full = history_store.get_run(summary["run_id"])
    assert full["inputs"] == {"x": 1}
    assert "log" in full["node_results"]
    assert full["node_results"]["log"]["error"] is None
    assert full["ended_at"] >= full["started_at"]


def test_source_falls_back_to_inline(output_dir):
    run_workflow(_definition(), {"inputs": {}}, None, None)
    runs = history_store.list_runs()
    assert runs[0]["source"] == "inline"


def test_failed_run_is_recorded_with_error(output_dir):
    definition = WorkflowDefinition.from_dict(
        {
            "name": "boom-wf",
            "nodes": [
                {
                    "id": "check",
                    "tool": "flow.assert",
                    "params": {"condition": False, "message": "nope"},
                }
            ],
        }
    )
    result = run_workflow(definition, {"inputs": {}}, None, None)
    assert result["success"] is False

    runs = history_store.list_runs()
    assert len(runs) == 1
    assert runs[0]["success"] is False
    assert "nope" in runs[0]["error"]


def test_recording_failure_does_not_break_run(output_dir, monkeypatch):
    def _boom(record):
        raise OSError("disk full")

    monkeypatch.setattr(history_store, "record_run", _boom)
    result = run_workflow(_definition(), {"inputs": {}}, None, None)
    assert result["success"] is True
