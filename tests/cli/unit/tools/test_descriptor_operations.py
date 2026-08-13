"""Wave 2 tests (T3): tool descriptor `operations` schema.

Covers:
  (a) a descriptor WITH operations parses into typed Operation objects
      (name/description/inputs/outputs/args_map all match the fixture);
  (b) a descriptor WITHOUT an operations key loads unchanged (backward
      compatibility — operations == [], and the raw-args surface is intact);
  (c) a malformed operation (missing name) raises ValueError naming the
      missing field and the descriptor.
"""

import json
from pathlib import Path

import pytest

from app.protocol import BaseType
from app.tools.descriptor_tool import Operation, ToolDescriptor, load_descriptor

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return str(FIXTURES / name)


# ---------------------------------------------------------------------------
# (a) descriptor with operations
# ---------------------------------------------------------------------------

def test_load_descriptor_with_operations_parses_typed_operation():
    descriptor = load_descriptor(_fixture("descriptor_with_operations.json"))

    assert isinstance(descriptor, ToolDescriptor)
    assert descriptor.name == "decode_tool"
    # Descriptor-level ports still parse as before.
    assert descriptor.inputs[0].name == "args"
    assert descriptor.outputs[0].name == "result"

    assert len(descriptor.operations) == 1
    op = descriptor.operations[0]
    assert isinstance(op, Operation)
    assert op.name == "decode"
    assert op.description == "Decode an APK into smali sources"

    # inputs: typed Ports, parsed through Port.from_dict-equivalent logic.
    assert [p.name for p in op.inputs] == ["apk", "force"]
    assert op.inputs[0].type.base == BaseType.FILE
    assert op.inputs[0].required is True
    assert op.inputs[1].type.base == BaseType.BOOLEAN
    assert op.inputs[1].required is False

    # outputs: typed Ports.
    assert [p.name for p in op.outputs] == ["output_dir"]
    assert op.outputs[0].type.base == BaseType.DIRECTORY
    assert op.outputs[0].required is True

    # args_map: mixed literal strings + dict placeholders, kept as-is.
    assert op.args_map == ["d", {"param": "apk"}, {"flag": "force", "value": "-f"}]


# ---------------------------------------------------------------------------
# (b) backward compatibility — no operations key
# ---------------------------------------------------------------------------

def test_load_descriptor_without_operations_is_backward_compatible():
    descriptor = load_descriptor(_fixture("descriptor_without_operations.json"))

    # Not just "no exception": operations must be an empty list, explicitly.
    assert isinstance(descriptor.operations, list)
    assert descriptor.operations == []
    # Existing raw-args surface intact.
    assert descriptor.name == "plain_tool"
    assert descriptor.type == "binary"
    assert descriptor.inputs[0].name == "args"
    assert descriptor.outputs[0].name == "result"


# ---------------------------------------------------------------------------
# (c) malformed operation — missing name
# ---------------------------------------------------------------------------

def test_load_descriptor_malformed_operation_raises_naming_field_and_descriptor():
    with pytest.raises(ValueError) as exc_info:
        load_descriptor(_fixture("descriptor_malformed_operation.json"))
    message = str(exc_info.value)
    assert "name" in message
    assert "malformed_tool" in message
    assert "operation" in message
