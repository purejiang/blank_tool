#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract tests for automation.traffic_detail (runs handler).

The report viewer only gets lightweight request summaries from
``automation.read_run`` — bodies and headers stay in the capture jsonl.
``traffic_detail`` is the per-record fetch the viewer uses when a row is
expanded; these tests pin the index→record mapping and the error paths.
"""

import json
import os

import pytest

from app.handlers.automation_runs_handler import handle_traffic_detail


@pytest.fixture
def run_env(tmp_path, monkeypatch):
    """A fake automation run: report.json + traffic/*.jsonl with 3 records.

    Returns (task_id, jsonl_path). ``BT_AUTO_TASKS_DIR`` is redirected to
    tmp_path so the handler's containment checks pass.
    """
    root = tmp_path / "auto_tasks"
    root.mkdir()
    monkeypatch.setenv("BT_AUTO_TASKS_DIR", str(root))

    task_id = "t-detail-1"
    run_dir = root / task_id
    traffic_dir = run_dir / "traffic"
    traffic_dir.mkdir(parents=True)
    jsonl = traffic_dir / "traffic-20260914-000000-deadbe.jsonl"

    records = [
        {"ts": 1.0, "method": "GET", "url": "https://a.example.com/x",
         "host": "a.example.com", "port": 443, "status": 200,
         "req_headers": {"host": "a.example.com"}, "req_body": None,
         "resp_headers": {"content-type": "application/json"},
         "resp_body": {"text": '{"ok": true}'},
         "client_addr": "127.0.0.1", "error": None},
        {"ts": 2.0, "method": "POST", "url": "https://b.example.com/y",
         "host": "b.example.com", "port": 443, "status": None,
         "req_headers": {}, "req_body": {"text": "k=v"},
         "resp_headers": {}, "resp_body": None,
         "client_addr": "127.0.0.1", "error": "Server TLS handshake failed"},
        {"ts": 3.0, "method": "GET", "url": "https://c.example.com/z",
         "host": "c.example.com", "port": 443, "status": 200,
         "req_headers": {}, "req_body": None,
         "resp_headers": {}, "resp_body": {"truncated": True, "size": 99999},
         "client_addr": "127.0.0.1", "error": None},
        {"ts": 4.0, "method": "POST", "url": "https://d.example.com/w",
         "host": "d.example.com", "port": 443, "status": 201,
         "req_headers": {"content-type": "application/octet-stream"},
         "req_body": {"b64": "aGVsbG8="},
         "resp_headers": {}, "resp_body": None,
         "client_addr": "127.0.0.1", "error": None},
    ]
    with open(jsonl, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    report = {"task_id": task_id, "traffic_log": str(jsonl)}
    with open(run_dir / "report.json", "w", encoding="utf-8") as f:
        json.dump(report, f)

    return task_id, str(jsonl)


def test_traffic_detail_in_api_map():
    from app.handlers.automation_runs_handler import API_MAP, handle_traffic_detail
    assert "automation.traffic_detail" in API_MAP
    assert API_MAP["automation.traffic_detail"] is handle_traffic_detail


def test_detail_returns_full_record(run_env):
    task_id, _ = run_env
    r = handle_traffic_detail({"task_id": task_id, "index": 0}, None)
    assert r["success"] is True
    rec = r["record"]
    # summaries dropped these; the detail record must carry them
    assert rec["req_headers"] == {"host": "a.example.com"}
    assert rec["resp_body"] == {"text": '{"ok": true}'}


def test_detail_index_maps_to_jsonl_line(run_env):
    task_id, _ = run_env
    r = handle_traffic_detail({"task_id": task_id, "index": 1}, None)
    rec = r["record"]
    assert rec["url"] == "https://b.example.com/y"
    assert rec["status"] is None
    assert rec["error"] == "Server TLS handshake failed"


def test_detail_body_shapes_preserved(run_env):
    """b64 / truncated markers must pass through untouched."""
    task_id, _ = run_env
    trunc = handle_traffic_detail({"task_id": task_id, "index": 2}, None)["record"]
    assert trunc["resp_body"] == {"truncated": True, "size": 99999}


def test_detail_index_out_of_range(run_env):
    task_id, _ = run_env
    r = handle_traffic_detail({"task_id": task_id, "index": 99}, None)
    assert r["success"] is False
    assert r["record"] is None
    assert "out of range" in r["error"]


def test_detail_invalid_index(run_env):
    task_id, _ = run_env
    r = handle_traffic_detail({"task_id": task_id, "index": "abc"}, None)
    assert r["success"] is False
    assert r["error"] == "invalid index"
    r2 = handle_traffic_detail({"task_id": task_id}, None)
    assert r2["success"] is False


def test_detail_missing_traffic_log(tmp_path, monkeypatch):
    root = tmp_path / "auto_tasks"
    root.mkdir()
    monkeypatch.setenv("BT_AUTO_TASKS_DIR", str(root))
    run_dir = root / "t-nolog"
    run_dir.mkdir()
    with open(run_dir / "report.json", "w", encoding="utf-8") as f:
        json.dump({"task_id": "t-nolog"}, f)
    r = handle_traffic_detail({"task_id": "t-nolog", "index": 0}, None)
    assert r["success"] is False
    assert r["error"] == "traffic log not found"


def test_detail_bad_task_id_rejected():
    r = handle_traffic_detail({"task_id": "../escape", "index": 0}, None)
    assert r["success"] is False
    assert r["record"] is None


# ---------------------------------------------------------------- export --
# The HTML export must embed what the summaries deliberately drop: headers
# and bodies of every captured request, in collapsible rows.

import base64 as _base64

import app.handlers.automation_runs_handler as runs_handler
from app.handlers.automation_runs_handler import handle_export_run, _read_traffic_full


def _export_html(run_env, tmp_path, extra=None):
    task_id, _ = run_env
    target = tmp_path / "report.html"
    params = {"task_id": task_id, "target": str(target)}
    if extra:
        params.update(extra)
    r = handle_export_run(params, None)
    assert r["success"] is True, r.get("error")
    with open(target, "r", encoding="utf-8") as f:
        return f.read()


def test_export_embeds_headers_and_text_bodies(run_env, tmp_path):
    html = _export_html(run_env, tmp_path)
    # four labeled sections per request detail row
    for label in ("请求头", "请求体", "响应头", "响应体"):
        assert label in html
    # record 0: request header + JSON response body (pretty-printed, escaped)
    assert "a.example.com" in html
    assert "&quot;ok&quot;: true" in html
    # record 1: POST body text
    assert "k=v" in html


def test_export_embeds_b64_and_truncation_markers(run_env, tmp_path):
    html = _export_html(run_env, tmp_path)
    # record 3: binary body becomes an inline download link, not a text dump
    assert 'href="data:application/octet-stream;base64,aGVsbG8=' in html
    # record 2: capture-time truncation is surfaced, not silently dropped
    assert "捕获时已截断" in html
    assert "99999" in html


def test_export_detail_rows_hidden_until_clicked(run_env, tmp_path):
    html = _export_html(run_env, tmp_path)
    assert 'class="rdet" data-kind="req" style="display:none"' in html
    # kind-toggle must not accidentally reveal detail rows when re-enabled
    assert "classList.contains('rdet')" in html


def test_export_body_budget_degrades_gracefully(run_env, tmp_path, monkeypatch):
    monkeypatch.setattr(runs_handler, "MAX_BODY_EMBED_BYTES", 2)
    html = _export_html(run_env, tmp_path)
    assert "超出内嵌体积上限" in html
    # summary rows are unaffected — only bodies degrade
    assert "a.example.com" in html


def test_read_traffic_full_keeps_wire_shapes(run_env):
    _, jsonl = run_env
    r = _read_traffic_full(jsonl, 100)
    assert r["total"] == 4
    assert len(r["entries"]) == 4
    rec = r["entries"][3]
    assert rec["req_body"] == {"b64": "aGVsbG8="}
    assert r["entries"][2]["resp_body"] == {"truncated": True, "size": 99999}


def test_read_traffic_full_respects_limit(run_env):
    _, jsonl = run_env
    r = _read_traffic_full(jsonl, 2)
    assert r["total"] == 4
    assert len(r["entries"]) == 2
    assert r["truncated"] is True
