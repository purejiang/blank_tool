#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automation run history handlers.

Every adb_auto run writes ``report.json`` into its per-run directory under
the AUTOMATION root — ``{BT_AUTO_TASKS_DIR}/{task_id}/``, i.e.
``auto_tasks/`` as a sibling of ``tasks/`` — with artifacts categorized into
``screenshots/`` ``traffic/`` ``crash_logs/``. These handlers list / read /
delete those run directories. Deletion removes the WHOLE run directory and
is containment-checked against the automation root, and only directories
that actually contain a ``report.json`` are eligible — APK/package task
dirs (which live under ``tasks/``) can never be touched from here.
"""

import base64
import gzip
import json
import os
import shutil
import time
import zlib

from app.utils.env import get_auto_tasks_root
from app.utils.logger import Logger

logger = Logger.get_logger("AutomationRunsHandler")

REPORT_NAME = "report.json"


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


def handle_list_runs(params, stream_handler):
    """Summaries of every automation run, newest first (max 100)."""
    root = os.path.realpath(get_auto_tasks_root())
    runs = []
    try:
        entries = os.listdir(root)
    except OSError as e:
        return {"success": False, "runs": [], "error": str(e)}
    for name in entries:
        report_path = os.path.join(root, name, REPORT_NAME)
        if not os.path.isfile(report_path):
            continue  # not an automation run (or an incomplete one)
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(report, dict):
            continue
        runs.append({
            "task_id": report.get("task_id") or name,
            "started_at": report.get("started_at", ""),
            "finished_at": report.get("finished_at", ""),
            "duration_ms": report.get("duration_ms", 0),
            "success": bool(report.get("success")),
            "cancelled": bool(report.get("cancelled")),
            "aborted_by_crash": bool(report.get("aborted_by_crash")),
            "total": report.get("total", 0),
            "passed": report.get("passed", 0),
            "failed": report.get("failed", 0),
            "package_name": report.get("package_name", ""),
            "run_dir": report.get("run_dir") or os.path.join(root, name),
        })
    runs.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    return {"success": True, "runs": runs[:100]}


def _read_traffic(jsonl_path: str, limit: int) -> dict:
    """Parse the capture jsonl into lightweight request summaries.

    Only the fields the report viewer needs are kept (timestamps, method,
    URL, status); bodies and headers stay in the jsonl on disk so a run
    with thousands of requests doesn't blow up the IPC payload.
    """
    entries = []
    total = 0
    if not jsonl_path or not os.path.isfile(jsonl_path):
        return {"entries": [], "total": 0, "truncated": False}
    try:
        with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
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
        return {"entries": entries, "total": total, "truncated": False, "error": str(e)}
    return {"entries": entries, "total": total, "truncated": total > len(entries)}


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


def _read_traffic_full(jsonl_path: str, limit: int) -> dict:
    """Parse the capture jsonl into FULL records (headers + bodies).

    Companion to ``_read_traffic`` — same file, same order, same limit
    semantics — but keeps every field. Used ONLY by the HTML export, which
    embeds per-request detail into a self-contained document; ``read_run``
    keeps serving lightweight summaries so IPC payloads stay small.
    """
    entries = []
    total = 0
    if not jsonl_path or not os.path.isfile(jsonl_path):
        return {"entries": [], "total": 0, "truncated": False}
    try:
        with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
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
        return {"entries": entries, "total": total, "truncated": False, "error": str(e)}
    return {"entries": entries, "total": total, "truncated": total > len(entries)}


def handle_read_run(params, stream_handler):
    """Full report.json of one run (+ lightweight request log by default).

    ``traffic_limit`` caps how many request summaries are returned; the
    viewer asks for a bounded slice, the HTML export embeds them all.
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

    limit = params.get("traffic_limit")
    if limit is None:
        limit = 2000
    try:
        limit = max(0, min(int(limit), 20000))
    except (TypeError, ValueError):
        limit = 2000
    traffic = _read_traffic(report.get("traffic_log") or "", limit)
    report["traffic"] = traffic["entries"]
    report["traffic_total"] = traffic["total"]
    report["traffic_truncated"] = traffic["truncated"]
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


def handle_delete_run(params, stream_handler):
    """Delete the WHOLE run directory (artifacts + report)."""
    try:
        run_dir = _run_dir_for(params.get("task_id", ""))
    except ValueError as e:
        return {"deleted": False, "error": str(e)}
    if not os.path.isfile(os.path.join(run_dir, REPORT_NAME)):
        return {"deleted": False,
                "error": "not an automation run dir (no report.json)"}
    try:
        shutil.rmtree(run_dir, ignore_errors=False)
        logger.info(f"deleted automation run dir: {run_dir}")
        return {"deleted": True}
    except Exception as e:
        logger.warning(f"failed to delete run dir '{run_dir}': {e}")
        return {"deleted": False, "error": str(e)}


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
        limit = params.get("traffic_limit")
        try:
            limit = max(0, min(int(limit), 100000)) if limit is not None else 100000
        except (TypeError, ValueError):
            limit = 100000
        traffic = _read_traffic_full(report.get("traffic_log") or "", limit)
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
    "automation.export_run": handle_export_run,
}
