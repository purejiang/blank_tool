#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract tests for the run span (从某一步开始) and step pacing (步骤间隔).

Two capabilities that make a long script debuggable without editing it:

* ``start_index`` — begin the run at step N; the earlier steps are **not
  executed**. Step numbers in the report keep their ORIGINAL 1-based position
  (starting at step 5 still reports #5, #6 …) so the run rows line up with the
  script rows, while ``total`` counts only the steps the run attempted —
  ``passed + failed <= total`` stays consistent for the history row.
* ``step_interval_ms`` — a default wait before every step (except the first
  executed one), overridable per step with ``delay_ms`` (``0`` = no wait for
  that step). Without it a script needs a hand-written ``wait`` step between
  every pair of actions.

The UI half of the contract is pinned at the bottom (renderer source checks).
"""

import inspect
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from app.automation import orchestrator  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class FakeContext:
    """Minimal StreamContext stand-in (same shape the other contract tests use)."""

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


def _install(monkeypatch, tmp_path):
    """Wire the orchestrator to a fake device; returns the executed-step list."""
    monkeypatch.setenv("BT_AUTO_TASKS_DIR", str(tmp_path / "auto_tasks"))
    executed = []

    def fake_execute(ctx, device_id, package_name, action, step, dt):
        executed.append(step)
        return True, "", None

    monkeypatch.setattr(orchestrator, "get_app_pid", lambda device_id, package: 100)
    monkeypatch.setattr(orchestrator, "execute_step", fake_execute)
    monkeypatch.setattr(orchestrator, "restore_ime", lambda device_id: None)
    monkeypatch.setattr(
        orchestrator, "get_display_transform",
        lambda device_id: {"rotation": 0, "width": 1080, "height": 1920},
    )
    monkeypatch.setattr(
        orchestrator, "take_screenshot",
        lambda device_id, name="", out_dir="": {"success": False},
    )
    # Intervals are recorded, never slept: a real 300ms wait per step would make
    # this file slow without testing anything the recorder does not see.
    slept = []
    monkeypatch.setattr(
        orchestrator, "_interruptible_sleep",
        lambda context, ms: slept.append(ms),
    )
    return executed, slept


def _steps(n, **extra):
    out = []
    for i in range(n):
        step = {"action": "tap", "mode": "coord", "coord": {"x": i, "y": i}}
        step.update(extra)
        out.append(step)
    return out


def _run(monkeypatch, tmp_path, steps, task_id="t-span", **kwargs):
    executed, slept = _install(monkeypatch, tmp_path)
    ctx = FakeContext()
    result = orchestrator.run(
        ctx, device_id="emulator-5554", package_name="com.demo",
        steps=steps, task_id=task_id, **kwargs,
    )
    return result, executed, slept, ctx


# ---------------------------------------------------------------------------
# start_index — run from step N
# ---------------------------------------------------------------------------

class TestStartIndex:
    def test_run_starts_at_the_given_step(self, monkeypatch, tmp_path):
        steps = _steps(5)
        result, executed, _, _ = _run(monkeypatch, tmp_path, steps, start_index=3)

        # only steps 4 and 5 executed, and they are the SAME objects the script had
        assert executed == steps[3:]
        assert result["start_index"] == 3
        # total = attempted steps, not the script length
        assert result["total"] == 2
        assert result["passed"] == 2 and result["failed"] == 0
        # report indices keep the ORIGINAL 1-based script position
        assert [r["index"] for r in result["steps"]] == [4, 5]

    def test_default_still_starts_at_the_first_step(self, monkeypatch, tmp_path):
        steps = _steps(5)
        result, executed, _, _ = _run(monkeypatch, tmp_path, steps)
        assert executed == steps
        assert result["start_index"] == 0
        assert result["total"] == 5
        assert [r["index"] for r in result["steps"]] == [1, 2, 3, 4, 5]

    def test_out_of_range_is_clamped_to_the_last_step_and_logged(self, monkeypatch, tmp_path):
        # A stale UI (the step was deleted after the menu was built) must not
        # turn into "nothing ran at all" — the closest honest reading is the
        # last step, and the clamp has to be visible in the log.
        steps = _steps(4)
        result, executed, _, ctx = _run(monkeypatch, tmp_path, steps, start_index=99)
        assert executed == [steps[-1]]
        assert result["start_index"] == 3
        assert result["total"] == 1
        assert any("out of range" in line for line in ctx.logs), ctx.logs

    def test_negative_start_index_runs_from_the_first_step(self, monkeypatch, tmp_path):
        steps = _steps(3)
        result, executed, _, _ = _run(monkeypatch, tmp_path, steps, start_index=-5)
        assert executed == steps
        assert result["start_index"] == 0

    @pytest.mark.parametrize("value", ["2", None, True, "abc", 1.9])
    def test_the_index_is_coerced_defensively(self, monkeypatch, tmp_path, value):
        """``start_index`` comes straight off the wire — never raise on it."""
        steps = _steps(4)
        result, executed, _, _ = _run(monkeypatch, tmp_path, steps, start_index=value)
        assert 0 <= result["start_index"] <= 3
        assert executed == steps[result["start_index"]:]

    def test_starting_midway_is_announced_in_the_run_log(self, monkeypatch, tmp_path):
        _, _, _, ctx = _run(monkeypatch, tmp_path, _steps(5), start_index=2)
        assert any("starting at step 3/5" in line for line in ctx.logs), ctx.logs

    def test_empty_script_is_untouched(self, monkeypatch, tmp_path):
        result, executed, _, _ = _run(monkeypatch, tmp_path, [], start_index=3)
        assert executed == []
        assert result["total"] == 0
        assert result["start_index"] == 0
        assert result["success"] is True

    def test_report_records_the_span_but_the_index_stays_small(self, monkeypatch, tmp_path):
        _run(monkeypatch, tmp_path, _steps(4), start_index=1, step_interval_ms=250)
        run_dir = tmp_path / "auto_tasks" / "t-span"
        with open(run_dir / "report.json", encoding="utf-8") as f:
            report = json.load(f)
        assert report["start_index"] == 1
        assert report["step_interval_ms"] == 250
        assert report["total"] == 3
        # the history index is the small list file: no new keys tacked onto it
        with open(run_dir / "summary.json", encoding="utf-8") as f:
            summary = json.load(f)
        assert "start_index" not in summary
        assert "step_interval_ms" not in summary


# ---------------------------------------------------------------------------
# step_interval_ms / per-step delay_ms — pacing
# ---------------------------------------------------------------------------

class TestStepInterval:
    def test_no_interval_means_no_wait_at_all(self, monkeypatch, tmp_path):
        _, _, slept, _ = _run(monkeypatch, tmp_path, _steps(3))
        assert slept == []

    def test_interval_waits_before_every_step_except_the_first(self, monkeypatch, tmp_path):
        _, executed, slept, _ = _run(monkeypatch, tmp_path, _steps(3), step_interval_ms=300)
        assert len(executed) == 3
        assert slept == [300, 300]

    def test_starting_midway_does_not_wait_before_the_first_executed_step(self, monkeypatch, tmp_path):
        _, executed, slept, _ = _run(
            monkeypatch, tmp_path, _steps(3), start_index=1, step_interval_ms=300,
        )
        assert len(executed) == 2
        assert slept == [300]

    def test_delay_ms_overrides_the_run_interval_per_step(self, monkeypatch, tmp_path):
        steps = _steps(4)
        steps[2]["delay_ms"] = 0        # this step needs no wait
        steps[3]["delay_ms"] = 120      # this one needs a longer one
        _, _, slept, _ = _run(monkeypatch, tmp_path, steps, step_interval_ms=300)
        # i=0 first executed → none; i=1 inherits 300; i=2 explicit 0 → none;
        # i=3 explicit 120
        assert slept == [300, 120]

    def test_a_malformed_delay_ms_falls_back_to_the_run_interval(self, monkeypatch, tmp_path):
        steps = _steps(2)
        steps[1]["delay_ms"] = "soon"
        _, _, slept, _ = _run(monkeypatch, tmp_path, steps, step_interval_ms=300)
        assert slept == [300]

    def test_the_interval_is_announced_in_the_run_log(self, monkeypatch, tmp_path):
        _, _, _, ctx = _run(monkeypatch, tmp_path, _steps(2), step_interval_ms=300)
        assert any("step interval 300ms" in line for line in ctx.logs), ctx.logs

    def test_cancel_during_the_interval_stops_before_the_step(self, monkeypatch, tmp_path):
        """The interval is slept BEFORE the step's cancel check, so a Stop
        pressed while a step is spacing must not execute that step."""
        executed, _ = _install(monkeypatch, tmp_path)
        # The FIRST step needs an explicit delay: the run-level interval is
        # deliberately skipped before the first executed step.
        steps = _steps(3)
        steps[0]["delay_ms"] = 300
        monkeypatch.setattr(
            orchestrator, "_interruptible_sleep",
            lambda context, ms: setattr(context, "cancelled", True),
        )
        ctx = FakeContext()
        result = orchestrator.run(
            ctx, device_id="emulator-5554", package_name="com.demo",
            steps=steps, task_id="t-span", step_interval_ms=300,
        )
        assert executed == []
        assert result["cancelled"] is True
        assert result["success"] is False

    @pytest.mark.parametrize("step,is_first,expected", [
        ({}, True, 0),                    # first executed step: nothing to space from
        ({}, False, 300),                 # inherit the run-level interval
        ({"delay_ms": 0}, False, 0),      # explicit "no wait"
        ({"delay_ms": 120}, False, 120),  # explicit override
        ({"delay_ms": -5}, False, 0),     # negative collapses to 0
        ({"delay_ms": None}, False, 300),  # null = inherit
        ({"delay_ms": True}, False, 300),  # a bool is a malformed payload, not 1ms
        ({"delay_ms": "x"}, False, 300),   # garbage = inherit
    ])
    def test_step_gap_ms_resolution(self, step, is_first, expected):
        assert orchestrator._step_gap_ms(step, 300, is_first) == expected


# ---------------------------------------------------------------------------
# UI half of the contract (renderer source checks)
# ---------------------------------------------------------------------------

class TestUiContract:
    def _read(self, rel):
        with open(os.path.join(REPO_ROOT, rel), "r", encoding="utf-8") as f:
            return f.read()

    def test_backend_signature_keeps_both_defaults(self):
        sig = inspect.signature(orchestrator.run)
        assert sig.parameters["start_index"].default == 0
        assert sig.parameters["step_interval_ms"].default == 0

    def test_step_type_declares_delay_ms(self):
        src = self._read("src/renderer/components/automation/stepTypes.ts")
        assert "delay_ms?: number" in src, "Step.delay_ms missing from stepTypes.ts"

    def test_step_editor_has_an_interval_row(self):
        src = self._read("src/renderer/components/automation/StepEditForm.vue")
        assert "automation.f.intervalMs" in src
        assert "next.delay_ms = " in src, (
            "save() must write the per-step interval back into the step"
        )
        assert "defaultInterval" in src, "the run-level default must reach the form"

    def test_row_menu_offers_run_from_this_step(self):
        src = self._read("src/renderer/components/automation/StepListEditor.vue")
        assert "automation.runFromStep" in src
        assert "'runFrom'" in src and "emit('runFrom'" in src

    def test_run_config_dialog_exposes_the_interval(self):
        src = self._read("src/renderer/components/automation/RunConfigDialog.vue")
        assert "runConfigExec" in src, "运行配置左栏要有「执行」页签"
        assert "update:stepIntervalMs" in src
        assert "automation.stepIntervalHint" in src

    def test_controls_forward_the_interval(self):
        src = self._read("src/renderer/components/automation/RunControls.vue")
        assert "update:stepIntervalMs" in src
        assert "step-interval-ms" in src

    def test_runner_forwards_both_run_options(self):
        src = self._read("src/renderer/composables/automation/useScriptRunner.ts")
        assert "start_index: Math.max(0" in src
        assert "step_interval_ms: Math.max(0" in src
        assert "start_index?: number" in src and "step_interval_ms?: number" in src

    def test_page_sends_the_span_and_the_interval(self):
        src = self._read("src/renderer/views/OtherToolsPage.vue")
        assert "start_index: start" in src
        assert "step_interval_ms: store.ui.stepIntervalMs" in src
        assert "@run-from=\"runFromStep\"" in src
        # the header Run button must stay "from the beginning" no matter what
        # arguments an emit could carry
        assert '@run="() => runScript(0)"' in src

    def test_ipc_protocol_declares_both_params(self):
        src = self._read("src/shared/ipc/protocol.ts")
        assert "start_index?: number" in src
        assert "step_interval_ms?: number" in src

    def test_ui_defaults_carry_the_interval(self):
        store = self._read("src/renderer/composables/automation/useAutomationStore.ts")
        assert "stepIntervalMs: 300" in store, "默认步骤间隔（300ms）在 UI 偏好里"
        # 0 is a legal value (= no interval), so sanitize must not use `> 0`
        assert "n >= 0) out.stepIntervalMs" in store
        schema = self._read("src/main/stores/appStore.ts")
        assert "stepIntervalMs: 300" in schema, "app-config schema 也要有默认值"

    def test_recording_does_not_synthesize_wait_steps(self):
        """录制只记录操作本身。

        等待由**运行配置里的步骤间隔**统一控制（个别步骤用 `delay_ms` 覆盖），
        所以录制侧不再有「按录制节奏合成等待步骤」这条路 —— 一份节奏设置，
        脚本里也不会凭空多出一堆 wait 步骤。
        """
        store = self._read("src/renderer/composables/automation/useAutomationStore.ts")
        assert "withWaits" not in store, "录制不再合成等待步骤"
        assert "thresholdMs" not in store and "payload.gap" not in store
        assert "message.success(t('automation.recordApplied'))" in store, (
            "录制落库后仍然只报「已应用」"
        )

        panel = self._read("src/renderer/components/automation/RecordPanel.vue")
        for gone in ("autoWaitEnabled", "waitThreshold", "waitMaxCap", "thresholdMs"):
            assert gone not in panel, f"录制面板不该再有 {gone}"
        assert "recordIntervalHint" in panel, "面板要说明等待改由运行配置控制"

        # 录制时间线（设备时间 ts）不再进入步骤模型：它只服务于旧的等待合成
        assert "ts?: number" not in self._read(
            "src/renderer/components/automation/stepTypes.ts"
        )
