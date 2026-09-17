"""End-to-end runs of the release-check workflow fixture family.

``release-check`` is the "complex" fixture (``tests/fixtures/workflows/``): it
audits a list of files through ``flow.foreach`` (per-file sub-workflow),
delegates the evidence file to a third template through ``workflow.run`` (three
template layers deep), applies a soft gate (``on_failure: skip``) and a hard
gate, then branches to a PASS/FAIL report template.

The test asserts the orchestration behaviour, not just the outcome: node
statuses, the run-root-relative node paths of every nesting level, the
workflow_id of each layer, and the artifacts each layer produced.
"""

import json
import uuid
from collections import Counter
from pathlib import Path

import pytest

from app.template.store import FileTemplateStore
from app.workflow.definition import WorkflowDefinition
from app.workflow.engine import ExecutionContext, WorkflowEngine
from app.workflow.rundir import run_dir_for
from app.workflow.streaming import WorkflowStreamHandler

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "workflows"

FAMILY = (
    "release-check",
    "release-check-item",
    "release-evidence",
    "release-report-ok",
    "release-report-bad",
)

#: Templates the parent resolves through the template store.
STORE_TEMPLATES = (
    "release-check-item",
    "release-evidence",
    "release-report-ok",
    "release-report-bad",
)


def _load(name: str) -> WorkflowDefinition:
    return WorkflowDefinition.from_json_file(str(FIXTURES / f"{name}.json"))


def _store(tmp_path) -> FileTemplateStore:
    store = FileTemplateStore(templates_dir=str(tmp_path / "templates"))
    for name in STORE_TEMPLATES:
        store.save(name, _load(name), {"description": f"example: {name}"})
    return store


def _run(inputs: dict, tmp_path, run_id: str = None):
    """Run release-check with the family registered, returning (result, events).

    Each call gets its OWN run id unless one is passed: the artifact directory
    is keyed by run id under the shared output dir, so a fixed id would mix
    this run's files with an earlier run's.
    """
    run_id = run_id or _new_run_id()
    definition = _load("release-check")
    events: list = []
    stream = WorkflowStreamHandler(
        workflow_id=definition.name, callback=events.append, run_id=run_id
    )
    context = ExecutionContext(
        work_dir=str(tmp_path),
        run_id=run_id,
        template_store=_store(tmp_path),
        stream_handler=events.append,
        workflow_stream=stream,
    )
    return WorkflowEngine().execute(definition, inputs, context), events


def _new_run_id() -> str:
    return f"release-{uuid.uuid4().hex[:8]}"


def _write_file(tmp_path, name: str, body: str) -> str:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return str(path)


def _clean_file(tmp_path, name: str) -> str:
    return _write_file(tmp_path, name, "def add(a, b):\n    return a + b\n")


def _dirty_file(tmp_path, name: str) -> str:
    return _write_file(
        tmp_path,
        name,
        "def add(a, b):\n    # TODO: validate inputs\n    print('debug', a)\n    return a + b\n",
    )


def _targets(*paths: str) -> list:
    return [{"path": path} for path in paths]


def _report(tmp_path) -> Path:
    return tmp_path / "release-report.txt"


def _base_inputs(targets, report_path, max_failures=0) -> dict:
    return {
        "targets": targets,
        "max_failures": max_failures,
        "report_path": str(report_path),
    }


def _node_ids(events, workflow_id=None, event_type="node_started"):
    return [
        event["node_id"]
        for event in events
        if event["type"] == event_type
        and (workflow_id is None or event["workflow_id"] == workflow_id)
    ]


# ---------------------------------------------------------------------------
# Static gate for the family
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", FAMILY)
def test_family_examples_load(name):
    definition = _load(name)
    assert definition.nodes
    assert definition.name == name


# ---------------------------------------------------------------------------
# Happy path: every file clean -> PASS report + one evidence file per item
# ---------------------------------------------------------------------------

def test_all_clean_writes_pass_report_and_evidence(tmp_path):
    first = _clean_file(tmp_path, "clean-one.py")
    second = _clean_file(tmp_path, "clean-two.py")
    report = _report(tmp_path)
    run_id = _new_run_id()

    result, events = _run(
        _base_inputs(_targets(first, second), report), tmp_path, run_id=run_id
    )

    assert result.success is True, result.error
    assert result.status == "succeeded"
    assert result.outputs == {"passed": True}

    loop = result.node_results["scan_all"]["outputs"]
    assert loop["count"] == 2
    assert loop["passed_count"] == 2
    assert loop["failed_count"] == 0
    assert loop["all_passed"] is True

    # The branch took the PASS template.
    assert result.node_results["route"]["outputs"]["template"] == "release-report-ok"
    assert report.read_text(encoding="utf-8").startswith("RELEASE CHECK: PASS")
    assert "failed: 0" in report.read_text(encoding="utf-8")

    # The soft gate is satisfied (0 <= 0), so it is NOT skipped.
    assert result.node_results["soft_gate"]["status"] == "ok"
    assert result.node_results["soft_gate"]["error"] is None

    # One evidence file per audited file, written by the third template layer
    # into the RUN's artifact directory (not into the workflow's directory).
    run_dir = Path(run_dir_for(run_id))
    assert sorted(p.name for p in run_dir.glob("evidence-*.txt")) == [
        "evidence-clean-one.py.txt",
        "evidence-clean-two.py.txt",
    ]
    body = (run_dir / "evidence-clean-one.py.txt").read_text(encoding="utf-8")
    assert "todo/fixme markers: 0" in body
    assert "debug statements: 0" in body
    # Nothing run-produced landed in the working directory.
    assert not list(tmp_path.glob("evidence-*.txt"))
    assert not list(tmp_path.glob("foreach_*.json"))


def test_nested_node_paths_span_three_template_layers(tmp_path):
    first = _clean_file(tmp_path, "layered.py")
    report = _report(tmp_path)
    run_id = _new_run_id()

    _result, events = _run(
        _base_inputs(_targets(first), report), tmp_path, run_id=run_id
    )

    # Layer 1 (loop body): scan_all/0/<node>
    assert _node_ids(events, workflow_id="release-check-item")[:2] == [
        "scan_all/0/read",
        "scan_all/0/todos",
    ]
    # Layer 2 (workflow.run inside the loop body): scan_all/0/evidence/<node>
    assert _node_ids(events, workflow_id="release-evidence") == [
        "scan_all/0/evidence/write",
        "scan_all/0/evidence/confirm",
    ]
    # Layer 3 (branch target): route/<node>
    assert _node_ids(events, workflow_id="release-report-ok") == [
        "route/write",
        "route/confirm",
    ]
    # run_id is the top-level run everywhere; no layer rewrites it.
    assert {event["run_id"] for event in events} == {run_id}

    # Exactly one terminal event per node at every layer.
    started = Counter(
        e["node_id"] for e in events if e["type"] == "node_started"
    )
    completed = Counter(
        e["node_id"] for e in events if e["type"] == "node_completed"
    )
    assert started == completed
    assert all(count == 1 for count in completed.values()), completed


# ---------------------------------------------------------------------------
# Failure path: hard gate + FAIL report
# ---------------------------------------------------------------------------

def test_dirty_file_fails_the_gate_and_writes_fail_report(tmp_path):
    clean = _clean_file(tmp_path, "ok.py")
    dirty = _dirty_file(tmp_path, "bad.py")
    report = _report(tmp_path)

    result, _events = _run(_base_inputs(_targets(clean, dirty), report), tmp_path)

    assert result.success is False
    assert result.status == "failed"

    loop = result.node_results["scan_all"]["outputs"]
    assert loop["count"] == 2
    assert loop["passed_count"] == 1
    assert loop["failed_count"] == 1
    assert loop["all_passed"] is False

    # flow.foreach keeps going after a failing item, so both files were audited.
    failing = [item for item in loop["results"] if item["error"]]
    assert len(failing) == 1
    assert "TODO/FIXME marker(s)" in failing[0]["error"]
    assert "bad.py" in failing[0]["error"]

    # The hard gate fails and the branch wrote the FAIL report.
    assert result.node_results["hard_decide"]["outputs"]["result"] is False
    assert result.node_results["route"]["outputs"]["template"] == "release-report-bad"
    assert report.read_text(encoding="utf-8").startswith("RELEASE CHECK: FAIL")
    assert result.node_results["confirm"]["status"] == "failed"
    assert "1 file(s) did not pass" in result.node_results["confirm"]["error"]
    assert loop["results_file"] in result.node_results["confirm"]["error"]


def test_debug_leftovers_also_fail_an_item(tmp_path):
    path = _write_file(tmp_path, "debuggy.py", "print('boom')\n")
    report = _report(tmp_path)

    result, _events = _run(_base_inputs(_targets(path), report), tmp_path)

    assert result.success is False
    failing = [
        item
        for item in result.node_results["scan_all"]["outputs"]["results"]
        if item["error"]
    ]
    assert len(failing) == 1
    assert "leftover debug statement(s)" in failing[0]["error"]


# ---------------------------------------------------------------------------
# Soft gate: tolerated failures are reported as skipped, the hard gate still fails
# ---------------------------------------------------------------------------

def test_soft_gate_is_skipped_when_failures_exceed_the_tolerance(tmp_path):
    clean = _clean_file(tmp_path, "ok2.py")
    dirty = _dirty_file(tmp_path, "bad2.py")
    report = _report(tmp_path)

    result, events = _run(
        _base_inputs(_targets(clean, dirty), report, max_failures=1), tmp_path
    )

    # 1 failure <= 1 tolerated => the soft gate passes and is not reported as failed.
    assert result.node_results["soft_gate"]["status"] == "ok"

    # Zero tolerated failures => the soft gate is skipped, but the run still
    # fails on the HARD gate (which requires zero failures).
    result2, events2 = _run(
        _base_inputs(_targets(clean, dirty), _report(tmp_path), max_failures=0),
        tmp_path,
    )
    assert result2.node_results["soft_gate"]["status"] == "skipped"
    assert "more than the 0 tolerated" in result2.node_results["soft_gate"]["error"]
    assert result2.success is False
    assert result2.node_results["confirm"]["status"] == "failed"

    # A skipped node still gets exactly one terminal event.
    terminal = [
        e
        for e in events2
        if e["type"] == "node_completed" and e["node_id"] == "soft_gate"
    ]
    assert len(terminal) == 1
    assert terminal[0]["status"] == "skipped"


def test_soft_gate_tolerates_failures_up_to_the_limit(tmp_path):
    dirty = _dirty_file(tmp_path, "only-bad.py")
    report = _report(tmp_path)

    result, _events = _run(
        _base_inputs(_targets(dirty), report, max_failures=1), tmp_path
    )

    assert result.node_results["soft_gate"]["status"] == "ok"
    # The hard gate is unaffected by the tolerance.
    assert result.success is False
    assert result.node_results["confirm"]["status"] == "failed"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_target_list_passes_and_writes_a_pass_report(tmp_path):
    report = _report(tmp_path)
    run_id = _new_run_id()

    result, _events = _run(_base_inputs([], report), tmp_path, run_id=run_id)

    assert result.success is True, result.error
    assert result.node_results["scan_all"]["outputs"]["count"] == 0
    assert result.node_results["scan_all"]["outputs"]["all_passed"] is True
    assert report.read_text(encoding="utf-8").startswith("RELEASE CHECK: PASS")
    # An empty target list produces no evidence file at all.
    assert not list(Path(run_dir_for(run_id)).glob("evidence-*.txt"))
    assert not list(tmp_path.glob("evidence-*.txt"))


def test_missing_file_fails_its_item_without_stopping_the_loop(tmp_path):
    clean = _clean_file(tmp_path, "present.py")
    missing = str(tmp_path / "nope.py")
    report = _report(tmp_path)

    result, _events = _run(_base_inputs(_targets(clean, missing), report), tmp_path)

    assert result.success is False
    loop = result.node_results["scan_all"]["outputs"]
    assert loop["count"] == 2
    assert loop["failed_count"] == 1
    failing = [item for item in loop["results"] if item["error"]]
    assert "file not found" in failing[0]["error"]


def test_per_item_results_file_is_named_after_run_and_node(tmp_path):
    clean = _clean_file(tmp_path, "named.py")
    report = _report(tmp_path)
    run_id = _new_run_id()

    result, _events = _run(
        _base_inputs(_targets(clean), report), tmp_path, run_id=run_id
    )

    results_file = Path(result.node_results["scan_all"]["outputs"]["results_file"])
    assert results_file.name == f"foreach_{run_id}_scan_all.json"
    assert results_file.parent == Path(run_dir_for(run_id))
    payload = json.loads(results_file.read_text(encoding="utf-8"))
    assert payload["count"] == 1
    assert payload["all_passed"] is True


def test_run_dir_is_shared_by_every_nesting_layer(tmp_path):
    """The evidence file of the third layer lands in the top-level run dir."""
    clean = _clean_file(tmp_path, "shared.py")
    report = _report(tmp_path)
    run_id = _new_run_id()

    result, _events = _run(
        _base_inputs(_targets(clean), report), tmp_path, run_id=run_id
    )

    assert result.success is True, result.error
    run_dir = Path(run_dir_for(run_id))
    assert (run_dir / "evidence-shared.py.txt").is_file()
    assert (run_dir / f"foreach_{run_id}_scan_all.json").is_file()
    # i.e. both the engine artifact and the workflow-authored output agree.
    assert {p.name for p in run_dir.glob("*")} == {
        "evidence-shared.py.txt",
        f"foreach_{run_id}_scan_all.json",
    }
