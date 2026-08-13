"""Wave 4 contract tests: template.* API_MAP handlers.

Calls the five template handlers directly with their (params, stream_handler)
signature — the same contract ApiHandler uses for JSON-RPC dispatch — and
asserts on their return shapes.  ``template.execute`` runs a real 2-node
file.write -> file.read workflow through the engine, so these tests also prove
the save -> execute roundtrip against the real tool stack.

Each test gets an isolated FileTemplateStore injected into the module singleton
(``template_handler._store``), so no test touches the real templates dir.
"""

import json
import logging

import pytest

from app.handlers import template_handler as th
from app.handlers.template_handler import (
    API_MAP,
    handle_delete,
    handle_execute,
    handle_list,
    handle_load,
    handle_save,
)
from app.template.store import FileTemplateStore, TemplateNotFoundError

TEMPLATE_METHODS = {
    "template.save",
    "template.load",
    "template.list",
    "template.delete",
    "template.execute",
}


@pytest.fixture(autouse=True)
def isolated_store(tmp_path):
    """Inject a store backed by a temp dir and reset it after the test."""
    th._store = FileTemplateStore(templates_dir=str(tmp_path))
    yield
    th._store = None


def _definition(name="tpl", message="hello-contract"):
    """A 2-node file.write -> file.read definition as a plain dict."""
    return {
        "name": name,
        "version": "1.0",
        "description": "contract template",
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

def test_api_map_contains_all_five_template_methods():
    assert TEMPLATE_METHODS <= set(API_MAP)


def test_each_handler_is_callable():
    for name, handler in API_MAP.items():
        assert callable(handler), name


def test_template_execute_is_marked_streaming():
    assert API_MAP["template.execute"].is_streaming is True


# ---------------------------------------------------------------------------
# template.save / template.load / template.list / template.delete
# ---------------------------------------------------------------------------

def test_save_returns_saved_true_with_name():
    result = handle_save({"name": "alpha", "definition": _definition("alpha")}, None)
    assert result == {"saved": True, "name": "alpha"}


def test_save_then_load_roundtrips_definition():
    handle_save(
        {
            "name": "alpha",
            "definition": _definition("alpha", "roundtrip"),
            "description": "desc",
            "tags": ["t1"],
        },
        None,
    )
    result = handle_load({"name": "alpha"}, None)

    assert result["definition"]["name"] == "alpha"
    assert [node["id"] for node in result["definition"]["nodes"]] == ["write", "read"]


def test_list_returns_saved_templates_with_metadata():
    handle_save(
        {"name": "beta", "definition": _definition("beta"), "description": "b", "tags": ["x"]},
        None,
    )
    handle_save(
        {"name": "alpha", "definition": _definition("alpha"), "description": "a", "tags": ["y"]},
        None,
    )
    result = handle_list({}, None)

    templates = result["templates"]
    assert [entry["name"] for entry in templates] == ["alpha", "beta"]
    alpha = templates[0]
    assert alpha["description"] == "a"
    assert alpha["tags"] == ["y"]
    assert alpha["node_count"] == 2
    assert alpha["created_at"] and alpha["updated_at"]


def test_list_logs_warning_and_skips_corrupted_template(tmp_path, caplog):
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

    store = FileTemplateStore(templates_dir=str(tmp_path))
    with caplog.at_level(logging.WARNING, logger="app.template.store"):
        infos = store.list()

    # Valid template still listed; corrupted one skipped but logged.
    assert [info.name for info in infos] == ["valid"]
    assert any(
        record.levelname == "WARNING"
        and "broken" in record.getMessage()
        for record in caplog.records
    )


def test_delete_removes_template():
    handle_save({"name": "alpha", "definition": _definition("alpha")}, None)
    result = handle_delete({"name": "alpha"}, None)
    assert result == {"deleted": True, "name": "alpha"}
    assert handle_list({}, None)["templates"] == []


def test_load_nonexistent_template_raises_not_found():
    with pytest.raises(TemplateNotFoundError):
        handle_load({"name": "ghost"}, None)


def test_delete_nonexistent_template_raises_not_found():
    with pytest.raises(TemplateNotFoundError):
        handle_delete({"name": "ghost"}, None)


def test_save_unsafe_name_raises_value_error():
    with pytest.raises(ValueError, match="invalid characters"):
        handle_save({"name": "../escape", "definition": _definition()}, None)


def test_save_missing_definition_raises_value_error():
    # A definition without a "name" is a caller contract error.
    with pytest.raises(ValueError, match="missing required field: 'name'"):
        handle_save({"name": "alpha"}, None)


# ---------------------------------------------------------------------------
# template.execute
# ---------------------------------------------------------------------------

def test_execute_runs_saved_template_and_streams_completion(tmp_path):
    handle_save(
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
            "name": "alpha",
            "inputs": {"message": "exec-hello"},
            "task_id": "tpl-contract-1",
            "work_dir": str(tmp_path),
        },
        events.append,
    )

    assert result["success"] is True
    assert result["error"] is None
    assert result["outputs"]["content"] == "exec-hello"
    assert set(result["node_results"]) == {"write", "read"}
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "exec-hello"
    assert any(
        event["type"] == "workflow_completed"
        and event["workflow_id"] == "tpl-contract-1"
        and event["success"] is True
        for event in events
    )


def test_execute_failing_template_reports_failure(tmp_path):
    handle_save(
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
            "name": "failing",
            "task_id": "tpl-contract-fail",
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


def test_execute_missing_template_raises_not_found(tmp_path):
    with pytest.raises(TemplateNotFoundError):
        handle_execute({"name": "ghost", "work_dir": str(tmp_path)}, None)
