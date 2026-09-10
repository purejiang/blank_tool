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
