#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File download handler with streaming progress.
Uses urllib (stdlib) — no external dependencies required.
"""

import os
import time
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from app.utils.logger import Logger
from app.utils.env import get_env, resolve_path
from app.common.decorators import streaming
from app.common.task_manager import TaskManager

logger = Logger.get_logger("DownloadHandler")


def _downloads_dir():
    cache_dir = get_env("BT_CACHE_DIR", "./cache")
    root = resolve_path(cache_dir)
    dl = os.path.join(root, "downloads")
    os.makedirs(dl, exist_ok=True)
    return dl


@streaming
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

    dest_dir = _downloads_dir()
    dest_path = os.path.join(dest_dir, filename)

    task_manager = TaskManager()

    try:
        req = Request(url, headers={"User-Agent": "BlankTool/1.0"})
        resp = urlopen(req, timeout=30)

        # Handle redirects (urlopen follows by default with HTTPRedirectHandler)
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

                chunk = resp.read(8192)
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

    except HTTPError as e:
        logger.error(f"Download HTTP error: {e.code} {e.reason}")
        stream_handler({
            "type": "error",
            "payload": {"task_id": task_id, "message": f"下载失败: HTTP {e.code} {e.reason}"},
        })
    except URLError as e:
        logger.error(f"Download URL error: {e.reason}")
        stream_handler({
            "type": "error",
            "payload": {"task_id": task_id, "message": f"下载失败: {e.reason}"},
        })
    except Exception as e:
        logger.error(f"Download error: {e}")
        stream_handler({
            "type": "error",
            "payload": {"task_id": task_id, "message": str(e)},
        })


API_MAP = {
    "download.file": download_file,
}
