#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API handler with middleware-style error formatting and protocol compliance.

Handler functions throw typed business exceptions; the middleware layer
catches and formats them into BackendResponse JSON using the protocol
models from ``app.protocol``.
"""

import threading
import importlib
import pkgutil
import uuid
from typing import Callable, Any

from app.utils.logger import Logger
from app.protocol import (
    BackendResponse,
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
        self.streaming_threads: dict[str, tuple] = {}
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
            module = importlib.import_module(name)
            if hasattr(module, 'API_MAP'):
                api_map.update(module.API_MAP)
        return api_map

    # ------------------------------------------------------------------
    # Request dispatch (middleware)
    # ------------------------------------------------------------------

    def handle_request(self, request_data: dict) -> dict:
        """Dispatch a JSON-RPC request to the appropriate handler.

        Returns a dict suitable for JSON serialisation (the output of
        ``BackendResponse.to_json()`` if the result is a protocol object,
        or the raw dict for streaming init responses).
        """
        req_id = request_data.get("id")
        method = request_data.get("method")
        params = request_data.get("params", {})

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
                raw_result = self.stream_handler(handler, req_id)(params)
                # Streaming init — return a raw dict (not a BackendResponse)
                return {"id": req_id, "result": raw_result, "finished": False}
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
        """Wrap a streaming handler to run in a background thread.

        Streaming events are sent via ``self.send_response`` and the
        final message signals ``finished: True``.
        """
        def wrapper(params: dict):
            stream_id = f"{handler.__name__}-{str(uuid.uuid4())}"
            task_id = params.get("task_id", "")
            stop_event = threading.Event()

            def stream_callback(data: dict):
                if task_id and isinstance(data, dict):
                    data["task_id"] = str(task_id)
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
                try:
                    handler(params_dict, stream_callback)
                except Exception as e:
                    self.logger.error(f"Error in stream thread: {e}")
                    stream_callback({
                        "type": "error",
                        "payload": {"message": str(e)},
                    })
                finally:
                    self.send_response({
                        "id": request_id,
                        "stream_id": stream_id,
                        "finished": True,
                    })

            thread = threading.Thread(
                target=stream_worker,
                args=(stop_event, stream_callback, params),
            )
            thread.start()

            self.streaming_threads[stream_id] = (thread, stop_event)
            return {"stream_id": stream_id}

        return wrapper
