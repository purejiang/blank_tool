#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deprecated compat layer — re-exports from ``app.automation``.

Everything now lives in focused modules under ``app/automation/``:
adb / coords / input / elements / apps / crash / traffic. This shim keeps
``adb_handler`` and the ``adb_auto`` plugin imports working unchanged; it
will be removed once all callers import from the new package.
"""

# keep import location stable for callers of ``app.utils.adb_auto_core``
from app.automation.adb import (  # noqa: F401
    run_adb,
)
from app.automation.coords import (  # noqa: F401
    get_display_transform,
    rotate_to_display,
)
from app.automation.input import (  # noqa: F401
    ADB_IME_ID,
    ADB_IME_PKG,
    adb_ime_installed,
    back,
    ensure_adb_ime,
    home,
    input_text,
    keyevent,
    restore_ime,
    shell,
    swipe,
    tap,
)
from app.automation.elements import (  # noqa: F401
    find_element,
    tap_element,
    ui_dump,
)
from app.automation.apps import (  # noqa: F401
    clear_app_data,
    current_activity,
    get_app_pid,
    launch_app,
    take_screenshot,
)
from app.automation.crash import dump_crash_log  # noqa: F401
from app.automation import traffic  # noqa: F401
