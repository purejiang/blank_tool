"""T1 regression test: the ``app.protocol`` package must export the message
payload classes and error codes alongside the existing type-system/port
symbols, and ``main`` must stay importable.
"""

import main
from app.protocol import (
    BackendSuccessPayload,
    BackendErrorPayload,
    ErrorCode,
    BaseType,
    TypeAnnotation,
    Port,
    PortSet,
)


# ---------------------------------------------------------------------------
# (a) message payloads + ErrorCode importable from app.protocol
# ---------------------------------------------------------------------------

def test_all_message_symbols_importable_from_app_protocol():
    # The import above would raise ImportError if any symbol were missing;
    # the is-not-None asserts guard against a silent partial re-export.
    for symbol in (
        BackendSuccessPayload,
        BackendErrorPayload,
        ErrorCode,
    ):
        assert symbol is not None


# ---------------------------------------------------------------------------
# (b) existing package symbols still importable
# ---------------------------------------------------------------------------

def test_all_package_symbols_still_importable_from_app_protocol():
    for symbol in (BaseType, TypeAnnotation, Port, PortSet):
        assert symbol is not None


# ---------------------------------------------------------------------------
# (c) ErrorCode values survived the move (sanity check)
# ---------------------------------------------------------------------------

def test_error_code_values_survived_the_move():
    assert ErrorCode.PARSE_ERROR == -32700
    assert ErrorCode.METHOD_NOT_FOUND == -32601
    assert ErrorCode.INTERNAL_ERROR == -32603


# ---------------------------------------------------------------------------
# (d) ``import main`` works (currently the bug: raises ImportError)
# ---------------------------------------------------------------------------

def test_main_module_imports_without_error():
    # main.py does ``from app.protocol import ErrorCode``; a broken import
    # chain raises ImportError when importing main.
    assert main is not None
    assert hasattr(main, "bootstrap")
