"""T2 tests: handler wiring — workflow.execute passes task_log_id.

Covers:
  - workflow.execute with an inline definition + task_id: buffer gains
    lifecycle lines; callback receives events (tee is additive, not stealing).
  - workflow.execute on a SAVED workflow + task_id: same dual-assertion.
  - workflow.execute WITHOUT task_id: no buffer key created; execution
    succeeds (logging must never break execution).
  - Monkeypatched BT_TASKS_DIR to tmp_path so cleanup_task_log flushes
    outside the repo.
"""

import os

import pytest

from app.workflow.store import FileWorkflowStore
from app.utils.task_log_writer import _per_task_buffers, cleanup_task_log
from app.workflow.definition import WorkflowDefinition

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

import app.handlers.workflow_handler as wh


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _monkeypatch_tasks_dir(monkeypatch, tmp_path):
    """Redirect task-log output into a temp dir so QA artifacts stay out of
    the repo."""
    tasks_dir = tmp_path / "tasks"
    os.makedirs(tasks_dir, exist_ok=True)
    monkeypatch.setenv("BT_TASKS_DIR", str(tasks_dir))
    yield
    # Teardown: flush + free all buffers
    for key in list(_per_task_buffers.keys()):
        cleanup_task_log(key)


@pytest.fixture(autouse=True)
def _monkeypatch_workflows_dir(monkeypatch, tmp_path):
    """Redirect the workflow store to a temp dir."""
    workflows_dir = tmp_path / "workflows"
    os.makedirs(workflows_dir, exist_ok=True)
    monkeypatch.setenv("BT_WORKFLOWS_DIR", str(workflows_dir))
    # Reset the workflow_handler module's store singleton so it picks up the
    # monkeypatched env var.
    wh._store = None
    yield
    wh._store = None


# ---------------------------------------------------------------------------
# Minimal inline workflow definition: a single flow.assert(true)
# ---------------------------------------------------------------------------

_MINIMAL_DEFINITION = {
    "name": "test_minimal_wiring",
    "nodes": [
        {
            "id": "assert_ok",
            "tool": "flow.assert",
            "params": {"condition": True},
        }
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _buffer_lines(task_id: str):
    """Return the list of buffered log lines for *task_id* (or empty)."""
    return list(_per_task_buffers.get(task_id, []))


def _first_line_matching(lines, fragment: str):
    """Return the first buffered line containing *fragment*, or None."""
    for line in lines:
        if fragment in line:
            return line
    return None


# ===================================================================
# workflow.execute — with task_id
# ===================================================================


def test_workflow_execute_with_task_id_buffers_lifecycle_events():
    """Given: workflow.execute with a valid inline definition + task_id.
    When: called with a capture-list stream handler.
    Then: _per_task_buffers["wt1"] contains [node_started] and
          [workflow_completed] success=True.
    """
    captured = []
    result = wh.handle_execute(
        {"definition": _MINIMAL_DEFINITION, "task_id": "wt1"},
        stream_handler=captured.append,
    )

    assert result["success"] is True

    lines = _buffer_lines("wt1")
    assert len(lines) >= 2, f"expected >=2 lifecycle lines, got {len(lines)}: {lines}"

    started = _first_line_matching(lines, "[node_started]")
    assert started is not None, f"missing node_started in: {lines}"
    assert "assert_ok" in started
    assert "flow.assert" in started

    completed = _first_line_matching(lines, "[workflow_completed]")
    assert completed is not None, f"missing workflow_completed in: {lines}"
    assert "success=True" in completed


def test_workflow_execute_with_task_id_does_not_steal_callback_events():
    """Given: workflow.execute with task_id.
    When: called with a capture-list stream handler.
    Then: the callback also received the event dicts (tee is additive).
    """
    captured = []
    wh.handle_execute(
        {"definition": _MINIMAL_DEFINITION, "task_id": "wt1"},
        stream_handler=captured.append,
    )

    assert len(captured) >= 2, (
        f"callback should receive >=2 events, got {len(captured)}: {captured}"
    )

    # At least node_started + workflow_completed must be present.
    event_types = [e["type"] for e in captured]
    assert "node_started" in event_types, f"missing node_started in: {captured}"
    assert "workflow_completed" in event_types, (
        f"missing workflow_completed in: {captured}"
    )

    # Root handler: workflow_id == task_log_id, so node_id is un-prefixed.
    started_events = [e for e in captured if e["type"] == "node_started"]
    assert any(
        e["node_id"] == "assert_ok" for e in started_events
    ), f"node_id should be un-prefixed in callback payloads: {started_events}"


# ===================================================================
# workflow.execute on a saved workflow — with task_id
# ===================================================================


def _save_minimal_workflow(store: FileWorkflowStore, name: str):
    """Save a minimal flow.assert(true) workflow into *store* under *name*."""
    definition = WorkflowDefinition.from_dict({**_MINIMAL_DEFINITION, "name": name})
    store.save(definition, {"description": "minimal test workflow", "tags": []})


def test_saved_workflow_execute_with_task_id_buffers_lifecycle_events():
    """Given: a saved minimal workflow + workflow.execute with task_id.
    When: called with a capture-list stream handler.
    Then: _per_task_buffers["tmpl1"] contains [node_started] and
          [workflow_completed] success=True.
    """
    store = FileWorkflowStore()  # uses monkeypatched BT_WORKFLOWS_DIR
    wh._store = store
    _save_minimal_workflow(store, "minimal_assert")

    captured = []
    result = wh.handle_execute(
        {"name": "minimal_assert", "task_id": "tmpl1"},
        stream_handler=captured.append,
    )

    assert result["success"] is True

    lines = _buffer_lines("tmpl1")
    assert len(lines) >= 2, f"expected >=2 lifecycle lines, got {len(lines)}: {lines}"

    started = _first_line_matching(lines, "[node_started]")
    assert started is not None, f"missing node_started in: {lines}"
    assert "flow.assert" in started

    completed = _first_line_matching(lines, "[workflow_completed]")
    assert completed is not None, f"missing workflow_completed in: {lines}"
    assert "success=True" in completed


def test_saved_workflow_execute_with_task_id_does_not_steal_callback_events():
    """Given: workflow.execute on a saved workflow, with task_id.
    When: called with a capture-list stream handler.
    Then: the callback also received the event dicts (tee is additive).
    """
    store = FileWorkflowStore()
    wh._store = store
    _save_minimal_workflow(store, "minimal_assert")

    captured = []
    wh.handle_execute(
        {"name": "minimal_assert", "task_id": "tmpl1"},
        stream_handler=captured.append,
    )

    assert len(captured) >= 2, (
        f"callback should receive >=2 events, got {len(captured)}: {captured}"
    )

    event_types = [e["type"] for e in captured]
    assert "node_started" in event_types, f"missing node_started in: {captured}"
    assert "workflow_completed" in event_types, (
        f"missing workflow_completed in: {captured}"
    )


# ===================================================================
# regression: workflow.execute WITHOUT task_id
# ===================================================================


def test_workflow_execute_without_task_id_no_buffer_created():
    """Given: workflow.execute WITHOUT a task_id.
    When: called.
    Then: no _per_task_buffers key is created and execution succeeds.
    """
    captured = []
    result = wh.handle_execute(
        {"definition": _MINIMAL_DEFINITION},
        stream_handler=captured.append,
    )

    assert result["success"] is True
    # Verify no key leaked into the buffer dict for a "None" or empty task_id.
    for key in list(_per_task_buffers.keys()):
        assert "wt" not in str(key), f"unexpected buffer key: {key}"


def test_workflow_execute_without_task_id_callback_not_invoked():
    """Given: workflow.execute WITHOUT a task_id.
    When: called with a capture-list callback.
    Then: the callback is NOT invoked (no workflow_stream is created), but
          execution succeeds — logging must never break execution.
    """
    captured = []
    result = wh.handle_execute(
        {"definition": _MINIMAL_DEFINITION},
        stream_handler=captured.append,
    )

    assert result["success"] is True
    # Without task_id, no WorkflowStreamHandler is constructed, so the
    # engine never routes events through it.  The stream_handler is
    # available in ExecutionContext but the engine only emits through
    # workflow_stream.  This is existing behavior — NOT changed by T2.
    assert len(captured) == 0, (
        f"without task_id no events should reach callback, got: {captured}"
    )
