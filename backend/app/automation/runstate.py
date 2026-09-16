#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""In-process registry of the automation runs executing RIGHT NOW.

``summary.json`` (written into each run dir) is the durable index
``automation.list_runs`` reads, but on its own it cannot answer "is this run
still writing?". A backend killed mid-run leaves its ``status: "running"``
summary behind forever, so:

* this module is the authority *inside* the process — the history handler
  asks it before deleting anything (a live run's directory must never be
  removed under the running script), and
* an on-disk ``running`` marker with no matching entry here means the run was
  interrupted (crash / force-quit), which is exactly the "orphan" the storage
  UI has to surface and let the user delete.

Only ``task_id -> run_dir`` is tracked; no device or adb state lives here.
"""

import os
import threading
from typing import Dict, List, Optional

_LOCK = threading.Lock()
_ACTIVE: Dict[str, str] = {}


def _norm(task_id) -> str:
    return str(task_id or "").strip()


def mark_started(task_id: str, run_dir: str) -> None:
    """Register a run as executing in this process."""
    tid = _norm(task_id)
    if not tid:
        return
    with _LOCK:
        _ACTIVE[tid] = os.path.abspath(str(run_dir or ""))


def mark_finished(task_id: str) -> None:
    """Deregister a run (called from the orchestrator's ``finally``)."""
    with _LOCK:
        _ACTIVE.pop(_norm(task_id), None)


def is_active(task_id: str) -> bool:
    with _LOCK:
        return _norm(task_id) in _ACTIVE


def is_active_dir(path) -> bool:
    """True when ``path`` is the run dir of a run executing in this process."""
    if not path:
        return False
    target = os.path.abspath(str(path))
    with _LOCK:
        return any(os.path.abspath(d) == target for d in _ACTIVE.values())


def active_task_ids() -> List[str]:
    with _LOCK:
        return sorted(_ACTIVE)


def active_run_dirs() -> List[str]:
    with _LOCK:
        return sorted(_ACTIVE.values())


def run_dir_for(task_id: str) -> Optional[str]:
    with _LOCK:
        return _ACTIVE.get(_norm(task_id))


def reset() -> None:
    """Drop every registration (tests / process teardown)."""
    with _LOCK:
        _ACTIVE.clear()
