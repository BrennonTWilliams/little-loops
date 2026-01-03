"""Tests for little_loops.issue_parser module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from little_loops.config import BRConfig
from little_loops.issue_parser import (
    IssueInfo,
    IssueParser,
    find_highest_priority_issue,
    find_issues,
    get_next_issue_number,
    slugify,
)


class TestSlugify:
    """Tests for the slugify function."""

    def test_basic_slugify(self) -> None:
        """Test basic text slugification."""
        assert slugify("Hello World") == "hello-world"

    def test_slugify_with_special_chars(self) -> None:
        """Test slugify removes special characters."""
        assert slugify("Hello! World?") == "hello-world"
        assert slugify("Test: Example") == "test-example"

    def test_slugify_with_multiple_spaces(self) -> None:
        """Test slugify handles multiple spaces."""
        assert slugify("Hello   World") == "hello-world"

    def test_slugify_with_hyphens(self) -> None:
        """Test slugify handles existing hyphens."""
        assert slugify("hello-world") == "hello-world"
        assert slugify("hello--world") == "hello-world"

    def test_slugify_strips_leading_trailing(self) -> None:
        """Test slugify strips leading and trailing hyphens."""
        assert slugify("-hello-") == "hello"
        assert slugify("  hello  ") == "hello"

    def test_slugify_empty_string(self) -> None:
        """Test slugify with empty string."""
        assert slugify("") == ""

    def test_slugify_only_special_chars(self) -> None:
        """Test slugify with only special characters."""
        assert slugify("!@#$%") == ""


class TestIssueInfo:
    """Tests for IssueInfo dataclass."""

    def test_priority_int_p0(self) -> None:
        """Test priority_int for P0."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority="P0",
            issue_id="BUG-001",
            title="Test",
        )
        assert info.priority_int == 0

    def test_priority_int_p5(self) -> None:
        """Test priority_int for P5."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority="P5",
            issue_id="BUG-001",
            title="Test",
        )
        assert info.priority_int == 5

    def test_priority_int_unknown(self) -> None:
        """Test priority_int for unknown priority."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority="HIGH",
            issue_id="BUG-001",
            title="Test",
        )
        assert info.priority_int == 99

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        info = IssueInfo(
            path=Path("/path/to/test.md"),
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test Issue",
        )
        result = info.to_dict()

        assert result["path"] == "/path/to/test.md"
        assert result["issue_type"] == "bugs"
        assert result["priority"] == "P1"
        assert result["issue_id"] == "BUG-001"
        assert result["title"] == "Test Issue"

    def test_from_dict(self) -> None:
        """Test from_dict deserialization."""
        data = {
            "path": "/path/to/test.md",
            "issue_type": "features",
            "priority": "P2",
            "issue_id": "FEAT-002",
            "title": "New Feature",
        }
        info = IssueInfo.from_dict(data)

        assert info.path == Path("/path/to/test.md")
        assert info.issue_type == "features"
        assert info.priority == "P2"
        assert info.issue_id == "FEAT-002"
        assert info.title == "New Feature"

    def test_roundtrip_serialization(self) -> None:
        """Test roundtrip through to_dict and from_dict."""
        original = IssueInfo(
            path=Path("/test/path.md"),
            issue_type="bugs",
            priority="P0",
            issue_id="BUG-999",
            title="Critical Bug",
        )
        restored = IssueInfo.from_dict(original.to_dict())

        assert restored.path == original.path
        assert restored.issue_type == original.issue_type
        assert restored.priority == original.priority
        assert restored.issue_id == original.issue_id
        assert restored.title == original.title


class TestIssueParser:
    """Tests for IssueParser class."""

    def test_parse_file_with_priority_and_id(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test parsing a file with priority and ID in filename."""
        # Setup config
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        # Create issue file
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P1-BUG-123-test-issue.md"
        issue_file.write_text("# BUG-123: Test Issue\n\nDescription here.")

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.priority == "P1"
        assert info.issue_id == "BUG-123"
        assert info.issue_type == "bugs"
        assert info.title == "Test Issue"

    def test_parse_file_without_priority_prefix(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test parsing a file without priority prefix defaults to lowest."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "BUG-456-no-priority.md"
        issue_file.write_text("# BUG-456: No Priority\n\nContent.")

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        # Should default to last priority in list
        assert info.priority == "P3"
        assert info.issue_id == "BUG-456"

    def test_parse_file_extracts_title_from_header(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test that title is extracted from markdown header."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P0-BUG-001-critical.md"
        issue_file.write_text("# BUG-001: Critical Database Crash\n\n## Summary\nDB crashes.")

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.title == "Critical Database Crash"

    def test_parse_file_title_fallback_to_simple_header(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test title extraction falls back to simple header."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P0-BUG-001-test.md"
        issue_file.write_text("# Simple Title\n\nContent without ID in header.")

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.title == "Simple Title"

    def test_parse_file_title_fallback_to_filename(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test title extraction falls back to filename when no header."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P0-BUG-001-no-header.md"
        issue_file.write_text("No markdown header in this file.\n\nJust content.")

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.title == "P0-BUG-001-no-header"  # Filename stem

    def test_parse_feature_issue(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test parsing a feature issue."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        features_dir = temp_project_dir / ".issues" / "features"
        features_dir.mkdir(parents=True)
        issue_file = features_dir / "P2-FEAT-001-dark-mode.md"
        issue_file.write_text("# FEAT-001: Add Dark Mode\n\nImplement dark theme.")

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.priority == "P2"
        assert info.issue_id == "FEAT-001"
        assert info.issue_type == "features"
        assert info.title == "Add Dark Mode"


class TestGetNextIssueNumber:
    """Tests for get_next_issue_number function."""

    def test_empty_directories(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test with empty issue directories."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)

        next_num = get_next_issue_number(config, "bugs")
        assert next_num == 1

    def test_with_existing_issues(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test with existing issues in directory."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        (bugs_dir / "P0-BUG-001-first.md").write_text("# BUG-001")
        (bugs_dir / "P1-BUG-005-fifth.md").write_text("# BUG-005")
        (bugs_dir / "P2-BUG-003-third.md").write_text("# BUG-003")

        next_num = get_next_issue_number(config, "bugs")
        assert next_num == 6  # Max is 5, so next is 6

    def test_includes_completed_issues(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test that completed issues are considered."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        completed_dir = temp_project_dir / ".issues" / "completed"
        bugs_dir.mkdir(parents=True)
        completed_dir.mkdir(parents=True)

        (bugs_dir / "P0-BUG-003-current.md").write_text("# BUG-003")
        (completed_dir / "P0-BUG-010-done.md").write_text("# BUG-010")

        next_num = get_next_issue_number(config, "bugs")
        assert next_num == 11  # Max in completed is 10


class TestFindIssues:
    """Tests for find_issues function."""

    def test_find_all_issues(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """Test finding all issues across categories."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        issues = find_issues(config)

        assert len(issues) == 5  # 3 bugs + 2 features

    def test_find_issues_by_category(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """Test finding issues filtered by category."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs = find_issues(config, category="bugs")
        features = find_issues(config, category="features")

        assert len(bugs) == 3
        assert len(features) == 2

    def test_find_issues_with_skip_ids(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """Test finding issues while skipping certain IDs."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        issues = find_issues(config, skip_ids={"BUG-001", "BUG-002"})

        assert len(issues) == 3  # 1 bug + 2 features
        issue_ids = [i.issue_id for i in issues]
        assert "BUG-001" not in issue_ids
        assert "BUG-002" not in issue_ids

    def test_find_issues_sorted_by_priority(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """Test that found issues are sorted by priority."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        issues = find_issues(config)

        # P0 should come first
        assert issues[0].priority == "P0"
        # Verify sorted order
        for i in range(len(issues) - 1):
            assert issues[i].priority_int <= issues[i + 1].priority_int

    def test_find_issues_empty_category(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test finding issues in non-existent category."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        issues = find_issues(config, category="nonexistent")

        assert len(issues) == 0

    def test_find_issues_skips_duplicates_in_completed(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test that issues already in completed/ are skipped from active directories."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        # Setup directories
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        completed_dir = temp_project_dir / ".issues" / "completed"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        completed_dir.mkdir(parents=True, exist_ok=True)

        # Create an issue in bugs/
        duplicate_file = "P0-BUG-100-duplicate-test.md"
        (bugs_dir / duplicate_file).write_text("# BUG-100: Duplicate Test\n\nContent.")

        # Create the same file in completed/ (simulating already-completed issue)
        (completed_dir / duplicate_file).write_text("# BUG-100: Duplicate Test\n\nContent.")

        # Create a non-duplicate issue
        (bugs_dir / "P1-BUG-101-not-duplicate.md").write_text("# BUG-101: Not Duplicate\n\nContent.")

        issues = find_issues(config, category="bugs")

        # Should only find the non-duplicate issue
        issue_ids = [i.issue_id for i in issues]
        assert "BUG-100" not in issue_ids
        assert "BUG-101" in issue_ids
        assert len(issues) == 1


class TestFindHighestPriorityIssue:
    """Tests for find_highest_priority_issue function."""

    def test_returns_p0_first(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """Test that P0 issue is returned first."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        highest = find_highest_priority_issue(config)

        assert highest is not None
        assert highest.priority == "P0"
        assert highest.issue_id == "BUG-001"

    def test_returns_none_when_empty(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test returns None when no issues exist."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        highest = find_highest_priority_issue(config)

        assert highest is None

    def test_respects_skip_ids(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """Test that skipped IDs are not returned."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        highest = find_highest_priority_issue(config, skip_ids={"BUG-001"})

        assert highest is not None
        assert highest.issue_id != "BUG-001"
        # Next highest should be P1 bugs
        assert highest.priority == "P1"

    def test_respects_category_filter(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """Test that category filter is respected."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        highest = find_highest_priority_issue(config, category="features")

        assert highest is not None
        assert highest.issue_type == "features"
        assert highest.priority == "P1"
        assert highest.issue_id == "FEAT-001"
