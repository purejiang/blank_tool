#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the plugin kernel's EventBus."""

import pytest

from app.plugins.events import EventBus


def test_emit_dispatches_payload_to_every_subscribed_handler_once():
    bus = EventBus()
    received = []

    def handler_a(payload):
        received.append(("a", payload))

    def handler_b(payload):
        received.append(("b", payload))

    bus.subscribe("test.event", handler_a)
    bus.subscribe("test.event", handler_b)

    bus.emit("test.event", {"n": 1})

    assert received == [("a", {"n": 1}), ("b", {"n": 1})]


def test_handlers_run_in_subscription_order():
    bus = EventBus()
    order = []

    def first(payload):
        order.append("first")

    def second(payload):
        order.append("second")

    bus.subscribe("test.event", first)
    bus.subscribe("test.event", second)

    bus.emit("test.event", None)

    assert order == ["first", "second"]


def test_unsubscribe_stops_future_calls():
    bus = EventBus()
    calls = []

    def handler(payload):
        calls.append(payload)

    bus.subscribe("test.event", handler)
    bus.emit("test.event", 1)
    bus.unsubscribe("test.event", handler)
    bus.emit("test.event", 2)

    assert calls == [1]


def test_unsubscribe_unknown_handler_is_noop():
    bus = EventBus()

    def handler(payload):
        pass

    bus.unsubscribe("test.event", handler)  # must not raise


def test_raising_handler_does_not_stop_others_or_reraise():
    bus = EventBus()
    calls = []

    def boom(payload):
        raise RuntimeError("boom")

    def ok(payload):
        calls.append(payload)

    bus.subscribe("test.event", boom)
    bus.subscribe("test.event", ok)

    # emit must swallow the RuntimeError and still run the second handler
    bus.emit("test.event", "payload")

    assert calls == ["payload"]


def test_emit_unknown_event_is_noop():
    bus = EventBus()
    bus.emit("missing.event", None)  # must not raise
