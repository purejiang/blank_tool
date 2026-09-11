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
import json
import os
import shutil
import time

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
# inlined as base64 and the request log is embedded as a table, so the report
# can be moved anywhere (mail, ticket, shared drive) without breaking.
MAX_EMBED_BYTES = 32 * 1024 * 1024  # cap on inlined screenshot payload


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


def build_report_html(report: dict, traffic: list) -> str:
    """Render the whole run as one standalone HTML document."""
    shots_meta = report.get("shots_meta") or []
    shot_by_path = {}
    for m in shots_meta:
        if isinstance(m, dict) and m.get("path"):
            shot_by_path[m["path"]] = m

    budget = {"used": 0, "skipped": 0}
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
                f'<img class="thumb" src="{data_uris[p]}" alt="{_esc(os.path.basename(p))}">'
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
                f'<tr class="row req {cls}" data-kind="req">'
                f'<td class="t">{rel_txt}<span class="clock">{clock}</span></td>'
                f'<td class="k"><span class="pill {cls}">{_esc(it["method"])}</span></td>'
                f'<td class="b"><div class="ttl">{_esc(it["url"])}</div>'
                f'<div class="d">{_esc(code)}{" · " + _esc(it["error"]) if it.get("error") else ""}</div></td></tr>'
            )

    gallery = "".join(
        f'<figure><img src="{data_uris[p]}" alt="{_esc(os.path.basename(p))}">'
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
table.filter-steps tr.req {{ display: none; }}
table.filter-reqs tr.step {{ display: none; }}
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
    .forEach(function(tr) {{ tr.style.display = on ? '' : 'none'; }});
}}
document.addEventListener('click', function(e) {{
  if (e.target.tagName === 'IMG') {{
    window.open(e.target.src, '_blank');
  }}
}});
</script>
</div></body></html>"""


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
        traffic = _read_traffic(report.get("traffic_log") or "", limit)
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
    "automation.delete_run": handle_delete_run,
    "automation.export_run": handle_export_run,
}
