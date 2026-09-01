#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File download handler with streaming progress and resilient retries.

Uses urllib (stdlib only). Adds retry-with-backoff for transient network
errors (connection refused / timeouts) — the common "[WinError 10061]" cases —
and transparently falls back to a direct (no-proxy) connection when a
configured proxy is unreachable.
"""

import os
import re
import socket
import time
from urllib.request import urlopen, Request, ProxyHandler, build_opener
from urllib.error import URLError, HTTPError

from app.utils.logger import Logger
from app.utils.env import get_task_subdir, get_tasks_root
from app.common.decorators import streaming, logs_errors
from app.common.task_manager import TaskManager

logger = Logger.get_logger("DownloadHandler")

_MAX_RETRIES = 3          # 总尝试次数（含首次）
_BACKOFF_BASE = 1.0       # 退避基数（秒），逐次翻倍
_CHUNK = 8192
_CONNECT_TIMEOUT = 30


def _friendly_reason(reason, use_proxy=False):
    """Turn a low-level connection error into an actionable message."""
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
            f"目标地址未监听端口，请确认下载地址或服务已就绪。"
        )
    if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in lowered:
        return f"下载超时（{text}）。网络较慢或服务器无响应，已自动重试。"
    return text


def _task_input_dir(task_id):
    if task_id:
        return get_task_subdir(task_id, "input")
    # Fallback for no task_id: use a downloads dir next to tasks
    dl = os.path.join(os.path.dirname(get_tasks_root()), "downloads")
    os.makedirs(dl, exist_ok=True)
    return dl


def _sanitize_filename(name: str) -> str:
    """Strip path separators and reserved chars so a malicious or garbled
    filename cannot escape the task input directory (path traversal)."""
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = name.strip().strip('.')
    if not name:
        name = "download"
    return name


def _cleanup_partial(dest_path):
    """Best-effort removal of a partial download after a terminal failure.

    The cancelled paths already delete the file inline; this covers the error
    exits (HTTPError / retries exhausted / unexpected) which previously left
    half-written files behind in the task input dir.
    """
    try:
        if os.path.exists(dest_path):
            os.remove(dest_path)
    except OSError as e:
        logger.warning(f"Failed to remove partial download '{dest_path}': {e}")


@streaming
@logs_errors("DownloadHandler")
def download_file(params, stream_handler):
    url = params.get("url", "")
    filename = params.get("filename", "")
    task_id = params.get("task_id", "")

    if not url:
        stream_handler({
            "type": "error",
            "payload": {"message": "Missing URL"},
        })
        return

    if not filename:
        filename = url.rsplit("/", 1)[-1].split("?")[0] or "download"
    filename = _sanitize_filename(filename)

    dest_dir = _task_input_dir(params.get("task_id", ""))
    dest_path = os.path.join(dest_dir, filename)

    task_manager = TaskManager()

    # Explicit switch from the UI (params.use_proxy) takes priority. When absent,
    # fall back to detecting a configured proxy via env (legacy behavior).
    if "use_proxy" in params:
        use_proxy = bool(params["use_proxy"])
    else:
        use_proxy = bool(os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"))
    last_err = None

    for attempt in range(1, _MAX_RETRIES + 1):
        # OFF (use_proxy=False): always connect directly (never touch the env proxy).
        # ON  (use_proxy=True): first attempt uses the env proxy; later attempts
        #       fall back to a direct connection on transient failures.
        bypass_now = (not use_proxy) or (attempt > 1)
        opener = build_opener(ProxyHandler({})) if bypass_now else None
        try:
            req = Request(url, headers={"User-Agent": "BlankTool/1.0"})
            resp = opener.open(req, timeout=_CONNECT_TIMEOUT) if opener else urlopen(req, timeout=_CONNECT_TIMEOUT)

            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            start_time = time.time()

            with open(dest_path, "wb") as f:
                while True:
                    if task_id and task_manager.is_cancelled(task_id):
                        resp.close()
                        f.close()
                        try:
                            os.remove(dest_path)
                        except OSError:
                            pass
                        stream_handler({
                            "type": "cancelled",
                            "payload": {"task_id": task_id},
                        })
                        return

                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total > 0:
                        pct = min(round(downloaded / total * 100), 99)
                        elapsed = time.time() - start_time
                        speed = downloaded / elapsed if elapsed > 0 else 0
                        stream_handler({
                            "type": "progress",
                            "payload": {
                                "task_id": task_id,
                                "progress": pct,
                                "downloaded": downloaded,
                                "total": total,
                                "speed": speed,
                            },
                        })

            resp.close()

            if task_id and task_manager.is_cancelled(task_id):
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
                stream_handler({
                    "type": "cancelled",
                    "payload": {"task_id": task_id},
                })
                return

            stream_handler({
                "type": "complete",
                "payload": {
                    "task_id": task_id,
                    "file_path": dest_path,
                    "file_name": filename,
                    "size": downloaded,
                },
            })
            return

        except HTTPError as e:
            logger.error(f"Download HTTP error: {e.code} {e.reason}")
            _cleanup_partial(dest_path)
            stream_handler({
                "type": "error",
                "payload": {"task_id": task_id, "message": f"下载失败: HTTP {e.code} {e.reason}"},
            })
            return
        except (URLError, socket.timeout, TimeoutError) as e:
            last_err = e
            logger.warning(f"Download attempt {attempt}/{_MAX_RETRIES} failed: {getattr(e, 'reason', e)}")
            if attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
                continue
            _cleanup_partial(dest_path)
            stream_handler({
                "type": "error",
                "payload": {"task_id": task_id, "message": f"下载失败: {_friendly_reason(getattr(e, 'reason', e), use_proxy)}"},
            })
            return
        except Exception as e:
            logger.error(f"Download error: {e}")
            _cleanup_partial(dest_path)
            stream_handler({
                "type": "error",
                "payload": {"task_id": task_id, "message": str(e)},
            })
            return


API_MAP = {
    "download.file": download_file,
}
