#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
automation CLI — run adb automation WITHOUT the app GUI.

Usage (from the repo root)::

    python automation_cli.py --steps steps.json [--device SERIAL] [--package PKG]

or with an explicit run directory / adb binary::

    python automation_cli.py --steps steps.json --out D:/runs --adb D:/sdk/adb.exe

Same core as the automation page and the adb_auto plugin
(``app/automation/orchestrator.run``): progress lines go to stdout, the
run report lands in ``{--out dir}/{task_id}/report.json``.

STANDALONE DISTRIBUTION: this CLI needs nothing but a Python 3.10+
(standard library only) plus an adb binary. To use it outside the app,
copy ``backend/app/`` + ``automation_cli.py`` and make adb reachable
(``--adb``, ``BT_TOOL_ADB``, or PATH).

Traffic capture is NOT available here (it requires the bundled
``runtime/mitmproxy``); use the app's automation page for that.

Cancellation: Ctrl+C aborts the process directly (steps run as short adb
commands, so nothing is left dangling on the device beyond the current
command).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from app.common.stream_context import StreamContext
from app.tools.tool_manager import ToolManager
from app.utils.env import get_runtime_dir
from app.utils.logger import Logger


class CliStreamContext(StreamContext):
    """StreamContext that prints progress to stdout instead of IPC.

    Keeps the exact same event contract (log / step_start / step /
    complete) as the streaming handlers, so the orchestrator behaves
    identically under CLI and GUI.
    """

    def _emit(self, event: dict):
        ev_type = event.get("type")
        payload = event.get("payload")
        ts = time.strftime("%H:%M:%S")
        if ev_type == "log":
            print(f"[{ts}] {payload}", flush=True)
        elif ev_type == "step_start":
            print(f"[{ts}] -> #{payload.get('index')} {payload.get('action')} ...", flush=True)
        elif ev_type == "step":
            ok = "OK  " if payload.get("ok") else "FAIL"
            dur = payload.get("duration_ms", 0)
            msg = payload.get("message", "")
            print(f"[{ts}] <- #{payload.get('index')} {payload.get('action')} {ok} ({dur}ms) {msg}", flush=True)
        elif ev_type == "complete":
            passed = payload.get("passed", 0)
            failed = payload.get("failed", 0)
            cancelled = payload.get("cancelled", False)
            run_dir = payload.get("run_dir", "")
            print("-" * 56, flush=True)
            print(f"result    : {'CANCELLED' if cancelled else ('SUCCESS' if payload.get('success') else 'FAILED')}", flush=True)
            print(f"steps     : {passed} passed / {failed} failed / {payload.get('total', 0)} total", flush=True)
            if run_dir:
                print(f"report    : {os.path.join(run_dir, 'report.json')}", flush=True)
            print("-" * 56, flush=True)
        # error events: orchestrator reserves context.error() for fatal
        # cases; the streaming wrapper turns a raised exception into the
        # error envelope, so print and let the non-zero exit code speak.
        elif ev_type == "error":
            print(f"[{ts}] [ERROR] {payload}", file=sys.stderr, flush=True)


def resolve_adb(explicit: Optional[str]) -> str:
    """Resolve the adb binary: --adb > BT_TOOL_ADB > runtime/ > PATH.

    Injects the result into the ToolManager so ``run_adb`` (which only
    knows about runtime/ paths) picks it up. A candidate that fails
    validation (set_custom_path runs ``adb -version`` once) is skipped.
    """
    candidates: List[str] = []
    if explicit:
        candidates.append(explicit)
    env_override = os.environ.get("BT_TOOL_ADB")
    if env_override:
        candidates.append(env_override)
    is_win = os.name == "nt"
    candidates.append(
        os.path.join(get_runtime_dir(), "adb", "adb.exe" if is_win else "adb")
    )

    def _inject(path: str) -> bool:
        try:
            ToolManager.instance().set_custom_path("adb", path)
            return True
        except OSError as e:
            print(f"[WARN] adb 候选不可用 {path}: {e}", file=sys.stderr, flush=True)
            return False

    for cand in candidates:
        if cand and os.path.isfile(cand) and _inject(cand):
            return cand
    which = shutil.which("adb")
    if which and _inject(which):
        return which
    raise SystemExit(
        "找不到 adb。请安装并加入 PATH，或用 --adb / 环境变量 BT_TOOL_ADB 指定路径。"
    )


def detect_single_device(adb: str) -> str:
    """Return the serial when exactly one device is online, else fail loudly."""
    out = subprocess.run(
        [adb, "devices"], capture_output=True, text=True, timeout=15
    ).stdout
    serials = [
        line.split("\t")[0].strip()
        for line in out.splitlines()
        if "\tdevice" in line
    ]
    if len(serials) == 1:
        return serials[0]
    if not serials:
        raise SystemExit("没有检测到在线设备（adb devices 为空）。")
    raise SystemExit(
        "检测到多台设备，请用 --device 指定序列号：\n  " + "\n  ".join(serials)
    )


def load_steps(path: str) -> List[Dict[str, Any]]:
    if not os.path.isfile(path):
        raise SystemExit(f"步骤文件不存在: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            steps = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"步骤文件解析失败: {e}")
    if not isinstance(steps, list):
        raise SystemExit("步骤文件必须是 JSON 数组（steps[]）。")
    return steps


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="automation_cli",
        description="adb 自动化命令行入口（与应用内自动化页/adb_auto 插件共用同一核心）",
    )
    parser.add_argument("--steps", required=True, help="步骤 JSON 文件路径（steps 数组）")
    parser.add_argument("--device", default="", help="设备序列号；省略时若只连接了一台设备则自动选择")
    parser.add_argument("--package", default="", help="目标应用包名（launch 等步骤需要）")
    parser.add_argument("--adb", default="", help="adb 可执行文件路径（默认 BT_TOOL_ADB > runtime/ > PATH）")
    parser.add_argument("--out", default="", help="运行产物根目录（默认 ./auto_runs）")
    parser.add_argument("--continue-on-error", action="store_true", help="步骤失败后继续执行后续步骤")
    args = parser.parse_args(argv)

    steps = load_steps(args.steps)
    adb = resolve_adb(args.adb or None)
    device = args.device or detect_single_device(adb)

    if args.out:
        os.environ["BT_AUTO_TASKS_DIR"] = os.path.abspath(args.out)
    else:
        os.environ.setdefault("BT_AUTO_TASKS_DIR", os.path.abspath("auto_runs"))
    task_id = f"cli-{time.strftime('%Y%m%d-%H%M%S')}"

    # 延迟 import：让 --out 的 env 默认值先生效（env.py 在调用时才读环境变量）
    from app.automation.orchestrator import run as run_orchestration

    logger = Logger.get_logger("automation.cli")
    logger.info(f"CLI run: device={device} steps={len(steps)} task_id={task_id}")

    ctx = CliStreamContext("automation")
    try:
        result = run_orchestration(
            ctx,
            device_id=device,
            package_name=args.package or None,
            steps=steps,
            continue_on_error=args.continue_on_error,
            capture_traffic=False,
            task_id=task_id,
        )
    except KeyboardInterrupt:
        print("\n[CANCELLED] 用户中断", file=sys.stderr, flush=True)
        return 1
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
