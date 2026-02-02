"""Tests for issue_history module."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from little_loops.issue_history import (
    CompletedIssue,
    HistoryAnalysis,
    HistorySummary,
    calculate_analysis,
    format_analysis_json,
    format_analysis_markdown,
    format_analysis_text,
)


class TestHistoryAnalysis:
    """Tests for HistoryAnalysis dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization."""

        analysis = HistoryAnalysis(
            generated_date=date(2026, 1, 23),
            total_completed=50,
            total_active=10,
            date_range_start=date(2026, 1, 1),
            date_range_end=date(2026, 1, 23),
            summary=HistorySummary(total_count=50),
        )
        result = analysis.to_dict()
        assert result["generated_date"] == "2026-01-23"
        assert result["total_completed"] == 50

    def test_to_dict_with_none_dates(self) -> None:
        """Test serialization with None dates."""

        analysis = HistoryAnalysis(
            generated_date=date(2026, 1, 23),
            total_completed=0,
            total_active=0,
            date_range_start=None,
            date_range_end=None,
            summary=HistorySummary(total_count=0),
        )
        result = analysis.to_dict()
        assert result["date_range_start"] is None
        assert result["date_range_end"] is None


class TestCalculateAnalysis:
    """Tests for calculate_analysis function."""

    def test_empty_issues(self) -> None:
        """Test analysis with no issues."""

        analysis = calculate_analysis([])
        assert analysis.total_completed == 0
        assert analysis.period_metrics == []
        assert analysis.velocity_trend == "stable"

    def test_with_issues(self, tmp_path: Path) -> None:
        """Test analysis with sample issues."""

        issues = [
            CompletedIssue(
                path=tmp_path / "P1-BUG-001.md",
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=date(2026, 1, 10),
            ),
            CompletedIssue(
                path=tmp_path / "P2-ENH-002.md",
                issue_type="ENH",
                priority="P2",
                issue_id="ENH-002",
                completed_date=date(2026, 1, 15),
            ),
        ]

        analysis = calculate_analysis(issues)
        assert analysis.total_completed == 2
        assert analysis.summary.type_counts["BUG"] == 1

    def test_with_comparison(self, tmp_path: Path) -> None:
        """Test analysis with comparison period."""

        today = date.today()
        issues = [
            CompletedIssue(
                path=tmp_path / "P1-BUG-001.md",
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=today,
            ),
        ]

        analysis = calculate_analysis(issues, compare_days=30)
        assert analysis.comparison_period == "30d"

    def test_with_issues_dir(self, tmp_path: Path) -> None:
        """Test analysis scanning active issues."""

        # Create completed issues
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        # Create active issues directory
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        (bugs_dir / "P1-BUG-010-active.md").write_text("# Active bug\n")

        issues = [
            CompletedIssue(
                path=completed_dir / "P1-BUG-001.md",
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=date(2026, 1, 10),
            ),
        ]

        analysis = calculate_analysis(issues, issues_dir=tmp_path / ".issues")
        assert analysis.total_active == 1
        assert analysis.debt_metrics is not None
        assert analysis.debt_metrics.backlog_size == 1


class TestFormatAnalysis:
    """Tests for analysis formatting functions."""

    def test_format_analysis_text(self) -> None:
        """Test text formatting."""

        analysis = HistoryAnalysis(
            generated_date=date(2026, 1, 23),
            total_completed=50,
            total_active=10,
            date_range_start=date(2026, 1, 1),
            date_range_end=date(2026, 1, 23),
            summary=HistorySummary(
                total_count=50,
                type_counts={"BUG": 20, "ENH": 30},
            ),
        )

        text = format_analysis_text(analysis)
        assert "Issue History Analysis" in text
        assert "Completed: 50" in text
        assert "BUG" in text

    def test_format_analysis_json(self) -> None:
        """Test JSON formatting."""

        analysis = HistoryAnalysis(
            generated_date=date(2026, 1, 23),
            total_completed=50,
            total_active=10,
            date_range_start=None,
            date_range_end=None,
            summary=HistorySummary(total_count=50),
        )

        json_str = format_analysis_json(analysis)
        data = json.loads(json_str)
        assert data["total_completed"] == 50

    def test_format_analysis_markdown(self) -> None:
        """Test Markdown formatting."""

        analysis = HistoryAnalysis(
            generated_date=date(2026, 1, 23),
            total_completed=50,
            total_active=10,
            date_range_start=date(2026, 1, 1),
            date_range_end=date(2026, 1, 23),
            summary=HistorySummary(
                total_count=50,
                type_counts={"BUG": 20},
            ),
        )

        md = format_analysis_markdown(analysis)
        assert "# Issue History Analysis Report" in md
        assert "| Metric |" in md
