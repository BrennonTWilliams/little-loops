"""ENH-230 regression walker for the verdict grammar contract.

Walks every reader in the consumer list and asserts each handles the full
verdict vocabulary (pass / fail / cannot_judge / refused) without silent
regressions. Producer-side coverage lives in the writer and schema tests;
this module is the consumer-side safety net — the regression walker QA
asked for in the contract conditions.

Consumer list (per ENH-230 prep):
  * history_reader.recent_verdict_events — surfaces every row, preserves
    NULL findings_count / abstention_reason
  * history_reader.verdict_pass_rate — buckets cannot_judge / refused
    separately and excludes neither from invocations (existing contract)
  * history_reader.check_high_confidence_abstention — flags cannot_judge
    rows whose confidence crosses the manual-review threshold

If a new consumer is added that reads verdict_events, add a walker
test here. The atomic-landing contract requires this file to land in the
same PR as the producer, the writer, and the schema migration.
"""

from __future__ import annotations

from pathlib import Path

import pytest


class TestVerdictGrammarRegression:
    """Walk every consumer of verdict_events; assert NULL/silent-regression safety."""

    def test_recent_verdict_events_surfaces_all_five_verdicts(
        self, tmp_path: Path
    ) -> None:
        from little_loops.history_reader import recent_verdict_events
        from little_loops.session_store import record_verdict_event

        db = tmp_path / "history.db"
        # Every value in the new verdict_events vocabulary, in one fixture.
        record_verdict_event(
            db,
            ts="2026-08-01T10:00:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-1",
            verdict="pass",
            findings_count=2,
            confidence=95,
        )
        record_verdict_event(
            db,
            ts="2026-08-01T10:01:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-2",
            verdict="fail",
            findings_count=4,
            confidence=40,
        )
        record_verdict_event(
            db,
            ts="2026-08-01T10:02:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-3",
            verdict="implement",
            findings_count=0,
            confidence=88,
        )
        record_verdict_event(
            db,
            ts="2026-08-01T10:03:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-4",
            verdict="cannot_judge",
            abstention_reason="missing_artifacts",
        )
        record_verdict_event(
            db,
            ts="2026-08-01T10:04:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-5",
            verdict="refused",
            abstention_reason="principled_refusal",
        )

        rows = recent_verdict_events(db=db)
        assert len(rows) == 5
        verdicts = {r.verdict for r in rows}
        assert verdicts == {"pass", "fail", "implement", "cannot_judge", "refused"}
        # NULL contract: cannot_judge and refused rows carry None, not 0.
        for row in rows:
            if row.verdict in ("cannot_judge", "refused"):
                assert row.findings_count is None
                assert row.confidence is None
            else:
                assert row.findings_count is not None

    def test_verdict_pass_rate_excludes_neither_nor_coalesces_null(
        self, tmp_path: Path
    ) -> None:
        from little_loops.history_reader import verdict_pass_rate
        from little_loops.session_store import record_verdict_event

        db = tmp_path / "history.db"
        # 1 pass + 1 fail + 2 cannot_judge + 1 refused = 5 invocations
        # successes = 1, cannot_judge_count = 2, refused_count = 1
        record_verdict_event(
            db,
            ts="2026-08-01T10:00:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-1",
            verdict="pass",
        )
        record_verdict_event(
            db,
            ts="2026-08-01T10:01:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-2",
            verdict="fail",
        )
        record_verdict_event(
            db,
            ts="2026-08-01T10:02:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-3",
            verdict="cannot_judge",
            abstention_reason="unparseable_criteria",
        )
        record_verdict_event(
            db,
            ts="2026-08-01T10:03:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-4",
            verdict="cannot_judge",
            abstention_reason="circular_dependencies",
        )
        record_verdict_event(
            db,
            ts="2026-08-01T10:04:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-5",
            verdict="refused",
            abstention_reason="principled_refusal",
        )

        rates = verdict_pass_rate(db=db)
        assert len(rates) == 1
        row = rates[0]
        assert row["invocations"] == 5
        assert row["successes"] == 1
        assert row["cannot_judge_count"] == 2
        assert row["refused_count"] == 1
        # success_rate denominator is invocations per existing contract;
        # a decision-rate variant is a follow-up if requested.
        assert row["success_rate"] == 0.2

    def test_high_confidence_abstention_walker(self, tmp_path: Path) -> None:
        """Walker covers the high-confidence sanity check across both abstention types."""
        from little_loops.history_reader import check_high_confidence_abstention
        from little_loops.session_store import record_verdict_event

        db = tmp_path / "history.db"
        # High-confidence cannot_judge — flagged.
        record_verdict_event(
            db,
            ts="2026-08-01T10:00:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-A",
            verdict="cannot_judge",
            abstention_reason="missing_artifacts",
            confidence=95,
        )
        # Low-confidence cannot_judge — NOT flagged.
        record_verdict_event(
            db,
            ts="2026-08-01T10:01:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-B",
            verdict="cannot_judge",
            abstention_reason="missing_artifacts",
            confidence=40,
        )
        # High-confidence refused — not a cannot_judge row, NOT flagged by this check.
        record_verdict_event(
            db,
            ts="2026-08-01T10:02:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-C",
            verdict="refused",
            abstention_reason="principled_refusal",
            confidence=95,
        )

        warnings = check_high_confidence_abstention(db=db, threshold=90)
        assert len(warnings) == 1
        assert warnings[0].target_id == "BUG-A"
        assert warnings[0].confidence == 95

    def test_no_consumer_coalesces_null_to_zero(self, tmp_path: Path) -> None:
        """NULL findings_count on abstention rows MUST stay None end-to-end.

        Walks every reader. Catches any `or 0` coalesce that an LLM
        gaming path could exploit by emitting cannot_judge +
        findings_count=0 to look like a normal fail.
        """
        from little_loops.history_reader import (
            recent_verdict_events,
            verdict_pass_rate,
        )
        from little_loops.session_store import record_verdict_event

        db = tmp_path / "history.db"
        record_verdict_event(
            db,
            ts="2026-08-01T10:00:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-NULL",
            verdict="cannot_judge",
            abstention_reason="missing_artifacts",
        )
        record_verdict_event(
            db,
            ts="2026-08-01T10:01:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-REFUSED",
            verdict="refused",
            abstention_reason="principled_refusal",
        )

        rows = recent_verdict_events(db=db)
        for row in rows:
            if row.verdict in ("cannot_judge", "refused"):
                assert row.findings_count is None
                assert row.confidence is None

        rates = verdict_pass_rate(db=db)
        assert rates[0]["cannot_judge_count"] == 1
        assert rates[0]["refused_count"] == 1
        # Neither abstention bucket contributes to successes.
        assert rates[0]["successes"] == 0

    @pytest.mark.parametrize(
        "verdict,abstention_reason",
        [
            ("pass", None),
            ("fail", None),
            ("implement", None),
            ("cannot_judge", "missing_artifacts"),
            ("cannot_judge", "unparseable_criteria"),
            ("cannot_judge", "evaluation_context_unavailable"),
            ("cannot_judge", "circular_dependencies"),
            ("refused", "principled_refusal"),
        ],
    )
    def test_full_vocabulary_round_trips(
        self,
        tmp_path: Path,
        verdict: str,
        abstention_reason: str | None,
    ) -> None:
        """Every verdict+abstention_reason pair round-trips through writer/reader.

        Parametrized over the full vocabulary so a regression in any single
        combination fails one test method with a clear name.
        """
        from little_loops.history_reader import recent_verdict_events
        from little_loops.session_store import record_verdict_event

        db = tmp_path / "history.db"
        record_verdict_event(
            db,
            ts="2026-08-01T10:00:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id=f"BUG-{verdict}-{abstention_reason or 'none'}",
            verdict=verdict,
            abstention_reason=abstention_reason,
        )

        rows = recent_verdict_events(db=db)
        assert len(rows) == 1
        assert rows[0].verdict == verdict
        assert rows[0].abstention_reason == abstention_reason
