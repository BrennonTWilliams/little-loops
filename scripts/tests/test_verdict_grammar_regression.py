"""ENH-230 regression walker for the verdict grammar contract.

Walks every reader of ``verdict_events`` and asserts each handles the
verdict vocabulary (pass / fail / implement / cannot_judge) without silent
regressions. Producer-side coverage lives in the writer and schema tests;
this module is the consumer-side safety net.

Consumer list:
  * ``history_reader.recent_verdict_events`` — surfaces every row and
    preserves NULL ``findings_count`` / ``abstention_reason``
  * ``history_reader.verdict_pass_rate`` — buckets ``cannot_judge``
    separately without dropping it from ``invocations``
  * ``history_reader.check_high_confidence_abstention`` — flags
    ``cannot_judge`` rows whose confidence crosses the review threshold

If a new consumer of ``verdict_events`` is added, add a walker test here.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _write(db: Path, **kwargs: object) -> None:
    """Record one verdict_events row with test-friendly defaults."""
    from little_loops.session_store import record_verdict_event

    params: dict = {
        "ts": "2026-08-01T10:00:00Z",
        "session_id": None,
        "verdict_kind": "ready-issue",
    }
    params.update(kwargs)
    record_verdict_event(db, **params)  # type: ignore[arg-type]


class TestVerdictGrammarRegression:
    """Walk every consumer of verdict_events; assert NULL/silent-regression safety."""

    def test_recent_verdict_events_surfaces_every_verdict(self, tmp_path: Path) -> None:
        from little_loops.history_reader import recent_verdict_events

        db = tmp_path / "history.db"
        # Every value in the verdict_events vocabulary, in one fixture.
        _write(
            db,
            ts="2026-08-01T10:00:00Z",
            target_id="BUG-1",
            verdict="pass",
            findings_count=2,
            confidence=95,
        )
        _write(
            db,
            ts="2026-08-01T10:01:00Z",
            target_id="BUG-2",
            verdict="fail",
            findings_count=4,
            confidence=40,
        )
        _write(
            db,
            ts="2026-08-01T10:02:00Z",
            target_id="BUG-3",
            verdict="implement",
            findings_count=0,
            confidence=88,
        )
        _write(
            db,
            ts="2026-08-01T10:03:00Z",
            target_id="BUG-4",
            verdict="cannot_judge",
            abstention_reason="missing_artifacts",
        )

        rows = recent_verdict_events(db=db)
        assert len(rows) == 4
        assert {r.verdict for r in rows} == {"pass", "fail", "implement", "cannot_judge"}
        # NULL contract: the abstention row carries None, not 0.
        for row in rows:
            if row.verdict == "cannot_judge":
                assert row.findings_count is None
                assert row.confidence is None
                assert row.abstention_reason == "missing_artifacts"
            else:
                assert row.findings_count is not None
                assert row.abstention_reason is None

    def test_verdict_pass_rate_buckets_abstentions_without_dropping_them(
        self, tmp_path: Path
    ) -> None:
        from little_loops.history_reader import verdict_pass_rate

        db = tmp_path / "history.db"
        # 1 pass + 1 fail + 2 cannot_judge = 4 invocations, 1 success.
        _write(db, ts="2026-08-01T10:00:00Z", target_id="BUG-1", verdict="pass")
        _write(db, ts="2026-08-01T10:01:00Z", target_id="BUG-2", verdict="fail")
        _write(
            db,
            ts="2026-08-01T10:02:00Z",
            target_id="BUG-3",
            verdict="cannot_judge",
            abstention_reason="unparseable_criteria",
        )
        _write(
            db,
            ts="2026-08-01T10:03:00Z",
            target_id="BUG-4",
            verdict="cannot_judge",
            abstention_reason="circular_dependencies",
        )

        rates = verdict_pass_rate(db=db)
        assert len(rates) == 1
        row = rates[0]
        assert row["invocations"] == 4
        assert row["successes"] == 1
        assert row["cannot_judge_count"] == 2
        # success_rate keeps its existing denominator (invocations); a
        # decision-rate variant that excludes abstentions is a follow-up.
        assert row["success_rate"] == 0.25

    def test_high_confidence_abstention_flags_only_confident_cannot_judge(
        self, tmp_path: Path
    ) -> None:
        from little_loops.history_reader import check_high_confidence_abstention

        db = tmp_path / "history.db"
        # High-confidence cannot_judge — flagged.
        _write(
            db,
            ts="2026-08-01T10:00:00Z",
            target_id="BUG-A",
            verdict="cannot_judge",
            abstention_reason="missing_artifacts",
            confidence=95,
        )
        # Low-confidence cannot_judge — not flagged.
        _write(
            db,
            ts="2026-08-01T10:01:00Z",
            target_id="BUG-B",
            verdict="cannot_judge",
            abstention_reason="missing_artifacts",
            confidence=40,
        )
        # High-confidence non-abstention — not flagged.
        _write(db, ts="2026-08-01T10:02:00Z", target_id="BUG-C", verdict="fail", confidence=95)

        flagged = check_high_confidence_abstention(db=db, threshold=90)
        assert len(flagged) == 1
        assert flagged[0].target_id == "BUG-A"
        assert flagged[0].confidence == 95

    def test_high_confidence_abstention_warns(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The sanity check is loud — a confident abstention emits a warning."""
        from little_loops.history_reader import check_high_confidence_abstention

        db = tmp_path / "history.db"
        _write(
            db,
            target_id="BUG-LOUD",
            verdict="cannot_judge",
            abstention_reason="missing_artifacts",
            confidence=99,
        )

        with caplog.at_level("WARNING", logger="little_loops.history_reader"):
            check_high_confidence_abstention(db=db, threshold=90)
        assert any("high-confidence abstention" in r.message for r in caplog.records)
        assert any("BUG-LOUD" in str(r.args) for r in caplog.records)

    def test_no_consumer_coalesces_null_to_zero(self, tmp_path: Path) -> None:
        """NULL findings_count on an abstention row MUST stay None end-to-end.

        Catches any ``or 0`` coalesce that would let a producer emit
        ``cannot_judge`` + ``findings_count=0`` and have it read back as a
        completed audit that found nothing.
        """
        from little_loops.history_reader import recent_verdict_events, verdict_pass_rate

        db = tmp_path / "history.db"
        _write(
            db, target_id="BUG-NULL", verdict="cannot_judge", abstention_reason="missing_artifacts"
        )

        rows = recent_verdict_events(db=db)
        assert rows[0].findings_count is None
        assert rows[0].confidence is None

        rates = verdict_pass_rate(db=db)
        assert rates[0]["cannot_judge_count"] == 1
        # The abstention does not contribute to successes.
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
        ],
    )
    def test_full_vocabulary_round_trips(
        self, tmp_path: Path, verdict: str, abstention_reason: str | None
    ) -> None:
        """Every legal verdict + abstention_reason pair round-trips writer -> reader."""
        from little_loops.history_reader import recent_verdict_events

        db = tmp_path / "history.db"
        _write(
            db,
            target_id=f"BUG-{verdict}-{abstention_reason or 'none'}",
            verdict=verdict,
            abstention_reason=abstention_reason,
        )

        rows = recent_verdict_events(db=db)
        assert len(rows) == 1
        assert rows[0].verdict == verdict
        assert rows[0].abstention_reason == abstention_reason
