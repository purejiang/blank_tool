#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified type system for the workflow engine.

Two-layer type model (D7):
  - Base types: coarse categories every value maps to (FILE, DIRECTORY, TEXT, ...).
  - Domain annotations: advisory, human/UI-facing hints ("apk", "aab").

The engine only validates base types; subtype is never enforced.
"""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Optional

_SUBTYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class BaseType(Enum):
    """Base category of a typed value."""

    FILE = "file"
    DIRECTORY = "directory"
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    JSON = "json"


@dataclass(frozen=True)
class TypeAnnotation:
    """A value's type: a base type plus an optional domain annotation.

    `subtype` is advisory only (D7): the engine ignores it for compatibility.
    """

    base: BaseType
    subtype: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate base is a BaseType and subtype matches the identifier pattern."""
        if not isinstance(self.base, BaseType):
            raise TypeError(
                f"base must be a BaseType, got {type(self.base).__name__}: {self.base!r}"
            )
        if self.subtype is not None and not _SUBTYPE_PATTERN.match(self.subtype):
            raise ValueError(
                f"subtype must match ^[a-z][a-z0-9_]*$, got: {self.subtype!r}"
            )

    @staticmethod
    def is_compatible(source: "TypeAnnotation", target: "TypeAnnotation") -> bool:
        """Return True when two annotations share the same base type.

        Subtype is advisory (D7) and deliberately ignored here.
        """
        return source.base == target.base
