from functools import wraps
import logging
from typing import Callable, Any

from app.common.exceptions import ToolException, ToolNotFoundError


def streaming(func):
    """
    Decorator to mark a handler as a streaming handler.
    Streaming handlers run in a separate thread and can send multiple events.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    
    wrapper.is_streaming = True
    return wrapper


def logs_errors(prefix: str = "", level: str = "error"):
    """Decorator that logs uncaught exceptions (excluding controlled
    ToolException / ToolNotFoundError).

    Usage::

        @logs_errors("AdbHandler")
        def adb_devices(params, stream_handler): ...

    For streaming handlers, compose with ``@streaming`` OUTERMOST::

        @streaming
        @logs_errors("AdbHandler")
        def adb_logcat(params, stream_handler): ...

    The decorator:
    - Re-raises ``ToolException`` and ``ToolNotFoundError`` WITHOUT logging
      (controlled flow).
    - Logs other ``Exception`` at the configured level with
      ``{prefix}: {e}`` format.
    - Re-raises **all** exceptions (does NOT swallow).
    - Propagates the ``is_streaming`` attribute if the wrapped function has
      it, so composition with ``@streaming`` is safe in either order.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except (ToolException, ToolNotFoundError):
                raise
            except Exception as e:
                # Use stdlib logging.getLogger — Logger.initialize() in
                # cli/main.py configures the root logger, so any child
                # logger inherits handlers and formatters automatically.
                logger = logging.getLogger(func.__module__ or "handlers")
                log_method = getattr(logger, level, logger.error)
                msg = f"{prefix}: {e}" if prefix else str(e)
                log_method(msg)
                raise

        # Safety net: if someone reverses @streaming / @logs_errors order,
        # still preserve the is_streaming attribute.
        if hasattr(func, "is_streaming"):
            wrapper.is_streaming = func.is_streaming  # type: ignore[attr-defined]

        return wrapper

    return decorator
