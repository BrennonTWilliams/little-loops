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
from little_loops.issue_history.quality_regressions import (
    ATTRIBUTION_MIN_SHIFT,
    load_window_compositions,
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


def _orchestration_run_raw(
    db: Path, *, run_id: str, driver: str, issue_id: str, started_at: str, ll_version: str | None
) -> None:
    """Insert an orchestration_runs row with an explicit ll_version, bypassing
    record_orchestration_run()'s FEAT-3404 auto-fill-from-installed-version default
    (passing ll_version=None to the writer stamps the current package version, not
    NULL -- this is the only way to simulate a genuinely-NULL legacy row in a test).
    """
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO orchestration_runs(run_id, driver, issue_id, status, started_at, "
            "ll_version) VALUES(?, ?, ?, 'completed', ?, ?)",
            (run_id, driver, issue_id, started_at, ll_version),
        )
        conn.commit()
    finally:
        conn.close()


def _raw_event(db: Path, session_id: str, host: str, *, line_no: int) -> None:
    """Insert one raw_events row tied to a session -- no existing helper covers `host`."""
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO raw_events"
            "(ts, session_id, host, source_path, line_no, event_type, raw_line, parsed_json)"
            " VALUES('2026-07-15T00:00:00Z', ?, ?, 's.jsonl', ?, 'user', '{}', '{}')",
            (session_id, host, line_no),
        )
        conn.commit()
    finally:
        conn.close()


def _compositions(db: Path) -> list:
    """Rebuild the (issue_window, issue_ids, session_issues) locals `analyze_agent_quality()`
    builds internally, and call `load_window_compositions()` directly -- for fixtures that
    assert on `WindowComposition` shape rather than on a detected `RegressionEvent`.
    """
    from little_loops.issue_history._utils import month_key
    from little_loops.issue_history._utils import orchestrator_labels as _orch_labels
    from little_loops.issue_history.agent_quality import _load_closed_issues, _session_issue_map
    from little_loops.issue_history.rework import UNATTRIBUTED_LABEL

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        closed = _load_closed_issues(conn)
        orch_labels = _orch_labels(conn, {c["issue_id"] for c in closed})
        issue_window: dict[int, tuple[str, str]] = {}
        issue_ids: dict[int, str] = {}
        for c in closed:
            period = month_key(c["done_ts"])
            orchestrator = orch_labels.get(c["issue_id"], UNATTRIBUTED_LABEL)
            issue_window[c["issue_num"]] = (period, orchestrator)
            issue_ids[c["issue_num"]] = c["issue_id"]
        session_issues = _session_issue_map(conn)
        return load_window_compositions(conn, issue_window, issue_ids, session_issues)
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


# ---------------------------------------------------------------------------
# Regression detection, attribution, and composition loading (FEAT-3405)
# ---------------------------------------------------------------------------


class TestRegressionDetectionFixRate:
    def test_flat_history_no_regression_detected(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for month, base in (("01", 2000), ("02", 2100), ("03", 2200), ("04", 2300)):
            for i in range(5):
                _close(db, f"BUG-{base + i}", f"2026-{month}-01T00:00:00Z")

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        assert analysis.regressions is not None
        assert [e for e in analysis.regressions.events if e.metric == "fix_rate"] == []

    def test_injected_drop_flagged(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for month, base in (("01", 2400), ("02", 2500), ("03", 2600)):
            for i in range(5):
                _close(db, f"BUG-{base + i}", f"2026-{month}-01T00:00:00Z")
        for i in range(5):
            issue_id = f"BUG-{2700 + i}"
            _close(db, issue_id, "2026-04-01T00:00:00Z")
            if i < 3:
                _reopen(db, issue_id, "2026-04-05T00:00:00Z")

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        assert analysis.regressions is not None
        fix_rate_events = [e for e in analysis.regressions.events if e.metric == "fix_rate"]
        assert len(fix_rate_events) == 1
        event = fix_rate_events[0]
        assert event.period == "2026-04"
        assert event.series == "unattributed"
        assert event.value == 1 - (3 / 5)
        assert event.baseline_value == 1.0
        assert event.magnitude > 0.30


class TestRegressionUnknownPeriod:
    def test_unknown_period_excluded_and_never_latest(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for month, base in (("01", 2800), ("02", 2900), ("03", 3000)):
            for i in range(5):
                _close(db, f"BUG-{base + i}", f"2026-{month}-01T00:00:00Z")
        for i in range(5):
            issue_id = f"BUG-{3100 + i}"
            _close(db, issue_id, "2026-04-01T00:00:00Z")
            if i < 3:
                _reopen(db, issue_id, "2026-04-05T00:00:00Z")
        # 5 more closed issues with an empty done_ts -> month_key sentinel "unknown".
        for i in range(5):
            _close(db, f"BUG-{3200 + i}", "")

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        assert analysis.regressions is not None
        assert analysis.regressions.skipped_unknown_period == 1
        assert all(e.period != "unknown" for e in analysis.regressions.events)
        fix_rate_events = [e for e in analysis.regressions.events if e.metric == "fix_rate"]
        assert len(fix_rate_events) == 1
        assert fix_rate_events[0].period == "2026-04"


class TestRegressionZeroBaseline:
    def test_zero_baseline_correction_rate_skipped_not_flagged(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for month, base in (("01", 3300), ("02", 3400), ("03", 3500)):
            for i in range(5):
                _close(db, f"BUG-{base + i}", f"2026-{month}-01T00:00:00Z")
        for i in range(5):
            issue_id = f"BUG-{3600 + i}"
            _close(db, issue_id, "2026-04-01T00:00:00Z", session_id=f"zb{i}")
        record_correction(db, "zb0", "please redo this", "user")
        record_correction(db, "zb1", "please redo this differently", "user")

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        assert analysis.regressions is not None
        assert [e for e in analysis.regressions.events if e.metric == "correction_rate"] == []
        assert analysis.regressions.skipped_zero_baseline == 1

    def test_zero_value_cost_window_ineligible_as_baseline(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for month, base in (("01", 3700), ("02", 3800), ("03", 3900)):
            for i in range(5):
                _close(db, f"BUG-{base + i}", f"2026-{month}-01T00:00:00Z")
        for i in range(5):
            issue_id = f"BUG-{4000 + i}"
            _close(db, issue_id, "2026-04-01T00:00:00Z", session_id=f"pr{i}")
            _usage_event(db, f"pr{i}", cost_usd=1.0)

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        assert analysis.regressions is not None
        assert [e for e in analysis.regressions.events if e.metric == "cost_per_issue"] == []

    def test_coverage_suppressed_cost_window_ineligible_as_baseline(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        # Jan: majority-null cost coverage -> verdict suppressed to None (ineligible).
        for i in range(5):
            issue_id = f"BUG-{4100 + i}"
            _close(db, issue_id, "2026-01-01T00:00:00Z", session_id=f"j{i}")
            _usage_event(db, f"j{i}", cost_usd=1.0 if i == 0 else None)
        # Feb, Mar: fully priced, eligible baseline.
        for month, base in (("02", 4200), ("03", 4300)):
            for i in range(5):
                issue_id = f"BUG-{base + i}"
                _close(db, issue_id, f"2026-{month}-01T00:00:00Z", session_id=f"{issue_id}-s")
                _usage_event(db, f"{issue_id}-s", cost_usd=1.0)
        # Apr: a real cost jump against the Feb/Mar baseline (Jan excluded).
        for i in range(5):
            issue_id = f"BUG-{4400 + i}"
            _close(db, issue_id, "2026-04-01T00:00:00Z", session_id=f"a{i}")
            _usage_event(db, f"a{i}", cost_usd=5.0)

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        assert analysis.regressions is not None
        cost_events = [e for e in analysis.regressions.events if e.metric == "cost_per_issue"]
        assert len(cost_events) == 1
        assert cost_events[0].period == "2026-04"
        assert cost_events[0].baseline_periods == ["2026-02", "2026-03"]
        assert cost_events[0].baseline_value == 1.0


class TestAttribution:
    def test_model_mix_shift_coincides_with_drop_attributes_model(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for month, base in (("01", 4500), ("02", 4600), ("03", 4700)):
            for i in range(5):
                issue_id = f"BUG-{base + i}"
                _close(db, issue_id, f"2026-{month}-01T00:00:00Z", session_id=f"{issue_id}-s")
                _usage_event(db, f"{issue_id}-s", model="claude-haiku-4-5")
        for i in range(5):
            issue_id = f"BUG-{4800 + i}"
            _close(db, issue_id, "2026-04-01T00:00:00Z", session_id=f"{issue_id}-s")
            _usage_event(db, f"{issue_id}-s", model="claude-opus-5")
            if i < 3:
                _reopen(db, issue_id, "2026-04-05T00:00:00Z")

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        assert analysis.regressions is not None
        fix_rate_events = [e for e in analysis.regressions.events if e.metric == "fix_rate"]
        assert len(fix_rate_events) == 1
        attribution = fix_rate_events[0].attribution
        assert attribution is not None
        assert attribution.dimension == "model"
        assert attribution.value == "claude-opus-5"
        assert attribution.shift > ATTRIBUTION_MIN_SHIFT

    def test_unchanged_model_mix_attributes_none(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for month, base in (("01", 4900), ("02", 5000), ("03", 5100)):
            for i in range(5):
                issue_id = f"BUG-{base + i}"
                _close(db, issue_id, f"2026-{month}-01T00:00:00Z", session_id=f"{issue_id}-s")
                _usage_event(db, f"{issue_id}-s", model="claude-sonnet-5")
        for i in range(5):
            issue_id = f"BUG-{5200 + i}"
            _close(db, issue_id, "2026-04-01T00:00:00Z", session_id=f"{issue_id}-s")
            _usage_event(db, f"{issue_id}-s", model="claude-sonnet-5")
            if i < 3:
                _reopen(db, issue_id, "2026-04-05T00:00:00Z")

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        assert analysis.regressions is not None
        fix_rate_events = [e for e in analysis.regressions.events if e.metric == "fix_rate"]
        assert len(fix_rate_events) == 1
        assert fix_rate_events[0].attribution is None

    def test_ll_version_stamped_month_against_all_null_baseline_attributes_none(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "history.db"
        for month, base in (("01", 5300), ("02", 5400), ("03", 5500)):
            for i in range(5):
                issue_id = f"BUG-{base + i}"
                _close(db, issue_id, f"2026-{month}-01T00:00:00Z")
                _orchestration_run_raw(
                    db,
                    run_id=issue_id,
                    driver="ll-auto",
                    issue_id=issue_id,
                    started_at=f"2026-{month}-01T00:00:00Z",
                    ll_version=None,
                )
        for i in range(5):
            issue_id = f"BUG-{5600 + i}"
            _close(db, issue_id, "2026-04-01T00:00:00Z")
            _orchestration_run_raw(
                db,
                run_id=issue_id,
                driver="ll-auto",
                issue_id=issue_id,
                started_at="2026-04-01T00:00:00Z",
                ll_version="0.42.0",
            )
            if i < 3:
                _reopen(db, issue_id, "2026-04-05T00:00:00Z")

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        assert analysis.regressions is not None
        fix_rate_events = [
            e
            for e in analysis.regressions.events
            if e.metric == "fix_rate" and e.series == "ll-auto"
        ]
        assert len(fix_rate_events) == 1
        assert fix_rate_events[0].attribution is None

    def test_partial_ll_version_coverage_skipped(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        for month, base in (("01", 5700), ("02", 5800), ("03", 5900)):
            for i in range(5):
                issue_id = f"BUG-{base + i}"
                _close(db, issue_id, f"2026-{month}-01T00:00:00Z")
                record_orchestration_run(
                    db,
                    run_id=issue_id,
                    driver="ll-auto",
                    issue_id=issue_id,
                    status="completed",
                    started_at=f"2026-{month}-01T00:00:00Z",
                )
        for i in range(20):
            issue_id = f"BUG-{6000 + i}"
            _close(db, issue_id, "2026-04-01T00:00:00Z")
            _orchestration_run_raw(
                db,
                run_id=issue_id,
                driver="ll-auto",
                issue_id=issue_id,
                started_at="2026-04-01T00:00:00Z",
                ll_version="0.9.0" if i == 0 else None,
            )
            if i < 12:
                _reopen(db, issue_id, "2026-04-05T00:00:00Z")

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        assert analysis.regressions is not None
        fix_rate_events = [
            e
            for e in analysis.regressions.events
            if e.metric == "fix_rate" and e.series == "ll-auto"
        ]
        assert len(fix_rate_events) == 1
        assert fix_rate_events[0].attribution is None

    def test_synthetic_model_excluded_from_dimension(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        _close(db, "BUG-6100", "2026-01-01T00:00:00Z", session_id="syn0")
        _usage_event(db, "syn0", model="<synthetic>")
        _usage_event(db, "syn0", model="claude-sonnet-5")

        comps = _compositions(db)
        comp = next(c for c in comps if c.period == "2026-01" and c.series == "unattributed")
        assert "<synthetic>" not in comp.counts.get("model", {})
        assert comp.counts["model"]["claude-sonnet-5"] == 1.0

    def test_model_share_weighted_by_row_count(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        _close(db, "BUG-6200", "2026-01-01T00:00:00Z", session_id="wr0")
        _usage_event(db, "wr0", model="claude-haiku-4-5")
        for _ in range(10):
            _usage_event(db, "wr0", model="claude-sonnet-5")

        comps = _compositions(db)
        comp = next(c for c in comps if c.period == "2026-01" and c.series == "unattributed")
        assert comp.counts["model"]["claude-haiku-4-5"] == 1.0
        assert comp.counts["model"]["claude-sonnet-5"] == 10.0

    def test_multi_run_issue_uses_latest_started_at_ll_version(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        _close(db, "BUG-6300", "2026-01-01T00:00:00Z")
        record_orchestration_run(
            db,
            run_id="run-a",
            driver="ll-auto",
            issue_id="BUG-6300",
            status="failed",
            started_at="2026-01-01T00:00:00Z",
            ll_version="0.40.0",
        )
        record_orchestration_run(
            db,
            run_id="run-b",
            driver="ll-auto",
            issue_id="BUG-6300",
            status="completed",
            started_at="2026-01-02T00:00:00Z",
            ll_version="0.41.0",
        )

        comps = _compositions(db)
        comp = next(c for c in comps if c.period == "2026-01" and c.series == "ll-auto")
        assert comp.counts["ll_version"] == {"0.41.0": 1.0}


class TestRetryInflationRegression:
    def test_retry_inflation_series_flagged_and_attributed_to_ll_version(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "history.db"
        for month in ("01", "02", "03"):
            for i in range(5):
                record_loop_run_summary(
                    db,
                    run_id=f"{month}-{i}",
                    loop_name="rn-refine",
                    started_at=f"2026-{month}-01T00:00:00Z",
                    ended_at=f"2026-{month}-01T01:00:00Z",
                    final_state="done",
                    iterations=1,
                    ll_version="0.40.0",
                )
        for i in range(5):
            record_loop_run_summary(
                db,
                run_id=f"04-{i}",
                loop_name="rn-refine",
                started_at="2026-04-01T00:00:00Z",
                ended_at="2026-04-01T01:00:00Z",
                final_state="done",
                iterations=3,
                ll_version="0.41.0",
            )

        analysis = analyze_agent_quality([], db=db, min_sample=5)
        assert analysis.regressions is not None
        retry_events = [e for e in analysis.regressions.events if e.metric == "retry_inflation"]
        assert len(retry_events) == 1
        event = retry_events[0]
        assert event.series == "rn-refine"
        assert event.period == "2026-04"
        assert event.attribution is not None
        assert event.attribution.dimension == "ll_version"
        assert event.attribution.value == "0.41.0"


class TestLatestOnlyVsAllWindows:
    def _build_two_drop_history(self, db: Path) -> None:
        for i in range(5):
            _close(db, f"BUG-{6400 + i}", "2026-01-01T00:00:00Z")
        for i in range(5):
            issue_id = f"BUG-{6500 + i}"
            _close(db, issue_id, "2026-02-01T00:00:00Z")
            if i < 4:
                _reopen(db, issue_id, "2026-02-05T00:00:00Z")
        for i in range(5):
            _close(db, f"BUG-{6600 + i}", "2026-03-01T00:00:00Z")
        for i in range(5):
            issue_id = f"BUG-{6700 + i}"
            _close(db, issue_id, "2026-04-01T00:00:00Z")
            if i < 4:
                _reopen(db, issue_id, "2026-04-05T00:00:00Z")

    def test_latest_only_emits_only_newest_window(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._build_two_drop_history(db)

        analysis = analyze_agent_quality([], db=db, min_sample=5, latest_only=True)
        assert analysis.regressions is not None
        fix_rate_events = [e for e in analysis.regressions.events if e.metric == "fix_rate"]
        assert [e.period for e in fix_rate_events] == ["2026-04"]

    def test_all_windows_emits_historical_events(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._build_two_drop_history(db)

        analysis = analyze_agent_quality([], db=db, min_sample=5, latest_only=False)
        assert analysis.regressions is not None
        fix_rate_events = [e for e in analysis.regressions.events if e.metric == "fix_rate"]
        assert {e.period for e in fix_rate_events} == {"2026-02", "2026-04"}
