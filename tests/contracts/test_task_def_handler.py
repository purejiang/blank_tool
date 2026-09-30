"""Contract tests: task-definition API_MAP handlers (``task.*``).

Calls the five handlers directly with their ``(params, stream_handler)``
signature — the same contract ``ApiHandler`` uses for JSON-RPC dispatch — and
asserts on their return shapes.  ``task.execute`` runs a real 2-node
file.write -> file.read workflow through the engine, so these tests also prove
the save -> execute roundtrip against the real tool stack, plus that the run is
recorded in history with ``task_name`` (and ``source`` still the workflow name).

Each test gets isolated ``FileTaskStore`` / ``FileWorkflowStore`` instances
injected into the handler's module singletons, plus a temp output dir for run
history, so no test touches real user data.
"""

import json
import os

import pytest

from app.common.exceptions import ToolException
from app.handlers import task_def_handler as tdh
from app.handlers.task_def_handler import (
    API_MAP,
    task_delete,
    task_execute,
    task_get,
    task_list,
    task_save,
)
from app.history import store as history_store
from app.ids import TASK_ID_RE
from app.task.store import FileTaskStore, TaskNotFoundError
from app.workflow.store import FileWorkflowStore

TASK_METHODS = {"task.list", "task.get", "task.save", "task.delete", "task.execute"}


@pytest.fixture(autouse=True)
def isolated_stores(tmp_path, monkeypatch):
    """Isolate the task store, workflow store and run-history dir per test."""
    monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("BT_SERVER_CONFIG", str(tmp_path / "no-server-config.json"))

    tdh._task_store = FileTaskStore(task_defs_dir=str(tmp_path / "task_defs"))
    tdh._workflow_store = FileWorkflowStore(workflows_dir=str(tmp_path / "workflows"))
    # The workflow_id backfill runs once per process; reset it so each test's
    # freshly injected store gets its own pass.
    tdh._backfilled = False
    yield
    tdh._task_store = None
    tdh._workflow_store = None
    tdh._backfilled = False


def _definition(name="wf", message="hello-contract"):
    """A 2-node file.write -> file.read definition as a plain dict."""
    return {
        "name": name,
        "version": "1.0",
        "description": "contract workflow",
        "inputs": [
            {"name": "message", "type": {"base": "text"}, "required": True},
        ],
        "nodes": [
            {
                "id": "write",
                "tool": "file.write",
                "params": {"path": "out.txt", "content": "$inputs.message"},
                "next": "read",
            },
            {
                "id": "read",
                "tool": "file.read",
                "params": {"path": "$nodes.write.outputs.path"},
            },
        ],
    }


def _save_workflow(name="wf", message="hello-contract"):
    """Store a workflow through the workflow handler's own API."""
    from app.handlers import workflow_handler as wh

    previous = wh._store
    wh._store = tdh._get_workflow_store()
    try:
        return wh.handle_save(
            {"name": name, "definition": _definition(name, message)}, None
        )
    finally:
        wh._store = previous


# ---------------------------------------------------------------------------
# API_MAP surface
# ---------------------------------------------------------------------------

def test_api_map_exposes_exactly_the_task_definition_methods():
    assert set(API_MAP) == TASK_METHODS


def test_task_list_does_not_shadow_the_in_flight_run_listing():
    """``task.list`` is definitions; in-flight runs are ``run.list``."""
    from app.handlers.task_handler import API_MAP as run_api_map

    assert "task.list" not in run_api_map
    assert "run.list" in run_api_map


# ---------------------------------------------------------------------------
# task.save / task.list / task.get
# ---------------------------------------------------------------------------

def test_save_and_list_roundtrip():
    _save_workflow("wf-a")

    saved = task_save(
        {
            "name": "nightly",
            "workflow": "wf-a",
            "inputs": {"message": "saved"},
            "work_dir": "D:/wd",
            "description": "desc",
        },
        None,
    )
    assert saved["saved"] is True
    assert saved["name"] == "nightly"
    assert TASK_ID_RE.match(saved["id"])

    payload = task_list({}, None)
    assert len(payload["tasks"]) == 1
    entry = payload["tasks"][0]
    assert entry["id"] == saved["id"]
    assert entry["name"] == "nightly"
    assert entry["workflow"] == "wf-a"
    assert entry["workflow_exists"] is True
    # The binding is by workflow id, with the name kept as the fallback label.
    assert entry["workflow_id"] == tdh._get_workflow_store().find_id_by_name("wf-a")
    assert entry["inputs"] == {"message": "saved"}
    assert entry["input_count"] == 1
    assert entry["has_work_dir"] is True
    assert entry["work_dir"] == "D:/wd"
    assert entry["description"] == "desc"
    assert entry["created_at"]

    # get returns the full record plus the workflow-exists flag
    got = task_get({"name": "nightly"}, None)
    assert got["workflow_exists"] is True
    assert got["task"]["inputs"] == {"message": "saved"}


def test_list_is_sorted_by_name_and_empty_by_default():
    assert task_list({}, None) == {"tasks": []}

    _save_workflow("wf-a")
    task_save({"name": "zeta", "workflow": "wf-a"}, None)
    task_save({"name": "alpha", "workflow": "wf-a"}, None)

    assert [t["name"] for t in task_list({}, None)["tasks"]] == ["alpha", "zeta"]


def test_list_marks_a_task_whose_workflow_was_deleted():
    _save_workflow("wf-gone")
    task_save({"name": "orphan", "workflow": "wf-gone"}, None)
    tdh._get_workflow_store().delete("wf-gone")

    entry = task_list({}, None)["tasks"][0]
    assert entry["workflow_exists"] is False
    assert task_get({"name": "orphan"}, None)["workflow_exists"] is False


def test_has_work_dir_is_false_without_one():
    _save_workflow("wf-a")
    task_save({"name": "plain", "workflow": "wf-a"}, None)

    entry = task_list({}, None)["tasks"][0]
    assert entry["has_work_dir"] is False
    assert entry["work_dir"] == ""
    assert entry["input_count"] == 0


def test_save_overwrites_and_keeps_created_at():
    _save_workflow("wf-a")
    first = task_save({"name": "t", "workflow": "wf-a", "inputs": {"message": "1"}}, None)
    created = task_list({}, None)["tasks"][0]["created_at"]

    # Saving the SAME task means passing its id: the display name is data now,
    # so a name-only save would create a second task instead of overwriting.
    task_save(
        {"id": first["id"], "name": "t", "workflow": "wf-a", "inputs": {"message": "2"}},
        None,
    )

    tasks = task_list({}, None)["tasks"]
    assert len(tasks) == 1
    entry = tasks[0]
    assert entry["created_at"] == created
    assert entry["inputs"] == {"message": "2"}
    assert first["saved"] is True and first["name"] == "t"


def test_save_requires_an_existing_workflow():
    with pytest.raises(ToolException, match="workflow not found: ghost"):
        task_save({"name": "t", "workflow": "ghost"}, None)


def test_save_rejects_an_unknown_workflow_id():
    with pytest.raises(ToolException, match="workflow not found: wf-000000000000"):
        task_save({"name": "t", "workflow_id": "wf-000000000000"}, None)


def test_save_with_a_path_like_workflow_name_finds_nothing():
    """A name is never treated as a path: it simply resolves to no workflow."""
    with pytest.raises(ToolException, match="workflow not found"):
        task_save({"name": "t", "workflow": "../escape"}, None)


def test_save_requires_a_workflow_field():
    for params in ({"name": "t"}, {"name": "t", "workflow": ""}, {"name": "t", "workflow": "  "}):
        with pytest.raises(ToolException, match="Missing 'workflow_id' or 'workflow' field"):
            task_save(params, None)


def test_save_requires_an_object_for_inputs():
    _save_workflow("wf-a")
    with pytest.raises(ToolException, match="'inputs' must be an object"):
        task_save({"name": "t", "workflow": "wf-a", "inputs": ["not", "a", "dict"]}, None)


def test_free_form_task_names_are_accepted():
    """The task name is data now, not a file name."""
    _save_workflow("wf-a")
    saved = task_save({"name": "../中文 任务/名", "workflow": "wf-a"}, None)

    assert saved["name"] == "../中文 任务/名"
    assert task_get({"id": saved["id"]}, None)["task"]["name"] == "../中文 任务/名"


def test_missing_name_is_a_contract_error():
    for handler in (task_get, task_delete, task_execute):
        with pytest.raises(ToolException, match="Missing 'id' or 'name' field"):
            handler({}, None)
    with pytest.raises(ToolException, match="Missing 'name' field"):
        task_save({"workflow": "wf-a"}, None)


def test_get_unknown_task_raises():
    with pytest.raises(ToolException, match="task not found: ghost"):
        task_get({"name": "ghost"}, None)


# ---------------------------------------------------------------------------
# task.delete
# ---------------------------------------------------------------------------

def test_delete_removes_the_task():
    _save_workflow("wf-a")
    saved = task_save({"name": "t", "workflow": "wf-a"}, None)

    result = task_delete({"name": "t"}, None)
    assert result == {"deleted": True, "id": saved["id"], "name": "t"}
    assert task_list({}, None) == {"tasks": []}


def test_delete_unknown_task_raises():
    with pytest.raises(ToolException, match="task not found: ghost"):
        task_delete({"name": "ghost"}, None)


def test_delete_leaves_run_records_alone(tmp_path):
    """Deleting a task must not touch the runs it produced."""
    _save_workflow("wf-a", "keep-history")
    task_save({"name": "t", "workflow": "wf-a", "inputs": {"message": "keep"}}, None)
    task_execute({"name": "t", "task_id": "tdh-del-1", "work_dir": str(tmp_path)}, None)
    assert len(history_store.list_runs()) == 1

    task_delete({"name": "t"}, None)

    assert len(history_store.list_runs()) == 1


def test_delete_removes_the_run_artifacts(tmp_path):
    """Deleting a task deletes the files its runs produced (the record stays).

    This is the behavior the removed ``autoDeleteOutputOnTaskRemove`` setting
    used to (never actually) toggle: deleting a task deletes its files.
    """
    _save_workflow("wf-a")
    task_save({"name": "t", "workflow": "wf-a", "inputs": {"message": "x"}}, None)
    task_execute({"name": "t", "task_id": "tdh-art-1", "work_dir": str(tmp_path)}, None)

    artifact_dirs = [r["run_dir"] for r in history_store.list_runs() if r.get("run_dir")]
    assert artifact_dirs, "the run must have produced an artifact dir"
    assert all(os.path.isdir(d) for d in artifact_dirs)

    task_delete({"name": "t"}, None)

    assert all(not os.path.exists(d) for d in artifact_dirs)
    # The run record survives: history has its own retention policy and its own
    # "clear records" action in the run-records UI.
    assert len(history_store.list_runs()) == 1


def test_delete_only_purges_its_own_artifacts(tmp_path):
    """The purge is keyed by the task's id — a sibling task's files survive."""
    _save_workflow("wf-a")
    task_save({"name": "t1", "workflow": "wf-a", "inputs": {"message": "x"}}, None)
    task_save({"name": "t2", "workflow": "wf-a", "inputs": {"message": "y"}}, None)
    task_execute({"name": "t1", "task_id": "tdh-own-1", "work_dir": str(tmp_path)}, None)
    task_execute({"name": "t2", "task_id": "tdh-own-2", "work_dir": str(tmp_path)}, None)

    run_dirs = {r["task_name"]: r["run_dir"] for r in history_store.list_runs()}
    assert set(run_dirs) == {"t1", "t2"}
    assert all(r.get("task_def_id") for r in history_store.list_runs())

    task_delete({"name": "t1"}, None)

    assert not os.path.exists(run_dirs["t1"])
    assert os.path.isdir(run_dirs["t2"])


def test_delete_purges_artifacts_of_a_renamed_task(tmp_path):
    """Renaming a task must not orphan the files its earlier runs produced.

    The purge matches on ``task_def_id``; a name-keyed purge would silently
    stop finding these artifacts the moment the task was renamed.
    """
    _save_workflow("wf-a")
    saved = task_save({"name": "before", "workflow": "wf-a", "inputs": {"message": "x"}}, None)
    task_execute({"id": saved["id"], "task_id": "tdh-rename-1", "work_dir": str(tmp_path)}, None)
    run_dir = history_store.list_runs()[0]["run_dir"]
    assert os.path.isdir(run_dir)

    # Rename the task, keeping its id.
    task_save({"id": saved["id"], "name": "after", "workflow": "wf-a"}, None)
    task_delete({"id": saved["id"]}, None)

    assert not os.path.exists(run_dir)


# ---------------------------------------------------------------------------
# task.execute
# ---------------------------------------------------------------------------

def test_execute_runs_the_bound_workflow_with_saved_inputs(tmp_path):
    _save_workflow("wf-a", "saved-message")
    task_save(
        {"name": "t", "workflow": "wf-a", "inputs": {"message": "from-task"}}, None
    )

    events = []
    result = task_execute(
        {"name": "t", "task_id": "tdh-exec-1", "work_dir": str(tmp_path)}, events.append
    )

    assert result["success"] is True
    assert result["status"] == "succeeded"
    assert result["cancelled"] is False
    assert result["error"] is None
    assert result["outputs"]["content"] == "from-task"
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "from-task"
    assert any(event["type"] == "workflow_completed" for event in events)


def test_execute_request_inputs_override_saved_values(tmp_path):
    _save_workflow("wf-a")
    task_save(
        {"name": "t", "workflow": "wf-a", "inputs": {"message": "saved"}}, None
    )

    result = task_execute(
        {
            "name": "t",
            "inputs": {"message": "override"},
            "task_id": "tdh-exec-2",
            "work_dir": str(tmp_path),
        },
        None,
    )

    assert result["outputs"]["content"] == "override"
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "override"


def test_execute_does_not_rewrite_the_saved_inputs(tmp_path):
    """A run is not a save: the stored task keeps its own values."""
    _save_workflow("wf-a")
    task_save({"name": "t", "workflow": "wf-a", "inputs": {"message": "saved"}}, None)

    task_execute(
        {
            "name": "t",
            "inputs": {"message": "override"},
            "task_id": "tdh-exec-3",
            "work_dir": str(tmp_path),
        },
        None,
    )

    assert task_get({"name": "t"}, None)["task"]["inputs"] == {"message": "saved"}


def test_execute_uses_the_saved_work_dir_when_none_is_passed(tmp_path):
    work_dir = tmp_path / "task-work"
    work_dir.mkdir()
    _save_workflow("wf-a")
    saved = task_save(
        {"name": "t", "workflow": "wf-a", "inputs": {"message": "wd"}}, None
    )
    # A directory chosen after the save, to prove the saved value is used.
    tdh._get_task_store().save(
        "t", "wf-a", {"message": "wd"}, str(work_dir), task_id=saved["id"]
    )

    task_execute({"name": "t", "task_id": "tdh-exec-4"}, None)

    assert (work_dir / "out.txt").read_text(encoding="utf-8") == "wd"


def test_execute_records_the_task_and_the_workflow_in_history(tmp_path):
    saved_workflow = _save_workflow("wf-history", "hist-message")
    saved_task = task_save(
        {"name": "nightly", "workflow": "wf-history", "inputs": {"message": "h"}}, None
    )

    task_execute(
        {"name": "nightly", "task_id": "tdh-exec-5", "work_dir": str(tmp_path)}, None
    )

    runs = history_store.list_runs()
    assert len(runs) == 1
    summary = runs[0]
    # The task identity travels as task_name / task_def_id; source stays the
    # WORKFLOW name, and workflow_id is the saved workflow's storage id.
    assert summary["task_name"] == "nightly"
    assert summary["task_def_id"] == saved_task["id"]
    assert summary["source"] == "wf-history"
    assert summary["workflow_name"] == "wf-history"
    assert summary["workflow_id"] == saved_workflow["id"]
    assert summary["task_id"] == "tdh-exec-5"

    full = history_store.get_run(summary["run_id"])
    assert full["inputs"] == {"message": "h"}


def test_execute_is_retryable_after_a_failed_run(tmp_path):
    """A failing node must not corrupt the task or block the next run."""
    from app.handlers import workflow_handler as wh

    previous = wh._store
    wh._store = tdh._get_workflow_store()
    try:
        wh.handle_save(
            {
                "name": "wf-failing",
                "definition": {
                    "name": "wf-failing",
                    "nodes": [
                        {
                            "id": "check",
                            "tool": "flow.assert",
                            "params": {"condition": False, "message": "boom"},
                        }
                    ],
                },
            },
            None,
        )
    finally:
        wh._store = previous
    task_save({"name": "t", "workflow": "wf-failing"}, None)

    result = task_execute(
        {"name": "t", "task_id": "tdh-exec-fail", "work_dir": str(tmp_path)}, None
    )

    assert result["success"] is False
    assert "boom" in (result["error"] or "")
    assert task_get({"name": "t"}, None)["task"]["workflow"] == "wf-failing"


def test_execute_unknown_task_raises():
    with pytest.raises(ToolException, match="task not found: ghost"):
        task_execute({"name": "ghost"}, None)


def test_execute_with_a_deleted_workflow_raises(tmp_path):
    _save_workflow("wf-gone")
    task_save({"name": "t", "workflow": "wf-gone"}, None)
    tdh._get_workflow_store().delete("wf-gone")

    with pytest.raises(ToolException, match="workflow not found: wf-gone"):
        task_execute({"name": "t", "task_id": "tdh-exec-6"}, None)


def test_execute_rejects_non_object_inputs(tmp_path):
    _save_workflow("wf-a")
    task_save({"name": "t", "workflow": "wf-a"}, None)

    with pytest.raises(ToolException, match="'inputs' must be an object"):
        task_execute({"name": "t", "inputs": "nope"}, None)


def test_execute_reports_a_corrupt_task_file(tmp_path):
    _save_workflow("wf-a")
    (tmp_path / "task_defs" / "broken.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(ToolException, match="invalid JSON"):
        task_execute({"name": "broken"}, None)


def test_task_store_is_created_lazily(monkeypatch, tmp_path):
    """_get_task_store() resolves on first use, not at import time."""
    tdh._task_store = None
    monkeypatch.setenv("BT_TASK_DEFS_DIR", str(tmp_path / "lazy"))

    store = tdh._get_task_store()

    assert isinstance(store, FileTaskStore)
    assert store.exists("anything") is False
    assert (tmp_path / "lazy").is_dir()
