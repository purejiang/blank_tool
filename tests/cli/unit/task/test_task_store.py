"""Unit tests: FileTaskStore (task-definition persistence layer).

Covers the CRUD surface (save / load / list / delete / exists), the ``_path_for``
safety matrix (path traversal, separators, empty / non-string names), overwrite
semantics (``created_at`` preserved, ``updated_at`` refreshed), the "inputs are
stored verbatim" contract, corrupt-file resilience in ``list``, and the default
writable task-definitions dir resolution (under ``get_output_dir()``, never under
``cli/`` and never in the per-run ``tasks/`` scratch tree).

Every test constructs the store with an explicit ``task_defs_dir=tmp_path`` so
no real directory is touched.
"""

import json
import os

import pytest

from app.task.store import FileTaskStore, TaskDefinitionInfo, TaskNotFoundError


def _store(tmp_path) -> FileTaskStore:
    return FileTaskStore(task_defs_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def test_save_creates_json_file_in_task_defs_dir(tmp_path):
    store = _store(tmp_path)
    info = store.save("nightly", "apk-audit", {"apk_path": "D:/x.apk"}, "D:/wd", "audit")

    path = tmp_path / "nightly.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {
        "name": "nightly",
        "workflow": "apk-audit",
        "inputs": {"apk_path": "D:/x.apk"},
        "work_dir": "D:/wd",
        "description": "audit",
        "created_at": info.created_at,
        "updated_at": info.updated_at,
    }


def test_save_returns_the_stored_definition(tmp_path):
    store = _store(tmp_path)
    info = store.save("alpha", "wf-a")

    assert isinstance(info, TaskDefinitionInfo)
    assert (info.name, info.workflow) == ("alpha", "wf-a")
    # Optional fields default to their empty values.
    assert info.inputs == {}
    assert info.work_dir == ""
    assert info.description == ""
    assert info.created_at and info.updated_at


def test_save_then_load_roundtrip(tmp_path):
    store = _store(tmp_path)
    store.save("beta", "wf-b", {"n": 3, "flag": True}, "D:/work", "desc")

    loaded = store.load("beta")
    assert loaded.to_dict() == {
        "name": "beta",
        "workflow": "wf-b",
        "inputs": {"n": 3, "flag": True},
        "work_dir": "D:/work",
        "description": "desc",
        "created_at": loaded.created_at,
        "updated_at": loaded.updated_at,
    }


def test_overwrite_preserves_created_at_and_refreshes_updated_at(tmp_path):
    store = _store(tmp_path)
    first = store.save("gamma", "wf-g", {"a": 1})
    second = store.save("gamma", "wf-g2", {"a": 2}, "D:/w2", "d2")

    assert second.created_at == first.created_at
    assert second.updated_at >= first.updated_at
    assert second.workflow == "wf-g2"
    # inputs are replaced wholesale, not merged with the previous save
    assert store.load("gamma").inputs == {"a": 2}


def test_inputs_are_stored_verbatim(tmp_path):
    """Nested values survive untouched — the store never interprets inputs."""
    store = _store(tmp_path)
    payload = {"nested": {"list": [1, "two", None]}, "empty": "", "unicode": "值"}
    store.save("delta", "wf-d", payload)

    assert store.load("delta").inputs == payload


def test_save_rejects_a_blank_workflow(tmp_path):
    store = _store(tmp_path)
    for bad in ("", "   ", None, 5):
        with pytest.raises(ValueError, match="workflow"):
            store.save("epsilon", bad)


def test_save_rejects_unsafe_names(tmp_path):
    store = _store(tmp_path)
    for bad in ("", "../escape", "a/b", "a\\b", "..", None, 7):
        with pytest.raises(ValueError):
            store.save(bad, "wf")


def test_list_sorted_by_name(tmp_path):
    store = _store(tmp_path)
    store.save("zeta", "wf-z")
    store.save("alpha", "wf-a")
    store.save("mid", "wf-m")

    assert [info.name for info in store.list()] == ["alpha", "mid", "zeta"]


def test_list_returns_empty_when_dir_missing(tmp_path):
    store = FileTaskStore(task_defs_dir=str(tmp_path / "missing"))
    (tmp_path / "missing").rmdir()
    assert store.list() == []


def test_exists(tmp_path):
    store = _store(tmp_path)
    store.save("exists", "wf-e")

    assert store.exists("exists") is True
    assert store.exists("nope") is False


def test_delete_removes_the_file(tmp_path):
    store = _store(tmp_path)
    store.save("doomed", "wf-d")

    store.delete("doomed")

    assert not (tmp_path / "doomed.json").exists()
    assert store.exists("doomed") is False


def test_delete_unknown_raises(tmp_path):
    with pytest.raises(TaskNotFoundError):
        _store(tmp_path).delete("ghost")


def test_load_unknown_raises(tmp_path):
    with pytest.raises(TaskNotFoundError):
        _store(tmp_path).load("ghost")


# ---------------------------------------------------------------------------
# Corruption resilience
# ---------------------------------------------------------------------------

def test_corrupt_file_skipped_in_list(tmp_path):
    store = _store(tmp_path)
    store.save("good", "wf-good")
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")

    assert [info.name for info in store.list()] == ["good"]


def test_load_corrupt_file_raises_value_error(tmp_path):
    store = _store(tmp_path)
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON"):
        store.load("broken")


def test_file_without_a_workflow_is_treated_as_corrupt(tmp_path):
    """A task with no workflow can never run, so it is not a valid task."""
    store = _store(tmp_path)
    (tmp_path / "noworkflow.json").write_text(
        json.dumps({"name": "noworkflow", "inputs": {}}), encoding="utf-8"
    )
    (tmp_path / "blankworkflow.json").write_text(
        json.dumps({"workflow": "   "}), encoding="utf-8"
    )

    assert store.list() == []
    for bad in ("noworkflow", "blankworkflow"):
        with pytest.raises(ValueError, match="workflow"):
            store.load(bad)


def test_non_object_inputs_is_treated_as_corrupt(tmp_path):
    store = _store(tmp_path)
    (tmp_path / "badinputs.json").write_text(
        json.dumps({"workflow": "wf", "inputs": [1, 2]}), encoding="utf-8"
    )

    assert store.list() == []
    with pytest.raises(ValueError, match="inputs"):
        store.load("badinputs")


def test_non_object_file_is_treated_as_corrupt(tmp_path):
    store = _store(tmp_path)
    (tmp_path / "array.json").write_text("[1, 2, 3]", encoding="utf-8")

    assert store.list() == []
    with pytest.raises(ValueError, match="expected a JSON object"):
        store.load("array")


def test_tolerates_missing_optional_fields(tmp_path):
    store = _store(tmp_path)
    (tmp_path / "minimal.json").write_text(
        json.dumps({"workflow": "wf-min"}), encoding="utf-8"
    )

    info = store.load("minimal")
    assert info.inputs == {}
    assert info.work_dir == ""
    assert info.description == ""
    assert info.created_at is None
    assert info.updated_at is None


def test_ignores_non_json_entries(tmp_path):
    store = _store(tmp_path)
    store.save("real", "wf-r")
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")
    (tmp_path / "subdir").mkdir()

    assert [info.name for info in store.list()] == ["real"]


# ---------------------------------------------------------------------------
# Directory resolution
# ---------------------------------------------------------------------------

def test_explicit_dir_created_on_construction(tmp_path):
    target = tmp_path / "nested" / "task_defs"
    store = FileTaskStore(task_defs_dir=str(target))

    assert store.task_defs_dir == str(target)
    assert target.is_dir()


def test_default_dir_resolves_under_output_dir(monkeypatch, tmp_path):
    # The default store dir must live under get_output_dir() (a writable path),
    # NOT under cli/ (read-only bundled resources) and NOT under the per-run
    # tasks/ scratch tree that tasks.clear wipes.
    output_dir = tmp_path / "my-output"
    monkeypatch.setenv("BT_OUTPUT_DIR", str(output_dir))
    monkeypatch.delenv("BT_TASK_DEFS_DIR", raising=False)

    store = FileTaskStore()

    expected = os.path.normpath(str(output_dir / "task_defs"))
    assert os.path.normpath(store.task_defs_dir) == expected
    assert os.path.isdir(store.task_defs_dir)
    assert os.access(store.task_defs_dir, os.W_OK)


def test_explicit_dir_beats_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BT_TASK_DEFS_DIR", str(tmp_path / "from-env"))

    store = FileTaskStore(task_defs_dir=str(tmp_path / "explicit"))

    assert os.path.normpath(store.task_defs_dir) == os.path.normpath(
        str(tmp_path / "explicit")
    )


def test_env_override_beats_output_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("BT_TASK_DEFS_DIR", str(tmp_path / "from-env"))

    store = FileTaskStore()

    assert os.path.normpath(store.task_defs_dir) == os.path.normpath(
        str(tmp_path / "from-env")
    )
