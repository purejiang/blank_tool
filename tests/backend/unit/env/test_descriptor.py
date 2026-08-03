"""Tests for backend/app/env/descriptor.py — EnvironmentDescriptor."""

import json

import pytest

from app.env.descriptor import EnvironmentDescriptor

_VALID = {
    "name": "java",
    "display_name": "Java Runtime",
    "type": "jre",
    "binary": "bin/java.exe",
    "version_cmd": ["-version"],
    "version_regex": 'version "([^"]+)"',
    "search_paths": ["jre"],
    "importable": True,
    "env_var_override": "BT_JAVA_BIN",
}


def _valid_copy(**overrides):
    data = dict(_VALID)
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# from_dict
# ---------------------------------------------------------------------------

def test_from_dict_with_valid_data_constructs():
    descriptor = EnvironmentDescriptor.from_dict(_VALID)
    assert descriptor.name == "java"
    assert descriptor.type == "jre"
    assert descriptor.binary == "bin/java.exe"
    assert descriptor.version_cmd == ["-version"]
    assert descriptor.version_regex == 'version "([^"]+)"'
    assert descriptor.search_paths == ["jre"]
    assert descriptor.importable is True
    assert descriptor.env_var_override == "BT_JAVA_BIN"


def test_from_dict_missing_required_field_raises_value_error():
    data = dict(_VALID)
    del data["binary"]
    with pytest.raises(ValueError, match="missing required field: 'binary'"):
        EnvironmentDescriptor.from_dict(data)


def test_from_dict_rejects_non_snake_case_name():
    with pytest.raises(ValueError, match="name"):
        EnvironmentDescriptor.from_dict(_valid_copy(name="Java"))


def test_from_dict_rejects_invalid_type():
    with pytest.raises(ValueError, match="type"):
        EnvironmentDescriptor.from_dict(_valid_copy(type="invalid"))


def test_from_dict_rejects_empty_binary():
    with pytest.raises(ValueError, match="binary"):
        EnvironmentDescriptor.from_dict(_valid_copy(binary=""))


def test_from_dict_accepts_empty_search_paths():
    descriptor = EnvironmentDescriptor.from_dict(_valid_copy(search_paths=[]))
    assert descriptor.search_paths == []


def test_from_dict_rejects_non_dict_data():
    with pytest.raises(ValueError, match="must be a dict"):
        EnvironmentDescriptor.from_dict(["not", "a", "dict"])


# ---------------------------------------------------------------------------
# to_dict roundtrip
# ---------------------------------------------------------------------------

def test_to_dict_from_dict_roundtrip_preserves_equality():
    descriptor = EnvironmentDescriptor.from_dict(_VALID)
    assert EnvironmentDescriptor.from_dict(descriptor.to_dict()) == descriptor


# ---------------------------------------------------------------------------
# load_from_file
# ---------------------------------------------------------------------------

def test_load_from_file_reads_valid_json(tmp_path):
    path = tmp_path / "java.json"
    path.write_text(json.dumps(_VALID), encoding="utf-8")
    descriptor = EnvironmentDescriptor.load_from_file(str(path))
    assert descriptor.name == "java"
    assert descriptor.type == "jre"


def test_load_from_file_missing_file_raises_value_error(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        EnvironmentDescriptor.load_from_file(str(tmp_path / "missing.json"))


def test_load_from_file_invalid_json_raises_value_error(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        EnvironmentDescriptor.load_from_file(str(path))
