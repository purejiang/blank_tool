"""Tests: descriptor ``parse_stdout_json`` merges script stdout JSON into outputs."""

import json

from app.env.registry import EnvironmentRegistry
from app.tools.builtin.base import ToolContext
from app.tools.descriptor_tool import DescriptorTool, load_descriptor


def _real_env_registry():
    reg = EnvironmentRegistry()
    reg.discover()
    return reg


def _write_and_load(tmp_path, script_body, parse_stdout_json=True):
    """Write a python_script + descriptor JSON, load it as a DescriptorTool."""
    (tmp_path / "s.py").write_text(script_body, encoding="utf-8")
    desc = {
        "name": "test_script",
        "display_name": "Test Script",
        "type": "python_script",
        "path": "s.py",
        "env_deps": ["python"],
        "validate": {},
        "version": {},
        "inputs": [],
        "outputs": [],
        "parse_stdout_json": parse_stdout_json,
        "operations": [
            {
                "name": "run",
                "description": "run",
                "inputs": [{"name": "x", "type": {"base": "text"}, "required": True}],
                "outputs": [],
                "args_map": [{"param": "x"}],
            }
        ],
    }
    desc_file = tmp_path / "desc.json"
    desc_file.write_text(json.dumps(desc), encoding="utf-8")
    descriptor = load_descriptor(str(desc_file))
    return DescriptorTool(descriptor, _real_env_registry(), source_dir=str(tmp_path))


def _run(tool, tmp_path):
    return tool.execute(
        {"operation": "run", "x": "1"}, ToolContext(work_dir=str(tmp_path))
    )


def test_stdout_json_object_merged_into_result(tmp_path):
    tool = _write_and_load(
        tmp_path,
        'import json\nprint(json.dumps({"sum": 7, "ok": True}))\n',
    )
    result = _run(tool, tmp_path)
    assert result["success"] is True
    assert result["sum"] == 7
    assert result["ok"] is True


def test_stdout_non_json_is_left_untouched(tmp_path):
    tool = _write_and_load(tmp_path, 'print("not json")\n')
    result = _run(tool, tmp_path)
    assert result["success"] is True
    assert result["stdout"].strip() == "not json"
    assert "sum" not in result


def test_stdout_json_does_not_override_executor_control_keys(tmp_path):
    tool = _write_and_load(
        tmp_path,
        'import json\nprint(json.dumps({"success": False, "returncode": 99, "foo": "bar"}))\n',
    )
    result = _run(tool, tmp_path)
    # Executor control keys win over same-named script keys.
    assert result["success"] is True
    assert result["returncode"] == 0
    # Unrelated script keys still merge.
    assert result["foo"] == "bar"


def test_parse_disabled_leaves_stdout_as_string(tmp_path):
    tool = _write_and_load(
        tmp_path,
        'import json\nprint(json.dumps({"sum": 7}))\n',
        parse_stdout_json=False,
    )
    result = _run(tool, tmp_path)
    assert "sum" not in result
    assert '"sum": 7' in result["stdout"]
