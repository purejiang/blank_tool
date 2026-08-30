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

    {"history": {"enabled": true, "max_runs": 200}}

Both keys are optional (defaults: enabled, 200 runs).  ``max_runs: 0``
prunes every write immediately (history effectively off but still writing).
Writes are atomic (``*.tmp`` + ``os.replace``).
"""

import json
import logging
import os
import re
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
    """Delete oldest ``*.json`` files beyond the retention cap (by mtime)."""
    max_runs = _max_runs()
    try:
        files = [f for f in os.listdir(history_dir) if f.endswith(".json")]
    except OSError:
        return
    if len(files) <= max_runs:
        return
    files.sort(key=lambda f: os.path.getmtime(os.path.join(history_dir, f)))
    for stale in files[: len(files) - max_runs]:
        try:
            os.remove(os.path.join(history_dir, stale))
        except OSError:
            logger.warning("history: failed to prune %s", stale)


def list_runs(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Return newest-first run summaries (corrupt files skipped).

    Args:
        limit: maximum number of summaries; ``0`` means no limit.
        offset: number of newest summaries to skip.
    """
    history_dir = _history_dir()
    if not os.path.isdir(history_dir):
        return []
    files = [f for f in os.listdir(history_dir) if f.endswith(".json")]
    files.sort(
        key=lambda f: os.path.getmtime(os.path.join(history_dir, f)),
        reverse=True,
    )

    summaries = []
    for fname in files:
        record = _read(os.path.join(history_dir, fname))
        if record is None:
            continue
        summaries.append({key: record.get(key) for key in _SUMMARY_KEYS})

    if offset:
        summaries = summaries[max(0, offset):]
    if limit and limit > 0:
        summaries = summaries[:limit]
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
    if not os.path.isfile(path):
        return False
    os.remove(path)
    return True


def clear_runs() -> int:
    """Delete every history file; returns the number removed."""
    history_dir = _history_dir()
    if not os.path.isdir(history_dir):
        return 0
    removed = 0
    for fname in os.listdir(history_dir):
        if not fname.endswith(".json"):
            continue
        try:
            os.remove(os.path.join(history_dir, fname))
            removed += 1
        except OSError:
            logger.warning("history: failed to remove %s", fname)
    return removed
