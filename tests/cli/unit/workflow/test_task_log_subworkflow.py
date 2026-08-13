"""T4 tests: sub-workflow task log propagation via workflow.run.

When context.task_id is set, child node lifecycle events are teed into
the per-task log buffer with namespaced node_ids (T1 namespacing rule).
"""

import os

import pytest

from app.template.store import FileTemplateStore
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.engine import ExecutionContext, WorkflowEngine
from app.workflow.streaming import WorkflowStreamHandler
from app.utils.task_log_writer import _per_task_buffers, cleanup_task_log

# ─────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────


def _node(node_id, tool="flow.log", **overrides) -> WorkflowNode:
    data = {"id": node_id, "tool": tool}
    data.update(overrides)
    return WorkflowNode(**data)


def _save_template(store: FileTemplateStore, name: str, definition: WorkflowDefinition):
    store.save(name, definition, {"description": f"auto: {name}"})


@pytest.fixture
def tasks_tmp(tmp_path, monkeypatch):
    """Point BT_TASKS_DIR to tmp_path so cleanup_task_log can flush.

    CRITICAL: must be an ABSOLUTE path — resolve_path in env.py resolves
    relative paths against the cli ROOT, doubling up.
    """
    tasks_root = tmp_path / "tasks"
    tasks_root.mkdir()
    monkeypatch.setenv("BT_TASKS_DIR", str(tasks_root))
    return tasks_root


# ─────────────────────────────────────────────────────────────────────────
# happy: child events land in buffer with namespaced node_ids
# ─────────────────────────────────────────────────────────────────────────


def test_subworkflow_child_events_namespaced_in_buffer(tasks_tmp, tmp_path):
    """Given a child template (flow.log "hello") and a parent with
    workflow.run + task_id="sub1", When context.stream_handler is None
    but context.task_id is set, Then child node events appear in
    _per_task_buffers["sub1"] with namespaced node_ids, and parent
    events are un-prefixed."""
    store_dir = tmp_path / "templates"
    store_dir.mkdir()
    store = FileTemplateStore(templates_dir=str(store_dir))

    # Child: single flow.log node
    child_def = WorkflowDefinition(
        name="child-log",
        nodes=[
            _node("log1", "flow.log",
                  params={"message": "hello from child"}),
        ],
    )
    _save_template(store, "child-log", child_def)

    # Parent: workflow.run -> child-log
    parent_def = WorkflowDefinition(
        name="parent-log",
        nodes=[
            _node("run_child", "workflow.run",
                  params={"template": "child-log", "inputs": {}}),
        ],
    )

    # Parent stream handler — tees parent events into buffer.
    # callback=None → no IPC; task_log_id="sub1" → tee fires.
    parent_stream = WorkflowStreamHandler(
        workflow_id="sub1",
        callback=None,
        task_log_id="sub1",
    )

    ctx = ExecutionContext(
        work_dir=str(tmp_path),
        task_id="sub1",
        template_store=store,
        workflow_stream=parent_stream,
        stream_handler=None,  # <-- no IPC callback, only task_id set
    )

    result = WorkflowEngine().execute(parent_def, {}, ctx)

    assert result.success is True, f"workflow failed: {result.error}"

    buffer = _per_task_buffers.get("sub1", [])
    buffer_text = "\n".join(buffer)

    # ── child event: namespaced node_id ─────────────────────────────
    # workflow_id="sub1/run_child" != task_log_id="sub1" →
    # T1 rule renders node_id as "sub1/run_child/log1"
    assert "sub1/run_child/log1" in buffer_text, (
        f"expected namespaced child node_id 'sub1/run_child/log1' "
        f"in buffer, got:\n{buffer_text}"
    )
    assert "[node_started] sub1/run_child/log1 (flow.log)" in buffer_text
    assert "[node_completed] sub1/run_child/log1" in buffer_text

    # ── parent event: un-prefixed ───────────────────────────────────
    # workflow_id="sub1" == task_log_id="sub1" → no prefixing
    assert "[node_started] run_child (workflow.run)" in buffer_text
    assert "[node_completed] run_child" in buffer_text

    # ── workflow-level events (not in NODE_LIFECYCLE_TYPES, no prefix)
    assert "[workflow_completed] success=True" in buffer_text

    cleanup_task_log("sub1")


# ─────────────────────────────────────────────────────────────────────────
# failure: missing child template — parent failure events land in buffer
# ─────────────────────────────────────────────────────────────────────────


def test_missing_child_template_logs_failure_in_buffer(tasks_tmp, tmp_path):
    """Given a parent with workflow.run referencing a nonexistent template
    and task_id="sub1b", When the engine executes, Then the parent stream
    tees node_failed + workflow_failed to _per_task_buffers["sub1b"]
    (no child stream is ever built)."""
    store_dir = tmp_path / "templates"
    store_dir.mkdir()
    store = FileTemplateStore(templates_dir=str(store_dir))

    parent_def = WorkflowDefinition(
        name="parent-missing",
        nodes=[
            _node("run_child", "workflow.run",
                  params={"template": "missing-tpl", "inputs": {}}),
        ],
    )

    parent_stream = WorkflowStreamHandler(
        workflow_id="sub1b",
        callback=None,
        task_log_id="sub1b",
    )

    ctx = ExecutionContext(
        work_dir=str(tmp_path),
        task_id="sub1b",
        template_store=store,
        workflow_stream=parent_stream,
        stream_handler=None,
    )

    result = WorkflowEngine().execute(parent_def, {}, ctx)

    assert result.success is False, "workflow should fail for missing template"

    buffer = _per_task_buffers.get("sub1b", [])
    buffer_text = "\n".join(buffer)

    # ── node_failed (in NODE_LIFECYCLE_TYPES, workflow_id == task_log_id → un-prefixed)
    assert "[node_failed] run_child: template not found: 'missing-tpl'" in buffer_text, (
        f"expected node_failed in buffer, got:\n{buffer_text}"
    )

    # ── workflow_failed (NOT in NODE_LIFECYCLE_TYPES, no prefixing)
    assert "[workflow_failed]" in buffer_text, (
        f"expected workflow_failed in buffer, got:\n{buffer_text}"
    )
    # The error message contains "node 'run_child' failed" from engine's emit_workflow_failed
    assert "run_child" in buffer_text

    cleanup_task_log("sub1b")


# ─────────────────────────────────────────────────────────────────────────
# teardown: sweep buffer leaks between tests
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _cleanup_buffers():
    """Sweep all task-log buffers after each test to prevent cross-test leaks."""
    yield
    task_ids = list(_per_task_buffers.keys())
    for tid in task_ids:
        cleanup_task_log(tid)
