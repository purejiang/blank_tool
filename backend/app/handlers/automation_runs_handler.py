#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automation run history handlers.

Every run writes ``report.json`` into its per-run directory under the
AUTOMATION root — ``{BT_AUTO_TASKS_DIR}/{task_id}/``, i.e. ``auto_tasks/`` as
a sibling of ``tasks/`` — with artifacts categorized into ``screenshots/``
``traffic/`` ``crash_logs/``. These handlers list / read / delete / prune
those run directories. Deletion removes the WHOLE run directory and is
containment-checked against the automation root.

Alongside the full ``report.json`` the orchestrator keeps a small
``summary.json`` index (written at run start as ``status: running`` and
rewritten at the end as ``finished``), so listing 100 runs no longer parses
100 full reports. It also makes interruptions visible: a directory whose
summary still says ``running`` while nothing is executing is a run the
backend was killed in the middle of — an ORPHAN. Orphans are listed (flagged
``orphan: true``) and can be deleted individually or by
``automation.prune_runs``; a run that IS executing right now can be neither
deleted nor pruned (see ``app.automation.runstate``).
"""

import base64
import gzip
import json
import os
import shutil
import time
import zlib

from app.automation import runstate
from app.utils.env import get_auto_tasks_root
from app.utils.logger import Logger

logger = Logger.get_logger("AutomationRunsHandler")

REPORT_NAME = "report.json"
SUMMARY_NAME = "summary.json"

# Fields the history list needs. Kept in sync with
# ``app.automation.orchestrator._SUMMARY_KEYS``.
SUMMARY_KEYS = (
    "kind", "task_id", "device_id", "package_name", "started_at", "finished_at",
    "started_ts", "finished_ts", "duration_ms", "success", "cancelled",
    "aborted_by_crash", "total", "passed", "failed", "run_dir",
)

LIST_LIMIT = 100
DEFAULT_TRAFFIC_LIMIT = 2000
# Scan caps. `read_run` serves the viewer a bounded slice of the capture log;
# a single run can otherwise hold hundreds of MB of jsonl. The HTML export
# asks for (almost) everything, so it passes a much larger budget.
DEFAULT_TRAFFIC_SCAN_BYTES = 8 * 1024 * 1024
EXPORT_TRAFFIC_SCAN_BYTES = 256 * 1024 * 1024
# `report.logs` is one entry per streamed log line: bounded by default so a
# long run cannot blow up the IPC payload, with the tail kept (the end of a
# run is what a report viewer looks at).
DEFAULT_LOG_LIMIT = 5000
_ORPHAN_SIZE_MAX_FILES = 5000


def _run_dir_for(task_id: str) -> str:
    """Resolve ``{auto_tasks_root}/{task_id}`` with containment checks.

    Script runs live in the automation root (``auto_tasks/``, a sibling of
    ``tasks/``), never inside ``tasks/``. Returns the real path; raises
    ``ValueError`` for bad ids / escapes.
    """
    task_id = str(task_id or "").strip()
    if not task_id or task_id in (".", ".."):
        raise ValueError("invalid task_id")
    if any(c in task_id for c in ("/", "\\",)) or ".." in task_id:
        raise ValueError(f"task_id contains invalid characters: {task_id}")
    root = os.path.realpath(get_auto_tasks_root())
    path = os.path.realpath(os.path.join(root, task_id))
    if path != root and not path.startswith(root + os.sep):
        raise ValueError("run dir outside tasks root")
    return path


def _read_report(run_dir: str) -> dict:
    with open(os.path.join(run_dir, REPORT_NAME), "r", encoding="utf-8") as f:
        report = json.load(f)
    return report if isinstance(report, dict) else {}


def _read_json_dict(path: str):
    """Load a JSON object, or ``None`` when missing / unreadable / not an object."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _iso(ts) -> str:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(float(ts)))
    except (TypeError, ValueError):
        return ""


def _dir_stats(path: str):
    """Bounded recursive size/file count (orphans have no report to read)."""
    total_size = 0
    total_files = 0
    for dirpath, _dirs, filenames in os.walk(path):
        for name in filenames:
            try:
                total_size += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
            total_files += 1
            if total_files >= _ORPHAN_SIZE_MAX_FILES:
                return total_size, total_files
    return total_size, total_files


def _project_summary(report: dict, fallback_id: str, run_dir: str) -> dict:
    """Pick the history-list fields out of a FULL report.json (legacy runs)."""
    entry = {k: report.get(k) for k in SUMMARY_KEYS}
    entry["task_id"] = entry.get("task_id") or fallback_id
    entry["run_dir"] = entry.get("run_dir") or run_dir
    entry["screenshot_count"] = len(report.get("screenshots") or [])
    return entry


def _index_run_dir(run_dir: str, name: str):
    """One history entry for ``run_dir``, or ``None`` when it is not a run.

    Resolution order — ``summary.json`` first (cheap), then the full
    ``report.json`` (legacy runs written before the index existed, and the
    killed-in-between case where the report landed but its summary rewrite did
    not), then "nothing indexable", which for a non-empty directory means an
    interrupted run: an orphan the storage UI can show and delete.
    """
    summary = _read_json_dict(os.path.join(run_dir, SUMMARY_NAME))
    # Any JSON object in `report.json` IS the run's report (only the
    # orchestrator writes into this root); the index file additionally has to
    # look like an index, otherwise it is treated as absent.
    if summary is not None and not (
        summary.get("kind") == "automation_run" or "status" in summary
    ):
        summary = None
    report = _read_json_dict(os.path.join(run_dir, REPORT_NAME))
    live = runstate.is_active(name) or runstate.is_active_dir(run_dir)

    if summary is not None:
        running = str(summary.get("status") or "") == "running"
        # A `running` marker with no live run means the backend died — UNLESS
        # the report is already on disk (killed between the two writes), in
        # which case the report is the truth.
        use_report = running and not live and report is not None
        if use_report:
            entry = _project_summary(report, name, run_dir)
            status = "finished"
        else:
            entry = {k: summary.get(k) for k in SUMMARY_KEYS}
            entry["task_id"] = entry.get("task_id") or name
            entry["run_dir"] = entry.get("run_dir") or run_dir
            entry.setdefault("screenshot_count", summary.get("screenshot_count") or 0)
            if running and live:
                status = "running"
            elif running:
                status = "interrupted"
                # Interrupted runs have no report to size them from, and the
                # storage UI wants to show what the leftover is worth.
                entry["size"], entry["files"] = _dir_stats(run_dir)
            else:
                status = "finished"
        entry.update(
            status=status,
            running=status == "running",
            interrupted=status == "interrupted",
            orphan=status == "interrupted",
        )
        return entry

    if report is not None:
        entry = _project_summary(report, name, run_dir)
        entry.update(
            status="running" if live else "finished",
            running=live,
            interrupted=False,
            orphan=False,
        )
        return entry

    size, files = _dir_stats(run_dir)
    if files == 0:
        return None  # empty leftover: nothing to show, nothing to delete
    mtime = 0.0
    try:
        mtime = os.path.getmtime(run_dir)
    except OSError:
        pass
    return {
        "kind": "automation_run",
        "task_id": name,
        "device_id": "",
        "package_name": "",
        "started_at": "",
        "finished_at": "",
        "started_ts": mtime or None,
        "finished_ts": None,
        "duration_ms": 0,
        "success": False,
        "cancelled": False,
        "aborted_by_crash": False,
        "total": 0,
        "passed": 0,
        "failed": 0,
        "screenshot_count": 0,
        "run_dir": run_dir,
        "mtime": mtime,
        "size": size,
        "files": files,
        # `status` is the coarse label (running / finished / interrupted);
        # `orphan` is the flag the UI acts on.
        "status": "interrupted",
        "running": False,
        "interrupted": True,
        "orphan": True,
    }


def _index_runs():
    """Every run dir under the automation root, newest first (uncapped)."""
    root = os.path.realpath(get_auto_tasks_root())
    with os.scandir(root) as it:  # OSError propagates to the handler
        entries = list(it)
    runs = []
    for entry in entries:
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue
        item = _index_run_dir(entry.path, entry.name)
        if item is None:
            continue
        mtime = item.get("mtime")
        if mtime is None:
            try:
                mtime = os.path.getmtime(entry.path)
            except OSError:
                mtime = 0.0
            item["mtime"] = mtime
        item["_sort"] = item.get("started_at") or _iso(mtime)
        runs.append(item)
    runs.sort(key=lambda r: (r.get("_sort") or "", r.get("task_id") or ""), reverse=True)
    return runs


def handle_list_runs(params, stream_handler):
    """Summaries of every automation run, newest first (max 100).

    ``orphans`` counts the interrupted / unindexable leftovers included in the
    same list, so the history view can badge them and the storage settings can
    offer a one-click cleanup.
    """
    try:
        runs = _index_runs()
    except OSError as e:
        return {"success": False, "runs": [], "orphans": 0, "total": 0, "error": str(e)}
    orphans = sum(1 for r in runs if r.get("orphan"))
    for r in runs:
        r.pop("_sort", None)
    return {
        "success": True,
        "runs": runs[:LIST_LIMIT],
        "total": len(runs),
        "orphans": orphans,
    }


def _read_traffic(jsonl_path: str, limit: int, max_bytes: int = DEFAULT_TRAFFIC_SCAN_BYTES) -> dict:
    """Parse the capture jsonl into lightweight request summaries.

    Only the fields the report viewer needs are kept (timestamps, method,
    URL, status); bodies and headers stay in the jsonl on disk so a run
    with thousands of requests doesn't blow up the IPC payload.

    ``max_bytes`` stops the scan on a huge capture: reading a 500 MB jsonl to
    answer "show me the first 2000 requests" is pure waste. When the budget is
    hit the result is marked ``truncated`` (``total`` becomes a lower bound),
    which the report viewer already renders as "请求列表已截断".
    """
    entries = []
    total = 0
    scanned = 0
    scan_limited = False
    if not jsonl_path or not os.path.isfile(jsonl_path):
        return {"entries": [], "total": 0, "truncated": False, "scan_limited": False}
    try:
        with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                scanned += len(line.encode("utf-8", errors="replace")) + 1
                if scanned > max_bytes:
                    scan_limited = True
                    break
                line = line.strip()
                if not line:
                    continue
                total += 1
                if len(entries) >= limit:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                entries.append({
                    "ts": rec.get("ts"),
                    "method": rec.get("method", ""),
                    "url": rec.get("url", ""),
                    "host": rec.get("host", ""),
                    "status": rec.get("status"),
                    "error": rec.get("error"),
                })
    except OSError as e:
        return {"entries": entries, "total": total, "truncated": False,
                "scan_limited": False, "error": str(e)}
    return {
        "entries": entries,
        "total": total,
        "truncated": scan_limited or total > len(entries),
        "scan_limited": scan_limited,
    }


_DEFLATE_RAW_WBITS = -zlib.MAX_WBITS


def _content_encoding(headers) -> str:
    """Content-Encoding 归一化（大小写不敏感；多值取第一个）。"""
    if not isinstance(headers, dict):
        return ""
    for key, value in headers.items():
        if str(key).lower() == "content-encoding":
            return str(value).split(",")[0].strip().lower()
    return ""


def _rescue_compressed_body(rec: dict) -> None:
    """历史抓包抢救：把压缩体就地还原成文本（就地修改 rec）。

    早期 traffic_addon 用 ``raw_content`` 落盘 —— gzip/deflate 响应存的是**线上
    压缩字节**，读取时 UTF-8 解码失败被判成二进制（b64），表现为「响应体都是二进制
    内容」。这里按 content-encoding 解压，能解成 UTF-8 的换成 ``{"text": ...}``
    并标注 ``decompressed``，使存量抓包在查看器与导出里都恢复可读。

    只覆盖 stdlib 能解的 gzip / deflate；``br`` 无标准库支持，需重抓
    （traffic_addon 已改为使用解码后的 ``.content``）。解不开或非 UTF-8 时保持原样。
    """
    for body_key, headers_key in (("req_body", "req_headers"), ("resp_body", "resp_headers")):
        body = rec.get(body_key)
        if not isinstance(body, dict) or "b64" not in body:
            continue
        encoding = _content_encoding(rec.get(headers_key))
        if encoding not in ("gzip", "x-gzip", "deflate"):
            continue
        try:
            raw = base64.b64decode(str(body["b64"]))
            if encoding in ("gzip", "x-gzip"):
                data = gzip.decompress(raw)
            else:
                try:
                    data = zlib.decompress(raw)              # 规范：zlib 包装
                except zlib.error:
                    data = zlib.decompress(raw, _DEFLATE_RAW_WBITS)  # 裸 deflate（部分服务端）
        except Exception:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        rec[body_key] = {"text": text, "decompressed": encoding}


def _read_traffic_full(jsonl_path: str, limit: int,
                       max_bytes: int = EXPORT_TRAFFIC_SCAN_BYTES) -> dict:
    """Parse the capture jsonl into FULL records (headers + bodies).

    Companion to ``_read_traffic`` — same file, same order, same limit
    semantics — but keeps every field. Used ONLY by the HTML export, which
    embeds per-request detail into a self-contained document; ``read_run``
    keeps serving lightweight summaries so IPC payloads stay small.
    """
    entries = []
    total = 0
    scanned = 0
    scan_limited = False
    if not jsonl_path or not os.path.isfile(jsonl_path):
        return {"entries": [], "total": 0, "truncated": False, "scan_limited": False}
    try:
        with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                scanned += len(line.encode("utf-8", errors="replace")) + 1
                if scanned > max_bytes:
                    scan_limited = True
                    break
                line = line.strip()
                if not line:
                    continue
                total += 1
                if len(entries) >= limit:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                _rescue_compressed_body(rec)
                entries.append(rec)
    except OSError as e:
        return {"entries": entries, "total": total, "truncated": False,
                "scan_limited": False, "error": str(e)}
    return {
        "entries": entries,
        "total": total,
        "truncated": scan_limited or total > len(entries),
        "scan_limited": scan_limited,
    }


def _bounded_int(value, default: int, low: int = 0, high: int = 100000) -> int:
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError):
        return default


def handle_read_run(params, stream_handler):
    """Full report.json of one run (+ lightweight request log by default).

    ``traffic_limit`` caps how many request summaries are returned; the
    viewer asks for a bounded slice, the HTML export embeds them all.
    ``include_logs`` / ``log_limit`` do the same for ``report.logs`` (one
    entry per streamed log line): the LAST ``log_limit`` lines are returned
    — a report viewer reads the tail of a run — together with
    ``log_total`` so the UI can say how much it is showing.
    """
    try:
        run_dir = _run_dir_for(params.get("task_id", ""))
    except ValueError as e:
        return {"success": False, "report": None, "error": str(e)}
    if not os.path.isfile(os.path.join(run_dir, REPORT_NAME)):
        return {"success": False, "report": None, "error": "report not found"}
    try:
        report = _read_report(run_dir)
    except (OSError, ValueError) as e:
        return {"success": False, "report": None, "error": str(e)}

    limit = _bounded_int(params.get("traffic_limit"), DEFAULT_TRAFFIC_LIMIT, 0, 20000)
    traffic = _read_traffic(report.get("traffic_log") or "", limit)
    report["traffic"] = traffic["entries"]
    report["traffic_total"] = traffic["total"]
    report["traffic_truncated"] = traffic["truncated"]

    logs = report.get("logs")
    if not isinstance(logs, list):
        logs = []
    report["log_total"] = len(logs)
    if params.get("include_logs") is False:
        report["logs"] = []
        report["logs_included"] = False
    else:
        log_limit = _bounded_int(params.get("log_limit"), DEFAULT_LOG_LIMIT, 0, 200000)
        # 0 = unlimited (explicit opt-in); otherwise keep the tail.
        report["logs"] = logs if not log_limit else logs[-log_limit:]
        report["logs_included"] = True
    report["logs_truncated"] = len(report["logs"]) < len(logs)
    return {"success": True, "report": report}



def handle_traffic_detail(params, stream_handler):
    """Full jsonl record (headers + bodies) for ONE captured request.

    ``index`` is the 0-based line number in the capture jsonl — the same
    order ``read_run`` returns request summaries in, so the viewer can map
    a summary row straight to its record. Bodies/headers are deliberately
    NOT inlined into ``read_run`` (a run with thousands of requests would
    blow up the IPC payload); the viewer pulls one record at a time.

    Body fields keep the addon's wire shapes: ``{"text": ...}`` when
    UTF-8, ``{"b64": ...}`` for binary, ``{"truncated": true, "size": N}``
    past the 16 KiB per-body cap.
    """
    try:
        run_dir = _run_dir_for(params.get("task_id", ""))
    except ValueError as e:
        return {"success": False, "record": None, "error": str(e)}
    traffic_log = ""
    try:
        traffic_log = _read_report(run_dir).get("traffic_log") or ""
    except (OSError, ValueError):
        pass
    if not traffic_log or not os.path.isfile(traffic_log):
        return {"success": False, "record": None, "error": "traffic log not found"}
    try:
        index = int(params.get("index", -1))
    except (TypeError, ValueError):
        index = -1
    if index < 0:
        return {"success": False, "record": None, "error": "invalid index"}
    try:
        with open(traffic_log, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i < index:
                    continue
                line = line.strip()
                if not line:
                    return {"success": False, "record": None,
                            "error": f"record {index} is empty"}
                try:
                    rec = json.loads(line)
                except ValueError as e:
                    return {"success": False, "record": None,
                            "error": f"record {index} is corrupt: {e}"}
                if isinstance(rec, dict):
                    _rescue_compressed_body(rec)
                return {"success": True,
                        "record": rec if isinstance(rec, dict) else None}
        return {"success": False, "record": None, "error": "index out of range"}
    except OSError as e:
        return {"success": False, "record": None, "error": str(e)}


def _delete_run_dir(run_dir: str) -> dict:
    """Remove one run dir. Refuses while its run is executing in this process.

    Returns ``{"ok": bool, "bytes": int, "error": str|None}``. The size is
    measured BEFORE removal so callers can report how much space was freed.
    """
    if runstate.is_active_dir(run_dir):
        return {"ok": False, "bytes": 0,
                "error": "run is still executing in this session"}
    size, _files = _dir_stats(run_dir)
    try:
        shutil.rmtree(run_dir, ignore_errors=False)
    except Exception as e:
        logger.warning(f"failed to delete run dir '{run_dir}': {e}")
        return {"ok": False, "bytes": 0, "error": str(e)}
    logger.info(f"deleted automation run dir: {run_dir}")
    return {"ok": True, "bytes": size, "error": None}


def handle_delete_run(params, stream_handler):
    """Delete the WHOLE run directory (artifacts + report).

    Orphan directories (a run the backend was killed in the middle of) are
    deletable too — they are exactly the ones the user needs to reclaim. A run
    that is executing right now is NOT: its script is still writing artifacts
    into that directory.
    """
    try:
        run_dir = _run_dir_for(params.get("task_id", ""))
    except ValueError as e:
        return {"deleted": False, "error": str(e)}
    if not os.path.isdir(run_dir):
        return {"deleted": False, "error": "run dir not found"}
    out = _delete_run_dir(run_dir)
    if not out["ok"]:
        return {"deleted": False, "error": out["error"]}
    return {"deleted": True, "size": out["bytes"]}


def handle_prune_runs(params, stream_handler):
    """Reclaim run storage by rule instead of one directory at a time.

    Rules (all optional, ANDed — a run is only deleted when every enabled rule
    agrees) :
      * ``keep_last``        keep the N most recent runs (orphans count).
      * ``older_than_days``  only runs older than N days (by started_at, or
                             by mtime for orphans, which have no start time).
      * ``orphans_only``     restrict everything to interrupted leftovers.
      * ``dry_run``          report what WOULD be deleted, delete nothing.

    With no rule enabled the call is refused outright: a stray request must
    never be able to wipe the whole history. Runs executing right now are
    always skipped.
    """
    keep_last = params.get("keep_last")
    older_days = params.get("older_than_days")
    orphans_only = bool(params.get("orphans_only"))
    dry_run = bool(params.get("dry_run"))

    keep = None
    if keep_last is not None and str(keep_last).strip() != "":
        keep = _bounded_int(keep_last, -1, 0, 100000)
        if keep < 0:
            return {"success": False, "error": "invalid keep_last"}
    cutoff = None
    if older_days is not None and str(older_days).strip() != "":
        try:
            days = float(older_days)
        except (TypeError, ValueError):
            return {"success": False, "error": "invalid older_than_days"}
        if days < 0:
            return {"success": False, "error": "invalid older_than_days"}
        cutoff = time.time() - days * 86400.0

    if keep is None and cutoff is None and not orphans_only:
        return {
            "success": False,
            "error": "no pruning rule given (keep_last / older_than_days / orphans_only)",
        }

    try:
        runs = _index_runs()
    except OSError as e:
        return {"success": False, "error": str(e)}

    candidates = [r for r in runs if not r.get("running")]
    skipped_active = len(runs) - len(candidates)
    if orphans_only:
        candidates = [r for r in candidates if r.get("orphan")]
    if cutoff is not None:
        def _ts(r):
            ts = r.get("started_ts")
            try:
                return float(ts)
            except (TypeError, ValueError):
                return float(r.get("mtime") or 0.0)
        candidates = [r for r in candidates if _ts(r) and _ts(r) < cutoff]
    if keep is not None:
        # `runs` is newest-first, so the newest `keep` entries are protected
        # regardless of the other filters.
        protected = {r.get("task_id") for r in runs[:keep]}
        candidates = [r for r in candidates if r.get("task_id") not in protected]

    deleted = []
    errors = []
    freed = 0
    for r in candidates:
        item = {"task_id": r.get("task_id"), "orphan": bool(r.get("orphan"))}
        if dry_run:
            item["size"] = r.get("size")
            deleted.append(item)
            continue
        out = _delete_run_dir(r.get("run_dir") or "")
        if out["ok"]:
            item["size"] = out["bytes"]
            freed += out["bytes"]
            deleted.append(item)
        else:
            errors.append({"task_id": r.get("task_id"), "error": out["error"]})

    logger.info(
        f"prune_runs: {'would delete' if dry_run else 'deleted'} "
        f"{len(deleted)} run(s), {len(errors)} error(s), freed={freed}B "
        f"(keep_last={keep}, older_than_days={older_days}, orphans_only={orphans_only})"
    )
    return {
        "success": True,
        "dry_run": dry_run,
        "deleted": deleted[:200],
        "deleted_count": len(deleted),
        "kept": len(runs) - len(deleted),
        "skipped_active": skipped_active,
        "freed_bytes": freed,
        "errors": errors[:50],
        "error_count": len(errors),
    }


# ---------------------------------------------------------------- export --
# The exported document is a single self-contained HTML file: screenshots are
# inlined as base64, and every captured request embeds its headers + bodies in
# a collapsible detail row (budget-capped, see MAX_BODY_EMBED_BYTES), so the
# report can be moved anywhere (mail, ticket, shared drive) without breaking.
MAX_EMBED_BYTES = 32 * 1024 * 1024  # cap on inlined screenshot payload
MAX_BODY_EMBED_BYTES = 16 * 1024 * 1024  # cap on inlined req/resp bodies


def _esc(v) -> str:
    return (str(v if v is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _data_uri(path: str, budget: dict) -> str:
    """Inline a screenshot as base64, honouring the total size budget."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return ""
    if budget["used"] + size * 1.37 > MAX_EMBED_BYTES:
        budget["skipped"] += 1
        return ""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return ""
    budget["used"] += len(raw) * 1.37
    ext = os.path.splitext(path)[1].lstrip(".").lower() or "png"
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _fmt_ts(ts) -> str:
    try:
        return time.strftime("%H:%M:%S", time.localtime(float(ts)))
    except (TypeError, ValueError):
        return ""


def _fmt_dur(ms) -> str:
    try:
        n = int(ms)
    except (TypeError, ValueError):
        return "-"
    return f"{n / 1000:.1f}s" if n >= 1000 else f"{n}ms"


def _pretty_json(text: str) -> str:
    """Re-indent a JSON body for readability; non-JSON passes through."""
    try:
        return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    except Exception:
        return text


def _headers_pre(headers) -> str:
    if not isinstance(headers, dict) or not headers:
        return '<pre class="empty">（无）</pre>'
    text = "\n".join(f"{k}: {v}" for k, v in headers.items())
    return f"<pre>{_esc(text)}</pre>"


def _body_html(body, budget: dict) -> str:
    """Render one captured body for the exported HTML, honouring the budget.

    Body fields keep the addon's wire shapes: ``{"text": ...}`` (pretty-
    printed when it parses as JSON), ``{"b64": ...}`` (inline download
    link), or the truncation marker. Payload counts against
    MAX_BODY_EMBED_BYTES; over-budget bodies become a pointer to the run
    directory instead of silently bloating the file.
    """
    if not isinstance(body, dict) or not body:
        return '<pre class="empty">（无）</pre>'
    if "text" in body:
        text = str(body["text"])
        if budget["used"] + len(text) > MAX_BODY_EMBED_BYTES:
            budget["dropped"] += 1
            return '<pre class="empty">（超出内嵌体积上限，未包含 —— 完整数据见运行目录 traffic/*.jsonl）</pre>'
        budget["used"] += len(text)
        return f"<pre>{_esc(_pretty_json(text))}</pre>"
    if "b64" in body:
        b64 = str(body["b64"])
        size = len(b64) * 3 // 4
        if budget["used"] + len(b64) > MAX_BODY_EMBED_BYTES:
            budget["dropped"] += 1
            return '<pre class="empty">（二进制体，超出内嵌体积上限，未包含 —— 完整数据见运行目录 traffic/*.jsonl）</pre>'
        budget["used"] += len(b64)
        return (f'<pre class="empty">二进制内容（约 {size} 字节）：'
                f'<a href="data:application/octet-stream;base64,{b64}" download="body.bin">点此下载</a></pre>')
    if body.get("truncated"):
        return (f'<pre class="empty">（捕获时已截断 —— 原始大小 {body.get("size", 0)} 字节，'
                f'完整数据见运行目录 traffic/*.jsonl）</pre>')
    return '<pre class="empty">（无）</pre>'


def _req_detail_html(rec: dict, budget: dict) -> str:
    """Hidden <tr> under a request row: headers + bodies, toggled by click."""
    sections = [
        ('<div class="lb">请求头</div>' + _headers_pre(rec.get("req_headers"))),
        ('<div class="lb">请求体</div>' + _body_html(rec.get("req_body"), budget)),
        ('<div class="lb">响应头</div>' + _headers_pre(rec.get("resp_headers"))),
        ('<div class="lb">响应体</div>' + _body_html(rec.get("resp_body"), budget)),
    ]
    return ('<tr class="rdet" data-kind="req" style="display:none">'
            f'<td colspan="3">{"".join(sections)}</td></tr>')


def build_report_html(report: dict, traffic: list) -> str:
    """Render the whole run as one standalone HTML document."""
    shots_meta = report.get("shots_meta") or []
    shot_by_path = {}
    for m in shots_meta:
        if isinstance(m, dict) and m.get("path"):
            shot_by_path[m["path"]] = m

    budget = {"used": 0, "skipped": 0}
    # inlined req/resp bodies have their own budget, separate from screenshots
    body_budget = {"used": 0, "dropped": 0}
    data_uris = {}
    for p in report.get("screenshots") or []:
        uri = _data_uri(p, budget)
        if uri:
            data_uris[p] = uri

    t0 = report.get("started_ts")
    try:
        t0 = float(t0)
    except (TypeError, ValueError):
        t0 = None

    def rel(ts):
        """Seconds since run start — the viewer's common timeline."""
        try:
            ts = float(ts)
        except (TypeError, ValueError):
            return None
        return (ts - t0) if t0 is not None else None

    # ---- unified timeline: steps and requests on one clock --------------
    items = []
    for st in report.get("steps") or []:
        if not isinstance(st, dict):
            continue
        shots = []
        own = st.get("screenshot")
        if own and own in data_uris:
            shots.append(own)
        idx = st.get("index")
        for m in shots_meta:
            if isinstance(m, dict) and m.get("step_index") == idx and m.get("path") in data_uris:
                if m["path"] not in shots:
                    shots.append(m["path"])
        items.append({
            "kind": "step",
            "ts": st.get("started_at"),
            "rel": rel(st.get("started_at")),
            "index": idx,
            "ok": st.get("ok"),
            "title": st.get("action") or "",
            "detail": st.get("message") or "",
            "dur": st.get("duration_ms"),
            "shots": shots,
        })
    for rq in traffic or []:
        if not isinstance(rq, dict):
            continue
        items.append({
            "kind": "req",
            "ts": rq.get("ts"),
            "rel": rel(rq.get("ts")),
            "method": rq.get("method") or "",
            "url": rq.get("url") or "",
            "status": rq.get("status"),
            "error": rq.get("error"),
            # full record (headers + bodies) for the collapsible detail row;
            # absent when the caller passed lightweight summaries
            "_full": rq,
        })
    # Steps with no timestamp stay in script order at the head of the list.
    items.sort(key=lambda it: (it["rel"] if it["rel"] is not None else -1))

    status_cls = "bad"
    status_txt = "FAILED"
    if report.get("cancelled"):
        status_cls, status_txt = "warn", "CANCELLED"
    elif report.get("success"):
        status_cls, status_txt = "ok", "PASSED"

    rows = []
    for it in items:
        rel_txt = f"+{it['rel']:.2f}s" if it.get("rel") is not None else "-"
        clock = _fmt_ts(it.get("ts"))
        if it["kind"] == "step":
            cls = "ok" if it.get("ok") else "bad"
            thumbs = "".join(
                f'<img class="thumb" src="{data_uris[p]}" alt="{_esc(os.path.basename(p))}" title="点击放大">'
                for p in it["shots"]
            )
            rows.append(
                f'<tr class="row step {cls}" data-kind="step">'
                f'<td class="t">{rel_txt}<span class="clock">{clock}</span></td>'
                f'<td class="k"><span class="pill {cls}">STEP {_esc(it["index"])}</span></td>'
                f'<td class="b"><div class="ttl">{_esc(it["title"])}'
                f'<span class="dur">{_fmt_dur(it.get("dur"))}</span></div>'
                f'<div class="d">{_esc(it["detail"])}</div>{thumbs}</td></tr>'
            )
        else:
            code = it.get("status")
            cls = "ok" if isinstance(code, int) and code < 400 else (
                "warn" if isinstance(code, int) else "bad")
            rows.append(
                f'<tr class="row req {cls}" data-kind="req" title="点击展开请求/响应明细">'
                f'<td class="t">{rel_txt}<span class="clock">{clock}</span></td>'
                f'<td class="k"><span class="pill {cls}">{_esc(it["method"])}</span></td>'
                f'<td class="b"><div class="ttl">{_esc(it["url"])}</div>'
                f'<div class="d">{_esc(code)}{" · " + _esc(it["error"]) if it.get("error") else ""}</div></td></tr>'
            )
            full = it.get("_full")
            if isinstance(full, dict):
                rows.append(_req_detail_html(full, body_budget))

    gallery = "".join(
        f'<figure><img src="{data_uris[p]}" alt="{_esc(os.path.basename(p))}" title="点击放大">'
        f'<figcaption>{_esc(os.path.basename(p))}'
        f'{" · step " + _esc(shot_by_path[p].get("step_index")) if shot_by_path.get(p, {}).get("step_index") else ""}'
        f'</figcaption></figure>'
        for p in (report.get("screenshots") or []) if p in data_uris
    )
    skipped_note = ""
    if budget["skipped"]:
        skipped_note = (f'<p class="note">（{budget["skipped"]} 张截图超出内嵌体积上限，'
                        f'未包含在本文件中，请查看运行目录）</p>')

    crash = report.get("crash_log") or ""
    crash_html = (f'<h2>Crash log</h2><pre class="crash">{_esc(crash)}</pre>' if crash else "")

    traffic_note = ""
    if report.get("traffic_truncated"):
        traffic_note = (f'<p class="note">请求列表已截断（共 {report.get("traffic_total")} 条），'
                        f'完整记录见运行目录下的 traffic/*.jsonl</p>')
    if body_budget["dropped"]:
        traffic_note += (f'<p class="note">（{body_budget["dropped"]} 个请求/响应体超出内嵌体积上限，'
                         f'未包含在本文件中，请查看运行目录下的 traffic/*.jsonl）</p>')

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Automation Report · {_esc(report.get('task_id'))}</title>
<style>
:root {{ color-scheme: light; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 28px 32px; background: #f6f7f9; color: #1f2329;
  font: 13px/1.6 -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; }}
h1 {{ font-size: 19px; margin: 0 0 4px; }}
h2 {{ font-size: 14px; margin: 26px 0 8px; color: #4b5563; }}
.wrap {{ max-width: 1040px; margin: 0 auto; }}
.meta {{ color: #6b7280; font-size: 12px; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0 4px; }}
.chip {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 999px;
  padding: 3px 10px; font-size: 12px; }}
.chip b {{ font-weight: 600; }}
.chip.st {{ border-color: transparent; color: #fff; }}
.chip.ok.st {{ background: #18a058; }} .chip.bad.st {{ background: #d03050; }}
.chip.warn.st {{ background: #f0a020; }}
.bar {{ display: flex; gap: 14px; align-items: center; margin: 14px 0 6px; font-size: 12px; }}
.bar label {{ cursor: pointer; user-select: none; }}
table {{ width: 100%; border-collapse: collapse; background: #fff;
  border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; }}
.row td {{ border-bottom: 1px solid #f0f1f3; padding: 8px 10px; vertical-align: top; }}
.row:last-child td {{ border-bottom: none; }}
.t {{ width: 76px; color: #6b7280; font-variant-numeric: tabular-nums;
  white-space: nowrap; font-size: 11.5px; }}
.t .clock {{ display: block; color: #9ca3af; font-size: 10.5px; }}
.k {{ width: 84px; }}
.pill {{ display: inline-block; padding: 1px 7px; border-radius: 6px; font-size: 11px;
  font-weight: 600; background: #eef1f5; color: #4b5563; }}
.pill.ok {{ background: #e7f6ee; color: #18a058; }}
.pill.bad {{ background: #fdeaee; color: #d03050; }}
.pill.warn {{ background: #fdf3e2; color: #b26a00; }}
.ttl {{ font-weight: 600; word-break: break-all; }}
.ttl .dur {{ font-weight: 400; color: #9ca3af; font-size: 11px; margin-left: 6px; }}
.d {{ color: #6b7280; font-size: 12px; word-break: break-all; }}
.thumb {{ height: 96px; border: 1px solid #e5e7eb; border-radius: 6px; margin: 6px 6px 0 0;
  cursor: zoom-in; }}
.gallery {{ display: flex; flex-wrap: wrap; gap: 12px; }}
.gallery figure {{ margin: 0; background: #fff; border: 1px solid #e5e7eb;
  border-radius: 10px; padding: 8px; }}
.gallery img {{ height: 220px; border-radius: 6px; display: block; cursor: zoom-in; }}
.gallery figcaption {{ font-size: 11px; color: #6b7280; margin-top: 6px; text-align: center; }}
pre.crash {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
  padding: 12px; font-size: 11.5px; overflow: auto; max-height: 320px; white-space: pre-wrap; }}
.note {{ color: #b26a00; font-size: 12px; }}
.row.req {{ cursor: pointer; }}
.rdet td {{ background: #fafbfc; padding: 4px 10px 12px; }}
.rdet .lb {{ color: #4b5563; font-size: 11px; font-weight: 600; margin: 10px 0 3px; }}
.rdet pre {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 6px;
  padding: 8px 10px; margin: 0; font: 11.5px/1.5 ui-monospace, Consolas, monospace;
  overflow: auto; max-height: 260px; white-space: pre-wrap; word-break: break-all; }}
.rdet pre.empty {{ color: #9ca3af; border-style: dashed; }}
table.filter-steps tr.req {{ display: none; }}
table.filter-reqs tr.step {{ display: none; }}
/* 截图放大：必须用页内灯箱 —— 截图以 data: URI 内嵌，而 Chromium 禁止顶层
   导航到 data: URL（Chrome 60 起），交给浏览器打开只会得到空白标签页。
   （测试断言此文件中不出现该旧做法，故此处不写其字面量。） */
#lightbox {{ position: fixed; inset: 0; z-index: 9999; display: none;
  align-items: center; justify-content: center;
  background: var(--app-overlay-bg); cursor: zoom-out; }}
#lightbox.open {{ display: flex; }}
#lightbox img {{ max-width: 92vw; max-height: 92vh; border-radius: 8px;
  box-shadow: var(--app-shadow-overlay); }}
</style></head>
<body><div class="wrap">
<h1>自动化执行报告</h1>
<div class="meta">
  {_esc(report.get('task_id'))} · {_esc(report.get('package_name') or '-')} ·
  设备 {_esc(report.get('device_id') or '-')}<br>
  {_esc(report.get('started_at'))} → {_esc(report.get('finished_at'))} ·
  耗时 {_fmt_dur(report.get('duration_ms'))}
</div>
<div class="chips">
  <span class="chip st {status_cls}"><b>{status_txt}</b></span>
  <span class="chip">步骤 <b>{report.get('passed', 0)}/{report.get('total', 0)}</b></span>
  <span class="chip">失败 <b>{report.get('failed', 0)}</b></span>
  <span class="chip">请求 <b>{report.get('traffic_total', 0)}</b></span>
  <span class="chip">截图 <b>{len(report.get('screenshots') or [])}</b></span>
</div>
<div class="bar">
  <label><input type="checkbox" checked onchange="toggleKind('step', this.checked)"> 执行步骤</label>
  <label><input type="checkbox" checked onchange="toggleKind('req', this.checked)"> 网络请求</label>
</div>
<h2>时间线（步骤与请求按时间戳对齐）</h2>
<table id="tl"><tbody>{''.join(rows)}</tbody></table>
{traffic_note}
<h2>截图</h2>
{skipped_note}
<div class="gallery">{gallery or '<p class="note">本次运行没有截图</p>'}</div>
{crash_html}
<script>
function toggleKind(kind, on) {{
  document.querySelectorAll('#tl tr[data-kind="' + kind + '"]')
    .forEach(function(tr) {{
      // detail rows (.rdet) stay hidden through kind toggles — re-expand by
      // clicking the request row again
      tr.style.display = (on && !tr.classList.contains('rdet')) ? '' : 'none';
    }});
}}
document.querySelectorAll('#tl tr.req').forEach(function(tr) {{
  tr.addEventListener('click', function() {{
    var d = tr.nextElementSibling;
    if (d && d.classList.contains('rdet')) {{
      d.style.display = d.style.display === 'none' ? '' : 'none';
    }}
  }});
}});
var lbox = document.getElementById('lightbox');
var lboxImg = lbox ? lbox.querySelector('img') : null;
document.addEventListener('click', function(e) {{
  if (!lboxImg) return;
  if (e.target.tagName === 'IMG' && e.target !== lboxImg) {{
    lboxImg.src = e.target.src;
    lboxImg.alt = e.target.alt || '';
    lbox.classList.add('open');
  }} else if (lbox.classList.contains('open')) {{
    lbox.classList.remove('open');
  }}
}});
document.addEventListener('keydown', function(e) {{
  if (e.key === 'Escape' && lbox.classList.contains('open')) {{
    lbox.classList.remove('open');
  }}
}});
</script>
</div>
<div id="lightbox"><img alt=""></div>
</body></html>"""


def handle_export_run(params, stream_handler):
    """Write a self-contained HTML report for one run.

    ``target`` is the user-chosen destination from the OS save dialog (same
    trust model as ``task.export_log``); when absent, the file lands next to
    the run's artifacts as ``report.html``.
    """
    try:
        run_dir = _run_dir_for(params.get("task_id", ""))
    except ValueError as e:
        return {"success": False, "error": str(e)}
    if not os.path.isfile(os.path.join(run_dir, REPORT_NAME)):
        return {"success": False, "error": "report not found"}
    try:
        report = _read_report(run_dir)
        limit = _bounded_int(params.get("traffic_limit"), 100000, 0, 1000000)
        # The export embeds every request it can, so it gets a far larger scan
        # budget than the interactive viewer (which only needs a first slice).
        traffic = _read_traffic_full(
            report.get("traffic_log") or "", limit,
            max_bytes=_bounded_int(
                params.get("traffic_scan_bytes"), EXPORT_TRAFFIC_SCAN_BYTES,
                0, EXPORT_TRAFFIC_SCAN_BYTES,
            ),
        )
        report["traffic_total"] = traffic["total"]
        report["traffic_truncated"] = traffic["truncated"]
        doc = build_report_html(report, traffic["entries"])
    except (OSError, ValueError) as e:
        logger.warning(f"failed to build report html for '{run_dir}': {e}")
        return {"success": False, "error": str(e)}

    target = str(params.get("target") or "").strip()
    archive = os.path.join(run_dir, "report.html")
    # always keep an archived copy beside the artifacts; `target` is the
    # user-chosen destination from the OS save dialog (may equal archive)
    written = []
    try:
        with open(archive, "w", encoding="utf-8") as f:
            f.write(doc)
        written.append(archive)
        if target and os.path.abspath(target) != os.path.abspath(archive):
            parent = os.path.dirname(os.path.abspath(target))
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(doc)
            written.append(target)
    except OSError as e:
        logger.warning(f"failed to write report html: {e}")
        return {"success": False, "error": str(e)}

    out_path = written[-1]
    logger.info(f"automation report exported: {out_path}")
    return {
        "success": True,
        "file_path": out_path,
        "archive_path": archive,
        "run_dir": run_dir,
        "size": len(doc.encode("utf-8")),
        "traffic_total": report.get("traffic_total", 0),
        "screenshots": len(report.get("screenshots") or []),
    }


API_MAP = {
    "automation.list_runs": handle_list_runs,
    "automation.read_run": handle_read_run,
    "automation.traffic_detail": handle_traffic_detail,
    "automation.delete_run": handle_delete_run,
    "automation.prune_runs": handle_prune_runs,
    "automation.export_run": handle_export_run,
}
