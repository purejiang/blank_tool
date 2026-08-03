"""Tests for backend/app/protocol/ports.py — Port and PortSet."""

import pytest

from app.protocol.ports import Port, PortSet
from app.protocol.types import BaseType, TypeAnnotation

FILE_TYPE = TypeAnnotation(BaseType.FILE)


def _file_port(name: str, required: bool = True) -> Port:
    return Port(name=name, type=FILE_TYPE, required=required)


# ---------------------------------------------------------------------------
# Port
# ---------------------------------------------------------------------------

def test_port_constructs_with_valid_snake_case_name():
    port = Port(name="path", type=TypeAnnotation(BaseType.FILE))
    assert port.name == "path"
    assert port.type.base is BaseType.FILE
    assert port.required is True
    assert port.description == ""


def test_port_rejects_invalid_name():
    with pytest.raises(ValueError, match="name must match"):
        Port(name="Bad-Name", type=TypeAnnotation(BaseType.FILE))


def test_port_rejects_non_type_annotation_type():
    with pytest.raises(TypeError, match="must be a TypeAnnotation"):
        Port(name="path", type="not-a-type")


def test_port_to_dict_from_dict_roundtrip():
    port = Port(
        name="apk_path",
        type=TypeAnnotation(BaseType.FILE, "apk"),
        required=False,
        description="path to an apk",
    )
    assert Port.from_dict(port.to_dict()) == port


# ---------------------------------------------------------------------------
# PortSet
# ---------------------------------------------------------------------------

def test_port_set_rejects_duplicate_input_names():
    with pytest.raises(ValueError, match="duplicate input port name"):
        PortSet(inputs=[_file_port("path"), _file_port("path")], outputs=[])


def test_port_set_rejects_duplicate_output_names():
    with pytest.raises(ValueError, match="duplicate output port name"):
        PortSet(inputs=[], outputs=[_file_port("out"), _file_port("out")])


def test_port_set_allows_input_output_name_overlap():
    ports = PortSet(inputs=[_file_port("path")], outputs=[_file_port("path")])
    assert len(ports.inputs) == 1
    assert len(ports.outputs) == 1


def test_validate_inputs_reports_missing_required():
    ports = PortSet(inputs=[_file_port("path")], outputs=[])
    assert ports.validate_inputs({}) == ["missing required input: path"]


def test_validate_inputs_passes_when_all_required_provided():
    ports = PortSet(inputs=[_file_port("path")], outputs=[])
    assert ports.validate_inputs({"path": "/x"}) == []


def test_validate_inputs_ignores_missing_optional_port():
    ports = PortSet(inputs=[_file_port("path", required=False)], outputs=[])
    assert ports.validate_inputs({}) == []


def test_port_set_to_dict_from_dict_roundtrip():
    ports = PortSet(
        inputs=[
            _file_port("path"),
            Port(name="mode", type=TypeAnnotation(BaseType.TEXT)),
        ],
        outputs=[_file_port("out")],
    )
    assert PortSet.from_dict(ports.to_dict()) == ports
