#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
automation.run — streaming handler for ADB UI automation runs.

Automation used to ride on the plugin framework (``plugin.run name=adb_auto``);
it is now a first-class feature with its own ``automation.*`` namespace
(sibling of ``automation.list_runs / read_run / delete_run / export_run``),
and ``plugin.run`` is reserved for actual plugins (external tools).

The streaming mechanics are IDENTICAL to what ``plugin_handler.run_plugin``
did: ``@streaming`` threads the handler, injects the request's ``task_id``
into the params so the orchestrator can find its per-run artifact
directory, and registers a stop_event the orchestrator polls for cancel.
"""

from app.automation.orchestrator import run as run_orchestration
from app.common.decorators import streaming
from app.common.exceptions import ToolException
from app.common.stream_context import StreamContext
from app.utils.logger import Logger

logger = Logger.get_logger("AutomationHandler")


@streaming
def run_automation(params, stream_handler):
    """Run an automation script (device + JSON step list)."""
    task_id = params.get("task_id")
    ctx = StreamContext("automation", stream_handler)
    try:
        return run_orchestration(ctx, task_id=str(task_id) if task_id else None, **{
            k: v for k, v in params.items() if k != "task_id"
        })
    except Exception as e:
        logger.error(f"automation.run failed: {e}", exc_info=True)
        raise ToolException(str(e) or "automation run failed")


API_MAP = {
    "automation.run": run_automation,
}
