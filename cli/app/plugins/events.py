#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
In-process event bus for the plugin system.

A kernel service shared by plugins: :meth:`EventBus.subscribe` registers a
handler for an event name, :meth:`EventBus.emit` synchronously dispatches a
payload to every subscribed handler in subscription order, and
:meth:`EventBus.unsubscribe` removes a handler.

A handler that raises is caught and logged (with full traceback) — it does
**not** prevent the remaining handlers from running, and ``emit`` never
re-raises. Thread safety: handler registries are guarded by a
:class:`threading.Lock`; dispatch snapshots the handler list under the lock and
runs it outside it, mirroring the pattern in :mod:`app.env.registry`.
"""

import logging
import threading
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)

# A handler receives the emitted payload as its single positional argument.
Handler = Callable[[object], None]


class EventBus:
    """Topic-based, synchronous, in-process event dispatcher.

    Multiple handlers may subscribe to the same event name; ``emit`` calls
    them in subscription order. A raising handler is isolated (caught and
    logged) so the rest still run. All methods are safe to call from multiple
    threads.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Handler]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_name: str, handler: Handler) -> None:
        """Register *handler* for *event_name* (appended to the subscription
        order). Re-subscribing the same handler adds it again."""
        with self._lock:
            self._handlers.setdefault(event_name, []).append(handler)

    def unsubscribe(self, event_name: str, handler: Handler) -> None:
        """Remove the first occurrence of *handler* from *event_name*.

        A no-op when the handler is not subscribed. An event name with no
        remaining handlers is dropped from the registry.
        """
        with self._lock:
            handlers = self._handlers.get(event_name)
            if handlers is None:
                return
            try:
                handlers.remove(handler)
            except ValueError:
                return
            if not handlers:
                del self._handlers[event_name]

    def emit(self, event_name: str, payload: object = None) -> None:
        """Synchronously dispatch *payload* to every handler subscribed to
        *event_name*, in subscription order.

        Handler exceptions are caught and logged with a full traceback; they
        never propagate and never stop the remaining handlers. Emitting an
        event with no subscribers is a no-op.
        """
        with self._lock:
            handlers = list(self._handlers.get(event_name, ()))
        for handler in handlers:
            try:
                handler(payload)
            except Exception:
                logger.exception("handler for event %r raised", event_name)
