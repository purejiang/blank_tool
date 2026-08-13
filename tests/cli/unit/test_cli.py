"""Wave 4 tests: headless CLI (cli/cli.py).

CLI subcommands are exercised as real subprocesses (``python cli.py ...`` with
``cwd=cli``) — the same way a user runs them — asserting exit codes and
stdout/stderr contract.  ``BT_LOG_LEVEL=ERROR`` keeps the boot log off stderr
so stderr assertions are precise.

Also validates the 5 Android workflow templates (now externalized to
``examples/workflows/android/``) load via ``WorkflowDefinition.from_json_file``
without error and expose the expected node/input counts.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.workflow.definition import WorkflowDefinition

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CLI_DIR = PROJECT_ROOT / "cli"
WORKFLOWS_DIR = PROJECT_ROOT / "examples" / "workflows" / "android"

WORKFLOW_TEMPLATES = {
    "download-install": (2, 2),  # nodes, inputs
    "aab-install": (2, 3),
    "decompile": (1, 2),
    "recompile": (1, 2),
    "sign": (2, 2),
}


def run_cli(*args, env=None):
    """Run ``cli.py`` as a subprocess from the cli/ directory."""
    full_env = os.environ.copy()
    full_env["BT_LOG_LEVEL"] = "ERROR"
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(CLI_DIR / "cli.py"), *args],
        cwd=str(CLI_DIR),
        capture_output=True,
        text=True,
        timeout=60,
        env=full_env,
    )


def _write_read_workflow(output_path: Path) -> dict:
    """A 2-node file.write -> file.read workflow writing to an absolute path."""
    return {
        "name": "cli-run",
        "nodes": [
            {
                "id": "write",
                "tool": "file.write",
                "params": {"path": str(output_path), "content": "$inputs.message"},
                "next": "read",
            },
            {
                "id": "read",
                "tool": "file.read",
                "params": {"path": "$nodes.write.outputs.path"},
            },
        ],
    }


# ---------------------------------------------------------------------------
# --help / list subcommands
# ---------------------------------------------------------------------------

def test_help_exits_zero_and_lists_all_five_subcommands():
    result = run_cli("--help")
    assert result.returncode == 0
    for subcommand in ("run", "list-tools", "list-envs", "validate", "list-templates"):
        assert subcommand in result.stdout


def test_list_tools_exits_zero_and_prints_tool_names():
    result = run_cli("list-tools")
    assert result.returncode == 0
    assert "name" in result.stdout
    # Builtin primitives are always appended, independent of the tool registry.
    assert "file.read" in result.stdout
    # After T21: no descriptor tools are bundled; code-based Android tools
    # may or may not be discovered depending on BT_RUNTIME_DIR at test time.
    # The builtins assertion above is the invariant.


def test_list_envs_exits_zero_and_prints_environment_names():
    result = run_cli("list-envs")
    assert result.returncode == 0
    assert "name" in result.stdout
    assert "java" in result.stdout


def test_list_templates_exits_zero_with_no_saved_templates():
    # No templates saved in the default writable dir -> empty listing, exit 0.
    result = run_cli("list-templates")
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def test_validate_valid_builtin_workflow_reports_correctly(tmp_path):
    """A workflow using only builtin tools must validate as 'valid' exit 0."""
    wf_path = tmp_path / "builtin.json"
    wf_path.write_text(
        json.dumps(
            {
                "name": "builtin-only",
                "version": "1.0",
                "nodes": [
                    {
                        "id": "log",
                        "tool": "flow.log",
                        "params": {"message": "hello", "level": "info"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = run_cli("validate", str(wf_path))
    assert result.returncode == 0
    assert "valid" in result.stdout


def test_validate_invalid_workflow_exits_one_with_errors(tmp_path):
    wf_path = tmp_path / "invalid.json"
    wf_path.write_text(
        json.dumps(
            {"name": "bad", "nodes": [{"id": "a", "tool": "definitely.not.a.tool"}]}
        ),
        encoding="utf-8",
    )
    result = run_cli("validate", str(wf_path))
    assert result.returncode == 1
    assert "tool not found" in result.stdout
    assert "definitely.not.a.tool" in result.stdout


def test_validate_missing_file_exits_one(tmp_path):
    result = run_cli("validate", str(tmp_path / "nope.json"))
    assert result.returncode == 1
    assert "invalid workflow" in result.stderr


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def test_run_json_workflow_executes_and_exits_zero(tmp_path):
    output_path = tmp_path / "out.txt"
    wf_path = tmp_path / "run.json"
    wf_path.write_text(json.dumps(_write_read_workflow(output_path)), encoding="utf-8")

    result = run_cli("run", str(wf_path), "--input", "message=hello-cli", "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["error"] is None
    assert payload["outputs"]["content"] == "hello-cli"
    assert set(payload["node_results"]) == {"write", "read"}
    assert output_path.read_text(encoding="utf-8") == "hello-cli"


def test_run_failing_workflow_exits_one(tmp_path):
    wf_path = tmp_path / "failing.json"
    wf_path.write_text(
        json.dumps(
            {
                "name": "failing",
                "nodes": [
                    {
                        "id": "check",
                        "tool": "flow.assert",
                        "params": {"condition": False, "message": "assert-boom"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = run_cli("run", str(wf_path), "--json")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["success"] is False
    assert "assert-boom" in payload["error"]


def test_run_nonexistent_json_file_exits_one(tmp_path):
    result = run_cli("run", str(tmp_path / "nope.json"), "--json")
    assert result.returncode == 1
    assert "error" in result.stderr


def test_run_missing_template_name_exits_one():
    result = run_cli("run", "no-such-template", "--json")
    assert result.returncode == 1
    assert "error: template" in result.stderr


# ---------------------------------------------------------------------------
# Android workflow templates (externalized to examples/workflows/android/)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(WORKFLOW_TEMPLATES))
def test_workflow_template_loads_from_json_file(name):
    definition = WorkflowDefinition.from_json_file(str(WORKFLOWS_DIR / f"{name}.json"))
    assert definition.name == name
    assert definition.nodes


@pytest.mark.parametrize(
    "name,expected",
    sorted(WORKFLOW_TEMPLATES.items()),
    ids=lambda value: str(value),
)
def test_workflow_template_node_and_input_counts(name, expected):
    definition = WorkflowDefinition.from_json_file(str(WORKFLOWS_DIR / f"{name}.json"))
    node_count, input_count = expected
    assert len(definition.nodes) == node_count
    assert len(definition.inputs) == input_count


# ---------------------------------------------------------------------------
# --tool-dir (T5: descriptor injection for validate/run)
# ---------------------------------------------------------------------------

ANDROID_TOOLS_DIR = PROJECT_ROOT / "examples" / "tools" / "android"


@pytest.mark.parametrize(
    "wf_name",
    ["decompile", "recompile", "sign", "aab-install"],
)
def test_validate_with_tool_dir_reports_valid(wf_name):
    """validate --tool-dir pointing at examples/tools/android resolves
    descriptor tools and reports 'valid' for migrated workflows."""
    wf_path = str(WORKFLOWS_DIR / f"{wf_name}.json")
    result = run_cli("validate", "--tool-dir", str(ANDROID_TOOLS_DIR), wf_path)
    assert result.returncode == 0, (
        f"expected exit 0 for {wf_name}, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "valid" in result.stdout


def test_validate_without_tool_dir_on_android_workflow_exits_one():
    """Without --tool-dir, descriptor tools are not discoverable -> exit 1
    with 'tool not found' (behavior preserved from before T5)."""
    wf_path = str(WORKFLOWS_DIR / "decompile.json")
    result = run_cli("validate", wf_path)
    assert result.returncode == 1
    assert "tool not found" in result.stdout


def test_validate_with_tool_dir_bogus_dir_warns_not_crash():
    """A non-existent --tool-dir prints a warning but does not crash."""
    wf_path = str(WORKFLOWS_DIR / "decompile.json")
    result = run_cli(
        "validate", "--tool-dir", str(PROJECT_ROOT / "nonexistent_dir_xyz"), wf_path
    )
    # With no valid descriptors loaded, decompile's apktool is unresolved
    # but the CLI must not crash.
    assert result.returncode in (0, 1)
    assert (
        "warning" in result.stderr.lower()
        or "nonexistent_dir_xyz" in result.stderr
        or "not a directory" in result.stderr
    )


# ---------------------------------------------------------------------------
# tool subcommand (T18: headless tool invocation)
# ---------------------------------------------------------------------------

def test_tool_builtin_executes_and_exits_zero(tmp_path):
    """``cli.py tool flow.log --input message=hello`` executes the builtin."""
    result = run_cli("tool", "flow.log", "--input", "message=hello-tool-cli")
    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    # flow.log returns {"logged": true} — assert success and tool name
    assert "flow.log" in result.stdout
    assert "logged" in result.stdout


def test_tool_builtin_json_output(tmp_path):
    """``cli.py tool flow.log --input message=hi --json`` prints raw JSON."""
    result = run_cli("tool", "flow.log", "--input", "message=json-test", "--json")
    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    payload = json.loads(result.stdout)
    # flow.log returns {"logged": true} — it logs, doesn't echo the message
    assert payload.get("logged") is True


def test_tool_unknown_tool_exits_nonzero_with_message():
    """Unknown tool name → exit non-zero with a clear message."""
    result = run_cli("tool", "nosuchtool")
    assert result.returncode != 0
    assert "nosuchtool" in (result.stderr + result.stdout)


def test_tool_operation_with_tool_dir_resolves_and_reaches_execution(tmp_path):
    """Operation resolution + binding succeeds; reaches the execute stage.

    apktool decode needs apk_path + output_dir.  The binary is likely absent,
    so the execution will fail with a tool/binary error — that is the
    ACCEPTED TERMINUS.  What matters is that the resolution+binding path
    succeeds (no "unknown tool" / "unknown operation" / "missing input").
    """
    result = run_cli(
        "tool", "apktool", "decode",
        "--tool-dir", str(ANDROID_TOOLS_DIR),
        "--input", "apk_path=test.apk",
        "--input", "output_dir=" + str(tmp_path / "out"),
        "--json",
    )
    # The tool binary is absent → non-zero exit is expected.
    # But the error MUST be about the binary/execution, NOT about resolution.
    assert result.returncode != 0
    stdout_and_stderr = result.stdout + result.stderr
    assert "unknown tool" not in stdout_and_stderr.lower()
    assert "unknown operation" not in stdout_and_stderr.lower()
    assert "missing" not in stdout_and_stderr.lower()
    # The error should name the tool (apktool) or mention execution failure.
    assert "apktool" in stdout_and_stderr.lower()


def test_tool_missing_required_input_exits_nonzero_with_message():
    """Missing a required operation input → exit non-zero, names the port."""
    result = run_cli(
        "tool", "apktool", "decode",
        "--tool-dir", str(ANDROID_TOOLS_DIR),
        # no --input flags at all → both apk_path and output_dir missing
    )
    assert result.returncode != 0
    stdout_and_stderr = result.stdout + result.stderr
    assert "apk_path" in stdout_and_stderr or "output_dir" in stdout_and_stderr
    assert "missing" in stdout_and_stderr.lower() or "required" in stdout_and_stderr.lower()


def test_tool_list_tools_unchanged():
    """``list-tools`` subcommand is unchanged and still works."""
    result = run_cli("list-tools")
    assert result.returncode == 0
    assert "file.read" in result.stdout
    assert "name" in result.stdout


def test_tool_help_mentions_tool_subcommand():
    """``--help`` now lists the ``tool`` subcommand."""
    result = run_cli("--help")
    assert result.returncode == 0
    assert "tool" in result.stdout


def test_tool_no_operation_on_descriptor_with_ops_lists_them(tmp_path):
    """Descriptor tool with operations but no operation given → clear message."""
    result = run_cli(
        "tool", "apktool",
        "--tool-dir", str(ANDROID_TOOLS_DIR),
    )
    # Exit non-zero because no operation was specified.
    assert result.returncode != 0
    stdout_and_stderr = result.stdout + result.stderr
    assert "operation" in stdout_and_stderr.lower()
    # Should name available operations or give guidance.
    assert "decode" in stdout_and_stderr or "build" in stdout_and_stderr or "specify" in stdout_and_stderr.lower()
