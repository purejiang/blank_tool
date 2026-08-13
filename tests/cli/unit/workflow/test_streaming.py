"""Wave 3 tests: workflow streaming events.

Covers the WorkflowStreamHandler emit methods and their wire-schema dicts
(node_started / node_completed / workflow_completed / workflow_failed /
workflow_cancelled), workflow_id propagation, the silent no-op when the
callback is None, event ordering, and WorkflowEvent.to_dict serialization.
"""

from app.workflow.streaming import (
    NODE_COMPLETED,
    NODE_FAILED,
    NODE_OUTPUT,
    NODE_STARTED,
    WORKFLOW_CANCELLED,
    WORKFLOW_COMPLETED,
    WORKFLOW_FAILED,
    WorkflowEvent,
    WorkflowStreamHandler,
    is_cancelled,
)


def _handler(callback):
    return WorkflowStreamHandler(workflow_id="wf-1", callback=callback)


# ---------------------------------------------------------------------------
# Emit methods — wire-schema dicts
# ---------------------------------------------------------------------------

def test_emit_node_started_with_correct_fields():
    events = []
    _handler(events.append).emit_node_started("convert", "bundletool")
    assert events == [
        {
            "type": NODE_STARTED,
            "workflow_id": "wf-1",
            "node_id": "convert",
            "tool": "bundletool",
        }
    ]


def test_emit_node_completed_with_duration_ms():
    events = []
    _handler(events.append).emit_node_completed("convert", 42)
    assert events[0] == {
        "type": NODE_COMPLETED,
        "workflow_id": "wf-1",
        "node_id": "convert",
        "duration_ms": 42,
    }


def test_emit_node_output_with_data():
    events = []
    _handler(events.append).emit_node_output("convert", {"path": "/tmp/a.apk"})
    assert events[0] == {
        "type": NODE_OUTPUT,
        "workflow_id": "wf-1",
        "node_id": "convert",
        "data": {"path": "/tmp/a.apk"},
    }


def test_emit_node_failed_with_error():
    events = []
    _handler(events.append).emit_node_failed("convert", "boom")
    assert events[0] == {
        "type": NODE_FAILED,
        "workflow_id": "wf-1",
        "node_id": "convert",
        "error": "boom",
    }


def test_emit_workflow_completed_with_success():
    events = []
    _handler(events.append).emit_workflow_completed(True)
    assert events == [{"type": WORKFLOW_COMPLETED, "workflow_id": "wf-1", "success": True}]


def test_emit_workflow_failed_with_error():
    events = []
    _handler(events.append).emit_workflow_failed("workflow boom")
    assert events == [{"type": WORKFLOW_FAILED, "workflow_id": "wf-1", "error": "workflow boom"}]


def test_emit_workflow_cancelled():
    events = []
    _handler(events.append).emit_workflow_cancelled()
    assert events == [{"type": WORKFLOW_CANCELLED, "workflow_id": "wf-1"}]


# ---------------------------------------------------------------------------
# workflow_id propagation + ordering
# ---------------------------------------------------------------------------

def test_all_events_carry_workflow_id():
    events = []
    handler = _handler(events.append)
    handler.emit_node_started("a", "file.read")
    handler.emit_node_completed("a", 5)
    handler.emit_workflow_completed(True)
    assert all(event["workflow_id"] == "wf-1" for event in events)


def test_event_order_started_then_completed():
    events = []
    handler = _handler(events.append)
    handler.emit_node_started("a", "file.read")
    handler.emit_node_completed("a", 7)
    assert [event["type"] for event in events] == [NODE_STARTED, NODE_COMPLETED]


# ---------------------------------------------------------------------------
# No-op callback + cancellation bridge
# ---------------------------------------------------------------------------

def test_noop_when_callback_is_none():
    handler = WorkflowStreamHandler(workflow_id="wf-1", callback=None)
    handler.emit_node_started("a", "file.read")
    handler.emit_workflow_completed(True)
    handler.emit_workflow_failed("boom")
    handler.emit_workflow_cancelled()
    # No crash, no way to observe output — reaching here is the assertion.


def test_is_cancelled_false_for_unregistered_workflow():
    assert is_cancelled("definitely-not-registered") is False


# ---------------------------------------------------------------------------
# WorkflowEvent typed representation
# ---------------------------------------------------------------------------

def test_workflow_event_to_dict_omits_unset_fields():
    event = WorkflowEvent(type=NODE_STARTED, workflow_id="wf-1", node_id="a")
    assert event.to_dict() == {"type": NODE_STARTED, "workflow_id": "wf-1", "node_id": "a"}


def test_workflow_event_to_dict_includes_set_fields():
    event = WorkflowEvent(
        type=NODE_COMPLETED,
        workflow_id="wf-1",
        node_id="a",
        duration_ms=12,
    )
    assert event.to_dict() == {
        "type": NODE_COMPLETED,
        "workflow_id": "wf-1",
        "node_id": "a",
        "duration_ms": 12,
    }
