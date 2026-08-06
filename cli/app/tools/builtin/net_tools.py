#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Network tools for the workflow engine (stdlib urllib only).

Two atomic tools:
  - ``net.download``: stream a URL to a local file with chunked reads and
    optional progress callbacks.
  - ``net.request``:  perform an HTTP request and expose the raw response
    (status code, headers, body) plus a JSON-parsed body when applicable.

Only the Python standard library is used (``urllib.request``,
``urllib.error``, ``json``, ``os``) — no external dependencies.
"""

import json
import os
from typing import Optional

from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.tools.builtin.base import BuiltinTool, ToolContext

_CHUNK_SIZE = 64 * 1024
_DEFAULT_USER_AGENT = "BlankTool/1.0"
_MAX_REDIRECTS = 5


class _LimitedRedirectHandler(HTTPRedirectHandler):
    """``HTTPRedirectHandler`` capped at 5 redirects (urllib defaults to 10)."""

    max_redirections = _MAX_REDIRECTS


def _request_headers(extra: dict) -> dict:
    """Merge a default User-Agent with caller-supplied headers.

    Args:
        extra: Caller-supplied headers (may override the User-Agent).

    Returns:
        dict: Header map with string values (urllib requires them).
    """
    headers = {"User-Agent": _DEFAULT_USER_AGENT}
    headers.update({str(k): str(v) for k, v in (extra or {}).items()})
    return headers


def _parse_json(headers, body_text: str):
    """Parse ``body_text`` as JSON when the response content type is JSON.

    Args:
        headers: Response headers (mapping-like, e.g. ``email.message.Message``).
        body_text: Decoded response body.

    Returns:
        object | None: The parsed JSON value, or None when the content type
        is not JSON or the body is not valid JSON.
    """
    content_type = (headers.get("Content-Type") or "").lower()
    if "json" not in content_type:
        return None
    try:
        return json.loads(body_text)
    except ValueError:
        return None


class NetDownload(BuiltinTool):
    """Download a URL to a local file, streaming to disk with progress.

    The response is read in 64 KiB chunks and written directly to ``dest``.
    Redirects are followed (up to 5).  When ``context.stream_handler`` is set
    it receives ``{"type": "progress", "downloaded": <bytes>, "total": <bytes>}``
    events; ``total`` is None when the server omits ``Content-Length``.
    """

    name = "net.download"
    description = (
        "Download a file from a URL to a local destination path, streaming "
        "the response to disk and reporting progress."
    )
    ports = PortSet(
        inputs=[
            Port("url", TypeAnnotation(BaseType.TEXT), True, "The URL to download from."),
            Port("dest", TypeAnnotation(BaseType.FILE), True, "Destination file path; relative paths resolve against the work dir."),
            Port("headers", TypeAnnotation(BaseType.JSON), False, "Extra HTTP request headers (default {})."),
        ],
        outputs=[
            Port("path", TypeAnnotation(BaseType.FILE), True, "Absolute path of the written file."),
            Port("size", TypeAnnotation(BaseType.NUMBER), True, "Number of bytes written."),
            Port("status_code", TypeAnnotation(BaseType.NUMBER), True, "HTTP status code of the final response."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        """Stream ``inputs["url"]`` to ``inputs["dest"]``.

        Args:
            inputs: url (required), dest (required), headers (optional).
            context: Execution environment (work dir, stream handler).

        Returns:
            dict: ``{"path", "size", "status_code"}`` on success, or an
            ``{"error": <message>}`` dict on failure.
        """
        url = inputs["url"]
        dest_path = os.path.abspath(os.path.join(context.work_dir, inputs["dest"]))
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        req = Request(url, headers=_request_headers(inputs.get("headers")))
        opener = build_opener(_LimitedRedirectHandler())

        try:
            with opener.open(req, timeout=30) as resp:
                status = resp.getcode()
                if not 200 <= status < 300:
                    return {"error": f"HTTP {status} error while downloading"}
                total = resp.headers.get("Content-Length")
                total = int(total) if total else None
                downloaded = 0
                with open(dest_path, "wb") as f:
                    while True:
                        chunk = resp.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        self._report_progress(context, downloaded, total)
                return {"path": dest_path, "size": downloaded, "status_code": status}
        except HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.reason}"}
        except URLError as e:
            return {"error": f"network error: {e.reason}"}
        except (OSError, ValueError) as e:
            return {"error": f"download failed: {e}"}

    @staticmethod
    def _report_progress(context: ToolContext, downloaded: int, total: Optional[int]) -> None:
        """Emit a progress event through ``context.stream_handler`` when set."""
        if context.stream_handler is None:
            return
        context.stream_handler({
            "type": "progress",
            "downloaded": downloaded,
            "total": total,
        })


class NetRequest(BuiltinTool):
    """Perform an HTTP request and expose the response.

    Returns the status code, response headers, raw body and a JSON-parsed
    body when the response content type indicates JSON.  HTTP error
    responses (4xx/5xx) are returned as regular results (status code + body);
    only genuine network failures produce an ``{"error": ...}`` dict.
    """

    name = "net.request"
    description = (
        "Perform an HTTP request and return the status code, headers, body "
        "and a JSON-parsed body when the response is JSON."
    )
    ports = PortSet(
        inputs=[
            Port("url", TypeAnnotation(BaseType.TEXT), True, "The URL to request."),
            Port("method", TypeAnnotation(BaseType.TEXT), False, "HTTP method (default \"GET\")."),
            Port("headers", TypeAnnotation(BaseType.JSON), False, "Extra HTTP request headers (default {})."),
            Port("body", TypeAnnotation(BaseType.TEXT), False, "Request body for methods like POST/PUT."),
            Port("timeout", TypeAnnotation(BaseType.NUMBER), False, "Request timeout in seconds (default 30)."),
        ],
        outputs=[
            Port("status_code", TypeAnnotation(BaseType.NUMBER), True, "HTTP status code."),
            Port("headers", TypeAnnotation(BaseType.JSON), True, "Response headers as a dict."),
            Port("body", TypeAnnotation(BaseType.TEXT), True, "Raw response body as text."),
            Port("json", TypeAnnotation(BaseType.JSON), True, "JSON-parsed body, or None when not JSON."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        """Perform the request described by ``inputs``.

        Args:
            inputs: url (required), method/headers/body/timeout (optional).
            context: Execution environment (work dir, unused by this tool).

        Returns:
            dict: ``{"status_code", "headers", "body", "json"}`` for any HTTP
            response (including 4xx/5xx), or ``{"error": <message>}`` on a
            network-level failure.
        """
        url = inputs["url"]
        method = inputs.get("method") or "GET"
        timeout = inputs.get("timeout") or 30
        body = inputs.get("body")
        data = body.encode("utf-8") if body else None
        req = Request(
            url,
            data=data,
            headers=_request_headers(inputs.get("headers")),
            method=method,
        )
        opener = build_opener(_LimitedRedirectHandler())

        try:
            with opener.open(req, timeout=timeout) as resp:
                body_text = resp.read().decode("utf-8", errors="replace")
                return {
                    "status_code": resp.getcode(),
                    "headers": dict(resp.headers),
                    "body": body_text,
                    "json": _parse_json(resp.headers, body_text),
                }
        except HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            return {
                "status_code": e.code,
                "headers": dict(e.headers),
                "body": body_text,
                "json": _parse_json(e.headers, body_text),
            }
        except URLError as e:
            return {"error": f"network error: {e.reason}"}
        except (OSError, ValueError) as e:
            return {"error": f"request failed: {e}"}
