"""Tests for issue_history module."""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.issue_history import (
    parse_completed_issue,
    scan_active_issues,
    scan_completed_issues,
)
from little_loops.issue_history.parsing import _parse_completion_date


class TestParseCompletedIssue:
    """Tests for parse_completed_issue function."""

    def test_parse_with_frontmatter(self, tmp_path: Path) -> None:
        """Test parsing issue with frontmatter."""
        issue_file = tmp_path / "P1-BUG-042-test-issue.md"
        issue_file.write_text(
            """---
discovered_by: scan-codebase
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
        assert issue.discovered_by == "scan-codebase"
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


class TestParseCompletionDate:
    """Tests for _parse_completion_date: field label variants and git-log fallback."""

    def test_fixed_label(self, tmp_path: Path) -> None:
        """**Fixed**: label is parsed correctly."""
        f = tmp_path / "P1-BUG-001-test.md"
        f.write_text("## Resolution\n\n- **Fixed**: 2026-02-14\n")
        result = _parse_completion_date(f.read_text(), f)
        assert result == date(2026, 2, 14)

    def test_closed_label(self, tmp_path: Path) -> None:
        """**Closed**: label is parsed correctly."""
        f = tmp_path / "P1-BUG-002-test.md"
        f.write_text("## Resolution\n\n- **Closed**: 2026-03-01\n")
        result = _parse_completion_date(f.read_text(), f)
        assert result == date(2026, 3, 1)

    def test_date_label(self, tmp_path: Path) -> None:
        """**Date**: label is parsed correctly."""
        f = tmp_path / "P2-ENH-003-test.md"
        f.write_text("## Resolution\n\n- **Date**: 2025-12-31\n")
        result = _parse_completion_date(f.read_text(), f)
        assert result == date(2025, 12, 31)

    def test_completed_label_still_works(self, tmp_path: Path) -> None:
        """**Completed**: label continues to work after the change."""
        f = tmp_path / "P1-BUG-004-test.md"
        f.write_text("## Resolution\n\n- **Completed**: 2026-01-15\n")
        result = _parse_completion_date(f.read_text(), f)
        assert result == date(2026, 1, 15)

    def test_git_log_fallback_when_no_date_field(self, tmp_path: Path) -> None:
        """When no date field found, git log --diff-filter=A is used as fallback."""
        f = tmp_path / "P3-ENH-005-test.md"
        f.write_text("## Resolution\n\nNo date field here.\n")
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="2026-03-15\n", stderr=""
        )
        with patch("little_loops.issue_history.parsing.subprocess.run", return_value=mock_result):
            result = _parse_completion_date(f.read_text(), f)
        assert result == date(2026, 3, 15)

    def test_git_log_fallback_returns_none_when_empty(self, tmp_path: Path) -> None:
        """When git log returns empty output, None is returned."""
        f = tmp_path / "P3-ENH-006-test.md"
        f.write_text("## Resolution\n\nNo date field here.\n")
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("little_loops.issue_history.parsing.subprocess.run", return_value=mock_result):
            result = _parse_completion_date(f.read_text(), f)
        assert result is None

    def test_git_log_fallback_returns_none_on_nonzero_exit(self, tmp_path: Path) -> None:
        """When git log returns non-zero exit code, None is returned."""
        f = tmp_path / "P3-ENH-007-test.md"
        f.write_text("## Resolution\n\nNo date field here.\n")
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=128, stdout="", stderr="not a git repo"
        )
        with patch("little_loops.issue_history.parsing.subprocess.run", return_value=mock_result):
            result = _parse_completion_date(f.read_text(), f)
        assert result is None

    def test_git_log_fallback_returns_none_on_oserror(self, tmp_path: Path) -> None:
        """When subprocess.run raises OSError, None is returned."""
        f = tmp_path / "P3-ENH-008-test.md"
        f.write_text("## Resolution\n\nNo date field here.\n")
        with patch(
            "little_loops.issue_history.parsing.subprocess.run",
            side_effect=OSError("git not found"),
        ):
            result = _parse_completion_date(f.read_text(), f)
        assert result is None


class TestBatchCompletionDates:
    """Tests for _batch_completion_dates and the N+1 fix in scan_completed_issues."""

    def test_scan_completed_issues_single_git_log_call(self, tmp_path: Path) -> None:
        """scan_completed_issues must call git log at most once regardless of file count."""
        completed_dir = tmp_path / "completed"
        completed_dir.mkdir()

        # Create 3 dateless files — each would trigger its own git log without the fix
        for i in range(1, 4):
            (completed_dir / f"P1-BUG-{i:03d}-issue.md").write_text("# BUG\n\nNo date.\n")

        batch_output = (
            "\x002026-01-10\n"
            "\n"
            "completed/P1-BUG-001-issue.md\n"
            "completed/P1-BUG-002-issue.md\n"
            "\n"
            "\x002026-01-05\n"
            "\n"
            "completed/P1-BUG-003-issue.md\n"
        )
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=batch_output, stderr=""
        )
        with patch(
            "little_loops.issue_history.parsing.subprocess.run", return_value=mock_result
        ) as mock_run:
            issues = scan_completed_issues(completed_dir)

        mock_run.assert_called_once()
        assert len(issues) == 3
        dates = {i.issue_id: i.completed_date for i in issues}
        assert dates["BUG-001"] == date(2026, 1, 10)
        assert dates["BUG-002"] == date(2026, 1, 10)
        assert dates["BUG-003"] == date(2026, 1, 5)

    def test_batch_dates_not_found_returns_none(self, tmp_path: Path) -> None:
        """Files missing from the batch result get None as the completion date."""
        completed_dir = tmp_path / "completed"
        completed_dir.mkdir()
        (completed_dir / "P2-ENH-001-enh.md").write_text("# ENH\n\nNo date.\n")

        # Batch returns empty (file not in git history yet)
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch(
            "little_loops.issue_history.parsing.subprocess.run", return_value=mock_result
        ):
            issues = scan_completed_issues(completed_dir)

        assert len(issues) == 1
        assert issues[0].completed_date is None

    def test_frontmatter_date_skips_git_log_entirely(self, tmp_path: Path) -> None:
        """Files with an inline Resolution date never trigger any git log call."""
        completed_dir = tmp_path / "completed"
        completed_dir.mkdir()
        (completed_dir / "P1-BUG-001-dated.md").write_text(
            "## Resolution\n\n- **Completed**: 2026-03-01\n"
        )

        # Batch returns empty; per-file fallback must not be called either
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch(
            "little_loops.issue_history.parsing.subprocess.run", return_value=mock_result
        ) as mock_run:
            issues = scan_completed_issues(completed_dir)

        # Only the one batch call is made; no per-file call
        mock_run.assert_called_once()
        assert issues[0].completed_date == date(2026, 3, 1)


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


class TestScanActiveIssues:
    """Tests for scan_active_issues function."""

    def test_scan_empty(self, tmp_path: Path) -> None:
        """Test scanning empty directory."""

        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()

        result = scan_active_issues(issues_dir)
        assert result == []

    def test_scan_with_issues(self, tmp_path: Path) -> None:
        """Test scanning directory with issues."""

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

    def test_scan_with_custom_category_dirs(self, tmp_path: Path) -> None:
        """Custom category_dirs are respected; default categories are not scanned."""
        issues_dir = tmp_path / ".issues"

        # Standard category with an issue (should be skipped)
        bugs_dir = issues_dir / "bugs"
        bugs_dir.mkdir(parents=True)
        (bugs_dir / "P1-BUG-001-skip.md").write_text("# Should not appear\n")

        # Custom category with an issue (should be included)
        tasks_dir = issues_dir / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "P3-TASK-001-my-task.md").write_text("# My task\n")

        result = scan_active_issues(issues_dir, category_dirs=["tasks"])
        assert len(result) == 1
        paths = [r[0] for r in result]
        assert any("TASK-001" in p.name for p in paths)

    def test_scan_default_categories_unchanged(self, tmp_path: Path) -> None:
        """Omitting category_dirs falls back to the default three categories."""
        issues_dir = tmp_path / ".issues"
        for cat in ["bugs", "features", "enhancements"]:
            d = issues_dir / cat
            d.mkdir(parents=True)
        (issues_dir / "bugs" / "P1-BUG-001-test.md").write_text("# BUG-001\n")

        result = scan_active_issues(issues_dir)
        assert len(result) == 1

    def test_scan_logs_warning_on_unreadable_file(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Parse errors are logged at WARNING level; issue still appears in results."""

        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001\n")

        with caplog.at_level("WARNING", logger="little_loops.issue_history.parsing"):
            with patch.object(Path, "read_text", side_effect=PermissionError("access denied")):
                result = scan_active_issues(tmp_path / ".issues")

        assert len(result) == 1
        assert "Failed to parse" in caplog.text
        assert "access denied" in caplog.text
