#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pure normalization of a descriptor/code tool result dict.

Descriptor and code tools return a ``{success, returncode, stdout, stderr, ...}``
shape.  Two call sites used to re-derive the same "is this a failure, and if so
build the message" logic by hand:

  * ``WorkflowEngine._execute_tool`` (cli/app/workflow/engine.py)
  * the headless ``cmd_tool`` (cli/cli.py)

That duplication is consolidated here so the failure message stays byte-for-byte
identical across both paths.  No behaviour change: defaults (success=True,
returncode=0) and the ``stderr``/``stdout`` detail fallback match the previous
inline code.
"""

from typing import Tuple


def normalize_result(result: dict, tool_name: str) -> Tuple[bool, str]:
    """Return ``(ok, message)`` for a descriptor/code tool result dict.

    ``ok`` is False when ``success is False`` or ``returncode != 0``; in that
    case ``message`` is the failure text (exit code plus optional
    stderr/stdout detail).  Otherwise ``ok`` is True and ``message`` is "".
    """
    success = result.get("success", True)
    returncode = result.get("returncode", 0)
    if success is False or returncode != 0:
        detail = (result.get("stderr") or result.get("stdout") or "").strip()
        message = f"tool {tool_name!r} failed (exit {returncode})"
        if detail:
            message += f": {detail}"
        return False, message
    return True, ""
