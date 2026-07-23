"""
Contract tests for the Task handler (``task.delete_output``).

The handler best-effort deletes output files/folders. It MUST refuse to touch
any path that does not resolve to a location inside ``get_output_dir()`` because
the incoming ``paths`` originate from renderer localStorage (user/devtools
editable).

The handler is called directly with ``(params, stream_handler)`` to mirror how
the framework dispatches it.
"""
import os
import shutil
import tempfile

import pytest

from app.handlers.task_handler import handle_delete_output, handle_read_log, handle_append_log, handle_delete_task_dir
from app.utils.env import get_output_dir


@pytest.fixture
def output_dir():
    """Ensure the output dir exists; return its resolved absolute path."""
    root = os.path.realpath(get_output_dir())
    os.makedirs(root, exist_ok=True)
    return root


def test_delete_file_under_output(output_dir):
    fd, path = tempfile.mkstemp(dir=output_dir, prefix="ct_file_", suffix=".tmp")
    os.close(fd)
    real = os.path.realpath(path)
    assert os.path.exists(real)

    result = handle_delete_output({"paths": [real]}, None)

    assert real in result["deleted"]
    assert not os.path.exists(real)
    assert result["failed"] == []


def test_delete_dir_under_output(output_dir):
    path = tempfile.mkdtemp(dir=output_dir, prefix="ct_dir_")
    # Put a file inside to prove recursive delete works.
    with open(os.path.join(path, "child.txt"), "w", encoding="utf-8") as f:
        f.write("x")
    real = os.path.realpath(path)
    assert os.path.isdir(real)

    result = handle_delete_output({"paths": [real]}, None)

    assert real in result["deleted"]
    assert not os.path.exists(real)


def test_nonexistent_path_noop(output_dir):
    real = os.path.realpath(os.path.join(output_dir, "does_not_exist_ct.tmp"))
    assert not os.path.exists(real)

    result = handle_delete_output({"paths": [real]}, None)

    # Idempotent: missing path is treated as success, never a failure.
    assert all(entry["path"] != real for entry in result["failed"])
    assert real in result["deleted"]


def test_refuse_path_outside_output():
    outside = tempfile.mkdtemp(prefix="ct_outside_")
    try:
        result = handle_delete_output({"paths": [outside]}, None)

        failed_paths = {entry["path"]: entry["error"] for entry in result["failed"]}
        assert outside in failed_paths
        assert "outside output dir" in failed_paths[outside]
        # Prove NO deletion occurred.
        assert os.path.exists(outside) is True
        assert outside not in result["deleted"]
    finally:
        shutil.rmtree(outside, ignore_errors=True)


def test_empty_path_skipped(output_dir):
    result = handle_delete_output({"paths": ["", "  "]}, None)

    assert result["deleted"] == []
    assert result["failed"] == []


# ──────────────────────────────────────────────────────────────────────
# handle_read_log
# ──────────────────────────────────────────────────────────────────────


def test_read_log_returns_content():
    from app.utils.env import get_task_dir
    task_dir = get_task_dir("ct_read_test")
    logs_dir = os.path.join(task_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, "task_exec.log")

    with open(log_path, "wb") as f:
        f.write(b"hello world\nline 2\n")

    result = handle_read_log({"task_id": "ct_read_test"}, None)

    assert result["content"] == "hello world\nline 2\n"
    assert result["truncated"] is False
    assert result["size"] > 0


def test_read_log_missing_task_returns_empty():
    result = handle_read_log({"task_id": "ct_nonexistent_zzz"}, None)

    assert result["content"] == ""
    assert result["truncated"] is False
    assert result["size"] == 0


def test_read_log_truncates_large_file():
    from app.utils.env import get_task_dir
    task_dir = get_task_dir("ct_trunc_test")
    logs_dir = os.path.join(task_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, "task_exec.log")

    # Write >1 MB of data.
    chunk = "A" * 1024  # 1 KB
    with open(log_path, "wb") as f:
        for _ in range(2048):  # 2 MB total
            f.write(chunk.encode("utf-8"))

    # Default tail_bytes is 1 MB (1024 * 1024 bytes).
    result = handle_read_log({"task_id": "ct_trunc_test", "tail_bytes": 1024 * 1024}, None)

    assert result["truncated"] is True
    assert len(result["content"]) <= 1024 * 1024 + 1024  # allow a little slack for decoding


def test_read_log_returns_log_path():
    from app.utils.env import get_task_dir

    task_dir = get_task_dir("ct_logpath_test")
    logs_dir = os.path.join(task_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, "task_exec.log")

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("test content")

    result = handle_read_log({"task_id": "ct_logpath_test"}, None)
    assert result["log_path"]
    assert result["log_path"].endswith(os.path.join("logs", "task_exec.log"))

    result2 = handle_read_log({"task_id": "ct_nonexistent_logpath"}, None)
    assert result2["log_path"]
    assert result2["log_path"].endswith(os.path.join("logs", "task_exec.log"))
    assert result2["content"] == ""

    result3 = handle_read_log({"task_id": ""}, None)
    assert result3["log_path"] == ""


# ──────────────────────────────────────────────────────────────────────
# handle_delete_task_dir
# ──────────────────────────────────────────────────────────────────────


def test_delete_task_dir_removes_tree():
    from app.utils.env import get_task_dir
    task_dir = get_task_dir("ct_delete_test")
    # Create a file inside the task dir.
    with open(os.path.join(task_dir, "dummy.txt"), "w", encoding="utf-8") as f:
        f.write("data")
    assert os.path.isdir(task_dir)

    result = handle_delete_task_dir({"task_id": "ct_delete_test"}, None)

    assert result["deleted"] is True
    assert result["path"] == task_dir
    assert not os.path.exists(task_dir)


def test_delete_task_dir_refuses_outside_tasks_root():
    # A malicious task_id with ".." is now caught by get_task_dir validation.
    result = handle_delete_task_dir({"task_id": "../../malicious"}, None)

    assert result["deleted"] is False
    assert "invalid" in result.get("error", "")


# ──────────────────────────────────────────────────────────────────────
# Invalid / empty task_id
# ──────────────────────────────────────────────────────────────────────


def test_read_log_empty_task_id():
    result = handle_read_log({"task_id": ""}, None)
    assert result["content"] == ""
    assert result["truncated"] is False
    assert result["size"] == 0


def test_delete_task_dir_empty_task_id():
    result = handle_delete_task_dir({"task_id": ""}, None)
    assert result["deleted"] is False
    assert "empty" in result.get("error", "")


def test_delete_task_dir_dotdot_traversal():
    """``..`` task_id must not crash and must not delete anything."""
    result = handle_delete_task_dir({"task_id": ".."}, None)
    assert result["deleted"] is False
    assert "invalid" in result.get("error", "")


def test_delete_task_dir_rejects_path_outside_tasks_root(monkeypatch):
    """A task dir that somehow resolves outside the tasks root must be rejected."""
    safe_root = tempfile.mkdtemp(prefix="ct_tasks_root_")
    monkeypatch.setattr("app.handlers.task_handler.get_tasks_root", lambda: safe_root)

    # Create a directory outside the tasks root.
    outside = tempfile.mkdtemp(prefix="ct_outside_tasks_")
    monkeypatch.setattr("app.handlers.task_handler.get_task_dir", lambda task_id: outside)

    try:
        result = handle_delete_task_dir({"task_id": "anything"}, None)
        assert result["deleted"] is False
        assert "outside tasks dir" in result.get("error", "")
        assert os.path.exists(outside) is True
    finally:
        shutil.rmtree(safe_root, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)


# ──────────────────────────────────────────────────────────────────────
# handle_append_log
# ──────────────────────────────────────────────────────────────────────


def test_append_log_writes_to_file():
    """Calling handle_append_log must create the per-task log file."""
    from app.utils.env import get_task_dir
    task_dir = get_task_dir("ct_append_test")
    logs_dir = os.path.join(task_dir, "logs")
    log_path = os.path.join(logs_dir, "task_exec.log")

    # Clean up any previous run
    if os.path.exists(log_path):
        os.remove(log_path)

    result = handle_append_log({"task_id": "ct_append_test", "line": "hello"}, None)

    assert result == {"written": True}
    assert os.path.exists(log_path)
    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "hello" in content


def test_append_log_empty_skips():
    """Empty task_id or line returns written=False and creates no file."""
    # Empty task_id
    r1 = handle_append_log({"task_id": "", "line": "x"}, None)
    assert r1 == {"written": False}

    # Empty line
    r2 = handle_append_log({"task_id": "ct_empty_skip", "line": ""}, None)
    assert r2 == {"written": False}

    # Both empty
    r3 = handle_append_log({"task_id": "", "line": ""}, None)
    assert r3 == {"written": False}
