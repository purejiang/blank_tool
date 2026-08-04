"""Tests for select/multi-select port fields (options + multi) on Port.

T2 of the workflow-tool-env-management plan: ``options: List[str]`` and
``multi: bool`` are pure data plumbing — no SELECT base type exists yet
(deliberate plan constraint; select is a later concern).  These tests pin
the serialization contract: absent keys on ``from_dict`` keep defaults so
pre-T2 workflow data round-trips unchanged, and a Port with ``multi=True``
but empty options still serializes (the presence check is advisory only).
"""

from app.protocol.ports import Port
from app.protocol.types import BaseType, TypeAnnotation

TEXT_TYPE = TypeAnnotation(BaseType.TEXT)


def test_port_roundtrip_preserves_options_and_multi():
    port = Port(
        name="env",
        type=TEXT_TYPE,
        required=True,
        description="target environment",
        options=["dev", "staging", "prod"],
        multi=True,
    )
    data = port.to_dict()
    assert data["options"] == ["dev", "staging", "prod"]
    assert data["multi"] is True
    # Full dataclass equality after the round trip — both fields must
    # survive to_dict -> from_dict, not just avoid raising.
    assert Port.from_dict(data) == port


def test_port_from_dict_defaults_options_when_absent():
    data = {
        "name": "env",
        "type": {"base": "text", "subtype": None},
        "required": True,
        "description": "target environment",
    }
    port = Port.from_dict(data)
    assert port.options == []
    assert port.multi is False


def test_port_from_dict_defaults_multi_when_absent():
    data = {
        "name": "env",
        "type": {"base": "text", "subtype": None},
        "required": True,
        "options": ["dev"],
    }
    port = Port.from_dict(data)
    assert port.multi is False
    assert port.options == ["dev"]


def test_port_multi_true_with_empty_options_still_serializes():
    port = Port(name="tags", type=TEXT_TYPE, options=[], multi=True)
    data = port.to_dict()
    assert data["multi"] is True
    assert data["options"] == []
    assert Port.from_dict(data) == port
