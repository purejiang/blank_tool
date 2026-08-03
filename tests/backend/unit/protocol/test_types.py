"""Tests for backend/app/protocol/types.py — BaseType, TypeAnnotation, TypeRegistry."""

import pytest

from app.protocol.types import BaseType, TypeAnnotation, TypeRegistry


# ---------------------------------------------------------------------------
# BaseType
# ---------------------------------------------------------------------------

def test_base_type_has_exactly_six_members():
    members = list(BaseType)
    assert len(members) == 6
    assert {member.name for member in members} == {
        "FILE",
        "DIRECTORY",
        "TEXT",
        "NUMBER",
        "BOOLEAN",
        "JSON",
    }
    assert {member.value for member in members} == {
        "file",
        "directory",
        "text",
        "number",
        "boolean",
        "json",
    }


# ---------------------------------------------------------------------------
# TypeAnnotation
# ---------------------------------------------------------------------------

def test_annotation_constructs_with_lowercase_subtype():
    annotation = TypeAnnotation(base=BaseType.FILE, subtype="apk")
    assert annotation.base is BaseType.FILE
    assert annotation.subtype == "apk"


def test_annotation_rejects_uppercase_subtype():
    with pytest.raises(ValueError, match="subtype"):
        TypeAnnotation(base=BaseType.FILE, subtype="APK")


def test_annotation_rejects_empty_subtype():
    with pytest.raises(ValueError, match="subtype"):
        TypeAnnotation(base=BaseType.FILE, subtype="")


def test_annotation_rejects_non_base_type_base():
    with pytest.raises(TypeError, match="base must be a BaseType"):
        TypeAnnotation(base="invalid", subtype=None)


def test_is_compatible_true_when_base_matches_subtype_ignored():
    source = TypeAnnotation(BaseType.FILE, "apk")
    target = TypeAnnotation(BaseType.FILE, "aab")
    assert TypeAnnotation.is_compatible(source, target) is True


def test_is_compatible_false_on_base_mismatch():
    source = TypeAnnotation(BaseType.FILE)
    target = TypeAnnotation(BaseType.TEXT)
    assert TypeAnnotation.is_compatible(source, target) is False


# ---------------------------------------------------------------------------
# TypeRegistry
# ---------------------------------------------------------------------------

def test_registry_register_and_resolve_roundtrip():
    registry = TypeRegistry()
    annotation = TypeAnnotation(BaseType.FILE, "apk")
    registry.register("apk", annotation)
    assert registry.resolve("apk") is annotation


def test_registry_is_compatible_by_name():
    registry = TypeRegistry()
    registry.register("apk", TypeAnnotation(BaseType.FILE, "apk"))
    registry.register("aab", TypeAnnotation(BaseType.FILE, "aab"))
    registry.register("text", TypeAnnotation(BaseType.TEXT))
    assert registry.is_compatible("apk", "aab") is True
    assert registry.is_compatible("apk", "text") is False


def test_registry_resolve_missing_name_raises_keyerror():
    registry = TypeRegistry()
    with pytest.raises(KeyError):
        registry.resolve("missing")
