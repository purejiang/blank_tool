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

from app.handlers.task_handler import handle_delete_output
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
