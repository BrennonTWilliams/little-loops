"""Tests for little_loops.issue_parser module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from little_loops.config import BRConfig
from little_loops.issue_parser import (
    IssueInfo,
    IssueParser,
    ProductImpact,
    find_highest_priority_issue,
    find_issues,
    get_next_issue_number,
    slugify,
)


def load_fixture(fixtures_dir: Path, *path_parts: str) -> str:
    """Load fixture file content by path parts."""
    fixture_path = fixtures_dir.joinpath(*path_parts)
    return fixture_path.read_text()


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

    def test_discovered_by_default_none(self) -> None:
        """Test discovered_by defaults to None."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority="P0",
            issue_id="BUG-001",
            title="Test",
        )
        assert info.discovered_by is None

    def test_discovered_by_value(self) -> None:
        """Test discovered_by can be set."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority="P0",
            issue_id="BUG-001",
            title="Test",
            discovered_by="scan-codebase",
        )
        assert info.discovered_by == "scan-codebase"

    def test_discovered_by_in_to_dict(self) -> None:
        """Test discovered_by appears in to_dict."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority="P0",
            issue_id="BUG-001",
            title="Test",
            discovered_by="audit-architecture",
        )
        data = info.to_dict()
        assert data["discovered_by"] == "audit-architecture"

    def test_discovered_by_from_dict(self) -> None:
        """Test discovered_by is restored from dict."""
        data = {
            "path": "/test/path.md",
            "issue_type": "bugs",
            "priority": "P1",
            "issue_id": "BUG-200",
            "title": "Test Issue",
            "discovered_by": "scan-codebase",
        }
        info = IssueInfo.from_dict(data)
        assert info.discovered_by == "scan-codebase"

    def test_discovered_by_from_dict_missing(self) -> None:
        """Test from_dict defaults to None for missing discovered_by."""
        data = {
            "path": "/test/path.md",
            "issue_type": "bugs",
            "priority": "P1",
            "issue_id": "BUG-200",
            "title": "Legacy Issue",
        }
        info = IssueInfo.from_dict(data)
        assert info.discovered_by is None

    def test_product_impact_default_none(self) -> None:
        """Test product_impact defaults to None."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority="P0",
            issue_id="BUG-001",
            title="Test",
        )
        assert info.product_impact is None

    def test_product_impact_with_values(self) -> None:
        """Test product_impact can be set with values."""
        impact = ProductImpact(
            goal_alignment="automation",
            persona_impact="developer",
            business_value="high",
            user_benefit="Faster processing",
        )
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority="P0",
            issue_id="BUG-001",
            title="Test",
            product_impact=impact,
        )
        assert info.product_impact is not None
        assert info.product_impact.goal_alignment == "automation"
        assert info.product_impact.persona_impact == "developer"
        assert info.product_impact.business_value == "high"
        assert info.product_impact.user_benefit == "Faster processing"

    def test_product_impact_in_to_dict(self) -> None:
        """Test product_impact appears in to_dict."""
        impact = ProductImpact(
            goal_alignment="ux",
            persona_impact="end_user",
            business_value="medium",
        )
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority="P0",
            issue_id="BUG-001",
            title="Test",
            product_impact=impact,
        )
        data = info.to_dict()
        assert data["product_impact"] is not None
        assert data["product_impact"]["goal_alignment"] == "ux"

    def test_product_impact_from_dict(self) -> None:
        """Test product_impact is restored from dict."""
        data = {
            "path": "/test/path.md",
            "issue_type": "bugs",
            "priority": "P1",
            "issue_id": "BUG-200",
            "title": "Test Issue",
            "discovered_by": "scan-product",
            "product_impact": {
                "goal_alignment": "performance",
                "persona_impact": "admin",
                "business_value": "high",
                "user_benefit": "Faster reports",
            },
        }
        info = IssueInfo.from_dict(data)
        assert info.product_impact is not None
        assert info.product_impact.goal_alignment == "performance"

    def test_product_impact_from_dict_missing(self) -> None:
        """Test from_dict defaults to None for missing product_impact."""
        data = {
            "path": "/test/path.md",
            "issue_type": "bugs",
            "priority": "P1",
            "issue_id": "BUG-200",
            "title": "Legacy Issue",
        }
        info = IssueInfo.from_dict(data)
        assert info.product_impact is None

    def test_product_impact_roundtrip(self) -> None:
        """Test product_impact survives roundtrip through to_dict/from_dict."""
        original = IssueInfo(
            path=Path("/test/path.md"),
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-100",
            title="Test",
            product_impact=ProductImpact(
                goal_alignment="security",
                persona_impact="admin",
                business_value="high",
                user_benefit="Better protection",
            ),
        )
        restored = IssueInfo.from_dict(original.to_dict())
        assert restored.product_impact is not None
        assert restored.product_impact.goal_alignment == "security"
        assert restored.product_impact.persona_impact == "admin"
        assert restored.product_impact.business_value == "high"
        assert restored.product_impact.user_benefit == "Better protection"


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

    def test_get_category_for_prefix(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test _get_category_for_prefix returns correct category."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        parser = IssueParser(config)

        assert parser._get_category_for_prefix("BUG") == "bugs"
        assert parser._get_category_for_prefix("FEAT") == "features"
        assert parser._get_category_for_prefix("UNKNOWN") == "bugs"  # Default

    def test_generate_id_uses_sequential_not_hash(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test that ID generation uses sequential numbers, not hash-based IDs."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        # Create bugs directory with existing issues
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        (bugs_dir / "P0-BUG-001-first.md").write_text("# BUG-001: First\n")
        (bugs_dir / "P1-BUG-005-fifth.md").write_text("# BUG-005: Fifth\n")

        parser = IssueParser(config)

        # Generate ID for a file without numeric ID in filename
        generated_id = parser._generate_id_from_filename("no-numbers-here.md", "BUG")

        # Should be BUG-006 (next after max 5), not a hash-based ID like BUG-1234
        assert generated_id == "BUG-006"

    def test_parse_file_without_explicit_id_gets_sequential(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test parsing file without ID in filename generates sequential ID."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        # Create bugs directory with one existing issue
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        (bugs_dir / "P0-BUG-010-existing.md").write_text("# BUG-010: Existing\n")

        # Create a file without any numbers at all (not even priority)
        # This tests the sequential fallback path
        issue_file = bugs_dir / "some-descriptive-name.md"
        issue_file.write_text("# Some Issue Title\n\nDescription here.")

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        # Should get sequential ID BUG-011, not a random hash-based ID
        assert info.issue_id == "BUG-011"
        assert info.issue_type == "bugs"

    def test_parse_discovered_by_from_frontmatter(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing discovered_by from YAML frontmatter."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P1-BUG-001-test.md"
        issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-with-frontmatter.md"))

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.discovered_by == "scan-codebase"

    def test_parse_no_frontmatter(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing issue without frontmatter."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P1-BUG-001-test.md"
        issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-no-frontmatter.md"))

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.discovered_by is None

    def test_parse_frontmatter_null_discovered_by(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing frontmatter with null discovered_by."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P1-BUG-001-test.md"
        issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-null-discovered-by.md"))

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.discovered_by is None

    def test_parse_frontmatter_only_discovered_by(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing frontmatter with only discovered_by field."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P1-BUG-001-test.md"
        issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-only-discovered-by.md"))

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.discovered_by == "audit-architecture"

    def test_parse_product_impact_from_frontmatter(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing product_impact from YAML frontmatter."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P1-BUG-001-test.md"
        issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-with-product-impact.md"))

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.product_impact is not None
        assert info.product_impact.goal_alignment == "automation"
        assert info.product_impact.persona_impact == "developer"
        assert info.product_impact.business_value == "high"
        assert info.product_impact.user_benefit == "Faster issue processing"

    def test_parse_no_product_impact(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing issue without product impact."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P1-BUG-002-test.md"
        issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-no-product-impact.md"))

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.product_impact is None

    def test_parse_product_impact_null_values(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing frontmatter with null product fields."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P1-BUG-003-test.md"
        issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-null-product-fields.md"))

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        # When all fields are null, product_impact should be None
        assert info.product_impact is None

    def test_read_content_unreadable_file_logs_warning(
        self, temp_project_dir: Path, sample_config: dict[str, Any], caplog: Any
    ) -> None:
        """Test that _read_content logs a warning when a file cannot be read."""
        import logging
        import os

        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P1-BUG-999-unreadable.md"
        issue_file.write_text("# BUG-999: Unreadable\n")
        os.chmod(issue_file, 0o000)

        parser = IssueParser(config)
        try:
            with caplog.at_level(logging.WARNING, logger="little_loops.issue_parser"):
                content = parser._read_content(issue_file)
        finally:
            os.chmod(issue_file, 0o644)

        assert content == ""
        assert any("P1-BUG-999-unreadable.md" in record.message for record in caplog.records)


class TestGetNextIssueNumber:
    """Tests for get_next_issue_number function.

    Issue numbers are globally unique across ALL issue types (BUG, FEAT, ENH).
    """

    def test_empty_directories(self, temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
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

    def test_includes_deferred_issues(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test that deferred issues are considered for ID uniqueness."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        deferred_dir = temp_project_dir / ".issues" / "deferred"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        deferred_dir.mkdir(parents=True, exist_ok=True)

        (bugs_dir / "P0-BUG-003-current.md").write_text("# BUG-003")
        (deferred_dir / "P0-FEAT-020-parked.md").write_text("# FEAT-020")

        next_num = get_next_issue_number(config, "bugs")
        assert next_num == 21  # Max in deferred is 20

    def test_global_uniqueness_across_types(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test that issue numbers are globally unique across all types."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        features_dir = temp_project_dir / ".issues" / "features"
        completed_dir = temp_project_dir / ".issues" / "completed"
        bugs_dir.mkdir(parents=True)
        features_dir.mkdir(parents=True)
        completed_dir.mkdir(parents=True)

        # Create issues of different types with various numbers
        (bugs_dir / "P0-BUG-003-bug.md").write_text("# BUG-003")
        (features_dir / "P2-FEAT-007-feature.md").write_text("# FEAT-007")
        (completed_dir / "P1-ENH-005-enhancement.md").write_text("# ENH-005")

        # Next number should be 8 (max across all types is 7 from FEAT-007)
        next_num = get_next_issue_number(config, "bugs")
        assert next_num == 8

        # Same result regardless of category parameter
        next_num = get_next_issue_number(config, "features")
        assert next_num == 8

    def test_global_uniqueness_with_higher_in_completed(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test global uniqueness when highest number is in completed with different type."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        completed_dir = temp_project_dir / ".issues" / "completed"
        bugs_dir.mkdir(parents=True)
        completed_dir.mkdir(parents=True)

        # Active bug has number 3
        (bugs_dir / "P0-BUG-003-current.md").write_text("# BUG-003")
        # Completed FEATURE has number 015 (highest)
        (completed_dir / "P2-FEAT-015-done.md").write_text("# FEAT-015")

        # Next number should be 16, even when asking for bugs
        next_num = get_next_issue_number(config, "bugs")
        assert next_num == 16


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
        (bugs_dir / "P1-BUG-101-not-duplicate.md").write_text(
            "# BUG-101: Not Duplicate\n\nContent."
        )

        issues = find_issues(config, category="bugs")

        # Should only find the non-duplicate issue
        issue_ids = [i.issue_id for i in issues]
        assert "BUG-100" not in issue_ids
        assert "BUG-101" in issue_ids
        assert len(issues) == 1

    def test_find_issues_skips_duplicates_in_deferred(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test that issues already in deferred/ are skipped from active directories."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        deferred_dir = temp_project_dir / ".issues" / "deferred"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        deferred_dir.mkdir(parents=True, exist_ok=True)

        # Create an issue in bugs/ and same file in deferred/
        duplicate_file = "P0-BUG-200-deferred-test.md"
        (bugs_dir / duplicate_file).write_text("# BUG-200: Deferred Test\n\nContent.")
        (deferred_dir / duplicate_file).write_text("# BUG-200: Deferred Test\n\nContent.")

        # Create a non-duplicate issue
        (bugs_dir / "P1-BUG-201-active.md").write_text("# BUG-201: Active\n\nContent.")

        issues = find_issues(config, category="bugs")

        issue_ids = [i.issue_id for i in issues]
        assert "BUG-200" not in issue_ids
        assert "BUG-201" in issue_ids
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


class TestDependencyParsing:
    """Tests for dependency parsing in IssueParser."""

    def test_parse_blocked_by_single(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing single blocker."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P1-BUG-001-test.md"
        issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-with-blocked-by.md"))

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.blocked_by == ["FEAT-001"]
        assert info.blocks == []

    def test_parse_blocked_by_multiple(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing multiple blockers."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P1-BUG-002-test.md"
        issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-with-multiple-blockers.md"))

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.blocked_by == ["FEAT-001", "FEAT-002", "ENH-003"]
        assert info.blocks == ["BUG-010"]

    def test_parse_blocked_by_empty(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing when no Blocked By section exists."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P1-BUG-003-test.md"
        issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-no-dependencies.md"))

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.blocked_by == []
        assert info.blocks == []

    def test_parse_blocked_by_with_none_text(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing section with 'None' text instead of list."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P1-BUG-004-test.md"
        issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-with-none-blockers.md"))

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.blocked_by == []
        assert info.blocks == []

    def test_parse_blocks_section(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing ## Blocks section."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        features_dir = temp_project_dir / ".issues" / "features"
        features_dir.mkdir(parents=True)
        issue_file = features_dir / "P0-FEAT-001-test.md"
        issue_file.write_text(
            load_fixture(fixtures_dir, "issues", "feature-with-blocks-section.md")
        )

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.blocked_by == []
        assert info.blocks == ["FEAT-002", "FEAT-003", "ENH-001"]

    def test_parse_skips_code_fenced_sections(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test that sections inside code fences are ignored."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        features_dir = temp_project_dir / ".issues" / "features"
        features_dir.mkdir(parents=True)
        issue_file = features_dir / "P2-FEAT-005-test.md"
        issue_file.write_text(load_fixture(fixtures_dir, "issues", "feature-with-code-fence.md"))

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        # Should only get the real dependencies, not the example ones
        assert info.blocked_by == ["REAL-001"]
        assert info.blocks == ["REAL-002"]

    def test_parse_with_asterisk_bullets(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing with asterisk-style bullets."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P1-BUG-006-test.md"
        issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-with-asterisk-bullets.md"))

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.blocked_by == ["FEAT-001", "FEAT-002"]
        assert info.blocks == ["BUG-010"]

    def test_parse_with_trailing_text(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing items with trailing descriptions."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P1-BUG-007-test.md"
        issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-with-trailing-text.md"))

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.blocked_by == ["FEAT-001", "FEAT-002"]
        assert info.blocks == ["ENH-005"]

    def test_parse_blocked_by_bold_markdown(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing blockers with bold markdown formatting."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P3-ENH-001-test.md"
        issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-with-bold-deps.md"))

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.blocked_by == ["ENH-1000", "FEAT-002"]

    def test_dependency_fields_in_serialization(self) -> None:
        """Test that blocked_by and blocks survive to_dict/from_dict roundtrip."""
        original = IssueInfo(
            path=Path("/test/path.md"),
            issue_type="bugs",
            priority="P0",
            issue_id="BUG-100",
            title="Test Bug",
            blocked_by=["FEAT-001", "FEAT-002"],
            blocks=["BUG-101", "BUG-102"],
        )

        data = original.to_dict()

        # Verify dict contains dependency fields
        assert data["blocked_by"] == ["FEAT-001", "FEAT-002"]
        assert data["blocks"] == ["BUG-101", "BUG-102"]

        # Verify roundtrip
        restored = IssueInfo.from_dict(data)
        assert restored.blocked_by == original.blocked_by
        assert restored.blocks == original.blocks

    def test_from_dict_defaults_empty_dependencies(self) -> None:
        """Test from_dict provides empty lists for missing dependency fields."""
        # Simulate old serialized data without dependency fields
        data = {
            "path": "/test/path.md",
            "issue_type": "bugs",
            "priority": "P1",
            "issue_id": "BUG-200",
            "title": "Legacy Issue",
        }

        info = IssueInfo.from_dict(data)

        assert info.blocked_by == []
        assert info.blocks == []
