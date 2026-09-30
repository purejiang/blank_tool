"""Unit tests: FileTaskStore (task-definition persistence layer).

Covers the CRUD surface (save / load / list / delete / exists), the identity
rules (``tk-…`` id is the file name; the display name is free-form data), the
``path_for_id`` safety matrix, overwrite semantics (``created_at`` preserved,
``updated_at`` refreshed), the "inputs are stored verbatim" contract,
corrupt-file resilience in ``list``, the one-time legacy migration and the
``workflow_id`` backfill, and the default writable task-definitions dir
resolution (under ``get_output_dir()``, never under ``cli/`` and never in the
per-run ``tasks/`` scratch tree).

Every test constructs the store with an explicit ``task_defs_dir=tmp_path`` so
no real directory is touched.
"""

import json
import os

import pytest

from app.ids import TASK_ID_RE
from app.task.store import (
    AmbiguousTaskNameError,
    FileTaskStore,
    TaskDefinitionInfo,
    TaskNotFoundError,
)


def _store(tmp_path) -> FileTaskStore:
    return FileTaskStore(task_defs_dir=str(tmp_path))


def _files(tmp_path):
    return sorted(p.name for p in tmp_path.iterdir())


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def test_save_creates_an_id_named_json_file(tmp_path):
    store = _store(tmp_path)
    info = store.save("nightly", "apk-audit", {"apk_path": "D:/x.apk"}, "D:/wd", "audit")

    assert TASK_ID_RE.match(info.id)
    path = tmp_path / f"{info.id}.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {
        "name": "nightly",
        "workflow_id": None,
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
    assert TASK_ID_RE.match(info.id)
    # Optional fields default to their empty values.
    assert info.inputs == {}
    assert info.work_dir == ""
    assert info.description == ""
    assert info.workflow_id is None
    assert info.created_at and info.updated_at


def test_save_binds_a_workflow_by_id(tmp_path):
    store = _store(tmp_path)
    info = store.save("bound", workflow_id="wf-3f9a2b1c4d5e", workflow="display name")

    assert info.workflow_id == "wf-3f9a2b1c4d5e"
    assert store.load(info.id).workflow_id == "wf-3f9a2b1c4d5e"


def test_save_rejects_a_malformed_workflow_id(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="invalid workflow id"):
        store.save("bad", workflow_id="../../escape")


def test_save_requires_some_binding(tmp_path):
    store = _store(tmp_path)
    for bad in ("", "   ", None):
        with pytest.raises(ValueError, match="workflow"):
            store.save("epsilon", bad)


def test_save_then_load_roundtrip(tmp_path):
    store = _store(tmp_path)
    info = store.save("beta", "wf-b", {"n": 3, "flag": True}, "D:/work", "desc")

    loaded = store.load(info.id)
    assert loaded.to_dict() == {
        "name": "beta",
        "workflow_id": None,
        "workflow": "wf-b",
        "inputs": {"n": 3, "flag": True},
        "work_dir": "D:/work",
        "description": "desc",
        "created_at": loaded.created_at,
        "updated_at": loaded.updated_at,
    }


def test_free_form_display_names_are_not_path_constrained(tmp_path):
    """The task name is data now, not a file name."""
    store = _store(tmp_path)
    for name in ["中文 任务", "a/b", "a:b*c?", "CON"]:
        info = store.save(name, "wf-x")
        assert info.name == name
        assert TASK_ID_RE.match(info.id)
        assert store.load(name).name == name


def test_save_rejects_a_non_id_shaped_explicit_task_id(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="invalid task id"):
        store.save("alpha", "wf-a", task_id="../escape")


def test_save_with_an_explicit_id_overwrites_in_place(tmp_path):
    store = _store(tmp_path)
    first = store.save("gamma", "wf-g", {"a": 1})
    second = store.save("gamma", "wf-g2", {"a": 2}, task_id=first.id)

    assert second.id == first.id
    assert _files(tmp_path) == [f"{first.id}.json"]


def test_overwrite_preserves_created_at_and_refreshes_updated_at(tmp_path):
    store = _store(tmp_path)
    first = store.save("gamma", "wf-g", {"a": 1})
    second = store.save("gamma", "wf-g2", {"a": 2}, "D:/w2", "d2", task_id=first.id)

    assert second.created_at == first.created_at
    assert second.updated_at >= first.updated_at
    assert second.workflow == "wf-g2"
    # inputs are replaced wholesale, not merged with the previous save
    assert store.load(first.id).inputs == {"a": 2}


def test_inputs_are_stored_verbatim(tmp_path):
    """Nested values survive untouched — the store never interprets inputs."""
    store = _store(tmp_path)
    payload = {"nested": {"list": [1, "two", None]}, "empty": "", "unicode": "值"}
    info = store.save("delta", "wf-d", payload)

    assert store.load(info.id).inputs == payload


def test_list_sorted_by_display_name(tmp_path):
    store = _store(tmp_path)
    store.save("zeta", "wf-z")
    store.save("alpha", "wf-a")
    store.save("mid", "wf-m")

    infos = store.list()
    assert [info.name for info in infos] == ["alpha", "mid", "zeta"]
    assert all(TASK_ID_RE.match(info.id) for info in infos)


def test_list_returns_empty_when_dir_missing(tmp_path):
    store = FileTaskStore(task_defs_dir=str(tmp_path / "missing"))
    (tmp_path / "missing").rmdir()
    assert store.list() == []


def test_exists_accepts_id_and_name(tmp_path):
    store = _store(tmp_path)
    info = store.save("exists", "wf-e")

    assert store.exists(info.id) is True
    assert store.exists("exists") is True
    assert store.exists("nope") is False


def test_delete_removes_the_file(tmp_path):
    store = _store(tmp_path)
    info = store.save("doomed", "wf-d")

    store.delete(info.id)

    assert _files(tmp_path) == []
    assert store.exists("doomed") is False


def test_delete_unknown_raises(tmp_path):
    with pytest.raises(TaskNotFoundError):
        _store(tmp_path).delete("ghost")


def test_load_unknown_raises(tmp_path):
    with pytest.raises(TaskNotFoundError):
        _store(tmp_path).load("ghost")


def test_ambiguous_name_raises_instead_of_guessing(tmp_path):
    store = _store(tmp_path)
    store.save("twin", "wf-a")
    store.save("twin", "wf-b")

    with pytest.raises(AmbiguousTaskNameError) as excinfo:
        store.load("twin")
    assert "matches 2 tasks" in str(excinfo.value)
    assert len(excinfo.value.ids) == 2


# ---------------------------------------------------------------------------
# Legacy migration / backfill
# ---------------------------------------------------------------------------

def test_legacy_name_file_is_renamed_to_an_id(tmp_path):
    """A pre-id ``<display name>.json`` is migrated on store construction."""
    (tmp_path / "nightly.json").write_text(
        json.dumps({"name": "nightly", "workflow": "wf-a", "inputs": {}}),
        encoding="utf-8",
    )

    store = FileTaskStore(task_defs_dir=str(tmp_path))

    assert len(_files(tmp_path)) == 1
    [filename] = _files(tmp_path)
    assert TASK_ID_RE.match(filename[: -len(".json")])
    assert store.load("nightly").workflow == "wf-a"


def test_legacy_migration_writes_the_old_file_name_in_as_the_task_name(tmp_path):
    """Pre-id files did not store a name — the file name WAS the name, so the
    migration must preserve it instead of losing it to the rename."""
    (tmp_path / "nightly audit.json").write_text(
        json.dumps({"workflow": "wf-a"}), encoding="utf-8"
    )

    store = FileTaskStore(task_defs_dir=str(tmp_path))

    assert [info.name for info in store.list()] == ["nightly audit"]


def test_legacy_migration_is_idempotent(tmp_path):
    (tmp_path / "legacy.json").write_text(
        json.dumps({"name": "legacy", "workflow": "wf-a"}), encoding="utf-8"
    )
    FileTaskStore(task_defs_dir=str(tmp_path))
    after_first = _files(tmp_path)

    FileTaskStore(task_defs_dir=str(tmp_path))
    assert _files(tmp_path) == after_first


def test_legacy_migration_leaves_unreadable_files_alone(tmp_path):
    (tmp_path / "junk.json").write_text("{not json", encoding="utf-8")
    FileTaskStore(task_defs_dir=str(tmp_path))
    assert "junk.json" in _files(tmp_path)


def test_backfill_fills_in_a_missing_workflow_id(tmp_path):
    store = _store(tmp_path)
    info = store.save("dangling", "apk-audit")  # name-only binding
    assert store.load(info.id).workflow_id is None

    updated = store.backfill_workflow_ids(
        lambda name: "wf-3f9a2b1c4d5e" if name == "apk-audit" else None
    )

    assert updated == 1
    assert store.load(info.id).workflow_id == "wf-3f9a2b1c4d5e"
    # Idempotent: nothing left to fill in.
    assert store.backfill_workflow_ids(lambda name: "wf-other") == 0


def test_backfill_leaves_an_unresolvable_binding_alone(tmp_path):
    """A dangling task must keep reporting workflow_exists=False, not lose its
    binding to a backfill."""
    store = _store(tmp_path)
    info = store.save("dangling", "gone")

    assert store.backfill_workflow_ids(lambda name: None) == 0
    assert store.load(info.id).workflow == "gone"
    assert store.load(info.id).workflow_id is None


def test_backfill_skips_an_ambiguous_name(tmp_path):
    store = _store(tmp_path)
    info = store.save("dangling", "twin")

    def ambiguous(name):
        raise AmbiguousTaskNameError(name, ["wf-1", "wf-2"])

    assert store.backfill_workflow_ids(ambiguous) == 0
    assert store.load(info.id).workflow_id is None


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


def test_file_without_a_binding_is_treated_as_corrupt(tmp_path):
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
    assert info.name == "minimal"  # falls back to the file stem
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
# path_for_id safety matrix
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    ["", "..", "../escape", "sub/name", "sub\\name", "a..b", "..\\escape", "C:/abs"],
)
def test_non_id_shaped_paths_are_rejected(tmp_path, value):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.path_for_id(value)


@pytest.mark.parametrize("value", ["", None, 123, b"bytes"])
def test_empty_or_non_string_ids_rejected(tmp_path, value):
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="non-empty string"):
        store.path_for_id(value)


def test_a_crafted_id_cannot_escape_task_defs_dir(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.save("x", "wf-a", task_id="../escaped")
    assert not (tmp_path.parent / "escaped.json").exists()


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
