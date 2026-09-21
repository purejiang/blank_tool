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
- ``history.clear``   remove all records;
- ``history.get_config`` / ``history.set_config``  read/update the retention
  policy stored in the ``history`` section of ``server.config.json``.
"""

from typing import Any, Dict

from app.common.decorators import logs_errors
from app.common.exceptions import ToolException
from app.env import resolve_server_config_path, save_server_config
from app.history import store as history_store

#: Numeric keys of the ``history`` section of ``server.config.json``.
_NUMERIC_CONFIG_KEYS = ("max_runs", "max_bytes")


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
        ended_at, duration_ms, success, error, status, cancelled,
        run_dir}, ...]}`` — the 12-key summary projection; the heavy
        ``inputs`` / ``node_results`` fields are never included.
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


def _read_config() -> Dict[str, Any]:
    """Effective retention policy (defaults applied), plus the config path.

    The store's own accessors are the single source of truth: they read the
    ``history`` section of ``server.config.json`` (via ``BT_SERVER_CONFIG``)
    on every call and apply the same tolerance/defaults the writer uses, so a
    value written by ``history.set_config`` takes effect without a restart.
    """
    return {
        "enabled": history_store._enabled(),
        "max_runs": history_store._max_runs(),
        "max_bytes": history_store._max_bytes(),
        "config_path": resolve_server_config_path(),
    }


@logs_errors("HistoryHandler")
def history_get_config(params, stream_handler):
    """Return the retention policy: ``{enabled, max_runs, max_bytes, config_path}``.

    Defaults (no ``history`` section): ``enabled=True``, ``max_runs=200``,
    ``max_bytes=200 * 1024 * 1024``.
    """
    return _read_config()


@logs_errors("HistoryHandler")
def history_set_config(params, stream_handler):
    """Update the retention policy and return the new effective values.

    Params (all optional, only the supplied keys are written):
        enabled: bool — record runs at all.
        max_runs: non-negative int — keep at most this many records.
        max_bytes: non-negative int — keep the history dir under this size.

    Only the ``history`` section is touched; every other key in
    ``server.config.json`` is preserved (atomic write).

    Raises:
        ToolException: when a supplied value has the wrong type.
    """
    updates: Dict[str, Any] = {}

    if "enabled" in params and params["enabled"] is not None:
        value = params["enabled"]
        if not isinstance(value, bool):
            raise ToolException("'enabled' must be a boolean")
        updates["enabled"] = value

    for key in _NUMERIC_CONFIG_KEYS:
        if key not in params or params[key] is None:
            continue
        value = params[key]
        # bool is an int subclass — reject it explicitly.
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ToolException(f"'{key}' must be a non-negative integer")
        updates[key] = value

    if updates:
        try:
            save_server_config({"history": updates})
        except (OSError, ValueError) as exc:
            raise ToolException(f"failed to save history config: {exc}") from exc

    return _read_config()


API_MAP = {
    "history.list": history_list,
    "history.get": history_get,
    "history.delete": history_delete,
    "history.clear": history_clear,
    "history.get_config": history_get_config,
    "history.set_config": history_set_config,
}
