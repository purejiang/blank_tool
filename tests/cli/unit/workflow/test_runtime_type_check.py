"""Runtime base-type checking in the workflow engine (warning-only, D7).

Pins ``WorkflowEngine._check_runtime_types``: type mismatches are reported
for logging but never block execution — the engine historically accepted
loosely typed values and existing workflows depend on that.

Run with:
    python -m pytest tests/cli/unit/workflow/test_runtime_type_check.py -v
"""

import logging

from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.workflow.engine import ExecutionContext, WorkflowEngine


class _StubRegistry:
    """Minimal registry so WorkflowEngine avoids ToolManager discovery."""

    def get_tool(self, name):
        return None


class _StubTypedTool:
    """Minimal tool with a declared port set; records executions."""

    def __init__(self, name, ports):
        self.name = name
        self.ports = ports
        self.executed = False

    def execute(self, inputs, context):
        self.executed = True
        return {"ok": True}


def _typed_tool(input_ports):
    return _StubTypedTool(
        "typed_tool", PortSet(inputs=input_ports, outputs=[])
    )


def _port(name, base):
    return Port(name=name, type=TypeAnnotation(base))


def _engine():
    return WorkflowEngine(registry=_StubRegistry())


def _context():
    return ExecutionContext(work_dir="C:/work")


# ── _check_runtime_types ─────────────────────────────────────────────────
class TestCheckRuntimeTypes:
    def test_number_mismatch_warns(self):
        """String on a NUMBER port → one warning naming the port and types."""
        tool = _typed_tool([_port("count", BaseType.NUMBER)])
        warnings = _engine()._check_runtime_types({"count": "hello"}, tool)
        assert len(warnings) == 1
        assert "count" in warnings[0]
        assert "expected number" in warnings[0]
        assert "got str" in warnings[0]

    def test_text_mismatch_warns(self):
        """int on a TEXT port → one warning."""
        tool = _typed_tool([_port("name", BaseType.TEXT)])
        warnings = _engine()._check_runtime_types({"name": 123}, tool)
        assert len(warnings) == 1
        assert "name" in warnings[0]
        assert "expected text" in warnings[0]

    def test_bool_is_not_a_number(self):
        """bool is a subclass of int in Python — must be rejected for NUMBER."""
        tool = _typed_tool([_port("count", BaseType.NUMBER)])
        warnings = _engine()._check_runtime_types({"count": True}, tool)
        assert len(warnings) == 1

    def test_valid_types_no_warnings(self):
        """Correct base types for every enum value → no warnings."""
        tool = _typed_tool(
            [
                _port("file", BaseType.FILE),
                _port("directory", BaseType.DIRECTORY),
                _port("text", BaseType.TEXT),
                _port("number", BaseType.NUMBER),
                _port("flag", BaseType.BOOLEAN),
                _port("data", BaseType.JSON),
            ]
        )
        warnings = _engine()._check_runtime_types(
            {
                "file": "a.txt",
                "directory": "out/",
                "text": "hi",
                "number": 42,
                "flag": True,
                "data": {"a": 1},
            },
            tool,
        )
        assert warnings == []

    def test_json_accepts_list_and_serialized_string(self):
        """JSON accepts dict, list, and str (serialized) forms."""
        tool = _typed_tool([_port("data", BaseType.JSON)])
        engine = _engine()
        assert engine._check_runtime_types({"data": [1, 2]}, tool) == []
        assert engine._check_runtime_types({"data": '{"a": 1}'}, tool) == []

    def test_absent_optional_port_skipped(self):
        """Ports absent from inputs (optional or unset) are not checked."""
        tool = _typed_tool([_port("path", BaseType.FILE)])
        assert _engine()._check_runtime_types({}, tool) == []


# ── _run_node integration ────────────────────────────────────────────────
class _RecordingRegistry:
    """Registry returning one specific tool instance."""

    def __init__(self, tool):
        self._tool = tool

    def get_tool(self, name):
        return self._tool


def _run(engine, tool, node_id="typed", **params):
    """Run one node against *tool* (the engine resolves it from the registry)."""
    from app.workflow.definition import WorkflowNode

    engine = WorkflowEngine(registry=_RecordingRegistry(tool))
    node = WorkflowNode(id=node_id, tool=tool.name)
    return engine._run_node(node, params, _context())


class TestRunNodeWiring:
    """The runtime type check is wired into the node attempt, not the tool call.

    It runs once per node (before the retry loop) and logs at DEBUG: a type
    mismatch is advisory and must never block execution or spam WARNINGs on
    every retry.
    """

    def test_number_mismatch_logs_once(self, caplog):
        """"hello" on a NUMBER port → one debug record naming the mismatch."""
        tool = _typed_tool([_port("count", BaseType.NUMBER)])
        with caplog.at_level(logging.DEBUG, logger="app.workflow.engine"):
            outcome = _run(_engine(), tool, count="hello")
        assert outcome.error is None
        assert outcome.outputs == {"ok": True}
        messages = [r.getMessage() for r in caplog.records]
        mismatches = [m for m in messages if "runtime type mismatch" in m]
        assert len(mismatches) == 1
        assert "expected number" in mismatches[0]

    def test_text_mismatch_logs_debug_not_warning(self, caplog):
        """123 on a TEXT port must not produce a WARNING record."""
        tool = _typed_tool([_port("name", BaseType.TEXT)])
        with caplog.at_level(logging.DEBUG, logger="app.workflow.engine"):
            outcome = _run(_engine(), tool, name=123)
        assert outcome.error is None
        assert not [
            r for r in caplog.records
            if r.levelno >= logging.WARNING and "runtime type mismatch" in r.getMessage()
        ]

    def test_mismatch_is_checked_once_per_node_not_per_attempt(self, caplog):
        """A failing node with retries must not repeat the type warning."""
        tool = _typed_tool([_port("count", BaseType.NUMBER)])
        tool.fail_times = 2

        def _execute(inputs, context):
            tool.executed = True
            if getattr(tool, "attempts_left", 0) > 0:
                tool.attempts_left -= 1
                raise RuntimeError("flaky")
            return {"ok": True}

        tool.attempts_left = 2
        tool.execute = _execute
        from app.workflow.definition import WorkflowNode

        node = WorkflowNode(id="flaky", tool=tool.name, retry=3)
        engine = WorkflowEngine(registry=_RecordingRegistry(tool))
        with caplog.at_level(logging.DEBUG, logger="app.workflow.engine"):
            outcome = engine._run_node(node, {"count": "hello"}, _context())
        assert outcome.error is None
        assert outcome.attempts == 3
        mismatches = [
            r.getMessage() for r in caplog.records
            if "runtime type mismatch" in r.getMessage()
        ]
        assert len(mismatches) == 1, mismatches

    def test_valid_types_log_nothing(self, caplog):
        """Correct types → no runtime-type warnings logged."""
        tool = _typed_tool(
            [
                _port("text", BaseType.TEXT),
                _port("number", BaseType.NUMBER),
                _port("flag", BaseType.BOOLEAN),
            ]
        )
        with caplog.at_level(logging.DEBUG, logger="app.workflow.engine"):
            outcome = _run(_engine(), tool, text="hi", number=1, flag=True)
        assert outcome.error is None
        assert outcome.outputs == {"ok": True}
        assert not any(
            "runtime type mismatch" in r.getMessage() for r in caplog.records
        )

    def test_execution_continues_on_mismatch(self):
        """A type mismatch must NOT block the tool from running."""
        tool = _typed_tool([_port("count", BaseType.NUMBER)])
        outcome = _run(_engine(), tool, count="hello")
        assert tool.executed is True
        assert outcome.error is None
        assert outcome.outputs == {"ok": True}

    def test_tool_without_ports_skips_check(self, caplog):
        """Tools exposing no ``ports`` skip the check entirely (code stubs)."""
        tool = _StubTypedTool("bare_tool", None)
        with caplog.at_level(logging.DEBUG, logger="app.workflow.engine"):
            outcome = _run(_engine(), tool, anything=1)
        assert outcome.error is None
        assert outcome.outputs == {"ok": True}
        assert not any(
            "runtime type mismatch" in r.getMessage() for r in caplog.records
        )
