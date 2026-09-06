"""Tests for harness.py: ll-harness / eval outcome telemetry (ENH-2775 split from test_history_reader.py)."""

from __future__ import annotations

from pathlib import Path

from little_loops.history_reader import (
    harness_eval_abstention_rate,
    harness_eval_pass_rate,
    recent_harness_events,
)
from little_loops.session_store import (
    record_harness_event,
)


class TestHarnessEventReaders:
    """ENH-2741: recent_harness_events() / harness_eval_pass_rate()."""

    def test_recent_harness_events_recency_ordering(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_harness_event(db, ts="2026-07-01T10:00:00Z", runner="cli", target="foo")
        record_harness_event(db, ts="2026-07-01T11:00:00Z", runner="cli", target="bar")

        rows = recent_harness_events(db=db)
        assert [row.target for row in rows] == ["bar", "foo"]

    def test_recent_harness_events_filters_combined(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_harness_event(db, ts="2026-07-01T10:00:00Z", runner="cli", target="foo")
        record_harness_event(db, ts="2026-07-01T11:00:00Z", runner="mcp", target="foo")
        record_harness_event(db, ts="2026-07-01T12:00:00Z", runner="cli", target="bar")

        assert [row.target for row in recent_harness_events(runner="cli", db=db)] == [
            "bar",
            "foo",
        ]
        assert [row.runner for row in recent_harness_events(target="foo", db=db)] == [
            "mcp",
            "cli",
        ]
        assert recent_harness_events(since="2026-07-01T11:30:00Z", db=db)[0].target == "bar"
        rows = recent_harness_events(runner="cli", target="foo", db=db)
        assert len(rows) == 1
        assert rows[0].target == "foo"

    def test_recent_harness_events_empty_when_no_db(self, tmp_path: Path) -> None:
        db = tmp_path / "nonexistent" / "history.db"
        assert recent_harness_events(db=db) == []

    def test_harness_eval_pass_rate(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for semantic_passed in (True, True, False):
            record_harness_event(
                db,
                ts="2026-07-01T10:00:00Z",
                target="foo",
                semantic_passed=semantic_passed,
            )
        rate = harness_eval_pass_rate("foo", db=db)
        assert rate is not None
        assert abs(rate - (2 / 3)) < 1e-9

    def test_harness_eval_pass_rate_none_when_all_unscored(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_harness_event(db, ts="2026-07-01T10:00:00Z", target="foo", exit_code=0)

        assert harness_eval_pass_rate("foo", db=db) is None

    def test_harness_eval_pass_rate_none_when_no_rows(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        assert harness_eval_pass_rate("foo", db=db) is None

    def test_harness_eval_pass_rate_excludes_abstained_rows(self, tmp_path: Path) -> None:
        """ENH-3185 AC4: an abstained row (semantic_passed=None) does not deflate
        the pass rate the way a coerced failure would."""

        db = tmp_path / "history.db"
        record_harness_event(
            db,
            ts="2026-07-01T10:00:00Z",
            target="foo",
            semantic_verdict="yes",
            semantic_passed=True,
        )
        record_harness_event(
            db,
            ts="2026-07-01T10:01:00Z",
            target="foo",
            semantic_verdict="cannot_judge",
            semantic_passed=None,
        )

        rate = harness_eval_pass_rate("foo", db=db)
        assert rate == 1.0

    def test_harness_eval_abstention_rate(self, tmp_path: Path) -> None:
        """ENH-3185 AC4: abstention is queryable as its own rate, separate from pass rate."""

        db = tmp_path / "history.db"
        for verdict, passed in [
            ("yes", True),
            ("no", False),
            ("cannot_judge", None),
            ("cannot_judge_uncertain", None),
        ]:
            record_harness_event(
                db,
                ts="2026-07-01T10:00:00Z",
                target="foo",
                semantic_verdict=verdict,
                semantic_passed=passed,
            )

        result = harness_eval_abstention_rate("foo", db=db)
        assert result is not None
        assert result["abstentions"] == 2
        assert result["scored"] == 4
        assert abs(result["abstention_rate"] - 0.5) < 1e-9

    def test_harness_eval_abstention_rate_does_not_match_unrelated_verdict(
        self, tmp_path: Path
    ) -> None:
        """The LIKE-based suffix match must not catch an unrelated verdict that
        merely starts with a similar prefix."""

        db = tmp_path / "history.db"
        record_harness_event(
            db, ts="2026-07-01T10:00:00Z", target="foo", semantic_verdict="cannot_judgex"
        )

        result = harness_eval_abstention_rate("foo", db=db)
        assert result is not None
        assert result["abstentions"] == 0

    def test_harness_eval_abstention_rate_none_when_no_rows(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        assert harness_eval_abstention_rate("foo", db=db) is None
