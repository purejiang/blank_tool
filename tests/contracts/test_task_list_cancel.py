"""
Contract tests for ``task.list`` and ``request.cancel`` handlers.

The TaskManager singleton keys registrations by **run_id** (the JSON-RPC
request id) and keeps a secondary index by ``task_id``, so a cancel by either
id reaches the run.  Tests must not leak state into each other, so every test
starts (and ends) with all four internal maps — ``_tasks``, ``_by_task``,
``_tombstones`` and ``_seen`` — cleared under ``_tasks_lock``.

Two cancel rules are load-bearing here and were verified against
``cli/app/common/task_manager.py``:

* cancelling an id that has *not* registered yet returns True and arms a
  short-lived tombstone, which the matching ``register`` consumes (so a cancel
  that races the execute request is never lost);
* cancelling an id whose run *recently finished* returns False — a late cancel
  must not poison the next run that reuses the id.
"""

import threading

import pytest

from app.common.task_manager import TaskManager


class _StubProcess:
    """Stands in for a ``subprocess.Popen`` (real spawns are sandbox-blocked)."""

    pid = 4242
    returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15


def _clear(tm):
    with tm._tasks_lock:
        tm._tasks.clear()
        tm._by_task.clear()
        tm._tombstones.clear()
        tm._seen.clear()


@pytest.fixture(autouse=True)
def _clean_task_manager():
    """Reset the TaskManager singleton around every test."""
    tm = TaskManager()
    _clear(tm)
    yield
    _clear(tm)


def _entry_for(tm, run_id):
    """Return the single list_tasks() entry for *run_id*."""
    matches = [item for item in tm.list_tasks() if item["run_id"] == run_id]
    assert len(matches) == 1, f"expected exactly one entry for {run_id!r}"
    return matches[0]


# ──────────────────────────────────────────────────────────────────────
# TaskManager.list_tasks()
# ──────────────────────────────────────────────────────────────────────


def test_list_tasks_returns_empty_when_none_registered():
    tm = TaskManager()
    assert tm.list_tasks() == []


def test_list_tasks_returns_registered_run():
    tm = TaskManager()
    tm.register("run-1", "test-task-1", threading.Event())

    result = tm.list_tasks()
    assert len(result) == 1
    entry = result[0]
    assert entry["run_id"] == "run-1"
    assert entry["task_id"] == "test-task-1"
    assert entry["cancelled"] is False
    assert entry["has_process"] is False
    assert entry["started_at"] is not None
    # The wire shape is exactly these five keys — the old "type" field is gone.
    assert set(entry) == {
        "run_id",
        "task_id",
        "cancelled",
        "started_at",
        "has_process",
    }


def test_list_tasks_does_not_expose_the_process_holder():
    """list_tasks() must NOT leak the holder dict (it carries a Popen)."""
    tm = TaskManager()
    tm.register("run-2", "test-task-2", threading.Event())
    holder = {"process": _StubProcess()}
    tm.attach_process("run-2", holder)

    entry = _entry_for(tm, "run-2")
    # The attachment is reported as a boolean...
    assert entry["has_process"] is True
    # ...and the holder / Popen itself is never part of the entry.
    for forbidden in ("holder", "process", "process_holder"):
        assert forbidden not in entry, (
            f"{forbidden!r} (contains Popen) must NOT be exposed by list_tasks()"
        )
    assert holder not in entry.values()


def test_list_tasks_reports_a_run_registered_with_a_stop_event():
    """A run carrying a stop_event is listed, not cancelled, until cancelled."""
    tm = TaskManager()
    stop = threading.Event()
    tm.register("run-stream-1", "test-stream-1", stop)

    entry = _entry_for(tm, "run-stream-1")
    assert entry["task_id"] == "test-stream-1"
    assert entry["cancelled"] is False
    assert entry["has_process"] is False

    # Cancelling the run signals the registered stop_event.
    assert tm.cancel("run-stream-1") is True
    assert stop.is_set()
    assert _entry_for(tm, "run-stream-1")["cancelled"] is True


def test_list_tasks_reflects_cancelled_state():
    tm = TaskManager()
    tm.register("run-cancel-1", "test-cancel-1", threading.Event())
    assert tm.cancel("run-cancel-1") is True

    entry = _entry_for(tm, "run-cancel-1")
    assert entry["cancelled"] is True


def test_unregister_removes_only_that_run():
    tm = TaskManager()
    tm.register("run-keep", "task-keep")
    tm.register("run-drop", "task-drop")

    tm.unregister("run-drop")

    listed = {item["run_id"] for item in tm.list_tasks()}
    assert listed == {"run-keep"}
    # The removed run is remembered as finished, so a late cancel is rejected.
    assert tm.cancel("run-drop") is False


# ──────────────────────────────────────────────────────────────────────
# Cancel
# ──────────────────────────────────────────────────────────────────────


def test_cancel_of_a_never_seen_id_arms_a_one_shot_tombstone():
    """A cancel that beats its run's registration is never lost."""
    tm = TaskManager()
    assert tm.cancel("never-registered") is True
    assert tm.is_cancelled("never-registered") is True

    # The tombstone is consumed by the matching registration...
    tm.register("never-registered", "late-task")
    assert _entry_for(tm, "never-registered")["cancelled"] is True

    # ...and is one-shot: re-registering the same id is a fresh, live run.
    tm.register("never-registered", "late-task")
    assert _entry_for(tm, "never-registered")["cancelled"] is False


def test_cancel_of_a_recently_finished_run_returns_false():
    """A late cancel for a finished run must not poison a future run."""
    tm = TaskManager()
    tm.register("run-finished", "task-finished")
    tm.unregister("run-finished")

    assert tm.cancel("run-finished") is False
    assert tm.is_cancelled("run-finished") is False


def test_cancel_with_registered_run():
    tm = TaskManager()
    tm.register("run-cancel-2", "test-cancel-2", threading.Event())

    assert tm.cancel("run-cancel-2") is True
    assert tm.is_cancelled("run-cancel-2") is True


def test_cancel_by_task_id_cancels_every_run_under_it():
    tm = TaskManager()
    tm.register("run-a", "shared-task")
    tm.register("run-b", "shared-task")

    assert tm.cancel("shared-task") is True
    assert tm.is_cancelled("run-a") is True
    assert tm.is_cancelled("run-b") is True


# ──────────────────────────────────────────────────────────────────────
# Handler dispatch (through handle_list_tasks / handle_cancel_request)
# ──────────────────────────────────────────────────────────────────────


def test_handle_list_tasks():
    """Call the handler function directly to verify API_MAP dispatch path."""
    from app.handlers.task_handler import handle_list_tasks

    tm = TaskManager()
    tm.register("run-handler", "handler-test-1", threading.Event())

    response = handle_list_tasks({}, None)
    assert "tasks" in response
    assert len(response["tasks"]) == 1
    assert response["tasks"][0]["run_id"] == "run-handler"
    assert response["tasks"][0]["task_id"] == "handler-test-1"


def test_handle_cancel_request_missing_id():
    from app.handlers.task_handler import handle_cancel_request

    response = handle_cancel_request({}, None)
    assert response["cancelled"] is False
    assert "Missing request_id" in response["message"]


def test_handle_cancel_request_by_request_id():
    from app.handlers.task_handler import handle_cancel_request

    tm = TaskManager()
    tm.register("req-cancel-test", "task-for-req")

    response = handle_cancel_request({"request_id": "req-cancel-test"}, None)
    assert response["cancelled"] is True
    assert response["task_id"] == "req-cancel-test"
    assert tm.is_cancelled("req-cancel-test") is True


def test_handle_cancel_request_by_task_id_alias():
    """request.cancel accepts task_id as an alias for request_id."""
    from app.handlers.task_handler import handle_cancel_request

    tm = TaskManager()
    tm.register("run-alias", "task-alias-test")

    response = handle_cancel_request({"task_id": "task-alias-test"}, None)
    assert response["cancelled"] is True
    assert response["task_id"] == "task-alias-test"
    assert tm.is_cancelled("run-alias") is True


def test_handle_cancel_request_before_register_is_honored():
    """The first cancel of an unseen id is a success (tombstone armed)."""
    from app.handlers.task_handler import handle_cancel_request

    tm = TaskManager()
    response = handle_cancel_request({"request_id": "cancel-early-id"}, None)
    assert response["cancelled"] is True

    # The run that registers afterwards starts already cancelled.
    tm.register("cancel-early-id", "early-task")
    assert _entry_for(tm, "cancel-early-id")["cancelled"] is True


def test_handle_cancel_request_after_completion_returns_false():
    from app.handlers.task_handler import handle_cancel_request

    tm = TaskManager()
    tm.register("run-done", "task-done")
    tm.unregister("run-done")

    response = handle_cancel_request({"request_id": "run-done"}, None)
    assert response["cancelled"] is False
    assert "not found" in response["message"] or "completed" in response["message"]
