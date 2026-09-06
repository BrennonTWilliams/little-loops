"""Tests for hooks.py: hook execution telemetry (ENH-2506) (ENH-2775 split from test_history_reader.py)."""

from __future__ import annotations

from pathlib import Path

from little_loops.history_reader import (
    hook_failure_rate,
    hook_latency_p95,
    recent_hook_events,
)
from little_loops.session_store import (
    record_hook_event,
)


class TestHookEventReaders:
    """ENH-2506: recent_hook_events / hook_failure_rate / hook_latency_p95."""

    def test_recent_hook_events_recency_ordering(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_hook_event(
            db,
            ts="2026-07-19T10:00:00Z",
            session_id="s1",
            event_name="PostToolUse",
            matcher=None,
            script=None,
            exit_code=0,
            duration_ms=1,
        )
        record_hook_event(
            db,
            ts="2026-07-19T11:00:00Z",
            session_id="s1",
            event_name="PostToolUse",
            matcher=None,
            script=None,
            exit_code=0,
            duration_ms=2,
        )
        rows = recent_hook_events(db=db)
        assert [r.duration_ms for r in rows] == [2, 1]

    def test_recent_hook_events_filter_by_event_name(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_hook_event(
            db,
            session_id="s1",
            event_name="PostToolUse",
            matcher=None,
            script=None,
            exit_code=0,
            duration_ms=1,
        )
        record_hook_event(
            db,
            session_id="s1",
            event_name="PreCompact",
            matcher=None,
            script=None,
            exit_code=0,
            duration_ms=1,
        )
        rows = recent_hook_events(event_name="PreCompact", db=db)
        assert len(rows) == 1
        assert rows[0].event_name == "PreCompact"

    def test_recent_hook_events_filter_by_exit_code(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_hook_event(
            db,
            session_id="s1",
            event_name="PostToolUse",
            matcher=None,
            script=None,
            exit_code=0,
            duration_ms=1,
        )
        record_hook_event(
            db,
            session_id="s1",
            event_name="PostToolUse",
            matcher=None,
            script=None,
            exit_code=1,
            duration_ms=1,
        )
        rows = recent_hook_events(exit_code=1, db=db)
        assert len(rows) == 1
        assert rows[0].exit_code == 1

    def test_recent_hook_events_since_filter(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_hook_event(
            db,
            ts="2026-07-19T10:00:00Z",
            session_id="s1",
            event_name="PostToolUse",
            matcher=None,
            script=None,
            exit_code=0,
            duration_ms=1,
        )
        record_hook_event(
            db,
            ts="2026-07-19T12:00:00Z",
            session_id="s1",
            event_name="PostToolUse",
            matcher=None,
            script=None,
            exit_code=0,
            duration_ms=2,
        )
        rows = recent_hook_events(since="2026-07-19T11:00:00Z", db=db)
        assert len(rows) == 1
        assert rows[0].duration_ms == 2

    def test_hook_failure_rate(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for exit_code in (0, 0, 1):
            record_hook_event(
                db,
                session_id="s1",
                event_name="PostToolUse",
                matcher=None,
                script=None,
                exit_code=exit_code,
                duration_ms=1,
            )
        rate = hook_failure_rate("PostToolUse", db=db)
        assert rate is not None
        assert abs(rate - (1 / 3)) < 1e-9

    def test_hook_failure_rate_none_when_no_fires(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        assert hook_failure_rate("PostToolUse", db=db) is None

    def test_hook_latency_p95(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for duration_ms in range(1, 21):  # 1..20
            record_hook_event(
                db,
                session_id="s1",
                event_name="PostToolUse",
                matcher=None,
                script=None,
                exit_code=0,
                duration_ms=duration_ms,
            )
        p95 = hook_latency_p95("PostToolUse", db=db)
        assert p95 == 19.0

    def test_hook_latency_p95_none_when_no_fires(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        assert hook_latency_p95("PostToolUse", db=db) is None
