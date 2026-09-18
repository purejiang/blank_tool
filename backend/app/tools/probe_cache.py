#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""On-disk cache of tool probe verdicts.

Probing a tool costs subprocess launches — up to two per tool, and four of the
seven tools are JVM programs whose cold start dominates the app's first paint.
A verdict only changes when the binary behind a path changes (or when the
environment that resolved it changes), so it is cached in
``<cache_dir>/tool-probes.json`` and reused while

* the file's ``mtime_ns`` + ``size`` are unchanged, and
* the probe key (which path/mode produced the verdict) is unchanged, and
* the environment fingerprint (app version, java, runtime dir) is unchanged.

Everything here is best-effort: a missing, unreadable or corrupt cache is just
a cache miss. Nothing in this module raises into a probe.

The document keeps **one entry per tool name** — the resolution that was probed
last. Switching a tool between its default path and a custom override therefore
costs one probe; that is a user action, and it buys a much simpler document
than tracking one entry per probe key.
"""

import json
import os
import threading
import time
from typing import Any, Dict, Optional

from app.utils.env import (
    ENV_APP_VERSION,
    get_cache_dir,
    get_env,
    get_java_bin,
    get_runtime_dir,
)
from app.utils.logger import Logger

logger = Logger.get_logger("ToolProbeCache")

# Bump whenever the meaning of a stored entry changes.
SCHEMA_VERSION = 1
CACHE_FILENAME = "tool-probes.json"

# A tool that could not be resolved (no file to stat) has nothing to validate
# the entry against, so the entry is aged out instead. Short on purpose: a tool
# installed right after a launch should be picked up without an app restart.
NEGATIVE_TTL_SECONDS = 300

_save_lock = threading.Lock()


# ------------------------------------------------------------------
# Document lifecycle
# ------------------------------------------------------------------

def cache_path() -> str:
    """Absolute path of the cache document inside ``BT_CACHE_DIR``."""
    return os.path.join(get_cache_dir(), CACHE_FILENAME)


def fingerprint() -> Dict[str, str]:
    """Environment values that can change any probe verdict on their own.

    The resolved binary paths already key each entry; these are the inputs
    that are *not* part of a path: which java runs the jar tools, where the
    bundled runtime lives, and which app build produced the verdict.
    """
    return {
        "app_version": get_env(ENV_APP_VERSION, "") or "",
        "java_bin": get_java_bin() or "",
        "runtime_dir": get_runtime_dir() or "",
    }


def new_doc() -> Dict[str, Any]:
    """An empty cache document stamped with the current schema/fingerprint."""
    return {
        "schema": SCHEMA_VERSION,
        "fingerprint": fingerprint(),
        "tools": {},
    }


def load(path: Optional[str] = None) -> Dict[str, Any]:
    """Read the cache document; an empty one on any problem.

    A stale schema, a changed fingerprint or unparsable JSON all mean the
    same thing to the caller: no reusable entries.
    """
    try:
        with open(path or cache_path(), "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return new_doc()

    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA_VERSION:
        return new_doc()
    if doc.get("fingerprint") != fingerprint():
        return new_doc()
    tools = doc.get("tools")
    if not isinstance(tools, dict):
        return new_doc()
    doc["tools"] = {k: v for k, v in tools.items() if isinstance(v, dict)}
    return doc


def save(doc: Dict[str, Any], path: Optional[str] = None) -> None:
    """Atomically replace the cache document. Never raises."""
    target = path or cache_path()
    with _save_lock:
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            tmp = f"{target}.tmp-{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
            os.replace(tmp, target)
        except OSError as e:
            # A cache we cannot write is a slow start, not a broken one.
            logger.warning(f"tool probe cache not written: {e}")


# ------------------------------------------------------------------
# Entries
# ------------------------------------------------------------------

def make_key(
    name: str,
    *,
    search_system: bool,
    default_path: str,
    custom_path: str = "",
) -> Dict[str, Any]:
    """Identity of one probe: every input that can change its verdict.

    ``search_system`` matters because it changes how the path is *resolved*
    (PATH lookup vs. bundled runtime), and the outcome of that resolution is
    what gets cached.
    """
    return {
        "name": name,
        "search_system": bool(search_system),
        "default_path": default_path or "",
        "custom_path": custom_path or "",
    }


def negative_ttl() -> int:
    """Seconds a "could not resolve" entry stays fresh (``BT_TOOL_PROBE_TTL``)."""
    raw = get_env("BT_TOOL_PROBE_TTL")
    if raw:
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            pass
    return NEGATIVE_TTL_SECONDS


def get_entry(
    doc: Dict[str, Any],
    key: Dict[str, Any],
    now: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Return a reusable entry for *key*, or ``None`` when a re-probe is due."""
    entry = (doc.get("tools") or {}).get(key.get("name"))
    if not isinstance(entry, dict):
        return None
    if entry.get("key") != key:
        return None

    path = entry.get("path") or ""
    if not path:
        # Unresolved tool — nothing to stat, so age decides.
        age = (now if now is not None else time.time()) - (entry.get("probed_at") or 0)
        return entry if age < negative_ttl() else None

    try:
        st = os.stat(path)
    except OSError:
        return None
    if entry.get("mtime_ns") != st.st_mtime_ns or entry.get("size") != st.st_size:
        return None
    return entry


def store(
    doc: Dict[str, Any],
    key: Dict[str, Any],
    *,
    path: str,
    is_valid: bool,
    version: str,
) -> Dict[str, Any]:
    """Record one probe result in *doc* (the caller persists it)."""
    entry: Dict[str, Any] = {
        "key": key,
        "path": path or "",
        "is_valid": bool(is_valid),
        "version": version or "",
        "probed_at": time.time(),
    }
    if path:
        try:
            st = os.stat(path)
            entry["mtime_ns"] = st.st_mtime_ns
            entry["size"] = st.st_size
        except OSError:
            # Raced away between probe and store — keep it, but as an
            # unresolved entry so the stat check does not lie later.
            entry["path"] = ""
    (doc.setdefault("tools", {}))[key.get("name")] = entry
    return entry


def invalidate(doc: Dict[str, Any], name: str) -> None:
    """Drop one tool's entry (custom path changed, forced refresh)."""
    (doc.get("tools") or {}).pop(name, None)


def invalidate_all(doc: Dict[str, Any]) -> None:
    """Drop every entry."""
    doc["tools"] = {}
