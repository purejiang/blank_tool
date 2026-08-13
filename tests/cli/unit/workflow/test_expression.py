"""Wave 3 tests: workflow expression engine.

Covers dot-notation resolution against all four context roots (inputs,
nodes, env, workdir), the three built-in pipes (basename / dirname /
default:<value>), passthrough of non-expression values, recursive
resolve_params, and the security/error surface (dunder rejection, unknown
pipes, unresolvable references).
"""

import pytest

from app.workflow.expression import ExpressionEngine, ExpressionError, WorkflowContext


def _engine() -> ExpressionEngine:
    return ExpressionEngine()


def _context(**overrides) -> WorkflowContext:
    data = {
        "inputs": {
            "x": "hello",
            "n": 42,
            "flag": True,
            "items": ["a", "b"],
            "empty": "",
            "none": None,
        },
        "nodes": {
            "write": {
                "outputs": {"path": "/tmp/a/out.txt"},
                "params": {"content": "hi"},
            }
        },
        "env": {"NAME": "world"},
        "workdir": "/tmp",
    }
    data.update(overrides)
    return WorkflowContext(**data)


# ---------------------------------------------------------------------------
# Dot-notation resolution
# ---------------------------------------------------------------------------

def test_resolve_inputs_returns_value():
    assert _engine().resolve("$inputs.x", _context()) == "hello"


def test_resolve_nodes_outputs_traverses_nested_dict():
    assert _engine().resolve("$nodes.write.outputs.path", _context()) == "/tmp/a/out.txt"


def test_resolve_nodes_params():
    assert _engine().resolve("$nodes.write.params.content", _context()) == "hi"


def test_resolve_env():
    assert _engine().resolve("$env.NAME", _context()) == "world"


def test_resolve_workdir():
    assert _engine().resolve("$workdir", _context()) == "/tmp"


# ---------------------------------------------------------------------------
# Pipes
# ---------------------------------------------------------------------------

def test_pipe_basename():
    assert _engine().resolve("$nodes.write.outputs.path | basename", _context()) == "out.txt"


def test_pipe_dirname():
    assert _engine().resolve("$nodes.write.outputs.path | dirname", _context()) == "/tmp/a"


def test_pipe_chained():
    assert _engine().resolve("$nodes.write.outputs.path | dirname | basename", _context()) == "a"


def test_pipe_default_substitutes_when_empty():
    assert _engine().resolve("$inputs.empty | default:fallback", _context()) == "fallback"


def test_pipe_default_substitutes_when_none():
    assert _engine().resolve("$inputs.none | default:fallback", _context()) == "fallback"


def test_pipe_default_keeps_value_when_present():
    assert _engine().resolve("$inputs.x | default:fallback", _context()) == "hello"


# ---------------------------------------------------------------------------
# Passthrough
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [42, True, [1, 2], {"k": "v"}, None, 3.5])
def test_non_string_passthrough(value):
    assert _engine().resolve(value, _context()) is value


def test_plain_string_without_dollar_passthrough():
    assert _engine().resolve("prefix $inputs.x", _context()) == "prefix $inputs.x"


# ---------------------------------------------------------------------------
# $$ escape
# ---------------------------------------------------------------------------

def test_escape_double_dollar():
    assert _engine().resolve("$$HOME/foo", _context()) == "$HOME/foo"


def test_escape_only_double_dollar():
    assert _engine().resolve("$$", _context()) == "$"


def test_single_dollar_still_resolves():
    assert _engine().resolve("$inputs.x", _context()) == "hello"


def test_no_dollar_passes_through():
    assert _engine().resolve("plain text", _context()) == "plain text"


def test_resolve_params_recursively_resolves_nesting():
    params = {
        "a": "$inputs.x",
        "b": {"c": "$env.NAME", "d": ["$inputs.n"]},
        "e": 5,
    }
    resolved = _engine().resolve_params(params, _context())
    assert resolved == {
        "a": "hello",
        "b": {"c": "world", "d": [42]},
        "e": 5,
    }
    # input dict is not mutated
    assert params["a"] == "$inputs.x"


# ---------------------------------------------------------------------------
# Error surface
# ---------------------------------------------------------------------------

def test_dunder_access_raises():
    with pytest.raises(ExpressionError, match="dunder access rejected: __class__"):
        _engine().resolve("$inputs.__class__", _context())


def test_unknown_pipe_raises():
    with pytest.raises(ExpressionError, match="unknown pipe: eval"):
        _engine().resolve("$inputs.x | eval", _context())


def test_unresolvable_reference_raises_with_key():
    with pytest.raises(ExpressionError, match="missing key: 'missing'"):
        _engine().resolve("$inputs.missing", _context())


def test_unknown_root_raises():
    with pytest.raises(ExpressionError, match="unknown root 'foo'"):
        _engine().resolve("$foo.bar", _context())


def test_missing_node_raises():
    with pytest.raises(ExpressionError, match="missing node: 'ghost'"):
        _engine().resolve("$nodes.ghost.outputs.x", _context())


def test_unknown_node_section_raises():
    with pytest.raises(ExpressionError, match="unknown node section 'secrets'"):
        _engine().resolve("$nodes.write.secrets.x", _context())


def test_basename_pipe_requires_string():
    with pytest.raises(ExpressionError, match="requires a string value"):
        _engine().resolve("$inputs.n | basename", _context())


def test_malformed_nodes_shape_raises():
    with pytest.raises(ExpressionError, match="malformed expression"):
        _engine().resolve("$nodes.write.outputs", _context())


def test_workdir_rejects_further_keys():
    with pytest.raises(ExpressionError, match="takes no further keys"):
        _engine().resolve("$workdir.sub", _context())
