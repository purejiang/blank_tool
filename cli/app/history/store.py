#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run history persistence — one JSON file per top-level workflow run.

The recorder is invoked directly from
:func:`app.workflow.runner.run_workflow` — deliberately NO event bus: with
a single producer (the runner) and a single consumer (this store) a pub/sub
layer is pure indirection.  Only top-level runs are recorded; nested
sub-workflow executions (``workflow.run`` / ``flow.foreach`` /
``flow.branch``) are visible through the parent run's ``node_results``.

Storage: ``<output_dir>/history/<run_id>.json`` (``run_id`` is a uuid4 hex).
Retention and the on/off switch live in ``server.config.json`` under a
``history`` section::

    {"history": {"enabled": true, "max_runs": 200, "max_bytes": 209715200}}

All keys are optional (defaults: enabled, 200 runs, 200 MB).  ``max_runs: 0``
prunes every write immediately (history effectively off but still writing).
Writes are atomic (``*.tmp`` + ``os.replace``).

Retention is bounded by BOTH the run count and the total on-disk size: one run
whose node outputs are large must not be able to push the directory into the
gigabytes.  Listing sorts by mtime first and only parses the requested window,
so a big history directory never blocks the backend's request loop.
"""

import json
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from app.utils.paths import ROOT, resolve_path
from app.env import (
    ENV_BT_SERVER_CONFIG,
    get_env,
    get_output_dir,
)

logger = logging.getLogger(__name__)

#: run_id format: uuid4 hex (32 lowercase hex chars).  Enforced on every
#: path-building entry point so a crafted id cannot escape the history dir.
_RUN_ID_RE = re.compile(r"^[0-9a-f]{32}$")

_DEFAULT_MAX_RUNS = 200

#: Total size cap for the history directory (bytes).
_DEFAULT_MAX_BYTES = 200 * 1024 * 1024

#: Age past which an abandoned ``*.json.tmp`` is deleted (seconds).
_TMP_MAX_AGE_SECONDS = 300

#: Keys projected into ``list_runs`` summaries.
_SUMMARY_KEYS = (
    "run_id",
    "task_id",
    "workflow_name",
    "source",
    "started_at",
    "ended_at",
    "duration_ms",
    "success",
    "error",
)


def new_run_id() -> str:
    """Return a fresh run id (uuid4 hex)."""
    return uuid.uuid4().hex


def _history_dir() -> str:
    return os.path.join(get_output_dir(), "history")


def _config() -> Dict[str, Any]:
    """Read the ``history`` section of ``server.config.json`` (tolerant)."""
    source = get_env(ENV_BT_SERVER_CONFIG, os.path.join(ROOT, "server.config.json"))
    resolved = resolve_path(source)
    if not resolved or not os.path.exists(resolved):
        return {}
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}
    section = raw.get("history") if isinstance(raw, dict) else None
    return section if isinstance(section, dict) else {}


def _enabled() -> bool:
    return bool(_config().get("enabled", True))


def _max_runs() -> int:
    try:
        return max(0, int(_config().get("max_runs", _DEFAULT_MAX_RUNS)))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_RUNS


def _max_bytes() -> int:
    try:
        return max(0, int(_config().get("max_bytes", _DEFAULT_MAX_BYTES)))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_BYTES


def _path_for(run_id: str) -> str:
    """Return the file path for *run_id*; reject anything but uuid4 hex."""
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError(f"invalid run id: {run_id!r}")
    return os.path.join(_history_dir(), f"{run_id}.json")


def _read(path: str) -> Optional[Dict[str, Any]]:
    """Read one history file; corrupt JSON / non-dict yields None."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        logger.warning("history: skipping unreadable file %s", path)
        return None
    return data if isinstance(data, dict) else None


def record_run(record: Dict[str, Any]) -> Optional[str]:
    """Persist *record* as ``<run_id>.json`` and prune to the retention cap.

    Args:
        record: the run record dict; ``run_id`` is generated when absent.

    Returns:
        The run id, or ``None`` when history is disabled in config.
    """
    if not _enabled():
        return None
    run_id = record.get("run_id") or new_run_id()
    record = dict(record, run_id=run_id)

    history_dir = _history_dir()
    os.makedirs(history_dir, exist_ok=True)
    tmp_path = os.path.join(history_dir, f"{run_id}.json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp_path, os.path.join(history_dir, f"{run_id}.json"))

    _prune(history_dir)
    return run_id


def _prune(history_dir: str) -> None:
    """Enforce the retention caps: oldest ``*.json`` by (mtime, name).

    A file is deleted when it is beyond the run-count cap OR when the totals
    still exceed the byte cap.  Sorting ties are broken by file name so the
    outcome is deterministic, and the sweep always frees the oldest records
    first — never the one just written.
    """
    _sweep_orphan_tmp(history_dir)

    max_runs = _max_runs()
    max_bytes = _max_bytes()
    try:
        names = [f for f in os.listdir(history_dir) if f.endswith(".json")]
    except OSError:
        return

    entries = []
    for fname in names:
        path = os.path.join(history_dir, fname)
        try:
            entries.append((os.path.getmtime(path), fname, os.path.getsize(path)))
        except OSError:
            continue
    if not entries:
        return
    entries.sort(key=lambda entry: (entry[0], entry[1]))

    by_count = max(0, len(entries) - max_runs)
    doomed = entries[:by_count]
    remaining = entries[by_count:]
    total = sum(entry[2] for entry in remaining)
    while remaining and total > max_bytes:
        oldest = remaining.pop(0)
        doomed.append(oldest)
        total -= oldest[2]

    for _mtime, fname, _size in doomed:
        try:
            os.remove(os.path.join(history_dir, fname))
        except OSError:
            logger.warning("history: failed to prune %s", fname)


def _sweep_orphan_tmp(history_dir: str) -> None:
    """Delete ``*.json.tmp`` files left behind by an interrupted write.

    Nothing else collects them (they are not ``*.json``), so without this
    sweep a crash mid-dump would leak disk space forever.
    """
    cutoff = time.time() - _TMP_MAX_AGE_SECONDS
    try:
        names = os.listdir(history_dir)
    except OSError:
        return
    for fname in names:
        if not fname.endswith(".json.tmp"):
            continue
        path = os.path.join(history_dir, fname)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            continue


def list_runs(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Return newest-first run summaries (corrupt files skipped).

    Ordering is decided from ``os.stat`` alone; only the requested window is
    parsed, so listing stays cheap however large the history directory grows.

    Args:
        limit: maximum number of summaries; ``0`` means no limit.
        offset: number of newest summaries to skip.
    """
    history_dir = _history_dir()
    if not os.path.isdir(history_dir):
        return []
    try:
        names = [f for f in os.listdir(history_dir) if f.endswith(".json")]
    except OSError:
        return []

    entries = []
    for fname in names:
        try:
            mtime = os.path.getmtime(os.path.join(history_dir, fname))
        except OSError:
            continue
        entries.append((mtime, fname))
    entries.sort(key=lambda entry: (-entry[0], entry[1]))

    window = entries[max(0, offset):]
    if limit and limit > 0:
        window = window[:limit]

    summaries = []
    for _mtime, fname in window:
        record = _read(os.path.join(history_dir, fname))
        if record is None:
            continue
        summaries.append({key: record.get(key) for key in _SUMMARY_KEYS})
    return summaries


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Return the full record for *run_id*, or None when absent/corrupt."""
    path = _path_for(run_id)
    if not os.path.isfile(path):
        return None
    return _read(path)


def delete_run(run_id: str) -> bool:
    """Delete the record for *run_id*; returns True when a file was removed."""
    path = _path_for(run_id)
    try:
        os.remove(path)
    except FileNotFoundError:
        return False
    except OSError:
        logger.warning("history: failed to delete %s", run_id)
        return False
    return True


def clear_runs() -> int:
    """Delete every history file (including orphans); returns the count removed."""
    history_dir = _history_dir()
    if not os.path.isdir(history_dir):
        return 0
    removed = 0
    try:
        names = os.listdir(history_dir)
    except OSError:
        return 0
    for fname in names:
        if not (fname.endswith(".json") or fname.endswith(".json.tmp")):
            continue
        try:
            os.remove(os.path.join(history_dir, fname))
            removed += 1
        except FileNotFoundError:
            continue
        except OSError:
            logger.warning("history: failed to remove %s", fname)
    return removed
