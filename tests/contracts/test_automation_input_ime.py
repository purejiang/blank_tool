#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「开启中文输入」(/ ``use_ime``) contract tests.

The run setting introduced for the automation page's 输入 panel: when it is
OFF, a run must NOT switch the device IME to ADBKeyboard — a non-ASCII input
step has to fail with a clear message instead of silently changing the user's
input method. Default stays ON, so the historical behaviour is unchanged.

Pinned here:
* ``input_text(use_ime=False)`` refuses non-ASCII text (ASCII still works),
* the default parameter keeps the old behaviour,
* ``orchestrator.run`` accepts ``use_ime`` (default True) and hands it to the
  step context / records it in ``report.json``,
* the renderer side actually declares and forwards the field, so the switch
  cannot silently regress into a dead toggle.
"""

import inspect
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from app.automation import input as input_mod  # noqa: E402
from app.automation import orchestrator, steps  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _read(rel):
    with open(os.path.join(REPO_ROOT, rel), "r", encoding="utf-8") as f:
        return f.read()


class TestInputText:
    def test_non_ascii_is_refused_when_the_setting_is_off(self, monkeypatch):
        called = []
        monkeypatch.setattr(input_mod, "ensure_adb_ime", lambda device_id: called.append(device_id) or (True, ""))
        r = input_mod.input_text("emulator-5554", "中文输入", use_ime=False)
        assert r["success"] is False
        assert "中文输入" in r["error"] or "non-ASCII" in r["error"]
        # 关键：连输入法都没碰
        assert called == []

    def test_ascii_still_uses_plain_input_text_when_the_setting_is_off(self, monkeypatch):
        runs = []
        monkeypatch.setattr(input_mod, "run_adb", lambda device_id, args: runs.append(args) or {"returncode": 0})
        r = input_mod.input_text("emulator-5554", "hello", use_ime=False)
        assert r["success"] is True
        assert runs and runs[0][:3] == ["shell", "input", "text"]

    def test_default_is_on(self, monkeypatch):
        """不传 use_ime 时保持历史行为（允许切换输入法）。"""
        switched = []

        def fake_ensure(device_id):
            switched.append(device_id)
            return True, ""

        monkeypatch.setattr(input_mod, "ensure_adb_ime", fake_ensure)
        monkeypatch.setattr(input_mod, "run_adb", lambda device_id, args: {"returncode": 0})
        r = input_mod.input_text("emulator-5554", "中文")
        assert r["success"] is True
        assert switched == ["emulator-5554"]
        assert inspect.signature(input_mod.input_text).parameters["use_ime"].default is True


class TestOrchestratorWiring:
    def test_run_accepts_use_ime_defaulting_to_true(self):
        sig = inspect.signature(orchestrator.run)
        assert sig.parameters["use_ime"].default is True

    def test_steps_forward_the_context_flag(self):
        src = _read("backend/app/automation/steps.py")
        assert 'getattr(ctx, "use_ime", True)' in src, (
            "input 步骤必须把运行级 use_ime 传给 input_text"
        )

    def test_report_records_the_setting(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BT_AUTO_TASKS_DIR", str(tmp_path / "auto_tasks"))
        monkeypatch.setattr(orchestrator, "get_app_pid", lambda device_id, package: 100)
        monkeypatch.setattr(
            orchestrator, "execute_step",
            lambda ctx, device_id, package_name, action, step, dt: (True, "", None),
        )
        monkeypatch.setattr(orchestrator, "restore_ime", lambda device_id: None)
        monkeypatch.setattr(
            orchestrator, "get_display_transform",
            lambda device_id: {"rotation": 0, "width": 1080, "height": 1920},
        )
        monkeypatch.setattr(
            orchestrator, "take_screenshot",
            lambda device_id, name="", out_dir="": {"success": False},
        )

        class Ctx:
            def __init__(self):
                self.logs, self.steps, self.completed = [], [], None
                self.cancelled = False
                self.run_dir = ""

            def log(self, message):
                self.logs.append(message)

            def step_start(self, index, action):
                pass

            def step(self, record):
                self.steps.append(record)

            def complete(self, payload):
                self.completed = payload

            def is_cancelled(self):
                return False

        ctx = Ctx()
        orchestrator.run(
            ctx, device_id="emulator-5554", package_name="com.demo",
            steps=[{"action": "tap", "mode": "coord", "coord": {"x": 1, "y": 2}}],
            task_id="t-ime", use_ime=False,
        )
        # 运行级设置必须下发给步骤执行器
        assert getattr(ctx, "use_ime") is False
        with open(tmp_path / "auto_tasks" / "t-ime" / "report.json", encoding="utf-8") as f:
            report = json.load(f)
        assert report["use_ime"] is False


class TestRendererWiring:
    def test_protocol_declares_the_param(self):
        src = _read("src/shared/ipc/protocol.ts")
        assert "use_ime?: boolean" in src

    def test_runner_forwards_it(self):
        src = _read("src/renderer/composables/automation/useScriptRunner.ts")
        assert "use_ime: payload.use_ime !== false" in src

    def test_page_reads_the_setting_into_the_run(self):
        src = _read("src/renderer/views/OtherToolsPage.vue")
        assert "use_ime: enableChineseInput.value" in src

    def test_ui_state_and_default_declare_the_field(self):
        assert "enableChineseInput: boolean" in _read(
            "src/renderer/composables/automation/useAutomationStore.ts"
        )
        assert "enableChineseInput: true" in _read("src/main/stores/appStore.ts")

    @pytest.mark.parametrize("locale", ["zh-CN", "en-US"])
    def test_both_locales_have_the_label(self, locale):
        src = _read(f"src/renderer/i18n/locales/{locale}.ts")
        assert "enableChineseInput:" in src
