"""T1 regression test: the ``app.protocol`` package must export the legacy
message classes (moved verbatim from ``app/protocol.py`` into
``app/protocol/messages.py``) alongside the existing type-system/port symbols,
and ``main`` must stay importable.

This is the failing-first regression for the protocol package collision bug:
before the fix, ``from app.protocol import BackendResponse`` raised ImportError
because the ``app/protocol/`` package shadowed the legacy ``app/protocol.py``
module (backend/main.py line 26 imports ErrorCode from app.protocol, and
app/api_handler.py lines 19-24 import the message classes from app.protocol).
"""

import json

import main
from app.protocol import (
    BackendResponse,
    BackendSuccessPayload,
    BackendErrorPayload,
    BackendStreamEvent,
    BackendApiRequest,
    ErrorCode,
    BaseType,
    TypeAnnotation,
    TypeRegistry,
    Port,
    PortSet,
)


# ---------------------------------------------------------------------------
# (a) all 6 message classes + ErrorCode importable from app.protocol
# ---------------------------------------------------------------------------

def test_all_legacy_message_symbols_importable_from_app_protocol():
    # The import above would raise ImportError if any symbol were missing;
    # the is-not-None asserts guard against a silent partial re-export.
    for symbol in (
        BackendResponse,
        BackendSuccessPayload,
        BackendErrorPayload,
        BackendStreamEvent,
        BackendApiRequest,
        ErrorCode,
    ):
        assert symbol is not None


# ---------------------------------------------------------------------------
# (b) existing package symbols still importable
# ---------------------------------------------------------------------------

def test_all_package_symbols_still_importable_from_app_protocol():
    for symbol in (BaseType, TypeAnnotation, TypeRegistry, Port, PortSet):
        assert symbol is not None


# ---------------------------------------------------------------------------
# (d) ErrorCode values survived the move (sanity check)
# ---------------------------------------------------------------------------

def test_error_code_values_survived_the_move():
    assert ErrorCode.PARSE_ERROR == -32700
    assert ErrorCode.METHOD_NOT_FOUND == -32601
    assert ErrorCode.INVALID_PARAMS == -32602
    assert ErrorCode.INTERNAL_ERROR == -32603
    assert ErrorCode.TIMEOUT == -32000
    assert ErrorCode.TOOL_ERROR == -32001


# ---------------------------------------------------------------------------
# behavioral check: the classes still behave (not just importable)
# ---------------------------------------------------------------------------

def test_backend_response_to_json_round_trip():
    resp = BackendResponse(id=7, result=BackendSuccessPayload(payload={"ok": True}))
    data = json.loads(resp.to_json())
    assert data["id"] == 7
    assert data["result"] == {"type": "success", "payload": {"ok": True}}
    assert data["finished"] is True


# ---------------------------------------------------------------------------
# (c) ``import main`` works (currently the bug: raises ImportError)
# ---------------------------------------------------------------------------

def test_main_module_imports_without_error():
    # main.py line 26 does ``from app.protocol import ErrorCode``; before the
    # fix this chain raised ImportError when importing main.
    assert main is not None
    assert hasattr(main, "bootstrap")
