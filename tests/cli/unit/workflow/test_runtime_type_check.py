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
            tool,
            {
                "file": "a.txt",
                "directory": "out/",
                "text": "hi",
                "number": 42,
                "flag": True,
                "data": {"a": 1},
            },
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


# ── _execute_tool integration ────────────────────────────────────────────
class TestExecuteToolWiring:
    def test_number_mismatch_logs_warning(self, caplog):
        """"hello" on a NUMBER port → logger.warning with the mismatch."""
        tool = _typed_tool([_port("count", BaseType.NUMBER)])
        with caplog.at_level(logging.WARNING, logger="app.workflow.engine"):
            outputs, error = _engine()._execute_tool(
                tool, {"count": "hello"}, _context()
            )
        assert error is None
        assert outputs == {"ok": True}
        messages = [r.message for r in caplog.records]
        assert any("runtime type mismatch" in m for m in messages)
        assert any("expected number" in m for m in messages)

    def test_text_mismatch_logs_warning(self, caplog):
        """123 on a TEXT port → logger.warning with the mismatch."""
        tool = _typed_tool([_port("name", BaseType.TEXT)])
        with caplog.at_level(logging.WARNING, logger="app.workflow.engine"):
            outputs, error = _engine()._execute_tool(
                tool, {"name": 123}, _context()
            )
        assert error is None
        assert outputs == {"ok": True}
        messages = [r.message for r in caplog.records]
        assert any("runtime type mismatch" in m for m in messages)
        assert any("expected text" in m for m in messages)

    def test_valid_types_log_nothing(self, caplog):
        """Correct types → no runtime-type warnings logged."""
        tool = _typed_tool(
            [
                _port("text", BaseType.TEXT),
                _port("number", BaseType.NUMBER),
                _port("flag", BaseType.BOOLEAN),
            ]
        )
        with caplog.at_level(logging.WARNING, logger="app.workflow.engine"):
            outputs, error = _engine()._execute_tool(
                tool, {"text": "hi", "number": 1, "flag": True}, _context()
            )
        assert error is None
        assert outputs == {"ok": True}
        assert not any(
            "runtime type mismatch" in r.message for r in caplog.records
        )

    def test_execution_continues_on_mismatch(self):
        """A type mismatch must NOT block the tool from running."""
        tool = _typed_tool([_port("count", BaseType.NUMBER)])
        engine = _engine()
        outputs, error = engine._execute_tool(tool, {"count": "hello"}, _context())
        assert tool.executed is True
        assert error is None
        assert outputs == {"ok": True}

    def test_tool_without_ports_skips_check(self, caplog):
        """Tools exposing no ``ports`` skip the check entirely (code stubs)."""
        tool = _StubTypedTool("bare_tool", None)
        with caplog.at_level(logging.WARNING, logger="app.workflow.engine"):
            outputs, error = _engine()._execute_tool(tool, {"anything": 1}, _context())
        assert error is None
        assert outputs == {"ok": True}
        assert not any(
            "runtime type mismatch" in r.message for r in caplog.records
        )
