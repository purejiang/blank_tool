"""End-to-end runs of the builtin-only workflow FIXTURES.

These fixtures under ``tests/fixtures/workflows/`` double as the user-facing
proof that the orchestration layer behaves: each file is loaded from disk and
executed in-process against a scratch tree, then asserted on run status, node
statuses and the streamed event paths (including nested composition).

They deliberately use only shipped-native BUILTIN tools, so they run in any
configuration — no external binary, no network, and no
``tools.atomic_extensions`` needed.  (The shipped examples live in
``examples/workflows/``; these are test fixtures and are not part of the
application's example content.)
"""

from pathlib import Path

import pytest

from app.template.store import FileTemplateStore
from app.tools.tool_manager import ToolManager
from app.workflow.definition import WorkflowDefinition
from app.workflow.engine import ExecutionContext, WorkflowEngine
from app.workflow.rundir import run_dir_for
from app.workflow.streaming import WorkflowStreamHandler
from app.workflow.validation import validate_workflow

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "workflows"

#: Every fixture in tests/fixtures/workflows (parents + their sub-workflows).
FIXTURE_NAMES = (
    "text-audit",
    "skip-gate",
    "branch-demo",
    "branch-high",
    "branch-low",
    "foreach-audit",
    "foreach-item",
    "release-check",
    "release-check-item",
    "release-evidence",
    "release-report-ok",
    "release-report-bad",
)

#: Templates the parent fixtures resolve through the template store.
CHILD_TEMPLATES = ("branch-high", "branch-low", "foreach-item")

#: Fixed run id for these runs (assertions only check the artifact FILE name,
#: which is run-id + node path; the run directory itself is shared by design).
RUN_ID = "run-e2e"


def _load(name: str) -> WorkflowDefinition:
    return WorkflowDefinition.from_json_file(str(FIXTURES / f"{name}.json"))


def _store(tmp_path) -> FileTemplateStore:
    """A store holding the sub-workflows the parent fixtures call."""
    store = FileTemplateStore(templates_dir=str(tmp_path / "templates"))
    for name in CHILD_TEMPLATES:
        store.save(name, _load(name), {"description": f"fixture: {name}"})
    return store


def _run(definition: WorkflowDefinition, inputs: dict, tmp_path):
    """Execute *definition* in-process, returning (result, events)."""
    events: list = []
    stream = WorkflowStreamHandler(
        workflow_id=definition.name, callback=events.append, run_id=RUN_ID
    )
    context = ExecutionContext(
        work_dir=str(tmp_path),
        run_id=RUN_ID,
        template_store=_store(tmp_path),
        stream_handler=events.append,
        workflow_stream=stream,
    )
    return WorkflowEngine().execute(definition, inputs, context), events


def _audit_file(tmp_path, name: str, hits: int) -> str:
    """Write a text file containing exactly *hits* lines matching ``TODO``."""
    lines = [f"TODO item {index}" for index in range(hits)]
    lines.append("nothing to see here")
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def _node_ids(events, workflow_id=None, event_type="node_started"):
    return [
        event["node_id"]
        for event in events
        if event["type"] == event_type
        and (workflow_id is None or event["workflow_id"] == workflow_id)
    ]


# ---------------------------------------------------------------------------
# The fixtures themselves: load + static validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_loads_without_validation_errors(name):
    definition = _load(name)
    findings = validate_workflow(definition, ToolManager.instance())
    errors = [finding for finding in findings if finding.severity == "error"]
    assert errors == [], [f"{e.node_id}: {e.message}" for e in errors]
    assert definition.nodes, f"{name} has no nodes"


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_uses_only_builtin_tools(name):
    """These fixtures must stay runnable with no external dependency."""
    registry = ToolManager.instance()
    for node in _load(name).nodes:
        tool = registry.get_tool(node.tool)
        assert tool is not None, f"{name}: unknown tool {node.tool!r}"
        assert registry._registry.get_kind(node.tool) == "shipped-native", (
            f"{name}: {node.tool!r} is not a shipped builtin"
        )


# ---------------------------------------------------------------------------
# text-audit: grep -> compare -> assert
# ---------------------------------------------------------------------------

def test_text_audit_passes_when_enough_lines_match(tmp_path):
    result, events = _run(
        _load("text-audit"),
        {"target": _audit_file(tmp_path, "a.txt", 3), "pattern": "TODO", "min_matches": 2},
        tmp_path,
    )
    assert result.success is True, result.error
    assert result.status == "succeeded"
    assert list(result.node_results) == ["announce", "scan", "counted", "enough", "gate"]
    assert all(
        entry["status"] == "ok" for entry in result.node_results.values()
    )
    assert result.outputs == {"passed": True}
    assert _node_ids(events) == ["announce", "scan", "counted", "enough", "gate"]
    assert [e["type"] for e in events][-1] == "workflow_completed"


def test_text_audit_fails_when_too_few_lines_match(tmp_path):
    result, events = _run(
        _load("text-audit"),
        {"target": _audit_file(tmp_path, "b.txt", 1), "pattern": "TODO", "min_matches": 3},
        tmp_path,
    )
    assert result.success is False
    assert result.status == "failed"
    # ${...} interpolation renders the real values into the message.
    assert "expected at least 3 matching line(s) of TODO, found 1" in result.error
    assert result.node_results["gate"]["status"] == "failed"
    assert result.node_results["gate"]["error"] is not None
    # The count is still observable on the successful node before the gate.
    assert result.node_results["counted"]["status"] == "ok"
    assert result.node_results["scan"]["outputs"]["count"] == 1
    assert [e["type"] for e in events][-1] == "workflow_failed"


# ---------------------------------------------------------------------------
# skip-gate: on_failure=skip still yields a terminal node event
# ---------------------------------------------------------------------------

def test_skip_gate_continues_and_reports_the_node_as_skipped(tmp_path):
    target = tmp_path / "c.txt"
    target.write_text("hello world\n", encoding="utf-8")

    result, events = _run(
        _load("skip-gate"), {"target": str(target), "marker": "ABSENT"}, tmp_path
    )

    assert result.success is True, result.error
    gate = result.node_results["gate"]
    assert gate["status"] == "skipped"
    assert gate["error"] == f"marker 'ABSENT' not found in {target}"
    # The node after the skipped gate still ran.
    assert result.node_results["after"]["status"] == "ok"
    assert result.outputs == {"logged": True}

    # Exactly one terminal event per node, and the skipped node has one too.
    completed = [e for e in events if e["type"] == "node_completed"]
    assert [(e["node_id"], e["status"]) for e in completed] == [
        ("read", "ok"),
        ("contains", "ok"),
        ("gate", "skipped"),
        ("after", "ok"),
    ]


def test_skip_gate_passes_when_the_marker_is_present(tmp_path):
    target = tmp_path / "d.txt"
    target.write_text("hello world\n", encoding="utf-8")

    result, _events = _run(
        _load("skip-gate"), {"target": str(target), "marker": "world"}, tmp_path
    )

    assert result.success is True, result.error
    assert result.node_results["gate"]["status"] == "ok"
    assert result.node_results["gate"]["error"] is None


# ---------------------------------------------------------------------------
# branch-demo: flow.compare + flow.branch over two sub-workflow templates
# ---------------------------------------------------------------------------

def test_branch_demo_takes_the_high_branch(tmp_path):
    result, events = _run(
        _load("branch-demo"),
        {"target": _audit_file(tmp_path, "e.txt", 3), "pattern": "TODO", "threshold": 1},
        tmp_path,
    )

    assert result.success is True, result.error
    assert result.node_results["route"]["outputs"]["template"] == "branch-high"
    assert result.node_results["route"]["outputs"]["executed"] is True

    # Nested events carry the parent node's path and the CHILD definition name.
    assert _node_ids(events, workflow_id="branch-high") == ["route/log", "route/confirm"]
    # The top-level run id is never rewritten by nesting.
    assert {event["run_id"] for event in events} == {RUN_ID}


def test_branch_demo_takes_the_low_branch(tmp_path):
    result, events = _run(
        _load("branch-demo"),
        {"target": _audit_file(tmp_path, "f.txt", 1), "pattern": "TODO", "threshold": 5},
        tmp_path,
    )

    assert result.success is True, result.error
    assert result.node_results["route"]["outputs"]["template"] == "branch-low"
    assert _node_ids(events, workflow_id="branch-low") == ["route/log", "route/confirm"]
    assert not _node_ids(events, workflow_id="branch-high")


# ---------------------------------------------------------------------------
# foreach-audit: per-item sub-workflow runs + all_passed gating
# ---------------------------------------------------------------------------

def _targets(tmp_path) -> list:
    return [
        {"target": _audit_file(tmp_path, "one.txt", 2), "min_matches": 2},
        {"target": _audit_file(tmp_path, "two.txt", 3), "min_matches": 1},
    ]


def test_foreach_audit_passes_when_every_target_matches(tmp_path):
    result, events = _run(
        _load("foreach-audit"),
        {"pattern": "TODO", "targets": _targets(tmp_path)},
        tmp_path,
    )

    assert result.success is True, result.error
    loop = result.node_results["loop"]["outputs"]
    assert loop["count"] == 2
    assert loop["passed_count"] == 2
    assert loop["failed_count"] == 0
    assert loop["all_passed"] is True

    # Per-item node paths are indexed under the loop node.
    assert _node_ids(events, workflow_id="foreach-item") == [
        "loop/0/scan",
        "loop/0/enough",
        "loop/0/gate",
        "loop/1/scan",
        "loop/1/enough",
        "loop/1/gate",
    ]

    # The results file is named after the run AND the node (so concurrent runs
    # or a second foreach cannot overwrite each other) and lives in the RUN's
    # artifact directory, not in the workflow's own directory.
    results_file = Path(loop["results_file"])
    assert results_file.name == f"foreach_{RUN_ID}_loop.json"
    assert results_file.is_file()
    assert results_file.parent == Path(run_dir_for(RUN_ID))
    assert not list(tmp_path.glob("foreach_*.json"))
    assert "loop/1/gate" not in results_file.name  # sanity: slug is the node path


def test_foreach_audit_fails_and_names_the_failing_target(tmp_path):
    targets = _targets(tmp_path)
    targets.append({"target": _audit_file(tmp_path, "three.txt", 0), "min_matches": 1})

    result, _events = _run(
        _load("foreach-audit"), {"pattern": "TODO", "targets": targets}, tmp_path
    )

    assert result.success is False
    loop = result.node_results["loop"]["outputs"]
    assert loop["count"] == 3
    assert loop["passed_count"] == 2
    assert loop["failed_count"] == 1
    assert loop["all_passed"] is False

    failing = [item for item in loop["results"] if item["error"]]
    assert len(failing) == 1
    assert "matched 0 line(s), needs >= 1" in failing[0]["error"]

    # The parent gate renders the per-item detail path into its message.
    assert result.node_results["gate"]["status"] == "failed"
    assert loop["results_file"] in result.node_results["gate"]["error"]
