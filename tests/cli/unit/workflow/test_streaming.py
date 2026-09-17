"""Wave 3 tests: workflow streaming events.

Covers the WorkflowStreamHandler emit methods and their wire-schema dicts
(node_started / node_completed / workflow_completed / workflow_failed /
workflow_cancelled), the run_id + workflow_id stamping, the silent no-op when
the callback is None, and event ordering.
"""

from app.workflow.streaming import (
    NODE_COMPLETED,
    NODE_STARTED,
    WORKFLOW_CANCELLED,
    WORKFLOW_COMPLETED,
    WORKFLOW_FAILED,
    WorkflowStreamHandler,
    is_cancelled,
)


def _handler(callback, **kwargs):
    kwargs.setdefault("workflow_id", "wf-1")
    kwargs.setdefault("run_id", "run-1")
    return WorkflowStreamHandler(callback=callback, **kwargs)


# ---------------------------------------------------------------------------
# Emit methods — wire-schema dicts
# ---------------------------------------------------------------------------

def test_emit_node_started_with_correct_fields():
    events = []
    _handler(events.append).emit_node_started("convert", "bundletool")
    assert events == [
        {
            "type": NODE_STARTED,
            "run_id": "run-1",
            "workflow_id": "wf-1",
            "node_id": "convert",
            "tool": "bundletool",
        }
    ]


def test_emit_node_completed_carries_status_and_attempts():
    events = []
    _handler(events.append).emit_node_completed("convert", "ok", 42)
    assert events[0] == {
        "type": NODE_COMPLETED,
        "run_id": "run-1",
        "workflow_id": "wf-1",
        "node_id": "convert",
        "status": "ok",
        "duration_ms": 42,
        "attempts": 1,
    }


def test_emit_node_completed_includes_error_when_present():
    events = []
    _handler(events.append).emit_node_completed(
        "convert", "failed", 12, error="boom", attempts=3
    )
    assert events[0]["status"] == "failed"
    assert events[0]["error"] == "boom"
    assert events[0]["attempts"] == 3


def test_emit_node_completed_omits_error_when_absent():
    events = []
    _handler(events.append).emit_node_completed("convert", "skipped", 12)
    assert "error" not in events[0]


def test_emit_workflow_completed_with_success():
    events = []
    _handler(events.append).emit_workflow_completed(True)
    assert events == [
        {
            "type": WORKFLOW_COMPLETED,
            "run_id": "run-1",
            "workflow_id": "wf-1",
            "success": True,
        }
    ]


def test_emit_workflow_failed_with_error():
    events = []
    _handler(events.append).emit_workflow_failed("workflow boom")
    assert events == [
        {
            "type": WORKFLOW_FAILED,
            "run_id": "run-1",
            "workflow_id": "wf-1",
            "error": "workflow boom",
        }
    ]


def test_emit_workflow_cancelled():
    events = []
    _handler(events.append).emit_workflow_cancelled()
    assert events == [
        {
            "type": WORKFLOW_CANCELLED,
            "run_id": "run-1",
            "workflow_id": "wf-1",
        }
    ]


# ---------------------------------------------------------------------------
# identity propagation + ordering
# ---------------------------------------------------------------------------

def test_all_events_carry_run_and_workflow_id():
    events = []
    handler = _handler(events.append)
    handler.emit_node_started("a", "file.read")
    handler.emit_node_completed("a", "ok", 5)
    handler.emit_workflow_completed(True)
    assert all(event["workflow_id"] == "wf-1" for event in events)
    assert all(event["run_id"] == "run-1" for event in events)


def test_run_id_defaults_to_workflow_id():
    events = []
    WorkflowStreamHandler(
        workflow_id="solo", callback=events.append
    ).emit_workflow_completed(True)
    assert events[0]["run_id"] == "solo"


def test_event_order_started_then_completed():
    events = []
    handler = _handler(events.append)
    handler.emit_node_started("a", "file.read")
    handler.emit_node_completed("a", "ok", 7)
    assert [event["type"] for event in events] == [NODE_STARTED, NODE_COMPLETED]


# ---------------------------------------------------------------------------
# No-op callback + cancellation bridge
# ---------------------------------------------------------------------------

def test_noop_when_callback_is_none():
    handler = WorkflowStreamHandler(workflow_id="wf-1", callback=None)
    handler.emit_node_started("a", "file.read")
    handler.emit_node_completed("a", "ok", 1)
    handler.emit_workflow_completed(True)
    handler.emit_workflow_failed("boom")
    handler.emit_workflow_cancelled()
    # No crash, no way to observe output — reaching here is the assertion.


def test_is_cancelled_false_for_unregistered_run():
    assert is_cancelled("definitely-not-registered") is False
