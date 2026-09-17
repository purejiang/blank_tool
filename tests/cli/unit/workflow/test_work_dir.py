"""The run's working directory is the workflow's OWN directory.

An explicit ``work_dir`` always wins; otherwise a run is anchored to where the
workflow came from — the folder holding the workflow JSON file, or the
template store's folder — so relative paths resolve predictably and produced
artifacts stay next to the workflow instead of landing in the process CWD.
"""

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

import app.handlers.template_handler as template_handler
from app.handlers.template_handler import handle_execute as template_execute
from app.handlers.template_handler import handle_save as template_save
from app.handlers.workflow_handler import handle_execute as workflow_execute
from app.tools.builtin.base import ToolContext
from app.tools.builtin.text_tools import TextGrep
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.runner import run_workflow

ROOT = Path(__file__).resolve().parents[4]


def _write_definition(folder: Path, name: str, relative_artifact: str) -> str:
    """Write a one-node workflow that writes *relative_artifact* and return its path."""
    definition = {
        "name": name,
        "nodes": [
            {
                "id": "write",
                "tool": "file.write",
                "params": {"path": relative_artifact, "content": "ok"},
                "next": None,
            }
        ],
    }
    path = folder / f"{name}.json"
    path.write_text(json.dumps(definition, indent=2), encoding="utf-8")
    return str(path)


def _inline_definition(name: str, relative_artifact: str) -> WorkflowDefinition:
    return WorkflowDefinition(
        name=name,
        nodes=[
            WorkflowNode(
                id="write",
                tool="file.write",
                params={"path": relative_artifact, "content": "ok"},
            )
        ],
    )


def _load_cli():
    """Import cli/cli.py as a module (the CLI itself spawns no process)."""
    cli_dir = ROOT / "cli"
    if str(cli_dir) not in sys.path:
        sys.path.insert(0, str(cli_dir))
    spec = importlib.util.spec_from_file_location("cli_under_test", cli_dir / "cli.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# run_workflow: source_dir is the fallback work dir
# ---------------------------------------------------------------------------

def test_run_workflow_uses_the_source_dir_when_no_work_dir(tmp_path):
    source = tmp_path / "workflow-home"
    source.mkdir()
    payload = run_workflow(
        _inline_definition("anchored", "artifact.txt"),
        {"inputs": {}},
        None,
        None,
        run_id="run-src",
        source_dir=str(source),
    )
    assert payload["success"] is True, payload["error"]
    assert (source / "artifact.txt").is_file()
    assert not (tmp_path / "artifact.txt").exists()


def test_run_workflow_prefers_an_explicit_work_dir(tmp_path):
    source = tmp_path / "workflow-home"
    explicit = tmp_path / "explicit"
    source.mkdir()
    explicit.mkdir()
    payload = run_workflow(
        _inline_definition("explicit", "artifact.txt"),
        {"inputs": {}, "work_dir": str(explicit)},
        None,
        None,
        run_id="run-explicit",
        source_dir=str(source),
    )
    assert payload["success"] is True, payload["error"]
    assert (explicit / "artifact.txt").is_file()
    assert not (source / "artifact.txt").exists()


# ---------------------------------------------------------------------------
# workflow.execute: the workflow file's folder
# ---------------------------------------------------------------------------

def test_workflow_execute_anchors_to_the_workflow_file(tmp_path):
    graphs = tmp_path / "graphs"
    graphs.mkdir()
    workflow_path = _write_definition(graphs, "from-file", "file-artifact.txt")

    payload = workflow_execute({"path": workflow_path, "inputs": {}}, None)

    assert payload["success"] is True, payload["error"]
    assert (graphs / "file-artifact.txt").is_file()
    assert not (tmp_path / "file-artifact.txt").exists()


def test_inline_definition_still_falls_back_to_the_process_cwd(tmp_path, monkeypatch):
    """An inline definition has no own directory; the CWD stays the anchor."""
    monkeypatch.chdir(tmp_path)
    payload = workflow_execute(
        {
            "definition": {
                "name": "inline",
                "nodes": [
                    {
                        "id": "write",
                        "tool": "file.write",
                        "params": {"path": "cwd-artifact.txt", "content": "ok"},
                        "next": None,
                    }
                ],
            },
            "inputs": {},
        },
        None,
    )
    assert payload["success"] is True, payload["error"]
    assert (tmp_path / "cwd-artifact.txt").is_file()


# ---------------------------------------------------------------------------
# template.execute: the template store's folder
# ---------------------------------------------------------------------------

def test_template_execute_anchors_to_the_template_store(tmp_path, monkeypatch):
    templates = tmp_path / "tpls"
    monkeypatch.setenv("BT_TEMPLATES_DIR", str(templates))
    monkeypatch.setattr(template_handler, "_store", None)

    template_save(
        {
            "name": "tpl-anchored",
            "definition": {
                "name": "tpl-anchored",
                "nodes": [
                    {
                        "id": "write",
                        "tool": "file.write",
                        "params": {"path": "tpl-artifact.txt", "content": "ok"},
                        "next": None,
                    }
                ],
            },
        },
        None,
    )

    payload = template_execute({"name": "tpl-anchored", "inputs": {}}, None)

    assert payload["success"] is True, payload["error"]
    assert (templates / "tpl-artifact.txt").is_file()


# ---------------------------------------------------------------------------
# CLI: run a workflow file from anywhere, artifacts land beside it
# ---------------------------------------------------------------------------

def test_cli_run_uses_the_workflow_folder(tmp_path, monkeypatch):
    graphs = tmp_path / "cli-graphs"
    graphs.mkdir()
    workflow_path = _write_definition(graphs, "cli-anchored", "cli-artifact.txt")

    # A deliberately unrelated CWD: nothing may be written here.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    cli = _load_cli()
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = cli.cmd_run(workflow_path, [], None, True)

    assert exit_code == 0
    assert (graphs / "cli-artifact.txt").is_file()
    assert not (elsewhere / "cli-artifact.txt").exists()


def test_cli_run_reports_engine_artifacts_in_the_run_dir(tmp_path, monkeypatch):
    """Engine-produced files go to ``<output_dir>/runs/<run_id>/``.

    The workflow's own directory (here the template store, since the child is
    loaded from it) must stay free of run artifacts.
    """
    graphs = tmp_path / "cli-foreach"
    graphs.mkdir()
    child = {
        "name": "child",
        "nodes": [
            {"id": "log", "tool": "flow.log", "params": {"message": "x"}, "next": None}
        ],
    }
    (graphs / "child.json").write_text(json.dumps(child), encoding="utf-8")
    parent = {
        "name": "parent",
        "inputs": [
            {"name": "items", "type": {"base": "json"}, "required": True,
             "description": "items"}
        ],
        "nodes": [
            {
                "id": "loop",
                "tool": "flow.foreach",
                "params": {"items": "$inputs.items", "template": "child"},
                "next": None,
            }
        ],
    }
    parent_path = graphs / "parent.json"
    parent_path.write_text(json.dumps(parent), encoding="utf-8")

    # The child template must be importable from the template store.
    monkeypatch.setenv("BT_TEMPLATES_DIR", str(graphs))
    monkeypatch.setattr(template_handler, "_store", None)
    monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path / "output"))

    cli = _load_cli()
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = cli.cmd_run(str(parent_path), ["items=[1, 2]"], None, True)

    assert exit_code == 0
    payload = json.loads(buffer.getvalue())
    results_file = Path(payload["node_results"]["loop"]["outputs"]["results_file"])
    assert results_file.is_file()
    # Named after the run and the node, inside the run's artifact directory.
    assert results_file.name == "foreach_cli_loop.json"
    assert results_file.parent == tmp_path / "output" / "runs" / "cli"
    # The workflow's own directory (the template store) stayed clean.
    assert sorted(p.name for p in graphs.iterdir()) == ["child.json", "parent.json"]


def test_expressions_expose_the_run_dir(tmp_path, monkeypatch):
    """``${rundir}`` is a writable per-run directory; ``$workdir`` is not it."""
    graphs = tmp_path / "expr-graphs"
    graphs.mkdir()
    output = tmp_path / "output"
    monkeypatch.setenv("BT_OUTPUT_DIR", str(output))
    workflow_path = _write_definition(
        graphs, "run-dir", "${rundir}/from-rundir.txt"
    )

    cli = _load_cli()
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = cli.cmd_run(workflow_path, [], None, True)

    assert exit_code == 0
    assert not (graphs / "from-rundir.txt").exists()
    assert (output / "runs" / "cli" / "from-rundir.txt").is_file()


# ---------------------------------------------------------------------------
# text.grep: relative paths follow the work dir, like the file.* tools
# ---------------------------------------------------------------------------

def test_text_grep_resolves_relative_paths_against_work_dir(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.txt").write_text("TODO one\nclean\n", encoding="utf-8")

    result = TextGrep().execute(
        {"path": "sub", "pattern": "TODO"}, ToolContext(work_dir=str(tmp_path))
    )

    assert result["count"] == 1
    assert result["matches"][0]["content"] == "TODO one"


def test_text_grep_rejects_traversal_out_of_the_work_dir(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("TODO\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()

    result = TextGrep().execute(
        {"path": "../outside", "pattern": "TODO"}, ToolContext(work_dir=str(work))
    )

    assert "escapes work dir" in result["error"]


def test_text_grep_keeps_absolute_paths_working(tmp_path):
    target = tmp_path / "abs.txt"
    target.write_text("TODO\n", encoding="utf-8")

    result = TextGrep().execute(
        {"path": str(target), "pattern": "TODO"}, ToolContext(work_dir="/nonexistent")
    )

    assert result["count"] == 1
