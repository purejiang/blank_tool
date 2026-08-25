"""Tests: flow.compare — the branch-condition producer.

Covers every operator, numeric vs string coercion (both-numeric compares
numerically; mixed coerces to strings so ``5`` equals ``"5"``), the default
op, and the unknown-op error.
"""

import pytest

from app.common.exceptions import ToolException
from app.tools.builtin.base import ToolContext
from app.tools.builtin.flow_tools import FlowCompare


def _run(a, b, op=None):
    inputs = {"a": a, "b": b}
    if op is not None:
        inputs["op"] = op
    return FlowCompare().execute(inputs, ToolContext(work_dir="."))["result"]


@pytest.mark.parametrize(
    "a,b,op,expected",
    [
        # eq / ne — numeric when both are numbers
        (5, 5, "eq", True),
        (5, 6, "eq", False),
        (5, 6, "ne", True),
        # mixed types coerce to strings ("5" == 5)
        (5, "5", "eq", True),
        ("abc", "abc", "eq", True),
        ("abc", "abd", "ne", True),
        # ordering — numeric
        (1, 2, "lt", True),
        (2, 2, "le", True),
        (3, 2, "gt", True),
        (2, 2, "ge", True),
        (10, 9, "gt", True),
        # ordering — string (lexicographic)
        ("10", "9", "lt", True),  # "1" < "9" lexicographically
        ("apple", "banana", "lt", True),
        # string operators
        ("hello world", "world", "contains", True),
        ("hello", "he", "starts_with", True),
        ("hello", "lo", "ends_with", True),
        ("hello", "zz", "contains", False),
        # bools are NOT treated as numbers (string coercion)
        (True, "True", "eq", True),
    ],
)
def test_operators(a, b, op, expected):
    assert _run(a, b, op) is expected


def test_default_op_is_eq():
    assert _run("x", "x") is True
    assert _run("x", "y") is False


def test_unknown_op_raises():
    with pytest.raises(ToolException, match="unknown op"):
        _run("a", "b", "between")
