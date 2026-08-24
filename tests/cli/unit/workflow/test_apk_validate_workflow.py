"""Engine-level test: the apk-validate example workflow end to end.

Runs ``examples/workflows/android/apk-validate.json`` through the real
WorkflowEngine with the four real python_script descriptor tools
(apk-resolve / apk-signature / validate-entry / validate-report) executing
as genuine subprocesses under the current interpreter.  The per-item
sub-workflow (``apk-validate-entry``) is pre-seeded into a throwaway
FileTemplateStore, mirroring the GUI requirement that both templates must
be imported before the main workflow can run.
"""

import hashlib
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.template.store import FileTemplateStore
from app.tools.descriptor_tool import DescriptorTool, load_descriptor
from app.tools.tool_manager import ToolManager
from app.workflow.definition import WorkflowDefinition
from app.workflow.engine import ExecutionContext, WorkflowEngine

ROOT = Path(__file__).resolve().parents[4]
TOOLS_DIR = ROOT / "examples" / "tools" / "android"
WORKFLOWS_DIR = ROOT / "examples" / "workflows" / "android"

TOOL_NAMES = ["apk-resolve", "apk-signature", "validate-entry", "validate-report"]

LOGIN_BYTES = b"\x89PNG fixture-login-binary"
CHANNEL_PROPS = b"# channel config\nchannel=huawei\n"


class _StubEnvRegistry:
    """Resolves the 'python' env dep to the current interpreter."""

    def resolve(self, name):
        binary = sys.executable if name == "python" else ""
        return SimpleNamespace(binary_path=binary)


def _make_engine() -> WorkflowEngine:
    tools = {}
    for name in TOOL_NAMES:
        descriptor = load_descriptor(str(TOOLS_DIR / f"{name}.json"))
        tools[name] = DescriptorTool(
            descriptor, _StubEnvRegistry(), source_dir=str(TOOLS_DIR)
        )

    fallback = ToolManager.instance()

    class _Registry:
        def get_tool(self, name):
            # Descriptor examples first; builtin primitives (flow.*) from the
            # shared shipped-native registry.
            return tools.get(name) or fallback.get_tool(name)

    return WorkflowEngine(registry=_Registry())


@pytest.fixture
def fixture_apk(tmp_path):
    apk_path = tmp_path / "fixture.apk"
    with zipfile.ZipFile(apk_path, "w") as zf:
        zf.writestr("assets/login.png", LOGIN_BYTES)
        zf.writestr("assets/channel.properties", CHANNEL_PROPS)
    return apk_path


@pytest.fixture
def template_store(tmp_path):
    store = FileTemplateStore(templates_dir=str(tmp_path / "templates"))
    entry_definition = WorkflowDefinition.from_json_file(
        str(WORKFLOWS_DIR / "apk-validate-entry.json")
    )
    store.save("apk-validate-entry", entry_definition, {})
    return store


def _mapping(apk_path, login_md5):
    return [
        {
            "name": "login",
            "type": "file",
            "path": "assets/login.png",
            "md5": login_md5,
        },
        {
            "name": "channel",
            "type": "text",
            "path": "assets/channel.properties",
            "key": "channel",
            "value": "huawei",
            "match": "equals",
        },
        {
            "name": "whole-apk",
            "type": "apk",
            "md5": hashlib.md5(Path(apk_path).read_bytes()).hexdigest(),
        },
    ]


def _run_workflow(engine, store, tmp_path, apk_path, mapping):
    definition = WorkflowDefinition.from_json_file(
        str(WORKFLOWS_DIR / "apk-validate.json")
    )
    output_path = tmp_path / "report.md"
    work_dir = tmp_path / "work"
    work_dir.mkdir()  # the executor uses work_dir as subprocess cwd
    context = ExecutionContext(work_dir=str(work_dir), template_store=store)
    result = engine.execute(
        definition,
        {
            "apk_path": str(apk_path),
            "mapping": mapping,
            "output_path": str(output_path),
        },
        context,
    )
    return result, output_path


def test_apk_validate_all_entries_pass(fixture_apk, template_store, tmp_path):
    engine = _make_engine()
    mapping = _mapping(fixture_apk, hashlib.md5(LOGIN_BYTES).hexdigest())

    result, output_path = _run_workflow(
        engine, template_store, tmp_path, fixture_apk, mapping
    )

    assert result.success is True, result.error
    assert output_path.is_file()
    report = output_path.read_text(encoding="utf-8")
    assert "| login | file | PASS |" in report
    assert "| channel | text | PASS |" in report
    assert "| whole-apk | apk | PASS |" in report
    assert "**Failed**: 0" in report


def test_apk_validate_tampered_entry_fails_assert(
    fixture_apk, template_store, tmp_path
):
    engine = _make_engine()
    # Correct md5 for everything except the in-APK file (tampered expected).
    mapping = _mapping(fixture_apk, "0" * 32)

    result, output_path = _run_workflow(
        engine, template_store, tmp_path, fixture_apk, mapping
    )

    # flow.assert gates the run: a failed entry fails the whole workflow.
    assert result.success is False
    assert "APK validation failed" in (result.error or "")
    # The report is still generated before the assert and shows the failure.
    assert output_path.is_file()
    report = output_path.read_text(encoding="utf-8")
    assert "| login | file | FAIL |" in report
    assert "| channel | text | PASS |" in report


def test_apk_validate_foreach_string_mapping_accepted(
    fixture_apk, template_store, tmp_path
):
    """A JSON-string mapping (undocumented entry point) parses via the
    flow.foreach string fallback instead of crashing the loop."""
    engine = _make_engine()
    mapping = json.dumps(_mapping(fixture_apk, hashlib.md5(LOGIN_BYTES).hexdigest()))

    definition = WorkflowDefinition.from_json_file(
        str(WORKFLOWS_DIR / "apk-validate.json")
    )
    work_dir = tmp_path / "work"
    work_dir.mkdir()  # the executor uses work_dir as subprocess cwd
    context = ExecutionContext(work_dir=str(work_dir), template_store=template_store)
    result = engine.execute(
        definition,
        {
            "apk_path": str(fixture_apk),
            "mapping": mapping,
            "output_path": str(tmp_path / "report.md"),
        },
        context,
    )

    assert result.success is True, result.error
