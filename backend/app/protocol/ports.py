#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Port model for tool I/O declarations.

A tool declares its inputs and outputs as typed ports.  Ports are the
contract between a workflow node and the tool it invokes: the engine
validates that every required input is provided before execution.

Design notes:
  - Type checking is base-type only (D7); subtype is advisory.
  - `validate_inputs` for the MVP only reports missing required inputs.
    Runtime value/type checking happens in the workflow engine.
"""

import re
from dataclasses import dataclass
from typing import Dict, List

from app.protocol.types import BaseType, TypeAnnotation

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass
class Port:
    """A single typed input or output of a tool.

    Attributes:
        name: snake_case identifier (lowercase start, alphanumerics + '_').
        type: the value's type annotation (base type + advisory subtype).
        required: whether an input must be provided (outputs may ignore).
        description: human-facing explanation of the port's meaning.
    """

    name: str
    type: TypeAnnotation
    required: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        """Validate name is snake_case and type is a TypeAnnotation."""
        if not _NAME_PATTERN.match(self.name):
            raise ValueError(
                f"port name must match ^[a-z][a-z0-9_]*$, got: {self.name!r}"
            )
        if not isinstance(self.type, TypeAnnotation):
            raise TypeError(
                f"port type must be a TypeAnnotation, got {type(self.type).__name__}: {self.type!r}"
            )

    def to_dict(self) -> dict:
        """Serialize this port to a JSON-able dict.

        TypeAnnotation is a frozen dataclass without its own to_dict, so it
        is serialized inline as ``{"base": <enum-value>, "subtype": <str|None>}``.
        """
        return {
            "name": self.name,
            "type": {
                "base": self.type.base.value,
                "subtype": self.type.subtype,
            },
            "required": self.required,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Port":
        """Reconstruct a Port from a dict produced by :meth:`to_dict`."""
        type_data = data["type"]
        return cls(
            name=data["name"],
            type=TypeAnnotation(
                base=BaseType(type_data["base"]),
                subtype=type_data.get("subtype"),
            ),
            required=data.get("required", True),
            description=data.get("description", ""),
        )


def _reject_duplicates(ports: List[Port], role: str) -> None:
    """Raise ValueError if any port name repeats within `ports`."""
    seen: Dict[str, Port] = {}
    for port in ports:
        if port.name in seen:
            raise ValueError(
                f"duplicate {role} port name: {port.name!r} "
                f"(defined as {port.name!r} in {seen[port.name]!r} and {port!r})"
            )
        seen[port.name] = port


@dataclass
class PortSet:
    """The declared inputs and outputs of a tool.

    Input and output names may overlap freely; duplicates are only rejected
    *within* each side.  This mirrors real tools that consume and produce a
    value with the same name (e.g. ``path``).
    """

    inputs: List[Port]
    outputs: List[Port]

    def __post_init__(self) -> None:
        """Reject duplicate names within each side of the port set."""
        _reject_duplicates(self.inputs, "input")
        _reject_duplicates(self.outputs, "output")

    def validate_inputs(self, data: dict) -> List[str]:
        """Return a list of error strings for missing required inputs.

        For the MVP this only checks presence of required inputs; the actual
        runtime type check of provided values happens in the workflow engine.
        An empty list means the data is valid.
        """
        errors: List[str] = []
        for port in self.inputs:
            if port.required and port.name not in data:
                errors.append(f"missing required input: {port.name}")
        return errors

    def to_dict(self) -> dict:
        """Serialize this port set to a JSON-able dict."""
        return {
            "inputs": [port.to_dict() for port in self.inputs],
            "outputs": [port.to_dict() for port in self.outputs],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PortSet":
        """Reconstruct a PortSet from a dict produced by :meth:`to_dict`."""
        return cls(
            inputs=[Port.from_dict(port) for port in data["inputs"]],
            outputs=[Port.from_dict(port) for port in data["outputs"]],
        )
