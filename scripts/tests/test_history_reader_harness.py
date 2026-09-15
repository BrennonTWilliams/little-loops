"""Tests for harness.py: ll-harness / eval outcome telemetry (ENH-2775 split from test_history_reader.py)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from little_loops.history_reader import (
    admissions_by_reason,
    authoritative_attempt,
    authoritative_attempts,
    harness_eval_abstention_rate,
    harness_eval_pass_rate,
    harness_event_by_id,
    recent_harness_events,
)
from little_loops.session_store import (
    admit_retry,
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

        # ENH-3408: a superseded timeout row is excluded from both the
        # denominator and the failure count -- only its surviving retry counts.
        cell = json.dumps(["cmd", "foo", "sha1"], separators=(",", ":"))
        original_id = record_attempt(
            db,
            cell_key=cell,
            attempt_kind="repetition",
            ts="2026-07-01T10:02:00Z",
            runner="cmd",
            target="foo",
            timed_out=True,
            semantic_passed=False,
        )
        record_attempt(
            db,
            cell_key=cell,
            attempt_kind="infra_retry",
            retry_of=original_id,
            reason="timeout",
            ts="2026-07-01T10:03:00Z",
            runner="cmd",
            target="foo",
            semantic_passed=True,
        )

        rate = harness_eval_pass_rate("foo", db=db)
        assert rate is not None
        assert abs(rate - (3 / 4)) < 1e-9

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

        # ENH-3408: a superseded timeout row (semantic_passed=False) must not
        # count as a failure -- only its surviving retry is authoritative.
        cell = json.dumps(["cmd", "foo", "sha1"], separators=(",", ":"))
        original_id = record_attempt(
            db,
            cell_key=cell,
            attempt_kind="repetition",
            ts="2026-07-01T10:02:00Z",
            runner="cmd",
            target="foo",
            timed_out=True,
            semantic_passed=False,
        )
        record_attempt(
            db,
            cell_key=cell,
            attempt_kind="infra_retry",
            retry_of=original_id,
            reason="timeout",
            ts="2026-07-01T10:03:00Z",
            runner="cmd",
            target="foo",
            semantic_passed=True,
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

        # ENH-3408: a superseded row's abstained verdict must not enter the
        # denominator or the abstention count -- only its surviving retry
        # (a non-abstained verdict here) is authoritative.
        cell = json.dumps(["cmd", "foo", "sha1"], separators=(",", ":"))
        original_id = record_attempt(
            db,
            cell_key=cell,
            attempt_kind="repetition",
            ts="2026-07-01T10:02:00Z",
            runner="cmd",
            target="foo",
            timed_out=True,
            semantic_verdict="cannot_judge",
            semantic_passed=None,
        )
        record_attempt(
            db,
            cell_key=cell,
            attempt_kind="infra_retry",
            retry_of=original_id,
            reason="timeout",
            ts="2026-07-01T10:03:00Z",
            runner="cmd",
            target="foo",
            semantic_verdict="yes",
            semantic_passed=True,
        )

        result = harness_eval_abstention_rate("foo", db=db)
        assert result is not None
        assert result["abstentions"] == 2  # superseded cannot_judge row excluded
        assert result["scored"] == 5  # 4 prior + 1 surviving retry

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

        # ENH-3408: a superseded row's real abstention must not leak into the
        # count either.
        cell = json.dumps(["cmd", "foo", "sha1"], separators=(",", ":"))
        original_id = record_attempt(
            db,
            cell_key=cell,
            attempt_kind="repetition",
            ts="2026-07-01T10:01:00Z",
            runner="cmd",
            target="foo",
            timed_out=True,
            semantic_verdict="cannot_judge",
            semantic_passed=None,
        )
        record_attempt(
            db,
            cell_key=cell,
            attempt_kind="infra_retry",
            retry_of=original_id,
            reason="timeout",
            ts="2026-07-01T10:02:00Z",
            runner="cmd",
            target="foo",
            semantic_verdict="cannot_judgex",
            semantic_passed=None,
        )

        result = harness_eval_abstention_rate("foo", db=db)
        assert result is not None
        assert result["abstentions"] == 0
        assert result["scored"] == 2

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

    def test_harness_event_carries_v51_efficiency_fields(self, tmp_path: Path) -> None:
        """ENH-3464: efficiency-vector columns round-trip through record_harness_event()."""
        db = tmp_path / "history.db"
        record_harness_event(
            db,
            ts="2026-09-14T00:00:00Z",
            runner="skill",
            target="foo",
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=10,
            cache_creation_tokens=5,
            tool_calls=3,
        )
        row = recent_harness_events(db=db)[0]
        assert row.input_tokens == 100
        assert row.output_tokens == 50
        assert row.cache_read_tokens == 10
        assert row.cache_creation_tokens == 5
        assert row.tool_calls == 3

    def test_harness_event_efficiency_fields_default_none(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_harness_event(db, ts="2026-09-14T00:00:00Z", runner="cmd", target="foo")
        row = recent_harness_events(db=db)[0]
        assert row.input_tokens is None
        assert row.output_tokens is None
        assert row.cache_read_tokens is None
        assert row.cache_creation_tokens is None
        assert row.tool_calls is None


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


class TestAuthoritativeRepetitionCounting:
    """ENH-3408 AC1/AC2: harness_eval_pass_rate() counts authoritative
    repetitions, not raw attempt rows -- a retry chain collapses to n=1."""

    def test_retry_chain_collapses_to_surviving_attempts_verdict(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        cell = json.dumps(["cmd", "foo", "sha1"], separators=(",", ":"))
        first = record_attempt(
            db,
            cell_key=cell,
            attempt_kind="repetition",
            ts="t0",
            runner="cmd",
            target="foo",
            timed_out=True,
            semantic_passed=False,
        )
        second = record_attempt(
            db,
            cell_key=cell,
            attempt_kind="infra_retry",
            retry_of=first,
            reason="timeout",
            ts="t1",
            runner="cmd",
            target="foo",
            timed_out=True,
            semantic_passed=False,
        )
        record_attempt(
            db,
            cell_key=cell,
            attempt_kind="infra_retry",
            retry_of=second,
            reason="timeout",
            ts="t2",
            runner="cmd",
            target="foo",
            semantic_passed=True,
        )

        # n=1 (the last, graded retry) rather than 1/3.
        rate = harness_eval_pass_rate("foo", db=db)
        assert rate == 1.0

    def test_two_clean_repetitions_yield_n_of_two(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        cell = json.dumps(["cmd", "foo", "sha1"], separators=(",", ":"))
        record_attempt(
            db,
            cell_key=cell,
            attempt_kind="repetition",
            ts="t0",
            runner="cmd",
            target="foo",
            semantic_passed=True,
        )
        record_attempt(
            db,
            cell_key=cell,
            attempt_kind="repetition",
            ts="t1",
            runner="cmd",
            target="foo",
            semantic_passed=False,
        )

        rate = harness_eval_pass_rate("foo", db=db)
        assert rate is not None
        assert abs(rate - 0.5) < 1e-9


class TestAdmissionsByReason:
    """ENH-3408: admissions_by_reason() — scoped admission tabulation."""

    def test_empty_ids_returns_empty_dict(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        assert admissions_by_reason(db, []) == {}

    def test_no_matching_admissions_returns_empty_dict(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_harness_event(db, ts="t0", runner="cmd", target="foo")
        assert admissions_by_reason(db, [999]) == {}

    def test_counts_by_reason_across_ids(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        sup1 = record_harness_event(db, ts="t0", runner="cmd", target="foo")
        att1 = record_harness_event(db, ts="t1", runner="cmd", target="foo")
        sup2 = record_harness_event(db, ts="t2", runner="cmd", target="foo")
        att2 = record_harness_event(db, ts="t3", runner="cmd", target="foo")

        admit_retry(db, attempt_id=att1, superseded_id=sup1, reason="timeout")
        admit_retry(db, attempt_id=att2, superseded_id=sup2, reason="network")

        result = admissions_by_reason(db, [att1, att2])
        assert result == {"timeout": 1, "network": 1}


class TestBaselineFor:
    """ENH-3435: baseline_for() — the unmutated-arm reader over harness_events."""

    @staticmethod
    def _seed(
        db: Path,
        *,
        conditions_fp: str,
        content_hash: str = "c0",
        input_hash: str = "",
        head_sha: str = "sha0",
        passed: bool = True,
        ts: str = "2026-09-10T00:00:00Z",
    ) -> int:
        cell = json.dumps(["skill", "my-skill", head_sha], separators=(",", ":"))
        return record_attempt(
            db,
            cell_key=cell,
            attempt_kind="repetition",
            ts=ts,
            runner="skill",
            target="my-skill",
            exit_code=0,
            semantic_verdict="yes" if passed else "no",
            semantic_passed=passed,
            timed_out=False,
            duration_ms=5,
            head_sha=head_sha,
            target_content_hash=content_hash,
            input_hash=input_hash,
            conditions_fp=conditions_fp,
        )

    @staticmethod
    def _conditions(n: int, conditions_fp: str):
        from little_loops.history_reader.harness import BaselineConditions

        return BaselineConditions(
            n=n,
            conditions_fp=conditions_fp,
            semantic_prompt=None,
            semantic_model=None,
            subject_model=None,
            timeout_s=120,
            host_cli="claude-code",
        )

    def test_returns_most_recent_n_matching_rows(self, tmp_path: Path) -> None:
        from little_loops.history_reader.harness import baseline_for

        db = tmp_path / "history.db"
        ids = [
            self._seed(db, conditions_fp="fp0", ts=f"2026-09-10T00:00:{i:02d}Z") for i in range(5)
        ]

        result = baseline_for(
            db,
            runner="skill",
            target="my-skill",
            input_hash="",
            target_content_hash="c0",
            conditions=self._conditions(3, "fp0"),
        )
        assert result is not None
        # Most recent n of the 5 matching rows — not all of them.
        assert result.attempt_ids == ids[2:]
        assert result.tally.requested == 3
        assert result.tally.graded == 3
        assert result.tally.passed == 3
        assert result.head_sha == "sha0"
        assert result.source == "reused"

    def test_ignores_head_sha_and_cell_key(self, tmp_path: Path) -> None:
        """AC4: head_sha is provenance, not a match key — rows at a moved HEAD match."""
        from little_loops.history_reader.harness import baseline_for

        db = tmp_path / "history.db"
        ids = [
            self._seed(db, conditions_fp="fp0", head_sha=f"sha{i}", ts=f"2026-09-10T00:00:{i:02d}Z")
            for i in range(3)
        ]

        result = baseline_for(
            db,
            runner="skill",
            target="my-skill",
            input_hash="",
            target_content_hash="c0",
            conditions=self._conditions(3, "fp0"),
        )
        assert result is not None
        assert result.attempt_ids == ids

    def test_fewer_than_n_rows_returns_none(self, tmp_path: Path) -> None:
        from little_loops.history_reader.harness import baseline_for

        db = tmp_path / "history.db"
        for i in range(2):
            self._seed(db, conditions_fp="fp0", ts=f"2026-09-10T00:00:{i:02d}Z")

        assert (
            baseline_for(
                db,
                runner="skill",
                target="my-skill",
                input_hash="",
                target_content_hash="c0",
                conditions=self._conditions(3, "fp0"),
            )
            is None
        )

    def test_zero_graded_rows_returns_none(self, tmp_path: Path) -> None:
        from little_loops.history_reader.harness import baseline_for

        db = tmp_path / "history.db"
        for i in range(3):
            self._seed(db, conditions_fp="fp0", passed=False, ts=f"2026-09-10T00:00:{i:02d}Z")
        # passed=False rows are graded (fail), so re-seed as abstained instead:
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "UPDATE harness_events SET semantic_passed = NULL, semantic_verdict = 'cannot_judge'"
            )
            conn.commit()
        finally:
            conn.close()

        assert (
            baseline_for(
                db,
                runner="skill",
                target="my-skill",
                input_hash="",
                target_content_hash="c0",
                conditions=self._conditions(3, "fp0"),
            )
            is None
        )

    def test_conditions_fp_mismatch_returns_none(self, tmp_path: Path) -> None:
        from little_loops.history_reader.harness import baseline_for

        db = tmp_path / "history.db"
        for i in range(3):
            self._seed(db, conditions_fp="fp0", ts=f"2026-09-10T00:00:{i:02d}Z")

        assert (
            baseline_for(
                db,
                runner="skill",
                target="my-skill",
                input_hash="",
                target_content_hash="c0",
                conditions=self._conditions(3, "fp-different"),
            )
            is None
        )

    def test_content_or_input_mismatch_returns_none(self, tmp_path: Path) -> None:
        from little_loops.history_reader.harness import baseline_for

        db = tmp_path / "history.db"
        for _ in range(3):
            self._seed(db, conditions_fp="fp0", content_hash="c0", input_hash="i0")

        assert (
            baseline_for(
                db,
                runner="skill",
                target="my-skill",
                input_hash="i0",
                target_content_hash="cX",
                conditions=self._conditions(3, "fp0"),
            )
            is None
        )
        assert (
            baseline_for(
                db,
                runner="skill",
                target="my-skill",
                input_hash="iX",
                target_content_hash="c0",
                conditions=self._conditions(3, "fp0"),
            )
            is None
        )
