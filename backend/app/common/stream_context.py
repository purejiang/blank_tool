#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StreamContext — streaming execution context (plugin-agnostic).

Carries everything a long-running streaming task needs to talk to the
frontend: log / error lines, per-step progress events, the terminal
``complete`` latch, and cancellation polling.

Event shapes are a cross-process contract (the Electron main process
forwards them to the renderer's TaskStreamService) — do NOT change the
``type`` names or payload shapes here without updating
``TaskStreamService`` and the ``@streaming`` wrapper in ``api_handler``.

``PluginContext`` (app/plugins/context.py) extends this with
plugin-specific helpers (tool access, external commands, work dirs).
"""

from typing import Callable, Optional

from app.utils.logger import Logger


class StreamContext:
    """
    Streaming context for a long-running task.

    ``name`` is the emitting prefix in log/error payloads (e.g. the plugin
    name or ``"automation"``). ``stream_handler`` is the per-request
    callback installed by ``api_handler.stream_handler``; it may be None
    when running outside a streaming request (contract tests, probes).
    """

    def __init__(self, name: str, stream_handler: Optional[Callable] = None):
        self.name = name
        self._stream_handler = stream_handler
        self._logger = Logger.get_logger(f"Stream.{name}")

    @property
    def logger(self):
        """获取日志记录器"""
        return self._logger

    def _emit(self, event: dict):
        if self._stream_handler:
            self._stream_handler(event)

    def log(self, message: str):
        """记录日志并推送到前端"""
        self._logger.info(message)
        self._emit({
            "type": "log",
            "payload": f"[{self.name}] {message}"
        })

    def error(self, message: str):
        """记录错误并推送到前端"""
        self._logger.error(message)
        self._emit({
            "type": "error",
            "payload": f"[{self.name}] {message}"
        })

    def step_start(self, index: int, action: str):
        """Emit a per-step ``step_start`` event (index is 1-based).

        Lets the frontend render the row immediately (pending state) instead
        of only showing everything at ``complete`` time.
        """
        self._emit({
            "type": "step_start",
            "payload": {"index": index, "action": action},
        })

    def step(self, record: dict):
        """Emit a per-step ``step`` event with the finished step record.

        Payload shape matches the entry appended to the run's ``steps``:
        ``{index, action, ok, message, duration_ms[, screenshot]}``.
        """
        self._emit({
            "type": "step",
            "payload": record,
        })

    def complete(self, payload: dict):
        """Emit the terminal ``complete`` event so the frontend's
        ``waitForPhase('operation')`` latch resolves.

        Must be called exactly once at the end of a streaming run (success,
        abort, or cancel). After this, the streaming wrapper sends the
        final ``finished: True`` envelope.
        """
        self._logger.info(f"[{self.name}] complete: {payload}")
        self._emit({
            "type": "complete",
            "payload": payload,
        })

    def is_cancelled(self) -> bool:
        """Return True if the task was cancelled (stop_event set).

        The stop_event is attached to the stream callback by
        api_handler.stream_handler (``stream_callback.bt_stop_event``).
        Returns False when running outside a streaming context.
        """
        stop_event = getattr(self._stream_handler, "bt_stop_event", None)
        if stop_event is None:
            return False
        return bool(stop_event.is_set())
