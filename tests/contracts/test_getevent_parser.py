"""
Contract tests for the pure getevent parser (``app.utils.getevent_parser``).

The parser is stdlib-only and side-effect free: string in, data out. These
tests pin the exact step schema consumed by ``backend/app/plugins/adb_auto.py``
(tap: ``x``/``y``; swipe: ``x1``/``y1``/``x2``/``y2``/``duration_ms``).
"""
import pytest

from app.utils.getevent_parser import (
    GeteventStatefulParser,
    find_touchscreen,
    parse_screen_size,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _ev(ts: float, etype: str, code: str, value: str,
        dev: str = "/dev/input/event2") -> str:
    """One ``getevent -lt`` event line (spacing mirrors real output)."""
    return f"[  {ts:.6f}] {dev}: EV_{etype:<11} {code:<20} {value}"


def _ev_solo(ts: float, etype: str, code: str, value: str) -> str:
    """One ``getevent -lt <device>`` event line — single-device streams have
    NO device prefix (verified against MuMu emulator `adb shell -tt getevent
    -lt /dev/input/event4`); PTY mode may append a trailing \\r."""
    return f"[{ts:.6f}] EV_{etype:<11} {code:<20} {value}\r"


def _pl_block(index: int, dev: str, name: str, key_lines, abs_lines) -> str:
    lines = [f"add device {index}: {dev}", f'  name: "{name}"', "  events: "]
    lines += [f"    KEY (0001): {k}" for k in key_lines]
    lines += [f"    ABS (0003): {a}" for a in abs_lines]
    return "\n".join(lines)


TOUCHSCREEN_BLOCK = _pl_block(
    2, "/dev/input/event2", "goodix-ts",
    key_lines=["BTN_TOUCH"],
    abs_lines=[
        "ABS_MT_POSITION_X : value 0, min 0, max 3974, fuzz 0, flat 0, resolution 0",
        "ABS_MT_POSITION_Y : value 0, min 0, max 2198, fuzz 0, flat 0, resolution 0",
        "ABS_MT_TRACKING_ID : value 0, min 0, max 65535, fuzz 0, flat 0",
    ],
)

KEYBOARD_BLOCK = _pl_block(
    1, "/dev/input/event0", "mtk-kpd",
    key_lines=["014a  014b"], abs_lines=[],
)


# ---------------------------------------------------------------------------
# find_touchscreen
# ---------------------------------------------------------------------------

class TestFindTouchscreen:
    def test_normal_block(self):
        text = KEYBOARD_BLOCK + "\n\n" + TOUCHSCREEN_BLOCK + "\n"
        res = find_touchscreen(text)
        assert res["device"] == "/dev/input/event2"
        assert res["max_x"] == 3974
        assert res["max_y"] == 2198
        assert res["candidates"] == ["/dev/input/event2"]

    def test_keyboard_only_raises(self):
        with pytest.raises(ValueError, match="no touchscreen device found"):
            find_touchscreen(KEYBOARD_BLOCK + "\n")

    def test_multiple_candidates_ordered(self):
        second = _pl_block(
            3, "/dev/input/event5", "secondary-ts",
            key_lines=["BTN_TOUCH"],
            abs_lines=[
                "ABS_MT_POSITION_X : value 0, min 0, max 1079, fuzz 0, flat 0",
                "ABS_MT_POSITION_Y : value 0, min 0, max 2339, fuzz 0, flat 0",
            ],
        )
        res = find_touchscreen(TOUCHSCREEN_BLOCK + "\n\n" + second + "\n")
        assert res["device"] == "/dev/input/event2"
        assert res["max_x"] == 3974 and res["max_y"] == 2198
        assert res["candidates"] == ["/dev/input/event2", "/dev/input/event5"]


# ---------------------------------------------------------------------------
# parse_screen_size
# ---------------------------------------------------------------------------

class TestParseScreenSize:
    def test_override_wins_over_physical(self):
        text = "Physical size: 1080x2400\nOverride size: 1080x2280\n"
        assert parse_screen_size(text) == (1080, 2280)

    def test_physical_only(self):
        assert parse_screen_size("Physical size: 1080x2400\n") == (1080, 2400)

    def test_garbage_raises(self):
        with pytest.raises(ValueError):
            parse_screen_size("adb: no devices found\n")


# ---------------------------------------------------------------------------
# GeteventStatefulParser
# ---------------------------------------------------------------------------

class TestTap:
    def test_tap_label_down_up_with_conversion(self):
        # raw X = 3974 (0xf86), max_x = 3974, screen_w = 1057 -> x = 1057
        # raw Y = 1100 (0x44c), max_y = 2198, screen_h = 600  -> y = 300
        p = GeteventStatefulParser(3974, 2198, 1057, 600)
        for line in [
            _ev(100.000000, "ABS", "ABS_MT_TRACKING_ID", "00000d4f"),
            _ev(100.000000, "KEY", "BTN_TOUCH", "DOWN"),
            _ev(100.001000, "ABS", "ABS_MT_POSITION_X", "00000f86"),
            _ev(100.001000, "ABS", "ABS_MT_POSITION_Y", "0000044c"),
            _ev(100.002000, "SYN", "SYN_REPORT", "00000000"),
            _ev(100.080000, "KEY", "BTN_TOUCH", "UP"),
            _ev(100.080000, "ABS", "ABS_MT_TRACKING_ID", "ffffffff"),
            _ev(100.081000, "SYN", "SYN_REPORT", "00000000"),
        ]:
            p.feed(line)
        assert p.pop_completed_steps() == [{"action": "tap", "x": 1057, "y": 300, "ts": 100.08}]

    def test_tap_hex_down_up_non_divisible_conversion(self):
        # raw X = 2605 (0xa2d), max_x = 3974, screen_w = 1080 -> 707.85 -> 708
        # raw Y = 2198 (0x896), max_y = 2198, screen_h = 600  -> 600
        p = GeteventStatefulParser(3974, 2198, 1080, 600)
        for line in [
            _ev(300.000000, "ABS", "ABS_MT_TRACKING_ID", "00000d4f"),
            _ev(300.000000, "KEY", "BTN_TOUCH", "00000001"),
            _ev(300.001000, "ABS", "ABS_MT_POSITION_X", "00000a2d"),
            _ev(300.001000, "ABS", "ABS_MT_POSITION_Y", "00000896"),
            _ev(300.002000, "SYN", "SYN_REPORT", "00000000"),
            _ev(300.120000, "KEY", "BTN_TOUCH", "00000000"),
            _ev(300.120000, "ABS", "ABS_MT_TRACKING_ID", "ffffffff"),
            _ev(300.121000, "SYN", "SYN_REPORT", "00000000"),
        ]:
            p.feed(line)
        steps = p.pop_completed_steps()
        assert steps == [{"action": "tap", "x": 708, "y": 600, "ts": 300.12}]
        # tap step must carry exactly the consumer schema: no duration, no x2
        assert set(steps[0].keys()) == {"action", "x", "y", "ts"}


class TestSwipe:
    def test_swipe_with_trajectory(self):
        # first (852,900)->(232,246); last (3100,640)->(842,175); 350 ms
        p = GeteventStatefulParser(3974, 2198, 1080, 600)
        for line in [
            _ev(200.000000, "ABS", "ABS_MT_TRACKING_ID", "00000d4f"),
            _ev(200.000000, "KEY", "BTN_TOUCH", "00000001"),
            _ev(200.001000, "ABS", "ABS_MT_POSITION_X", "00000354"),
            _ev(200.001000, "ABS", "ABS_MT_POSITION_Y", "00000384"),
            _ev(200.002000, "SYN", "SYN_REPORT", "00000000"),
            _ev(200.150000, "ABS", "ABS_MT_POSITION_X", "00000c1c"),
            _ev(200.150000, "ABS", "ABS_MT_POSITION_Y", "00000280"),
            _ev(200.151000, "SYN", "SYN_REPORT", "00000000"),
            _ev(200.350000, "KEY", "BTN_TOUCH", "00000000"),
            _ev(200.350000, "ABS", "ABS_MT_TRACKING_ID", "ffffffff"),
            _ev(200.351000, "SYN", "SYN_REPORT", "00000000"),
        ]:
            p.feed(line)
        assert p.pop_completed_steps() == [{
            "action": "swipe",
            "x1": 232, "y1": 246, "x2": 842, "y2": 175,
            "duration_ms": 350, "ts": 200.35,
        }]

    def test_fast_swipe_short_duration_still_swipe(self):
        # displacement > 10px with 100 ms duration -> swipe, not tap
        p = GeteventStatefulParser(3974, 2198, 1080, 600)
        for line in [
            _ev(400.000000, "ABS", "ABS_MT_TRACKING_ID", "00000d4f"),
            _ev(400.000000, "KEY", "BTN_TOUCH", "DOWN"),
            _ev(400.001000, "ABS", "ABS_MT_POSITION_X", "00000f86"),
            _ev(400.001000, "ABS", "ABS_MT_POSITION_Y", "00000896"),
            _ev(400.002000, "SYN", "SYN_REPORT", "00000000"),
            _ev(400.050000, "ABS", "ABS_MT_POSITION_X", "00000000"),
            _ev(400.050000, "ABS", "ABS_MT_POSITION_Y", "00000000"),
            _ev(400.051000, "SYN", "SYN_REPORT", "00000000"),
            _ev(400.100000, "KEY", "BTN_TOUCH", "UP"),
        ]:
            p.feed(line)
        assert p.pop_completed_steps() == [{
            "action": "swipe",
            "x1": 1080, "y1": 600, "x2": 0, "y2": 0,
            "duration_ms": 100, "ts": 400.1,
        }]


class TestSequences:
    def test_two_consecutive_taps(self):
        p = GeteventStatefulParser(3974, 2198, 1080, 600)
        for line in [
            # tap 1: (852,500) -> x=232, y=136; 50 ms
            _ev(600.000000, "ABS", "ABS_MT_TRACKING_ID", "00000d4f"),
            _ev(600.000000, "KEY", "BTN_TOUCH", "DOWN"),
            _ev(600.001000, "ABS", "ABS_MT_POSITION_X", "00000354"),
            _ev(600.001000, "ABS", "ABS_MT_POSITION_Y", "000001f4"),
            _ev(600.002000, "SYN", "SYN_REPORT", "00000000"),
            _ev(600.050000, "KEY", "BTN_TOUCH", "UP"),
            # tap 2: (2400,800) -> x=652, y=218; 60 ms
            _ev(601.000000, "ABS", "ABS_MT_TRACKING_ID", "00000e10"),
            _ev(601.000000, "KEY", "BTN_TOUCH", "DOWN"),
            _ev(601.001000, "ABS", "ABS_MT_POSITION_X", "00000960"),
            _ev(601.001000, "ABS", "ABS_MT_POSITION_Y", "00000320"),
            _ev(601.002000, "SYN", "SYN_REPORT", "00000000"),
            _ev(601.060000, "KEY", "BTN_TOUCH", "UP"),
        ]:
            p.feed(line)
        assert p.pop_completed_steps() == [
            {"action": "tap", "x": 232, "y": 136, "ts": 600.05},
            {"action": "tap", "x": 652, "y": 218, "ts": 601.06},
        ]
        # pop drains
        assert p.pop_completed_steps() == []

    def test_second_finger_ignored_first_touch_tracked(self):
        p = GeteventStatefulParser(3974, 2198, 1080, 600)
        for line in [
            _ev(500.000000, "ABS", "ABS_MT_TRACKING_ID", "00000d4f"),
            _ev(500.000000, "KEY", "BTN_TOUCH", "00000001"),
            _ev(500.001000, "ABS", "ABS_MT_POSITION_X", "000003e8"),
            _ev(500.001000, "ABS", "ABS_MT_POSITION_Y", "000003e8"),
            _ev(500.002000, "SYN", "SYN_REPORT", "00000000"),
            # finger B joins mid-touch: its tracking id must be ignored
            _ev(500.010000, "ABS", "ABS_MT_TRACKING_ID", "00000e10"),
            # finger A second frame (no movement)
            _ev(500.020000, "ABS", "ABS_MT_POSITION_X", "000003e8"),
            _ev(500.020000, "ABS", "ABS_MT_POSITION_Y", "000003e8"),
            _ev(500.021000, "SYN", "SYN_REPORT", "00000000"),
            # finger A lifts
            _ev(500.150000, "ABS", "ABS_MT_TRACKING_ID", "ffffffff"),
            _ev(500.150000, "KEY", "BTN_TOUCH", "00000000"),
            _ev(500.151000, "SYN", "SYN_REPORT", "00000000"),
        ]:
            p.feed(line)
        steps = p.pop_completed_steps()
        assert len(steps) == 1
        # (1000,1000) -> x=round(1000*1080/3974)=272, y=round(1000*600/2198)=273
        assert steps[0] == {"action": "tap", "x": 272, "y": 273, "ts": 500.15}


class TestSingleDeviceNoPrefix:
    """``getevent -lt <path>`` omits the device prefix — the format the
    recording handler actually receives (regression: every line was silently
    dropped and recording showed 0 steps)."""

    def test_tap_without_device_prefix(self):
        # emulator: max 900x1600 raw, screen 900x1600 -> raw == screen
        p = GeteventStatefulParser(900, 1600, 900, 1600)
        for line in [
            _ev_solo(315.813601, "ABS", "ABS_MT_TRACKING_ID", "00000001"),
            _ev_solo(315.813601, "KEY", "BTN_TOUCH", "DOWN"),
            _ev_solo(315.813601, "ABS", "ABS_MT_POSITION_X", "000002f9"),
            _ev_solo(315.813601, "ABS", "ABS_MT_POSITION_Y", "00000358"),
            _ev_solo(315.813601, "SYN", "SYN_REPORT", "ffffffff"),
            _ev_solo(315.898308, "ABS", "ABS_MT_TRACKING_ID", "0000c350"),
            _ev_solo(315.898308, "KEY", "BTN_TOUCH", "UP"),
            _ev_solo(315.898308, "SYN", "SYN_REPORT", "ffffffff"),
        ]:
            p.feed(line)
        assert p.pop_completed_steps() == [{"action": "tap", "x": 761, "y": 856, "ts": 315.898308}]

    def test_swipe_without_device_prefix(self):
        p = GeteventStatefulParser(900, 1600, 900, 1600)
        for line in [
            _ev_solo(400.000000, "ABS", "ABS_MT_TRACKING_ID", "00000001"),
            _ev_solo(400.000000, "KEY", "BTN_TOUCH", "DOWN"),
            _ev_solo(400.000000, "ABS", "ABS_MT_POSITION_X", "000002f9"),
            _ev_solo(400.000000, "ABS", "ABS_MT_POSITION_Y", "00000358"),
            _ev_solo(400.000000, "SYN", "SYN_REPORT", "ffffffff"),
            _ev_solo(400.100000, "ABS", "ABS_MT_POSITION_X", "0000012c"),
            _ev_solo(400.100000, "ABS", "ABS_MT_POSITION_Y", "00000320"),
            _ev_solo(400.100000, "SYN", "SYN_REPORT", "ffffffff"),
            _ev_solo(400.200000, "ABS", "ABS_MT_TRACKING_ID", "0000c350"),
            _ev_solo(400.200000, "KEY", "BTN_TOUCH", "UP"),
            _ev_solo(400.200000, "SYN", "SYN_REPORT", "ffffffff"),
        ]:
            p.feed(line)
        assert p.pop_completed_steps() == [{
            "action": "swipe",
            "x1": 761, "y1": 856, "x2": 300, "y2": 800,
            "duration_ms": 200, "ts": 400.2,
        }]

    def test_prefixed_and_prefixless_lines_mixed(self):
        """Both forms may interleave (e.g. all-device probe data replayed)."""
        p = GeteventStatefulParser(900, 1600, 900, 1600)
        for line in [
            _ev_solo(500.000000, "ABS", "ABS_MT_TRACKING_ID", "00000001"),
            _ev(500.000000, "KEY", "BTN_TOUCH", "DOWN"),
            _ev(500.000000, "ABS", "ABS_MT_POSITION_X", "000002f9"),
            _ev_solo(500.000000, "ABS", "ABS_MT_POSITION_Y", "00000358"),
            _ev_solo(500.000000, "SYN", "SYN_REPORT", "ffffffff"),
            _ev_solo(500.050000, "ABS", "ABS_MT_TRACKING_ID", "0000c350"),
            _ev_solo(500.050000, "KEY", "BTN_TOUCH", "UP"),
        ]:
            p.feed(line)
        assert p.pop_completed_steps() == [{"action": "tap", "x": 761, "y": 856, "ts": 500.05}]


class TestRobustness:
    def test_garbage_and_truncated_touch_produce_nothing(self):
        p = GeteventStatefulParser(3974, 2198, 1080, 600)
        garbage = [
            "",
            "hello world",
            "[ 12.0 garbage without device",
            "[ abc ] :::: broken ::::",
            "\x00\x01 binary junk \x7f",
            "EV_KEY BTN_TOUCH DOWN",  # missing timestamp/device prefix
            "[  1.000000] /dev/input/event2: EV_KEY BTN_TOUCH",  # missing value
            "x" * 10000,
        ]
        for line in garbage:
            p.feed(line)  # must never raise
        # truncated touch: starts but never ends before session end
        for line in [
            _ev(700.000000, "ABS", "ABS_MT_TRACKING_ID", "00000d4f"),
            _ev(700.000000, "KEY", "BTN_TOUCH", "DOWN"),
            _ev(700.001000, "ABS", "ABS_MT_POSITION_X", "00000354"),
            _ev(700.001000, "ABS", "ABS_MT_POSITION_Y", "000001f4"),
            _ev(700.002000, "SYN", "SYN_REPORT", "00000000"),
        ]:
            p.feed(line)
        assert p.pop_completed_steps() == []
        assert p.pop_completed_steps() == []

    def test_garbage_does_not_break_valid_touch(self):
        p = GeteventStatefulParser(3974, 2198, 1080, 600)
        for line in [
            "\x00 garbage \x00",
            "[ bad ] line ]]",
            # then a valid tap
            _ev(800.000000, "ABS", "ABS_MT_TRACKING_ID", "00000d4f"),
            _ev(800.000000, "KEY", "BTN_TOUCH", "DOWN"),
            _ev(800.001000, "ABS", "ABS_MT_POSITION_X", "00000354"),
            _ev(800.001000, "ABS", "ABS_MT_POSITION_Y", "000001f4"),
            _ev(800.002000, "SYN", "SYN_REPORT", "00000000"),
            _ev(800.090000, "KEY", "BTN_TOUCH", "UP"),
            "trailing junk after UP",
        ]:
            p.feed(line)
        assert p.pop_completed_steps() == [{"action": "tap", "x": 232, "y": 136, "ts": 800.09}]
