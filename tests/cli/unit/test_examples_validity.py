"""Sweep test: every shipped example stays loadable.

Guards the ``examples/`` tree against rot:

- every ``examples/tools/**/*.json`` parses as a valid :class:`ToolDescriptor`
  (including the ``operations`` schema);
- every ``examples/workflows/**/*.json`` parses as a valid
  :class:`WorkflowDefinition`.

Parsing only — no tool binary, environment, or network is required, so the
sweep is hermetic.  A broken example fails here, not in a user's import.
"""

from pathlib import Path

import pytest

from app.tools.descriptor_tool import load_descriptor
from app.workflow.definition import WorkflowDefinition

ROOT = Path(__file__).resolve().parents[3]
TOOL_EXAMPLES = sorted((ROOT / "examples" / "tools").rglob("*.json"))
WORKFLOW_EXAMPLES = sorted((ROOT / "examples" / "workflows").rglob("*.json"))


def test_examples_present():
    """The sweep must actually find examples (guard against a moved tree)."""
    assert TOOL_EXAMPLES, "no tool descriptors found under examples/tools/"
    assert WORKFLOW_EXAMPLES, "no workflows found under examples/workflows/"


@pytest.mark.parametrize(
    "path", TOOL_EXAMPLES, ids=lambda p: p.stem
)
def test_tool_descriptor_loads(path):
    descriptor = load_descriptor(str(path))
    assert descriptor.name
    assert descriptor.display_name


@pytest.mark.parametrize(
    "path", WORKFLOW_EXAMPLES, ids=lambda p: p.stem
)
def test_workflow_definition_loads(path):
    definition = WorkflowDefinition.from_json_file(str(path))
    assert definition.name
