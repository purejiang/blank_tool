#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
getevent parser — stdlib-only, pure functions, no IO.

Parses raw Android ``getevent`` output into automation steps that match the
consumer schema of the ``adb_auto`` plugin:

  * ``find_touchscreen``   — pick the touchscreen + axis maxima from
    ``getevent -pl`` output.
  * ``parse_screen_size``  — read the (possibly overridden) ``wm size`` output.
  * ``GeteventStatefulParser`` — feed ``getevent -lt`` lines, pop completed
    tap/swipe steps (tap: ``x``/``y``; swipe: ``x1``/``y1``/``x2``/``y2``/
    ``duration_ms``; every step carries ``ts`` — device-time seconds of the
    touch END marker, used by the frontend to synthesize ``wait`` gaps).

Strings in, data out. Unparseable lines are silently skipped and never raise;
incomplete touches (no UP before the stream ends) are never emitted.
"""

import re
from typing import Dict, List, Optional, Tuple

# ----------------------------------------------------------------------
# line patterns
# ----------------------------------------------------------------------

# [  3428.167047] /dev/input/event2: EV_KEY       BTN_TOUCH            DOWN
# When getevent monitors a SINGLE device (getevent -lt /dev/input/eventN)
# the device prefix is OMITTED entirely:
# [     315.693233] EV_KEY       BTN_TOUCH            UP
# The device token is therefore optional; a line without it belongs to the
# one device the stream was started with.
_EVENT_RE = re.compile(
    r"^\[\s*(\d+(?:\.\d+)?)\](?:\s+(\S+):)?\s+EV_(\w+)\s+(\S+)\s+(\S+)\s*$"
)
_AXIS_MAX_RE = re.compile(r"ABS_MT_POSITION_([XY])\s*:.*?\bmax\s+(\d+)")
_OVERRIDE_SIZE_RE = re.compile(r"Override size:\s*(\d+)x(\d+)")
_PHYSICAL_SIZE_RE = re.compile(r"Physical size:\s*(\d+)x(\d+)")

_DEVICE_HEADER_RE = re.compile(r"^add device \d+:\s+(\S+)")

_TRACKING_LIFTED = 0xFFFFFFFF

# step classification thresholds
_TAP_MAX_DISPLACEMENT_PX = 10
_TAP_MAX_DURATION_MS = 300.0


# ----------------------------------------------------------------------
# find_touchscreen
# ----------------------------------------------------------------------

def _split_device_blocks(text: str) -> List[Tuple[str, str]]:
    """Split ``getevent -pl`` text into (device_path, block_text) pairs."""
    blocks: List[Tuple[str, str]] = []
    path = ""
    lines: List[str] = []
    for line in text.splitlines():
        m = _DEVICE_HEADER_RE.match(line)
        if m:
            if path:
                blocks.append((path, "\n".join(lines)))
            path = m.group(1)
            lines = [line]
        elif path:
            lines.append(line)
    if path:
        blocks.append((path, "\n".join(lines)))
    return blocks


def find_touchscreen(getevent_pl_text: str) -> Dict[str, object]:
    """Pick the touchscreen device from ``getevent -pl`` output.

    A device qualifies when its block contains ``ABS_MT_POSITION_X`` and
    either ``BTN_TOUCH`` or ``ABS_MT_TRACKING_ID``. The first qualifying
    device is returned as ``device``; all qualifying paths are listed in
    ``candidates`` in order. Raises ``ValueError`` when none qualifies.
    """
    candidates: List[str] = []
    max_x = 0
    max_y = 0
    for path, block in _split_device_blocks(getevent_pl_text):
        if "ABS_MT_POSITION_X" not in block:
            continue
        if "BTN_TOUCH" not in block and "ABS_MT_TRACKING_ID" not in block:
            continue
        candidates.append(path)
        if len(candidates) == 1:
            for m in _AXIS_MAX_RE.finditer(block):
                if m.group(1) == "X":
                    max_x = int(m.group(2))
                else:
                    max_y = int(m.group(2))

    if not candidates:
        raise ValueError("no touchscreen device found")
    return {
        "device": candidates[0],
        "max_x": max_x,
        "max_y": max_y,
        "candidates": candidates,
    }


# ----------------------------------------------------------------------
# parse_screen_size
# ----------------------------------------------------------------------

def parse_screen_size(wm_size_text: str) -> Tuple[int, int]:
    """Read ``(width, height)`` from ``adb shell wm size`` output.

    ``Override size:`` wins over ``Physical size:`` when both are present.
    Raises ``ValueError`` when neither parses.
    """
    for pattern in (_OVERRIDE_SIZE_RE, _PHYSICAL_SIZE_RE):
        m = pattern.search(wm_size_text)
        if m:
            return int(m.group(1)), int(m.group(2))
    raise ValueError("no screen size found in wm size output")


# ----------------------------------------------------------------------
# stateful -lt stream parser
# ----------------------------------------------------------------------

def _key_pressed(value: str) -> Optional[bool]:
    """BTN_TOUCH value -> pressed state. ``DOWN``/``UP`` labels and raw hex
    (``00000001``/``00000000``) are both accepted; unknown -> None (skip)."""
    v = value.strip().upper()
    if v == "DOWN":
        return True
    if v == "UP":
        return False
    try:
        return int(value, 16) != 0
    except ValueError:
        return None


def _hex_value(value: str) -> Optional[int]:
    try:
        return int(value, 16)
    except ValueError:
        return None


class GeteventStatefulParser:
    """Accumulate ``getevent -lt`` lines and emit completed tap/swipe steps.

    Rules:
      * touch starts on BTN_TOUCH DOWN/1 or ABS_MT_TRACKING_ID != ffffffff;
        ends on BTN_TOUCH UP/0 or ffffffff. Only the first active touch is
        tracked — further tracking-id/BTN_TOUCH sequences during an active
        touch are ignored.
      * positions captured before each SYN_REPORT update the current raw
        position; the trajectory keeps the first and last points.
      * duration = end-marker timestamp - start-marker timestamp (seconds).
      * conversion at touch end: screen = round(raw * screen_dim / axis_max).
      * classification: screen-space displacement <= 10 px and duration
        < 300 ms -> tap (first point); otherwise swipe (first -> last).
      * every emitted step carries ``ts`` (float, device-time seconds of the
        touch END marker) so consumers can synthesize inter-step waits.
      * garbage lines are skipped silently; a touch that never ends is
        discarded (never emitted, never raised).
    """

    def __init__(self, max_x: int, max_y: int, screen_w: int, screen_h: int):
        self._max_x = int(max_x)
        self._max_y = int(max_y)
        self._screen_w = int(screen_w)
        self._screen_h = int(screen_h)
        self._active = False
        self._start_ts = 0.0
        self._first: Optional[Tuple[int, int]] = None
        self._last: Optional[Tuple[int, int]] = None
        self._cur_x = 0
        self._cur_y = 0
        self._dirty = False  # raw positions seen since last commit
        self._completed: List[Dict[str, object]] = []

    # -- public API ----------------------------------------------------

    def feed(self, line: str) -> None:
        m = _EVENT_RE.match(line)
        if not m:
            return  # garbage / non-event line: silently skipped
        ts = float(m.group(1))
        etype = m.group(3)
        code = m.group(4)
        value = m.group(5)
        if etype == "KEY" and code == "BTN_TOUCH":
            self._on_btn_touch(ts, value)
        elif etype == "ABS" and code == "ABS_MT_TRACKING_ID":
            self._on_tracking_id(ts, value)
        elif etype == "ABS" and code == "ABS_MT_POSITION_X":
            self._on_position("x", value)
        elif etype == "ABS" and code == "ABS_MT_POSITION_Y":
            self._on_position("y", value)
        elif etype == "SYN" and code == "SYN_REPORT":
            self._on_syn_report()
        # any other event type/code (slots, keyboard keys, ...) is ignored

    def pop_completed_steps(self) -> List[Dict[str, object]]:
        steps = self._completed
        self._completed = []
        return steps

    # -- event handlers --------------------------------------------------

    def _on_btn_touch(self, ts: float, value: str) -> None:
        pressed = _key_pressed(value)
        if pressed is None:
            return
        if pressed and not self._active:
            self._begin(ts)
        elif not pressed and self._active:
            self._end(ts)
        # else: stray marker while already started/ended — ignored

    def _on_tracking_id(self, ts: float, value: str) -> None:
        tid = _hex_value(value)
        if tid is None:
            return
        if tid == _TRACKING_LIFTED:
            if self._active:
                self._end(ts)
        elif not self._active:
            self._begin(ts)
        # else: another finger's id while tracking the first touch — ignored

    def _on_position(self, axis: str, value: str) -> None:
        if not self._active:
            return
        raw = _hex_value(value)
        if raw is None:
            return
        if axis == "x":
            self._cur_x = raw
        else:
            self._cur_y = raw
        self._dirty = True

    def _on_syn_report(self) -> None:
        if self._active and self._dirty:
            self._commit()

    # -- state transitions -----------------------------------------------

    def _begin(self, ts: float) -> None:
        self._active = True
        self._start_ts = ts
        self._first = None
        self._last = None
        self._dirty = False

    def _commit(self) -> None:
        pos = (self._cur_x, self._cur_y)
        if self._first is None:
            self._first = pos
        self._last = pos
        self._dirty = False

    def _end(self, ts: float) -> None:
        if self._dirty:
            self._commit()
        self._active = False
        if self._first is None or self._last is None:
            return  # touch without any position: nothing to report
        if self._max_x <= 0 or self._max_y <= 0:
            return  # unusable axis maxima: cannot convert, discard
        fx, fy = self._convert(*self._first)
        lx, ly = self._convert(*self._last)
        duration_ms = (ts - self._start_ts) * 1000.0
        if (abs(lx - fx) <= _TAP_MAX_DISPLACEMENT_PX
                and abs(ly - fy) <= _TAP_MAX_DISPLACEMENT_PX
                and duration_ms < _TAP_MAX_DURATION_MS):
            self._completed.append({"action": "tap", "x": fx, "y": fy, "ts": ts})
        else:
            self._completed.append({
                "action": "swipe",
                "x1": fx, "y1": fy, "x2": lx, "y2": ly,
                "duration_ms": max(1, round(duration_ms)),
                "ts": ts,
            })

    def _convert(self, raw_x: int, raw_y: int) -> Tuple[int, int]:
        return (
            round(raw_x * self._screen_w / self._max_x),
            round(raw_y * self._screen_h / self._max_y),
        )
