#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrcpy_mirror — builtin plugin that launches the EXTERNAL scrcpy GUI.

Same pattern as ``jadx_decompile``: the plugin is a thin launcher around a
local tool, nothing about scrcpy is bundled or hardcoded.

scrcpy is a long-running GUI process: the mirror window stays open until the
user closes it (scrcpy exits 0) or the run is stopped from the frontend
(``run_command``'s cooperative cancel kills it). While it runs, its output
streams to the plugin log.

Two deliberate details:

* ``--adb`` points scrcpy at the SAME adb the rest of the app uses
  (``context.adb.tool_path``). scrcpy ships its own adb; if the two adb
  versions differ, scrcpy restarting the adb server would kick devices
  already connected by the automation features. Sharing one server avoids
  that. Falls back silently when the app-side adb is unavailable.
* ``-s <serial>`` is only added when the user filled the param — empty
  means "let scrcpy pick the only/default device".

Contract: end with ``return context.finish(...)`` exactly once
(success, failure, or cancel) — it emits the terminal ``complete``.
"""

import os

DESCRIPTION = (
    "Mirror a device screen with the external scrcpy GUI "
    "(requires scrcpy on PATH, BT_TOOL_SCRCPY, or <runtime>/scrcpy/)."
)
VERSION = "1.0.0"
AUTHOR = "blank_tool"

PARAMS = [
    {
        "key": "serial",
        "label": "设备序列号（空 = 默认设备）",
        "type": "string",
        "required": False,
        "default": "",
    },
    {
        "key": "extra_args",
        "label": "附加参数（空格分隔，如 --max-size 1280）",
        "type": "string",
        "required": False,
        "default": "",
    },
]


def run(context, serial: str = "", extra_args: str = "",
        task_id: str = "", **kwargs):
    scrcpy = context.which("scrcpy")
    if not scrcpy:
        return context.finish({
            "success": False,
            "message": "找不到 scrcpy。请安装后加入 PATH，设置 BT_TOOL_SCRCPY，"
                       "或将其解压到 <runtime>/scrcpy/。",
        })

    cmd = [scrcpy]

    # 复用应用侧的 adb，避免 scrcpy 自带 adb 版本不一致时重启 adb server、
    # 踢掉 automation 已连接的设备
    adb_path = None
    try:
        adb_path = context.adb.tool_path
    except Exception:
        adb_path = context.which("adb")
    if adb_path and os.path.isfile(adb_path):
        cmd += ["--adb", adb_path]

    if serial:
        cmd += ["-s", serial]
    if extra_args:
        cmd += [a for a in extra_args.split() if a]

    context.log(f"scrcpy 启动: {os.path.basename(scrcpy)}"
                + (f" (设备 {serial})" if serial else " (默认设备)"))
    proc = context.run_command(cmd)

    if proc["cancelled"]:
        result = {"success": False, "cancelled": True, "message": "镜像已停止"}
    elif proc["returncode"] != 0:
        result = {
            "success": False,
            "message": f"scrcpy 退出码 {proc['returncode']}，详见日志",
        }
    else:
        result = {
            "success": True,
            "message": "镜像已关闭",
            "duration_ms": proc["duration_ms"],
        }
    return context.finish(result)
