"""Tests for harness.py: ll-harness / eval outcome telemetry (ENH-2775 split from test_history_reader.py)."""

from __future__ import annotations

import json
from pathlib import Path

from little_loops.history_reader import (
    authoritative_attempt,
    authoritative_attempts,
    harness_eval_abstention_rate,
    harness_eval_pass_rate,
    harness_event_by_id,
    recent_harness_events,
)
from little_loops.session_store import (
    record_attempt,
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

    def test_harness_event_carries_id_and_v49_fields(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_harness_event(db, ts="2026-08-01T00:00:00Z", runner="cmd", target="foo")
        row = recent_harness_events(db=db)[0]
        assert isinstance(row.id, int)
        assert row.cell_key is None
        assert row.repetition is None
        assert row.attempt_kind is None
        assert row.continuations is None
        assert row.superseded_by is None


class TestHarnessEventById:
    """ENH-3407: harness_event_by_id() — used by the --retry-of gate."""

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        assert harness_event_by_id(db, 999) is None

    def test_returns_the_matching_row(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        new_id = record_harness_event(db, ts="2026-08-01T00:00:00Z", runner="cmd", target="foo")
        row = harness_event_by_id(db, new_id)
        assert row is not None
        assert row.id == new_id
        assert row.target == "foo"


class TestAuthoritativeAttempts:
    """ENH-3407: authoritative_attempt() / authoritative_attempts() — read side of
    the retry-admission model, feeding ENH-3408's n-counting."""

    CELL = json.dumps(["cmd", "echo hi", "sha1"], separators=(",", ":"))

    def test_authoritative_attempt_returns_earliest_non_superseded_row_of_timeout_chain(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "history.db"
        original_id = record_attempt(
            db,
            cell_key=self.CELL,
            attempt_kind="repetition",
            ts="t0",
            runner="cmd",
            target="echo hi",
            timed_out=True,
        )
        retry_id = record_attempt(
            db,
            cell_key=self.CELL,
            attempt_kind="infra_retry",
            retry_of=original_id,
            reason="timeout",
            ts="t1",
            runner="cmd",
            target="echo hi",
        )
        result = authoritative_attempt(db, self.CELL, 0)
        assert result is not None
        assert result.id == retry_id

    def test_authoritative_attempts_returns_one_per_repetition_excluding_superseded(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "history.db"
        rep0_original = record_attempt(
            db,
            cell_key=self.CELL,
            attempt_kind="repetition",
            ts="t0",
            runner="cmd",
            target="echo hi",
            timed_out=True,
        )
        rep0_retry = record_attempt(
            db,
            cell_key=self.CELL,
            attempt_kind="infra_retry",
            retry_of=rep0_original,
            reason="timeout",
            ts="t1",
            runner="cmd",
            target="echo hi",
        )
        rep1 = record_attempt(
            db,
            cell_key=self.CELL,
            attempt_kind="repetition",
            ts="t2",
            runner="cmd",
            target="echo hi",
        )

        attempts = authoritative_attempts(db, self.CELL)
        ids = sorted(a.id for a in attempts)
        assert ids == sorted([rep0_retry, rep1])
        assert rep0_original not in ids

    def test_authoritative_attempt_none_when_no_rows(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        assert authoritative_attempt(db, self.CELL, 0) is None

    def test_authoritative_attempts_empty_when_no_rows(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        assert authoritative_attempts(db, self.CELL) == []
