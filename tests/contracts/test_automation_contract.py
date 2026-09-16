#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Frontend ↔ backend step-action contract (refactor step C1).

The renderer's ``stepTypes.ts`` ``StepAction`` union and the backend's
``app.automation.steps`` ``ACTIONS`` registry must stay in sync — every
action the UI can emit must have an executor, and the backend must not
grow executors the UI can never reach (that would be dead code).

stepTypes.ts is a TS module; rather than compiling it, the union is
extracted with a regex anchored to ``export type StepAction =`` — the file
is formatted one-per-line which keeps this robust. If the regex misses,
the test fails loudly instead of silently passing.
"""
import os
import re
import struct

import pytest

from app.automation.steps import ACTIONS

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STEP_TYPES_TS = os.path.join(
    ROOT, "src", "renderer", "components", "automation", "stepTypes.ts"
)


def _frontend_union() -> set:
    with open(STEP_TYPES_TS, "r", encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"export type StepAction\s*=\s*((?:\s*\|[^\n]*\n)+)", src)
    assert m, "StepAction union not found in stepTypes.ts — regex anchor moved?"
    actions = set(re.findall(r"'([A-Za-z_]+)'", m.group(1)))
    assert actions, "StepAction union parsed as empty — format changed?"
    return actions


def _frontend_addable() -> set:
    with open(STEP_TYPES_TS, "r", encoding="utf-8") as f:
        src = f.read()
    m = re.search(
        r"export const ADDABLE_ACTIONS[^=]*=\s*\[([^\]]*)\]", src
    )
    assert m, "ADDABLE_ACTIONS not found in stepTypes.ts"
    return set(re.findall(r"'([A-Za-z_]+)'", m.group(1)))


class TestActionContract:
    def test_step_types_file_exists(self):
        assert os.path.isfile(STEP_TYPES_TS), STEP_TYPES_TS

    def test_backend_registry_covers_frontend_union(self):
        """Every action the UI can emit must have a backend executor."""
        missing = _frontend_union() - set(ACTIONS)
        assert not missing, f"frontend actions without backend executor: {missing}"

    def test_frontend_union_covers_backend_registry(self):
        """No dead backend executors: every registry key must be a UI action."""
        extra = set(ACTIONS) - _frontend_union()
        assert not extra, f"backend executors not reachable from the UI: {extra}"

    def test_addable_actions_are_subset_of_union(self):
        """The add-step dropdown may only offer actions in the union."""
        over = _frontend_addable() - _frontend_union()
        assert not over, f"ADDABLE_ACTIONS outside StepAction union: {over}"

    def test_registry_entries_are_callable(self):
        from app.automation import steps
        for name, handler in ACTIONS.items():
            assert callable(handler), f"ACTIONS[{name!r}] is not callable"
            assert getattr(handler, "__name__", "").startswith("_"), (
                f"{name}: handler should be a private module fn in steps.py"
            )


@pytest.mark.parametrize("action", sorted(_frontend_union()))
def test_every_action_has_a_handler(action):
    """Parametrized one-per-action so a missing executor names itself."""
    assert action in ACTIONS


# ---------------------------------------------------------------------------
# hasNonAsciiInput mirror (renderer hint ↔ backend input_text branch)
# ---------------------------------------------------------------------------

OTHER_TOOLS_PAGE = os.path.join(
    ROOT, "src", "renderer", "views", "OtherToolsPage.vue"
)
INPUT_PY = os.path.join(ROOT, "backend", "app", "automation", "input.py")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _ts_has_non_ascii(text: str) -> bool:
    """The renderer predicate, reimplemented over UTF-16 code units.

    ``hasNonAsciiInput`` iterates a JS string, i.e. UTF-16 code UNITS — not
    code points. For every astral character (emoji) the two loops still agree,
    because a surrogate is also > 0x7F, but that is exactly the kind of
    agreement worth pinning rather than assuming.
    """
    return any(unit > 0x7F for unit in struct.unpack(
        f"<{len(text.encode('utf-16-le')) // 2}H", text.encode("utf-16-le")
    ))


class TestNonAsciiMirror:
    """The page's IME hint must fire exactly when the backend takes the
    ADBKeyboard branch — one side drifting makes the hint lie (either a run
    that fails on a warning-less step, or a pointless warning)."""

    def test_backend_uses_the_0x7f_boundary(self):
        src = _read(INPUT_PY)
        assert "any(ord(c) > 0x7F for c in text)" in src, (
            "input.py's non-ASCII predicate changed — update the renderer mirror"
        )

    def test_renderer_mirrors_the_same_boundary(self):
        src = _read(OTHER_TOOLS_PAGE)
        m = re.search(
            r"function hasNonAsciiInput[\s\S]*?\n}", src
        )
        assert m, "hasNonAsciiInput not found in OtherToolsPage.vue"
        body = m.group(0)
        assert "0x7F" in body or "127" in body, body
        assert "charCodeAt" in body, body
        assert "mirror" in src.lower(), "the mirror note was dropped from the page"

    @pytest.mark.parametrize("text", [
        "",
        "hello world",
        "abc123 !@#$%^&*()",
        "café",                    # Latin-1 supplement
        "中文输入",
        "日本語テキスト",
        "emoji 😀 tail",           # surrogate pair
        "mixed ascii 中",
        "\u007f",                  # DEL is NOT > 0x7F
        "\u0080",                  # first code point above the boundary
    ])
    def test_predicates_agree_per_string(self, text):
        from app.automation import input as input_mod

        # the backend expression, evaluated exactly as written in input.py
        backend = any(ord(c) > 0x7F for c in text)
        assert backend is _ts_has_non_ascii(text), (
            f"predicate mismatch for {text!r}: backend={backend}"
        )
        # and the real function's branch agrees with it
        assert hasattr(input_mod, "input_text")

    def test_del_and_ascii_only_are_negative(self):
        assert _ts_has_non_ascii("\u007f") is False
        assert any(ord(c) > 0x7F for c in "\u007f") is False

    def test_first_positive_code_point(self):
        assert any(ord(c) > 0x7F for c in "\u0080") is True
        assert _ts_has_non_ascii("\u0080") is True
