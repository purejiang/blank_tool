#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run-history query handlers.

Exposes the run-history store (:mod:`app.history.store`) over the existing
``call-backend-api`` JSON-RPC channel — no new IPC channels.  The
module-level ``API_MAP`` is auto-discovered by
:class:`app.api_handler.ApiHandler`:

- ``history.list``    newest-first run summaries (``limit`` / ``offset``);
- ``history.get``     full record for one ``run_id``;
- ``history.delete``  remove one record;
- ``history.clear``   remove all records.
"""

from app.common.decorators import logs_errors
from app.common.exceptions import ToolException
from app.history import store as history_store


def _int_param(params: dict, key: str, default: int) -> int:
    """Coerce an integer query param; fall back to *default* on junk."""
    try:
        return int(params.get(key, default))
    except (TypeError, ValueError):
        return default


def _require_run_id(params: dict) -> str:
    run_id = params.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ToolException("Missing 'run_id' field")
    return run_id


@logs_errors("HistoryHandler")
def history_list(params, stream_handler):
    """Return newest-first run summaries.

    Params:
        limit: max summaries (default 50; 0 = no limit).
        offset: skip this many newest summaries (default 0).

    Returns:
        ``{"runs": [{run_id, task_id, workflow_name, source, started_at,
        ended_at, duration_ms, success, error}, ...]}``.
    """
    limit = _int_param(params, "limit", 50)
    offset = _int_param(params, "offset", 0)
    return {"runs": history_store.list_runs(limit=limit, offset=offset)}


@logs_errors("HistoryHandler")
def history_get(params, stream_handler):
    """Return the full record for one run.

    Raises:
        ToolException: when the run id is missing, malformed, or unknown.
    """
    run_id = _require_run_id(params)
    try:
        record = history_store.get_run(run_id)
    except ValueError as exc:
        raise ToolException(str(exc)) from exc
    if record is None:
        raise ToolException(f"run not found: {run_id}")
    return {"run": record}


@logs_errors("HistoryHandler")
def history_delete(params, stream_handler):
    """Delete one run record; raises when the run id is unknown."""
    run_id = _require_run_id(params)
    try:
        deleted = history_store.delete_run(run_id)
    except ValueError as exc:
        raise ToolException(str(exc)) from exc
    if not deleted:
        raise ToolException(f"run not found: {run_id}")
    return {"deleted": run_id}


@logs_errors("HistoryHandler")
def history_clear(params, stream_handler):
    """Delete every run record; returns ``{"cleared": <count>}``."""
    return {"cleared": history_store.clear_runs()}


API_MAP = {
    "history.list": history_list,
    "history.get": history_get,
    "history.delete": history_delete,
    "history.clear": history_clear,
}
