"""Wave 3 contract tests: workflow API_MAP handlers.

Calls the four workflow handlers directly with their (params, stream_handler)
signature — the same contract ApiHandler uses for JSON-RPC dispatch — and
asserts on their return shapes against the real ToolManager / EnvironmentRegistry.
"""

import json

import pytest

from app.common.exceptions import ToolException
from app.handlers.workflow_handler import (
    API_MAP,
    handle_execute,
    handle_list_envs,
    handle_list_tools,
    handle_validate,
)

WORKFLOW_METHODS = {"workflow.execute", "workflow.validate", "workflow.list_tools", "workflow.list_envs"}


def _inline_definition(name="contract-exec", tool="file.write"):
    """A 2-node file.write -> file.read definition as a plain dict."""
    return {
        "name": name,
        "version": "1.0",
        "description": "contract test",
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

def test_api_map_contains_four_workflow_methods():
    assert WORKFLOW_METHODS <= set(API_MAP)


def test_each_handler_is_callable():
    for name, handler in API_MAP.items():
        assert callable(handler), name


def test_workflow_execute_is_marked_streaming():
    assert API_MAP["workflow.execute"].is_streaming is True


# ---------------------------------------------------------------------------
# workflow.validate
# ---------------------------------------------------------------------------

def test_workflow_validate_with_nonexistent_tool_returns_error():
    result = handle_validate(
        {"definition": {"name": "bad", "nodes": [{"id": "a", "tool": "definitely.not.a.tool"}]}},
        None,
    )
    assert result["errors"]
    error = result["errors"][0]
    assert error["node_id"] == "a"
    assert error["field"] == "tool"
    assert error["severity"] == "error"
    assert "definitely.not.a.tool" in error["message"]


def test_workflow_validate_with_empty_definition_returns_no_errors():
    result = handle_validate({"definition": {"name": "empty", "nodes": []}}, None)
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# workflow.list_tools / workflow.list_envs
# ---------------------------------------------------------------------------

def test_workflow_list_tools_non_empty_with_builtin_and_registered():
    result = handle_list_tools({}, None)
    tools = result["tools"]
    assert tools
    names = {entry["name"] for entry in tools}
    # The 8 CORE shipped-native builtin primitives are always present (the
    # extended atomic tools are opt-in and NOT part of the default surface).
    assert "file.read" in names
    assert "file.write" in names
    assert "flow.assert" in names

    # Every entry carries a ``kind`` (todo 8).
    assert all("kind" in entry for entry in tools)

    # The shipped-native (builtin) set is exactly the 8 core primitives.
    shipped_native = {entry["name"] for entry in tools if entry["kind"] == "shipped-native"}
    expected_builtins = {
        "file.read", "file.write", "text.grep", "shell.exec",
        "flow.assert", "flow.log", "flow.foreach", "workflow.run",
    }
    assert shipped_native == expected_builtins
    assert len(shipped_native) == 8

    # Legacy ``builtin`` boolean is True only for shipped-native.
    builtin = next(
        entry for entry in tools
        if entry["name"] == "file.read" and entry["builtin"] is True
    )
    assert builtin["kind"] == "shipped-native"
    assert builtin["is_valid"] is True
    assert "ports" in builtin
    assert "description" in builtin
    # Non-builtin entries (descriptor/native) must NOT be grouped as builtin.
    for entry in tools:
        if entry["kind"] != "shipped-native":
            assert entry.get("builtin") is False


def test_workflow_list_envs_returns_java_python_node():
    result = handle_list_envs({}, None)
    names = {entry["name"] for entry in result["environments"]}
    assert {"java", "python", "node"} <= names
    for entry in result["environments"]:
        assert set(entry) == {"name", "is_valid", "binary_path", "version", "root_path"}


# ---------------------------------------------------------------------------
# workflow.execute
# ---------------------------------------------------------------------------

def test_workflow_execute_with_inline_definition_runs(tmp_path):
    events = []
    result = handle_execute(
        {
            "definition": _inline_definition(),
            "inputs": {"message": "hello-contract"},
            "task_id": "contract-inline-1",
            "work_dir": str(tmp_path),
        },
        events.append,
    )
    assert result["success"] is True
    assert result["error"] is None
    assert result["outputs"]["content"] == "hello-contract"
    assert set(result["node_results"]) == {"write", "read"}
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "hello-contract"
    # Terminal event streamed through the callback with the workflow_id.
    assert any(
        event["type"] == "workflow_completed"
        and event["workflow_id"] == "contract-inline-1"
        and event["success"] is True
        for event in events
    )


def test_workflow_execute_with_file_path_loads_and_runs(tmp_path):
    wf_path = tmp_path / "wf.json"
    wf_path.write_text(json.dumps(_inline_definition("disk-wf")), encoding="utf-8")
    events = []
    result = handle_execute(
        {
            "path": str(wf_path),
            "inputs": {"message": "from-disk"},
            "task_id": "contract-path-1",
            "work_dir": str(tmp_path),
        },
        events.append,
    )
    assert result["success"] is True
    assert result["outputs"]["content"] == "from-disk"
    assert any(event["type"] == "workflow_completed" for event in events)


def test_workflow_execute_with_failed_node_streams_workflow_failed(tmp_path):
    events = []
    result = handle_execute(
        {
            "definition": {
                "name": "failing",
                "nodes": [
                    {"id": "check", "tool": "flow.assert",
                     "params": {"condition": False, "message": "assert-boom"}}
                ],
            },
            "task_id": "contract-fail-1",
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


def test_workflow_execute_with_missing_definition_raises():
    with pytest.raises(ToolException, match="missing definition or path"):
        handle_execute({"task_id": "x"}, None)
