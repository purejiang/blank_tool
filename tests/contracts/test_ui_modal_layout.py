#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用弹窗布局契约（AppModal 外壳的约定）。

`AppModal` 把「标题左上 / 关闭 X 右上 / 内容居中 / 功能按钮右下」收敛成一个组件，
这两条约定靠源码级检查守住，免得下次又被逐个弹窗手写回去：

* **footer 里不再放「关闭」按钮** —— 右上角已经有 X 了，右下角再来一个就是同一件
  事画两遍；footer 只留给真正的动作（刷新、确定……）。
* **内容长度会变的弹窗必须固定高度 + 内部滚动** —— 工具安装（探测态 → 两段内容 →
  安装日志逐行出现）和运行配置（三个页签长短不一）都因此会「弹窗自己长高/缩回」，
  标题和按钮跟着跳。
"""
import glob
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RENDERER = os.path.join(ROOT, "src", "renderer")


def _read(rel):
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
        return f.read()


def _app_modal_components():
    """所有使用 AppModal 的 SFC（路径 + 源码）。"""
    out = []
    for path in glob.glob(os.path.join(RENDERER, "**", "*.vue"), recursive=True):
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        if "<AppModal" in src:
            out.append((path, src))
    return out


def _rule(src, class_name):
    m = re.search(r"\." + class_name + r"\s*\{[^}]*\}", src)
    assert m, f"找不到 .{class_name} 样式（被改名或删除？）"
    return m.group(0)


class TestFooterHasNoRedundantClose:
    def test_some_component_uses_app_modal(self):
        assert _app_modal_components(), "没有任何组件使用 AppModal —— 这条契约已经失效"

    def test_footer_never_carries_a_close_button(self):
        offenders = []
        for path, src in _app_modal_components():
            for m in re.finditer(r"<template #footer>([\s\S]*?)</template>", src):
                if "common.close" in m.group(1):
                    offenders.append(os.path.relpath(path, ROOT))
        assert offenders == [], (
            f"footer 里出现重复的「关闭」按钮（右上角 X 已经能关）：{offenders}"
        )


class TestFixedHeightModals:
    """内容会变长的弹窗：固定内容高度 + 内部滚动。"""

    def test_tool_install_body_is_fixed_and_scrolls(self):
        block = _rule(_read("src/renderer/components/automation/ToolInstallModal.vue"), "tim-root")
        assert re.search(r"height:\s*\d+px", block), (
            "工具安装弹窗内容区必须固定高度，否则探测/日志会让弹窗不断长高"
        )
        assert "overflow-y: auto" in block, "内容超出时应在弹窗内部滚动"

    def test_run_config_panel_is_fixed_and_scrolls(self):
        block = _rule(_read("src/renderer/components/automation/RunConfigDialog.vue"), "rcfg-panel")
        assert re.search(r"height:\s*\d+px", block), (
            "运行配置内容区必须固定高度，否则切页签会改变弹窗高度"
        )
        assert "overflow-y: auto" in block, "内容超出时应在面板内部滚动"


class TestNavAccessibility:
    """左侧导航是 tablist：role/aria + 键盘操作（见 renderer/utils/navKeys.ts）。"""

    NAV_CONSUMERS = (
        "src/renderer/views/SettingsPage.vue",
        "src/renderer/components/automation/RunConfigDialog.vue",
    )

    def test_nav_items_are_tabs_with_roving_tabindex(self):
        for rel in self.NAV_CONSUMERS:
            src = _read(rel)
            assert 'role="tablist"' in src, f"{rel} 的左栏缺少 role=tablist"
            assert 'role="tab"' in src, f"{rel} 的导航项缺少 role=tab"
            assert "aria-selected" in src, f"{rel} 的导航项缺少 aria-selected"
            assert ":tabindex=" in src, f"{rel} 的导航项缺少 roving tabindex"
            assert "onNavKeydown" in src, f"{rel} 的导航项没有接键盘处理"

    def test_keyboard_helper_covers_arrows_home_end_and_activation(self):
        src = _read("src/renderer/utils/navKeys.ts")
        for key in ("ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight", "Home", "End", "Enter", " "):
            assert key in src, f"navKeys 缺少 {key!r} 的处理"
