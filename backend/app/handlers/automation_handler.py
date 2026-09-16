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
from typing import Optional
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
from app.automation.traffic import recover_stale_capture as recover_stale_capture_impl
from app.common.decorators import logs_errors, streaming
from app.common.exceptions import ToolException
from app.common.stream_context import StreamContext
from app.common.task_manager import TaskManager
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

    A FAILED install keeps the impl's ``{success: false, error}`` shape (the
    modal renders ``error`` verbatim) but appends the likely cause: an
    unreachable device and a read-only ``/system`` produce the same generic
    "adb push CA failed" from the impl, and the second one is the common case
    on a stock device.
    """
    device_id = str(params.get("device_id") or "").strip()
    if not device_id:
        raise ToolException("device_id is required")
    if not os.path.isfile(ca_cert_path()):
        raise ToolException("CA cert not generated yet — run one capture first")
    result = install_ca_impl(device_id)
    if not isinstance(result, dict) or result.get("success"):
        return result
    state = _device_state(device_id)
    reason = str(result.get("error") or "")
    if state != "device":
        hint = f"设备 {device_id} 当前不可用（status={state or 'offline'}），请先连接设备"
    else:
        hint = (
            "需要 root 且 /system 可写（MuMu 12 等系统级 root 可成功）。"
            "只影响 HTTPS 解密，HTTP 抓包不受影响"
        )
    return {**result, "error": f"{reason} —— {hint}", "device_state": state or "offline"}


def _device_state(device_id: str) -> str:
    """``adb get-state`` for a device (``device`` / ``offline`` / ``unknown``).

    Never raises: a missing or broken adb is reported as ``unknown`` — this is
    a diagnostic hint, not a gate.
    """
    try:
        r = run_adb(device_id, ["get-state"])
        out = ((r.get("stdout") or "") + " " + (r.get("stderr") or "")).strip()
    except Exception:
        return "unknown"
    if (r.get("stdout") or "").strip() == "device":
        return "device"
    low = out.lower()
    if "unauthorized" in low:
        return "unauthorized"
    if "offline" in low:
        return "offline"
    if "not found" in low or "no devices" in low or "device not found" in low:
        return "disconnected"
    return out.splitlines()[0].strip() if out else "unknown"


@logs_errors("AutomationHandler")
def traffic_reset(params, stream_handler=None):
    """Undo device-side capture wiring left behind by a killed backend.

    Idempotent repair for the one failure mode the user cannot fix from the
    UI: a capture in flight when the app was force-closed leaves the device's
    ``global http_proxy`` pointing at a dead local proxy (device offline) and
    an orphaned mitmdump holding the port. ``device_id`` is optional — empty
    recovers every device recorded in the registry. Never raises on an
    offline device; per-device outcome is reported in ``restored``.
    """
    device_id = str(params.get("device_id") or "").strip()
    return recover_stale_capture_impl(device_id or None)


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


def _pip_install(lib_path: str, on_line, task_id: str = "") -> int:
    """``pip install --target`` mitmproxy into ``lib_path``.

    Streams every stdout/stderr line through ``on_line``. Returns the exit
    code; ANY exception (spawn failure, broken pipe, ...) counts as a
    non-zero code so the caller degrades to the manual command.

    ``task_id`` registers the pip process in TaskManager's holder so the UI's
    cancel button can actually terminate it — otherwise "取消" only took effect
    once pip had finished (minutes on a slow link).
    """
    if task_id:
        # Register BEFORE spawning so `cancel()`'s "wait up to 2s for the
        # process" branch can see it appear (see TaskManager.cancel).
        # `register()` REPLACES an existing entry, so it must be skipped when
        # the @streaming wrapper already registered this task — overwriting it
        # would drop the stop_event and make `ctx.is_cancelled()` never fire.
        tasks = TaskManager()
        if not tasks.is_registered(task_id):
            tasks.register(task_id)
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
    if task_id:
        holder = TaskManager().get_process_holder(task_id)
        if holder is not None:
            holder["process"] = proc
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


def _write_python_marker(runtime: str) -> None:
    """Stamp ``<runtime>/mitmproxy/PYTHON_MARKER`` with this interpreter's X.Y.

    Writes through a temp file + ``os.replace`` so a failed stamp can never
    leave a PARTIAL marker behind: readers see the old content or the new,
    never in-between (a truncated "3.1" of "3.11" would fake a version
    mismatch). A leftover ``.tmp`` file is read by no probe.
    """
    marker_dir = os.path.join(runtime, "mitmproxy")
    os.makedirs(marker_dir, exist_ok=True)
    marker = os.path.join(marker_dir, "PYTHON_MARKER")
    tmp = f"{marker}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(f"{sys.version_info[0]}.{sys.version_info[1]}")
    os.replace(tmp, marker)


@streaming
@logs_errors("AutomationHandler")
def install_mitmproxy(params, stream_handler):
    """Install mitmproxy into the bundled runtime via pip (streaming).

    Order matters: refuse while a capture runs (Windows locks mitmdump's
    .pyd/.dll), bail without a runtime dir, then probe pip. Any failure
    — pip probe, pip install, or the finalize tail (marker write / status
    build) — degrades to a copy-pasteable manual command with both paths
    double-quoted (space-safe). Never generates the CA; the first capture
    run does that.
    """
    ctx = StreamContext("automation", stream_handler)

    if any_capture_active():
        ctx.error("请先停止运行中的抓包再安装")
        return

    task_id = str(params.get("task_id") or "")
    if ctx.is_cancelled():
        ctx.cancelled({"task_id": task_id})
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

    code = _pip_install(lib, ctx.log, task_id=task_id)
    if ctx.is_cancelled():
        # pip itself is killed through the task's process holder; report the
        # cancel instead of the (inevitable, misleading) non-zero exit code.
        ctx.log("安装已取消")
        ctx.cancelled({"task_id": task_id})
        return
    if code != 0:
        degraded()
        return

    try:
        _write_python_marker(runtime)
        status = traffic_status_impl()
    except Exception as e:
        # Plan contract: ANY failure degrades. pip exited 0, but a finalize
        # blow-up (marker stamp / status build) must still hand the user the
        # copy-pasteable manual command instead of a bare error event.
        # Exception only: KeyboardInterrupt/SystemExit are control flow.
        logger.error(f"mitmproxy install finalize failed: {e}", exc_info=True)
        degraded()
        return

    ctx.complete({"success": True, **status})


# ADBKeyBoard download sources, in priority order.
#
# The upstream repo RENAMED the file (`ADBKeyBoard.apk` → `ADBKeyboard.apk`),
# which made the single hard-coded URL return HTTP 404 and left the installer
# with no way forward but the local-APK picker. A list of independent
# locations — repo file first, then the two release assets — survives that
# kind of rename; `BT_ADBKEYBOARD_URL` overrides it for a mirror/offline
# deployment. Every candidate must still look like a real APK (see
# ``_looks_like_apk``): a captive portal or proxy error page answers 200 with
# HTML, and installing that would fail as a corrupt APK.
ADBKEYBOARD_URLS = (
    "https://raw.githubusercontent.com/senzhk/ADBKeyBoard/master/ADBKeyboard.apk",
    "https://github.com/senzhk/ADBKeyBoard/releases/download/v2.5-dev/keyboardservice-debug.apk",
    "https://github.com/senzhk/ADBKeyBoard/releases/download/v2.4-dev/keyboardservice-debug.apk",
)
# Kept as the canonical first choice: referenced by log/error messages
# (including the "download this yourself" hint) and by the contract tests.
ADBKEYBOARD_URL = ADBKEYBOARD_URLS[0]

# ZIP/APK local-file-header magic; an APK is a ZIP.
_APK_MAGIC = b"PK\x03\x04"


def adbkeyboard_urls() -> tuple:
    """Candidate URLs, with ``BT_ADBKEYBOARD_URL`` as an override.

    An override replaces the list entirely (deliberate user intent: point at
    an internal mirror), rather than being tried after the public ones.
    """
    override = (os.environ.get("BT_ADBKEYBOARD_URL") or "").strip()
    if override:
        return (override,)
    return ADBKEYBOARD_URLS


def _looks_like_apk(path: str) -> bool:
    """True when ``path`` starts with the ZIP magic an APK must have."""
    try:
        with open(path, "rb") as f:
            return f.read(4) == _APK_MAGIC
    except OSError:
        return False


# Download constants — inline copy of download_handler's retry pattern
# (its private helpers are intentionally NOT imported).
_DL_MAX_RETRIES = 3      # total attempts per URL, including the first
_DL_BACKOFF_BASE = 1.0   # seconds, doubles per retry
_DL_CHUNK = 8192
_DL_CONNECT_TIMEOUT = 30

# HTTP codes that mean "this location will not work, try the next one" —
# retrying the same URL is pure waiting.
_DL_DEAD_URL_CODES = frozenset({400, 401, 403, 404, 410, 451})


class DownloadCancelled(Exception):
    """The user cancelled a download — NOT a failure.

    Kept distinct from the RuntimeError the retry paths raise so the caller
    reports "已取消" instead of a download error (and does not retry).
    """


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


def _truthy(value) -> bool:
    """Accept the JSON booleans the UI sends plus their string spellings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _valid_cached_apk(path: str) -> Optional[str]:
    """Return ``path`` when it is a usable cached APK, else ``None``.

    A zero-byte file (interrupted write, an empty placeholder) or one whose
    first bytes are not a ZIP is deleted and reported as missing. Handing it to
    ``adb install`` fails as a corrupt APK — which points the user at the wrong
    problem — and because the cache-reuse path is sticky, that failure would
    repeat on every attempt with no way out but a manual re-download.
    """
    try:
        if not os.path.isfile(path):
            return None
        if os.path.getsize(path) > 0 and _looks_like_apk(path):
            return path
    except OSError:
        return None
    logger.warning(f"removing unusable cached APK: {path}")
    _cleanup_partial(path)
    return None


def _download_apk(dest: str, on_progress, on_log, cancel_check=None) -> None:
    """Download ADBKeyBoard.apk to ``dest`` (stdlib urllib only).

    Writes to ``dest.part`` and renames on success: a hard kill mid-download
    must never leave a truncated file at the real path, where the cache-reuse
    path in ``install_ime`` would happily install it.

    ``cancel_check`` (optional callable) is polled before every chunk: a cancel
    during a slow download aborts within one chunk instead of running the full
    retry budget. A cancel raises ``DownloadCancelled`` and removes the part
    file; it is never recorded as a download failure.

    Every candidate in :func:`adbkeyboard_urls` is tried in order: a hard HTTP
    failure (404 after an upstream rename, 403, …) moves on to the NEXT
    location immediately, while a transient network error is retried up to
    ``_DL_MAX_RETRIES`` times with exponential backoff and proxy fallback
    (direct connection when the env proxy is off or died). A response that is
    not a real APK (captive-portal HTML, a proxy error page) is rejected and
    treated like a dead candidate.

    Raises ``RuntimeError`` with every attempted URL when all candidates fail —
    the handler turns that into the error event with the local-APK hint.
    """
    part = dest + ".part"
    use_proxy = bool(os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"))
    urls = adbkeyboard_urls()
    failures = []          # (url, reason) per exhausted candidate
    last_error = ""

    for url_index, url in enumerate(urls):
        for attempt in range(1, _DL_MAX_RETRIES + 1):
            # OFF: always direct. ON: first attempt via the env proxy, later
            # attempts fall back to a direct connection.
            bypass_now = (not use_proxy) or (attempt > 1)
            opener = build_opener(ProxyHandler({})) if bypass_now else None
            downloaded = 0
            try:
                req = Request(url, headers={"User-Agent": "BlankTool/1.0"})
                resp = (
                    opener.open(req, timeout=_DL_CONNECT_TIMEOUT)
                    if opener
                    else urlopen(req, timeout=_DL_CONNECT_TIMEOUT)
                )
                total = int(resp.headers.get("Content-Length", 0) or 0)
                start_time = time.time()
                with open(part, "wb") as f:
                    while True:
                        if cancel_check and cancel_check():
                            raise DownloadCancelled()
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
                if not _looks_like_apk(part):
                    # A 200 answer that is not a ZIP: a login/captive-portal
                    # page or a proxy notice. Installing it would fail later as
                    # a "corrupt APK", which points the user at the wrong thing.
                    _cleanup_partial(part)
                    reason = "返回内容不是 APK（可能是网络门户/代理拦截页）"
                    logger.warning(f"ADBKeyBoard download from {url}: {reason}")
                    on_log(f"地址不可用：{url}（{reason}）")
                    failures.append((url, reason))
                    break
                os.replace(part, dest)
                on_log(f"ADBKeyBoard.apk 下载完成：{dest}（{downloaded} 字节）")
                if url != ADBKEYBOARD_URL:
                    on_log(f"（来源：{url}）")
                return
            except DownloadCancelled:
                # Cancel is terminal for this download: no retry, no traceback.
                _cleanup_partial(part)
                raise
            except HTTPError as e:
                logger.error(f"ADBKeyBoard download HTTP error from {url}: {e.code} {e.reason}")
                _cleanup_partial(part)
                reason = f"HTTP {e.code} {e.reason}"
                if e.code in _DL_DEAD_URL_CODES:
                    # Dead location — the next candidate is the only thing that
                    # can help, so do not burn the retry budget on it.
                    on_log(f"地址不可用：{url}（{reason}），尝试下一个下载地址")
                    failures.append((url, reason))
                    break
                failures.append((url, reason))
                break
            except (URLError, socket.timeout, TimeoutError) as e:
                reason = _friendly_reason(getattr(e, "reason", e), use_proxy)
                if attempt < _DL_MAX_RETRIES:
                    on_log(
                        f"下载尝试 {attempt}/{_DL_MAX_RETRIES} 失败（{url}）："
                        f"{getattr(e, 'reason', e)}，将自动重试"
                    )
                    time.sleep(_DL_BACKOFF_BASE * (2 ** (attempt - 1)))
                    continue
                _cleanup_partial(part)
                failures.append((url, reason))
                last_error = reason
                if url_index + 1 < len(urls):
                    on_log(f"地址不可用：{url}（{reason}），尝试下一个下载地址")
                break
            except Exception as e:
                logger.error(f"ADBKeyBoard download error from {url}: {e}")
                _cleanup_partial(part)
                last_error = str(e)
                failures.append((url, last_error))
                if url_index + 1 < len(urls):
                    on_log(f"地址不可用：{url}（{last_error}），尝试下一个下载地址")
                break

    # Every candidate failed: report them ALL. The message is what the user
    # copies into a browser, so a single stale URL is not enough.
    tried = "；".join(f"{u}（{r}）" for u, r in failures) or ADBKEYBOARD_URL
    raise RuntimeError(f"下载失败: {last_error or '所有下载地址均不可用'}。已尝试：{tried}")


@streaming
@logs_errors("AutomationHandler")
def install_ime(params, stream_handler):
    """Install ADBKeyBoard on one device (streaming: download → install → verify).

    Optional ``apk_path`` switches to the offline local-APK mode: the GitHub
    download is skipped entirely. Optional ``redownload`` forces a fresh
    download even when a cached APK exists. The download retries like
    download.file; a terminal download failure points the user at the
    local-APK fallback instead of a dead end.

    A cached ``cache/tools/ADBKeyBoard.apk`` is REUSED: the file is a fixed
    release asset, and re-fetching ~1 MB on every install attempt made a
    flaky connection block an otherwise offline-capable flow. A zero-byte
    cache entry is treated as missing (and removed).
    """
    ctx = StreamContext("automation", stream_handler)
    device_id = str(params.get("device_id") or "").strip()
    if not device_id:
        ctx.error("device_id is required")
        return
    task_id = params.get("task_id")
    # Cancellation: `request.cancel` sets the stream's stop_event, so a cancel
    # can land at any of the three boundaries below (download / install /
    # verify). Emitting `cancelled` (not `complete`) is what makes the renderer
    # stop waiting instead of holding the install open for the idle timeout.
    if ctx.is_cancelled():
        ctx.cancelled({"task_id": str(task_id or ""), "device_id": device_id})
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
        redownload = _truthy(params.get("redownload"))
        cached = _valid_cached_apk(dest)

        if cached is not None and not redownload:
            ctx.log(f"使用已缓存的 APK：{cached}（{os.path.getsize(cached)} 字节）")
            path = cached
        else:
            def on_progress(info: dict) -> None:
                stream_handler({"type": "progress", "payload": info})

            ctx.log(f"开始下载 ADBKeyBoard.apk：{ADBKEYBOARD_URL}")
            try:
                _download_apk(dest, on_progress, ctx.log, cancel_check=ctx.is_cancelled)
            except DownloadCancelled:
                ctx.log("下载已取消")
                ctx.cancelled({"task_id": str(task_id or ""), "device_id": device_id})
                return
            except Exception as e:
                logger.warning(f"ADBKeyBoard download failed: {e}")
                # A broken cache entry must not poison every later attempt.
                _cleanup_partial(dest)
                ctx.error(
                    f"ADBKeyBoard.apk 下载失败：{e}；默认下载地址：{ADBKEYBOARD_URL}；"
                    f"离线或网络受限时，可在弹窗选择本地 APK 安装，"
                    f"或用 BT_ADBKEYBOARD_URL 指向内网镜像"
                )
                return
            path = dest

    if ctx.is_cancelled():
        ctx.cancelled({"task_id": str(task_id or ""), "device_id": device_id})
        return

    ctx.log(f"开始安装 APK：{path}")
    r = run_adb(device_id, ["install", "-r", path])
    output = ((r.get("stdout") or "") + "\n" + (r.get("stderr") or "")).strip()
    for line in output.splitlines():
        if line.strip():
            ctx.log(line.strip())
    adb_ok = r.get("returncode", 1) == 0

    if ctx.is_cancelled():
        ctx.log("已取消（APK 安装命令已执行，请确认设备上的安装结果）")
        ctx.cancelled({"task_id": str(task_id or ""), "device_id": device_id})
        return

    installed_now = adb_ime_installed(device_id)
    ctx.log(f"ADBKeyBoard 校验：{'已安装' if installed_now else '未检测到'}")
    # `adb install` returning 0 is NOT proof the IME is usable: a wrong APK
    # picked via apk_path installs fine and still leaves the device without
    # ADBKeyBoard, which used to be reported as success and then failed at the
    # first non-ASCII input.
    success = adb_ok and bool(installed_now)
    if adb_ok and not installed_now:
        ctx.log("[FAIL] APK 安装命令成功，但设备输入法列表里没有 ADBKeyBoard —— "
                "请确认安装的是 ADBKeyBoard.apk")
    ctx.complete({"success": success, **ime_status_impl(device_id)})


API_MAP = {
    "automation.run": run_automation,
    "automation.traffic_status": traffic_status,
    "automation.ime_status": ime_status,
    "automation.install_ca": install_ca,
    "automation.install_mitmproxy": install_mitmproxy,
    "automation.install_ime": install_ime,
    "automation.traffic_reset": traffic_reset,
}
