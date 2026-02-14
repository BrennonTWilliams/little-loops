"""Tests for issue_history module."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from little_loops.issue_history import (
    parse_completed_issue,
    scan_active_issues,
    scan_completed_issues,
)


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
