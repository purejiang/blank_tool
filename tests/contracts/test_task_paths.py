"""
Contract tests for per-task working directory resolver (env.py).

``get_tasks_root()`` returns the tasks root (inside the cache directory).
``get_task_dir(task_id)`` creates and returns ``<tasks_root>/<task_id>/``.
``get_task_subdir(task_id, name)`` creates a named sub-directory underneath.
"""
import os
import shutil
import tempfile

import pytest

from app.env import get_task_dir, get_task_subdir, get_tasks_root


@pytest.fixture
def temp_cache(monkeypatch):
    """Redirect ``get_cache_dir()`` to a temp directory; clean up after."""
    tmp = tempfile.mkdtemp(prefix="ct_task_paths_")
    monkeypatch.setattr("app.env.get_cache_dir", lambda: tmp)
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


def test_tasks_root_inside_cache_dir(temp_cache):
    """``get_tasks_root()`` must be inside ``get_cache_dir()``, NOT under output."""
    tasks_root = get_tasks_root()
    assert tasks_root == os.path.join(temp_cache, "tasks")
    assert not tasks_root.startswith(temp_cache + os.path.join("Tasks", ""))
    assert os.path.isdir(tasks_root)


def test_task_dir_under_tasks_root(temp_cache):
    """Task dir should live inside the tasks root (under cache dir)."""
    d = get_task_dir("42")
    assert d.endswith(os.sep + "42")
    assert d.startswith(temp_cache)


def test_task_dir_creates_subdirs(temp_cache):
    """``get_task_subdir("42", "input")`` must create ``Tasks/42/input/`` on disk."""
    sub = get_task_subdir("42", "input")
    assert os.path.isdir(sub)
    assert sub.endswith(os.path.join("42", "input"))


def test_empty_task_id_raises():
    """An empty task_id is forbidden."""
    with pytest.raises(ValueError):
        get_task_dir("")


def test_task_dir_rejects_traversal():
    """Path traversal / separators / single-dot must raise ValueError."""
    bad_ids = ["..", ".", "a/b", "a\\b"]

    for bad in bad_ids:
        with pytest.raises(ValueError, match="invalid"):
            get_task_dir(bad)
