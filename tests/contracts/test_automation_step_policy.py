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

    def test_step_editor_rows_are_three_columns_with_a_separate_action_cell(self):
        """步骤编辑表单的布局契约。

        每行三列：标签 | 输入 | 动作。控件列 `minmax(0, 1fr)` 的最小宽度必须是 0
        （否则控件的 min-content 会把行撑宽、窄列下按钮被挤出可见区）；动作列
        `max-content` 且每行都渲染 `.form-actions-cell`（没动作时留空），这样所有
        输入框右边缘对齐。

        按钮**只**出现在动作列里：不得再塞进输入框的前缀/后缀（"按钮和输入框别
        混在一起"）。
        """
        src = self._read("src/renderer/components/automation/StepEditForm.vue")
        assert "grid-template-columns: 72px minmax(0, 1fr) max-content" in src, (
            "三列网格（标签 | 输入 | 动作）是这套布局的地基"
        )
        assert "form-actions-cell" in src
        # 动作列之外的输入框里不许有按钮：只允许 prefix 放 X / Y 文字标记
        assert "#suffix" not in src, "拾取按钮不许再放进输入框后缀"
        assert "IconButton" not in src, "动作列用的是带文字的按钮，不是输入框内图标"

    def test_step_list_add_entry_is_pinned_at_the_bottom(self):
        """添加步骤的入口固定在列表底部；顶部「插入到开头」幽灵行已删除。"""
        page = self._read("src/renderer/views/OtherToolsPage.vue")
        assert "insert-top" not in page, "顶部幽灵行应已删除"
        assert "automation.insertStart" not in page

        steps = self._read("src/renderer/components/automation/StepListEditor.vue")
        assert "add-step" in steps, "列表底部要有常驻的「添加步骤」入口"
        assert "onAppend" in steps

    def test_step_row_ops_are_a_single_vertical_menu(self):
        """每行右侧只有一个竖排「⋮」菜单：向下添加步骤 / 上移 / 下移 / 置顶 / 复制 / 删除。"""
        steps = self._read("src/renderer/components/automation/StepListEditor.vue")
        assert "MoreVertical" in steps
        assert "rowMenuOptions" in steps
        for key in ("addStepBelow", "stepUp", "stepDown", "moveToTop", "duplicateStep"):
            assert f"automation.{key}" in steps, f"行菜单缺少 {key}"

    def test_project_tree_uses_overlay_scrollbar_and_reports_expansion(self):
        """左栏：覆盖式滚动条（不占宽度）+ 开合箭头（aria-expanded）+ 行内徽标。"""
        src = self._read("src/renderer/components/automation/ProjectTree.vue")
        assert "n-scrollbar" in src, "左栏滚动容器应与步骤列表统一用 n-scrollbar"
        assert not re.search(r"^\s*scrollbar-gutter\s*:", src, re.M)
        assert "aria-expanded" in src, "开合箭头要暴露 aria-expanded"
        assert "proj-caret" in src
        assert "scriptCountBadge" in src and "stepCountBadge" in src, "行内要有规模徽标"

    def test_run_controls_expose_both_run_level_switches(self):
        """两个运行级开关的 UI 在 RunConfigDialog（两栏运行配置）里；RunControls
        只保留同名 prop/emit 做转发，所以两个文件都要出现这两个 v-model 名。"""
        dialog = self._read("src/renderer/components/automation/RunConfigDialog.vue")
        assert "update:continueOnError" in dialog
        assert "update:abortOnCrash" in dialog
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


class TestRunConfigDialogLayout:
    """运行配置弹窗的布局契约。

    弹窗是两栏（左「抓包 / 输入 / 异常处理」，右内容）。三个页签的内容长短差很多
    （抓包最长），若让 n-card 自适应高度，切页签时整个弹窗会长高/缩小、关闭按钮
    跟着跳 —— 所以内容区必须是**固定高度 + 内部滚动**。
    """

    def _read(self, rel):
        with open(os.path.join(REPO_ROOT, rel), "r", encoding="utf-8") as f:
            return f.read()

    def test_dialog_declares_the_three_tabs(self):
        src = self._read("src/renderer/components/automation/RunConfigDialog.vue")
        for key in ("runConfigCapture", "runConfigInput", "runConfigErrors"):
            assert key in src, f"运行配置弹窗缺少 {key} 页签"

    def test_panel_height_is_fixed_so_tabs_do_not_resize_the_dialog(self):
        src = self._read("src/renderer/components/automation/RunConfigDialog.vue")
        m = re.search(r"\.rcfg-panel\s*\{[^}]*\}", src)
        assert m, ".rcfg-panel 样式被改名或删除"
        block = m.group(0)
        assert re.search(r"height:\s*\d+px", block), (
            "内容区必须有固定高度，否则切换页签会改变弹窗高度"
        )
        assert "overflow-y: auto" in block, (
            "更高的页签应当在面板内部滚动，而不是把弹窗撑高"
        )

    def test_step_list_uses_an_overlay_scrollbar_so_rows_stay_centered(self):
        """步骤列表不能用「原生滚动条 + scrollbar-gutter: stable」：
        那会在右侧常驻一条 10px 车道，卡片因此比上面的「插入到开头」按钮窄一截，
        看上去就是「列表没居中」。改用覆盖式滚动条（n-scrollbar）后不占布局宽度。"""
        page = self._read("src/renderer/views/OtherToolsPage.vue")
        m = re.search(r"\.editor-body\s*\{[^}]*\}", page)
        assert m, ".editor-body 样式被改名或删除"
        assert "scrollbar-gutter" not in m.group(0)

        steps = self._read("src/renderer/components/automation/StepListEditor.vue")
        assert "n-scrollbar" in steps and "sl-scroll" in steps
        # 注释里保留着「为什么不用它」的说明，所以先把注释剥掉再看有没有真正的声明
        no_comments = re.sub(r"<!--[\s\S]*?-->", "", steps)
        no_comments = re.sub(r"/\*[\s\S]*?\*/", "", no_comments)
        assert not re.search(r"^\s*scrollbar-gutter\s*:", no_comments, re.M), (
            "步骤列表不要预留滚动条车道，否则行列与按钮右边缘对不齐"
        )

    def test_filter_conditions_are_a_list_not_a_tag_cloud(self):
        """域名过滤是一条一行的滑动列表：标签云会跟过滤说明抢高度、条件多了放不下。"""
        src = self._read("src/renderer/components/automation/RunConfigDialog.vue")
        assert "n-dynamic-tags" not in src, "过滤条件应改为列表形式"
        assert "rcfg-list-row" in src
        m = re.search(r"\.rcfg-list\s*\{[^}]*\}", src)
        assert m, ".rcfg-list 样式被改名或删除"
        block = m.group(0)
        assert re.search(r"height:\s*\d+px", block), (
            "滑动列表必须有固定高度，否则条件一多就会把弹窗顶高"
        )
        assert "overflow-y: auto" in block, "列表内部要能滚动"
