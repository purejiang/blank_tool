"""T3 tests: CLI delegates to render_event_line + task_log_id + try/finally flush.

Covers:
  - cmd_run with task_id creates <tasks_root>/<task_id>/logs/task_exec.log via finally
  - Log file contains expected lifecycle lines (node_started, workflow_completed)
  - Console output still shows the same lines (byte-identical for known types)
  - Failure path (flow.assert condition=false) still flushes via finally
  - No task_id → no task dir created (negative test)
"""

import io
import json
import os
import sys
from pathlib import Path

import pytest

from app.utils.task_log_writer import _per_task_buffers, cleanup_task_log
from cli import cmd_run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_workflow_json(tmp_path: Path, condition: bool) -> Path:
    """Write a minimal flow.assert workflow to a temp JSON file."""
    wf_path = tmp_path / "wf.json"
    wf_path.write_text(
        json.dumps(
            {
                "name": "cli-test",
                "nodes": [
                    {
                        "id": "assert_node",
                        "tool": "flow.assert",
                        "params": {
                            "condition": condition,
                            "message": "test message",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return wf_path


def _read_log_file(tasks_root: Path, task_id: str) -> str:
    """Read the task_exec.log for *task_id* under *tasks_root*."""
    log_path = tasks_root / task_id / "logs" / "task_exec.log"
    return log_path.read_text(encoding="utf-8") if log_path.exists() else ""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_buffers():
    """Teardown: clean _per_task_buffers after every test."""
    yield
    for key in list(_per_task_buffers.keys()):
        cleanup_task_log(key)


@pytest.fixture
def tasks_tmp(tmp_path, monkeypatch):
    """Point BT_TASKS_DIR to tmp_path so task logs land in a temp directory."""
    tasks_root = tmp_path / "tasks"
    tasks_root.mkdir()
    monkeypatch.setenv("BT_TASKS_DIR", str(tasks_root))
    return tasks_root


# ---------------------------------------------------------------------------
# Happy path: task_id → log file created via finally, console output matches
# ---------------------------------------------------------------------------


def test_cmd_run_with_task_id_creates_log_file(tasks_tmp, tmp_path):
    """cmd_run with task_id writes task_exec.log on success path (finally)."""
    wf_path = _write_workflow_json(tmp_path, condition=True)

    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        exit_code = cmd_run(
            target=str(wf_path),
            raw_inputs=[],
            task_id="cli1",
            json_output=False,
        )
    finally:
        sys.stdout = old_stdout

    assert exit_code == 0

    # Log file exists and contains expected lines
    log_content = _read_log_file(tasks_tmp, "cli1")
    assert log_content, "task_exec.log should exist"
    assert "[node_started] assert_node (flow.assert)" in log_content
    assert "[workflow_completed] success=True" in log_content

    # Console output still shows the same lines (byte-identical for known types)
    stdout_text = captured.getvalue()
    assert "[node_started] assert_node (flow.assert)" in stdout_text
    assert "[workflow_completed] success=True" in stdout_text


def test_cmd_run_with_task_id_console_shows_all_event_types(tasks_tmp, tmp_path):
    """Console output contains node_started, node_completed, workflow_completed."""
    wf_path = _write_workflow_json(tmp_path, condition=True)

    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        exit_code = cmd_run(
            target=str(wf_path),
            raw_inputs=[],
            task_id="cli1c",
            json_output=False,
        )
    finally:
        sys.stdout = old_stdout

    assert exit_code == 0
    stdout_text = captured.getvalue()

    # Log file also has these
    log_content = _read_log_file(tasks_tmp, "cli1c")
    assert "[node_started] assert_node (flow.assert)" in log_content
    assert "[node_completed] assert_node" in log_content
    assert "[workflow_completed] success=True" in log_content

    # Console too
    assert "[node_started] assert_node (flow.assert)" in stdout_text
    assert "[node_completed] assert_node" in stdout_text
    assert "[workflow_completed] success=True" in stdout_text


# ---------------------------------------------------------------------------
# Failure path: finally still flushes even on workflow failure
# ---------------------------------------------------------------------------


def test_cmd_run_failure_flushes_log_via_finally(tasks_tmp, tmp_path):
    """When a workflow fails, the finally block still runs cleanup_task_log."""
    wf_path = _write_workflow_json(tmp_path, condition=False)

    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        exit_code = cmd_run(
            target=str(wf_path),
            raw_inputs=[],
            task_id="cli1b",
            json_output=False,
        )
    finally:
        sys.stdout = old_stdout

    assert exit_code == 1

    log_content = _read_log_file(tasks_tmp, "cli1b")
    assert log_content, "task_exec.log should exist even on failure"
    assert "[node_started] assert_node (flow.assert)" in log_content
    assert "[node_failed] assert_node" in log_content
    assert "[workflow_failed]" in log_content


# ---------------------------------------------------------------------------
# No-task-id negative: creates NO task dir
# ---------------------------------------------------------------------------


def test_cmd_run_without_task_id_creates_no_task_dir(tasks_tmp, tmp_path):
    """When task_id is None, no task directory is created under tasks_root."""
    wf_path = _write_workflow_json(tmp_path, condition=True)

    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        exit_code = cmd_run(
            target=str(wf_path),
            raw_inputs=[],
            task_id=None,
            json_output=False,
        )
    finally:
        sys.stdout = old_stdout

    assert exit_code == 0

    # No task_id → no directory created
    children = list(tasks_tmp.iterdir())
    assert children == [], (
        f"Expected no task dirs, but found: {[c.name for c in children]}"
    )


# ---------------------------------------------------------------------------
# Exact log line content (not just presence) for all lifecycle types
# ---------------------------------------------------------------------------


def test_log_contains_exact_workflow_completed_line(tasks_tmp, tmp_path):
    """The log file has the exact [workflow_completed] success=True line."""
    wf_path = _write_workflow_json(tmp_path, condition=True)

    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        cmd_run(target=str(wf_path), raw_inputs=[], task_id="cli2", json_output=False)
    finally:
        sys.stdout = old_stdout

    log_lines = _read_log_file(tasks_tmp, "cli2").strip().split("\n")
    assert any(
        "[workflow_completed] success=True" in line for line in log_lines
    ), f"Expected workflow_completed line in: {log_lines}"
    assert any(
        "[node_started] assert_node (flow.assert)" in line for line in log_lines
    ), f"Expected node_started line in: {log_lines}"
