"""Tests for issue_history module."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.issue_history import (
    CompletedIssue,
    HistorySummary,
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
