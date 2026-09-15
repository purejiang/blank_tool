#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
automation.run — streaming handler for ADB UI automation runs.

Automation used to ride on the plugin framework (``plugin.run name=adb_auto``);
it is now a first-class feature with its own ``automation.*`` namespace
(sibling of ``automation.list_runs / read_run / delete_run / export_run``),
and ``plugin.run`` is reserved for actual plugins (external tools).

The streaming mechanics are IDENTICAL to what ``plugin_handler.run_plugin``
did: ``@streaming`` threads the handler, injects the request's ``task_id``
into the params so the orchestrator can find its per-run artifact
directory, and registers a stop_event the orchestrator polls for cancel.
"""

import os
import subprocess
import sys

from app.automation.input import ime_status as ime_status_impl
from app.automation.orchestrator import run as run_orchestration
from app.automation.traffic import status as traffic_status_impl
from app.automation.traffic import any_capture_active
from app.automation.traffic import ca_cert_path
from app.automation.traffic import install_ca as install_ca_impl
from app.common.decorators import logs_errors, streaming
from app.common.exceptions import ToolException
from app.common.stream_context import StreamContext
from app.utils.env import get_runtime_dir
from app.utils.logger import Logger

logger = Logger.get_logger("AutomationHandler")


@streaming
def run_automation(params, stream_handler):
    """Run an automation script (device + JSON step list)."""
    task_id = params.get("task_id")
    ctx = StreamContext("automation", stream_handler)
    try:
        return run_orchestration(ctx, task_id=str(task_id) if task_id else None, **{
            k: v for k, v in params.items() if k != "task_id"
        })
    except Exception as e:
        logger.error(f"automation.run failed: {e}", exc_info=True)
        raise ToolException(str(e) or "automation run failed")


@logs_errors("AutomationHandler")
def traffic_status(params, stream_handler=None):
    """Report mitmproxy availability (non-streaming, read-only).

    Backs the settings page's capability card and the automation page's
    "capture traffic" hint. Never touches the device.
    """
    return traffic_status_impl()


@logs_errors("AutomationHandler")
def ime_status(params, stream_handler=None):
    """Report ADBKeyBoard availability on one device (non-streaming).

    Non-ASCII ``input_text`` steps silently fail without ADBKeyBoard, so the
    UI probes this before a run instead of discovering it mid-run. Device
    side, hence the required ``device_id``.
    """
    device_id = str(params.get("device_id") or "").strip()
    if not device_id:
        raise ToolException("device_id is required")
    return ime_status_impl(device_id)


@logs_errors("AutomationHandler")
def install_ca(params, stream_handler=None):
    """Install the mitmproxy CA cert onto one device (non-streaming).

    Only meaningful after a first capture generated the CA locally, so the
    preflight below rejects before touching the device. The preflight reads
    THIS module's ``ca_cert_path`` alias (not the traffic impl) so tests can
    point it at a tmp path — same impl-alias convention as ``ime_status_impl``.
    """
    device_id = str(params.get("device_id") or "").strip()
    if not device_id:
        raise ToolException("device_id is required")
    if not os.path.isfile(ca_cert_path()):
        raise ToolException("CA cert not generated yet — run one capture first")
    return install_ca_impl(device_id)


def _pip_available() -> bool:
    """True when this interpreter can run ``pip`` at all.

    The packaged ``runtime/python`` may ship without pip (unverifiable from
    the repo), so every probe failure — missing module, timeout, any OS
    error — degrades to the manual-command path instead of crashing.
    """
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "pip", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return False
    try:
        proc.communicate(timeout=30)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        return False
    return proc.returncode == 0


def _pip_install(lib_path: str, on_line) -> int:
    """``pip install --target`` mitmproxy into ``lib_path``.

    Streams every stdout/stderr line through ``on_line``. Returns the exit
    code; ANY exception (spawn failure, broken pipe, ...) counts as a
    non-zero code so the caller degrades to the manual command.
    """
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "pip", "install", "--target", lib_path,
             "--upgrade", "mitmproxy"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return 1
    try:
        for line in proc.stdout:
            line = line.rstrip("\r\n")
            if line:
                on_line(line)
        proc.wait()
        return proc.returncode if proc.returncode is not None else 1
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        return 1


@streaming
@logs_errors("AutomationHandler")
def install_mitmproxy(params, stream_handler):
    """Install mitmproxy into the bundled runtime via pip (streaming).

    Order matters: refuse while a capture runs (Windows locks mitmdump's
    .pyd/.dll), bail without a runtime dir, then probe pip. Any pip failure
    — probe or install — degrades to a copy-pasteable manual command with
    both paths double-quoted (space-safe). Never generates the CA; the
    first capture run does that.
    """
    ctx = StreamContext("automation", stream_handler)

    if any_capture_active():
        ctx.error("请先停止运行中的抓包再安装")
        return

    runtime = get_runtime_dir()
    if not runtime:
        ctx.error("runtime 目录缺失，无法安装 mitmproxy")
        return

    lib = os.path.join(runtime, "mitmproxy", "lib")
    python_bin = sys.executable
    manual_command = f'"{python_bin}" -m pip install --target "{lib}" --upgrade mitmproxy'

    def degraded() -> None:
        ctx.complete({
            "success": False,
            "degraded": True,
            "manual_command": manual_command,
            "lib_path": lib,
            "python_bin": python_bin,
        })

    if not _pip_available():
        degraded()
        return

    code = _pip_install(lib, ctx.log)
    if code != 0:
        degraded()
        return

    marker_dir = os.path.join(runtime, "mitmproxy")
    os.makedirs(marker_dir, exist_ok=True)
    marker = os.path.join(marker_dir, "PYTHON_MARKER")
    with open(marker, "w", encoding="utf-8") as f:
        f.write(f"{sys.version_info[0]}.{sys.version_info[1]}")

    ctx.complete({"success": True, **traffic_status_impl()})


API_MAP = {
    "automation.run": run_automation,
    "automation.traffic_status": traffic_status,
    "automation.ime_status": ime_status,
    "automation.install_ca": install_ca,
    "automation.install_mitmproxy": install_mitmproxy,
}
