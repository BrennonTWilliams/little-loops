"""Tests for issue_history.rework — the FEAT-2867 rework-rate signals.

Covers: injected rework (degrading), injected improvement, a flat history,
a below-min-sample history, a low-attribution-coverage window, supersession
as reopen, revert-lineage detection, orchestrator labeling/unattributed
fallback, and the quality-adjustment formula itself.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.issue_history.rework import (
    MIN_SAMPLE_SIZE,
    UNATTRIBUTED_LABEL,
    ReworkAnalysis,
    analyze_rework,
    format_rework_json,
    format_rework_markdown,
    format_rework_text,
    format_rework_yaml,
    quality_adjusted_throughput,
)
from little_loops.issue_parser import IssueInfo
from little_loops.session_store import record_commit_event, record_issue_event
from little_loops.session_store.writers import record_orchestration_run


def _issue(issue_id: str, *, supersedes: list[str] | None = None) -> IssueInfo:
    return IssueInfo(
        path=Path(f"{issue_id}.md"),
        issue_type="bugs",
        priority="P2",
        issue_id=issue_id,
        title=issue_id,
        supersedes=supersedes or [],
    )


def _close(db: Path, issue_id: str, ts: str) -> None:
    record_issue_event(db, issue_id, "done", completed_at=ts)
    # record_issue_event's dedup key is (issue_num, transition); ts is
    # stamped by the writer itself at call time, not from completed_at, so
    # patch it in directly for deterministic period bucketing in tests.
    _stamp_ts(db, issue_id, "done", ts)


def _stamp_ts(db: Path, issue_id: str, transition: str, ts: str) -> None:
    import sqlite3

    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "UPDATE issue_events SET ts = ? WHERE issue_id = ? AND transition = ?",
            (ts, issue_id, transition),
        )
        conn.commit()
    finally:
        conn.close()


def _reopen(db: Path, issue_id: str, ts: str, transition: str = "open") -> None:
    record_issue_event(db, issue_id, transition)
    _stamp_ts(db, issue_id, transition, ts)


class TestQualityAdjustedThroughput:
    def test_pinned_formula(self) -> None:
        assert quality_adjusted_throughput(10, 0.3) == 7.0

    def test_zero_rework_share_equals_raw_count(self) -> None:
        assert quality_adjusted_throughput(8, 0.0) == 8.0


class TestEmptyAndMissingDb:
    def test_missing_db_returns_empty_analysis(self, tmp_path: Path) -> None:
        analysis = analyze_rework([], db=tmp_path / "nonexistent" / "history.db")
        assert isinstance(analysis, ReworkAnalysis)
        assert analysis.windows == []

    def test_empty_db_returns_empty_windows(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        # Force schema creation with an unrelated write, no issue_events rows.
        from little_loops.session_store import ensure_db

        ensure_db(db)
        analysis = analyze_rework([], db=db)
        assert analysis.windows == []


class TestBelowMinimumSample:
    def test_window_below_threshold_reports_insufficient_history(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(MIN_SAMPLE_SIZE - 1):
            _close(db, f"BUG-{100 + i}", "2026-03-01T00:00:00Z")

        analysis = analyze_rework([], db=db)
        assert len(analysis.windows) == 1
        w = analysis.windows[0]
        assert w.insufficient_history is True
        assert w.reopen.rate is None
        assert w.reopen.verdict == "insufficient history"
        assert w.quality_adjusted is None


class TestFlatHistory:
    def test_no_rework_events_yields_zero_rates_and_full_throughput(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(MIN_SAMPLE_SIZE):
            _close(db, f"BUG-{200 + i}", "2026-04-01T00:00:00Z")

        analysis = analyze_rework([], db=db)
        assert len(analysis.windows) == 1
        w = analysis.windows[0]
        assert w.insufficient_history is False
        assert w.reopen.rate == 0.0
        assert w.revert.rate == 0.0
        assert w.rework_share == 0.0
        assert w.quality_adjusted == float(MIN_SAMPLE_SIZE)
        # Sole window for its orchestrator group: no earlier baseline to compare against.
        assert w.reopen.verdict == "stable"


class TestInjectedRework:
    def test_reopened_issues_degrade_the_window_vs_baseline(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        # Baseline period: nothing reopens.
        for i in range(MIN_SAMPLE_SIZE):
            _close(db, f"BUG-{300 + i}", "2026-01-01T00:00:00Z")
        # Later period: most issues reopen.
        for i in range(MIN_SAMPLE_SIZE):
            issue_id = f"BUG-{400 + i}"
            _close(db, issue_id, "2026-02-01T00:00:00Z")
            if i < 4:
                _reopen(db, issue_id, "2026-02-05T00:00:00Z")

        analysis = analyze_rework([], db=db)
        assert len(analysis.windows) == 2
        baseline, later = analysis.windows
        assert baseline.period == "2026-01"
        assert later.period == "2026-02"
        assert baseline.reopen.rate == 0.0
        assert later.reopen.rate == 4 / MIN_SAMPLE_SIZE
        assert later.reopen.verdict == "degrading"
        assert later.reopen.baseline_period == "2026-01"
        assert later.rework_share == later.reopen.rate
        assert later.quality_adjusted == quality_adjusted_throughput(
            MIN_SAMPLE_SIZE, later.rework_share
        )

    def test_supersession_counts_as_reopen(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(MIN_SAMPLE_SIZE):
            issue_id = f"BUG-{500 + i}"
            _close(db, issue_id, "2026-05-01T00:00:00Z")
            if i == 0:
                _reopen(db, issue_id, "2026-05-10T00:00:00Z", transition="cancelled")

        issues = [_issue("BUG-500", supersedes=[]), _issue("BUG-999", supersedes=["BUG-500"])]

        analysis = analyze_rework(issues, db=db)
        w = analysis.windows[0]
        assert w.reopen.rate == 1 / MIN_SAMPLE_SIZE

    def test_plain_cancellation_without_supersession_is_not_reopen(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(MIN_SAMPLE_SIZE):
            issue_id = f"BUG-{600 + i}"
            _close(db, issue_id, "2026-06-01T00:00:00Z")
            if i == 0:
                _reopen(db, issue_id, "2026-06-10T00:00:00Z", transition="cancelled")

        # No supersedes edge pointing at BUG-600 this time.
        analysis = analyze_rework([_issue("BUG-600")], db=db)
        w = analysis.windows[0]
        assert w.reopen.rate == 0.0

    def test_deferred_after_done_is_not_reopen(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(MIN_SAMPLE_SIZE):
            issue_id = f"BUG-{700 + i}"
            _close(db, issue_id, "2026-07-01T00:00:00Z")
            if i == 0:
                _reopen(db, issue_id, "2026-07-10T00:00:00Z", transition="deferred")

        analysis = analyze_rework([], db=db)
        w = analysis.windows[0]
        assert w.reopen.rate == 0.0

    def test_revert_lineage_detected_via_commit_message(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(MIN_SAMPLE_SIZE):
            issue_id = f"BUG-{800 + i}"
            _close(db, issue_id, "2026-08-01T00:00:00Z")
            record_commit_event(
                db,
                f"{800 + i}abcdef0000000000000000000000000000000",
                f"fix {issue_id}",
                issue_id=issue_id,
                ts="2026-08-01T01:00:00Z",
            )
        record_commit_event(
            db,
            "eeeeeeee0000000000000000000000000000000",
            "Revert 'fix BUG-800'\n\n"
            "This reverts commit 800abcdef0000000000000000000000000000000.",
            issue_id="BUG-800",
            ts="2026-08-02T00:00:00Z",
        )

        analysis = analyze_rework([], db=db)
        w = analysis.windows[0]
        assert w.revert.rate == 1 / MIN_SAMPLE_SIZE
        assert w.rework_share >= w.revert.rate


class TestInjectedImprovement:
    def test_later_window_improves_over_baseline(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        # Baseline: heavy reopen rate.
        for i in range(MIN_SAMPLE_SIZE):
            issue_id = f"BUG-{900 + i}"
            _close(db, issue_id, "2026-01-01T00:00:00Z")
            if i < 4:
                _reopen(db, issue_id, "2026-01-05T00:00:00Z")
        # Later: no reopens at all.
        for i in range(MIN_SAMPLE_SIZE):
            _close(db, f"BUG-{950 + i}", "2026-02-01T00:00:00Z")

        analysis = analyze_rework([], db=db)
        baseline, later = analysis.windows
        assert baseline.reopen.rate == 4 / MIN_SAMPLE_SIZE
        assert later.reopen.rate == 0.0
        assert later.reopen.verdict == "improving"


class TestLowAttributionCoverage:
    def test_unattributed_commits_lower_coverage_and_flag_window(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(MIN_SAMPLE_SIZE):
            _close(db, f"BUG-{1000 + i}", "2026-09-01T00:00:00Z")
        # Plenty of unattributed commits in the same month to push coverage below 50%.
        for i in range(20):
            record_commit_event(
                db,
                f"unattrib{i}",
                "misc cleanup",
                issue_id=None,
                ts="2026-09-15T00:00:00Z",
            )

        analysis = analyze_rework([], db=db)
        w = analysis.windows[0]
        assert w.commit_attribution_coverage is not None
        assert w.commit_attribution_coverage < 0.5
        assert w.low_attribution_coverage is True


class TestOrchestratorLabeling:
    def test_driver_label_used_when_orchestration_run_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(MIN_SAMPLE_SIZE):
            issue_id = f"BUG-{1100 + i}"
            _close(db, issue_id, "2026-10-01T00:00:00Z")
            record_orchestration_run(
                db,
                run_id="run-1",
                driver="ll-auto",
                issue_id=issue_id,
                status="completed",
                started_at="2026-10-01T00:00:00Z",
            )

        analysis = analyze_rework([], db=db)
        assert len(analysis.windows) == 1
        assert analysis.windows[0].orchestrator == "ll-auto"

    def test_unattributed_bucket_when_no_orchestration_run(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(MIN_SAMPLE_SIZE):
            _close(db, f"BUG-{1200 + i}", "2026-11-01T00:00:00Z")

        analysis = analyze_rework([], db=db)
        assert analysis.windows[0].orchestrator == UNATTRIBUTED_LABEL


class TestFormatting:
    def test_json_round_trips_window_fields(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(MIN_SAMPLE_SIZE):
            _close(db, f"BUG-{1300 + i}", "2026-12-01T00:00:00Z")
        analysis = analyze_rework([], db=db)

        import json

        payload = json.loads(format_rework_json(analysis))
        assert payload["min_sample_size"] == MIN_SAMPLE_SIZE
        assert payload["windows"][0]["period"] == "2026-12"
        assert "notes" in payload
        assert any("correlational" in n for n in payload["notes"])

    def test_text_and_markdown_render_without_error_on_empty(self) -> None:
        empty = ReworkAnalysis()
        assert "No closed-issue history found" in format_rework_text(empty)
        assert "No closed-issue history found" in format_rework_markdown(empty)

    def test_yaml_falls_back_gracefully(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(MIN_SAMPLE_SIZE):
            _close(db, f"BUG-{1400 + i}", "2026-01-01T00:00:00Z")
        analysis = analyze_rework([], db=db)
        out = format_rework_yaml(analysis)
        assert "windows" in out
