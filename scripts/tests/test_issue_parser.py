"""Tests for little_loops.issue_parser module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

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

    def test_epic_default_none(self) -> None:
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority="P0",
            issue_id="BUG-001",
            title="Test",
        )
        assert info.epic is None

    def test_epic_in_to_dict(self) -> None:
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
            epic="EPIC-001",
        )
        assert info.to_dict()["epic"] == "EPIC-001"

    def test_epic_from_dict(self) -> None:
        info = IssueInfo.from_dict(
            {
                "path": "/path/to/test.md",
                "issue_type": "bugs",
                "priority": "P1",
                "issue_id": "BUG-001",
                "title": "Test",
                "epic": "EPIC-001",
            }
        )
        assert info.epic == "EPIC-001"

    def test_epic_from_dict_missing(self) -> None:
        info = IssueInfo.from_dict(
            {
                "path": "/path/to/test.md",
                "issue_type": "bugs",
                "priority": "P1",
                "issue_id": "BUG-001",
                "title": "Test",
            }
        )
        assert info.epic is None

    def test_epic_roundtrip(self) -> None:
        """Verify epic survives to_dict → from_dict; catches missing to_dict/from_dict wiring."""
        original = IssueInfo(
            path=Path("/test/path.md"),
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-100",
            title="Test",
            epic="EPIC-042",
        )
        restored = IssueInfo.from_dict(original.to_dict())
        assert restored.epic == "EPIC-042"


class TestIssueParser:
    """Tests for IssueParser class."""

    def test_parse_file_with_priority_and_id(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test parsing a file with priority and ID in filename."""
        # Setup config
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        # Create issue file
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P0-BUG-001-critical.md"
        issue_file.write_text("# BUG-001: Critical Database Crash\n\n## Summary\nDB crashes.")

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.title == "Critical Database Crash"

    def test_parse_file_title_fallback_to_simple_header(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test title extraction falls back to simple header."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P0-BUG-001-test.md"
        issue_file.write_text("# Simple Title\n\nContent without ID in header.")

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.title == "Simple Title"

    def test_parse_file_title_fallback_to_filename(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test title extraction falls back to filename when no header."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P0-BUG-001-no-header.md"
        issue_file.write_text("No markdown header in this file.\n\nJust content.")

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.title == "P0-BUG-001-no-header"  # Filename stem

    def test_parse_feature_issue(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test parsing a feature issue."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        features_dir = temp_project_dir / ".issues" / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        # Create bugs directory with existing issues
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        # Create bugs directory with one existing issue
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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

    def test_parse_file_priority_prefix_without_type_token(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Filenames like P2-9096-foo.md (no type token) must yield BUG-9096, not BUG-2."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P2-9096-eval-specfile-gold-animation-bounce.md"
        issue_file.write_text("# Eval failure\n\nDetails.")

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.priority == "P2"
        assert info.issue_id == "BUG-9096"
        assert info.issue_type == "bugs"

    def test_parse_file_priority_prefix_features_dir(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Priority-prefixed feature filenames pair with the directory-derived prefix."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        features_dir = temp_project_dir / ".issues" / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        issue_file = features_dir / "P3-4242-add-thing.md"
        issue_file.write_text("# Add thing\n")

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.issue_id == "FEAT-4242"
        assert info.issue_type == "features"

    def test_generate_id_strips_priority_prefix(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """_generate_id_from_filename must skip the leading priority token when scanning."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        parser = IssueParser(config)

        # P2-9096-... must yield BUG-9096 (was BUG-2 before the fix).
        assert (
            parser._generate_id_from_filename(
                "P2-9096-eval-specfile-gold-animation-bounce.md", "BUG"
            )
            == "BUG-9096"
        )
        # No priority token: first number still wins.
        assert parser._generate_id_from_filename("9096-eval-specfile-gold.md", "BUG") == "BUG-9096"

    def test_parse_discovered_by_from_frontmatter(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing discovered_by from YAML frontmatter."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P1-BUG-001-test.md"
        issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-with-frontmatter.md"))

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.discovered_by == "scan-codebase"

    def test_parse_file_ignores_captured_at(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
    ) -> None:
        """Test parse_file ignores captured_at frontmatter and still reads discovered_by."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P1-BUG-001-test.md"
        issue_file.write_text(
            "---\ncaptured_at: 2026-04-18T10:30:00Z\ndiscovered_by: capture-issue\n---\n\n# BUG-001: Test\n"
        )

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.discovered_by == "capture-issue"

    def test_parse_no_frontmatter(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        fixtures_dir: Path,
    ) -> None:
        """Test parsing issue without frontmatter."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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

        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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

    def test_parse_epic_from_frontmatter(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
    ) -> None:
        """Test parse_file reads epic: from YAML frontmatter."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P1-BUG-001-test.md"
        issue_file.write_text("---\nepic: EPIC-042\n---\n\n# BUG-001: Test\n")

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.epic == "EPIC-042"

    def test_parse_no_epic(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
    ) -> None:
        """Test parse_file returns None for epic when frontmatter field is absent."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001: Test\n")

        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.epic is None


class TestGetNextIssueNumber:
    """Tests for get_next_issue_number function.

    Issue numbers are globally unique across ALL issue types (BUG, FEAT, ENH).
    """

    def test_empty_directories(self, temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
        """Test with empty issue directories."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        next_num = get_next_issue_number(config, "bugs")
        assert next_num == 1

    def test_with_existing_issues(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test with existing issues in directory."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (bugs_dir / "P0-BUG-001-first.md").write_text("# BUG-001")
        (bugs_dir / "P1-BUG-005-fifth.md").write_text("# BUG-005")
        (bugs_dir / "P2-BUG-003-third.md").write_text("# BUG-003")

        next_num = get_next_issue_number(config, "bugs")
        assert next_num == 6  # Max is 5, so next is 6

    def test_includes_completed_issues(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test that completed issues are considered."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        completed_dir = temp_project_dir / ".issues" / "completed"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        completed_dir.mkdir(parents=True, exist_ok=True)

        (bugs_dir / "P0-BUG-003-current.md").write_text("# BUG-003")
        (completed_dir / "P0-BUG-010-done.md").write_text("# BUG-010")

        next_num = get_next_issue_number(config, "bugs")
        assert next_num == 11  # Max in completed is 10

    def test_includes_deferred_issues(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test that deferred issues are considered for ID uniqueness."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        features_dir = temp_project_dir / ".issues" / "features"
        completed_dir = temp_project_dir / ".issues" / "completed"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        features_dir.mkdir(parents=True, exist_ok=True)
        completed_dir.mkdir(parents=True, exist_ok=True)

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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        completed_dir = temp_project_dir / ".issues" / "completed"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        completed_dir.mkdir(parents=True, exist_ok=True)

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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        issues = find_issues(config)

        assert len(issues) == 5  # 3 bugs + 2 features

    def test_find_issues_by_category(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """Test finding issues filtered by category."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        issues = find_issues(config, category="nonexistent")

        assert len(issues) == 0

    def test_find_issues_skips_status_done(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Issues with ``status: done`` in frontmatter are skipped (post-ENH-1418)."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        (bugs_dir / "P0-BUG-100-done.md").write_text(
            "---\nstatus: done\n---\n\n# BUG-100: Done Test\n\nContent."
        )
        (bugs_dir / "P1-BUG-101-not-done.md").write_text(
            "---\nstatus: open\n---\n\n# BUG-101: Active\n\nContent."
        )

        issues = find_issues(config, category="bugs")

        issue_ids = [i.issue_id for i in issues]
        assert "BUG-100" not in issue_ids
        assert "BUG-101" in issue_ids
        assert len(issues) == 1

    def test_find_issues_skips_status_completed(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Issues with ``status: completed`` in frontmatter are skipped (BUG-1485)."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        (bugs_dir / "P0-BUG-300-completed.md").write_text(
            "---\nstatus: completed\n---\n\n# BUG-300: Completed Test\n\nContent."
        )
        (bugs_dir / "P1-BUG-301-active.md").write_text(
            "---\nstatus: open\n---\n\n# BUG-301: Active\n\nContent."
        )

        issues = find_issues(config, category="bugs")

        issue_ids = [i.issue_id for i in issues]
        assert "BUG-300" not in issue_ids
        assert "BUG-301" in issue_ids
        assert len(issues) == 1

    def test_find_issues_skips_status_deferred(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Issues with ``status: deferred`` in frontmatter are skipped (post-ENH-1418)."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        (bugs_dir / "P0-BUG-200-deferred.md").write_text(
            "---\nstatus: deferred\n---\n\n# BUG-200: Parked\n\nContent."
        )
        (bugs_dir / "P1-BUG-201-active.md").write_text(
            "---\nstatus: open\n---\n\n# BUG-201: Active\n\nContent."
        )

        issues = find_issues(config, category="bugs")

        issue_ids = [i.issue_id for i in issues]
        assert "BUG-200" not in issue_ids
        assert "BUG-201" in issue_ids
        assert len(issues) == 1

    def test_find_issues_status_filter_includes_deferred(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """status_filter={'open','in_progress','blocked','deferred'} includes deferred issues."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        (bugs_dir / "P0-BUG-300-deferred.md").write_text(
            "---\nstatus: deferred\n---\n\n# BUG-300: Parked\n\nContent."
        )
        (bugs_dir / "P1-BUG-301-active.md").write_text(
            "---\nstatus: open\n---\n\n# BUG-301: Active\n\nContent."
        )
        (bugs_dir / "P2-BUG-302-done.md").write_text(
            "---\nstatus: done\n---\n\n# BUG-302: Done\n\nContent."
        )

        issues = find_issues(
            config,
            category="bugs",
            status_filter={"open", "in_progress", "blocked", "deferred"},
        )

        issue_ids = [i.issue_id for i in issues]
        assert "BUG-300" in issue_ids  # deferred now included
        assert "BUG-301" in issue_ids
        assert "BUG-302" not in issue_ids  # done still excluded

    def test_find_issues_status_filter_none_preserves_default(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """status_filter=None (default) must preserve deferred-exclusion behaviour."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        (bugs_dir / "P0-BUG-400-deferred.md").write_text(
            "---\nstatus: deferred\n---\n\n# BUG-400: Parked\n\nContent."
        )
        (bugs_dir / "P1-BUG-401-open.md").write_text("# BUG-401: Open\n\nContent.")

        issues = find_issues(config, category="bugs")  # status_filter=None (default)

        issue_ids = [i.issue_id for i in issues]
        assert "BUG-400" not in issue_ids
        assert "BUG-401" in issue_ids

    def test_find_issues_only_ids_ordered(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """When only_ids is a list, results are returned in list order."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = issues_dir / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        # Create issues with different priorities so priority sort would give a different order
        (bugs_dir / "P3-BUG-010-low.md").write_text("# BUG-010: Low\n\nContent.")
        (bugs_dir / "P1-BUG-020-high.md").write_text("# BUG-020: High\n\nContent.")
        (bugs_dir / "P2-BUG-030-mid.md").write_text("# BUG-030: Mid\n\nContent.")

        # Request in caller-specified order: BUG-010, BUG-030, BUG-020
        issues = find_issues(config, only_ids=["BUG-010", "BUG-030", "BUG-020"])

        issue_ids = [i.issue_id for i in issues]
        assert issue_ids == ["BUG-010", "BUG-030", "BUG-020"]

    def test_find_issues_only_ids_set_uses_priority_sort(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """When only_ids is a set, results are sorted by priority as usual."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = issues_dir / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        (bugs_dir / "P3-BUG-010-low.md").write_text("# BUG-010: Low\n\nContent.")
        (bugs_dir / "P1-BUG-020-high.md").write_text("# BUG-020: High\n\nContent.")

        issues = find_issues(config, only_ids={"BUG-010", "BUG-020"})

        issue_ids = [i.issue_id for i in issues]
        # Priority sort: BUG-020 (P1) before BUG-010 (P3)
        assert issue_ids == ["BUG-020", "BUG-010"]

    def test_find_issues_skip_check_no_dir_globs(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Post-ENH-1418, find_issues must NOT glob completed/ or deferred/ at all.

        Status filtering happens via frontmatter on type-dir files; the legacy
        directory globs (``completed_dir.glob("*.md")`` /
        ``deferred_dir.glob("*.md")``) used for the old skip-check are gone.
        """
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        for i in range(1, 6):
            (bugs_dir / f"P1-BUG-{i:03d}-issue.md").write_text(
                f"---\nstatus: open\n---\n\n# BUG-{i:03d}: Issue\n\nContent."
            )

        real_glob = Path.glob

        def counting_glob(self: Path, pattern: str):  # type: ignore[override]
            return real_glob(self, pattern)

        with patch.object(Path, "glob", autospec=True, side_effect=counting_glob) as mock_glob:
            find_issues(config, category="bugs")

        completed_dir = temp_project_dir / ".issues" / "completed"
        deferred_dir = temp_project_dir / ".issues" / "deferred"
        legacy_dir_globs = [
            c
            for c in mock_glob.call_args_list
            if c.args[1] == "*.md" and c.args[0] in (completed_dir, deferred_dir)
        ]
        assert legacy_dir_globs == [], (
            f"find_issues should not glob legacy completed/ or deferred/ dirs; got {legacy_dir_globs}"
        )

    def test_find_issues_skip_blocked_default_is_byte_identical(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Default skip_blocked=False includes blocked issues (ENH-2436)."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        (bugs_dir / "P0-BUG-500-blocker.md").write_text(
            "---\nstatus: open\n---\n\n# BUG-500: Blocker\n\nContent."
        )
        (bugs_dir / "P0-BUG-501-blocked.md").write_text(
            "---\nstatus: open\nblocked_by:\n  - BUG-500\n---\n\n# BUG-501: Blocked\n\nContent."
        )

        without_flag = find_issues(config, category="bugs")
        with_default_flag = find_issues(config, category="bugs", skip_blocked=False)

        assert [i.issue_id for i in without_flag] == [i.issue_id for i in with_default_flag]
        assert "BUG-501" in [i.issue_id for i in without_flag]

    def test_find_issues_skip_blocked_true_excludes_blocked(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """skip_blocked=True excludes an issue with an unresolved blocker (ENH-2436)."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        (bugs_dir / "P0-BUG-510-blocker.md").write_text(
            "---\nstatus: open\n---\n\n# BUG-510: Blocker\n\nContent."
        )
        (bugs_dir / "P0-BUG-511-blocked.md").write_text(
            "---\nstatus: open\nblocked_by:\n  - BUG-510\n---\n\n# BUG-511: Blocked\n\nContent."
        )

        issues = find_issues(config, category="bugs", skip_blocked=True)

        issue_ids = [i.issue_id for i in issues]
        assert "BUG-511" not in issue_ids
        assert "BUG-510" in issue_ids

    def test_find_issues_skip_blocked_terminal_blocker_unblocks(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """A `done` or `cancelled` blocker does not block (ENH-2436)."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        (bugs_dir / "P0-BUG-520-done-blocker.md").write_text(
            "---\nstatus: done\n---\n\n# BUG-520: Done Blocker\n\nContent."
        )
        (bugs_dir / "P0-BUG-521-unblocked.md").write_text(
            "---\nstatus: open\nblocked_by:\n  - BUG-520\n---\n\n# BUG-521: Unblocked\n\nContent."
        )

        issues = find_issues(config, category="bugs", skip_blocked=True)

        assert "BUG-521" in [i.issue_id for i in issues]

    def test_find_issues_skip_blocked_deferred_blocker_still_blocks(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """A `deferred` blocker is non-terminal and still blocks (ENH-2436)."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        (bugs_dir / "P0-BUG-530-deferred-blocker.md").write_text(
            "---\nstatus: deferred\n---\n\n# BUG-530: Deferred Blocker\n\nContent."
        )
        (bugs_dir / "P0-BUG-531-still-blocked.md").write_text(
            "---\nstatus: open\nblocked_by:\n  - BUG-530\n---\n\n# BUG-531: Still Blocked\n\nContent."
        )

        issues = find_issues(config, category="bugs", skip_blocked=True)

        assert "BUG-531" not in [i.issue_id for i in issues]

    def test_find_issues_skip_blocked_false_byte_identical_for_all_caller_shapes(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """`skip_blocked=False` is byte-identical to omitting the kwarg for every
        kwarg shape the 13 external callers in ENH-2436's Dependent Files section
        use.

        This is the per-implementation-locus breadth sentinel: rather than asserting
        per-caller, it walks every ``(category, type_prefixes, status_filter,
        only_ids, skip_ids)`` shape the 13 callers pass and verifies the
        kwarg-only default keeps each shape byte-identical. If a future change
        to ``find_issues()`` reorders, deduplicates, or re-shuffles status
        filtering for any one of these shapes, this test will fail.
        """
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        features_dir = temp_project_dir / ".issues" / "features"
        features_dir.mkdir(parents=True, exist_ok=True)

        # Terminal blocker — would unblock the issue that depends on it.
        (bugs_dir / "P0-BUG-700-blocker-terminal.md").write_text(
            "---\nstatus: done\n---\n\n# BUG-700: Done blocker.\n\nContent."
        )
        (bugs_dir / "P0-BUG-701-blocked-by-terminal.md").write_text(
            "---\nstatus: open\nblocked_by:\n  - BUG-700\n---\n\n# BUG-701: Blocked by done.\n\nContent."
        )
        # Active blocker — would still block the issue that depends on it.
        (bugs_dir / "P0-BUG-702-blocker-active.md").write_text(
            "---\nstatus: open\n---\n\n# BUG-702: Active blocker.\n\nContent."
        )
        (bugs_dir / "P0-BUG-703-blocked-by-active.md").write_text(
            "---\nstatus: open\nblocked_by:\n  - BUG-702\n---\n\n# BUG-703: Blocked by open.\n\nContent."
        )
        # Plain issues — always present, never blocked.
        (bugs_dir / "P0-BUG-704-plain.md").write_text(
            "---\nstatus: open\n---\n\n# BUG-704: Plain bug.\n\nContent."
        )
        (features_dir / "P0-FEAT-800-plain.md").write_text(
            "---\nstatus: open\n---\n\n# FEAT-800: Plain feature.\n\nContent."
        )

        # Mirror `_ALL_STATUSES` / `_ACTIVE_STATUSES` from
        # `scripts/little_loops/issue_progress.py` (not imported here to keep the
        # test self-contained — the values are stable per the issue_progress
        # module's contract).
        _ALL_STATUSES = frozenset(
            {
                "open",
                "in_progress",
                "blocked",
                "done",
                "cancelled",
                "deferred",
            }
        )
        _ACTIVE_STATUSES = frozenset({"open", "in_progress", "blocked"})

        # Each entry: (description, kwargs). The kwargs mirror how the caller
        # listed in the Dependent Files section of ENH-2436 invokes
        # `find_issues()` — same parameter names, same shape. The default
        # value of any kwarg not passed by the caller is left at the function's
        # own default (None / empty).
        callsite_shapes: list[tuple[str, dict[str, Any]]] = [
            # issue_manager.py:1170 — AutoManager.__init__
            ("issue_manager:1170", {"category": "bugs"}),
            # parallel/priority_queue.py:244 — IssuePriorityQueue.scan_issues
            (
                "priority_queue:244",
                {
                    "category": "bugs",
                    "skip_ids": set(),
                    "only_ids": None,
                    "type_prefixes": None,
                },
            ),
            # hooks/sweep_stale_refs.py:159 — done_issues lookup
            ("sweep_stale_refs:159", {"status_filter": {"done"}}),
            # hooks/sweep_stale_refs.py:166 — open_issues lookup
            ("sweep_stale_refs:166", {}),
            # sprint.py:325 — SprintManager.load_or_resolve
            ("sprint:325", {"status_filter": _ACTIVE_STATUSES}),
            # cli/deps.py:38 — cmd_deps
            ("cli/deps:38", {"only_ids": {"BUG-704", "FEAT-800"}}),
            # cli/deps.py:269 — tree rendering
            ("cli/deps:269", {"status_filter": _ALL_STATUSES}),
            # cli/issues/set_status.py:75 — cmd_set_status
            ("set_status:75", {}),
            # cli/issues/next_action.py:30 — cmd_next_action
            ("next_action:30", {"skip_ids": None}),
            # cli/issues/refine_status.py:281 — cmd_refine_status
            (
                "refine_status:281",
                {"type_prefixes": {"BUG", "FEAT", "ENH"}},
            ),
            # cli/issues/epic_consistency.py:274 — cmd_epic_consistency
            ("epic_consistency:274", {"status_filter": _ALL_STATUSES}),
            # cli/issues/epic_progress.py:53 — cmd_epic_progress
            ("epic_progress:53", {"status_filter": _ALL_STATUSES}),
            # cli/issues/sequence.py:28 — cmd_sequence
            (
                "sequence:28",
                {"type_prefixes": {"BUG", "FEAT", "ENH"}},
            ),
            # cli/issues/clusters.py:311 — cmd_clusters
            ("clusters:311", {"status_filter": {"open", "in_progress"}}),
            # cli/issues/impact_effort.py:188 — cmd_impact_effort
            (
                "impact_effort:188",
                {"type_prefixes": {"BUG", "FEAT", "ENH"}},
            ),
            # cli/issues/list_cmd.py:166 — _find_issues_all
            ("list_cmd:166", {"status_filter": _ALL_STATUSES}),
        ]

        for description, kwargs in callsite_shapes:
            without_kwarg = [i.issue_id for i in find_issues(config, **kwargs)]
            with_explicit_false = [
                i.issue_id for i in find_issues(config, skip_blocked=False, **kwargs)
            ]
            assert without_kwarg == with_explicit_false, (
                f"skip_blocked=False must be byte-identical to omitting the kwarg "
                f"for callsite shape {description!r}; "
                f"without={without_kwarg}, with_false={with_explicit_false}"
            )


class TestFindHighestPriorityIssue:
    """Tests for find_highest_priority_issue function."""

    def test_returns_p0_first(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """Test that P0 issue is returned first."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        highest = find_highest_priority_issue(config)

        assert highest is None

    def test_respects_skip_ids(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """Test that skipped IDs are not returned."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        features_dir = temp_project_dir / ".issues" / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        features_dir = temp_project_dir / ".issues" / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
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

    def test_blocked_by_comma_string_frontmatter(self, tmp_path: Path) -> None:
        """Comma-separated scalar string in blocked_by frontmatter is split into individual IDs."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P3-BUG-1276-test.md"
        issue_file.write_text(
            '---\nblocked_by: "ENH-419, ENH-422, ENH-423"\n---\n# BUG-1276: Test\n'
        )

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.blocked_by == ["ENH-419", "ENH-422", "ENH-423"]

    def test_blocks_comma_string_frontmatter(self, tmp_path: Path) -> None:
        """Comma-separated scalar string in blocks frontmatter is split into individual IDs."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P3-BUG-1276-blocks-test.md"
        issue_file.write_text('---\nblocks: "FEAT-001, FEAT-002"\n---\n# BUG-1276: Test\n')

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.blocks == ["FEAT-001", "FEAT-002"]

    def test_blocked_by_yaml_list_frontmatter_unchanged(self, tmp_path: Path) -> None:
        """Proper YAML list in blocked_by frontmatter continues to work unchanged."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P3-BUG-1276-list-test.md"
        issue_file.write_text("---\nblocked_by:\n  - ENH-419\n  - ENH-422\n---\n# BUG-1276: Test\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.blocked_by == ["ENH-419", "ENH-422"]

    def test_blocked_by_comma_string_whitespace_variants(self, tmp_path: Path) -> None:
        """Comma-separated string with irregular whitespace is stripped correctly."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P3-BUG-1276-ws-test.md"
        issue_file.write_text('---\nblocked_by: "  ENH-419 ,  ENH-422  "\n---\n# BUG-1276: Test\n')

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.blocked_by == ["ENH-419", "ENH-422"]

    def test_parse_parent_from_frontmatter(self, tmp_path: Path) -> None:
        """parent: frontmatter key is parsed into IssueInfo.parent."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P2-ENH-001-test.md"
        issue_file.write_text("---\nparent: EPIC-10\n---\n# ENH-001: Test\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.parent == "EPIC-10"

    def test_parse_parent_issue_alias_emits_warning(self, tmp_path: Path, caplog: Any) -> None:
        """Deprecated parent_issue: alias populates parent and emits a warning."""
        import json
        import logging

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P2-ENH-002-test.md"
        issue_file.write_text("---\nparent_issue: EPIC-20\n---\n# ENH-002: Test\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        with caplog.at_level(logging.WARNING, logger="little_loops.issue_parser"):
            info = parser.parse_file(issue_file)

        assert info.parent == "EPIC-20"
        assert any("parent_issue" in r.message for r in caplog.records)
        assert any("deprecated" in r.message for r in caplog.records)

    def test_parse_depends_on_from_frontmatter(self, tmp_path: Path) -> None:
        """depends_on: YAML list in frontmatter is parsed into IssueInfo.depends_on."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P2-ENH-003-test.md"
        issue_file.write_text("---\ndepends_on:\n  - ENH-100\n  - ENH-101\n---\n# ENH-003: Test\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.depends_on == ["ENH-100", "ENH-101"]

    def test_parse_relates_to_from_frontmatter(self, tmp_path: Path) -> None:
        """relates_to: YAML list in frontmatter is parsed into IssueInfo.relates_to."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P2-ENH-004-test.md"
        issue_file.write_text("---\nrelates_to:\n  - FEAT-50\n  - BUG-99\n---\n# ENH-004: Test\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.relates_to == ["FEAT-50", "BUG-99"]

    def test_parse_related_alias_emits_warning(self, tmp_path: Path, caplog: Any) -> None:
        """Deprecated related: alias populates relates_to and emits a warning."""
        import json
        import logging

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P2-ENH-005-test.md"
        issue_file.write_text("---\nrelated:\n  - FEAT-30\n  - BUG-40\n---\n# ENH-005: Test\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        with caplog.at_level(logging.WARNING, logger="little_loops.issue_parser"):
            info = parser.parse_file(issue_file)

        assert info.relates_to == ["FEAT-30", "BUG-40"]
        assert any("related" in r.message for r in caplog.records)
        assert any("deprecated" in r.message for r in caplog.records)

    def test_parse_duplicate_of_from_frontmatter(self, tmp_path: Path) -> None:
        """duplicate_of: frontmatter key is parsed into IssueInfo.duplicate_of."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P3-BUG-006-test.md"
        issue_file.write_text("---\nduplicate_of: BUG-001\n---\n# BUG-006: Test\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.duplicate_of == "BUG-001"

    def test_new_relationship_fields_default_to_empty(self) -> None:
        """New relationship fields default to None/empty list when absent."""
        info = IssueInfo(
            path=Path("/test/path.md"),
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-007",
            title="Test",
        )
        assert info.parent is None
        assert info.depends_on == []
        assert info.relates_to == []
        assert info.duplicate_of is None

    def test_new_relationship_fields_roundtrip_serialization(self) -> None:
        """New relationship fields survive to_dict/from_dict roundtrip."""
        original = IssueInfo(
            path=Path("/test/path.md"),
            issue_type="enhancements",
            priority="P2",
            issue_id="ENH-008",
            title="Test",
            parent="EPIC-1",
            depends_on=["ENH-5", "ENH-6"],
            relates_to=["FEAT-10"],
            duplicate_of="ENH-3",
        )

        data = original.to_dict()

        assert data["parent"] == "EPIC-1"
        assert data["depends_on"] == ["ENH-5", "ENH-6"]
        assert data["relates_to"] == ["FEAT-10"]
        assert data["duplicate_of"] == "ENH-3"

        restored = IssueInfo.from_dict(data)
        assert restored.parent == original.parent
        assert restored.depends_on == original.depends_on
        assert restored.relates_to == original.relates_to
        assert restored.duplicate_of == original.duplicate_of

    def test_from_dict_defaults_empty_new_relationship_fields(self) -> None:
        """from_dict provides correct defaults for missing new relationship fields."""
        data = {
            "path": "/test/path.md",
            "issue_type": "bugs",
            "priority": "P1",
            "issue_id": "BUG-009",
            "title": "Legacy Issue",
        }
        info = IssueInfo.from_dict(data)

        assert info.parent is None
        assert info.depends_on == []
        assert info.relates_to == []
        assert info.duplicate_of is None
        assert info.milestone is None


class TestIssueInfoTestable:
    """Tests for IssueInfo.testable field."""

    def test_testable_default_none(self) -> None:
        """Test testable defaults to None when not provided."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P4",
            issue_id="ENH-801",
            title="Test",
        )
        assert info.testable is None

    def test_testable_false(self) -> None:
        """Test testable can be set to False."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P4",
            issue_id="ENH-801",
            title="Test",
            testable=False,
        )
        assert info.testable is False

    def test_testable_true(self) -> None:
        """Test testable can be set to True."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P4",
            issue_id="ENH-801",
            title="Test",
            testable=True,
        )
        assert info.testable is True

    def test_testable_in_to_dict(self) -> None:
        """Test testable appears in to_dict output."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P4",
            issue_id="ENH-801",
            title="Test",
            testable=False,
        )
        data = info.to_dict()
        assert data["testable"] is False

    def test_testable_from_dict_missing(self) -> None:
        """Test from_dict defaults to None when testable key is absent."""
        data = {
            "path": "/test/path.md",
            "issue_type": "enhancements",
            "priority": "P4",
            "issue_id": "ENH-801",
            "title": "Test Issue",
        }
        info = IssueInfo.from_dict(data)
        assert info.testable is None

    def test_testable_from_dict_false(self) -> None:
        """Test from_dict restores testable=False."""
        data = {
            "path": "/test/path.md",
            "issue_type": "enhancements",
            "priority": "P4",
            "issue_id": "ENH-801",
            "title": "Test Issue",
            "testable": False,
        }
        info = IssueInfo.from_dict(data)
        assert info.testable is False

    def test_parse_file_testable_false(self, tmp_path: Path) -> None:
        """Integration: parse_file reads testable: false from frontmatter."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "issues": {"base_dir": ".issues"},
                    "project": {"src_dir": "scripts/"},
                }
            )
        )
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P1-BUG-999-no-test.md"
        issue_file.write_text("---\ntestable: false\n---\n# BUG-999: No Test\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.testable is False

    def test_parse_file_testable_absent(self, tmp_path: Path) -> None:
        """Integration: parse_file yields testable=None when frontmatter key absent."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "issues": {"base_dir": ".issues"},
                    "project": {"src_dir": "scripts/"},
                }
            )
        )
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P1-BUG-998-normal.md"
        issue_file.write_text("---\ndiscovered_by: scan-codebase\n---\n# BUG-998: Normal\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.testable is None


class TestIssueInfoDecisionNeeded:
    """Tests for IssueInfo.decision_needed field."""

    def test_decision_needed_default_none(self) -> None:
        """Test decision_needed defaults to None when not provided."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1239",
            title="Test",
        )
        assert info.decision_needed is None

    def test_decision_needed_false(self) -> None:
        """Test decision_needed can be set to False."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1239",
            title="Test",
            decision_needed=False,
        )
        assert info.decision_needed is False

    def test_decision_needed_true(self) -> None:
        """Test decision_needed can be set to True."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1239",
            title="Test",
            decision_needed=True,
        )
        assert info.decision_needed is True

    def test_decision_needed_in_to_dict(self) -> None:
        """Test decision_needed appears in to_dict output."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1239",
            title="Test",
            decision_needed=True,
        )
        data = info.to_dict()
        assert data["decision_needed"] is True

    def test_decision_needed_from_dict_missing(self) -> None:
        """Test from_dict defaults to None when decision_needed key is absent."""
        data = {
            "path": "/test/path.md",
            "issue_type": "enhancements",
            "priority": "P3",
            "issue_id": "ENH-1239",
            "title": "Test Issue",
        }
        info = IssueInfo.from_dict(data)
        assert info.decision_needed is None

    def test_decision_needed_from_dict_false(self) -> None:
        """Test from_dict restores decision_needed=False."""
        data = {
            "path": "/test/path.md",
            "issue_type": "enhancements",
            "priority": "P3",
            "issue_id": "ENH-1239",
            "title": "Test Issue",
            "decision_needed": False,
        }
        info = IssueInfo.from_dict(data)
        assert info.decision_needed is False

    def test_parse_file_decision_needed_true(self, tmp_path: Path) -> None:
        """Integration: parse_file reads decision_needed: true from frontmatter."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "issues": {"base_dir": ".issues"},
                    "project": {"src_dir": "scripts/"},
                }
            )
        )
        features_dir = tmp_path / ".issues" / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        issue_file = features_dir / "P3-FEAT-1239-decide-needed.md"
        issue_file.write_text("---\ndecision_needed: true\n---\n# FEAT-1239: Decide Needed\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.decision_needed is True

    def test_parse_file_decision_needed_absent(self, tmp_path: Path) -> None:
        """Integration: parse_file yields decision_needed=None when frontmatter key absent."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "issues": {"base_dir": ".issues"},
                    "project": {"src_dir": "scripts/"},
                }
            )
        )
        features_dir = tmp_path / ".issues" / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        issue_file = features_dir / "P3-FEAT-1238-normal.md"
        issue_file.write_text("---\ndiscovered_by: scan-codebase\n---\n# FEAT-1238: Normal\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.decision_needed is None


class TestIssueInfoLearningTestsRequired:
    """Tests for IssueInfo.learning_tests_required field."""

    def test_learning_tests_required_default_none(self) -> None:
        """Test learning_tests_required defaults to None when not provided."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1284",
            title="Test",
        )
        assert info.learning_tests_required is None

    def test_learning_tests_required_empty_list(self) -> None:
        """Test learning_tests_required can be set to an empty list."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1284",
            title="Test",
            learning_tests_required=[],
        )
        assert info.learning_tests_required == []

    def test_learning_tests_required_with_targets(self) -> None:
        """Test learning_tests_required can hold a list of target strings."""
        targets = ["Anthropic SDK streaming", "GitHub pagination"]
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1284",
            title="Test",
            learning_tests_required=targets,
        )
        assert info.learning_tests_required == targets

    def test_learning_tests_required_in_to_dict(self) -> None:
        """Test learning_tests_required appears in to_dict output."""
        targets = ["Anthropic SDK streaming"]
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1284",
            title="Test",
            learning_tests_required=targets,
        )
        data = info.to_dict()
        assert data["learning_tests_required"] == targets

    def test_learning_tests_required_from_dict_missing(self) -> None:
        """Test from_dict defaults to None when learning_tests_required key is absent."""
        data = {
            "path": "/test/path.md",
            "issue_type": "enhancements",
            "priority": "P3",
            "issue_id": "ENH-1284",
            "title": "Test Issue",
        }
        info = IssueInfo.from_dict(data)
        assert info.learning_tests_required is None

    def test_learning_tests_required_from_dict_with_value(self) -> None:
        """Test from_dict restores learning_tests_required list."""
        targets = ["target-a", "target-b"]
        data = {
            "path": "/test/path.md",
            "issue_type": "enhancements",
            "priority": "P3",
            "issue_id": "ENH-1284",
            "title": "Test Issue",
            "learning_tests_required": targets,
        }
        info = IssueInfo.from_dict(data)
        assert info.learning_tests_required == targets

    def test_parse_file_learning_tests_required_yaml_list(self, tmp_path: Path) -> None:
        """Integration: parse_file reads learning_tests_required YAML list from frontmatter."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "issues": {"base_dir": ".issues"},
                    "project": {"src_dir": "scripts/"},
                }
            )
        )
        features_dir = tmp_path / ".issues" / "enhancements"
        features_dir.mkdir(parents=True, exist_ok=True)
        issue_file = features_dir / "P4-ENH-1284-lt-gate.md"
        issue_file.write_text(
            "---\nlearning_tests_required:\n  - Anthropic SDK streaming\n---\n# ENH-1284: LT Gate\n"
        )

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.learning_tests_required == ["Anthropic SDK streaming"]

    def test_parse_file_learning_tests_required_comma_string(self, tmp_path: Path) -> None:
        """Integration: parse_file splits comma-separated scalar string into list."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "issues": {"base_dir": ".issues"},
                    "project": {"src_dir": "scripts/"},
                }
            )
        )
        features_dir = tmp_path / ".issues" / "enhancements"
        features_dir.mkdir(parents=True, exist_ok=True)
        issue_file = features_dir / "P4-ENH-1285-lt-gate.md"
        issue_file.write_text(
            "---\nlearning_tests_required: 'Anthropic SDK streaming, GitHub pagination'\n---\n# ENH-1285: LT Gate\n"
        )

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.learning_tests_required == ["Anthropic SDK streaming", "GitHub pagination"]

    def test_parse_file_learning_tests_required_absent(self, tmp_path: Path) -> None:
        """Integration: parse_file yields learning_tests_required=None when frontmatter key absent."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "issues": {"base_dir": ".issues"},
                    "project": {"src_dir": "scripts/"},
                }
            )
        )
        features_dir = tmp_path / ".issues" / "enhancements"
        features_dir.mkdir(parents=True, exist_ok=True)
        issue_file = features_dir / "P4-ENH-1286-normal.md"
        issue_file.write_text("---\ndiscovered_by: scan-codebase\n---\n# ENH-1286: Normal\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.learning_tests_required is None


class TestIssueInfoMissingArtifacts:
    """Tests for IssueInfo.missing_artifacts field."""

    def test_missing_artifacts_default_none(self) -> None:
        """Test missing_artifacts defaults to None when not provided."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1291",
            title="Test",
        )
        assert info.missing_artifacts is None

    def test_missing_artifacts_false(self) -> None:
        """Test missing_artifacts can be set to False."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1291",
            title="Test",
            missing_artifacts=False,
        )
        assert info.missing_artifacts is False

    def test_missing_artifacts_true(self) -> None:
        """Test missing_artifacts can be set to True."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1291",
            title="Test",
            missing_artifacts=True,
        )
        assert info.missing_artifacts is True

    def test_missing_artifacts_in_to_dict(self) -> None:
        """Test missing_artifacts appears in to_dict output."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1291",
            title="Test",
            missing_artifacts=True,
        )
        data = info.to_dict()
        assert data["missing_artifacts"] is True

    def test_missing_artifacts_from_dict_missing(self) -> None:
        """Test from_dict defaults to None when missing_artifacts key is absent."""
        data = {
            "path": "/test/path.md",
            "issue_type": "enhancements",
            "priority": "P3",
            "issue_id": "ENH-1291",
            "title": "Test Issue",
        }
        info = IssueInfo.from_dict(data)
        assert info.missing_artifacts is None

    def test_missing_artifacts_from_dict_false(self) -> None:
        """Test from_dict restores missing_artifacts=False."""
        data = {
            "path": "/test/path.md",
            "issue_type": "enhancements",
            "priority": "P3",
            "issue_id": "ENH-1291",
            "title": "Test Issue",
            "missing_artifacts": False,
        }
        info = IssueInfo.from_dict(data)
        assert info.missing_artifacts is False

    def test_parse_file_missing_artifacts_true(self, tmp_path: Path) -> None:
        """Integration: parse_file reads missing_artifacts: true from frontmatter."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "issues": {"base_dir": ".issues"},
                    "project": {"src_dir": "scripts/"},
                }
            )
        )
        features_dir = tmp_path / ".issues" / "enhancements"
        features_dir.mkdir(parents=True, exist_ok=True)
        issue_file = features_dir / "P3-ENH-1291-missing-artifacts.md"
        issue_file.write_text("---\nmissing_artifacts: true\n---\n# ENH-1291: Missing Artifacts\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.missing_artifacts is True

    def test_parse_file_missing_artifacts_absent(self, tmp_path: Path) -> None:
        """Integration: parse_file yields missing_artifacts=None when frontmatter key absent."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "issues": {"base_dir": ".issues"},
                    "project": {"src_dir": "scripts/"},
                }
            )
        )
        features_dir = tmp_path / ".issues" / "enhancements"
        features_dir.mkdir(parents=True, exist_ok=True)
        issue_file = features_dir / "P3-ENH-1292-normal.md"
        issue_file.write_text("---\ndiscovered_by: scan-codebase\n---\n# ENH-1292: Normal\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.missing_artifacts is None


class TestIssueInfoImplementationOrderRisk:
    """Tests for IssueInfo.implementation_order_risk field (ENH-1492)."""

    def test_implementation_order_risk_default_none(self) -> None:
        """implementation_order_risk defaults to None when not provided."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="ENH",
            priority="P3",
            issue_id="ENH-1492",
            title="Test",
        )
        assert info.implementation_order_risk is None

    def test_implementation_order_risk_false(self) -> None:
        """implementation_order_risk can be set to False."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="ENH",
            priority="P3",
            issue_id="ENH-1492",
            title="Test",
            implementation_order_risk=False,
        )
        assert info.implementation_order_risk is False

    def test_implementation_order_risk_true(self) -> None:
        """implementation_order_risk can be set to True."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="ENH",
            priority="P3",
            issue_id="ENH-1492",
            title="Test",
            implementation_order_risk=True,
        )
        assert info.implementation_order_risk is True

    def test_implementation_order_risk_in_to_dict(self) -> None:
        """to_dict() includes implementation_order_risk."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="ENH",
            priority="P3",
            issue_id="ENH-1492",
            title="Test",
            implementation_order_risk=True,
        )
        data = info.to_dict()
        assert data["implementation_order_risk"] is True

    def test_implementation_order_risk_from_dict_missing(self) -> None:
        """from_dict() yields None when key is absent."""
        data = {
            "path": "test.md",
            "issue_type": "ENH",
            "priority": "P3",
            "issue_id": "ENH-1492",
            "title": "Test",
        }
        info = IssueInfo.from_dict(data)
        assert info.implementation_order_risk is None

    def test_implementation_order_risk_from_dict_false(self) -> None:
        """from_dict() round-trips False."""
        data = {
            "path": "test.md",
            "issue_type": "ENH",
            "priority": "P3",
            "issue_id": "ENH-1492",
            "title": "Test",
            "implementation_order_risk": False,
        }
        info = IssueInfo.from_dict(data)
        assert info.implementation_order_risk is False

    def test_parse_file_implementation_order_risk_true(self, tmp_path: Path) -> None:
        """Integration: parse_file yields implementation_order_risk=True from frontmatter."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "issues": {"base_dir": ".issues"},
                    "project": {"src_dir": "scripts/"},
                }
            )
        )
        features_dir = tmp_path / ".issues" / "enhancements"
        features_dir.mkdir(parents=True, exist_ok=True)
        issue_file = features_dir / "P3-ENH-1492-order-risk.md"
        issue_file.write_text("---\nimplementation_order_risk: true\n---\n# ENH-1492: Order risk\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.implementation_order_risk is True

    def test_parse_file_implementation_order_risk_absent(self, tmp_path: Path) -> None:
        """Integration: parse_file yields implementation_order_risk=None when frontmatter key absent."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "issues": {"base_dir": ".issues"},
                    "project": {"src_dir": "scripts/"},
                }
            )
        )
        features_dir = tmp_path / ".issues" / "enhancements"
        features_dir.mkdir(parents=True, exist_ok=True)
        issue_file = features_dir / "P3-ENH-1493-normal.md"
        issue_file.write_text("---\ndiscovered_by: scan-codebase\n---\n# ENH-1493: Normal\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.implementation_order_risk is None


class TestIssueInfoSize:
    """Tests for IssueInfo.size field."""

    def test_size_default_none(self) -> None:
        """Test size defaults to None when not provided."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1091",
            title="Test",
        )
        assert info.size is None

    def test_size_value(self) -> None:
        """Test size can be set to a valid value."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1091",
            title="Test",
            size="Large",
        )
        assert info.size == "Large"

    def test_size_very_large(self) -> None:
        """Test size can hold 'Very Large' (10 chars, max valid value)."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1091",
            title="Test",
            size="Very Large",
        )
        assert info.size == "Very Large"

    def test_size_in_to_dict(self) -> None:
        """Test size appears in to_dict output."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1091",
            title="Test",
            size="Medium",
        )
        data = info.to_dict()
        assert data["size"] == "Medium"

    def test_size_none_in_to_dict(self) -> None:
        """Test size=None is preserved in to_dict output."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1091",
            title="Test",
        )
        data = info.to_dict()
        assert data["size"] is None

    def test_size_from_dict(self) -> None:
        """Test size is restored from dict."""
        data = {
            "path": "/test/path.md",
            "issue_type": "enhancements",
            "priority": "P3",
            "issue_id": "ENH-1091",
            "title": "Test Issue",
            "size": "Small",
        }
        info = IssueInfo.from_dict(data)
        assert info.size == "Small"

    def test_size_from_dict_missing(self) -> None:
        """Test from_dict defaults to None when size key is absent."""
        data = {
            "path": "/test/path.md",
            "issue_type": "enhancements",
            "priority": "P3",
            "issue_id": "ENH-1091",
            "title": "Test Issue",
        }
        info = IssueInfo.from_dict(data)
        assert info.size is None

    def test_parse_file_size_present(self, tmp_path: Path) -> None:
        """Integration: parse_file reads size from frontmatter."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "issues": {"base_dir": ".issues"},
                    "project": {"src_dir": "scripts/"},
                }
            )
        )
        enhancements_dir = tmp_path / ".issues" / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        issue_file = enhancements_dir / "P3-ENH-1091-size-test.md"
        issue_file.write_text("---\nsize: Very Large\n---\n# ENH-1091: Size Test\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.size == "Very Large"

    def test_parse_file_size_absent(self, tmp_path: Path) -> None:
        """Integration: parse_file yields size=None when frontmatter key absent."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "issues": {"base_dir": ".issues"},
                    "project": {"src_dir": "scripts/"},
                }
            )
        )
        enhancements_dir = tmp_path / ".issues" / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        issue_file = enhancements_dir / "P3-ENH-1092-no-size.md"
        issue_file.write_text("---\ndiscovered_by: scan-codebase\n---\n# ENH-1092: No Size\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.size is None


class TestIssueInfoScoreDimensions:
    """Tests for IssueInfo score dimension fields (score_complexity, score_test_coverage,
    score_ambiguity, score_change_surface)."""

    def test_score_dimensions_default_none(self) -> None:
        """All four dimension fields default to None when not provided."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1099",
            title="Test",
        )
        assert info.score_complexity is None
        assert info.score_test_coverage is None
        assert info.score_ambiguity is None
        assert info.score_change_surface is None

    def test_score_dimensions_values(self) -> None:
        """All four dimension fields can be set to integer values."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1099",
            title="Test",
            score_complexity=20,
            score_test_coverage=18,
            score_ambiguity=22,
            score_change_surface=12,
        )
        assert info.score_complexity == 20
        assert info.score_test_coverage == 18
        assert info.score_ambiguity == 22
        assert info.score_change_surface == 12

    def test_score_dimensions_in_to_dict(self) -> None:
        """All four dimension fields appear in to_dict output."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1099",
            title="Test",
            score_complexity=20,
            score_test_coverage=18,
            score_ambiguity=22,
            score_change_surface=12,
        )
        data = info.to_dict()
        assert data["score_complexity"] == 20
        assert data["score_test_coverage"] == 18
        assert data["score_ambiguity"] == 22
        assert data["score_change_surface"] == 12

    def test_score_dimensions_none_in_to_dict(self) -> None:
        """None dimension fields are preserved as None in to_dict output."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-1099",
            title="Test",
        )
        data = info.to_dict()
        assert data["score_complexity"] is None
        assert data["score_test_coverage"] is None
        assert data["score_ambiguity"] is None
        assert data["score_change_surface"] is None

    def test_score_dimensions_from_dict(self) -> None:
        """All four dimension fields are restored from dict."""
        data = {
            "path": "/test/path.md",
            "issue_type": "enhancements",
            "priority": "P3",
            "issue_id": "ENH-1099",
            "title": "Test Issue",
            "score_complexity": 20,
            "score_test_coverage": 18,
            "score_ambiguity": 22,
            "score_change_surface": 12,
        }
        info = IssueInfo.from_dict(data)
        assert info.score_complexity == 20
        assert info.score_test_coverage == 18
        assert info.score_ambiguity == 22
        assert info.score_change_surface == 12

    def test_score_dimensions_from_dict_missing(self) -> None:
        """from_dict defaults all four fields to None when keys are absent."""
        data = {
            "path": "/test/path.md",
            "issue_type": "enhancements",
            "priority": "P3",
            "issue_id": "ENH-1099",
            "title": "Test Issue",
        }
        info = IssueInfo.from_dict(data)
        assert info.score_complexity is None
        assert info.score_test_coverage is None
        assert info.score_ambiguity is None
        assert info.score_change_surface is None

    def test_parse_file_score_dimensions_present(self, tmp_path: Path) -> None:
        """Integration: parse_file reads all four dimension scores from frontmatter."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "issues": {"base_dir": ".issues"},
                    "project": {"src_dir": "scripts/"},
                }
            )
        )
        enhancements_dir = tmp_path / ".issues" / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        issue_file = enhancements_dir / "P3-ENH-1099-dims-test.md"
        issue_file.write_text(
            "---\n"
            "score_complexity: 20\n"
            "score_test_coverage: 18\n"
            "score_ambiguity: 22\n"
            "score_change_surface: 12\n"
            "---\n"
            "# ENH-1099: Dimension Test\n"
        )

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.score_complexity == 20
        assert info.score_test_coverage == 18
        assert info.score_ambiguity == 22
        assert info.score_change_surface == 12

    def test_parse_file_score_dimensions_absent(self, tmp_path: Path) -> None:
        """Integration: parse_file yields None for all four fields when absent."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "issues": {"base_dir": ".issues"},
                    "project": {"src_dir": "scripts/"},
                }
            )
        )
        enhancements_dir = tmp_path / ".issues" / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        issue_file = enhancements_dir / "P3-ENH-1100-no-dims.md"
        issue_file.write_text("---\ndiscovered_by: scan-codebase\n---\n# ENH-1100: No Dimensions\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.score_complexity is None
        assert info.score_test_coverage is None
        assert info.score_ambiguity is None
        assert info.score_change_surface is None


class TestIssueInfoStatus:
    """Tests for IssueInfo.status field."""

    def test_status_default_open(self) -> None:
        """IssueInfo without status kwarg defaults to 'open'."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P2",
            issue_id="ENH-1417",
            title="Test",
        )
        assert info.status == "open"

    def test_status_value(self) -> None:
        """IssueInfo accepts an explicit status value."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P2",
            issue_id="ENH-1417",
            title="Test",
            status="blocked",
        )
        assert info.status == "blocked"

    def test_status_in_to_dict(self) -> None:
        """to_dict() includes 'status' key."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="enhancements",
            priority="P2",
            issue_id="ENH-1417",
            title="Test",
            status="in_progress",
        )
        assert info.to_dict()["status"] == "in_progress"

    def test_status_from_dict(self) -> None:
        """from_dict() restores an explicit status value."""
        info = IssueInfo.from_dict(
            {
                "path": "/path/to/test.md",
                "issue_type": "enhancements",
                "priority": "P2",
                "issue_id": "ENH-1417",
                "title": "Test",
                "status": "blocked",
            }
        )
        assert info.status == "blocked"

    def test_status_from_dict_missing(self) -> None:
        """from_dict() defaults to 'open' when status key is absent."""
        info = IssueInfo.from_dict(
            {
                "path": "/path/to/test.md",
                "issue_type": "enhancements",
                "priority": "P2",
                "issue_id": "ENH-1417",
                "title": "Test",
            }
        )
        assert info.status == "open"

    def test_status_roundtrip(self) -> None:
        """from_dict(to_dict()) preserves status value."""
        original = IssueInfo(
            path=Path("/test/path.md"),
            issue_type="enhancements",
            priority="P2",
            issue_id="ENH-1417",
            title="Test",
            status="done",
        )
        restored = IssueInfo.from_dict(original.to_dict())
        assert restored.status == "done"

    def test_parse_file_status_from_frontmatter(self, tmp_path: Path) -> None:
        """Integration: parse_file() reads status: key from frontmatter."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        enhancements_dir = tmp_path / ".issues" / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        issue_file = enhancements_dir / "P2-ENH-1417-status-test.md"
        issue_file.write_text("---\nstatus: blocked\n---\n# ENH-1417: Status Test\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.status == "blocked"

    def test_parse_file_status_default_open(self, tmp_path: Path) -> None:
        """Integration: parse_file() defaults to 'open' when status key is absent."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        enhancements_dir = tmp_path / ".issues" / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        issue_file = enhancements_dir / "P2-ENH-1417-no-status.md"
        issue_file.write_text("---\ndiscovered_by: scan-codebase\n---\n# ENH-1417: No Status\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.status == "open"

    def test_parse_labels_from_frontmatter(self, tmp_path: Path) -> None:
        """labels: YAML list in frontmatter is parsed into IssueInfo.labels."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        enhancements_dir = tmp_path / ".issues" / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        issue_file = enhancements_dir / "P3-ENH-1392-test.md"
        issue_file.write_text(
            "---\nlabels:\n  - fsm\n  - cli\n  - quick-win\n---\n# ENH-1392: Test\n"
        )

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.labels == ["fsm", "cli", "quick-win"]

    def test_parse_labels_absent(self, tmp_path: Path) -> None:
        """IssueInfo.labels defaults to empty list when labels: field is absent."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        enhancements_dir = tmp_path / ".issues" / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        issue_file = enhancements_dir / "P3-ENH-1392-no-labels.md"
        issue_file.write_text("---\ndiscovered_by: scan\n---\n# ENH-1392: No Labels\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.labels == []

    def test_parse_labels_empty_list(self, tmp_path: Path) -> None:
        """labels: [] in frontmatter yields IssueInfo.labels == []."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        enhancements_dir = tmp_path / ".issues" / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        issue_file = enhancements_dir / "P3-ENH-1392-empty-labels.md"
        issue_file.write_text("---\nlabels: []\n---\n# ENH-1392: Empty Labels\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.labels == []


class TestIssueInfoMilestone:
    """Tests for IssueInfo.milestone field."""

    def test_parse_milestone_from_frontmatter(self, tmp_path: Path) -> None:
        """milestone: string in frontmatter is parsed into IssueInfo.milestone."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        enhancements_dir = tmp_path / ".issues" / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        issue_file = enhancements_dir / "P3-ENH-1393-test.md"
        issue_file.write_text("---\nmilestone: sprint-2026-q2\n---\n# ENH-1393: Test\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.milestone == "sprint-2026-q2"

    def test_parse_milestone_absent(self, tmp_path: Path) -> None:
        """IssueInfo.milestone defaults to None when milestone: field is absent."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        enhancements_dir = tmp_path / ".issues" / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        issue_file = enhancements_dir / "P3-ENH-1393-no-milestone.md"
        issue_file.write_text("---\ndiscovered_by: scan\n---\n# ENH-1393: No Milestone\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.milestone is None

    def test_parse_milestone_explicit_null(self, tmp_path: Path) -> None:
        """milestone: null in frontmatter yields IssueInfo.milestone == None."""
        import json

        from little_loops.config import BRConfig

        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"issues": {"base_dir": ".issues"}, "project": {"src_dir": "scripts/"}})
        )
        enhancements_dir = tmp_path / ".issues" / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        issue_file = enhancements_dir / "P3-ENH-1393-null-milestone.md"
        issue_file.write_text("---\nmilestone: null\n---\n# ENH-1393: Null Milestone\n")

        config = BRConfig(tmp_path)
        parser = IssueParser(config)
        info = parser.parse_file(issue_file)

        assert info.milestone is None


# ---------------------------------------------------------------------------
# TestIsFormatted — BUG-2395
# ---------------------------------------------------------------------------


class TestIsFormatted:
    """is_formatted() must return True for canonical post-ENH-1392 issues.

    Pre-fix: Labels.required=true in templates causes is_formatted() to return
    False for issues whose labels live in frontmatter (canonical post-ENH-1392).
    Also, feat issues with ## Use Case (v2.0 name) are flagged because the
    deprecated 'User Story' entry still had level='required'.

    Post-fix: Labels.required demoted to false; User Story.level demoted to
    optional → is_formatted() returns True for canonical frontmatter-labels issues.

    Model: test_refine_status.py:1245 (test_fmt_checkmark_after_append_session_log_entry).
    Uses direct Python call to is_formatted(), not shell execution.
    """

    def test_feat_frontmatter_labels_use_case_is_formatted(self, tmp_path: Path) -> None:
        """feat with labels: frontmatter + ## Use Case → is_formatted() True (BUG-2395).

        Pre-fix: returns False (Labels required but absent from body).
        Post-fix: returns True (Labels no longer required; Use Case satisfies type req).
        """
        from little_loops.issue_parser import is_formatted

        feats_dir = tmp_path / "feats"
        feats_dir.mkdir()
        issue_file = feats_dir / "P3-FEAT-9999-test-feature.md"
        issue_file.write_text(
            "\n".join(
                [
                    "---",
                    "labels:",
                    "- host-compat",
                    "- portfolio",
                    "---",
                    "",
                    "# FEAT-9999: Test feature",
                    "",
                    "## Summary",
                    "A test feature.",
                    "",
                    "## Current Behavior",
                    "N/A — new feature.",
                    "",
                    "## Expected Behavior",
                    "It works as described.",
                    "",
                    "## Use Case",
                    "As a developer, I want X so that Y.",
                    "",
                    "## Acceptance Criteria",
                    "- Criterion 1",
                    "",
                    "## Impact",
                    "- **Priority**: P3 - Low",
                    "",
                    "## Status",
                    "open",
                ]
            )
        )
        assert is_formatted(issue_file) is True, (
            "feat with frontmatter labels + ## Use Case should be formatted (BUG-2395)"
        )

    def test_bug_frontmatter_labels_is_formatted(self, tmp_path: Path) -> None:
        """bug with labels: frontmatter + no ## Labels body → is_formatted() True (BUG-2395).

        Pre-fix: returns False (Labels required but absent from body).
        Post-fix: returns True (Labels.required demoted to false).
        """
        from little_loops.issue_parser import is_formatted

        bugs_dir = tmp_path / "bugs"
        bugs_dir.mkdir()
        issue_file = bugs_dir / "P3-BUG-9999-test-bug.md"
        issue_file.write_text(
            "\n".join(
                [
                    "---",
                    "labels:",
                    "- rn-remediate",
                    "- loop",
                    "---",
                    "",
                    "# BUG-9999: Test bug",
                    "",
                    "## Summary",
                    "A test bug.",
                    "",
                    "## Current Behavior",
                    "It breaks.",
                    "",
                    "## Expected Behavior",
                    "It works.",
                    "",
                    "## Steps to Reproduce",
                    "1. Do the thing.",
                    "",
                    "## Impact",
                    "- **Priority**: P3 - Low",
                    "",
                    "## Status",
                    "open",
                ]
            )
        )
        assert is_formatted(issue_file) is True, (
            "bug with frontmatter labels + no ## Labels body should be formatted (BUG-2395)"
        )

    def test_sparse_issue_still_not_formatted(self, tmp_path: Path) -> None:
        """issue missing a genuinely required section → is_formatted() False after demotion.

        Regression guard: demoting Labels must not gut the check (vacuous-True risk).
        A feat missing ## Impact is still not formatted.
        """
        from little_loops.issue_parser import is_formatted

        feats_dir = tmp_path / "feats"
        feats_dir.mkdir()
        issue_file = feats_dir / "P3-FEAT-9998-sparse.md"
        issue_file.write_text(
            "\n".join(
                [
                    "---",
                    "labels:",
                    "- test",
                    "---",
                    "",
                    "# FEAT-9998: Sparse",
                    "",
                    "## Summary",
                    "Only has Summary — missing Impact, Status, Use Case, etc.",
                ]
            )
        )
        assert is_formatted(issue_file) is False, (
            "feat missing required sections should still report not formatted after demotion"
        )


# ---------------------------------------------------------------------------
# TestFormatGradedChecker — ENH-2426
# ---------------------------------------------------------------------------

_CLEAN_BUG_BODY = "\n".join(
    [
        "---",
        "id: BUG-9001",
        "status: open",
        "---",
        "",
        "# BUG-9001: Test bug",
        "",
        "## Summary",
        "A real problem happens under specific conditions.",
        "",
        "## Current Behavior",
        "It breaks in a specific way.",
        "",
        "## Expected Behavior",
        "It should not break.",
        "",
        "## Steps to Reproduce",
        "1. Do the thing.",
        "2. Observe failure.",
        "",
        "## Impact",
        "- **Priority**: P3 - Low",
        "- **Effort**: Small",
        "- **Risk**: Low",
        "- **Breaking Change**: No",
        "",
        "## Status",
        "open",
    ]
)


class TestFormatGradedChecker:
    """check_format_gaps() must grade missing/renamed/empty/boilerplate gaps (ENH-2426).

    Model: TestIsFormatted (line 3130) — direct Python calls, real templates_dir.
    """

    def test_clean_issue_returns_empty_gap_list(self, tmp_path: Path) -> None:
        """A fully-populated, non-boilerplate bug issue reports no gaps."""
        from little_loops.issue_parser import check_format_gaps

        bugs_dir = tmp_path / "bugs"
        bugs_dir.mkdir()
        issue_file = bugs_dir / "P3-BUG-9001-test-bug.md"
        issue_file.write_text(_CLEAN_BUG_BODY)

        gaps = check_format_gaps(issue_file)

        assert gaps.has_gaps is False
        assert gaps.missing == []
        assert gaps.renamed == []
        assert gaps.empty == []
        assert gaps.boilerplate == []

    def test_missing_required_section_reports_missing(self, tmp_path: Path) -> None:
        """A required section absent entirely is reported under `missing`."""
        from little_loops.issue_parser import check_format_gaps

        bugs_dir = tmp_path / "bugs"
        bugs_dir.mkdir()
        issue_file = bugs_dir / "P3-BUG-9002-test-bug.md"
        body = _CLEAN_BUG_BODY.replace("## Expected Behavior\nIt should not break.\n\n", "")
        issue_file.write_text(body)

        gaps = check_format_gaps(issue_file)

        assert "Expected Behavior" in gaps.missing
        assert gaps.has_gaps is True

    def test_renamed_deprecated_section_reports_renamed(self, tmp_path: Path) -> None:
        """A present deprecated section with a canonical replacement is reported as renamed.

        'Proposed Fix' is deprecated in bug-sections.json with
        deprecation_reason "Renamed to 'Proposed Solution' in v2.0". Neither
        section is required for bug issues, so this must be the *only* gap.
        """
        from little_loops.issue_parser import check_format_gaps

        bugs_dir = tmp_path / "bugs"
        bugs_dir.mkdir()
        issue_file = bugs_dir / "P3-BUG-9003-test-bug.md"
        body = _CLEAN_BUG_BODY + "\n\n## Proposed Fix\nOld-style content.\n"
        issue_file.write_text(body)

        gaps = check_format_gaps(issue_file)

        assert gaps.renamed == ["Proposed Fix → Proposed Solution"]
        assert gaps.missing == []
        assert gaps.empty == []
        assert gaps.boilerplate == []

    def test_empty_required_section_reports_empty(self, tmp_path: Path) -> None:
        """A required header present with a whitespace-only body is reported as empty."""
        from little_loops.issue_parser import check_format_gaps

        bugs_dir = tmp_path / "bugs"
        bugs_dir.mkdir()
        issue_file = bugs_dir / "P3-BUG-9004-test-bug.md"
        body = _CLEAN_BUG_BODY.replace(
            "## Summary\nA real problem happens under specific conditions.\n",
            "## Summary\n\n",
        )
        issue_file.write_text(body)

        gaps = check_format_gaps(issue_file)

        assert gaps.empty == ["Summary"]
        assert gaps.missing == []
        assert gaps.boilerplate == []

    def test_boilerplate_body_reports_boilerplate(self, tmp_path: Path) -> None:
        """A required header whose body equals the creation_template is reported as boilerplate."""
        from little_loops.issue_parser import check_format_gaps

        bugs_dir = tmp_path / "bugs"
        bugs_dir.mkdir()
        issue_file = bugs_dir / "P3-BUG-9005-test-bug.md"
        body = _CLEAN_BUG_BODY.replace(
            "## Summary\nA real problem happens under specific conditions.\n",
            "## Summary\n[Description extracted from input]\n",
        )
        issue_file.write_text(body)

        gaps = check_format_gaps(issue_file)

        assert gaps.boilerplate == ["Summary"]
        assert gaps.missing == []
        assert gaps.empty == []

    def test_template_load_failure_returns_empty_gap_list(self, tmp_path: Path) -> None:
        """Fail-open mirror of is_formatted(): unresolved template -> no gaps reported."""
        from little_loops.issue_parser import check_format_gaps

        bugs_dir = tmp_path / "bugs"
        bugs_dir.mkdir()
        issue_file = bugs_dir / "P3-BUG-9006-test-bug.md"
        issue_file.write_text("## Summary\nOnly has Summary.")

        empty_templates = tmp_path / "empty-templates"
        empty_templates.mkdir()

        gaps = check_format_gaps(issue_file, templates_dir=empty_templates)

        assert gaps.has_gaps is False

    def test_unreadable_file_returns_empty_gap_list(self, tmp_path: Path) -> None:
        """Fail-open mirror of is_formatted(): unreadable issue file -> no gaps reported."""
        from little_loops.issue_parser import check_format_gaps

        gaps = check_format_gaps(tmp_path / "does-not-exist.md")

        assert gaps.has_gaps is False
