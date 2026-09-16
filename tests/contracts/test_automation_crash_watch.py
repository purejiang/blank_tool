"""Contract tests for the automation crash watch (``orchestrator.run``).

Two behaviours are locked here:

1. A scripted app restart (``clear_app_data`` / ``launch_app`` — the normal
   way a script relaunches its target) must NOT be reported as a crash. The
   watch re-anchors on the pid after those actions; without that, the very
   next step boundary saw "pid gone" and aborted the whole run.
2. A genuinely unexpected process disappearance still aborts the run, and the
   run is still reported through ``complete`` + ``report.json``.

Also locked: ``restore_ime`` runs exactly once on every exit path (it lives in
the orchestrator's ``finally`` so an exception cannot leave the device on the
ADBKeyboard IME).
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from app.automation import orchestrator  # noqa: E402


class FakeContext:
    """Minimal stand-in for ``StreamContext`` (no IPC, no threads)."""

    def __init__(self):
        self.run_dir = ""
        self.logs = []
        self.step_starts = []
        self.steps = []
        self.completed = None
        self.cancelled = False

    def log(self, message):
        self.logs.append(message)

    def step_start(self, index, action):
        self.step_starts.append((index, action))

    def step(self, record):
        self.steps.append(record)

    def complete(self, payload):
        self.completed = payload

    def is_cancelled(self):
        return self.cancelled


def _install(monkeypatch, tmp_path, pid_sequence, executed, restore_calls,
             failing_actions=()):
    """Patch every device/adb touchpoint the orchestrator reaches."""
    monkeypatch.setenv("BT_AUTO_TASKS_DIR", str(tmp_path / "auto_tasks"))
    pids = list(pid_sequence)

    def fake_pid(device_id, package):
        return pids.pop(0) if pids else None

    def fake_execute(ctx, device_id, package_name, action, step, dt):
        executed.append(action)
        if action in failing_actions:
            return False, "boom", None
        return True, "", None

    monkeypatch.setattr(orchestrator, "get_app_pid", fake_pid)
    monkeypatch.setattr(orchestrator, "execute_step", fake_execute)
    monkeypatch.setattr(
        orchestrator, "get_display_transform",
        lambda device_id: {"rotation": 0, "width": 1080, "height": 1920},
    )
    monkeypatch.setattr(orchestrator, "restore_ime", lambda device_id: restore_calls.append(device_id))
    monkeypatch.setattr(
        orchestrator, "take_screenshot",
        lambda device_id, name="", out_dir="": {"success": False, "file_path": "", "error": "no shot"},
    )
    monkeypatch.setattr(
        orchestrator, "dump_crash_log",
        lambda device_id, path: {"success": False, "error": "logcat unavailable"},
    )


def _report(tmp_path, task_id):
    path = tmp_path / "auto_tasks" / task_id / "report.json"
    return json.loads(path.read_text(encoding="utf-8"))


TAP = {"action": "tap", "mode": "coord", "coord": {"x": 10, "y": 20}}


class TestScriptedRestartIsNotACrash:
    def test_clear_app_data_then_launch_app_runs_to_completion(self, monkeypatch, tmp_path):
        """REGRESSION: `clear_app_data` kills the pid, so the next step used to
        abort with 'app com.demo crashed: exited'."""
        ctx = FakeContext()
        executed, restore_calls = [], []
        # before-loop probe, step1 check, re-anchor(after clear) -> None,
        # step2 check (None), re-anchor(after launch) -> 200, step3 check.
        _install(monkeypatch, tmp_path, [100, 100, None, None, 200, 200],
                 executed, restore_calls)

        result = orchestrator.run(
            ctx,
            device_id="emulator-5554",
            package_name="com.demo",
            steps=[
                {"action": "clear_app_data", "package": "com.demo"},
                {"action": "launch_app", "package": "com.demo"},
                TAP,
            ],
            task_id="t-restart",
        )

        # The key is only set on the crash path; absence == not aborted.
        assert result.get("aborted_by_crash") is not True
        assert result["failed"] == 0
        assert result["passed"] == 3
        assert result["success"] is True
        assert ctx.completed is result
        # The persisted report the history UI reads must agree.
        assert _report(tmp_path, "t-restart")["aborted_by_crash"] is False
        assert executed == ["clear_app_data", "launch_app", "tap"]

    def test_launch_app_adopts_the_new_pid(self, monkeypatch, tmp_path):
        """App not running before the run -> launch_app anchors the watch."""
        ctx = FakeContext()
        executed, restore_calls = [], []
        _install(monkeypatch, tmp_path, [None, None, 200, 200], executed, restore_calls)

        result = orchestrator.run(
            ctx,
            device_id="emulator-5554",
            package_name="com.demo",
            steps=[{"action": "launch_app", "package": "com.demo"}, TAP],
            task_id="t-launch",
        )

        assert result.get("aborted_by_crash") is not True
        assert result["passed"] == 2


class TestUnexpectedExitStillAborts:
    def test_pid_disappearing_aborts_the_run(self, monkeypatch, tmp_path):
        ctx = FakeContext()
        executed, restore_calls = [], []
        _install(monkeypatch, tmp_path, [100, 100, None], executed, restore_calls)

        result = orchestrator.run(
            ctx,
            device_id="emulator-5554",
            package_name="com.demo",
            steps=[TAP, TAP],
            task_id="t-crash",
        )

        assert result["aborted_by_crash"] is True
        assert result["success"] is False
        assert result["failed"] == 1
        assert result["steps"][-1]["action"] == "app_crash"
        assert "crashed" in result["steps"][-1]["message"]
        assert executed == ["tap"]  # step 2 never ran
        assert _report(tmp_path, "t-crash")["aborted_by_crash"] is True

    def test_pid_change_outside_restart_actions_aborts(self, monkeypatch, tmp_path):
        """A restart we did NOT script is still reported (message says so)."""
        ctx = FakeContext()
        executed, restore_calls = [], []
        _install(monkeypatch, tmp_path, [100, 100, 200], executed, restore_calls)

        result = orchestrator.run(
            ctx,
            device_id="emulator-5554",
            package_name="com.demo",
            steps=[TAP, TAP],
            task_id="t-restart-external",
        )

        assert result["aborted_by_crash"] is True
        assert "restarted" in result["steps"][-1]["message"]

    def test_watch_disabled_ignores_pid_changes(self, monkeypatch, tmp_path):
        ctx = FakeContext()
        executed, restore_calls = [], []
        _install(monkeypatch, tmp_path, [], executed, restore_calls)

        result = orchestrator.run(
            ctx,
            device_id="emulator-5554",
            package_name="com.demo",
            steps=[TAP, TAP],
            abort_on_crash=False,
            task_id="t-nocrashwatch",
        )

        assert result.get("aborted_by_crash") is not True
        assert result["passed"] == 2


class TestRestoreImeOnEveryExitPath:
    def test_success_path_restores_once(self, monkeypatch, tmp_path):
        ctx = FakeContext()
        executed, restore_calls = [], []
        _install(monkeypatch, tmp_path, [100, 100], executed, restore_calls)

        result = orchestrator.run(
            ctx,
            device_id="emulator-5554",
            package_name="com.demo",
            steps=[TAP],
            task_id="t-ime",
        )

        assert result["success"] is True
        assert restore_calls == ["emulator-5554"], "restore_ime must run exactly once"

    def test_step_failure_abort_restores_once(self, monkeypatch, tmp_path):
        ctx = FakeContext()
        executed, restore_calls = [], []
        _install(monkeypatch, tmp_path, [100, 100], executed, restore_calls,
                 failing_actions=("tap",))

        result = orchestrator.run(
            ctx,
            device_id="emulator-5554",
            package_name="com.demo",
            steps=[TAP],
            task_id="t-ime-fail",
        )

        assert result["success"] is False
        assert result["failed"] == 1
        assert restore_calls == ["emulator-5554"]

    def test_crash_abort_path_restores(self, monkeypatch, tmp_path):
        ctx = FakeContext()
        executed, restore_calls = [], []
        _install(monkeypatch, tmp_path, [100, 100, None], executed, restore_calls)

        orchestrator.run(
            ctx,
            device_id="emulator-5554",
            package_name="com.demo",
            steps=[TAP, TAP],
            task_id="t-ime-crash",
        )

        assert restore_calls == ["emulator-5554"]

    def test_cancel_path_restores(self, monkeypatch, tmp_path):
        ctx = FakeContext()
        ctx.cancelled = True
        executed, restore_calls = [], []
        _install(monkeypatch, tmp_path, [100], executed, restore_calls)

        result = orchestrator.run(
            ctx,
            device_id="emulator-5554",
            package_name="com.demo",
            steps=[TAP],
            task_id="t-ime-cancel",
        )

        assert result["cancelled"] is True
        assert restore_calls == ["emulator-5554"]

    def test_exception_path_restores(self, monkeypatch, tmp_path):
        """A raising step escapes execute_step's guard -> finally must clean up."""
        ctx = FakeContext()
        executed, restore_calls = [], []
        _install(monkeypatch, tmp_path, [100, 100], executed, restore_calls)

        def boom(ctx, device_id, package_name, action, step, dt):
            raise RuntimeError("stream died")

        monkeypatch.setattr(orchestrator, "execute_step", boom)

        with pytest.raises(RuntimeError, match="stream died"):
            orchestrator.run(
                ctx,
                device_id="emulator-5554",
                package_name="com.demo",
                steps=[TAP],
                task_id="t-ime-exc",
            )

        assert restore_calls == ["emulator-5554"]
        # The report is still written before the exception propagates.
        assert _report(tmp_path, "t-ime-exc")["kind"] == "automation_run"
        assert ctx.completed is not None
