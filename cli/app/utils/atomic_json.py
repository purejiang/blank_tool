#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Atomic JSON writes (temp file + ``os.replace``).

Shared by the stores that persist user data as one JSON document per file
(``app.workflow.store`` for saved workflows, ``app.task.store`` for task
definitions).  A reader either sees the previous complete file or the new
one — never a truncated prefix; without this, a save racing a concurrent
load makes the reader fail with "invalid JSON".

Windows raises ``PermissionError`` when the replace target is momentarily
open for reading (a concurrent load), so the replace is retried a few times
and the temp file is removed when every attempt failed.
"""

import json
import os
import time
from typing import Any, Dict, Optional

#: Windows raises PermissionError when the replace target is momentarily open
#: for reading (a concurrent ``load``), so the replace is retried a few times.
_REPLACE_ATTEMPTS = 3
_REPLACE_RETRY_DELAY_SECONDS = 0.05


def atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    """Write *data* as UTF-8 JSON to *path* via a temp file + ``os.replace``.

    The temp file lives next to *path* (same directory, so the replace stays
    on one filesystem), is written with 2-space indent and a trailing newline,
    and is deleted again when every replace attempt failed.

    Raises:
        OSError: the last replace error, after ``_REPLACE_ATTEMPTS`` tries.
    """
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    last_error: Optional[BaseException] = None
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(tmp_path, path)
            return
        except OSError as exc:  # destination briefly locked (Windows)
            last_error = exc
            time.sleep(_REPLACE_RETRY_DELAY_SECONDS * (attempt + 1))
    try:
        os.remove(tmp_path)
    except OSError:
        pass
    raise last_error  # type: ignore[misc]
