"""T10 tests: sub-workflow composition node (workflow.run) with recursion guard.

Covers: happy path (parent->child composition, child outputs flow to
downstream), self-reference detection (template calls itself → recursion
error), depth limit (chain >10 → error), namespaced nested events, and
unknown template name → clean error.
"""

import json
import os
import tempfile

import pytest

from app.template.store import FileTemplateStore
from app.workflow.definition import WorkflowDefinition, WorkflowNode
from app.workflow.engine import ExecutionContext, WorkflowEngine
from app.workflow.streaming import WorkflowStreamHandler


# ── helpers ──────────────────────────────────────────────────────────────

class RecordingHandler:
    """Captures every workflow event for later assertion (like T11 tests)."""

    def __init__(self):
        self.events: list = []
        self.workflow_id = "test"

    def emit_node_started(self, node_id: str, tool: str) -> None:
        self.events.append({"type": "node_started", "node_id": node_id, "tool": tool})

    def emit_node_completed(
        self, node_id: str, status: str, duration_ms: int, **kwargs
    ) -> None:
        self.events.append(
            {
                "type": "node_completed",
                "node_id": node_id,
                "status": status,
                "duration_ms": duration_ms,
                "error": kwargs.get("error"),
            }
        )

    def emit_workflow_completed(self, success: bool) -> None:
        self.events.append({"type": "workflow_completed", "success": success})

    def emit_workflow_failed(self, error: str) -> None:
        self.events.append({"type": "workflow_failed", "error": error})

    def emit_workflow_cancelled(self) -> None:
        self.events.append({"type": "workflow_cancelled"})


def _node(node_id, tool="file.write", **overrides) -> WorkflowNode:
    data = {"id": node_id, "tool": tool}
    data.update(overrides)
    return WorkflowNode(**data)


def _definition(name="wf", nodes=None) -> WorkflowDefinition:
    return WorkflowDefinition(name=name, nodes=nodes or [])


def _engine() -> WorkflowEngine:
    return WorkflowEngine()


def _context(tmp_path, **overrides) -> ExecutionContext:
    data = {"work_dir": str(tmp_path)}
    data.update(overrides)
    return ExecutionContext(**data)


def _save_template(store: FileTemplateStore, name: str, definition: WorkflowDefinition):
    """Save a workflow definition into the store so workflow.run can load it."""
    store.save(name, definition, {"description": f"auto: {name}"})


def _make_child_definition(name: str = "child") -> WorkflowDefinition:
    """Return a minimal 2-node child workflow (write → read)."""
    return WorkflowDefinition(
        name=name,
        nodes=[
            _node("w", "file.write", next="r",
                  params={"path": "child-out.txt", "content": "$inputs.message"}),
            _node("r", "file.read",
                  params={"path": "$nodes.w.outputs.path"}),
        ],
    )


# ── (a) happy path: parent invokes child; child outputs flow to downstream ──

def test_parent_invokes_child_returns_child_outputs(tmp_path):
    """Given a child template (write→read) saved in the store, and a parent
    workflow whose single node is workflow.run pointing at the child,
    When the engine executes the parent, Then the workflow.run node outputs
    contain the child's outputs, and overall success is True."""
    store = FileTemplateStore(templates_dir=str(tmp_path))
    child_def = _make_child_definition("child")
    _save_template(store, "child", child_def)

    parent_def = WorkflowDefinition(
        name="parent",
        nodes=[
            _node("sub", "workflow.run",
                  params={"template": "child", "inputs": {"message": "hello"}}),
        ],
    )

    ctx = _context(tmp_path, template_store=store)
    result = _engine().execute(parent_def, {}, ctx)

    assert result.success is True, f"workflow failed: {result.error}"
    assert "sub" in result.node_results, f"node_results: {list(result.node_results)}"
    sub_result = result.node_results["sub"]
    assert sub_result["error"] is None, f"sub node error: {sub_result['error']}"
    assert "outputs" in sub_result["outputs"], (
        f"expected 'outputs' key in sub outputs, got {sub_result['outputs']}"
    )
    child_outputs = sub_result["outputs"]["outputs"]
    assert child_outputs["content"] == "hello"


def test_downstream_node_resolves_child_output_via_expression(tmp_path):
    """Given parent: workflow.run → flow.log that reads
    $nodes.sub.outputs.outputs, When executed, Then flow.log logs
    the child's content value (the child outputs dict)."""
    store = FileTemplateStore(templates_dir=str(tmp_path))
    child_def = _make_child_definition("child-downstream")
    _save_template(store, "child-downstream", child_def)

    parent_def = WorkflowDefinition(
        name="parent-downstream",
        nodes=[
            _node("sub", "workflow.run", next="log",
                  params={"template": "child-downstream", "inputs": {"message": "hey"}}),
            _node("log", "flow.log",
                  params={"message": "$nodes.sub.outputs.outputs"}),
        ],
    )

    ctx = _context(tmp_path, template_store=store)
    result = _engine().execute(parent_def, {}, ctx)

    assert result.success is True, f"workflow failed: {result.error}"
    # The child workflow's outputs dict is available under
    # node_results["sub"]["outputs"]["outputs"].
    child_result = result.node_results["sub"]
    assert child_result["error"] is None
    child_outputs = child_result["outputs"]["outputs"]
    assert child_outputs["content"] == "hey"
    assert result.outputs["logged"] is True


# ── (b) self-reference: template calls itself → recursion error ──────────

def test_self_referencing_template_raises_recursion_error(tmp_path):
    """Given a template whose only node is workflow.run pointing at itself,
    When executed, Then the engine raises a ToolException with a 'recursion'
    message — and does NOT hang."""
    store = FileTemplateStore(templates_dir=str(tmp_path))
    # For a direct self-ref, the template definition must exist in the store
    # so workflow.run can load it.  Build it as a raw dict that survives
    # to/from_dict.
    self_def = WorkflowDefinition(
        name="self-ref",
        nodes=[
            _node("sub", "workflow.run",
                  params={"template": "self-ref", "inputs": {}}),
        ],
    )
    _save_template(store, "self-ref", self_def)

    ctx = _context(tmp_path, template_store=store)
    result = _engine().execute(self_def, {}, ctx)

    assert result.success is False, "self-referencing workflow should fail"
    assert "recursion" in result.error.lower(), (
        f"expected 'recursion' in error, got: {result.error}"
    )


# ── (c) depth limit: chain deeper than 10 → clear error ──────────────────

def _save_depth_chain(store: FileTemplateStore, name: str, depth: int):
    """Save a chain of templates: T<N> calls T<N+1>, up to the given depth.
    The last template (depth stop) is a simple write node."""
    for i in range(depth):
        tpl_name = f"{name}-{i}"
        if i < depth - 1:
            child_name = f"{name}-{i + 1}"
            node = _node("sub", "workflow.run",
                         params={"template": child_name, "inputs": {}})
        else:
            node = _node("w", "file.write",
                         params={"path": "depth.txt", "content": "bot"})
        tpl_def = WorkflowDefinition(name=tpl_name, nodes=[node])
        _save_template(store, tpl_name, tpl_def)


def test_depth_limit_exceeded_returns_clear_error(tmp_path):
    """Given a chain of 12 templates (depth 12 > max 10), When the top-level
    template is executed, Then the engine fails with a clear 'maximum nesting
    depth' error — and does NOT hang."""
    store = FileTemplateStore(templates_dir=str(tmp_path))
    _save_depth_chain(store, "deep", 12)

    tpl_def = WorkflowDefinition(
        name="deep-0",
        nodes=[
            _node("sub", "workflow.run",
                  params={"template": "deep-1", "inputs": {}}),
        ],
    )
    _save_template(store, "deep-0", tpl_def)

    ctx = _context(tmp_path, template_store=store)
    result = _engine().execute(tpl_def, {}, ctx)

    assert result.success is False, "depth-exceeding workflow should fail"
    assert "nesting depth" in result.error.lower() or "depth" in result.error.lower(), (
        f"expected 'nesting depth' in error, got: {result.error}"
    )


# ── (d) nested event identity: node_id is a path, run_id is stable ────────

def test_nested_events_carry_a_single_node_path_prefix(tmp_path):
    """Child node events must be attributed by path, not by rewriting ids.

    ``node_id`` becomes ``<parent node>/<child node>`` (exactly one level),
    ``workflow_id`` names the emitting workflow (the child template), and
    ``run_id`` is the top-level run — never prefixed.
    """
    store = FileTemplateStore(templates_dir=str(tmp_path))
    child_def = _make_child_definition("ns-child")
    _save_template(store, "ns-child", child_def)

    parent_def = WorkflowDefinition(
        name="ns-parent",
        nodes=[
            _node("sub", "workflow.run",
                  params={"template": "ns-child", "inputs": {"message": "ns"}}),
        ],
    )

    recorder = RecordingHandler()

    # Parent node events are emitted by the WorkflowStreamHandler; child
    # events go through context.stream_handler (the child stream wraps the
    # same callback), so both land in the recorder.
    shared_callback = lambda event: recorder.events.append(dict(event))

    stream = WorkflowStreamHandler(
        workflow_id="ns-parent",
        callback=shared_callback,
        run_id="RUN-1",
    )

    ctx = _context(tmp_path, run_id="RUN-1", template_store=store,
                   workflow_stream=stream, stream_handler=shared_callback)
    result = _engine().execute(parent_def, {}, ctx)

    assert result.success is True, f"parent failed: {result.error}"

    child_events = [
        e for e in recorder.events
        if e.get("workflow_id") == "ns-child"
    ]
    assert child_events, (
        f"expected child events naming workflow_id='ns-child', "
        f"got events: {json.dumps(recorder.events, indent=2)}"
    )

    # Exactly one level of prefixing, and the path is parent-node/child-node.
    child_node_ids = sorted(
        e["node_id"] for e in child_events if e["type"] == "node_started"
    )
    assert child_node_ids == ["sub/r", "sub/w"], child_node_ids

    # run_id identifies the top-level run everywhere.
    assert all(e.get("run_id") == "RUN-1" for e in recorder.events)

    # Parent events keep their own workflow_id and bare node ids.
    parent_events = [e for e in recorder.events if e.get("workflow_id") == "ns-parent"]
    assert all(e.get("node_id") in (None, "sub") for e in parent_events)


# ── (e) unknown template name → clean error string ────────────────────────

def test_unknown_template_name_returns_clean_error(tmp_path):
    """Given a workflow.run node referencing a template that doesn't exist,
    When executed, Then the node fails with an error mentioning 'not found'
    (no crash)."""
    store = FileTemplateStore(templates_dir=str(tmp_path))

    parent_def = WorkflowDefinition(
        name="bad-ref",
        nodes=[
            _node("sub", "workflow.run",
                  params={"template": "nonexistent", "inputs": {}}),
        ],
    )

    ctx = _context(tmp_path, template_store=store)
    result = _engine().execute(parent_def, {}, ctx)

    assert result.success is False, "unknown-template workflow should fail"
    assert "not found" in result.error.lower() or "unknown" in result.error.lower() or "nonexistent" in result.error, (
        f"expected 'not found' or 'unknown' in error, got: {result.error}"
    )
