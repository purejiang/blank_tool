#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python backend main entry point.

- Reads JSON-RPC requests from stdin, writes responses to stdout.
- Supports health-check pings, stdin EOF reconnection, and graceful shutdown.
"""

import sys
import os
import json
import signal
import time
import threading
from pathlib import Path
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.api_handler import ApiHandler
from app.utils.logger import Logger
from app.utils.env import get_env, load_dotenv, load_server_config, resolve_path
from app.protocol import BackendResponse, BackendSuccessPayload, BackendErrorPayload, ErrorCode

# Thread-safe lock for writing to stdout
stdout_lock = threading.Lock()

# Track the process start time for health-check uptime
_start_time = time.time()

# Sentinel to signal graceful shutdown
_shutdown_requested = threading.Event()

# Track pending request count for graceful drain
_pending_requests = 0
_pending_lock = threading.Lock()


def send_json(data: Dict[str, Any]):
    """Thread-safe JSON write to stdout."""
    with stdout_lock:
        sys.stdout.write(json.dumps(data) + '\n')
        sys.stdout.flush()


# ------------------------------------------------------------------
# Health check handler (injected into ApiHandler.api_map)
# ------------------------------------------------------------------

def _handle_health(params: dict, _stream_handler) -> dict:
    """Lightweight health-check returning status and uptime."""
    return {
        "status": "ok",
        "uptime": round(time.time() - _start_time, 2),
    }


# ------------------------------------------------------------------
# Bootstrap
# ------------------------------------------------------------------

def bootstrap():
    dotenv_keys = load_dotenv()
    load_server_config(override_keys=dotenv_keys)

    cache_dir = get_env('BT_CACHE_DIR', './cache')
    resolved_cache_dir = resolve_path(cache_dir)
    logs_file_path = Path(resolved_cache_dir) / "logs"

    log_level = get_env('BT_LOG_LEVEL', 'DEBUG')
    Logger.initialize(log_dir=logs_file_path, log_level=log_level)


# ------------------------------------------------------------------
# Signal handling (graceful shutdown)
# ------------------------------------------------------------------

def _install_signal_handlers(executor: ThreadPoolExecutor, logger: Logger):
    """Register OS signal handlers for graceful shutdown.

    On SIGTERM / SIGINT the handler sets a shutdown flag, drains pending
    requests (with a 10 s grace period), then force-exits.
    """
    def _on_shutdown(signum, frame):
        if _shutdown_requested.is_set():
            # Second signal — force exit
            logger.warning(
                f"Second signal received (sig={signum}), forcing exit."
            )
            os._exit(1)
        logger.info(
            f"Received signal {signum}, initiating graceful shutdown..."
        )
        _shutdown_requested.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _on_shutdown)
        except (ValueError, AttributeError):
            # Signal handlers may not be supported on all platforms (e.g. Windows)
            pass


def _drain_pending(logger: Logger, timeout: float = 10.0):
    """Wait for in-flight requests to complete before exiting."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with _pending_lock:
            if _pending_requests <= 0:
                return
        time.sleep(0.1)
    logger.warning(
        f"Graceful shutdown timed out after {timeout}s "
        f"({_pending_requests} request(s) still pending)"
    )


# ------------------------------------------------------------------
# Main loop
# ------------------------------------------------------------------

def main():
    """Main loop: bootstrap, register handlers, process stdin lines."""
    try:
        bootstrap()
        api_handler = ApiHandler(send_response=send_json)
        logger = Logger.get_logger("Main")
    except Exception as e:
        error_msg = f"Initialization failed: {e}"
        sys.stderr.write(error_msg + "\n")
        sys.stderr.flush()
        send_json({
            "id": None,
            "error": {"code": -32603, "message": error_msg},
        })
        sys.exit(1)

    # Inject health-check handler
    api_handler.api_map["health"] = _handle_health

    # Thread pool for request processing
    executor = ThreadPoolExecutor(max_workers=4)
    _install_signal_handlers(executor, logger)

    # Track submitted futures so we can drain on shutdown
    _futures = []

    def process_request(line: str):
        """Parse one JSON-RPC request line and dispatch to ApiHandler."""
        global _pending_requests
        request_id = None
        with _pending_lock:
            _pending_requests += 1
        try:
            request = json.loads(line)
            request_id = request.get("id")

            response = api_handler.handle_request(request)

            if response:
                send_json(response)

        except json.JSONDecodeError:
            send_json({
                "id": None,
                "error": {"code": ErrorCode.PARSE_ERROR, "message": "Parse error"},
            })
        except Exception as e:
            send_json({
                "id": request_id,
                "error": {
                    "code": ErrorCode.INTERNAL_ERROR,
                    "message": f"Internal error: {e}",
                },
            })
        finally:
            with _pending_lock:
                _pending_requests -= 1

    logger.info("Backend ready, reading from stdin...")

    # --- Primary read loop with EOF reconnection ---
    max_reconnect_attempts = 10
    reconnect_delay = 1.0

    while not _shutdown_requested.is_set():
        for line in sys.stdin:
            # Strip trailing whitespace / newline
            line = line.strip()
            if not line:
                continue
            future = executor.submit(process_request, line)
            _futures.append(future)

        # stdin loop exited (EOF) — attempt reconnect
        logger.warning("stdin closed, attempting reconnect...")
        for attempt in range(1, max_reconnect_attempts + 1):
            if _shutdown_requested.is_set():
                break
            logger.info(
                f"Reconnect attempt {attempt}/{max_reconnect_attempts} "
                f"(waiting {reconnect_delay}s)"
            )
            time.sleep(reconnect_delay)
            # Reopen stdin — the main process may have connected a new pipe
            try:
                sys.stdin = open(0, 'r')
                logger.info("stdin reopened successfully")
                break  # Break out of reconnect loop, re-enter the for-loop
            except OSError:
                logger.warning("Failed to reopen stdin")
        else:
            # All reconnect attempts exhausted
            logger.error(
                f"Failed to reconnect stdin after {max_reconnect_attempts} "
                f"attempts, shutting down."
            )
            break

    # --- Graceful shutdown path ---
    logger.info("Shutting down...")
    _drain_pending(logger, timeout=10.0)
    executor.shutdown(wait=False)
    logger.info("Backend stopped.")


if __name__ == "__main__":
    main()
