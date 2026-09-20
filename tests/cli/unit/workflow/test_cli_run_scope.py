"""Headless-CLI run scope: registration, cancellation, timeout, history.

``cmd_run`` / ``main`` are driven in-process (no subprocess, no pipes), so
these cover the CLI's cancellation wiring, the ``--timeout`` watchdog and the
"every terminal path is recorded" contract even where spawning a captured
child is unavailable.
"""

import json
import threading
import time
from pathlib import Path

import pytest

from app.workflow.engine import WorkflowResult
from cli import (
    _ACTIVE_RUN,
    _fire_timeout,
    _on_interrupt,
    _run_scope,
    _set_active_run,
    cmd_run,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_workflow(path: Path, name: str = "cli-scope") -> Path:
    path.write_text(
        json.dumps(
            {
                "name": name,
                "nodes": [
                    {"id": "log", "tool": "flow.log", "params": {"message": "hi"}}
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    """Point BT_OUTPUT_DIR at a temp dir (history + $rundir land there)."""
    out = tmp_path / "output"
    monkeypatch.setenv("BT_OUTPUT_DIR", str(out))
    return out


@pytest.fixture(autouse=True)
def _retire_active_run():
    """Never leak the module-level active-run slot between tests."""
    yield
    _ACTIVE_RUN.clear()


def _history_records(output_dir: Path) -> list:
    history = output_dir / "history"
    if not history.is_dir():
        return []
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in history.glob("*.json")
    ]


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------

def test_pre_armed_cancel_returns_2_and_records_the_run(
    tmp_path, output_dir, capsys
):
    """A cancel event set before the run aborts at the first checkpoint."""
    wf = _write_workflow(tmp_path / "wf.json")
    event = threading.Event()
    event.set()

    code = cmd_run(str(wf), [], None, True, run_id="a" * 32, interrupt_event=event)

    assert code == 2, "a cancelled run is neither success (0) nor failure (1)"
    payload = json.loads(capsys.readouterr().out)
    assert payload["cancelled"] is True
    assert payload["status"] == "cancelled"
    assert payload["run_id"] == "a" * 32

    records = _history_records(output_dir)
    assert len(records) == 1, "an interrupted/cancelled run must still be recorded"
    assert records[0]["status"] == "cancelled"
    assert records[0]["cancelled"] is True
    assert records[0]["run_id"] == "a" * 32


def test_run_scope_registers_and_unregisters_the_run():
    from app.common.task_manager import TaskManager

    with _run_scope("scope-run", None) as (_event, _token):
        assert any(
            t["run_id"] == "scope-run" for t in TaskManager().list_tasks()
        ), "the run must be cancellable while it executes"

    assert not any(
        t["run_id"] == "scope-run" for t in TaskManager().list_tasks()
    )


# ---------------------------------------------------------------------------
# Interruption
# ---------------------------------------------------------------------------

def test_first_interrupt_requests_cancellation(monkeypatch):
    exits: list = []
    monkeypatch.setattr("cli.os._exit", lambda code: exits.append(code))
    monkeypatch.setattr("cli._write_stderr", lambda _text: None)

    token = object()
    event = threading.Event()
    _set_active_run(token, event, "run-i", None)

    _on_interrupt(2, None)

    assert event.is_set(), "the signal handler only sets the per-run event"
    assert exits == [], "the first interrupt must not force an exit"


def test_second_interrupt_forces_exit_130(monkeypatch):
    exits: list = []
    monkeypatch.setattr("cli.os._exit", lambda code: exits.append(code))
    monkeypatch.setattr("cli._write_stderr", lambda _text: None)

    token = object()
    event = threading.Event()
    _set_active_run(token, event, "run-i2", None)

    _on_interrupt(2, None)
    _on_interrupt(2, None)

    assert exits == [130]


def test_interrupt_outside_a_run_exits_immediately(monkeypatch):
    exits: list = []
    monkeypatch.setattr("cli.os._exit", lambda code: exits.append(code))
    monkeypatch.setattr("cli._write_stderr", lambda _text: None)
    _ACTIVE_RUN.clear()

    _on_interrupt(2, None)

    assert exits == [130]


def test_main_maps_keyboard_interrupt_to_cancelled(monkeypatch):
    # The handler is normally installed by main(); installing the real one in
    # the test process would hijack pytest's Ctrl+C handling.
    monkeypatch.setattr("cli._install_signal_handlers", lambda: None)
    monkeypatch.setattr("cli._sweep_live_children", lambda: None)

    def _boom():
        raise KeyboardInterrupt

    monkeypatch.setattr("cli.cmd_list_tools", _boom)

    assert main(["list-tools"]) == 2


# ---------------------------------------------------------------------------
# --timeout
# ---------------------------------------------------------------------------

def test_timeout_returns_124_and_records_the_timeout(
    tmp_path, output_dir, capsys, monkeypatch
):
    from app.workflow import engine as engine_module

    wf = _write_workflow(tmp_path / "wf.json")

    def _waiting_execute(self, definition, inputs, context):
        """A node that honours cancellation, like the real tools do."""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if context.cancelled():
                return WorkflowResult(
                    success=False, outputs={}, node_results={},
                    error="workflow cancelled", cancelled=True,
                )
            time.sleep(0.02)
        return WorkflowResult(success=True, outputs={}, node_results={})

    monkeypatch.setattr(engine_module.WorkflowEngine, "execute", _waiting_execute)

    start = time.monotonic()
    code = cmd_run(str(wf), [], None, True, timeout=1)
    elapsed = time.monotonic() - start

    assert code == 124, "a timeout is distinct from a user cancel (2)"
    payload = json.loads(capsys.readouterr().out)
    assert payload["timeout"] is True
    assert payload["cancelled"] is True
    assert "timed out" in payload["error"]
    assert elapsed < 4, "the watchdog must not add its full delay to the run"

    records = _history_records(output_dir)
    assert len(records) == 1
    assert records[0]["status"] == "cancelled"
    assert "timed out" in records[0]["error"]


def test_a_run_that_finishes_inside_the_budget_is_not_a_timeout(
    tmp_path, output_dir, capsys
):
    wf = _write_workflow(tmp_path / "wf.json")

    code = cmd_run(str(wf), [], None, True, timeout=30)

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["timeout"] is False
    assert payload["success"] is True
    assert _ACTIVE_RUN == {}, "the active-run slot must be retired"


def test_late_watchdog_fire_is_inert_for_a_stale_token():
    """A timer that fires after its run finished must not cancel anything."""
    event = threading.Event()
    _ACTIVE_RUN.clear()

    _fire_timeout(object(), event, 1)

    assert event.is_set() is False
    assert _ACTIVE_RUN == {}


# ---------------------------------------------------------------------------
# History identity + internal errors
# ---------------------------------------------------------------------------

def test_run_id_is_the_history_record_id(tmp_path, output_dir, capsys):
    from app.history import store as history_store

    wf = _write_workflow(tmp_path / "wf.json")
    run_id = "b" * 32

    assert cmd_run(str(wf), [], None, True, run_id=run_id) == 0
    capsys.readouterr()

    record = history_store.get_run(run_id)
    assert record is not None, "the run id must resolve through `history <id>`"
    assert record["run_id"] == run_id


def test_non_history_run_id_still_runs_and_records(
    tmp_path, output_dir, capsys
):
    """A programmatic non-hex run id names $rundir but not the history file."""
    wf = _write_workflow(tmp_path / "wf.json")

    assert cmd_run(str(wf), [], None, True, run_id="cli") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == "cli"

    records = _history_records(output_dir)
    assert len(records) == 1
    assert records[0]["run_id"] != "cli", "history ids stay uuid4 hex"


def test_internal_error_still_emits_json_and_records_history(
    tmp_path, output_dir, capsys, monkeypatch
):
    from app.workflow import engine as engine_module

    wf = _write_workflow(tmp_path / "wf.json")

    def _boom(self, definition, inputs, context):
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(engine_module.WorkflowEngine, "execute", _boom)

    code = cmd_run(str(wf), [], None, True)

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert "engine exploded" in payload["error"]
    assert len(_history_records(output_dir)) == 1


# ---------------------------------------------------------------------------
# main() argument handling
# ---------------------------------------------------------------------------

def test_main_rejects_a_non_hex_run_id(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("cli._install_signal_handlers", lambda: None)
    monkeypatch.setattr("cli._sweep_live_children", lambda: None)
    wf = _write_workflow(tmp_path / "wf.json")

    assert main(["run", str(wf), "--run-id", "nope"]) == 1
    assert "32 lowercase hex" in capsys.readouterr().err


def test_main_help_documents_the_new_flags(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["run", "--help"])

    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "--run-id" in out
    assert "--timeout" in out
    assert "124" in out, "the exit codes must be documented"
