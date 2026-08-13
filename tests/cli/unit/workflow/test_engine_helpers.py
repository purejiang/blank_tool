"""Wave 5 T14 — regression baseline for unified tool dispatch.

Pins the EXACT error-message formats and return shapes after unification
to a single ``tool.execute(inputs, context)`` contract.  All assertions
must hold identically BEFORE and AFTER the refactor.

Run with:
    python -m pytest tests/cli/unit/workflow/test_engine_helpers.py -v
"""

from types import SimpleNamespace

from app.common.base_executor import CommandExecutionContext
from app.common.exceptions import ToolException
from app.workflow.engine import ExecutionContext, WorkflowEngine


# ── Stubs ────────────────────────────────────────────────────────────────
class _StubCommandTool:
    """Descriptor/code tool stub implementing the unified ``execute(inputs,
    context)`` ToolProtocol contract.

    Internally converts ``ToolContext`` → ``CommandExecutionContext``
    (matching real DescriptorTool), then routes:
    - ``inputs["operation"]`` → operation path (builds command from
      args_map, calls ``_execute_fn(command, cmd_context)``).
    - ``inputs["args"]`` → bare-args path (calls
      ``_execute_fn(inputs["args"], cmd_context)``).
    """

    def __init__(self, name="echo_tool", descriptor=None, execute_fn=None):
        self.name = name
        self._descriptor = descriptor
        self._execute_fn = execute_fn or (lambda cmd, ctx: {
            "success": True,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "command": " ".join(cmd),
        })

    def execute(self, inputs, context):
        """Unified dispatch: operation path or bare-args path."""
        cmd_context = self._to_command_context(context)

        operation_name = inputs.get("operation")
        if operation_name and self._descriptor and self._descriptor.operations:
            return self._execute_operation(operation_name, inputs, cmd_context)

        command_list = inputs.get("args")
        if isinstance(command_list, list):
            return self._execute_fn(command_list, cmd_context)

        raise ToolException(
            f"tool {self.name!r} requires either 'operation' or 'args' "
            f"in inputs, got keys: {list(inputs.keys())}"
        )

    def _execute_operation(self, operation_name, inputs, cmd_context):
        """Lookup operation, build command from args_map, execute."""
        op = None
        for candidate in self._descriptor.operations:
            if candidate.name == operation_name:
                op = candidate
                break
        if op is None:
            raise ToolException(
                f"unknown operation {operation_name!r}"
            )
        command = []
        for entry in op.args_map:
            if isinstance(entry, str):
                command.append(entry)
            elif isinstance(entry, dict):
                if "param" in entry:
                    command.append(str(inputs.get(entry["param"], "")))
                elif "flag" in entry:
                    if inputs.get(entry["flag"], False):
                        command.append(str(entry["value"]))
        return self._execute_fn(command, cmd_context)

    @staticmethod
    def _to_command_context(context):
        """Convert ToolContext (or ExecutionContext) to CommandExecutionContext."""
        return CommandExecutionContext(
            cwd=getattr(context, "work_dir", getattr(context, "cwd", "")),
            task_id=getattr(context, "task_id", ""),
            env=getattr(context, "env", None),
            process_holder={},
        )


class _FakeDescriptor:
    """Minimal ToolDescriptor stub exposing ``operations``."""

    def __init__(self, name="echo_tool", operations=None):
        self.name = name
        self.operations = operations or []


class _StubRegistry:
    """Minimal registry so WorkflowEngine avoids ToolManager discovery."""

    def get_tool(self, name):
        return None


def _op(name, args_map):
    """Minimal operation stub: only what the engine reads (name/inputs/
    outputs/args_map)."""
    return SimpleNamespace(name=name, inputs=[], outputs=[], args_map=args_map)


def _engine():
    return WorkflowEngine(registry=_StubRegistry())


def _context():
    return ExecutionContext(work_dir="C:/work")


def _op_tool(op, execute_fn, name="echo_tool"):
    """Tool carrying an operation-based descriptor (drives the operation path)."""
    return _StubCommandTool(
        name=name, descriptor=_FakeDescriptor(operations=[op]), execute_fn=execute_fn
    )


# ── Shared failure-dict helpers ──────────────────────────────────────────
_FAILURE_DICT = {
    "success": False,
    "returncode": 1,
    "stderr": "boom",
    "stdout": "",
    "command": "echo",
}


def _failure_execute(command, context):
    return dict(_FAILURE_DICT)


# ── Operation path ───────────────────────────────────────────────────────
class TestOperationTool:
    """Unified dispatch error/return-shape pins (operation path)."""

    def test_failure_dict_exact_error_message(self):
        """A non-zero-exit result must produce the exact engine error string."""
        tool = _op_tool(_op("run", ["echo"]), _failure_execute)
        outputs, error = _engine()._execute_tool(
            tool, {"operation": "run", "name": "world"}, _context()
        )
        assert error == "tool 'echo_tool' failed (exit 1): boom"
        assert outputs == _FAILURE_DICT

    def test_failure_without_detail_omits_suffix(self):
        """No stderr/stdout detail → message without the ': detail' suffix."""
        def _exec(command, context):
            return {"success": False, "returncode": 2, "stderr": "", "stdout": ""}
        tool = _op_tool(_op("run", ["echo"]), _exec)
        _, error = _engine()._execute_tool(
            tool, {"operation": "run"}, _context()
        )
        assert error == "tool 'echo_tool' failed (exit 2)"

    def test_stderr_precedence_over_stdout_in_detail(self):
        """stderr wins when both streams carry output (or-expression order)."""
        def _exec(command, context):
            return {"success": False, "returncode": 1,
                    "stderr": "boom", "stdout": "noise"}
        tool = _op_tool(_op("run", ["echo"]), _exec)
        _, error = _engine()._execute_tool(
            tool, {"operation": "run"}, _context()
        )
        assert error == "tool 'echo_tool' failed (exit 1): boom"

    def test_success_returns_result_and_none_error(self):
        """Zero exit → (result_dict, None)."""
        def _exec(command, context):
            return {"success": True, "returncode": 0, "stdout": "ok",
                    "stderr": "", "command": "echo"}
        tool = _op_tool(_op("run", ["echo"]), _exec)
        outputs, error = _engine()._execute_tool(
            tool, {"operation": "run"}, _context()
        )
        assert error is None
        assert outputs == {"success": True, "returncode": 0, "stdout": "ok",
                           "stderr": "", "command": "echo"}

    def test_tool_exception_maps_to_message(self):
        """ToolException → ({}, exc.message) — no f-string wrapping."""
        def _exec(command, context):
            raise ToolException("boom")
        tool = _op_tool(_op("run", ["echo"]), _exec)
        outputs, error = _engine()._execute_tool(
            tool, {"operation": "run"}, _context()
        )
        assert outputs == {}
        assert error == "boom"

    def test_non_dict_result_exact_error_message(self):
        """Non-dict result → exact 'returned a non-dict result' string."""
        tool = _op_tool(_op("run", ["echo"]), lambda cmd, ctx: "oops")
        outputs, error = _engine()._execute_tool(
            tool, {"operation": "run"}, _context()
        )
        assert outputs == {}
        assert error == "tool 'echo_tool' returned a non-dict result: 'oops'"

    def test_command_context_wiring(self):
        """CommandExecutionContext must receive cwd/task_id/env/process_holder."""
        captured = {}

        def _exec(command, context):
            captured["cwd"] = context.cwd
            captured["task_id"] = context.task_id
            captured["env"] = context.env
            captured["process_holder"] = context.process_holder
            return {"success": True, "returncode": 0, "stdout": "",
                    "stderr": "", "command": "echo"}

        tool = _op_tool(_op("run", ["echo"]), _exec)
        engine = _engine()
        context = ExecutionContext(
            work_dir="C:/work", task_id="t-42", env={"A": "1"}
        )
        engine._execute_tool(
            tool, {"operation": "run"}, context
        )
        assert captured["cwd"] == "C:/work"
        assert captured["task_id"] == "t-42"
        assert captured["env"] == {"A": "1"}
        assert captured["process_holder"] == {}


# ── Command path ─────────────────────────────────────────────────────────
class TestCommandTool:
    """Unified dispatch error/return-shape pins (bare-args path)."""

    def test_failure_dict_exact_error_message(self):
        """Same failure dict → the exact same engine error string."""
        tool = _StubCommandTool(execute_fn=_failure_execute)
        outputs, error = _engine()._execute_tool(
            tool, {"args": ["echo"]}, _context()
        )
        assert error == "tool 'echo_tool' failed (exit 1): boom"
        assert outputs == _FAILURE_DICT

    def test_success_returns_result_and_none_error(self):
        def _exec(command, context):
            return {"success": True, "returncode": 0, "stdout": "ok",
                    "stderr": "", "command": " ".join(command)}
        tool = _StubCommandTool(execute_fn=_exec)
        outputs, error = _engine()._execute_tool(
            tool, {"args": ["echo"]}, _context()
        )
        assert error is None
        assert outputs["stdout"] == "ok"

    def test_tool_exception_maps_to_message(self):
        def _exec(command, context):
            raise ToolException("boom")
        tool = _StubCommandTool(execute_fn=_exec)
        outputs, error = _engine()._execute_tool(
            tool, {"args": ["echo"]}, _context()
        )
        assert outputs == {}
        assert error == "boom"

    def test_non_dict_result_exact_error_message(self):
        tool = _StubCommandTool(execute_fn=lambda cmd, ctx: "oops")
        outputs, error = _engine()._execute_tool(
            tool, {"args": ["echo"]}, _context()
        )
        assert outputs == {}
        assert error == "tool 'echo_tool' returned a non-dict result: 'oops'"

    def test_missing_args_validation_message(self):
        """params without 'args' or 'operation' → ToolException from stub."""
        tool = _StubCommandTool()
        outputs, error = _engine()._execute_tool(
            tool, {}, _context()
        )
        assert outputs == {}
        assert "requires either 'operation' or 'args'" in error

    def test_command_context_wiring(self):
        captured = {}

        def _exec(command, context):
            captured["cwd"] = context.cwd
            captured["task_id"] = context.task_id
            captured["env"] = context.env
            captured["process_holder"] = context.process_holder
            return {"success": True, "returncode": 0, "stdout": "",
                    "stderr": "", "command": "echo"}

        tool = _StubCommandTool(execute_fn=_exec)
        context = ExecutionContext(
            work_dir="C:/work", task_id="t-42", env={"A": "1"}
        )
        _engine()._execute_tool(tool, {"args": ["echo"]}, context)
        assert captured["cwd"] == "C:/work"
        assert captured["task_id"] == "t-42"
        assert captured["env"] == {"A": "1"}
        assert captured["process_holder"] == {}
