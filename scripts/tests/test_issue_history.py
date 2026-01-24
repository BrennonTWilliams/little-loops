"""Tests for issue_history module."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.issue_history import (
    CompletedIssue,
    HistorySummary,
    Hotspot,
    HotspotAnalysis,
    RegressionAnalysis,
    RegressionCluster,
    _extract_paths_from_issue,
    analyze_hotspots,
    analyze_regression_clustering,
    calculate_summary,
    format_summary_json,
    format_summary_text,
    parse_completed_issue,
    scan_completed_issues,
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
            discovered_by="scan_codebase",
            completed_date=date(2026, 1, 15),
        )
        result = issue.to_dict()

        assert result["path"] == "/test/P1-BUG-001-test.md"
        assert result["issue_type"] == "BUG"
        assert result["priority"] == "P1"
        assert result["issue_id"] == "BUG-001"
        assert result["discovered_by"] == "scan_codebase"
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


class TestParseCompletedIssue:
    """Tests for parse_completed_issue function."""

    def test_parse_with_frontmatter(self, tmp_path: Path) -> None:
        """Test parsing issue with frontmatter."""
        issue_file = tmp_path / "P1-BUG-042-test-issue.md"
        issue_file.write_text(
            """---
discovered_by: scan_codebase
---

# BUG-042: Test Issue

## Resolution

- **Completed**: 2026-01-15
"""
        )

        issue = parse_completed_issue(issue_file)

        assert issue.issue_type == "BUG"
        assert issue.priority == "P1"
        assert issue.issue_id == "BUG-042"
        assert issue.discovered_by == "scan_codebase"
        assert issue.completed_date == date(2026, 1, 15)

    def test_parse_without_frontmatter(self, tmp_path: Path) -> None:
        """Test parsing issue without frontmatter."""
        issue_file = tmp_path / "P2-ENH-007-enhancement.md"
        issue_file.write_text(
            """# ENH-007: Enhancement

## Resolution

- **Completed**: 2026-01-10
"""
        )

        issue = parse_completed_issue(issue_file)

        assert issue.issue_type == "ENH"
        assert issue.priority == "P2"
        assert issue.issue_id == "ENH-007"
        assert issue.discovered_by is None
        assert issue.completed_date == date(2026, 1, 10)

    def test_parse_feat_type(self, tmp_path: Path) -> None:
        """Test parsing FEAT type issue."""
        issue_file = tmp_path / "P3-FEAT-015-feature.md"
        issue_file.write_text("# FEAT-015: Feature\n")

        issue = parse_completed_issue(issue_file)

        assert issue.issue_type == "FEAT"
        assert issue.issue_id == "FEAT-015"

    def test_parse_frontmatter_null_discovered_by(self, tmp_path: Path) -> None:
        """Test parsing frontmatter with null discovered_by."""
        issue_file = tmp_path / "P1-BUG-001-test.md"
        issue_file.write_text(
            """---
discovered_by: null
---

# BUG-001: Test
"""
        )

        issue = parse_completed_issue(issue_file)

        assert issue.discovered_by is None


class TestScanCompletedIssues:
    """Tests for scan_completed_issues function."""

    def test_scan_empty_directory(self, tmp_path: Path) -> None:
        """Test scanning empty directory."""
        completed_dir = tmp_path / "completed"
        completed_dir.mkdir()

        issues = scan_completed_issues(completed_dir)

        assert issues == []

    def test_scan_nonexistent_directory(self, tmp_path: Path) -> None:
        """Test scanning nonexistent directory."""
        completed_dir = tmp_path / "nonexistent"

        issues = scan_completed_issues(completed_dir)

        assert issues == []

    def test_scan_multiple_issues(self, tmp_path: Path) -> None:
        """Test scanning multiple issues."""
        completed_dir = tmp_path / "completed"
        completed_dir.mkdir()

        (completed_dir / "P0-BUG-001-critical.md").write_text("# BUG-001\n")
        (completed_dir / "P1-ENH-002-improve.md").write_text("# ENH-002\n")
        (completed_dir / "P2-FEAT-003-feature.md").write_text("# FEAT-003\n")

        issues = scan_completed_issues(completed_dir)

        assert len(issues) == 3
        ids = {i.issue_id for i in issues}
        assert ids == {"BUG-001", "ENH-002", "FEAT-003"}

    def test_scan_ignores_non_md_files(self, tmp_path: Path) -> None:
        """Test scanning ignores non-markdown files."""
        completed_dir = tmp_path / "completed"
        completed_dir.mkdir()

        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")
        (completed_dir / "readme.txt").write_text("Not an issue\n")
        (completed_dir / ".gitkeep").write_text("")

        issues = scan_completed_issues(completed_dir)

        assert len(issues) == 1
        assert issues[0].issue_id == "BUG-001"


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
            CompletedIssue(
                Path("b.md"), "BUG", "P1", "BUG-2", discovered_by="scan_codebase"
            ),
            CompletedIssue(Path("c.md"), "BUG", "P1", "BUG-3"),  # None -> "unknown"
        ]

        summary = calculate_summary(issues)

        assert "manual" in summary.discovery_counts
        assert "scan_codebase" in summary.discovery_counts
        assert "unknown" in summary.discovery_counts

    def test_date_range(self) -> None:
        """Test date range calculation."""
        issues = [
            CompletedIssue(
                Path("a.md"), "BUG", "P1", "BUG-1", completed_date=date(2026, 1, 5)
            ),
            CompletedIssue(
                Path("b.md"), "BUG", "P1", "BUG-2", completed_date=date(2026, 1, 10)
            ),
            CompletedIssue(
                Path("c.md"), "BUG", "P1", "BUG-3", completed_date=date(2026, 1, 1)
            ),
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


class TestHistoryArgumentParsing:
    """Tests for ll-history argument parsing."""

    def _parse_history_args(self, args: list[str]) -> argparse.Namespace:
        """Parse arguments using the same parser as main_history."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        summary_parser = subparsers.add_parser("summary")
        summary_parser.add_argument("--json", action="store_true")
        summary_parser.add_argument("-d", "--directory", type=Path, default=None)
        return parser.parse_args(args)

    def test_summary_default(self) -> None:
        """Test summary with defaults."""
        args = self._parse_history_args(["summary"])
        assert args.command == "summary"
        assert args.json is False
        assert args.directory is None

    def test_summary_json_flag(self) -> None:
        """Test --json flag."""
        args = self._parse_history_args(["summary", "--json"])
        assert args.json is True

    def test_summary_directory(self) -> None:
        """Test -d flag."""
        args = self._parse_history_args(["summary", "-d", "/custom/path"])
        assert args.directory == Path("/custom/path")

    def test_summary_combined(self) -> None:
        """Test combined flags."""
        args = self._parse_history_args(["summary", "--json", "-d", "/path"])
        assert args.json is True
        assert args.directory == Path("/path")


class TestMainHistoryIntegration:
    """Integration tests for main_history entry point."""

    def test_main_history_no_command(self) -> None:
        """Test main_history with no command shows help."""
        with patch.object(sys, "argv", ["ll-history"]):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 1

    def test_main_history_summary_empty(self, tmp_path: Path) -> None:
        """Test main_history summary with empty directory."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with patch.object(
            sys, "argv", ["ll-history", "summary", "-d", str(tmp_path / ".issues")]
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0

    def test_main_history_summary_json(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Test main_history summary --json output."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")

        with patch.object(
            sys, "argv", ["ll-history", "summary", "--json", "-d", str(tmp_path / ".issues")]
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total_count"] == 1
        assert data["type_counts"]["BUG"] == 1

    def test_main_history_summary_text(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Test main_history summary text output."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")
        (completed_dir / "P2-ENH-002-test.md").write_text("# ENH-002\n")

        with patch.object(
            sys, "argv", ["ll-history", "summary", "-d", str(tmp_path / ".issues")]
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0

        captured = capsys.readouterr()
        assert "Total Completed: 2" in captured.out
        assert "BUG" in captured.out
        assert "ENH" in captured.out


# =============================================================================
# FEAT-110: Advanced History Analysis Tests
# =============================================================================


class TestPeriodMetrics:
    """Tests for PeriodMetrics dataclass."""

    def test_bug_ratio(self) -> None:
        """Test bug ratio calculation."""
        from little_loops.issue_history import PeriodMetrics

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
        from little_loops.issue_history import PeriodMetrics

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
        from little_loops.issue_history import PeriodMetrics

        period = PeriodMetrics(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            period_label="Jan 2026",
            total_completed=0,
        )
        assert period.bug_ratio is None

    def test_to_dict(self) -> None:
        """Test serialization."""
        from little_loops.issue_history import PeriodMetrics

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


class TestHistoryAnalysis:
    """Tests for HistoryAnalysis dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization."""
        from little_loops.issue_history import HistoryAnalysis, HistorySummary

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
        from little_loops.issue_history import HistoryAnalysis, HistorySummary

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
        from little_loops.issue_history import calculate_analysis

        analysis = calculate_analysis([])
        assert analysis.total_completed == 0
        assert analysis.period_metrics == []
        assert analysis.velocity_trend == "stable"

    def test_with_issues(self, tmp_path: Path) -> None:
        """Test analysis with sample issues."""
        from little_loops.issue_history import CompletedIssue, calculate_analysis

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
        from little_loops.issue_history import CompletedIssue, calculate_analysis

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
        from little_loops.issue_history import CompletedIssue, calculate_analysis

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


class TestScanActiveIssues:
    """Tests for scan_active_issues function."""

    def test_scan_empty(self, tmp_path: Path) -> None:
        """Test scanning empty directory."""
        from little_loops.issue_history import scan_active_issues

        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()

        result = scan_active_issues(issues_dir)
        assert result == []

    def test_scan_with_issues(self, tmp_path: Path) -> None:
        """Test scanning directory with issues."""
        from little_loops.issue_history import scan_active_issues

        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        (bugs_dir / "P0-BUG-001-critical.md").write_text("# Critical bug\n")
        (bugs_dir / "P2-BUG-002-minor.md").write_text("# Minor bug\n")

        features_dir = tmp_path / ".issues" / "features"
        features_dir.mkdir(parents=True)
        (features_dir / "P3-FEAT-001-feature.md").write_text("# Feature\n")

        result = scan_active_issues(tmp_path / ".issues")
        assert len(result) == 3

        # Check types were extracted
        types = {r[1] for r in result}
        assert "BUG" in types
        assert "FEAT" in types


class TestFormatAnalysis:
    """Tests for analysis formatting functions."""

    def test_format_analysis_text(self) -> None:
        """Test text formatting."""
        from little_loops.issue_history import (
            HistoryAnalysis,
            HistorySummary,
            format_analysis_text,
        )

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
        from little_loops.issue_history import (
            HistoryAnalysis,
            HistorySummary,
            format_analysis_json,
        )

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
        from little_loops.issue_history import (
            HistoryAnalysis,
            HistorySummary,
            format_analysis_markdown,
        )

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


class TestAnalyzeArgumentParsing:
    """Tests for ll-history analyze argument parsing."""

    def _parse_history_args(self, args: list[str]) -> argparse.Namespace:
        """Parse arguments using the same parser as main_history."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")

        # summary
        summary_parser = subparsers.add_parser("summary")
        summary_parser.add_argument("--json", action="store_true")
        summary_parser.add_argument("-d", "--directory", type=Path, default=None)

        # analyze
        analyze_parser = subparsers.add_parser("analyze")
        analyze_parser.add_argument(
            "-f",
            "--format",
            type=str,
            choices=["text", "json", "markdown", "yaml"],
            default="text",
        )
        analyze_parser.add_argument("-d", "--directory", type=Path, default=None)
        analyze_parser.add_argument(
            "-p",
            "--period",
            type=str,
            choices=["weekly", "monthly", "quarterly"],
            default="monthly",
        )
        analyze_parser.add_argument("-c", "--compare", type=int, default=None)

        return parser.parse_args(args)

    def test_analyze_default(self) -> None:
        """Test analyze with defaults."""
        args = self._parse_history_args(["analyze"])
        assert args.command == "analyze"
        assert args.format == "text"
        assert args.period == "monthly"
        assert args.compare is None

    def test_analyze_format_markdown(self) -> None:
        """Test --format markdown."""
        args = self._parse_history_args(["analyze", "--format", "markdown"])
        assert args.format == "markdown"

    def test_analyze_format_short(self) -> None:
        """Test -f json."""
        args = self._parse_history_args(["analyze", "-f", "json"])
        assert args.format == "json"

    def test_analyze_compare(self) -> None:
        """Test --compare flag."""
        args = self._parse_history_args(["analyze", "--compare", "30"])
        assert args.compare == 30

    def test_analyze_period_quarterly(self) -> None:
        """Test --period quarterly."""
        args = self._parse_history_args(["analyze", "--period", "quarterly"])
        assert args.period == "quarterly"

    def test_analyze_combined(self) -> None:
        """Test multiple flags together."""
        args = self._parse_history_args(
            ["analyze", "-f", "markdown", "-p", "weekly", "-c", "14"]
        )
        assert args.format == "markdown"
        assert args.period == "weekly"
        assert args.compare == 14


class TestMainHistoryAnalyze:
    """Integration tests for ll-history analyze."""

    def test_main_history_analyze_text(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test ll-history analyze text output."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")

        with patch.object(
            sys,
            "argv",
            ["ll-history", "analyze", "-d", str(tmp_path / ".issues")],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        assert "Issue History Analysis" in captured.out

    def test_main_history_analyze_markdown(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test ll-history analyze --format markdown."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")

        with patch.object(
            sys,
            "argv",
            ["ll-history", "analyze", "--format", "markdown", "-d", str(tmp_path / ".issues")],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        assert "# Issue History Analysis Report" in captured.out

    def test_main_history_analyze_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test ll-history analyze --format json."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")

        with patch.object(
            sys,
            "argv",
            ["ll-history", "analyze", "--format", "json", "-d", str(tmp_path / ".issues")],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total_completed" in data

    def test_main_history_analyze_with_compare(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test ll-history analyze --compare."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")

        with patch.object(
            sys,
            "argv",
            ["ll-history", "analyze", "--compare", "30", "-d", str(tmp_path / ".issues")],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0

    def test_main_history_analyze_empty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test ll-history analyze with empty directory."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with patch.object(
            sys,
            "argv",
            ["ll-history", "analyze", "-d", str(tmp_path / ".issues")],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        assert "Completed: 0" in captured.out


class TestHotspot:
    """Tests for Hotspot dataclass."""

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        hotspot = Hotspot(
            path="src/core/processor.py",
            issue_count=5,
            issue_ids=["BUG-001", "BUG-002", "ENH-003", "BUG-004", "ENH-005"],
            issue_types={"BUG": 3, "ENH": 2},
            bug_ratio=0.6,
            churn_indicator="high",
        )
        result = hotspot.to_dict()

        assert result["path"] == "src/core/processor.py"
        assert result["issue_count"] == 5
        assert result["bug_ratio"] == 0.6
        assert result["churn_indicator"] == "high"
        assert result["issue_types"] == {"BUG": 3, "ENH": 2}

    def test_to_dict_limits_issue_ids(self) -> None:
        """Test that to_dict limits issue_ids to 10."""
        hotspot = Hotspot(
            path="test.py",
            issue_count=15,
            issue_ids=[f"BUG-{i:03d}" for i in range(15)],
        )
        result = hotspot.to_dict()

        assert len(result["issue_ids"]) == 10


class TestHotspotAnalysis:
    """Tests for HotspotAnalysis dataclass."""

    def test_to_dict_empty(self) -> None:
        """Test to_dict with empty lists."""
        analysis = HotspotAnalysis()
        result = analysis.to_dict()

        assert result["file_hotspots"] == []
        assert result["directory_hotspots"] == []
        assert result["bug_magnets"] == []

    def test_to_dict_with_hotspots(self) -> None:
        """Test to_dict with hotspots."""
        hotspot = Hotspot(path="test.py", issue_count=3)
        analysis = HotspotAnalysis(file_hotspots=[hotspot])
        result = analysis.to_dict()

        assert len(result["file_hotspots"]) == 1
        assert result["file_hotspots"][0]["path"] == "test.py"


class TestExtractPathsFromIssue:
    """Tests for _extract_paths_from_issue function."""

    def test_extract_file_pattern(self) -> None:
        """Test extracting **File**: pattern."""
        content = "**File**: `scripts/little_loops/cli.py`"
        paths = _extract_paths_from_issue(content)
        assert "scripts/little_loops/cli.py" in paths

    def test_extract_backtick_pattern(self) -> None:
        """Test extracting backtick file paths."""
        content = "The bug is in `src/core/processor.py` and `src/utils/helper.py`"
        paths = _extract_paths_from_issue(content)
        assert "src/core/processor.py" in paths
        assert "src/utils/helper.py" in paths

    def test_extract_path_with_line_number(self) -> None:
        """Test extracting paths with line numbers."""
        content = "See scripts/cli.py:123 for the issue"
        paths = _extract_paths_from_issue(content)
        assert "scripts/cli.py" in paths

    def test_no_paths_found(self) -> None:
        """Test with no file paths."""
        content = "This is a general issue with no specific files."
        paths = _extract_paths_from_issue(content)
        assert paths == []

    def test_multiple_file_extensions(self) -> None:
        """Test various file extensions."""
        content = """
        config.json
        readme.md
        test.yaml
        app.ts
        """
        paths = _extract_paths_from_issue(content)
        assert "config.json" in paths
        assert "readme.md" in paths
        assert "test.yaml" in paths
        assert "app.ts" in paths


class TestAnalyzeHotspots:
    """Tests for analyze_hotspots function."""

    def test_empty_issues(self) -> None:
        """Test with empty issues list."""
        result = analyze_hotspots([])
        assert result.file_hotspots == []
        assert result.directory_hotspots == []
        assert result.bug_magnets == []

    def test_single_issue(self, tmp_path: Path) -> None:
        """Test with a single issue containing file paths."""
        issue_file = tmp_path / "P1-BUG-001.md"
        issue_file.write_text("**File**: `src/core/processor.py`\n\nBug in processor.")

        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
            )
        ]

        result = analyze_hotspots(issues)
        assert len(result.file_hotspots) == 1
        assert result.file_hotspots[0].path == "src/core/processor.py"
        assert result.file_hotspots[0].issue_count == 1

    def test_bug_magnet_detection(self, tmp_path: Path) -> None:
        """Test detection of bug magnets (>60% bug ratio)."""
        # Create 4 issues for same file: 3 bugs, 1 enhancement
        issues = []
        for i, issue_type in enumerate(["BUG", "BUG", "BUG", "ENH"]):
            issue_file = tmp_path / f"P1-{issue_type}-{i:03d}.md"
            issue_file.write_text("**File**: `src/problematic.py`")
            issues.append(
                CompletedIssue(
                    path=issue_file,
                    issue_type=issue_type,
                    priority="P1",
                    issue_id=f"{issue_type}-{i:03d}",
                )
            )

        result = analyze_hotspots(issues)
        assert len(result.bug_magnets) == 1
        assert result.bug_magnets[0].path == "src/problematic.py"
        assert result.bug_magnets[0].bug_ratio == 0.75  # 3/4

    def test_churn_indicator_high(self, tmp_path: Path) -> None:
        """Test high churn indicator assignment (5+ issues)."""
        issues = []
        for i in range(5):
            issue_file = tmp_path / f"P1-BUG-{i:03d}.md"
            issue_file.write_text("**File**: `src/churny.py`")
            issues.append(
                CompletedIssue(
                    path=issue_file,
                    issue_type="BUG",
                    priority="P1",
                    issue_id=f"BUG-{i:03d}",
                )
            )

        result = analyze_hotspots(issues)
        assert result.file_hotspots[0].churn_indicator == "high"

    def test_churn_indicator_medium(self, tmp_path: Path) -> None:
        """Test medium churn indicator assignment (3-4 issues)."""
        issues = []
        for i in range(3):
            issue_file = tmp_path / f"P1-BUG-{i:03d}.md"
            issue_file.write_text("**File**: `src/moderate.py`")
            issues.append(
                CompletedIssue(
                    path=issue_file,
                    issue_type="BUG",
                    priority="P1",
                    issue_id=f"BUG-{i:03d}",
                )
            )

        result = analyze_hotspots(issues)
        assert result.file_hotspots[0].churn_indicator == "medium"

    def test_churn_indicator_low(self, tmp_path: Path) -> None:
        """Test low churn indicator assignment (1-2 issues)."""
        issue_file = tmp_path / "P1-BUG-001.md"
        issue_file.write_text("**File**: `src/stable.py`")

        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
            )
        ]

        result = analyze_hotspots(issues)
        assert result.file_hotspots[0].churn_indicator == "low"

    def test_directory_hotspot(self, tmp_path: Path) -> None:
        """Test directory hotspot aggregation."""
        issues = []
        for i, filename in enumerate(["file1.py", "file2.py"]):
            issue_file = tmp_path / f"P1-BUG-{i:03d}.md"
            issue_file.write_text(f"**File**: `src/core/{filename}`")
            issues.append(
                CompletedIssue(
                    path=issue_file,
                    issue_type="BUG",
                    priority="P1",
                    issue_id=f"BUG-{i:03d}",
                )
            )

        result = analyze_hotspots(issues)
        # Should have 2 file hotspots
        assert len(result.file_hotspots) == 2
        # Should have 1 directory hotspot with 2 issues
        dir_hotspot = next(
            (h for h in result.directory_hotspots if h.path == "src/core/"), None
        )
        assert dir_hotspot is not None
        assert dir_hotspot.issue_count == 2

    def test_bug_magnet_threshold(self, tmp_path: Path) -> None:
        """Test bug magnet requires at least 3 issues."""
        # Create 2 issues for same file: 2 bugs (100% but under threshold)
        issues = []
        for i in range(2):
            issue_file = tmp_path / f"P1-BUG-{i:03d}.md"
            issue_file.write_text("**File**: `src/small.py`")
            issues.append(
                CompletedIssue(
                    path=issue_file,
                    issue_type="BUG",
                    priority="P1",
                    issue_id=f"BUG-{i:03d}",
                )
            )

        result = analyze_hotspots(issues)
        # Should not be a bug magnet (only 2 issues, needs 3+)
        assert len(result.bug_magnets) == 0


class TestRegressionCluster:
    """Tests for RegressionCluster dataclass."""

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        cluster = RegressionCluster(
            primary_file="src/core/processor.py",
            regression_count=3,
            fix_bug_pairs=[
                ("BUG-001", "BUG-002"),
                ("BUG-002", "BUG-003"),
                ("BUG-003", "BUG-004"),
            ],
            related_files=["src/core/state.py", "src/core/events.py"],
            time_pattern="chronic",
            severity="critical",
        )
        result = cluster.to_dict()

        assert result["primary_file"] == "src/core/processor.py"
        assert result["regression_count"] == 3
        assert result["time_pattern"] == "chronic"
        assert result["severity"] == "critical"
        assert len(result["fix_bug_pairs"]) == 3

    def test_to_dict_limits_lists(self) -> None:
        """Test that to_dict limits lists to 10 items."""
        cluster = RegressionCluster(
            primary_file="test.py",
            regression_count=15,
            fix_bug_pairs=[(f"BUG-{i:03d}", f"BUG-{i + 1:03d}") for i in range(15)],
            related_files=[f"file{i}.py" for i in range(15)],
        )
        result = cluster.to_dict()

        assert len(result["fix_bug_pairs"]) == 10
        assert len(result["related_files"]) == 10


class TestRegressionAnalysis:
    """Tests for RegressionAnalysis dataclass."""

    def test_to_dict_empty(self) -> None:
        """Test to_dict with empty data."""
        analysis = RegressionAnalysis()
        result = analysis.to_dict()

        assert result["clusters"] == []
        assert result["total_regression_chains"] == 0
        assert result["most_fragile_files"] == []

    def test_to_dict_with_clusters(self) -> None:
        """Test to_dict with clusters."""
        cluster = RegressionCluster(primary_file="test.py", regression_count=2)
        analysis = RegressionAnalysis(
            clusters=[cluster],
            total_regression_chains=1,
            most_fragile_files=["test.py"],
        )
        result = analysis.to_dict()

        assert len(result["clusters"]) == 1
        assert result["total_regression_chains"] == 1
        assert result["most_fragile_files"] == ["test.py"]


class TestAnalyzeRegressionClustering:
    """Tests for analyze_regression_clustering function."""

    def test_empty_issues(self) -> None:
        """Test with empty issues list."""
        result = analyze_regression_clustering([])
        assert result.clusters == []
        assert result.total_regression_chains == 0

    def test_no_bugs(self, tmp_path: Path) -> None:
        """Test with no bug issues."""
        issue_file = tmp_path / "P1-ENH-001.md"
        issue_file.write_text("**File**: `src/core/processor.py`")

        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="ENH",
                priority="P1",
                issue_id="ENH-001",
                completed_date=date(2026, 1, 1),
            )
        ]

        result = analyze_regression_clustering(issues)
        assert result.clusters == []

    def test_single_bug(self, tmp_path: Path) -> None:
        """Test with single bug issue."""
        issue_file = tmp_path / "P1-BUG-001.md"
        issue_file.write_text("**File**: `src/core/processor.py`")

        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=date(2026, 1, 1),
            )
        ]

        result = analyze_regression_clustering(issues)
        assert result.clusters == []

    def test_regression_detected(self, tmp_path: Path) -> None:
        """Test detection of regression chain."""
        # Create two bugs affecting same file within 7 days
        bug1_file = tmp_path / "P1-BUG-001.md"
        bug1_file.write_text("**File**: `src/core/processor.py`")

        bug2_file = tmp_path / "P1-BUG-002.md"
        bug2_file.write_text("**File**: `src/core/processor.py`")

        issues = [
            CompletedIssue(
                path=bug1_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=date(2026, 1, 1),
            ),
            CompletedIssue(
                path=bug2_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-002",
                completed_date=date(2026, 1, 3),  # 2 days later
            ),
        ]

        result = analyze_regression_clustering(issues)
        assert result.total_regression_chains == 1
        assert len(result.clusters) == 1
        assert result.clusters[0].primary_file == "src/core/processor.py"
        assert result.clusters[0].regression_count == 1
        assert ("BUG-001", "BUG-002") in result.clusters[0].fix_bug_pairs

    def test_no_regression_beyond_7_days(self, tmp_path: Path) -> None:
        """Test that bugs >7 days apart are not considered regressions."""
        bug1_file = tmp_path / "P1-BUG-001.md"
        bug1_file.write_text("**File**: `src/core/processor.py`")

        bug2_file = tmp_path / "P1-BUG-002.md"
        bug2_file.write_text("**File**: `src/core/processor.py`")

        issues = [
            CompletedIssue(
                path=bug1_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=date(2026, 1, 1),
            ),
            CompletedIssue(
                path=bug2_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-002",
                completed_date=date(2026, 1, 10),  # 9 days later
            ),
        ]

        result = analyze_regression_clustering(issues)
        assert result.total_regression_chains == 0
        assert len(result.clusters) == 0

    def test_no_regression_different_files(self, tmp_path: Path) -> None:
        """Test that bugs affecting different files are not regressions."""
        bug1_file = tmp_path / "P1-BUG-001.md"
        bug1_file.write_text("**File**: `src/core/processor.py`")

        bug2_file = tmp_path / "P1-BUG-002.md"
        bug2_file.write_text("**File**: `src/api/handlers.py`")

        issues = [
            CompletedIssue(
                path=bug1_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=date(2026, 1, 1),
            ),
            CompletedIssue(
                path=bug2_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-002",
                completed_date=date(2026, 1, 3),
            ),
        ]

        result = analyze_regression_clustering(issues)
        assert result.total_regression_chains == 0

    def test_severity_classification(self, tmp_path: Path) -> None:
        """Test severity classification based on regression count."""
        # Create 5 bugs with same file to trigger critical severity (4+ pairs)
        issues = []
        for i in range(5):
            bug_file = tmp_path / f"P1-BUG-{i:03d}.md"
            bug_file.write_text("**File**: `src/critical.py`")
            issues.append(
                CompletedIssue(
                    path=bug_file,
                    issue_type="BUG",
                    priority="P1",
                    issue_id=f"BUG-{i:03d}",
                    completed_date=date(2026, 1, 1) + timedelta(days=i),
                )
            )

        result = analyze_regression_clustering(issues)
        assert result.clusters[0].severity == "critical"

    def test_time_pattern_immediate(self, tmp_path: Path) -> None:
        """Test immediate time pattern (<3 days)."""
        bug1_file = tmp_path / "P1-BUG-001.md"
        bug1_file.write_text("**File**: `src/fast.py`")

        bug2_file = tmp_path / "P1-BUG-002.md"
        bug2_file.write_text("**File**: `src/fast.py`")

        issues = [
            CompletedIssue(
                path=bug1_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=date(2026, 1, 1),
            ),
            CompletedIssue(
                path=bug2_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-002",
                completed_date=date(2026, 1, 2),  # 1 day later
            ),
        ]

        result = analyze_regression_clustering(issues)
        assert result.clusters[0].time_pattern == "immediate"

    def test_most_fragile_files(self, tmp_path: Path) -> None:
        """Test most fragile files list."""
        # Create two separate regression chains
        files = [
            ("src/fragile1.py", 0),
            ("src/fragile1.py", 1),
            ("src/fragile2.py", 3),
            ("src/fragile2.py", 4),
        ]
        issues = []
        for i, (file_path, day_offset) in enumerate(files):
            bug_file = tmp_path / f"P1-BUG-{i:03d}.md"
            bug_file.write_text(f"**File**: `{file_path}`")
            issues.append(
                CompletedIssue(
                    path=bug_file,
                    issue_type="BUG",
                    priority="P1",
                    issue_id=f"BUG-{i:03d}",
                    completed_date=date(2026, 1, 1) + timedelta(days=day_offset),
                )
            )

        result = analyze_regression_clustering(issues)
        assert "src/fragile1.py" in result.most_fragile_files
        assert "src/fragile2.py" in result.most_fragile_files
