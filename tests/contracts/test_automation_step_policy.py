#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract tests for the step / run failure policy and shell output (P2-6).

The backend has always accepted ``continue_on_error`` and per-step
``on_error``, but the renderer hard-coded ``continue_on_error: false`` and no
UI ever set ``on_error`` — the capability was unreachable. These tests pin:

* the precedence rule (per-step ``on_error`` wins over the run-level flag),
* the default (no policy = abort at the first failure, unchanged behaviour),
* that a ``shell`` step publishes its stdout to the run log (and is capped),
* that the renderer/step schema actually declares the fields, so the wiring
  cannot silently regress to "no UI sets this".
"""

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from app.automation import orchestrator, steps  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class FakeContext:
    def __init__(self):
        self.run_dir = ""
        self.logs = []
        self.steps = []
        self.completed = None
        self.cancelled = False

    def log(self, message):
        self.logs.append(message)

    def step_start(self, index, action):
        pass

    def step(self, record):
        self.steps.append(record)

    def complete(self, payload):
        self.completed = payload

    def is_cancelled(self):
        return self.cancelled


TAP = {"action": "tap", "mode": "coord", "coord": {"x": 1, "y": 2}}
# The failing step is a `shell` (the probe covered below) and the following
# step is a tap that always succeeds — so "kept going" is observable as
# passed == 1 rather than as two failures.
FAIL = {"action": "shell", "command": "getprop x"}


def _install(monkeypatch, tmp_path, failing_actions):
    monkeypatch.setenv("BT_AUTO_TASKS_DIR", str(tmp_path / "auto_tasks"))
    executed = []

    def fake_pid(device_id, package):
        return 100

    def fake_execute(ctx, device_id, package_name, action, step, dt):
        executed.append(step)
        if action in failing_actions:
            return False, "boom", None
        return True, "", None

    monkeypatch.setattr(orchestrator, "get_app_pid", fake_pid)
    monkeypatch.setattr(orchestrator, "execute_step", fake_execute)
    monkeypatch.setattr(orchestrator, "restore_ime", lambda device_id: None)
    monkeypatch.setattr(orchestrator, "get_display_transform",
                        lambda device_id: {"rotation": 0, "width": 1080, "height": 1920})
    monkeypatch.setattr(orchestrator, "take_screenshot",
                        lambda device_id, name="", out_dir="": {"success": False})
    return executed


class TestFailurePolicy:
    """Default behaviour must stay "abort on first failure"."""

    def _run(self, monkeypatch, tmp_path, first_step, **kwargs):
        """Run [first_step, TAP] with `shell` wired to fail."""
        executed = _install(monkeypatch, tmp_path, {"shell"})
        ctx = FakeContext()
        result = orchestrator.run(
            ctx, device_id="emulator-5554", package_name="com.demo",
            steps=[first_step, dict(TAP)], task_id="t-policy", **kwargs,
        )
        return result, executed

    def test_default_aborts_after_the_first_failure(self, monkeypatch, tmp_path):
        result, executed = self._run(monkeypatch, tmp_path, dict(FAIL))
        assert result["success"] is False
        assert result["failed"] == 1
        assert len(executed) == 1             # step 2 never ran
        assert result["total"] == 2

    def test_run_level_continue_on_error_keeps_going(self, monkeypatch, tmp_path):
        result, executed = self._run(monkeypatch, tmp_path, dict(FAIL), continue_on_error=True)
        assert len(executed) == 2
        assert result["failed"] == 1 and result["passed"] == 1
        # A run with a failed step is NOT a success, even when it finished.
        assert result["success"] is False

    def test_step_on_error_continue_wins_over_the_run_default(self, monkeypatch, tmp_path):
        result, executed = self._run(
            monkeypatch, tmp_path, dict(FAIL, on_error="continue"),
        )
        assert len(executed) == 2
        assert result["passed"] == 1 and result["failed"] == 1

    def test_step_on_error_abort_wins_over_run_level_continue(self, monkeypatch, tmp_path):
        result, executed = self._run(
            monkeypatch, tmp_path, dict(FAIL, on_error="abort"), continue_on_error=True,
        )
        assert result["success"] is False
        assert result["failed"] == 1
        assert len(executed) == 1             # aborted despite the run-level flag

    def test_unknown_on_error_value_falls_back_to_the_run_setting(self, monkeypatch, tmp_path):
        result, executed = self._run(
            monkeypatch, tmp_path, dict(FAIL, on_error="wat"),
        )
        assert len(executed) == 1             # treated as abort, not as continue

    def test_a_failing_step_marked_continue_does_not_stop_the_run(self, monkeypatch, tmp_path):
        result, _ = self._run(monkeypatch, tmp_path, dict(FAIL, on_error="continue"))
        assert result["cancelled"] is False
        assert result.get("aborted_by_crash") is not True


class TestShellOutput:
    def _run_shell(self, monkeypatch, stdout, ctx=None):
        monkeypatch.setattr(
            steps, "shell",
            lambda device_id, command: {"success": True, "stdout": stdout, "stderr": ""},
        )
        return steps.execute_step(
            ctx, "emulator-5554", None, "shell", {"action": "shell", "command": "getprop x"}, None,
        )

    def test_stdout_reaches_the_run_log(self, monkeypatch):
        ctx = FakeContext()
        ok, message, shot = self._run_shell(monkeypatch, "34\n", ctx)
        assert ok is True and shot is None
        assert message == "34"                      # first line on the step row
        assert len(ctx.logs) == 1
        assert "$ getprop x" in ctx.logs[0]
        assert "34" in ctx.logs[0]

    def test_multiline_output_is_kept_whole(self, monkeypatch):
        ctx = FakeContext()
        self._run_shell(monkeypatch, "a\nb\nc\n", ctx)
        assert "a\nb\nc" in ctx.logs[0]

    def test_huge_output_is_truncated(self, monkeypatch):
        ctx = FakeContext()
        self._run_shell(monkeypatch, "x" * 20000, ctx)
        assert len(ctx.logs[0]) < 20000
        assert "截断" in ctx.logs[0]

    def test_empty_output_logs_nothing_and_keeps_the_row_clean(self, monkeypatch):
        ctx = FakeContext()
        ok, message, _ = self._run_shell(monkeypatch, "  \n", ctx)
        assert ok is True and message == ""
        assert ctx.logs == []

    def test_works_without_a_context(self, monkeypatch):
        """Handlers are also driven by unit tests with ctx=None."""
        ok, message, _ = self._run_shell(monkeypatch, "ok\n", None)
        assert ok is True and message == "ok"

    def test_failure_message_wins_over_stdout(self, monkeypatch):
        monkeypatch.setattr(
            steps, "shell",
            lambda device_id, command: {"success": False, "stdout": "partial", "error": "denied"},
        )
        ctx = FakeContext()
        ok, message, _ = steps.execute_step(
            ctx, "emulator-5554", None, "shell",
            {"action": "shell", "command": "su"}, None,
        )
        assert ok is False
        assert message == "denied"
        assert "partial" in ctx.logs[0]   # the output is still worth reading


class TestSchemaDeclaresThePolicy:
    """The UI half of the contract (renderer files, source-level checks)."""

    def _read(self, rel):
        with open(os.path.join(REPO_ROOT, rel), "r", encoding="utf-8") as f:
            return f.read()

    def test_step_type_declares_on_error(self):
        src = self._read("src/renderer/components/automation/stepTypes.ts")
        assert re.search(r"on_error\?:\s*'continue'\s*\|\s*'abort'", src), \
            "Step.on_error missing from stepTypes.ts"

    def test_step_editor_offers_all_three_choices(self):
        src = self._read("src/renderer/components/automation/StepEditForm.vue")
        for value in ("inherit", "continue", "abort"):
            assert f"'{value}'" in src, f"StepEditForm is missing the {value!r} option"
        assert "next.on_error = onError.value" in src, \
            "save() must write the explicit choice back into the step"

    def test_run_controls_expose_both_run_level_switches(self):
        src = self._read("src/renderer/components/automation/RunControls.vue")
        assert "update:continueOnError" in src
        assert "update:abortOnCrash" in src

    def test_runner_no_longer_hardcodes_continue_on_error(self):
        src = self._read("src/renderer/composables/automation/useScriptRunner.ts")
        assert "continue_on_error: false" not in src
        assert "continue_on_error: payload.continue_on_error === true" in src
        assert "abort_on_crash: payload.abort_on_crash !== false" in src

    def test_page_forwards_the_policy_to_the_runner(self):
        src = self._read("src/renderer/views/OtherToolsPage.vue")
        assert "continue_on_error: continueOnError.value" in src
        assert "abort_on_crash: abortOnCrash.value" in src

    def test_backend_signature_keeps_the_defaults(self):
        import inspect
        sig = inspect.signature(orchestrator.run)
        assert sig.parameters["continue_on_error"].default is False
        assert sig.parameters["abort_on_crash"].default is True

    def test_report_records_the_policy_in_force(self, monkeypatch, tmp_path):
        """The saved report must show which policy was in force."""
        monkeypatch.setenv("BT_AUTO_TASKS_DIR", str(tmp_path / "auto_tasks"))
        _install(monkeypatch, tmp_path, set())
        ctx = FakeContext()
        result = orchestrator.run(
            ctx, device_id="emulator-5554", package_name="com.demo",
            steps=[dict(TAP)], task_id="t-report",
            continue_on_error=True, abort_on_crash=False,
        )
        assert result["success"] is True
        with open(tmp_path / "auto_tasks" / "t-report" / "report.json",
                  encoding="utf-8") as f:
            report = json.load(f)
        assert report["kind"] == "automation_run"
        assert report["continue_on_error"] is True
        assert report["abort_on_crash"] is False
        # the history index stays small — the policy is report-only
        with open(tmp_path / "auto_tasks" / "t-report" / "summary.json",
                  encoding="utf-8") as f:
            summary = json.load(f)
        assert "continue_on_error" not in summary
