#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mitmproxy addon — append every completed HTTP(S) exchange to a JSONL file.

Runs INSIDE mitmdump (passed via ``mitmdump -s <this file>``), so importing
``mitmproxy`` here is fine — unlike the rest of ``backend/`` which stays
stdlib-only. Configuration comes from environment variables:

  TRAFFIC_JSONL       output file, one JSON object per line (required)
  TRAFFIC_HOST_FILTER optional substring; only flows whose host contains it
                      are recorded (empty = record everything)
  TRAFFIC_MAX_BODY    bodies larger than this are replaced by a
                      ``{"truncated": true, "size": N}`` marker (default 16 KiB)

One record per response::

  {ts, method, url, host, port, status, req_headers, req_body,
   resp_headers, resp_body, client_addr, error}

``req_body`` / ``resp_body`` are ``{"text": ...}`` when UTF-8 decodable,
``{"b64": ...}`` for binary, or the truncation marker.
"""

import base64
import json
import os
import time

from mitmproxy import http

_OUT = os.environ.get("TRAFFIC_JSONL", "")
_HOST_FILTER = os.environ.get("TRAFFIC_HOST_FILTER", "")
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


def response(flow: http.HTTPFlow) -> None:
    global _fh, _count
    if not _OUT:
        return
    if _HOST_FILTER and _HOST_FILTER not in flow.request.pretty_host:
        return
    rec = {
        "ts": time.time(),
        "method": flow.request.method,
        "url": flow.request.pretty_url,
        "host": flow.request.pretty_host,
        "port": flow.request.port,
        "status": flow.response.status_code if flow.response else None,
        "req_headers": dict(flow.request.headers),
        "req_body": _encode_body(flow.request.raw_content),
        "resp_headers": dict(flow.response.headers) if flow.response else {},
        "resp_body": _encode_body(flow.response.raw_content) if flow.response else None,
        "client_addr": flow.client_conn.peername[0] if flow.client_conn.peername else "",
        "error": str(flow.error.msg) if flow.error else None,
    }
    try:
        if _fh is None:
            _fh = open(_OUT, "a", encoding="utf-8")
        _fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _fh.flush()
        _count += 1
    except Exception:
        # never let a write failure kill the proxy
        pass


def done():
    global _fh
    if _fh:
        try:
            _fh.close()
        except Exception:
            pass
        _fh = None
