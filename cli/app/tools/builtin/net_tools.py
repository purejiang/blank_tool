#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Network tools for the workflow engine (stdlib urllib only).

Two atomic tools:
  - ``net.download``: stream a URL to a local file with chunked reads,
    integrity checking and optional progress callbacks.
  - ``net.request``:  perform an HTTP request and expose the raw response
    (status code, headers, body) plus a JSON-parsed body when applicable.

Only the Python standard library is used (``urllib.request``,
``urllib.error``, ``json``, ``os``) — no external dependencies.

Proxy behaviour
---------------
Both tools honor the ambient proxy configuration by default: the opener is
built by :func:`urllib.request.build_opener`, whose default ``ProxyHandler``
reads ``http_proxy`` / ``https_proxy`` / ``no_proxy`` (and, on Windows, the
IE/WinINET registry settings when ``ProxyEnable=1``).  An unreachable proxy
surfaces as ``{"error": "network error: [WinError 10061] ..."}``; a proxy
that silently drops packets surfaces as ``{"error": "network error: timed
out"}`` once the socket timeout expires — never as an indefinite hang.

The optional ``proxy`` input overrides that: ``""``/absent keeps the ambient
behaviour, ``"direct"``/``"none"`` bypasses every proxy, and any other value
is used as an explicit ``http``+``https`` proxy URL (which *replaces* the
ambient handler, so ``no_proxy`` no longer applies to that node).

Cancellation
------------
Both tools poll ``ToolContext.cancelled()`` between 64 KiB chunks and raise
:class:`~app.common.exceptions.WorkflowCancelled`, so a cancelled run stops
instead of finishing the transfer.  A single blocked socket read can still
take up to the socket ``timeout`` (30s by default) to notice.
"""

import http.client
import json
import os
import socket
import time
from typing import Any, Optional, Tuple

from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from app.common.exceptions import WorkflowCancelled
from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.tools.builtin.base import BuiltinTool, ToolContext

_CHUNK_SIZE = 64 * 1024
_DEFAULT_USER_AGENT = "BlankTool/1.0"
_MAX_REDIRECTS = 5

#: Default per-socket-operation timeout, in seconds.
_DEFAULT_TIMEOUT = 30

#: Default cap on a ``net.request`` body, in bytes (0 disables the cap).
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024

#: Progress events are throttled to one per this many bytes...
_PROGRESS_MIN_BYTES = 1024 * 1024
#: ...or this many seconds, whichever comes first (the last one always fires).
_PROGRESS_MIN_SECONDS = 0.5

#: Proxy values that mean "do not use any proxy".
_DIRECT_PROXY_VALUES = ("direct", "none")


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


def _numeric_input(value: Any, default: int, minimum: int = 0) -> int:
    """Coerce *value* to an int >= *minimum*, else return *default*.

    Bools are rejected (``True`` is not a timeout) and non-numeric or
    out-of-range values fall back to the documented default instead of
    producing a surprising zero.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    value = int(value)
    return value if value >= minimum else default


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


def _build_opener(proxy: Optional[str]):
    """Build an opener for *proxy*.

    Args:
        proxy: ``None``/empty = honor the environment and system proxy;
            ``"direct"``/``"none"`` = bypass every proxy; anything else = an
            explicit ``http``/``https`` proxy URL.

    Returns:
        An ``OpenerDirector``, or ``None`` when *proxy* is not a usable URL
        (the caller turns that into an ``{"error": ...}`` result).
    """
    redirect = _LimitedRedirectHandler()
    if proxy is None or not str(proxy).strip():
        return build_opener(redirect)
    value = str(proxy).strip()
    if value.lower() in _DIRECT_PROXY_VALUES:
        # An empty mapping disables proxying; the handler is dropped from
        # ``opener.handlers`` but ``proxy_open`` still short-circuits.
        return build_opener(ProxyHandler({}), redirect)
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return build_opener(ProxyHandler({"http": value, "https": value}), redirect)


def _opener_for(proxy: Optional[str]) -> Tuple[Optional[Any], Optional[dict]]:
    """Return ``(opener, error_result)`` for the ``proxy`` input."""
    opener = _build_opener(proxy)
    if opener is None:
        return None, {"error": f"invalid proxy: {proxy!r}"}
    return opener, None


class NetDownload(BuiltinTool):
    """Download a URL to a local file, streaming to disk with progress.

    The response is read in 64 KiB chunks and written to a sibling ``.part``
    file that is renamed onto ``dest`` only after the transfer completed and
    — when the server declared a ``Content-Length`` — the byte count matched.
    A failed, cancelled or truncated download therefore never leaves a
    half-written file at ``dest``.

    When ``context.stream_handler`` is set it receives
    ``{"type": "progress", "downloaded": <bytes>, "total": <bytes>}`` events
    (``total`` is None when the server omits ``Content-Length``), throttled to
    one event per MiB / half second with the final event always emitted.
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
            Port("timeout", TypeAnnotation(BaseType.NUMBER), False, "Per-socket-operation timeout in seconds (default 30)."),
            Port("max_seconds", TypeAnnotation(BaseType.NUMBER), False, "Overall wall-clock budget for the transfer in seconds (default 0 = no limit)."),
            Port("proxy", TypeAnnotation(BaseType.TEXT), False, "Proxy override: empty/absent honors the environment and system proxy, 'direct' bypasses every proxy, any other value is an explicit proxy URL."),
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
            inputs: url/dest (required); headers, timeout, max_seconds and
                proxy (optional).
            context: Execution environment (work dir, stream handler,
                cancellation).

        Returns:
            dict: ``{"path", "size", "status_code"}`` on success, or an
            ``{"error": <message>}`` dict on failure.

        Raises:
            WorkflowCancelled: when the run was cancelled mid-transfer.
        """
        url = inputs["url"]
        dest_path = os.path.abspath(os.path.join(context.work_dir, inputs["dest"]))
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        timeout = _numeric_input(inputs.get("timeout"), _DEFAULT_TIMEOUT, minimum=1)
        max_seconds = _numeric_input(inputs.get("max_seconds"), 0)
        opener, error = _opener_for(inputs.get("proxy"))
        if error is not None:
            return error

        req = Request(url, headers=_request_headers(inputs.get("headers")))
        # Per-process part name: two concurrent runs must not clobber each
        # other's partial file (they share the destination path).
        part_path = f"{dest_path}.{os.getpid()}.part"
        deadline = time.monotonic() + max_seconds if max_seconds > 0 else None

        try:
            with opener.open(req, timeout=timeout) as resp:
                status = resp.getcode()
                if not 200 <= status < 300:
                    return {"error": f"HTTP {status} error while downloading"}
                total = resp.headers.get("Content-Length")
                try:
                    total = int(total) if total else None
                except (TypeError, ValueError):
                    total = None
                downloaded = 0
                last_report = (0, time.monotonic())
                with open(part_path, "wb") as f:
                    while True:
                        if context.cancelled():
                            raise WorkflowCancelled()
                        if deadline is not None and time.monotonic() > deadline:
                            return {
                                "error": f"download timed out after {max_seconds}s"
                            }
                        chunk = resp.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        done = total is not None and downloaded >= total
                        last_report = self._report_progress(
                            context, downloaded, total, last_report, force=done
                        )
                if downloaded != last_report[0]:
                    self._report_progress(
                        context, downloaded, total, last_report, force=True
                    )
                if total is not None and downloaded != total:
                    # A truncated body must never masquerade as a success.
                    return {
                        "error": f"download truncated: {downloaded} of {total} bytes"
                    }
                os.replace(part_path, dest_path)
                return {"path": dest_path, "size": downloaded, "status_code": status}
        except WorkflowCancelled:
            raise
        except HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.reason}"}
        except URLError as e:
            return {"error": f"network error: {e.reason}"}
        except (http.client.HTTPException, socket.timeout, TimeoutError) as e:
            return {"error": f"network error: {e}"}
        except (OSError, ValueError) as e:
            return {"error": f"download failed: {e}"}
        finally:
            _discard_part(part_path)

    @staticmethod
    def _report_progress(
        context: ToolContext,
        downloaded: int,
        total: Optional[int],
        last: Tuple[int, float],
        *,
        force: bool = False,
    ) -> Tuple[int, float]:
        """Emit a throttled progress event; return the new (bytes, time) mark."""
        now = time.monotonic()
        last_bytes, last_time = last
        if not force:
            if (downloaded - last_bytes) < _PROGRESS_MIN_BYTES and (
                now - last_time
            ) < _PROGRESS_MIN_SECONDS:
                return last
        if context.stream_handler is not None:
            context.stream_handler({
                "type": "progress",
                "downloaded": downloaded,
                "total": total,
            })
        return downloaded, now


class NetRequest(BuiltinTool):
    """Perform an HTTP request and expose the response.

    Returns the status code, response headers, raw body and a JSON-parsed
    body when the response content type indicates JSON.  HTTP error
    responses (4xx/5xx) are returned as regular results (status code + body)
    unless ``fail_on_http_error`` is true; only genuine transport failures
    produce an ``{"error": ...}`` dict — note this asymmetry with
    ``net.download``, which treats 4xx/5xx as a failure.

    The body is read in 64 KiB chunks and is capped by ``max_bytes``
    (default 10 MiB) so an unexpectedly large response cannot exhaust memory.
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
            Port("timeout", TypeAnnotation(BaseType.NUMBER), False, "Per-socket-operation timeout in seconds (default 30)."),
            Port("max_bytes", TypeAnnotation(BaseType.NUMBER), False, "Maximum response body size in bytes (default 10485760; 0 = unlimited)."),
            Port("max_seconds", TypeAnnotation(BaseType.NUMBER), False, "Overall wall-clock budget for the request in seconds (default 0 = no limit)."),
            Port("proxy", TypeAnnotation(BaseType.TEXT), False, "Proxy override: empty/absent honors the environment and system proxy, 'direct' bypasses every proxy, any other value is an explicit proxy URL."),
            Port("fail_on_http_error", TypeAnnotation(BaseType.BOOLEAN), False, "When true a 4xx/5xx response becomes an error instead of a normal result (default false)."),
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
            inputs: url (required); method/headers/body/timeout/max_bytes/
                max_seconds/proxy/fail_on_http_error (optional).
            context: Execution environment (work dir, cancellation).

        Returns:
            dict: ``{"status_code", "headers", "body", "json"}`` for any HTTP
            response (including 4xx/5xx unless ``fail_on_http_error``), or
            ``{"error": <message>}`` on a network-level failure.

        Raises:
            WorkflowCancelled: when the run was cancelled while reading.
        """
        url = inputs["url"]
        method = inputs.get("method") or "GET"
        timeout = _numeric_input(inputs.get("timeout"), _DEFAULT_TIMEOUT, minimum=1)
        max_bytes = _numeric_input(inputs.get("max_bytes"), _DEFAULT_MAX_BYTES)
        max_seconds = _numeric_input(inputs.get("max_seconds"), 0)
        fail_on_http_error = bool(inputs.get("fail_on_http_error"))
        body = inputs.get("body")
        data = body.encode("utf-8") if body else None
        opener, error = _opener_for(inputs.get("proxy"))
        if error is not None:
            return error

        req = Request(
            url,
            data=data,
            headers=_request_headers(inputs.get("headers")),
            method=method,
        )
        deadline = time.monotonic() + max_seconds if max_seconds > 0 else None

        try:
            with opener.open(req, timeout=timeout) as resp:
                body_text, read_error = self._read_body(
                    resp, context, max_bytes, deadline, max_seconds
                )
                if read_error is not None:
                    return read_error
                return {
                    "status_code": resp.getcode(),
                    "headers": dict(resp.headers),
                    "body": body_text,
                    "json": _parse_json(resp.headers, body_text),
                }
        except HTTPError as e:
            if fail_on_http_error:
                return {"error": f"HTTP {e.code}: {e.reason}"}
            body_text, read_error = self._read_body(
                e, context, max_bytes, deadline, max_seconds
            )
            if read_error is not None:
                return read_error
            return {
                "status_code": e.code,
                "headers": dict(e.headers),
                "body": body_text,
                "json": _parse_json(e.headers, body_text),
            }
        except WorkflowCancelled:
            raise
        except URLError as e:
            return {"error": f"network error: {e.reason}"}
        except (http.client.HTTPException, socket.timeout, TimeoutError) as e:
            return {"error": f"network error: {e}"}
        except (OSError, ValueError) as e:
            return {"error": f"request failed: {e}"}

    @staticmethod
    def _read_body(
        response,
        context: ToolContext,
        max_bytes: int,
        deadline: Optional[float],
        max_seconds: int,
    ) -> Tuple[Optional[str], Optional[dict]]:
        """Read a response body in chunks, capped and cancellable.

        Returns:
            ``(body_text, None)`` on success or ``(None, {"error": ...})``
            when the body exceeded *max_bytes* / the deadline expired.

        Raises:
            WorkflowCancelled: when the run was cancelled while reading.
        """
        declared = response.headers.get("Content-Length")
        if declared and max_bytes:
            try:
                if int(declared) > max_bytes:
                    return None, {
                        "error": (
                            f"response too large: {declared} bytes > "
                            f"max_bytes ({max_bytes})"
                        )
                    }
            except (TypeError, ValueError):
                pass  # a malformed header is not a size signal

        chunks = []
        received = 0
        while True:
            if context.cancelled():
                raise WorkflowCancelled()
            if deadline is not None and time.monotonic() > deadline:
                return None, {"error": f"request timed out after {max_seconds}s"}
            chunk = response.read(_CHUNK_SIZE)
            if not chunk:
                break
            received += len(chunk)
            if max_bytes and received > max_bytes:
                return None, {
                    "error": f"response too large: more than {max_bytes} bytes"
                }
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", errors="replace"), None


def _discard_part(part_path: str) -> None:
    """Remove a leftover ``.part`` file (best-effort; post-replace it is gone)."""
    try:
        if os.path.exists(part_path):
            os.remove(part_path)
    except OSError:
        pass
