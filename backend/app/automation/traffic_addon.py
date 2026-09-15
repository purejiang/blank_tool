#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mitmproxy addon — append every completed HTTP(S) exchange to a JSONL file.

Runs INSIDE mitmdump (passed via ``mitmdump -s <this file>``), so importing
``mitmproxy`` here is fine — unlike the rest of ``backend/`` which stays
stdlib-only. Configuration comes from environment variables:

  TRAFFIC_JSONL       output file, one JSON object per line (required)
  TRAFFIC_HOST_FILTER optional comma-separated substrings; only flows whose
                      host contains ANY of them are recorded (empty = record
                      everything). Whitespace around entries and empty
                      segments are ignored.
  TRAFFIC_MAX_BODY    bodies larger than this are replaced by a
                      ``{"truncated": true, "size": N}`` marker (default 16 KiB)

One record per completed response, plus one record (``status: null``,
``error`` set) per FAILED flow via the ``error`` hook — TLS handshake
failures, timeouts, CONNECT refusals — so missing requests are visible
with their reason instead of silently dropped::

  {ts, method, url, host, port, status, req_headers, req_body,
   resp_headers, resp_body, client_addr, error}

``req_body`` / ``resp_body`` are ``{"text": ...}`` when UTF-8 decodable,
``{"b64": ...}`` for binary, or the truncation marker. Bodies are taken from
the **decoded** content (``Message.content``, i.e. Content-Encoding applied)
so gzip/br responses are stored as readable text instead of binary blobs.
"""

import base64
import json
import os
import time

from mitmproxy import http

_OUT = os.environ.get("TRAFFIC_JSONL", "")
# Comma-separated substring allowlist, evaluated as OR: a flow is recorded
# when its host contains ANY entry. Note the host is what the client sent in
# CONNECT / Host — for domain traffic it is the DOMAIN, never the resolved
# IP, so IP entries only match connections made to a literal IP.
_FILTERS = [s.strip() for s in os.environ.get("TRAFFIC_HOST_FILTER", "").split(",") if s.strip()]
try:
    _MAX_BODY = int(os.environ.get("TRAFFIC_MAX_BODY", "16384"))
except ValueError:
    _MAX_BODY = 16384

_fh = None
_count = 0


def _encode_body(data: bytes):
    if data is None:
        return None
    if len(data) > _MAX_BODY:
        return {"truncated": True, "size": len(data)}
    try:
        return {"text": data.decode("utf-8")}
    except UnicodeDecodeError:
        return {"b64": base64.b64encode(data).decode("ascii")}


def _decoded_content(msg) -> bytes:
    """解压后的 body。mitmproxy 的 ``.content`` 会按 Content-Encoding 解压
    （gzip/br/deflate…）；``.raw_content`` 是线上原始字节。

    早期版本用 raw_content 落盘，导致 gzip 响应被存成二进制 blob（"响应体都是
    二进制"的根因）。解码失败时回退原始字节——宁可退化成 b64，也不丢记录。
    """
    if msg is None:
        return None
    try:
        return msg.content
    except Exception:
        try:
            return msg.raw_content
        except Exception:
            return None


def _write(rec: dict) -> None:
    global _fh, _count
    try:
        if _fh is None:
            _fh = open(_OUT, "a", encoding="utf-8")
        _fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _fh.flush()
        _count += 1
    except Exception:
        # never let a write failure kill the proxy
        pass


def response(flow: http.HTTPFlow) -> None:
    if not _OUT:
        return
    if _FILTERS and not any(s in flow.request.pretty_host for s in _FILTERS):
        return
    rec = {
        "ts": time.time(),
        "method": flow.request.method,
        "url": flow.request.pretty_url,
        "host": flow.request.pretty_host,
        "port": flow.request.port,
        "status": flow.response.status_code if flow.response else None,
        "req_headers": dict(flow.request.headers),
        "req_body": _encode_body(_decoded_content(flow.request)),
        "resp_headers": dict(flow.response.headers) if flow.response else {},
        "resp_body": _encode_body(_decoded_content(flow.response)),
        "client_addr": flow.client_conn.peername[0] if flow.client_conn.peername else "",
        "error": str(flow.error.msg) if flow.error else None,
    }
    _write(rec)


def error(flow: http.HTTPFlow) -> None:
    """Flows that never complete — upstream TLS handshake failure, timeout,
    client abort, CONNECT refused — never reach ``response()``, so without
    this hook they vanish from the capture entirely (the "some requests are
    missing" incident: HMS grs.dbankcloud.* failed upstream cert verify and
    left no trace). Record them with the reason instead."""
    if not _OUT:
        return
    if flow.response is not None:
        return  # response() already recorded it
    if _FILTERS and not any(s in flow.request.pretty_host for s in _FILTERS):
        return
    rec = {
        "ts": time.time(),
        "method": flow.request.method,
        "url": flow.request.pretty_url,
        "host": flow.request.pretty_host,
        "port": flow.request.port,
        "status": None,
        "req_headers": dict(flow.request.headers),
        "req_body": _encode_body(_decoded_content(flow.request)),
        "resp_headers": {},
        "resp_body": None,
        "client_addr": flow.client_conn.peername[0] if flow.client_conn.peername else "",
        "error": str(flow.error.msg) if flow.error else "unknown error",
    }
    _write(rec)


def done():
    global _fh
    if _fh:
        try:
            _fh.close()
        except Exception:
            pass
        _fh = None
