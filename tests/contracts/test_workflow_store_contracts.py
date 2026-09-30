"""Contract tests: the saved-workflow surface of the workflow API_MAP handlers.

Calls the handlers directly with their (params, stream_handler) signature — the
same contract ApiHandler uses for JSON-RPC dispatch — and asserts on their
return shapes.  ``workflow.execute`` with a saved reference runs a real 2-node
file.write -> file.read workflow through the engine, so these tests also prove
the save -> execute roundtrip against the real tool stack.

Each test gets an isolated FileWorkflowStore injected into the module singleton
(``workflow_handler._store``), so no test touches the real workflows dir.

Identity contract exercised here:
- a saved workflow is addressed by its ``wf-…`` id (its file name) or by its
  free-form display name, and ``id`` wins when both are given;
- the display name is NOT path-constrained any more (it is no longer a file
  name), so names containing ``/`` or non-ASCII characters are legal.
"""

import json
import logging

import pytest

from app.common.exceptions import ToolException
from app.handlers import workflow_handler as wh
from app.handlers.workflow_handler import (
    API_MAP,
    handle_delete,
    handle_execute,
    handle_list,
    handle_load,
    handle_save,
)
from app.ids import WORKFLOW_ID_RE
from app.workflow.store import FileWorkflowStore

WORKFLOW_STORE_METHODS = {
    "workflow.save",
    "workflow.load",
    "workflow.list",
    "workflow.delete",
    "workflow.import_path",
    "workflow.execute",
}


@pytest.fixture(autouse=True)
def isolated_store(tmp_path):
    """Inject a store backed by a temp dir and reset it after the test."""
    wh._store = FileWorkflowStore(workflows_dir=str(tmp_path))
    yield
    wh._store = None


def _definition(name="tpl", message="hello-contract"):
    """A 2-node file.write -> file.read definition as a plain dict."""
    return {
        "name": name,
        "version": "1.0",
        "description": "contract workflow",
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


# ---------------------------------------------------------------------------
# API_MAP surface
# ---------------------------------------------------------------------------

def test_api_map_contains_the_workflow_store_methods():
    assert WORKFLOW_STORE_METHODS <= set(API_MAP)


def test_each_handler_is_callable():
    for name, handler in API_MAP.items():
        assert callable(handler), name


def test_workflow_execute_is_marked_streaming():
    assert API_MAP["workflow.execute"].is_streaming is True


# ---------------------------------------------------------------------------
# workflow.save / load / list / delete
# ---------------------------------------------------------------------------

def test_save_returns_an_id_and_the_display_name():
    result = handle_save({"name": "alpha", "definition": _definition("alpha")}, None)
    assert result["saved"] is True
    assert result["name"] == "alpha"
    # The id is the storage identity and is id-shaped (it becomes the file name).
    assert WORKFLOW_ID_RE.match(result["id"])


def test_save_then_load_roundtrips_definition():
    saved = handle_save(
        {
            "name": "alpha",
            "definition": _definition("alpha", "roundtrip"),
            "description": "desc",
            "tags": ["t1"],
        },
        None,
    )
    result = handle_load({"id": saved["id"]}, None)

    assert result["id"] == saved["id"]
    assert result["name"] == "alpha"
    assert result["definition"]["name"] == "alpha"
    assert [node["id"] for node in result["definition"]["nodes"]] == ["write", "read"]


def test_load_accepts_a_display_name_as_well_as_an_id():
    saved = handle_save({"name": "中文 名字/带斜杠", "definition": _definition("中文 名字/带斜杠")}, None)

    by_name = handle_load({"name": "中文 名字/带斜杠"}, None)
    assert by_name["id"] == saved["id"]
    # A free-form name is no longer a path: the file is the id, the name is data.
    assert by_name["name"] == "中文 名字/带斜杠"


def test_load_prefers_the_id_over_the_name():
    first = handle_save({"name": "shared", "definition": _definition("shared", "one")}, None)
    second = handle_save({"name": "shared", "definition": _definition("shared", "two")}, None)
    assert first["id"] != second["id"]

    result = handle_load({"id": second["id"], "name": "shared"}, None)
    assert result["id"] == second["id"]
    assert result["definition"]["nodes"][0]["params"]["content"] == "$inputs.message"


def test_save_with_the_same_id_overwrites_in_place():
    saved = handle_save({"name": "alpha", "definition": _definition("alpha")}, None)
    again = handle_save(
        {
            "id": saved["id"],
            "name": "alpha renamed",
            "definition": _definition("alpha renamed"),
        },
        None,
    )

    assert again["id"] == saved["id"]
    assert again["name"] == "alpha renamed"
    assert len(handle_list({}, None)["workflows"]) == 1


def test_load_returns_wrapper_metadata():
    saved = handle_save(
        {
            "name": "meta",
            "definition": _definition("meta", "meta-roundtrip"),
            "description": "meta description",
            "tags": ["android", "install"],
        },
        None,
    )
    result = handle_load({"id": saved["id"]}, None)

    assert set(result) == {
        "id",
        "name",
        "definition",
        "description",
        "tags",
        "created_at",
        "updated_at",
    }
    assert result["definition"]["name"] == "meta"
    assert result["description"] == "meta description"
    assert result["tags"] == ["android", "install"]
    assert isinstance(result["created_at"], str) and result["created_at"]
    assert isinstance(result["updated_at"], str) and result["updated_at"]


def test_load_raw_definition_file_returns_metadata_defaults(tmp_path):
    # The examples/ import format: a bare WorkflowDefinition with no
    # "definition" wrapper key.  It carries no wrapper metadata: tags default
    # to [] and the timestamps come from the file's mtime.  The description is
    # the definition's own top-level field, so load() and list() agree on it.
    (tmp_path / "raw.json").write_text(
        json.dumps(_definition("raw")), encoding="utf-8"
    )

    result = handle_load({"name": "raw"}, None)

    assert result["definition"]["name"] == "raw"
    assert [node["id"] for node in result["definition"]["nodes"]] == ["write", "read"]
    assert result["description"] == "contract workflow"
    assert result["tags"] == []
    # Timestamps fall back to the file's mtime (None when it is unreadable),
    # so a raw file yields either two equal ISO strings or two Nones.
    assert result["created_at"] == result["updated_at"]
    assert result["created_at"] is None or isinstance(result["created_at"], str)


def test_list_returns_saved_workflows_with_ids_sorted_by_name():
    beta = handle_save(
        {"name": "beta", "definition": _definition("beta"), "description": "b", "tags": ["x"]},
        None,
    )
    alpha = handle_save(
        {"name": "alpha", "definition": _definition("alpha"), "description": "a", "tags": ["y"]},
        None,
    )
    result = handle_list({}, None)

    workflows = result["workflows"]
    assert [entry["name"] for entry in workflows] == ["alpha", "beta"]
    assert [entry["id"] for entry in workflows] == [alpha["id"], beta["id"]]
    first = workflows[0]
    assert first["description"] == "a"
    assert first["tags"] == ["y"]
    assert first["node_count"] == 2
    assert first["created_at"] and first["updated_at"]


def test_list_logs_warning_and_skips_corrupted_workflow(tmp_path, caplog):
    # One valid (wrapped format) + one corrupted (malformed JSON) file.
    valid = {
        "definition": _definition("valid"),
        "created_at": "2026-08-10T00:00:00.000000",
        "updated_at": "2026-08-10T00:00:00.000000",
        "description": "ok",
        "tags": ["t"],
    }
    (tmp_path / "valid.json").write_text(json.dumps(valid), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{ not valid json !!!", encoding="utf-8")

    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    with caplog.at_level(logging.WARNING, logger="app.workflow.store"):
        infos = store.list()

    # Valid workflow still listed (under an id — the migration renamed it);
    # corrupted one skipped but logged.
    assert [info.name for info in infos] == ["valid"]
    assert WORKFLOW_ID_RE.match(infos[0].id)
    assert any(
        record.levelname == "WARNING"
        and "broken" in record.getMessage()
        for record in caplog.records
    )


def test_delete_removes_the_workflow():
    saved = handle_save({"name": "alpha", "definition": _definition("alpha")}, None)
    result = handle_delete({"id": saved["id"]}, None)
    assert result == {"deleted": True, "id": saved["id"], "name": "alpha"}
    assert handle_list({}, None)["workflows"] == []


def test_load_nonexistent_workflow_raises_not_found():
    with pytest.raises(ToolException, match="workflow not found: 'ghost'"):
        handle_load({"name": "ghost"}, None)


def test_delete_nonexistent_workflow_raises_not_found():
    with pytest.raises(ToolException, match="workflow not found: 'ghost'"):
        handle_delete({"name": "ghost"}, None)


def test_delete_by_an_unknown_id_raises_not_found():
    with pytest.raises(ToolException, match="workflow not found"):
        handle_delete({"id": "wf-000000000000"}, None)


def test_load_without_any_reference_is_a_contract_error():
    with pytest.raises(ToolException, match="missing 'id' or 'name'"):
        handle_load({}, None)


def test_save_without_a_name_is_a_contract_error():
    with pytest.raises(ToolException, match="Missing 'name'"):
        handle_save({"definition": _definition()}, None)


def test_save_rejects_a_non_object_definition():
    with pytest.raises(ToolException, match="'definition' must be an object"):
        handle_save({"name": "alpha", "definition": ["not", "an", "object"]}, None)


def test_load_with_an_ambiguous_name_is_a_contract_error():
    """Two workflows may share a display name; a name lookup then fails loudly."""
    handle_save({"name": "twin", "definition": _definition("twin", "one")}, None)
    handle_save({"name": "twin", "definition": _definition("twin", "two")}, None)

    with pytest.raises(ToolException, match="matches 2 workflows"):
        handle_load({"name": "twin"}, None)


# ---------------------------------------------------------------------------
# workflow.execute with a saved reference
# ---------------------------------------------------------------------------

def test_execute_runs_saved_workflow_and_streams_completion(tmp_path):
    saved = handle_save(
        {
            "name": "alpha",
            "definition": _definition("alpha", "contract-exec"),
            "description": "exec",
        },
        None,
    )
    events = []
    result = handle_execute(
        {
            "id": saved["id"],
            "inputs": {"message": "exec-hello"},
            "task_id": "wf-contract-1",
            "work_dir": str(tmp_path),
        },
        events.append,
    )

    assert result["success"] is True
    assert result["status"] == "succeeded"
    assert result["cancelled"] is False
    assert result["error"] is None
    assert result["outputs"]["content"] == "exec-hello"
    assert set(result["node_results"]) == {"write", "read"}
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "exec-hello"
    # run_id is the run identity (the task id here); workflow_id is the saved
    # workflow's storage id and workflow_name its display name.
    assert any(
        event["type"] == "workflow_completed"
        and event["run_id"] == "wf-contract-1"
        and event["workflow_id"] == saved["id"]
        and event["workflow_name"] == "alpha"
        and event["success"] is True
        for event in events
    )


def test_execute_accepts_a_display_name(tmp_path):
    handle_save({"name": "by-name", "definition": _definition("by-name", "via-name")}, None)
    result = handle_execute(
        {"name": "by-name", "inputs": {"message": "x"}, "task_id": "wf-contract-2"},
        None,
    )
    assert result["success"] is True


def test_execute_failing_workflow_reports_failure(tmp_path):
    saved = handle_save(
        {
            "name": "failing",
            "definition": {
                "name": "failing",
                "nodes": [
                    {
                        "id": "check",
                        "tool": "flow.assert",
                        "params": {"condition": False, "message": "assert-boom"},
                    }
                ],
            },
        },
        None,
    )
    events = []
    result = handle_execute(
        {
            "id": saved["id"],
            "task_id": "wf-contract-fail",
            "work_dir": str(tmp_path),
        },
        events.append,
    )

    assert result["success"] is False
    assert "assert-boom" in result["error"]
    assert any(
        event["type"] == "workflow_failed" and event["error"] is not None
        for event in events
    )


def test_execute_missing_workflow_raises_not_found(tmp_path):
    with pytest.raises(ToolException, match="workflow not found"):
        handle_execute({"name": "ghost", "work_dir": str(tmp_path)}, None)
