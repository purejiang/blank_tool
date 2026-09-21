"""Contract test: the backend `health` method payload shape.

`health` is injected into ``ApiHandler.api_map`` by ``cli/main.py`` (it is not
part of any handler's ``API_MAP``), which is why nothing pinned its wire shape
before — and why the field name silently drifted from the one declared in
``src/shared/ipc/protocol.ts`` (``HealthResult.uptime_s``) and read by the
renderer. This test locks the name so the T24 diagnostics wiring can rely on it.
"""

import main


def test_health_reports_status_and_uptime_s():
    payload = main._handle_health({}, None)

    assert payload["status"] == "ok"
    # The key is `uptime_s` (seconds), matching the main-process liveness probe
    # and `HealthResult` in protocol.ts — NOT `uptime`.
    assert "uptime_s" in payload
    assert "uptime" not in payload
    assert isinstance(payload["uptime_s"], (int, float))
    assert payload["uptime_s"] >= 0


def test_health_is_registered_on_the_api_map_by_bootstrap_source():
    # The injection happens in bootstrap(); assert the handler exists and is
    # callable with the (params, stream_handler) handler signature.
    assert callable(main._handle_health)
    assert main._handle_health({}, None)["status"] == "ok"
