"""Tests for issue_history.agent_quality — the FEAT-3183 agent-quality signals.

Covers: empty/missing DB, below-min-sample windows, fix-rate trend (derived
from rework_share), correction rate (with retirement filtering and
multi-issue-session split), cost/tokens per issue (with the coverage gate),
retry inflation, the unattributed-dominant rendering path, and `--min-sample
0` honored rather than replaced.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from little_loops.issue_history.agent_quality import (
    QualityAnalysis,
    analyze_agent_quality,
    format_agent_quality_json,
    format_agent_quality_markdown,
    format_agent_quality_text,
    format_agent_quality_yaml,
)
from little_loops.issue_parser import IssueInfo
from little_loops.session_store import record_issue_event
from little_loops.session_store.writers import (
    record_correction,
    record_loop_run_summary,
    record_orchestration_run,
)


def _issue(issue_id: str) -> IssueInfo:
    return IssueInfo(
        path=Path(f"{issue_id}.md"),
        issue_type="bugs",
        priority="P2",
        issue_id=issue_id,
        title=issue_id,
        supersedes=[],
    )


def _stamp_ts(db: Path, issue_id: str, transition: str, ts: str) -> None:
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "UPDATE issue_events SET ts = ? WHERE issue_id = ? AND transition = ?",
            (ts, issue_id, transition),
        )
        conn.commit()
    finally:
        conn.close()


def _close(db: Path, issue_id: str, ts: str, *, session_id: str | None = None) -> None:
    record_issue_event(db, issue_id, "done", session_id=session_id, completed_at=ts)
    _stamp_ts(db, issue_id, "done", ts)


def _link_session(db: Path, issue_id: str, session_id: str) -> None:
    """Give an issue a session_id via a second transition -- issue_sessions dedups on it."""
    record_issue_event(db, issue_id, "in_progress", session_id=session_id)


def _reopen(db: Path, issue_id: str, ts: str) -> None:
    record_issue_event(db, issue_id, "open")
    _stamp_ts(db, issue_id, "open", ts)


def _usage_event(
    db: Path,
    session_id: str,
    *,
    ts: str = "2026-07-15T00:00:00Z",
    model: str = "claude-sonnet-5",
    input_tokens: int = 1000,
    output_tokens: int = 500,
    cost_usd: float | None = 1.0,
) -> None:
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO usage_events(ts, session_id, model, input_tokens, output_tokens, "
            "cache_read_input_tokens, cache_creation_input_tokens, cost_usd) "
            "VALUES(?, ?, ?, ?, ?, 0, 0, ?)",
            (ts, session_id, model, input_tokens, output_tokens, cost_usd),
        )
        conn.commit()
    finally:
        conn.close()


def _retire(db: Path, fingerprint: str) -> None:
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO correction_retirements(topic_fingerprint, addressed_at) VALUES(?, ?)",
            (fingerprint, "2026-01-01T00:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()


class TestEmptyAndMissingDb:
    def test_missing_db_returns_empty_analysis(self, tmp_path: Path) -> None:
        analysis = analyze_agent_quality([], db=tmp_path / "nonexistent" / "history.db")
        assert isinstance(analysis, QualityAnalysis)
        assert analysis.windows == []
        assert analysis.retry_windows == []
        assert len(analysis.definitions) == 4

    def test_empty_db_returns_empty_windows(self, tmp_path: Path) -> None:
        from little_loops.session_store import ensure_db

        db = tmp_path / "history.db"
        ensure_db(db)
        analysis = analyze_agent_quality([], db=db)
        assert analysis.windows == []


class TestBelowMinimumSample:
    def test_window_below_threshold_marks_every_metric_insufficient(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(4):
            _close(db, f"BUG-{100 + i}", "2026-03-01T00:00:00Z")

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        assert len(analysis.windows) == 1
        w = analysis.windows[0]
        for metric in w.metrics.values():
            assert metric.insufficient_history is True
            assert metric.value is None
            assert metric.verdict is None


class TestFixRate:
    def test_flat_history_yields_full_fix_rate(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(5):
            _close(db, f"BUG-{200 + i}", "2026-04-01T00:00:00Z")

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        w = analysis.windows[0]
        fix_rate = w.metrics["fix_rate"]
        assert fix_rate.value == 1.0
        assert fix_rate.verdict == "stable"

    def test_reopened_issues_degrade_fix_rate_vs_baseline(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(5):
            _close(db, f"BUG-{300 + i}", "2026-01-01T00:00:00Z")
        for i in range(5):
            issue_id = f"BUG-{400 + i}"
            _close(db, issue_id, "2026-02-01T00:00:00Z")
            if i < 4:
                _reopen(db, issue_id, "2026-02-05T00:00:00Z")

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        baseline, later = analysis.windows
        assert baseline.metrics["fix_rate"].value == 1.0
        assert later.metrics["fix_rate"].value == 1 - (4 / 5)
        assert later.metrics["fix_rate"].verdict == "degrading"
        assert later.metrics["fix_rate"].baseline_period == "2026-01"


class TestCorrectionRate:
    def test_corrections_attributed_via_session_join(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(5):
            issue_id = f"BUG-{500 + i}"
            _close(db, issue_id, "2026-05-01T00:00:00Z", session_id=f"s{i}")

        record_correction(db, "s0", "please redo this", "user")
        record_correction(db, "s1", "please redo this", "user")

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        w = analysis.windows[0]
        assert w.metrics["correction_rate"].value == 2 / 5

    def test_retired_corrections_excluded_from_numerator(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(5):
            issue_id = f"BUG-{600 + i}"
            _close(db, issue_id, "2026-06-01T00:00:00Z", session_id=f"t{i}")

        content = "please redo this"
        record_correction(db, "t0", content, "user")
        from little_loops.issue_history.agent_quality import _fingerprint

        _retire(db, _fingerprint(content))

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        w = analysis.windows[0]
        assert w.metrics["correction_rate"].value == 0.0

    def test_multi_issue_session_correction_split_evenly(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(5):
            issue_id = f"BUG-{700 + i}"
            _close(db, issue_id, "2026-07-01T00:00:00Z")
        # Two issues share the same session.
        _link_session(db, "BUG-700", "shared")
        _link_session(db, "BUG-701", "shared")
        record_correction(db, "shared", "shared session correction", "user")

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        w = analysis.windows[0]
        # 0.5 attributed to each of two issues in the same window -> 1.0 total / 5 closed.
        assert w.metrics["correction_rate"].value == 1.0 / 5


class TestCostAndTokensPerIssue:
    def test_cost_and_tokens_split_evenly_across_multi_issue_session(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(5):
            issue_id = f"BUG-{800 + i}"
            _close(db, issue_id, "2026-08-01T00:00:00Z")
        _link_session(db, "BUG-800", "shared-usage")
        _link_session(db, "BUG-801", "shared-usage")
        _usage_event(db, "shared-usage", input_tokens=1000, output_tokens=1000, cost_usd=2.0)

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        w = analysis.windows[0]
        # $2.0 split across 2 issues = $1.0 each; total $2.0 / 5 closed issues.
        assert w.metrics["cost_per_issue"].value == 2.0 / 5
        # 2000 tokens split across 2 issues = 1000 each; total 2000 / 5 closed issues.
        assert w.metrics["tokens_per_issue"].value == 2000 / 5

    def test_fully_priced_window_reports_full_coverage(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(5):
            issue_id = f"BUG-{900 + i}"
            _close(db, issue_id, "2026-09-01T00:00:00Z", session_id=f"p{i}")
            _usage_event(db, f"p{i}", cost_usd=1.0)

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        w = analysis.windows[0]
        assert w.metrics["cost_per_issue"].coverage == 1.0
        assert w.metrics["cost_per_issue"].verdict == "stable"


class TestCostCoverageGate:
    def test_majority_null_cost_suppresses_verdict_but_not_tokens(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(5):
            issue_id = f"BUG-{1000 + i}"
            _close(db, issue_id, "2026-10-01T00:00:00Z", session_id=f"u{i}")
            # 4 of 5 sessions get an unpriced (null cost_usd) usage row; 1 is priced.
            cost = 1.0 if i == 0 else None
            _usage_event(db, f"u{i}", cost_usd=cost)

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        w = analysis.windows[0]
        cost_metric = w.metrics["cost_per_issue"]
        assert cost_metric.coverage is not None
        assert cost_metric.coverage < 0.5
        assert cost_metric.verdict is None
        # The number itself still renders -- only the verdict is withheld.
        assert cost_metric.value is not None

        tokens_metric = w.metrics["tokens_per_issue"]
        assert tokens_metric.coverage is None
        assert tokens_metric.verdict is not None


class TestRetryInflation:
    def test_retry_windows_computed_independently_of_orchestrator_axis(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "history.db"
        for i in range(5):
            record_loop_run_summary(
                db,
                run_id=f"baseline-{i}",
                loop_name="rn-refine",
                started_at="2026-01-01T00:00:00Z",
                ended_at="2026-01-01T01:00:00Z",
                final_state="done",
                iterations=1,
            )
        for i in range(5):
            record_loop_run_summary(
                db,
                run_id=f"later-{i}",
                loop_name="rn-refine",
                started_at="2026-02-01T00:00:00Z",
                ended_at="2026-02-01T01:00:00Z",
                final_state="done",
                iterations=3,
            )

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        assert len(analysis.retry_windows) == 2
        baseline, later = analysis.retry_windows
        assert baseline.mean_iterations == 1.0
        assert later.mean_iterations == 3.0
        assert later.verdict == "degrading"

    def test_sparse_loop_window_reports_insufficient_history(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_loop_run_summary(
            db,
            run_id="only-run",
            loop_name="code-run-gate",
            started_at="2026-03-01T00:00:00Z",
            ended_at="2026-03-01T01:00:00Z",
            final_state="done",
            iterations=2,
        )
        analysis = analyze_agent_quality([], db=db, min_sample=5)
        assert len(analysis.retry_windows) == 1
        assert analysis.retry_windows[0].insufficient_history is True
        assert analysis.retry_windows[0].mean_iterations is None


class TestUnattributedDominant:
    def test_text_renderer_legible_when_unattributed_dominates(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        # 4 issues with no orchestration_runs row (unattributed), 1 attributed.
        for i in range(4):
            _close(db, f"BUG-{1100 + i}", "2026-11-01T00:00:00Z")
        record_orchestration_run(
            db,
            run_id="run-x",
            driver="ll-auto",
            issue_id="BUG-1104",
            status="completed",
            started_at="2026-11-01T00:00:00Z",
        )
        _close(db, "BUG-1104", "2026-11-01T00:00:00Z")

        analysis = analyze_agent_quality([], db=db, min_sample=4)
        text = format_agent_quality_text(analysis)
        assert "unattributed" in text
        unattributed_windows = [w for w in analysis.windows if w.orchestrator == "unattributed"]
        assert len(unattributed_windows) == 1
        assert unattributed_windows[0].closed_count == 4


class TestMinSampleZero:
    def test_min_sample_zero_is_honored(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        _close(db, "BUG-1200", "2026-12-01T00:00:00Z")

        analysis = analyze_agent_quality([], db=db, min_sample=0)
        assert len(analysis.windows) == 1
        w = analysis.windows[0]
        assert w.metrics["fix_rate"].insufficient_history is False
        assert w.metrics["fix_rate"].value == 1.0


class TestFormatting:
    def test_json_round_trips_window_fields(self, tmp_path: Path) -> None:
        import json

        db = tmp_path / "history.db"
        for i in range(5):
            _close(db, f"BUG-{1300 + i}", "2026-01-01T00:00:00Z")
        analysis = analyze_agent_quality([], db=db, min_sample=5)

        payload = json.loads(format_agent_quality_json(analysis))
        assert payload["min_sample_size"] == 5
        assert payload["windows"][0]["period"] == "2026-01"
        assert "notes" in payload
        assert any("correlational" in n for n in payload["notes"])

    def test_text_and_markdown_render_without_error_on_empty(self) -> None:
        empty = QualityAnalysis()
        assert "No closed-issue history found" in format_agent_quality_text(empty)
        assert "No closed-issue history found" in format_agent_quality_markdown(empty)

    def test_yaml_falls_back_gracefully(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for i in range(5):
            _close(db, f"BUG-{1400 + i}", "2026-01-01T00:00:00Z")
        analysis = analyze_agent_quality([], db=db, min_sample=5)
        out = format_agent_quality_yaml(analysis)
        assert "windows" in out
