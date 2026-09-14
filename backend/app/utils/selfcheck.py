#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Installation self-check behind the diagnostics page's "system self-check" card.

Answers one question — *can this installation actually do its job?* — as a list
of small, independent probes over the **backend's own** view of the world:
directory usability, interpreter / JVM resolution, and the proxy environment.

Scope is deliberately narrow. Facts only the Electron side knows (app version,
IPC health) or only the tool registry knows (``tool.get_tools``) are composed by
the renderer. Keeping those out means this module never imports ``ToolManager``
or touches ``appStore`` — it stays a pure "what does the process see" probe.

Every check carries a stable machine-readable ``id`` plus a raw ``value``
(a path, a version, a URL — never a sentence). The renderer owns all wording, so
the report stays translatable; ``facts`` carries the few extra fields it needs
to pick the right status or hint.

Status vocabulary:
  ``ok``   — healthy, nothing to do
  ``warn`` — works, but with a caveat worth knowing (uncontrolled version,
             dependency that will be created on demand, ...)
  ``fail`` — a real defect that breaks a feature
"""

import os
import platform
import shutil
import socket
import subprocess
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.utils.env import (
    ROOT,
    get_auto_tasks_root,
    get_cache_dir,
    get_env,
    get_java_bin,
    get_output_dir,
    get_python_bin,
    get_runtime_dir,
    get_tasks_root,
)

OK = "ok"
WARN = "warn"
FAIL = "fail"

CAT_ENV = "env"
CAT_CONFIG = "config"


def _item(
    check_id: str,
    category: str,
    status: str,
    value: str,
    facts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "id": check_id,
        "category": category,
        "status": status,
        "value": value,
    }
    if facts:
        item["facts"] = facts
    return item


def _join(*parts: str) -> str:
    return " · ".join(p for p in parts if p)


def _writable(path: str) -> bool:
    """Probe writability by really creating and removing a temp file.

    ``os.access`` is unreliable on Windows — it reports the ACL verdict, which
    routinely disagrees with reality for a non-elevated process. Creating the
    file is the only honest test, and the context manager removes it again.
    """
    try:
        with tempfile.NamedTemporaryFile(
            dir=path, prefix=".selfcheck-", delete=True
        ):
            return True
    except Exception:
        return False


def _dir_check(
    check_id: str,
    path: str,
    *,
    writable: bool = True,
    auto_created: bool = False,
) -> Dict[str, Any]:
    if not path:
        return _item(check_id, CAT_CONFIG, FAIL, "", {"reason": "unresolved"})
    if not os.path.isdir(path):
        # A directory the app creates on demand isn't a defect, just a state.
        return _item(
            check_id,
            CAT_CONFIG,
            WARN if auto_created else FAIL,
            path,
            {"reason": "missing"},
        )
    if writable and not _writable(path):
        return _item(check_id, CAT_CONFIG, FAIL, path, {"reason": "readonly"})
    return _item(check_id, CAT_CONFIG, OK, path)


def _created_dir_check(
    check_id: str, getter: Callable[[], str]
) -> Dict[str, Any]:
    """Check a directory whose getter ``makedirs`` it as a side effect.

    That side effect *is* the probe: if the directory cannot be created or
    reached, the exception is the finding.
    """
    try:
        path = getter()
    except Exception as e:  # noqa: BLE001 — the message is the finding
        return _item(
            check_id,
            CAT_CONFIG,
            FAIL,
            f"{type(e).__name__}: {e}",
            {"reason": "unusable"},
        )
    return _dir_check(check_id, path)


# ---------------------------------------------------------------------------
# Environment probes
# ---------------------------------------------------------------------------

def _os_check() -> Dict[str, Any]:
    return _item(
        "env.os",
        CAT_ENV,
        OK,
        _join(platform.system(), platform.release(), platform.machine()),
    )


def _python_check() -> Dict[str, Any]:
    path = get_python_bin()
    if not path:
        return _item("env.python", CAT_ENV, FAIL, "", {"reason": "unresolved"})
    exists = os.path.exists(path) if os.path.isabs(path) else bool(shutil.which(path))
    if not exists:
        return _item("env.python", CAT_ENV, FAIL, path, {"reason": "missing"})
    # The backend *is* this interpreter, so the version is free — no subprocess.
    return _item("env.python", CAT_ENV, OK, _join(platform.python_version(), path))


def _java_version(path: str) -> str:
    """Run ``java -version`` and pull the quoted version out of stderr."""
    try:
        result = subprocess.run(
            [path, "-version"], capture_output=True, text=True, timeout=10
        )
        for line in (result.stderr or "").splitlines():
            if "version" in line and '"' in line:
                return line.split('"')[1]
    except Exception:
        pass
    return ""


def _java_check() -> Dict[str, Any]:
    path = get_java_bin()
    runtime_dir = get_runtime_dir()

    if path and os.path.isabs(path) and os.path.exists(path):
        in_runtime = bool(runtime_dir) and os.path.abspath(path).lower().startswith(
            os.path.abspath(runtime_dir).lower()
        )
        source = "builtin" if in_runtime else "external"
        version = _java_version(path)
        if not version:
            # Resolved but won't execute — signing / recompiling would fail late.
            return _item(
                "env.java", CAT_ENV, WARN, path, {"source": source, "reason": "not_runnable"}
            )
        return _item("env.java", CAT_ENV, OK, _join(version, path), {"source": source})

    # ``get_java_bin`` falls back to the bare name "java" when nothing usable
    # was found — so an unresolved result means "not installed".
    on_path = shutil.which(path) if path else None
    if on_path:
        return _item(
            "env.java",
            CAT_ENV,
            WARN,
            _join(_java_version(on_path), on_path),
            {"source": "system"},
        )
    return _item("env.java", CAT_ENV, FAIL, "", {"source": "none"})


def _tcp_ok(host: str, port: int, timeout: float = 0.8) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def _proxy_check() -> Dict[str, Any]:
    """Report the proxy the process would actually use for downloads.

    urllib honours these env vars, so a stale value here is exactly what turns
    a download into ``[WinError 10061]`` — worth surfacing before it happens.
    """
    url = ""
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        url = get_env(key, "")
        if url:
            break
    if not url:
        return _item("env.proxy", CAT_ENV, OK, "", {"configured": False})

    parsed = urlparse(url if "//" in url else f"//{url}")
    host, port = parsed.hostname, parsed.port
    if not host:
        return _item(
            "env.proxy", CAT_ENV, WARN, url, {"configured": True, "reachable": False}
        )
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    reachable = _tcp_ok(host, port)
    return _item(
        "env.proxy",
        CAT_ENV,
        OK if reachable else WARN,
        url,
        {"configured": True, "reachable": reachable, "host": host, "port": port},
    )


def _tool_search_check() -> Dict[str, Any]:
    """Is the tool registry allowed to fall back to the system PATH?

    Convenient, but it makes which binary gets used depend on the machine —
    the one setting that can silently change results between runs.
    """
    enabled = get_env("BT_SEARCH_SYSTEM_TOOLS", "") not in ("", None)
    return _item(
        "config.tool_search",
        CAT_CONFIG,
        WARN if enabled else OK,
        "",
        {"enabled": enabled},
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def build_report() -> Dict[str, Any]:
    """Run every probe and return ``{generated_at, checks}``.

    Order is stable and meaningful: environment first, then configuration —
    the renderer renders checks in the order it receives them.
    """
    checks: List[Dict[str, Any]] = [
        _os_check(),
        _python_check(),
        _java_check(),
        _proxy_check(),
        _dir_check("config.dir.runtime", get_runtime_dir(), writable=False),
        _dir_check("config.dir.backend", ROOT, writable=False),
        _created_dir_check("config.dir.cache", get_cache_dir),
        _created_dir_check("config.dir.tasks", get_tasks_root),
        _created_dir_check("config.dir.auto_tasks", get_auto_tasks_root),
        # ``get_output_dir`` doesn't create — it only resolves.
        _dir_check("config.dir.output", get_output_dir(), auto_created=True),
        _tool_search_check(),
    ]
    return {"generated_at": time.time(), "checks": checks}
