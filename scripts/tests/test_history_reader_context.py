"""Tests for context.py: context-pressure curve/crossings/summary queries (ENH-2507) (ENH-2775 split from test_history_reader.py)."""

from __future__ import annotations

from pathlib import Path

from little_loops.history_reader import (
    context_pressure_curve,
    pressure_crossings,
    pressure_summary,
)
from little_loops.session_store import (
    ensure_db,
    record_context_pressure_event,
)


class TestContextPressureReaders:
    """ENH-2507: context_pressure_curve / pressure_crossings / pressure_summary."""

    def test_curve_ordering_and_session_filter(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_context_pressure_event(db, session_id="a", used_pct=10.0, used_tokens_est=1000)
        record_context_pressure_event(db, session_id="a", used_pct=20.0, used_tokens_est=2000)
        record_context_pressure_event(db, session_id="b", used_pct=90.0, used_tokens_est=9000)

        rows = context_pressure_curve("a", db=db)
        assert [r.used_pct for r in rows] == [10.0, 20.0]  # oldest first

    def test_curve_missing_db(self, tmp_path: Path) -> None:
        assert context_pressure_curve("a", db=tmp_path / "no" / "history.db") == []

    def test_pressure_crossings_filters_uncrossed_rows(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_context_pressure_event(db, session_id="a", used_pct=10.0, used_tokens_est=1000)
        record_context_pressure_event(
            db,
            session_id="a",
            used_pct=82.0,
            used_tokens_est=8200,
            threshold_crossed=True,
            crossed_level="80",
        )

        rows = pressure_crossings("a", db=db)
        assert len(rows) == 1
        assert rows[0].crossed_level == "80"

    def test_pressure_crossings_since_filter(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_context_pressure_event(
            db,
            session_id="a",
            used_pct=52.0,
            used_tokens_est=5200,
            threshold_crossed=True,
            crossed_level="50",
            ts="2026-07-01T00:00:00Z",
        )
        record_context_pressure_event(
            db,
            session_id="a",
            used_pct=82.0,
            used_tokens_est=8200,
            threshold_crossed=True,
            crossed_level="80",
            ts="2026-07-02T00:00:00Z",
        )
        rows = pressure_crossings("a", since="2026-07-01T12:00:00Z", db=db)
        assert [r.crossed_level for r in rows] == ["80"]

    def test_pressure_crossings_missing_db(self, tmp_path: Path) -> None:
        assert pressure_crossings("a", db=tmp_path / "no" / "history.db") == []

    def test_pressure_summary_peak_and_avg(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_context_pressure_event(db, session_id="a", used_pct=10.0, used_tokens_est=1000)
        record_context_pressure_event(db, session_id="a", used_pct=30.0, used_tokens_est=3000)

        summary = pressure_summary("a", db=db)
        assert summary["samples"] == 2
        assert summary["peak_pct"] == 30.0
        assert summary["avg_pct"] == 20.0

    def test_pressure_summary_no_rows_returns_none(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        assert pressure_summary("nope", db=db) is None

    def test_pressure_summary_missing_db(self, tmp_path: Path) -> None:
        assert pressure_summary("a", db=tmp_path / "no" / "history.db") is None
