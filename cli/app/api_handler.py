#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API handler with middleware-style error formatting and protocol compliance.

Handler functions throw typed business exceptions; the middleware layer
catches and formats them into JSON-RPC responses using the protocol
payload models from ``app.protocol``.
"""

import threading
import importlib
import pkgutil
import uuid
from typing import Callable, Any

from app.utils.logger import Logger
from app.common.task_manager import TaskManager
from app.protocol import (
    BackendSuccessPayload,
    BackendErrorPayload,
    ErrorCode,
)
from app.common.exceptions import ToolException, ToolNotFoundError, TimeoutException


class ApiHandler:
    """Receives JSON-RPC requests, dispatches to handler functions, and
    formats responses using the shared protocol models."""

    def __init__(self, send_response: Callable[[dict], None]):
        self.send_response = send_response
        self.logger = Logger.get_logger(self.__class__.__name__)
        self.api_map = self._load_handlers()

    # ------------------------------------------------------------------
    # Handler discovery
    # ------------------------------------------------------------------

    def _load_handlers(self) -> dict:
        """Auto-discover handler modules and collect their API_MAP entries."""
        api_map: dict = {}
        handlers_package = 'app.handlers'
        package = importlib.import_module(handlers_package)
        for _, name, _ in pkgutil.walk_packages(
            package.__path__, package.__name__ + '.'
        ):
            try:
                module = importlib.import_module(name)
                if hasattr(module, 'API_MAP'):
                    api_map.update(module.API_MAP)
            except Exception as e:
                self.logger.warning(f"Failed to load handler module '{name}': {e}")
        return api_map

    # ------------------------------------------------------------------
    # Request dispatch (middleware)
    # ------------------------------------------------------------------

    def handle_request(self, request_data: dict) -> dict:
        """Dispatch a JSON-RPC request to the appropriate handler.

        Returns a dict suitable for JSON serialisation: a success/error
        envelope built from the protocol payload models, or the raw dict
        for streaming init responses.
        """
        req_id = request_data.get("id")
        method = request_data.get("method", "unknown")
        params = request_data.get("params", {})

        self.logger.info(f'[trace {req_id}] {method} start')

        try:
            handler = self.api_map.get(method)

            if not handler:
                return self._error_response(
                    req_id,
                    f"Method '{method}' not found",
                    ErrorCode.METHOD_NOT_FOUND,
                )

            try:
                is_streaming = getattr(handler, 'is_streaming', False)

                if is_streaming:
                    # The streaming wrapper writes the init frame itself and
                    # returns None: the init frame must be on the wire before
                    # the worker thread can emit anything.
                    self.stream_handler(handler, req_id)(params)
                    return None
                else:
                    raw_result = handler(params, None)
                    return self._success_response(req_id, raw_result)

            except ToolNotFoundError as e:
                self.logger.error(f"Tool not found (method={method}): {e}")
                return self._error_response(req_id, e.message, e.code)
            except TimeoutException as e:
                self.logger.error(f"Timeout (method={method}): {e}")
                return self._error_response(req_id, e.message, e.code)
            except ToolException as e:
                self.logger.error(f"Tool error (method={method}): {e}")
                return self._error_response(req_id, e.message, e.code)
            except Exception as e:
                self.logger.error(f"Handler error (method={method}): {e}")
                return self._error_response(
                    req_id, str(e), ErrorCode.INTERNAL_ERROR
                )
        finally:
            self.logger.info(f'[trace {req_id}] {method} end')

    # ------------------------------------------------------------------
    # Response formatting
    # ------------------------------------------------------------------

    def _success_response(self, req_id: Any, raw_result: Any) -> dict:
        """Wrap a handler return value into a response dict for send_json."""
        if isinstance(raw_result, dict) and "type" in raw_result:
            result = raw_result
        else:
            result = BackendSuccessPayload(payload=raw_result).to_dict()
        return {"id": req_id, "result": result, "finished": True}

    def _error_response(
        self, req_id: Any, message: str, code: int
    ) -> dict:
        """Build a JSON-RPC error response dict for send_json."""
        return {
            "id": req_id,
            "result": BackendErrorPayload(message=message, code=code).to_dict(),
            "finished": True,
        }

    # ------------------------------------------------------------------
    # Streaming support
    # ------------------------------------------------------------------

    def stream_handler(
        self, handler: Callable, request_id: Any
    ):
        """Wrap a streaming handler so it runs in a background thread.

        Ordering contract: the init frame (``{stream_id, finished: False}``)
        is written by this wrapper *before* the worker thread starts, so no
        event frame can ever overtake it — a client that resolves the invoke
        on its first frame always gets the init frame.

        The worker's return value is sent as the terminal frame's ``payload``,
        so a caller receives the run result (outputs / node_results / error)
        rather than a bare ``null``.

        The run is registered with :class:`TaskManager` (keyed by the JSON-RPC
        request id, with the task id as an alias) *before* the worker starts,
        so a cancel that is dispatched concurrently with the execute request
        still lands on a registered run.  ``params["_run_id"]`` carries that
        identity into the handler.
        """
        def wrapper(params: dict):
            stream_id = f"{handler.__name__}-{str(uuid.uuid4())}"
            task_id = str(
                params.get("task_id") or
                params.get("options", {}).get("task_id") or
                params.get("keystore", {}).get("task_id") or
                ""
            )
            run_id = str(request_id) if request_id is not None else ""
            cancel_key = run_id or task_id
            stop_event = threading.Event()

            task_manager = TaskManager()
            if cancel_key:
                task_manager.register(cancel_key, task_id, stop_event)

            # The handler cannot see the JSON-RPC id; hand it the run identity
            # so the engine can query cancellation with the same key.
            params = dict(params or {})
            params["_run_id"] = cancel_key

            def stream_callback(data: dict):
                if task_id and isinstance(data, dict):
                    data["task_id"] = task_id
                response = {
                    "id": request_id,
                    "result": data,
                    "stream_id": stream_id,
                    "finished": False,
                }
                self.send_response(response)

            def stream_worker(
                stop_event: threading.Event,
                stream_callback: Callable[[dict], None],
                params_dict: dict,
            ):
                result: Any = None
                try:
                    if stop_event.is_set():
                        return
                    result = handler(params_dict, stream_callback)
                except Exception as e:
                    self.logger.error(f"Error in stream thread: {e}")
                    stream_callback({
                        "type": "error",
                        "payload": {"message": str(e)},
                    })
                    # Keep the terminal frame's shape stable for consumers.
                    result = {
                        "success": False,
                        "status": "failed",
                        "cancelled": False,
                        "outputs": {},
                        "node_results": {},
                        "error": str(e),
                    }
                finally:
                    if cancel_key:
                        task_manager.unregister(cancel_key)
                    self.send_response({
                        "id": request_id,
                        "stream_id": stream_id,
                        "result": BackendSuccessPayload(payload=result).to_dict(),
                        "finished": True,
                    })

            # Init frame first — see the ordering contract above.
            self.send_response({
                "id": request_id,
                "result": {"stream_id": stream_id},
                "finished": False,
            })

            thread = threading.Thread(
                target=stream_worker,
                args=(stop_event, stream_callback, params),
                daemon=True,
                name=f"stream-{handler.__name__}",
            )
            thread.start()

        return wrapper
