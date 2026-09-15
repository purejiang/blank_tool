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


# ------------------------------------------------- 压缩体抢救（存量抓包） --
# 早期 traffic_addon 用 raw_content 落盘：gzip/deflate 响应存的是线上压缩字节，
# 读取时 UTF-8 解码失败被判成二进制 → 表现为「响应体都是二进制内容」。
# 读取侧按 content-encoding 就地解压，让存量 jsonl 在查看器与导出里恢复可读。

import gzip as _gzip
import zlib as _zlib


def _gzip_b64(text: str) -> str:
    return _base64.b64encode(_gzip.compress(text.encode("utf-8"))).decode("ascii")


def _deflate_b64(text: str) -> str:
    return _base64.b64encode(_zlib.compress(text.encode("utf-8"))).decode("ascii")


_PAYLOAD = '{"ok": true, "msg": "解压成功"}'


@pytest.fixture
def gz_run_env(tmp_path, monkeypatch):
    """一条 gzip、一条 deflate、一条真二进制、一条「gzip 但非 UTF-8」的 jsonl。"""
    root = tmp_path / "auto_tasks"
    root.mkdir()
    monkeypatch.setenv("BT_AUTO_TASKS_DIR", str(root))
    task_id = "t-gzip"
    run_dir = root / task_id
    (run_dir / "traffic").mkdir(parents=True)
    jsonl = run_dir / "traffic" / "traffic-gz.jsonl"

    records = [
        {  # ① gzip（请求体同样压缩）→ 两侧都该还原成 text
            "ts": 1.0, "method": "POST", "url": "https://a.example.com/gz",
            "host": "a.example.com", "port": 443, "status": 200,
            "req_headers": {"Content-Encoding": "gzip"},
            "req_body": {"b64": _gzip_b64(_PAYLOAD)},
            "resp_headers": {"Content-Encoding": "gzip", "Content-Type": "application/json"},
            "resp_body": {"b64": _gzip_b64(_PAYLOAD)},
            "client_addr": "127.0.0.1", "error": None,
        },
        {  # ② deflate（header 小写）→ 还原
            "ts": 2.0, "method": "GET", "url": "https://b.example.com/df",
            "host": "b.example.com", "port": 443, "status": 200,
            "req_headers": {}, "req_body": None,
            "resp_headers": {"content-encoding": "deflate"},
            "resp_body": {"b64": _deflate_b64(_PAYLOAD)},
            "client_addr": "127.0.0.1", "error": None,
        },
        {  # ③ 真二进制（无 content-encoding）→ 保持 b64，不误判
            "ts": 3.0, "method": "GET", "url": "https://c.example.com/blob",
            "host": "c.example.com", "port": 443, "status": 200,
            "req_headers": {}, "req_body": None,
            "resp_headers": {"Content-Type": "application/octet-stream"},
            "resp_body": {"b64": _base64.b64encode(b"\x00\x01\x02\x03").decode("ascii")},
            "client_addr": "127.0.0.1", "error": None,
        },
        {  # ④ 声明 gzip 但解出来不是 UTF-8 → 保持 b64
            "ts": 4.0, "method": "GET", "url": "https://d.example.com/bin",
            "host": "d.example.com", "port": 443, "status": 200,
            "req_headers": {}, "req_body": None,
            "resp_headers": {"Content-Encoding": "gzip"},
            "resp_body": {"b64": _base64.b64encode(
                _gzip.compress(b"\xff\xfe\x00\x01")).decode("ascii")},
            "client_addr": "127.0.0.1", "error": None,
        },
    ]
    with open(jsonl, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with open(run_dir / "report.json", "w", encoding="utf-8") as f:
        json.dump({"task_id": task_id, "traffic_log": str(jsonl)}, f)
    return task_id


def test_detail_rescues_gzip_and_deflate_bodies(gz_run_env):
    gz = handle_traffic_detail({"task_id": gz_run_env, "index": 0}, None)["record"]
    assert gz["resp_body"]["text"] == _PAYLOAD
    assert gz["resp_body"]["decompressed"] == "gzip"
    assert gz["req_body"]["text"] == _PAYLOAD          # 请求体同因同修
    assert gz["req_body"]["decompressed"] == "gzip"

    df = handle_traffic_detail({"task_id": gz_run_env, "index": 1}, None)["record"]
    assert df["resp_body"]["text"] == _PAYLOAD
    assert df["resp_body"]["decompressed"] == "deflate"


def test_detail_leaves_genuinely_binary_and_non_utf8_untouched(gz_run_env):
    blob = handle_traffic_detail({"task_id": gz_run_env, "index": 2}, None)["record"]
    assert "b64" in blob["resp_body"] and "text" not in blob["resp_body"]

    non_utf8 = handle_traffic_detail({"task_id": gz_run_env, "index": 3}, None)["record"]
    assert "b64" in non_utf8["resp_body"] and "text" not in non_utf8["resp_body"]


def tmp_jsonl(task_id):
    """按 BT_AUTO_TASKS_DIR 定位 jsonl（供 _read_traffic_full 直接调用）。"""
    root = os.environ["BT_AUTO_TASKS_DIR"]
    return os.path.join(root, task_id, "traffic", "traffic-gz.jsonl")


def test_read_traffic_full_rescues_compressed_bodies(gz_run_env):
    r = _read_traffic_full(tmp_jsonl(gz_run_env), 100)
    assert r["entries"][0]["resp_body"]["text"] == _PAYLOAD
    assert r["entries"][1]["resp_body"]["decompressed"] == "deflate"
    assert "b64" in r["entries"][2]["resp_body"]
    assert "b64" in r["entries"][3]["resp_body"]
