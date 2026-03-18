"""Tests for issue_history module."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from little_loops.issue_history import (
    CompletedIssue,
    HistorySummary,
    PeriodMetrics,
    calculate_summary,
    format_summary_json,
    format_summary_text,
)
from little_loops.issue_history.summary import (
    _analyze_subsystems,
    _calculate_trend,
    _group_by_period,
)


class TestCompletedIssue:
    """Tests for CompletedIssue dataclass."""

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        issue = CompletedIssue(
            path=Path("/test/P1-BUG-001-test.md"),
            issue_type="BUG",
            priority="P1",
            issue_id="BUG-001",
            discovered_by="scan-codebase",
            completed_date=date(2026, 1, 15),
        )
        result = issue.to_dict()

        assert result["path"] == "/test/P1-BUG-001-test.md"
        assert result["issue_type"] == "BUG"
        assert result["priority"] == "P1"
        assert result["issue_id"] == "BUG-001"
        assert result["discovered_by"] == "scan-codebase"
        assert result["completed_date"] == "2026-01-15"

    def test_to_dict_none_values(self) -> None:
        """Test to_dict with None values."""
        issue = CompletedIssue(
            path=Path("/test/P2-ENH-002-test.md"),
            issue_type="ENH",
            priority="P2",
            issue_id="ENH-002",
        )
        result = issue.to_dict()

        assert result["discovered_by"] is None
        assert result["completed_date"] is None


class TestHistorySummary:
    """Tests for HistorySummary dataclass."""

    def test_date_range_days(self) -> None:
        """Test date range calculation."""
        summary = HistorySummary(
            total_count=10,
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 1, 10),
        )
        assert summary.date_range_days == 10

    def test_date_range_days_none(self) -> None:
        """Test date range with missing dates."""
        summary = HistorySummary(total_count=10)
        assert summary.date_range_days is None

    def test_velocity(self) -> None:
        """Test velocity calculation."""
        summary = HistorySummary(
            total_count=20,
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 1, 10),
        )
        assert summary.velocity == 2.0

    def test_velocity_none(self) -> None:
        """Test velocity with missing dates."""
        summary = HistorySummary(total_count=10)
        assert summary.velocity is None

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        summary = HistorySummary(
            total_count=5,
            type_counts={"BUG": 3, "ENH": 2},
            priority_counts={"P1": 2, "P2": 3},
            discovery_counts={"manual": 5},
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 1, 5),
        )
        result = summary.to_dict()

        assert result["total_count"] == 5
        assert result["type_counts"] == {"BUG": 3, "ENH": 2}
        assert result["date_range_days"] == 5
        assert result["velocity"] == 1.0


class TestCalculateSummary:
    """Tests for calculate_summary function."""

    def test_empty_list(self) -> None:
        """Test summary of empty list."""
        summary = calculate_summary([])

        assert summary.total_count == 0
        assert summary.type_counts == {}
        assert summary.velocity is None

    def test_type_counts(self) -> None:
        """Test type counting."""
        issues = [
            CompletedIssue(Path("a.md"), "BUG", "P1", "BUG-1"),
            CompletedIssue(Path("b.md"), "BUG", "P2", "BUG-2"),
            CompletedIssue(Path("c.md"), "ENH", "P1", "ENH-1"),
        ]

        summary = calculate_summary(issues)

        assert summary.type_counts == {"BUG": 2, "ENH": 1}

    def test_priority_counts(self) -> None:
        """Test priority counting."""
        issues = [
            CompletedIssue(Path("a.md"), "BUG", "P0", "BUG-1"),
            CompletedIssue(Path("b.md"), "BUG", "P1", "BUG-2"),
            CompletedIssue(Path("c.md"), "BUG", "P1", "BUG-3"),
        ]

        summary = calculate_summary(issues)

        assert summary.priority_counts == {"P0": 1, "P1": 2}

    def test_discovery_counts(self) -> None:
        """Test discovery source counting."""
        issues = [
            CompletedIssue(Path("a.md"), "BUG", "P1", "BUG-1", discovered_by="manual"),
            CompletedIssue(Path("b.md"), "BUG", "P1", "BUG-2", discovered_by="scan-codebase"),
            CompletedIssue(Path("c.md"), "BUG", "P1", "BUG-3"),  # None -> "unknown"
        ]

        summary = calculate_summary(issues)

        assert "manual" in summary.discovery_counts
        assert "scan-codebase" in summary.discovery_counts
        assert "unknown" in summary.discovery_counts

    def test_date_range(self) -> None:
        """Test date range calculation."""
        issues = [
            CompletedIssue(Path("a.md"), "BUG", "P1", "BUG-1", completed_date=date(2026, 1, 5)),
            CompletedIssue(Path("b.md"), "BUG", "P1", "BUG-2", completed_date=date(2026, 1, 10)),
            CompletedIssue(Path("c.md"), "BUG", "P1", "BUG-3", completed_date=date(2026, 1, 1)),
        ]

        summary = calculate_summary(issues)

        assert summary.earliest_date == date(2026, 1, 1)
        assert summary.latest_date == date(2026, 1, 10)


class TestFormatSummary:
    """Tests for format functions."""

    def test_format_summary_text(self) -> None:
        """Test text formatting."""
        summary = HistorySummary(
            total_count=10,
            type_counts={"BUG": 5, "ENH": 5},
            priority_counts={"P1": 10},
            discovery_counts={"manual": 10},
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 1, 10),
        )

        text = format_summary_text(summary)

        assert "Total Completed: 10" in text
        assert "BUG" in text
        assert "ENH" in text
        assert "P1" in text
        assert "manual" in text
        assert "Velocity:" in text

    def test_format_summary_text_empty(self) -> None:
        """Test text formatting with empty summary."""
        summary = HistorySummary(total_count=0)

        text = format_summary_text(summary)

        assert "Total Completed: 0" in text

    def test_format_summary_json(self) -> None:
        """Test JSON formatting."""
        summary = HistorySummary(
            total_count=5,
            type_counts={"BUG": 5},
        )

        json_str = format_summary_json(summary)
        data = json.loads(json_str)

        assert data["total_count"] == 5
        assert data["type_counts"] == {"BUG": 5}

    def test_format_summary_json_roundtrip(self) -> None:
        """Test JSON output is valid JSON."""
        summary = HistorySummary(
            total_count=3,
            type_counts={"BUG": 1, "ENH": 2},
            priority_counts={"P1": 3},
            discovery_counts={"manual": 3},
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 1, 3),
        )

        json_str = format_summary_json(summary)
        data = json.loads(json_str)

        assert data["total_count"] == 3
        assert data["date_range_days"] == 3
        assert data["velocity"] == 1.0


class TestPeriodMetrics:
    """Tests for PeriodMetrics dataclass."""

    def test_bug_ratio(self) -> None:
        """Test bug ratio calculation."""

        period = PeriodMetrics(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            period_label="Jan 2026",
            total_completed=10,
            type_counts={"BUG": 3, "ENH": 5, "FEAT": 2},
        )
        assert period.bug_ratio == 0.3

    def test_bug_ratio_no_bugs(self) -> None:
        """Test bug ratio with no bugs."""

        period = PeriodMetrics(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            period_label="Jan 2026",
            total_completed=5,
            type_counts={"ENH": 5},
        )
        assert period.bug_ratio == 0.0

    def test_bug_ratio_empty(self) -> None:
        """Test bug ratio with no completions."""

        period = PeriodMetrics(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            period_label="Jan 2026",
            total_completed=0,
        )
        assert period.bug_ratio is None

    def test_to_dict(self) -> None:
        """Test serialization."""

        period = PeriodMetrics(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            period_label="Jan 2026",
            total_completed=10,
            type_counts={"BUG": 3},
        )
        result = period.to_dict()
        assert result["period_start"] == "2026-01-01"
        assert result["period_label"] == "Jan 2026"
        assert result["bug_ratio"] == 0.3


class TestSubsystemHealth:
    """Tests for SubsystemHealth dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization."""
        from little_loops.issue_history import SubsystemHealth

        health = SubsystemHealth(
            subsystem="scripts/little_loops/",
            total_issues=10,
            recent_issues=3,
            issue_ids=["BUG-001", "BUG-002"],
            trend="improving",
        )
        result = health.to_dict()
        assert result["subsystem"] == "scripts/little_loops/"
        assert result["trend"] == "improving"

    def test_to_dict_limits_issue_ids(self) -> None:
        """Test that to_dict limits issue_ids to 5."""
        from little_loops.issue_history import SubsystemHealth

        health = SubsystemHealth(
            subsystem="test/",
            issue_ids=["ID-1", "ID-2", "ID-3", "ID-4", "ID-5", "ID-6", "ID-7"],
        )
        result = health.to_dict()
        assert len(result["issue_ids"]) == 5


class TestTechnicalDebtMetrics:
    """Tests for TechnicalDebtMetrics dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization."""
        from little_loops.issue_history import TechnicalDebtMetrics

        debt = TechnicalDebtMetrics(
            backlog_size=25,
            backlog_growth_rate=1.5,
            aging_30_plus=8,
            high_priority_open=2,
        )
        result = debt.to_dict()
        assert result["backlog_size"] == 25
        assert result["backlog_growth_rate"] == 1.5

    def test_to_dict_rounds_values(self) -> None:
        """Test that to_dict rounds float values."""
        from little_loops.issue_history import TechnicalDebtMetrics

        debt = TechnicalDebtMetrics(
            backlog_growth_rate=1.567,
            debt_paydown_ratio=2.789,
        )
        result = debt.to_dict()
        assert result["backlog_growth_rate"] == 1.57
        assert result["debt_paydown_ratio"] == 2.79


class TestGroupByPeriod:
    """Tests for _group_by_period function."""

    def test_empty_list_returns_empty(self) -> None:
        """No issues → empty result."""
        result = _group_by_period([], period_type="monthly")
        assert result == []

    def test_issues_without_dates_returns_empty(self) -> None:
        """Issues with no completed_date are excluded."""
        issues = [CompletedIssue(Path("a.md"), "BUG", "P1", "BUG-1")]
        result = _group_by_period(issues, period_type="monthly")
        assert result == []

    def test_monthly_period_start(self) -> None:
        """Issue on July 15 groups into July 1 monthly period."""
        issues = [
            CompletedIssue(Path("a.md"), "BUG", "P1", "BUG-1", completed_date=date(2026, 7, 15))
        ]
        result = _group_by_period(issues, period_type="monthly")
        assert len(result) == 1
        assert result[0].period_start == date(2026, 7, 1)
        assert result[0].period_end == date(2026, 7, 31)
        assert result[0].total_completed == 1

    def test_quarterly_period_start(self) -> None:
        """Issue on July 15 groups into Q3 period starting July 1."""
        issues = [
            CompletedIssue(Path("a.md"), "BUG", "P1", "BUG-1", completed_date=date(2026, 7, 15))
        ]
        result = _group_by_period(issues, period_type="quarterly")
        assert len(result) == 1
        assert result[0].period_start == date(2026, 7, 1)
        assert result[0].period_end == date(2026, 9, 30)

    def test_quarterly_december_wrap(self) -> None:
        """Issue in December falls in Q4 (Oct 1); period end wraps to Dec 31."""
        issues = [
            CompletedIssue(Path("a.md"), "BUG", "P1", "BUG-1", completed_date=date(2026, 12, 15))
        ]
        result = _group_by_period(issues, period_type="quarterly")
        assert len(result) == 1
        assert result[0].period_start == date(2026, 10, 1)
        assert result[0].period_end == date(2026, 12, 31)

    def test_monthly_december_wrap(self) -> None:
        """December monthly period ends on Dec 31 (January wraps to next year)."""
        issues = [
            CompletedIssue(Path("a.md"), "BUG", "P1", "BUG-1", completed_date=date(2026, 12, 5))
        ]
        result = _group_by_period(issues, period_type="monthly")
        assert len(result) == 1
        assert result[0].period_start == date(2026, 12, 1)
        assert result[0].period_end == date(2026, 12, 31)


class TestCalculateTrend:
    """Tests for _calculate_trend function."""

    def test_ascending_returns_increasing(self) -> None:
        """Clearly ascending values produce 'increasing'."""
        assert _calculate_trend([1.0, 2.0, 3.0]) == "increasing"

    def test_descending_returns_decreasing(self) -> None:
        """Clearly descending values produce 'decreasing'."""
        assert _calculate_trend([3.0, 2.0, 1.0]) == "decreasing"

    def test_flat_returns_stable(self) -> None:
        """All-equal values produce 'stable' (slope = 0)."""
        assert _calculate_trend([2.0, 2.0, 2.0]) == "stable"

    def test_two_elements_returns_stable(self) -> None:
        """Short series (< 3 elements) returns 'stable' unconditionally."""
        assert _calculate_trend([1.0, 2.0]) == "stable"

    def test_one_element_returns_stable(self) -> None:
        """Single-element series returns 'stable'."""
        assert _calculate_trend([5.0]) == "stable"

    def test_empty_returns_stable(self) -> None:
        """Empty series returns 'stable'."""
        assert _calculate_trend([]) == "stable"

    def test_near_zero_normalized_slope_returns_stable(self) -> None:
        """Normalized slope within ±0.05 threshold returns 'stable'."""
        assert _calculate_trend([1.0, 1.02, 1.01]) == "stable"


class TestAnalyzeSubsystems:
    """Tests for _analyze_subsystems function."""

    def _make_issue(self, issue_id: str, completed_date: date | None = None) -> CompletedIssue:
        """Create a CompletedIssue with a path matching the issue_id."""
        return CompletedIssue(
            path=Path(f"/issues/{issue_id}.md"),
            issue_type="BUG",
            priority="P1",
            issue_id=issue_id,
            completed_date=completed_date,
        )

    def _subsystem_content(self, subsystem: str) -> str:
        """Return issue content that extracts the given subsystem path."""
        return f"**File**: `{subsystem}`\nSome issue description."

    def test_degrading_trend(self) -> None:
        """recent_ratio > 0.5 with total_issues >= 5 → trend='degrading'."""
        today = date.today()
        old = date(2020, 1, 1)
        issues = [
            self._make_issue("BUG-1", today),
            self._make_issue("BUG-2", today),
            self._make_issue("BUG-3", today),
            self._make_issue("BUG-4", today),
            self._make_issue("BUG-5", old),
            self._make_issue("BUG-6", old),
        ]
        contents = {
            issue.path: self._subsystem_content("scripts/little_loops/") for issue in issues
        }

        result = _analyze_subsystems(issues, recent_days=30, contents=contents)

        assert len(result) == 1
        assert result[0].total_issues == 6
        assert result[0].recent_issues == 4
        assert result[0].trend == "degrading"

    def test_improving_trend(self) -> None:
        """recent_ratio < 0.2 with total_issues >= 5 → trend='improving'."""
        old = date(2020, 1, 1)
        subsystem = "scripts/little_loops/"
        issues = [self._make_issue(f"BUG-{i}", old) for i in range(1, 6)]
        contents = {issue.path: self._subsystem_content(subsystem) for issue in issues}

        result = _analyze_subsystems(issues, recent_days=30, contents=contents)

        assert len(result) == 1
        assert result[0].total_issues == 5
        assert result[0].recent_issues == 0
        assert result[0].trend == "improving"

    def test_below_minimum_gate_stays_stable(self) -> None:
        """Fewer than 5 total issues → trend stays 'stable' regardless of ratio."""
        today = date.today()
        subsystem = "scripts/little_loops/"
        issues = [self._make_issue(f"BUG-{i}", today) for i in range(1, 5)]
        contents = {issue.path: self._subsystem_content(subsystem) for issue in issues}

        result = _analyze_subsystems(issues, recent_days=30, contents=contents)

        assert len(result) == 1
        assert result[0].total_issues == 4
        assert result[0].trend == "stable"

    def test_no_content_skips_issue(self) -> None:
        """Issues without content in the dict are skipped."""
        issues = [self._make_issue("BUG-1", date.today())]
        result = _analyze_subsystems(issues, recent_days=30, contents={})
        assert result == []
