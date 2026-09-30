"""Tests: workflow.import_path (import_workflows_from_path + handler).

Covers the bulk workflow-import contract:

- a single workflow JSON file imports into the store and loads back;
- a directory import brings in every ``*.json`` (sorted), per-file
  failures are reported without stopping the remaining files;
- the stored display name comes from ``definition.name`` — a mismatch
  with the file stem is surfaced as ``renamed_from``;
- re-importing is idempotent: a file whose name already names exactly one
  stored workflow overwrites it in place, keeping its id (so task bindings and
  sub-workflow references survive a re-import);
- unusable inputs (missing path, directory without JSON) raise ToolException.

Every test uses an explicit ``FileWorkflowStore(workflows_dir=...)``
so no real workflows directory is touched.
"""

import json
from pathlib import Path

import pytest

from app.ids import WORKFLOW_ID_RE
from app.common.exceptions import ToolException
from app.handlers.workflow_handler import import_workflows_from_path
from app.workflow.store import FileWorkflowStore


def _workflow(name: str) -> dict:
    """A minimal valid workflow definition dict (single flow.log node)."""
    return {
        "name": name,
        "nodes": [
            {
                "id": "log",
                "tool": "flow.log",
                "params": {"message": "hi"},
            }
        ],
    }


def _write_workflow(dir_path: Path, filename: str, data: dict) -> Path:
    path = dir_path / filename
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def store(tmp_path):
    return FileWorkflowStore(workflows_dir=str(tmp_path / "workflows"))


class TestImportWorkflowsFromPath:
    def test_single_file_imports_and_loads_back(self, store, tmp_path):
        wf = _write_workflow(tmp_path, "solo.json", _workflow("solo"))

        report = import_workflows_from_path(str(wf), store=store)

        assert report["ok"] is True
        assert report["imported"] == 1
        assert report["results"][0]["status"] == "imported"
        assert report["results"][0]["name"] == "solo"
        assert WORKFLOW_ID_RE.match(report["results"][0]["id"])
        assert store.load("solo").name == "solo"

    def test_directory_import_brings_in_every_workflow(self, store, tmp_path):
        pack = tmp_path / "pack"
        pack.mkdir()
        _write_workflow(pack, "a.json", _workflow("alpha"))
        _write_workflow(pack, "b.json", _workflow("beta"))
        (pack / "notes.txt").write_text("not a workflow", encoding="utf-8")

        report = import_workflows_from_path(str(pack), store=store)

        assert report["ok"] is True
        assert report["imported"] == 2
        assert store.load("alpha").name == "alpha"
        assert store.load("beta").name == "beta"

    def test_bad_file_is_reported_without_stopping_others(
        self, store, tmp_path
    ):
        pack = tmp_path / "pack"
        pack.mkdir()
        _write_workflow(pack, "good.json", _workflow("good"))
        _write_workflow(pack, "bad.json", {"no_name": True})

        report = import_workflows_from_path(str(pack), store=store)

        assert report["ok"] is False
        assert report["imported"] == 1
        assert report["failed"] == 1
        by_file = {r["file"]: r for r in report["results"]}
        assert by_file["good.json"]["status"] == "imported"
        assert by_file["bad.json"]["status"] == "failed"
        assert "name" in by_file["bad.json"]["reason"]
        # The good one still landed in the store (per-file semantics).
        assert store.load("good").name == "good"

    def test_definition_name_wins_over_file_stem(self, store, tmp_path):
        wf = _write_workflow(
            tmp_path, "file-stem.json", _workflow("definition-name")
        )

        report = import_workflows_from_path(str(wf), store=store)

        entry = report["results"][0]
        assert entry["name"] == "definition-name"
        assert entry["renamed_from"] == "file-stem"
        assert store.load("definition-name").name == "definition-name"

    def test_reimport_overwrites_in_place_and_keeps_the_id(self, store, tmp_path):
        wf = _write_workflow(tmp_path, "solo.json", _workflow("solo"))
        first = import_workflows_from_path(str(wf), store=store)

        # Re-import a changed version of the same workflow.
        wf.write_text(json.dumps(_workflow("solo")), encoding="utf-8")
        second = import_workflows_from_path(str(wf), store=store)

        assert second["results"][0]["id"] == first["results"][0]["id"]
        assert len(store.list()) == 1

    def test_missing_path_raises(self, store, tmp_path):
        with pytest.raises(ToolException):
            import_workflows_from_path(str(tmp_path / "nope"), store=store)

    def test_directory_without_json_raises(self, store, tmp_path):
        with pytest.raises(ToolException):
            import_workflows_from_path(str(tmp_path), store=store)
