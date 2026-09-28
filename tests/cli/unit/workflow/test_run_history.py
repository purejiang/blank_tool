"""Tests: run_history recording hook in app.workflow.runner.run_workflow.

Covers: a top-level run lands in the history store with the full record
shape; the ``source`` field reflects template name vs file path vs inline;
``task_name`` carries the saved task definition for ``task.execute`` runs and
stays ``null`` otherwise; the per-run artifact directory (``run_dir``) is on
both the wire payload and the record and is linked to the execution identity
via ``exec_run_id``; and a recording failure NEVER changes the run's result.
"""

import json
import os

import pytest

from app.env import get_output_dir
from app.history import store as history_store
from app.workflow.definition import WorkflowDefinition
from app.workflow.rundir import safe_slug
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

    # WP2 (#4): the payload carries the per-run artifact directory.  With no
    # explicit run_id the identity falls back to the task id.
    assert result["run_dir"] == os.path.join(
        get_output_dir(), "runs", safe_slug("task-1")
    )

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
    assert full["run_dir"] == result["run_dir"]
    assert full["exec_run_id"] == "task-1"


def test_payload_run_dir_is_derivable_from_the_exec_identity(output_dir):
    """The IPC request id is not a valid history file id — only exec_run_id."""
    exec_id = "1700000000000-0.1234"
    result = run_workflow(_definition(), {"inputs": {}}, None, "task-1", exec_id)

    expected = os.path.join(get_output_dir(), "runs", safe_slug(exec_id))
    assert result["run_dir"] == expected
    assert os.path.isdir(expected)

    runs = history_store.list_runs()
    assert len(runs) == 1
    record_id = runs[0]["run_id"]
    # The record/file id stays a uuid4 hex; the two identities are linked by
    # exec_run_id instead of being conflated.
    assert record_id != exec_id
    assert history_store.get_run(record_id)["exec_run_id"] == exec_id


def test_list_summary_is_light_but_carries_status_cancelled_run_dir(output_dir):
    """WP2 (#11): the summary gains status/cancelled/run_dir, not heavy keys."""
    run_workflow(_definition(), {"inputs": {"x": 1}}, None, "task-1")

    summary = history_store.list_runs()[0]
    assert summary["status"] == "succeeded"
    assert summary["cancelled"] is False
    assert summary["run_dir"] == os.path.join(
        get_output_dir(), "runs", safe_slug("task-1")
    )
    # A plain run has no task definition behind it.
    assert summary["task_name"] is None
    assert "node_results" not in summary
    assert "inputs" not in summary


def test_task_name_is_recorded_for_task_runs(output_dir):
    """`task.execute` passes task_name; plain runs leave it null."""
    run_workflow(
        _definition(), {"inputs": {}}, None, "task-1", task_name="nightly-audit"
    )

    runs = history_store.list_runs()
    assert runs[0]["task_name"] == "nightly-audit"
    full = history_store.get_run(runs[0]["run_id"])
    assert full["task_name"] == "nightly-audit"


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
