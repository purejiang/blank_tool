#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jadx_decompile — builtin plugin that drives an EXTERNAL CLI (jadx).

The reference example for "plugin = run an outside tool":
  * ``context.which("jadx")`` locates the binary — resolution order is
    ``BT_TOOL_JADX`` env → ``<runtime>/jadx/`` → system PATH. Nothing about
    jadx is hardcoded in the app itself.
  * ``context.run_command([...])`` streams jadx's stdout line-by-line to
    the frontend log, honors Stop (cooperative cancel) and timeout.
  * artifacts land in ``context.work_dir(task_id, sub)`` — the same
    per-task directory scheme every other feature uses.

jadx is NOT bundled with the app: install it separately (or unzip it into
``<runtime>/jadx/``), otherwise this plugin fails with a clear message.

Contract: call ``context.complete(...)`` exactly once before returning
(success, failure, or cancel).
"""

import os

DESCRIPTION = (
    "Decompile an APK with the external jadx CLI "
    "(requires jadx on PATH, BT_TOOL_JADX, or <runtime>/jadx/)."
)
VERSION = "1.0.0"
AUTHOR = "blank_tool"

PARAMS = [
    {
        "key": "apk_path",
        "label": "APK 路径",
        "type": "string",
        "required": True,
        "default": "",
    },
    {
        "key": "out_name",
        "label": "输出目录名",
        "type": "string",
        "required": False,
        "default": "jadx_out",
    },
    {
        "key": "extra_args",
        "label": "附加参数（空格分隔）",
        "type": "string",
        "required": False,
        "default": "",
    },
]


def run(context, apk_path: str = "", out_name: str = "jadx_out",
        extra_args: str = "", task_id: str = "", **kwargs):
    if not apk_path or not os.path.isfile(apk_path):
        context.complete({"success": False, "message": f"APK 不存在: {apk_path}"})
        return {"success": False, "message": f"APK 不存在: {apk_path}"}

    jadx = context.which("jadx")
    if not jadx:
        context.complete({
            "success": False,
            "message": "找不到 jadx。请安装后加入 PATH，设置 BT_TOOL_JADX，"
                       "或将其解压到 <runtime>/jadx/。",
        })
        return {"success": False, "message": "jadx not found"}

    out_dir = context.work_dir(task_id, os.path.join("jadx", out_name))
    cmd = [jadx, "-d", out_dir, apk_path]
    if extra_args:
        cmd += [a for a in extra_args.split() if a]

    context.log(f"jadx: {os.path.basename(apk_path)} -> {out_dir}")
    proc = context.run_command(cmd, on_line=None)

    if proc["cancelled"]:
        result = {"success": False, "cancelled": True, "out_dir": out_dir}
    elif proc["returncode"] != 0:
        result = {
            "success": False,
            "message": f"jadx 退出码 {proc['returncode']}，详见日志",
            "out_dir": out_dir,
        }
    else:
        result = {
            "success": True,
            "out_dir": out_dir,
            "duration_ms": proc["duration_ms"],
        }
    context.complete(result)
    return result
