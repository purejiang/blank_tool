"""Contract tests for ``app.automation.apps.current_activity``.

Two defects are locked here:

1. The resumed-activity KEY is ROM/API dependent. Only ``mResumedActivity``
   was matched, so ``assert_activity`` failed on every device that prints
   ``topResumedActivity`` (Android 10+) or a bare ``ResumedActivity``.
2. ``timeout_ms`` was accepted and then ignored: a single ``dumpsys`` shot
   failed whenever the navigation had not settled yet. It now polls.

The result shape ``{success, activity, error}`` is the contract the
``device.current_activity`` handler (and through it the UI "grab activity"
button) types against.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from app.automation import apps  # noqa: E402


def _dumpsys(*lines):
    return {"returncode": 0, "stdout": "\n".join(lines), "stderr": ""}


LEGACY = (
    "  mResumedActivity: ActivityRecord{1a2b3c u0 com.demo/.MainActivity t42}"
)
MODERN_TOP = (
    "    topResumedActivity=ActivityRecord{2b3c4d u0 com.other/.Settings t7}"
)
BARE = "  ResumedActivity: ActivityRecord{3c4d5e u0 com.third/.Home t9}"
NO_ACTIVITY = "  no activities here"


def _run(monkeypatch, outputs, record=None):
    """Patch ``run_adb`` with a queue of dumpsys outputs."""
    queue = list(outputs)

    def fake_run_adb(device_id, args, *a, **kw):
        if record is not None:
            record.append(tuple(args))
        return queue.pop(0) if queue else _dumpsys(NO_ACTIVITY)

    monkeypatch.setattr(apps, "run_adb", fake_run_adb)


class TestResumedActivityKeyVariants:
    def test_legacy_mresumedactivity(self, monkeypatch):
        _run(monkeypatch, [_dumpsys(LEGACY)])
        out = apps.current_activity("emulator-5554")
        assert out == {"success": True, "activity": "com.demo/.MainActivity", "error": ""}

    def test_modern_topresumedactivity(self, monkeypatch):
        """REGRESSION: Android 10+ prints `topResumedActivity`."""
        _run(monkeypatch, [_dumpsys(MODERN_TOP)])
        out = apps.current_activity("emulator-5554")
        assert out["success"] is True
        assert out["activity"] == "com.other/.Settings"

    def test_bare_resumedactivity(self, monkeypatch):
        _run(monkeypatch, [_dumpsys(BARE)])
        out = apps.current_activity("emulator-5554")
        assert out["success"] is True
        assert out["activity"] == "com.third/.Home"

    def test_queries_dumpsys_activity_activities(self, monkeypatch):
        calls = []
        _run(monkeypatch, [_dumpsys(MODERN_TOP)], record=calls)
        apps.current_activity("emulator-5554")
        assert calls == [("shell", "dumpsys", "activity", "activities")]


class TestTimeoutIsHonoured:
    def test_polls_until_the_transition_settles(self, monkeypatch):
        """First dump has no resumed activity, the second one does."""
        _run(monkeypatch, [_dumpsys(NO_ACTIVITY), _dumpsys(MODERN_TOP)])
        out = apps.current_activity("emulator-5554", timeout_ms=2000)
        assert out["success"] is True
        assert out["activity"] == "com.other/.Settings"

    def test_gives_up_after_the_timeout(self, monkeypatch):
        calls = []
        _run(monkeypatch, [_dumpsys(NO_ACTIVITY)] * 10, record=calls)
        out = apps.current_activity("emulator-5554", timeout_ms=300)
        assert out["success"] is False
        assert out["activity"] == ""
        assert out["error"]
        assert 1 <= len(calls) <= 4, f"polled {len(calls)} times for a 300ms budget"

    def test_zero_timeout_is_a_single_shot(self, monkeypatch):
        calls = []
        _run(monkeypatch, [_dumpsys(NO_ACTIVITY)] * 10, record=calls)
        out = apps.current_activity("emulator-5554", timeout_ms=0)
        assert out["success"] is False
        assert len(calls) == 1

    def test_non_numeric_timeout_does_not_raise(self, monkeypatch):
        _run(monkeypatch, [_dumpsys(LEGACY)])
        out = apps.current_activity("emulator-5554", timeout_ms="nonsense")
        assert out["success"] is True

    def test_adb_failure_surfaces_stderr(self, monkeypatch):
        _run(monkeypatch, [{"returncode": 1, "stdout": "", "stderr": "device offline"}])
        out = apps.current_activity("emulator-5554", timeout_ms=0)
        assert out["success"] is False
        assert out["error"] == "device offline"


class TestAssertActivityStep:
    """``steps._assert_activity`` consumes the same helper."""

    def test_assertion_passes_on_modern_dumpsys(self, monkeypatch):
        from app.automation import steps

        _run(monkeypatch, [_dumpsys(MODERN_TOP)])
        ok, message, shot = steps.execute_step(
            None, "emulator-5554", None, "assert_activity",
            {"action": "assert_activity", "activity": "com.other/.Settings"},
            {"rotation": 0, "width": 1080, "height": 1920},
        )
        assert ok is True
        assert message == ""
        assert shot is None

    def test_assertion_fails_with_the_seen_activity(self, monkeypatch):
        from app.automation import steps

        _run(monkeypatch, [_dumpsys(MODERN_TOP)])
        ok, message, _ = steps.execute_step(
            None, "emulator-5554", None, "assert_activity",
            {"action": "assert_activity", "activity": "com.wanted/.Screen"},
            {"rotation": 0, "width": 1080, "height": 1920},
        )
        assert ok is False
        assert "com.other/.Settings" in message
