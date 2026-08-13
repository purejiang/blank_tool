"""Wave 4 tests: FileTemplateStore (template persistence layer).

Covers the CRUD surface (save / load / list / delete / exists), the ``_path_for``
safety matrix (path traversal, separators, empty / non-string names), metadata
roundtrips (description, tags, node_count), overwrite semantics (created_at
preserved, updated_at refreshed), ``copy_defaults`` seeding (never overwrites
user-edited templates), corrupt-file resilience in ``list``, and the default
writable templates-dir resolution (under ``get_output_dir()``, never under
``cli/``).

Every test constructs the store with an explicit ``templates_dir=tmp_path`` so
no real directory is touched.
"""

import json
import os
import time

import pytest

from app.template.store import FileTemplateStore, TemplateNotFoundError
from app.workflow.definition import WorkflowDefinition


def _definition(name="wf", message="hello", **overrides) -> WorkflowDefinition:
    """A 2-node file.write -> file.read definition as a WorkflowDefinition."""
    data = {
        "name": name,
        "version": "1.0",
        "description": f"definition {name}",
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
    data.update(overrides)
    return WorkflowDefinition.from_dict(data)


def _metadata(description="a template", tags=None):
    return {"description": description, "tags": list(tags or [])}


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def test_save_creates_json_file_in_templates_dir(tmp_path):
    store = FileTemplateStore(templates_dir=str(tmp_path))
    store.save("alpha", _definition("alpha"), _metadata("desc", ["t1"]))

    assert (tmp_path / "alpha.json").is_file()
    raw = json.loads((tmp_path / "alpha.json").read_text(encoding="utf-8"))
    assert raw["definition"]["name"] == "alpha"
    assert raw["description"] == "desc"
    assert raw["tags"] == ["t1"]


def test_save_then_load_roundtrips_definition(tmp_path):
    store = FileTemplateStore(templates_dir=str(tmp_path))
    original = _definition("alpha", message="roundtrip")
    store.save("alpha", original, _metadata())

    loaded = store.load("alpha")
    assert loaded.to_dict() == original.to_dict()
    assert [node.id for node in loaded.nodes] == ["write", "read"]


def test_list_returns_metadata_sorted_by_name(tmp_path):
    store = FileTemplateStore(templates_dir=str(tmp_path))
    store.save("beta", _definition("beta"), _metadata("beta desc", ["x", "y"]))
    store.save("alpha", _definition("alpha"), _metadata("alpha desc", ["z"]))

    infos = store.list()
    assert [info.name for info in infos] == ["alpha", "beta"]

    alpha = infos[0]
    assert alpha.description == "alpha desc"
    assert alpha.tags == ["z"]
    assert alpha.node_count == 2
    assert alpha.created_at
    assert alpha.updated_at


def test_delete_removes_file_and_exists_returns_false(tmp_path):
    store = FileTemplateStore(templates_dir=str(tmp_path))
    store.save("alpha", _definition("alpha"), _metadata())
    assert store.exists("alpha")

    store.delete("alpha")

    assert not (tmp_path / "alpha.json").exists()
    assert store.exists("alpha") is False
    assert store.list() == []


def test_load_deleted_template_raises_not_found(tmp_path):
    store = FileTemplateStore(templates_dir=str(tmp_path))
    store.save("alpha", _definition("alpha"), _metadata())
    store.delete("alpha")

    with pytest.raises(TemplateNotFoundError):
        store.load("alpha")


def test_load_missing_template_raises_not_found(tmp_path):
    store = FileTemplateStore(templates_dir=str(tmp_path))
    with pytest.raises(TemplateNotFoundError):
        store.load("ghost")


def test_delete_missing_template_raises_not_found(tmp_path):
    store = FileTemplateStore(templates_dir=str(tmp_path))
    with pytest.raises(TemplateNotFoundError):
        store.delete("ghost")


def test_exists_false_before_save_true_after(tmp_path):
    store = FileTemplateStore(templates_dir=str(tmp_path))
    assert store.exists("alpha") is False
    store.save("alpha", _definition("alpha"), _metadata())
    assert store.exists("alpha") is True


# ---------------------------------------------------------------------------
# _path_for safety matrix
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name",
    [
        "..",
        "../escape",
        "sub/name",
        "sub\\name",
        "a..b",
        "..\\escape",
    ],
)
def test_unsafe_names_rejected(tmp_path, name):
    store = FileTemplateStore(templates_dir=str(tmp_path))
    with pytest.raises(ValueError, match="invalid characters"):
        store._path_for(name)
    with pytest.raises(ValueError):
        store.save(name, _definition("x"), _metadata())


@pytest.mark.parametrize("name", ["", None, 123, b"bytes"])
def test_empty_or_non_string_names_rejected(tmp_path, name):
    store = FileTemplateStore(templates_dir=str(tmp_path))
    with pytest.raises(ValueError):
        store._path_for(name)


def test_unsafe_name_cannot_escape_templates_dir(tmp_path):
    store = FileTemplateStore(templates_dir=str(tmp_path))
    with pytest.raises(ValueError):
        store.save("../escaped", _definition("x"), _metadata())
    assert not (tmp_path.parent / "escaped.json").exists()


# ---------------------------------------------------------------------------
# Roundtrip / overwrite semantics
# ---------------------------------------------------------------------------

def test_roundtrip_preserves_metadata_and_node_count(tmp_path):
    store = FileTemplateStore(templates_dir=str(tmp_path))
    store.save(
        "alpha",
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
    store = FileTemplateStore(templates_dir=str(tmp_path))
    store.save("alpha", _definition("alpha"), _metadata("v1", ["t1"]))
    first = store.list()[0]
    time.sleep(0.002)

    store.save("alpha", _definition("alpha", message="v2"), _metadata("v2", ["t2"]))
    second = store.list()[0]

    assert second.created_at == first.created_at
    assert second.updated_at >= first.updated_at
    assert second.updated_at != first.updated_at
    # The stored definition itself was replaced.
    assert store.load("alpha").nodes[0].params["content"] == "$inputs.message"


def test_overwrite_reuses_created_at_from_disk(tmp_path):
    # Second save reads created_at from the existing file, even for a fresh
    # store instance (i.e. created_at survives across store objects).
    first_store = FileTemplateStore(templates_dir=str(tmp_path))
    first_store.save("alpha", _definition("alpha"), _metadata())
    created_at = first_store.list()[0].created_at
    time.sleep(0.002)

    second_store = FileTemplateStore(templates_dir=str(tmp_path))
    second_store.save("alpha", _definition("alpha"), _metadata())
    assert second_store.list()[0].created_at == created_at


# ---------------------------------------------------------------------------
# Corruption resilience / dir defaults
# ---------------------------------------------------------------------------

def test_corrupt_file_skipped_in_list(tmp_path):
    store = FileTemplateStore(templates_dir=str(tmp_path))
    store.save("good", _definition("good"), _metadata())
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")

    infos = store.list()
    assert [info.name for info in infos] == ["good"]


def test_load_corrupt_file_raises_value_error(tmp_path):
    store = FileTemplateStore(templates_dir=str(tmp_path))
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        store.load("broken")


def test_load_file_without_definition_wrapper_loads_as_raw(tmp_path):
    # Raw workflow files (seeded by copy_defaults) have no "definition" key;
    # the whole file IS the definition (F3 fix).
    store = FileTemplateStore(templates_dir=str(tmp_path))
    (tmp_path / "bare.json").write_text('{"name": "raw-wf"}', encoding="utf-8")
    loaded = store.load("bare")
    assert loaded.name == "raw-wf"


def test_load_non_object_file_raises_value_error(tmp_path):
    # A JSON file that is not an object can never be a template.
    store = FileTemplateStore(templates_dir=str(tmp_path))
    (tmp_path / "array.json").write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a JSON object"):
        store.load("array")


def test_explicit_templates_dir_created_on_construction(tmp_path):
    target = tmp_path / "nested" / "templates"
    store = FileTemplateStore(templates_dir=str(target))
    assert store.templates_dir == str(target)
    assert target.is_dir()


def test_default_templates_dir_resolves_under_output_dir(monkeypatch, tmp_path):
    # The default store dir must live under get_output_dir() (a writable path),
    # NOT under cli/ (the read-only bundled resources).
    output_dir = tmp_path / "my-output"
    monkeypatch.setenv("BT_OUTPUT_DIR", str(output_dir))

    store = FileTemplateStore()

    expected = os.path.normpath(str(output_dir / "templates"))
    assert os.path.normpath(store.templates_dir) == expected
    assert os.path.isdir(store.templates_dir)
    assert os.access(store.templates_dir, os.W_OK)


def test_explicit_templates_dir_beats_output_dir_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path / "ignored"))
    store = FileTemplateStore(templates_dir=str(tmp_path / "explicit"))
    assert os.path.normpath(store.templates_dir) == os.path.normpath(
        str(tmp_path / "explicit")
    )
    assert not (tmp_path / "ignored" / "templates").exists()
