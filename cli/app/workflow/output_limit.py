#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Size discipline for recorded node results.

Node outputs are copied three times over: into the in-memory run result, into
the streamed terminal payload, and into the run-history file on disk.  A tool
that returns a large blob (``file.read`` of a big file, a command's captured
stdout, a ``flow.foreach`` over many items) would therefore multiply its size
by three and can push a single history record into the hundreds of megabytes.

:func:`shrink_outputs` bounds that copy: long strings are replaced by a
truncation marker that keeps a preview and the original length.  It is applied
ONLY to the recorded copy — ``$nodes.<id>.outputs.*`` expression resolution
uses the untruncated values, so workflows that pass data between nodes are
unaffected.
"""

from typing import Any, Dict, List, Optional

#: Longest string kept verbatim in a recorded result.
MAX_STRING_CHARS = 8 * 1024

#: Total character budget for one recorded result.
MAX_TOTAL_CHARS = 256 * 1024

_TRUNCATED_KEY = "_truncated"


def _marker(value: str, kept: int, reason: Optional[str] = None) -> Dict[str, Any]:
    marker: Dict[str, Any] = {
        _TRUNCATED_KEY: True,
        "_chars": len(value),
        "_preview": value[: max(0, kept)],
    }
    if reason:
        marker["_reason"] = reason
    return marker


def _shrink(value: Any, budget: List[int]) -> Any:
    if isinstance(value, str):
        if budget[0] <= 0:
            return _marker(value, 0, "result size budget exceeded")
        if len(value) > MAX_STRING_CHARS:
            kept = min(MAX_STRING_CHARS, budget[0])
            budget[0] -= kept
            return _marker(value, kept, "string longer than 8 KiB")
        budget[0] -= len(value)
        return value
    if isinstance(value, dict):
        return {key: _shrink(item, budget) for key, item in value.items()}
    if isinstance(value, list):
        return [_shrink(item, budget) for item in value]
    return value


def shrink_outputs(value: Any) -> Any:
    """Return a size-bounded copy of a node's outputs.

    Strings longer than :data:`MAX_STRING_CHARS`, and any content past
    :data:`MAX_TOTAL_CHARS`, become ``{"_truncated": True, "_chars": <len>,
    "_preview": <head>}`` markers.  Non-string scalars and the structure
    (dict keys / list length) are preserved.
    """
    return _shrink(value, [MAX_TOTAL_CHARS])
