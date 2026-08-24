"""
Contract tests for ``task.list`` and ``request.cancel`` handlers.

The TaskManager is a singleton — tests must clean up ``_tasks`` to avoid
cross-test pollution. The ``with tm._tasks_lock: tm._tasks.clear()`` pattern
handles this.
"""

import threading

import pytest
from app.common.task_manager import TaskManager


# ──────────────────────────────────────────────────────────────────────
# TaskManager.list_tasks()
# ──────────────────────────────────────────────────────────────────────


def test_list_tasks_returns_empty_when_none_registered():
    tm = TaskManager()
    with tm._tasks_lock:
        tm._tasks.clear()
    result = tm.list_tasks()
    assert result == []


def test_list_tasks_returns_registered_task():
    tm = TaskManager()
    with tm._tasks_lock:
        tm._tasks.clear()
    tm.register_stream("test-task-1", threading.Event())
    try:
        result = tm.list_tasks()
        assert len(result) == 1
        assert result[0]["task_id"] == "test-task-1"
        assert result[0]["type"] == "streaming"
        assert result[0]["cancelled"] is False
        assert result[0]["has_process"] is False
        assert "started_at" in result[0]
    finally:
        with tm._tasks_lock:
            tm._tasks.clear()


def test_list_tasks_does_not_expose_process_holder():
    """list_tasks() must NOT leak the subprocess.Popen reference."""
    tm = TaskManager()
    with tm._tasks_lock:
        tm._tasks.clear()
    tm.register_stream("test-task-2", threading.Event())
    try:
        result = tm.list_tasks()
        assert len(result) == 1
        for key in result[0]:
            assert key != "process_holder", (
                "process_holder (contains Popen) must NOT be exposed in list_tasks()"
            )
    finally:
        with tm._tasks_lock:
            tm._tasks.clear()


def test_list_tasks_streaming_type():
    """register_stream tasks should report type='streaming'."""
    tm = TaskManager()
    with tm._tasks_lock:
        tm._tasks.clear()
    stop = threading.Event()
    tm.register_stream("test-stream-1", stop)
    try:
        result = tm.list_tasks()
        assert len(result) == 1
        assert result[0]["task_id"] == "test-stream-1"
        assert result[0]["type"] == "streaming"
        assert result[0]["cancelled"] is False
    finally:
        with tm._tasks_lock:
            tm._tasks.clear()


def test_list_tasks_reflects_cancelled_state():
    tm = TaskManager()
    with tm._tasks_lock:
        tm._tasks.clear()
    tm.register_stream("test-cancel-1", threading.Event())
    tm.cancel("test-cancel-1")
    try:
        result = tm.list_tasks()
        assert len(result) == 1
        assert result[0]["cancelled"] is True
    finally:
        with tm._tasks_lock:
            tm._tasks.clear()


# ──────────────────────────────────────────────────────────────────────
# Cancel
# ──────────────────────────────────────────────────────────────────────


def test_cancel_request_with_bogus_id_returns_false():
    tm = TaskManager()
    with tm._tasks_lock:
        tm._tasks.clear()
    result = tm.cancel("nonexistent-task-id")
    assert result is False


def test_cancel_request_with_registered_task():
    tm = TaskManager()
    with tm._tasks_lock:
        tm._tasks.clear()
    tm.register_stream("test-cancel-2", threading.Event())
    try:
        result = tm.cancel("test-cancel-2")
        assert result is True
    finally:
        with tm._tasks_lock:
            tm._tasks.clear()


# ──────────────────────────────────────────────────────────────────────
# Handler dispatch (through handle_list_tasks / handle_cancel_request)
# ──────────────────────────────────────────────────────────────────────


def test_handle_list_tasks():
    """Call the handler function directly to verify API_MAP dispatch path."""
    from app.handlers.task_handler import handle_list_tasks

    tm = TaskManager()
    with tm._tasks_lock:
        tm._tasks.clear()
    tm.register_stream("handler-test-1", threading.Event())
    try:
        response = handle_list_tasks({}, None)
        assert "tasks" in response
        assert len(response["tasks"]) == 1
        assert response["tasks"][0]["task_id"] == "handler-test-1"
    finally:
        with tm._tasks_lock:
            tm._tasks.clear()


def test_handle_cancel_request_missing_id():
    from app.handlers.task_handler import handle_cancel_request

    response = handle_cancel_request({}, None)
    assert response["cancelled"] is False
    assert "Missing request_id" in response["message"]


def test_handle_cancel_request_by_request_id():
    from app.handlers.task_handler import handle_cancel_request

    tm = TaskManager()
    with tm._tasks_lock:
        tm._tasks.clear()
    tm.register_stream("req-cancel-test", threading.Event())
    try:
        response = handle_cancel_request({"request_id": "req-cancel-test"}, None)
        assert response["cancelled"] is True
        assert response["task_id"] == "req-cancel-test"
    finally:
        with tm._tasks_lock:
            tm._tasks.clear()


def test_handle_cancel_request_by_task_id_alias():
    """request.cancel accepts task_id as an alias for request_id."""
    from app.handlers.task_handler import handle_cancel_request

    tm = TaskManager()
    with tm._tasks_lock:
        tm._tasks.clear()
    tm.register_stream("task-alias-test", threading.Event())
    try:
        response = handle_cancel_request({"task_id": "task-alias-test"}, None)
        assert response["cancelled"] is True
        assert response["task_id"] == "task-alias-test"
    finally:
        with tm._tasks_lock:
            tm._tasks.clear()


def test_handle_cancel_request_nonexistent():
    from app.handlers.task_handler import handle_cancel_request

    response = handle_cancel_request({"request_id": "nonexistent-id"}, None)
    assert response["cancelled"] is False
    assert "not found" in response["message"] or "completed" in response["message"]
