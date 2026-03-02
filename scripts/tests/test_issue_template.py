"""Tests for issue template assembly utility."""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.issue_template import assemble_issue_markdown, load_issue_sections


@pytest.fixture
def sections_data() -> dict:
    """Load the real issue-sections.json for testing."""
    return load_issue_sections()


class TestLoadIssueSections:
    """Tests for loading issue-sections.json."""

    def test_load_default(self) -> None:
        """Loads from bundled templates/ directory."""
        data = load_issue_sections()
        assert "_meta" in data
        assert data["_meta"]["version"] == "2.0"
        assert "common_sections" in data
        assert "creation_variants" in data

    def test_load_custom_dir(self, tmp_path: Path) -> None:
        """Loads from a custom templates directory."""
        template = {
            "_meta": {"version": "test"},
            "common_sections": {"Summary": {"required": True, "creation_template": "test"}},
            "creation_variants": {"minimal": {"include_common": ["Summary"]}},
        }
        import json

        (tmp_path / "issue-sections.json").write_text(json.dumps(template))
        data = load_issue_sections(tmp_path)
        assert data["_meta"]["version"] == "test"

    def test_load_missing_file(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError for missing template."""
        with pytest.raises(FileNotFoundError):
            load_issue_sections(tmp_path)


class TestAssembleIssueMarkdown:
    """Tests for markdown assembly."""

    def test_minimal_variant(self, sections_data: dict) -> None:
        """Minimal variant produces core sections only."""
        result = assemble_issue_markdown(
            sections_data=sections_data,
            issue_type="ENH",
            variant="minimal",
            issue_id="ENH-100",
            title="Test Enhancement",
            frontmatter={"discovered_by": "test", "discovered_date": "2026-03-01"},
        )
        assert "# ENH-100: Test Enhancement" in result
        assert "## Summary" in result
        assert "## Current Behavior" in result
        assert "## Expected Behavior" in result
        assert "## Impact" in result
        assert "## Status" in result
        # Minimal should NOT include type-specific sections
        assert "## Scope Boundaries" not in result
        # Minimal should NOT include deprecated sections
        assert "## Context" not in result

    def test_full_variant(self, sections_data: dict) -> None:
        """Full variant includes common + type-specific sections."""
        result = assemble_issue_markdown(
            sections_data=sections_data,
            issue_type="BUG",
            variant="full",
            issue_id="BUG-050",
            title="Test Bug",
            frontmatter={"discovered_by": "test"},
        )
        assert "## Summary" in result
        assert "## Motivation" in result
        assert "## Implementation Steps" in result
        # Full includes type-specific for BUG
        assert "## Steps to Reproduce" in result

    def test_content_overrides(self, sections_data: dict) -> None:
        """Provided content replaces creation_template placeholders."""
        result = assemble_issue_markdown(
            sections_data=sections_data,
            issue_type="ENH",
            variant="minimal",
            issue_id="ENH-200",
            title="Override Test",
            frontmatter={"discovered_by": "test"},
            content={"Summary": "This is the real summary content."},
        )
        assert "This is the real summary content." in result
        # Default creation_template should NOT appear for Summary
        assert "[Description extracted from input]" not in result

    def test_labels_appended_in_minimal(self, sections_data: dict) -> None:
        """Labels section is appended even when not in minimal variant."""
        result = assemble_issue_markdown(
            sections_data=sections_data,
            issue_type="ENH",
            variant="minimal",
            issue_id="ENH-300",
            title="Labels Test",
            frontmatter={"discovered_by": "test"},
            labels=["enhancement", "sync"],
        )
        assert "## Labels" in result
        assert "`enhancement`" in result
        assert "`sync`" in result

    def test_frontmatter_rendered(self, sections_data: dict) -> None:
        """Frontmatter is correctly rendered as YAML block."""
        result = assemble_issue_markdown(
            sections_data=sections_data,
            issue_type="FEAT",
            variant="minimal",
            issue_id="FEAT-010",
            title="FM Test",
            frontmatter={
                "github_issue": 42,
                "github_url": "https://github.com/test/repo/issues/42",
                "discovered_by": "github_sync",
            },
        )
        assert result.startswith("---\n")
        assert "github_issue: 42" in result
        assert "github_url: https://github.com/test/repo/issues/42" in result
        assert "discovered_by: github_sync" in result

    def test_unknown_variant_raises(self, sections_data: dict) -> None:
        """Unknown variant raises ValueError."""
        with pytest.raises(ValueError, match="Unknown creation variant"):
            assemble_issue_markdown(
                sections_data=sections_data,
                issue_type="ENH",
                variant="nonexistent",
                issue_id="ENH-999",
                title="Bad Variant",
                frontmatter={},
            )

    def test_labels_in_content_used_by_full_variant(self, sections_data: dict) -> None:
        """When Labels is in include_common, content dict is used."""
        result = assemble_issue_markdown(
            sections_data=sections_data,
            issue_type="ENH",
            variant="full",
            issue_id="ENH-400",
            title="Full Labels",
            frontmatter={"discovered_by": "test"},
            content={"Labels": "`enhancement`, `sync`"},
            labels=["enhancement", "sync"],
        )
        assert "## Labels" in result
        assert "`enhancement`, `sync`" in result
