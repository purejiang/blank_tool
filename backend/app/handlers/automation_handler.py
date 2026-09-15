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
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, build_opener, urlopen

from app.automation.adb import run_adb
from app.automation.input import adb_ime_installed
from app.automation.input import ime_status as ime_status_impl
from app.automation.orchestrator import run as run_orchestration
from app.automation.traffic import status as traffic_status_impl
from app.automation.traffic import any_capture_active
from app.automation.traffic import ca_cert_path
from app.automation.traffic import install_ca as install_ca_impl
from app.common.decorators import logs_errors, streaming
from app.common.exceptions import ToolException
from app.common.stream_context import StreamContext
from app.utils.env import get_cache_dir, get_runtime_dir
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


ADBKEYBOARD_URL = "https://github.com/senzhk/ADBKeyBoard/raw/master/ADBKeyBoard.apk"

# Download constants — inline copy of download_handler's retry pattern
# (its private helpers are intentionally NOT imported).
_DL_MAX_RETRIES = 3      # total attempts, including the first
_DL_BACKOFF_BASE = 1.0   # seconds, doubles per retry
_DL_CHUNK = 8192
_DL_CONNECT_TIMEOUT = 30


def _friendly_reason(reason, use_proxy=False):
    """Turn a low-level connection error into an actionable message.

    Inline copy of download_handler's mapping (URLError / timeout / 404 /
    SSL → human guidance); the handler module's privates are never imported.
    """
    text = str(reason)
    lowered = text.lower()
    if isinstance(reason, ConnectionRefusedError) or "10061" in text or "refused" in lowered:
        if use_proxy:
            proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
            if proxy:
                return (
                    f"连接被拒绝（{text}）。"
                    f"常见原因：代理 {proxy} 未启动或已退出；"
                    f"可在系统/Shell 中关闭 HTTPS_PROXY/HTTP_PROXY 后重试。"
                )
        return (
            f"连接被拒绝（{text}）。"
            f"目标地址未监听端口，请确认网络或稍后重试。"
        )
    if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in lowered:
        return f"下载超时（{text}）。网络较慢或服务器无响应，已自动重试。"
    if "404" in lowered or "not found" in lowered:
        return f"资源不存在（{text}）。下载地址可能已失效，请检查仓库发布页。"
    if "certificate" in lowered or "ssl" in lowered:
        return f"证书校验失败（{text}）。请检查系统时间或网络代理设置。"
    return text


def _cleanup_partial(dest_path):
    """Best-effort removal of a partial download after a terminal failure."""
    try:
        if os.path.exists(dest_path):
            os.remove(dest_path)
    except OSError as e:
        logger.warning(f"Failed to remove partial download '{dest_path}': {e}")


def _download_apk(dest: str, on_progress, on_log) -> None:
    """Download ADBKeyBoard.apk to ``dest`` (stdlib urllib only).

    Reproduces download_handler's structure: up to 3 attempts with
    exponential backoff for transient errors, proxy fallback on retry
    (direct connection when the env proxy is off or died), chunked read
    with a running speed/percent computation, and friendly terminal errors.
    Raises on terminal failure — the handler turns that into the error
    event with the URL + local-APK hint.
    """
    url = ADBKEYBOARD_URL
    use_proxy = bool(os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"))
    for attempt in range(1, _DL_MAX_RETRIES + 1):
        # OFF: always direct. ON: first attempt via the env proxy, later
        # attempts fall back to a direct connection.
        bypass_now = (not use_proxy) or (attempt > 1)
        opener = build_opener(ProxyHandler({})) if bypass_now else None
        try:
            req = Request(url, headers={"User-Agent": "BlankTool/1.0"})
            resp = (
                opener.open(req, timeout=_DL_CONNECT_TIMEOUT)
                if opener
                else urlopen(req, timeout=_DL_CONNECT_TIMEOUT)
            )
            total = int(resp.headers.get("Content-Length", 0) or 0)
            downloaded = 0
            start_time = time.time()
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(_DL_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    elapsed = time.time() - start_time
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    pct = min(round(downloaded / total * 100), 99) if total > 0 else 0
                    on_progress({
                        "progress": pct,
                        "downloaded": downloaded,
                        "total": total,
                        "speed": speed,
                    })
            resp.close()
            on_log(f"ADBKeyBoard.apk 下载完成：{dest}（{downloaded} 字节）")
            return
        except HTTPError as e:
            logger.error(f"ADBKeyBoard download HTTP error: {e.code} {e.reason}")
            _cleanup_partial(dest)
            raise RuntimeError(f"下载失败: HTTP {e.code} {e.reason}")
        except (URLError, socket.timeout, TimeoutError) as e:
            if attempt < _DL_MAX_RETRIES:
                on_log(
                    f"下载尝试 {attempt}/{_DL_MAX_RETRIES} 失败："
                    f"{getattr(e, 'reason', e)}，将自动重试"
                )
                time.sleep(_DL_BACKOFF_BASE * (2 ** (attempt - 1)))
                continue
            _cleanup_partial(dest)
            raise RuntimeError(
                f"下载失败: {_friendly_reason(getattr(e, 'reason', e), use_proxy)}"
            )
        except Exception as e:
            logger.error(f"ADBKeyBoard download error: {e}")
            _cleanup_partial(dest)
            raise RuntimeError(f"下载失败: {e}")


@streaming
@logs_errors("AutomationHandler")
def install_ime(params, stream_handler):
    """Install ADBKeyBoard on one device (streaming: download → install → verify).

    Optional ``apk_path`` switches to the offline local-APK mode: the GitHub
    download is skipped entirely. The download retries like download.file;
    a terminal download failure points the user at the local-APK fallback
    instead of a dead end.
    """
    ctx = StreamContext("automation", stream_handler)
    device_id = str(params.get("device_id") or "").strip()
    if not device_id:
        ctx.error("device_id is required")
        return

    apk_path = str(params.get("apk_path") or "").strip()
    if apk_path:
        if not os.path.isfile(apk_path):
            ctx.error(f"本地 APK 不存在：{apk_path}，请重新选择有效的 APK 文件")
            return
        path = apk_path
    else:
        dest = os.path.join(get_cache_dir(), "tools", "ADBKeyBoard.apk")
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        def on_progress(info: dict) -> None:
            stream_handler({"type": "progress", "payload": info})

        ctx.log(f"开始下载 ADBKeyBoard.apk：{ADBKEYBOARD_URL}")
        try:
            _download_apk(dest, on_progress, ctx.log)
        except Exception as e:
            logger.warning(f"ADBKeyBoard download failed: {e}")
            ctx.error(
                f"ADBKeyBoard.apk 下载失败：{e}。下载地址：{ADBKEYBOARD_URL}；"
                f"离线或网络受限时，可在弹窗选择本地 APK 安装"
            )
            return
        path = dest

    ctx.log(f"开始安装 APK：{path}")
    r = run_adb(device_id, ["install", "-r", path])
    output = ((r.get("stdout") or "") + "\n" + (r.get("stderr") or "")).strip()
    for line in output.splitlines():
        if line.strip():
            ctx.log(line.strip())
    success = r.get("returncode", 1) == 0

    installed_now = adb_ime_installed(device_id)
    ctx.log(f"ADBKeyBoard 校验：{'已安装' if installed_now else '未检测到'}")
    ctx.complete({"success": success, **ime_status_impl(device_id)})


API_MAP = {
    "automation.run": run_automation,
    "automation.traffic_status": traffic_status,
    "automation.ime_status": ime_status,
    "automation.install_ca": install_ca,
    "automation.install_mitmproxy": install_mitmproxy,
    "automation.install_ime": install_ime,
}
