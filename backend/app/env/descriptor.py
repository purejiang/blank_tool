"""
Data-driven environment (runtime) descriptors.

An :class:`EnvironmentDescriptor` declares *what* an environment is — its
identifier, where its binary lives relative to the environment root, how to
probe its version, and where to search for it inside ``runtime/`` — without
resolving any actual path. Path resolution is the registry's job
(``app.env.registry.EnvironmentRegistry``).

This module replaces the hardcoded ``get_java_bin()`` / ``get_python_bin()`` /
``get_node_bin()`` functions in ``app.utils.env`` by encoding the same
resolution parameters (search paths, version commands, env var overrides) as
data.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Valid environment types.
VALID_TYPES = frozenset({"jre", "python", "node", "custom"})

# snake_case identifier: lowercase start, then lowercase/digits/underscores.
_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

# Fields that are required (no default) when parsing from a dict.
_REQUIRED_FIELDS = (
    "name",
    "display_name",
    "type",
    "binary",
    "version_cmd",
    "version_regex",
    "search_paths",
)


@dataclass
class EnvironmentDescriptor:
    """
    Schema for one environment (runtime) that Blank Tool can resolve and run.

    Attributes:
        name: snake_case identifier, e.g. ``"java"``, ``"python"``, ``"node"``.
        display_name: human-readable name, e.g. ``"Java Runtime"``.
        type: one of ``"jre"``, ``"python"``, ``"node"``, ``"custom"``.
        binary: path relative to the environment root, e.g. ``"bin/java.exe"``.
        version_cmd: command arguments used to query the version, e.g. ``["-version"]``.
        version_regex: regex with exactly one capture group for version extraction.
        search_paths: directories to search, relative to ``runtime/``. May be
            empty, which means the environment is not bundled and must be
            provided by the user (e.g. node.js).
        importable: whether users can import custom instances of this type.
        env_var_override: name of the environment variable that, when set,
            points directly at the binary (e.g. ``"BT_JAVA_BIN"``).
    """

    name: str
    display_name: str
    type: str
    binary: str
    version_cmd: List[str]
    version_regex: str
    search_paths: List[str]
    importable: bool = True
    env_var_override: Optional[str] = None

    # Required fields are declared above with no default; keep this marker so
    # field ordering stays explicit and dataclass semantics are obvious.
    _required_fields: tuple = field(default=_REQUIRED_FIELDS, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate the descriptor after construction."""
        if not isinstance(self.name, str) or not _NAME_PATTERN.fullmatch(self.name):
            raise ValueError(
                f"invalid name {self.name!r}: must be snake_case matching "
                r"^[a-z][a-z0-9_]*$"
            )

        if self.type not in VALID_TYPES:
            raise ValueError(
                f"invalid type {self.type!r}: must be one of "
                f"{sorted(VALID_TYPES)}"
            )

        if not isinstance(self.binary, str) or not self.binary:
            raise ValueError("binary must be a non-empty string")

        if not isinstance(self.search_paths, list):
            raise ValueError("search_paths must be a list (empty list means 'not bundled')")

        if not isinstance(self.version_cmd, list):
            raise ValueError("version_cmd must be a list of command arguments")

        if not isinstance(self.version_regex, str):
            raise ValueError("version_regex must be a string")

        if self.env_var_override is not None and not isinstance(self.env_var_override, str):
            raise ValueError("env_var_override must be a string or None")

    def to_dict(self) -> dict:
        """Serialize this descriptor to a JSON-able dict."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "type": self.type,
            "binary": self.binary,
            "version_cmd": list(self.version_cmd),
            "version_regex": self.version_regex,
            "search_paths": list(self.search_paths),
            "importable": self.importable,
            "env_var_override": self.env_var_override,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EnvironmentDescriptor":
        """
        Build an :class:`EnvironmentDescriptor` from a plain dict.

        Args:
            data: dict with (at least) all required fields. Missing or invalid
                fields raise :class:`ValueError` naming the offending field.

        Returns:
            A validated :class:`EnvironmentDescriptor`.

        Raises:
            ValueError: if a required field is missing, or a field value fails
                validation.
        """
        if not isinstance(data, dict):
            raise ValueError(f"descriptor data must be a dict, got {type(data).__name__}")

        for field_name in cls._required_fields:
            if field_name not in data:
                raise ValueError(f"missing required field: {field_name!r}")

        try:
            return cls(
                name=data["name"],
                display_name=data["display_name"],
                type=data["type"],
                binary=data["binary"],
                version_cmd=list(data["version_cmd"]),
                version_regex=data["version_regex"],
                search_paths=list(data["search_paths"]),
                importable=bool(data.get("importable", True)),
                env_var_override=data.get("env_var_override"),
            )
        except (TypeError, ValueError) as exc:
            # __post_init__ already raised a descriptive ValueError; pass it
            # through. TypeErrors (e.g. a non-list version_cmd) get wrapped.
            if isinstance(exc, ValueError):
                raise
            raise ValueError(f"invalid descriptor field: {exc}") from exc

    @classmethod
    def load_from_file(cls, path: str) -> "EnvironmentDescriptor":
        """
        Load a descriptor from a JSON file on disk.

        Args:
            path: filesystem path to the JSON descriptor file.

        Returns:
            A validated :class:`EnvironmentDescriptor`.

        Raises:
            ValueError: if the file cannot be read, is not valid JSON, or does
                not contain a valid descriptor dict.
        """
        file_path = Path(path)
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ValueError(f"descriptor file not found: {path}") from None
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in descriptor file {path}: {exc}") from exc
        return cls.from_dict(raw)
