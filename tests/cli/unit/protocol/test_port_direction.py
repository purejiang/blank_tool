"""Tests for Port.direction — the I/O direction flag on input ports.

Direction lets a descriptor declare a single port that is *bound* as an
input (the user supplies the value, e.g. an ``--out <path>`` argument)
but whose value represents an *output artifact* of the tool (the file
that gets written). The engine surfaces such ports on the node's
``outputs`` so downstream nodes can reference ``$nodes.<id>.outputs.<name>``
without the descriptor redeclaring the port on the outputs side.
"""

import pytest

from app.protocol.ports import Port
from app.protocol.types import BaseType, TypeAnnotation

_FILE = TypeAnnotation(BaseType.FILE)


# ---------------------------------------------------------------------------
# Defaults & validation
# ---------------------------------------------------------------------------

def test_port_direction_defaults_to_input():
    port = Port(name="path", type=_FILE)
    assert port.direction == "input"


def test_port_accepts_direction_output():
    port = Port(name="out_path", type=_FILE, direction="output")
    assert port.direction == "output"


def test_port_rejects_invalid_direction():
    with pytest.raises(ValueError, match="direction must be 'input' or 'output'"):
        Port(name="path", type=_FILE, direction="both")


def test_port_rejects_non_string_direction():
    # Non-str values fail the membership check; bool is a subclass of int
    # but here we test that arbitrary values are rejected, not silently coerced.
    with pytest.raises((ValueError, TypeError)):
        Port(name="path", type=_FILE, direction=1)


# ---------------------------------------------------------------------------
# Serialization roundtrip
# ---------------------------------------------------------------------------

def test_port_to_dict_emits_direction_key():
    port = Port(name="out_path", type=_FILE, direction="output")
    data = port.to_dict()
    assert data["direction"] == "output"


def test_port_to_dict_from_dict_roundtrip_preserves_direction():
    port = Port(
        name="bundle",
        type=TypeAnnotation(BaseType.FILE, "json"),
        required=False,
        description="generated bundle path",
        direction="output",
    )
    rebuilt = Port.from_dict(port.to_dict())
    assert rebuilt == port
    assert rebuilt.direction == "output"


def test_port_from_dict_without_direction_key_defaults_to_input():
    # Old workflow JSON written before `direction` existed must still load.
    legacy = {
        "name": "path",
        "type": {"base": "file", "subtype": None},
        "required": True,
        "description": "",
        "options": [],
        "multi": False,
        # note: no "direction" key
    }
    port = Port.from_dict(legacy)
    assert port.direction == "input"
