"""Tests: FileWorkflowStore — the id-addressed saved-workflow persistence layer.

Covers the CRUD surface (save / load / list / delete / exists), the identity
rules (``wf-…`` id is the file name; the display name is free-form data), the
one-time legacy migrations (pre-id file names, and the pre-rename ``templates/``
directory), corrupt-file resilience in ``list``, atomic writes, and the default
writable-directory resolution.

Every test constructs the store with an explicit ``workflows_dir=tmp_path`` so
nothing touches the real output directory.
"""

import json
import os
import time

import pytest

from app.ids import WORKFLOW_ID_RE
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.store import (
    AmbiguousWorkflowNameError,
    FileWorkflowStore,
    WorkflowNotFoundError,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _definition(name="alpha", message="hello", description=None):
    return WorkflowDefinition(
        name=name,
        description=description if description is not None else f"definition {name}",
        nodes=[
            WorkflowNode(
                id="write",
                tool="file.write",
                params={"path": "out.txt", "content": "$inputs.message"},
                next="read",
            ),
            WorkflowNode(id="read", tool="file.read"),
        ],
    )


def _metadata(description="desc", tags=None):
    return {"description": description, "tags": list(tags or [])}


def _saved_ids(tmp_path):
    return sorted(p.name for p in tmp_path.iterdir())


# ---------------------------------------------------------------------------
# save / load roundtrip
# ---------------------------------------------------------------------------

def test_save_creates_an_id_named_json_file(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    info = store.save(_definition("alpha"), _metadata("desc", ["t1"]))

    assert WORKFLOW_ID_RE.match(info.id)
    assert info.name == "alpha"
    assert _saved_ids(tmp_path) == [f"{info.id}.json"]

    raw = json.loads((tmp_path / f"{info.id}.json").read_text(encoding="utf-8"))
    assert raw["definition"]["name"] == "alpha"
    assert raw["description"] == "desc"
    assert raw["tags"] == ["t1"]


def test_save_then_load_roundtrips_definition(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    original = _definition("alpha", "roundtrip")
    info = store.save(original, _metadata())

    loaded = store.load(info.id)
    assert loaded.name == "alpha"
    assert [node.id for node in loaded.nodes] == ["write", "read"]
    assert loaded.nodes[0].params["content"] == "$inputs.message"


def test_save_returns_wrapper_metadata(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    info = store.save(_definition("alpha"), _metadata("my description", ["a", "b"]))

    assert info.description == "my description"
    assert info.tags == ["a", "b"]
    assert info.node_count == 2
    assert info.created_at and info.updated_at


def test_save_with_an_explicit_id_overwrites_in_place(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    first = store.save(_definition("alpha"), _metadata())
    second = store.save(_definition("alpha", message="v2"), _metadata(), workflow_id=first.id)

    assert second.id == first.id
    assert _saved_ids(tmp_path) == [f"{first.id}.json"]


def test_save_rejects_a_non_id_shaped_explicit_id(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    with pytest.raises(ValueError, match="invalid workflow id"):
        store.save(_definition("alpha"), _metadata(), workflow_id="../../escape")


def test_save_requires_a_definition_name(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    with pytest.raises(ValueError, match="non-empty name"):
        store.save(_definition("   "), _metadata())


def test_free_form_display_names_are_not_path_constrained(tmp_path):
    """The name is data now, not a file name: separators and CJK are fine."""
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    for name in ["中文 名字", "a/b", "a:b*c?", "CON"]:
        info = store.save(_definition(name), _metadata())
        assert info.name == name
        assert WORKFLOW_ID_RE.match(info.id)
        assert store.load(name).name == name


# ---------------------------------------------------------------------------
# identity resolution: id or display name
# ---------------------------------------------------------------------------

def test_resolve_accepts_id_or_name(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    info = store.save(_definition("alpha"), _metadata())

    assert store.resolve(info.id) == info.id
    assert store.resolve("alpha") == info.id
    assert store.resolve("nope") is None
    # An id-shaped string that is not on disk resolves to nothing.
    assert store.resolve("wf-000000000000") is None


def test_resolve_is_case_insensitive_for_names(tmp_path):
    """The pre-id store compared names through the file system, so a
    case-insensitive fallback must keep old references working."""
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    info = store.save(_definition("Alpha"), _metadata())

    assert store.resolve("alpha") == info.id
    assert store.resolve("ALPHA") == info.id


def test_exact_name_match_wins_over_a_case_insensitive_one(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    lower = store.save(_definition("alpha"), _metadata())
    upper = store.save(_definition("Alpha"), _metadata())

    assert store.resolve("Alpha") == upper.id
    assert store.resolve("alpha") == lower.id


def test_ambiguous_name_raises_instead_of_guessing(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    store.save(_definition("twin"), _metadata())
    store.save(_definition("twin"), _metadata())

    with pytest.raises(AmbiguousWorkflowNameError) as excinfo:
        store.resolve("twin")
    assert "matches 2 workflows" in str(excinfo.value)
    # Both ids are reported so a caller can pick one.
    assert len(excinfo.value.ids) == 2


def test_exists_accepts_id_and_name(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    assert store.exists("alpha") is False

    info = store.save(_definition("alpha"), _metadata())
    assert store.exists(info.id) is True
    assert store.exists("alpha") is True


def test_exists_is_true_for_an_ambiguous_name(tmp_path):
    """Several workflows share the name — for "does it exist" that is a yes."""
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    store.save(_definition("twin"), _metadata())
    store.save(_definition("twin"), _metadata())
    assert store.exists("twin") is True


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def test_list_returns_metadata_sorted_by_display_name(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    store.save(_definition("beta"), _metadata("beta desc", ["x"]))
    store.save(_definition("alpha"), _metadata("alpha desc", ["y"]))

    infos = store.list()
    assert [info.name for info in infos] == ["alpha", "beta"]
    assert all(WORKFLOW_ID_RE.match(info.id) for info in infos)
    assert infos[0].description == "alpha desc"
    assert infos[0].tags == ["y"]


def test_list_reads_the_name_from_the_definition_not_the_file_name(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    store.save(_definition("显示名"), _metadata())

    info = store.list()[0]
    assert info.name == "显示名"
    assert WORKFLOW_ID_RE.match(info.id)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

def test_delete_removes_the_file_and_exists_returns_false(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    info = store.save(_definition("alpha"), _metadata())

    store.delete(info.id)
    assert _saved_ids(tmp_path) == []
    assert store.exists(info.id) is False
    assert store.list() == []


def test_delete_accepts_a_display_name(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    store.save(_definition("alpha"), _metadata())
    store.delete("alpha")
    assert store.list() == []


def test_load_deleted_workflow_raises_not_found(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    info = store.save(_definition("alpha"), _metadata())
    store.delete(info.id)

    with pytest.raises(WorkflowNotFoundError):
        store.load(info.id)


def test_load_missing_workflow_raises_not_found(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    with pytest.raises(WorkflowNotFoundError):
        store.load("ghost")


def test_delete_missing_workflow_raises_not_found(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    with pytest.raises(WorkflowNotFoundError):
        store.delete("ghost")


# ---------------------------------------------------------------------------
# Legacy migrations
# ---------------------------------------------------------------------------

def test_legacy_name_file_is_renamed_to_an_id(tmp_path):
    """A pre-id ``<display name>.json`` is migrated on store construction."""
    (tmp_path / "My Workflow.json").write_text(
        json.dumps({"definition": _definition("My Workflow").to_dict()}), encoding="utf-8"
    )

    store = FileWorkflowStore(workflows_dir=str(tmp_path))

    assert len(_saved_ids(tmp_path)) == 1
    [filename] = _saved_ids(tmp_path)
    assert WORKFLOW_ID_RE.match(filename[: -len(".json")])
    # The display name survived (it lives inside the file) and is resolvable.
    assert store.list()[0].name == "My Workflow"
    assert store.load("My Workflow").name == "My Workflow"


def test_legacy_migration_is_idempotent(tmp_path):
    (tmp_path / "legacy.json").write_text(
        json.dumps({"definition": _definition("legacy").to_dict()}), encoding="utf-8"
    )
    FileWorkflowStore(workflows_dir=str(tmp_path))
    after_first = _saved_ids(tmp_path)

    FileWorkflowStore(workflows_dir=str(tmp_path))
    assert _saved_ids(tmp_path) == after_first


def test_legacy_migration_leaves_unreadable_files_alone(tmp_path):
    """An unrelated/corrupt JSON must never be relabelled as a workflow."""
    (tmp_path / "junk.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "notes.json").write_text("[1, 2, 3]", encoding="utf-8")

    store = FileWorkflowStore(workflows_dir=str(tmp_path))

    assert "junk.json" in _saved_ids(tmp_path)
    assert "notes.json" in _saved_ids(tmp_path)
    assert store.list() == []


def test_legacy_templates_dir_is_adopted_into_workflows_dir(monkeypatch, tmp_path):
    """The pre-rename ``<output>/templates/`` files move into ``workflows/``."""
    output_dir = tmp_path / "out"
    legacy_dir = output_dir / "templates"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "old.json").write_text(
        json.dumps({"definition": _definition("old").to_dict()}), encoding="utf-8"
    )
    monkeypatch.setenv("BT_OUTPUT_DIR", str(output_dir))

    store = FileWorkflowStore()

    workflows_dir = output_dir / "workflows"
    assert os.path.normpath(store.workflows_dir) == os.path.normpath(str(workflows_dir))
    # Adopted AND renamed to an id; the legacy directory is gone once empty.
    assert not legacy_dir.exists()
    assert len(list(workflows_dir.iterdir())) == 1
    assert store.load("old").name == "old"


def test_legacy_templates_dir_is_ignored_for_an_explicit_store(tmp_path):
    """An explicitly configured store never reaches into an unrelated path."""
    legacy_dir = tmp_path / "templates"
    legacy_dir.mkdir()
    (legacy_dir / "old.json").write_text(
        json.dumps({"definition": _definition("old").to_dict()}), encoding="utf-8"
    )

    store = FileWorkflowStore(workflows_dir=str(tmp_path / "explicit"))

    assert (legacy_dir / "old.json").is_file()
    assert store.list() == []


# ---------------------------------------------------------------------------
# Atomic writes (tmp file + os.replace)
# ---------------------------------------------------------------------------

def test_save_leaves_no_tmp_sibling_behind(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    info = store.save(_definition("alpha"), _metadata())
    assert _saved_ids(tmp_path) == [f"{info.id}.json"]

    # Overwriting goes through the same tmp + replace path.
    store.save(_definition("alpha", message="v2"), _metadata(), workflow_id=info.id)
    assert _saved_ids(tmp_path) == [f"{info.id}.json"]
    assert not (tmp_path / f"{info.id}.json.tmp").exists()


def test_saved_file_is_complete_and_readable_immediately(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    info = store.save(_definition("alpha"), _metadata("desc", ["t1"]))

    # No flush/sleep/retry needed: the tmp file was atomically replaced.
    on_disk = (tmp_path / f"{info.id}.json").read_text(encoding="utf-8")
    assert on_disk.endswith("\n")
    assert store.load(info.id).name == "alpha"


def test_atomic_write_retries_a_transient_permission_error(tmp_path, monkeypatch):
    from app.workflow import store as store_module

    real_replace = store_module.os.replace
    calls = []

    def flaky_replace(src, dst):
        calls.append((src, dst))
        if len(calls) <= 2:
            raise PermissionError(13, "destination briefly locked")
        return real_replace(src, dst)

    monkeypatch.setattr(store_module.os, "replace", flaky_replace)

    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    info = store.save(_definition("alpha"), _metadata())

    assert len(calls) == 3, "the replace must be retried"
    assert store.load(info.id).name == "alpha"
    assert not (tmp_path / f"{info.id}.json.tmp").exists()


def test_atomic_write_cleans_up_tmp_when_replace_keeps_failing(tmp_path, monkeypatch):
    from app.workflow import store as store_module

    def always_locked(src, dst):
        raise PermissionError(13, "destination locked")

    monkeypatch.setattr(store_module.os, "replace", always_locked)

    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    with pytest.raises(PermissionError):
        store.save(_definition("alpha"), _metadata())

    # Neither a half-written target nor a leftover tmp file is left behind.
    assert _saved_ids(tmp_path) == []
    assert store.exists("alpha") is False


# ---------------------------------------------------------------------------
# path_for_id safety matrix
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        "",
        "..",
        "../escape",
        "sub/name",
        "sub\\name",
        "a..b",
        "..\\escape",
        "C:/abs",
        "wf-zzzzzzzzzzzz",
        "wf-0123456789ab extra",
    ],
)
def test_non_id_shaped_paths_are_rejected(tmp_path, value):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    with pytest.raises(ValueError):
        store.path_for_id(value)


@pytest.mark.parametrize("value", ["", None, 123, b"bytes"])
def test_empty_or_non_string_ids_rejected(tmp_path, value):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    with pytest.raises(ValueError, match="non-empty string"):
        store.path_for_id(value)


def test_a_crafted_id_cannot_escape_workflows_dir(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    with pytest.raises(ValueError):
        store.save(_definition("x"), _metadata(), workflow_id="../escaped")
    assert not (tmp_path.parent / "escaped.json").exists()


# ---------------------------------------------------------------------------
# Roundtrip / overwrite semantics
# ---------------------------------------------------------------------------

def test_roundtrip_preserves_metadata_and_node_count(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    store.save(
        _definition("alpha", message="meta-check"),
        _metadata("my description", ["tag-a", "tag-b"]),
    )

    info = store.list()[0]
    assert info.node_count == 2
    assert info.description == "my description"
    assert info.tags == ["tag-a", "tag-b"]

    loaded = store.load("alpha")
    assert len(loaded.nodes) == 2
    assert loaded.description == "definition alpha"


def test_overwrite_preserves_created_at_and_refreshes_updated_at(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    first = store.save(_definition("alpha"), _metadata("v1", ["t1"]))
    time.sleep(0.002)

    second = store.save(
        _definition("alpha", message="v2"), _metadata("v2", ["t2"]), workflow_id=first.id
    )

    assert second.created_at == first.created_at
    assert second.updated_at >= first.updated_at
    assert second.updated_at != first.updated_at
    # The stored definition itself was replaced.
    assert store.load(first.id).description == "definition alpha"


def test_overwrite_reuses_created_at_from_disk(tmp_path):
    # The second save reads created_at from the existing file, even for a fresh
    # store instance (i.e. created_at survives across store objects).
    first_store = FileWorkflowStore(workflows_dir=str(tmp_path))
    info = first_store.save(_definition("alpha"), _metadata())
    created_at = first_store.list()[0].created_at
    time.sleep(0.002)

    second_store = FileWorkflowStore(workflows_dir=str(tmp_path))
    second_store.save(_definition("alpha"), _metadata(), workflow_id=info.id)
    assert second_store.list()[0].created_at == created_at


# ---------------------------------------------------------------------------
# Corruption resilience / dir defaults
# ---------------------------------------------------------------------------

def test_corrupt_file_skipped_in_list(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    store.save(_definition("good"), _metadata())

    infos = store.list()
    assert [info.name for info in infos] == ["good"]


def test_corrupt_file_that_stays_corrupt_is_skipped(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    store.save(_definition("good"), _metadata())
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")

    infos = store.list()
    assert [info.name for info in infos] == ["good"]


def test_load_corrupt_file_raises_value_error(tmp_path):
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        store.load("broken")


def test_load_file_without_definition_wrapper_loads_as_raw(tmp_path):
    # Raw workflow files have no "definition" key; the whole file IS the
    # definition, and its display name comes from the definition itself.
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    (tmp_path / "bare.json").write_text('{"name": "raw-wf"}', encoding="utf-8")
    loaded = store.load("bare")
    assert loaded.name == "raw-wf"


def test_load_non_object_file_raises_value_error(tmp_path):
    # A JSON file that is not an object can never be a workflow.
    store = FileWorkflowStore(workflows_dir=str(tmp_path))
    (tmp_path / "array.json").write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a JSON object"):
        store.load("array")


def test_explicit_workflows_dir_created_on_construction(tmp_path):
    target = tmp_path / "nested" / "workflows"
    store = FileWorkflowStore(workflows_dir=str(target))
    assert store.workflows_dir == str(target)
    assert target.is_dir()


def test_default_workflows_dir_resolves_under_output_dir(monkeypatch, tmp_path):
    # The default store dir must live under get_output_dir() (a writable path),
    # NOT under cli/ (the read-only bundled resources).
    output_dir = tmp_path / "my-output"
    monkeypatch.setenv("BT_OUTPUT_DIR", str(output_dir))

    store = FileWorkflowStore()

    expected = os.path.normpath(str(output_dir / "workflows"))
    assert os.path.normpath(store.workflows_dir) == expected
    assert os.path.isdir(store.workflows_dir)
    assert os.access(store.workflows_dir, os.W_OK)


def test_explicit_workflows_dir_beats_output_dir_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path / "ignored"))
    store = FileWorkflowStore(workflows_dir=str(tmp_path / "explicit"))
    assert os.path.normpath(store.workflows_dir) == os.path.normpath(
        str(tmp_path / "explicit")
    )
    assert not (tmp_path / "ignored" / "workflows").exists()


def test_bt_workflows_dir_env_is_honored(monkeypatch, tmp_path):
    monkeypatch.setenv("BT_WORKFLOWS_DIR", str(tmp_path / "from-env"))
    store = FileWorkflowStore()
    assert os.path.normpath(store.workflows_dir) == os.path.normpath(
        str(tmp_path / "from-env")
    )


def test_legacy_bt_templates_dir_env_is_still_honored(monkeypatch, tmp_path):
    """A configured pre-rename env var keeps pointing at the same directory."""
    monkeypatch.delenv("BT_WORKFLOWS_DIR", raising=False)
    monkeypatch.setenv("BT_TEMPLATES_DIR", str(tmp_path / "legacy-env"))
    store = FileWorkflowStore()
    assert os.path.normpath(store.workflows_dir) == os.path.normpath(
        str(tmp_path / "legacy-env")
    )
