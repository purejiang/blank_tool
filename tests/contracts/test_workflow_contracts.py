"""Wave 3 contract tests: workflow API_MAP handlers.

Calls the four workflow handlers directly with their (params, stream_handler)
signature — the same contract ApiHandler uses for JSON-RPC dispatch — and
asserts on their return shapes against the real ToolManager / EnvironmentRegistry.

The execution payload is ``{success, status, cancelled, outputs, node_results,
error}`` with ``status`` one of ``succeeded`` / ``failed`` / ``cancelled``, and
the streamed event schema is exactly the five workflow lifecycle events
documented in ``app/workflow/streaming.py`` — ``node_failed`` and
``node_output`` no longer exist.
"""

import json

import pytest

from app.common.exceptions import ToolException
from app.common.task_manager import TaskManager
from app.handlers.workflow_handler import (
    API_MAP,
    handle_execute,
    handle_list_envs,
    handle_list_tools,
    handle_validate,
)
from app.workflow.output_limit import MAX_STRING_CHARS

WORKFLOW_METHODS = {"workflow.execute", "workflow.validate", "workflow.list_tools", "workflow.list_envs"}

#: Exactly the keys each event type carries (``error`` is optional on
#: ``node_completed`` and only present when the node failed/skipped).
_EVENT_KEYS = {
    "node_started": {"type", "run_id", "workflow_id", "node_id", "tool"},
    "node_completed": {
        "type", "run_id", "workflow_id", "node_id", "status", "duration_ms",
        "attempts",
    },
    "workflow_completed": {"type", "run_id", "workflow_id", "success"},
    "workflow_failed": {"type", "run_id", "workflow_id", "error"},
    "workflow_cancelled": {"type", "run_id", "workflow_id"},
}

_NODE_STATUSES = {"ok", "failed", "skipped", "cancelled"}

_PAYLOAD_KEYS = {"success", "status", "cancelled", "outputs", "node_results", "error"}


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


def _types(events):
    return [event["type"] for event in events]


def _of_type(events, event_type):
    return [event for event in events if event["type"] == event_type]


def _completed_for(events, node_id):
    matches = [
        event for event in _of_type(events, "node_completed")
        if event["node_id"] == node_id
    ]
    assert len(matches) == 1, (
        f"node {node_id!r} must emit exactly one node_completed, got {len(matches)}"
    )
    return matches[0]


def _assert_event_schema(event, run_id, workflow_id):
    """Assert *event* matches the documented schema for its type."""
    event_type = event["type"]
    assert event_type in _EVENT_KEYS, f"undocumented event type: {event_type!r}"

    expected = set(_EVENT_KEYS[event_type])
    if event_type == "node_completed" and "error" in event:
        expected.add("error")
    assert set(event) == expected

    assert event["run_id"] == run_id
    assert event["workflow_id"] == workflow_id

    if event_type in ("node_started", "node_completed"):
        assert isinstance(event["node_id"], str) and event["node_id"]
    if event_type == "node_completed":
        assert event["status"] in _NODE_STATUSES
        assert isinstance(event["duration_ms"], int) and event["duration_ms"] >= 0
        assert isinstance(event["attempts"], int) and event["attempts"] >= 1
    if event_type == "workflow_completed":
        assert isinstance(event["success"], bool)


@pytest.fixture(autouse=True)
def _clean_task_manager():
    """Keep TaskManager registrations/tombstones out of other tests."""
    tm = TaskManager()
    with tm._tasks_lock:
        tm._tasks.clear()
        tm._by_task.clear()
        tm._tombstones.clear()
        tm._seen.clear()
    yield
    with tm._tasks_lock:
        tm._tasks.clear()
        tm._by_task.clear()
        tm._tombstones.clear()
        tm._seen.clear()


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
    # The 10 CORE shipped-native builtin primitives are always present (the
    # extended atomic tools are opt-in and NOT part of the default surface).
    assert "file.read" in names
    assert "file.write" in names
    assert "flow.assert" in names

    # Every entry carries a ``kind`` (todo 8).
    assert all("kind" in entry for entry in tools)

    # The shipped-native (builtin) set is exactly the 10 core primitives.
    shipped_native = {entry["name"] for entry in tools if entry["kind"] == "shipped-native"}
    expected_builtins = {
        "file.read", "file.write", "text.grep", "shell.exec",
        "flow.assert", "flow.log", "flow.foreach", "flow.branch",
        "flow.compare", "workflow.run",
    }
    assert shipped_native == expected_builtins
    assert len(shipped_native) == 10

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

    # Payload contract: success/status/cancelled plus the run data.
    assert set(result) == _PAYLOAD_KEYS
    assert result["success"] is True
    assert result["status"] == "succeeded"
    assert result["cancelled"] is False
    assert result["error"] is None
    assert result["outputs"]["content"] == "hello-contract"
    assert set(result["node_results"]) == {"write", "read"}
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "hello-contract"

    # Event contract: one node_started + exactly one node_completed per node,
    # then a single workflow_completed.  task_id doubles as the run id here
    # (no ``_run_id`` was supplied) while workflow_id is the definition name.
    assert _types(events) == [
        "node_started",
        "node_completed",
        "node_started",
        "node_completed",
        "workflow_completed",
    ]
    for event in events:
        _assert_event_schema(event, "contract-inline-1", "contract-exec")

    assert all(event["status"] == "ok" for event in _of_type(events, "node_completed"))
    assert _of_type(events, "workflow_completed") == [
        {
            "type": "workflow_completed",
            "run_id": "contract-inline-1",
            "workflow_id": "contract-exec",
            "success": True,
        }
    ]


def test_workflow_execute_emits_no_legacy_event_types(tmp_path):
    """``node_failed`` / ``node_output`` are gone — only the five remain."""
    events = []
    handle_execute(
        {
            "definition": _inline_definition(),
            "inputs": {"message": "hello-contract"},
            "task_id": "contract-legacy-1",
            "work_dir": str(tmp_path),
        },
        events.append,
    )
    assert {event["type"] for event in events} <= set(_EVENT_KEYS)
    assert "node_failed" not in _types(events)
    assert "node_output" not in _types(events)


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
    assert result["status"] == "succeeded"
    assert result["cancelled"] is False
    assert result["outputs"]["content"] == "from-disk"

    assert _types(events)[-1] == "workflow_completed"
    for event in events:
        _assert_event_schema(event, "contract-path-1", "disk-wf")


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
    assert result["status"] == "failed"
    assert result["cancelled"] is False
    assert "assert-boom" in result["error"]

    # The failing node still gets its single terminal event, with the error.
    assert _types(events) == ["node_started", "node_completed", "workflow_failed"]
    for event in events:
        _assert_event_schema(event, "contract-fail-1", "failing")

    completed = _completed_for(events, "check")
    assert completed["status"] == "failed"
    assert "assert-boom" in completed["error"]

    failed = _of_type(events, "workflow_failed")
    assert len(failed) == 1
    assert failed[0]["error"] is not None
    assert "assert-boom" in failed[0]["error"]
    assert not _of_type(events, "workflow_completed")


def test_workflow_execute_reports_cancelled_status(tmp_path):
    """A cancel armed before the run registers aborts it and reports cancelled."""
    events = []
    assert TaskManager().cancel("contract-cancel-run") is True

    result = handle_execute(
        {
            "definition": _inline_definition(),
            "inputs": {"message": "never-written"},
            "task_id": "contract-cancel-1",
            "_run_id": "contract-cancel-run",
            "work_dir": str(tmp_path),
        },
        events.append,
    )

    assert result["success"] is False
    assert result["status"] == "cancelled"
    assert result["cancelled"] is True
    assert result["error"] == "workflow cancelled"
    assert result["node_results"] == {}
    assert not (tmp_path / "out.txt").exists()

    assert _types(events) == ["workflow_cancelled"]
    _assert_event_schema(events[0], "contract-cancel-run", "contract-exec")


def test_workflow_execute_truncates_oversized_recorded_outputs(tmp_path):
    """The payload copy is size-bounded; expressions still see full values."""
    payload = "x" * (MAX_STRING_CHARS + 100)
    events = []
    result = handle_execute(
        {
            "definition": _inline_definition("big-output"),
            "inputs": {"message": payload},
            "task_id": "contract-big-1",
            "work_dir": str(tmp_path),
        },
        events.append,
    )

    assert result["status"] == "succeeded"
    content = result["outputs"]["content"]
    assert isinstance(content, dict)
    assert content["_truncated"] is True
    assert content["_chars"] == len(payload)
    assert len(content["_preview"]) == MAX_STRING_CHARS
    assert content["_reason"]

    # Structure is preserved: the sibling scalar passes through untouched.
    assert result["outputs"]["size"] == len(payload)
    # node_results carries the same bounded copy.
    assert result["node_results"]["read"]["outputs"]["content"]["_truncated"] is True


def test_workflow_execute_with_missing_definition_raises():
    with pytest.raises(ToolException, match="missing definition or path"):
        handle_execute({"task_id": "x"}, None)
