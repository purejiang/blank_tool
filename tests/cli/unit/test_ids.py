#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for `app.ids` — the generated storage identities.

These are the guard rails the two stores lean on: a display name must never be
able to become a file name, and an id must never be able to become a path.
"""

import os
import re

import pytest

from app.ids import (
    MAX_ID_ATTEMPTS,
    TASK_ID_RE,
    WORKFLOW_ID_RE,
    id_file_path,
    is_plain_stem,
    is_task_id,
    is_workflow_id,
    new_task_id,
    new_workflow_id,
)


# ── generators ──────────────────────────────────────────────────────────────


def test_new_workflow_id_matches_its_pattern():
    for _ in range(50):
        value = new_workflow_id()
        assert WORKFLOW_ID_RE.match(value), value
        assert value.startswith("wf-")
        assert len(value) == len("wf-") + 12


def test_new_task_id_matches_its_pattern():
    for _ in range(50):
        value = new_task_id()
        assert TASK_ID_RE.match(value), value
        assert value.startswith("tk-")
        assert len(value) == len("tk-") + 12


def test_ids_are_ascii_and_lowercase_hex():
    # The whole point of the prefix + hex alphabet is that the stem is safe on
    # every file system and never needs escaping in a URL or a log line.
    for value in (new_workflow_id(), new_task_id()):
        body = value.split("-", 1)[1]
        assert re.fullmatch(r"[0-9a-f]{12}", body), value
        assert value.isascii()


def test_generated_ids_do_not_collide_in_practice():
    assert len({new_workflow_id() for _ in range(500)}) == 500


def test_the_two_prefixes_do_not_accept_each_other():
    assert is_workflow_id(new_workflow_id())
    assert not is_task_id(new_workflow_id())
    assert is_task_id(new_task_id())
    assert not is_workflow_id(new_task_id())


# ── validators ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        "wf-0123456789ab",
        "wf-ffffffffffff",
        "wf-000000000000",
    ],
)
def test_valid_workflow_ids(value):
    assert is_workflow_id(value)


@pytest.mark.parametrize(
    "value",
    [
        None,
        123,
        b"wf-0123456789ab",
        [],
        {},
        "",
        "wf-",
        "wf-0123456789a",  # 11 hex
        "wf-0123456789abc",  # 13 hex
        "wf-0123456789AB",  # uppercase is not the generated shape
        "wf-0123456789ag",  # not hex
        "Wf-0123456789ab",  # case-sensitive prefix
        " wf-0123456789ab",  # no trimming: a padded value is not an id
        "wf-0123456789ab ",  # ditto
        "wf_0123456789ab",  # separator must be a hyphen
        "0123456789ab",  # unprefixed
        "release-check",  # a plausible display name
        "../../etc/passwd",
        "wf-0123456789ab/../x",
    ],
)
def test_invalid_workflow_ids(value):
    assert not is_workflow_id(value)
    assert not is_task_id(value) or value == "wf-0123456789ab"


def test_task_ids_use_the_same_rules():
    assert is_task_id("tk-0123456789ab")
    assert not is_task_id("tk-0123456789AB")
    assert not is_task_id("tk-0123456789ab.json")
    assert not is_task_id("wf-0123456789ab")


# ── is_plain_stem ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        "release-check",
        "wf-0123456789ab",
        "带中文的名字",
        "has space",
        "UPPER",
        "a.b",
        "con",
        "-",
        ".hidden",
    ],
)
def test_plain_stems(value):
    assert is_plain_stem(value)


@pytest.mark.parametrize(
    "value",
    [
        None,
        5,
        b"bytes",
        [""],
        "",
        "..",
        "../x",
        "..\\x",
        "a/../b",
        "a/b",
        "a\\b",
        "/abs",
        "C:\\abs",
        "\\\\server\\share",
    ],
)
def test_traversal_shaped_values_are_not_plain_stems(value):
    # Rejecting these is what keeps the "the file name is the name" fallback
    # lookup from becoming a path-traversal hole.
    assert not is_plain_stem(value)


# ── id_file_path ────────────────────────────────────────────────────────────


def test_id_file_path_joins_the_stem_inside_the_directory(tmp_path):
    directory = str(tmp_path)
    target = id_file_path(directory, "wf-0123456789ab", WORKFLOW_ID_RE, "workflow")
    assert target == os.path.join(directory, "wf-0123456789ab.json")
    assert os.path.dirname(target) == directory


@pytest.mark.parametrize(
    "value",
    [
        None,
        7,
        "",
        "..",
        "../wf-0123456789ab",
        "wf-0123456789ab/../../evil",
        "wf-0123456789ab\\..\\evil",
        "wf-0123456789ab.json",
        "release-check",
        "WF-0123456789AB",
    ],
)
def test_id_file_path_refuses_anything_that_is_not_an_id(tmp_path, value):
    with pytest.raises(ValueError):
        id_file_path(str(tmp_path), value, WORKFLOW_ID_RE, "workflow")


def test_id_file_path_never_escapes_its_directory(tmp_path):
    for hostile in ("../evil", "..", "/etc/passwd", "C:\\Windows\\evil"):
        with pytest.raises(ValueError):
            id_file_path(str(tmp_path), hostile, WORKFLOW_ID_RE, "workflow")


def test_id_file_path_error_names_the_label(tmp_path):
    with pytest.raises(ValueError, match="task id must be a non-empty string"):
        id_file_path(str(tmp_path), "", TASK_ID_RE, "task")
    with pytest.raises(ValueError, match="invalid task id"):
        id_file_path(str(tmp_path), "nope", TASK_ID_RE, "task")


def test_max_id_attempts_is_a_small_positive_bound():
    # Documentation-level guard: 10 redraws of a 48-bit id is already paranoia,
    # but the stores rely on it being a real number.
    assert isinstance(MAX_ID_ATTEMPTS, int)
    assert MAX_ID_ATTEMPTS >= 1
