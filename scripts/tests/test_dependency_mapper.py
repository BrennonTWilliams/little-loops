"""Tests for little_loops.dependency_mapper module."""

from __future__ import annotations

from pathlib import Path

from little_loops.dependency_mapper import (
    DependencyProposal,
    DependencyReport,
    ValidationResult,
    analyze_dependencies,
    apply_proposals,
    extract_file_paths,
    find_file_overlaps,
    format_mermaid,
    format_report,
    validate_dependencies,
)
from little_loops.issue_parser import IssueInfo


def make_issue(
    issue_id: str,
    priority: str = "P1",
    blocked_by: list[str] | None = None,
    blocks: list[str] | None = None,
    title: str | None = None,
) -> IssueInfo:
    """Helper to create test IssueInfo objects."""
    return IssueInfo(
        path=Path(f"{issue_id.lower()}.md"),
        issue_type="features",
        priority=priority,
        issue_id=issue_id,
        title=title or f"Test {issue_id}",
        blocked_by=blocked_by or [],
        blocks=blocks or [],
    )


# =============================================================================
# extract_file_paths tests
# =============================================================================


class TestExtractFilePaths:
    """Tests for file path extraction from issue content."""

    def test_extract_from_location_section(self) -> None:
        """Test extracting path from **File**: format."""
        content = '- **File**: `scripts/little_loops/config.py`'
        paths = extract_file_paths(content)
        assert "scripts/little_loops/config.py" in paths

    def test_extract_inline_backtick_paths(self) -> None:
        """Test extracting paths from inline backticks."""
        content = "Update `scripts/little_loops/config.py` and `scripts/tests/test_config.py`."
        paths = extract_file_paths(content)
        assert "scripts/little_loops/config.py" in paths
        assert "scripts/tests/test_config.py" in paths

    def test_ignores_paths_in_code_fences(self) -> None:
        """Test that paths inside code fences are not extracted."""
        content = """
Some text.

```python
# This is inside a code fence
import scripts/little_loops/fake_module.py
```

Real reference: `scripts/little_loops/real_module.py`
"""
        paths = extract_file_paths(content)
        assert "scripts/little_loops/real_module.py" in paths
        assert "scripts/little_loops/fake_module.py" not in paths

    def test_empty_content(self) -> None:
        """Test with empty string."""
        assert extract_file_paths("") == set()

    def test_deduplicates_paths(self) -> None:
        """Test that duplicate paths are deduplicated."""
        content = (
            "See `scripts/config.py` for details.\n"
            "Also check `scripts/config.py` again."
        )
        paths = extract_file_paths(content)
        assert paths == {"scripts/config.py"}

    def test_various_extensions(self) -> None:
        """Test extraction of various file extensions."""
        content = (
            "Files: `src/app.ts`, `src/style.css`, `data/config.json`, "
            "`scripts/run.sh`"
        )
        paths = extract_file_paths(content)
        assert "src/app.ts" in paths
        assert "src/style.css" in paths
        assert "data/config.json" in paths
        assert "scripts/run.sh" in paths

    def test_no_file_paths(self) -> None:
        """Test content with no file paths."""
        content = "This is just plain text with no paths."
        assert extract_file_paths(content) == set()

    def test_standalone_path(self) -> None:
        """Test extracting standalone paths without backticks."""
        content = "The file scripts/little_loops/config.py needs updating."
        paths = extract_file_paths(content)
        assert "scripts/little_loops/config.py" in paths


# =============================================================================
# find_file_overlaps tests
# =============================================================================


class TestFindFileOverlaps:
    """Tests for file overlap detection between issues."""

    def test_no_overlap(self) -> None:
        """Test with issues referencing different files."""
        issues = [
            make_issue("FEAT-001", priority="P1"),
            make_issue("FEAT-002", priority="P2"),
        ]
        contents = {
            "FEAT-001": "See `scripts/module_a.py`",
            "FEAT-002": "See `scripts/module_b.py`",
        }
        proposals = find_file_overlaps(issues, contents)
        assert len(proposals) == 0

    def test_single_file_overlap(self) -> None:
        """Test with two issues referencing the same file."""
        issues = [
            make_issue("FEAT-001", priority="P1"),
            make_issue("FEAT-002", priority="P2"),
        ]
        contents = {
            "FEAT-001": "Fix `scripts/config.py`",
            "FEAT-002": "Update `scripts/config.py`",
        }
        proposals = find_file_overlaps(issues, contents)
        assert len(proposals) == 1
        p = proposals[0]
        assert p.target_id == "FEAT-001"  # Higher priority = blocker
        assert p.source_id == "FEAT-002"  # Lower priority = blocked
        assert "scripts/config.py" in p.overlapping_files

    def test_multiple_file_overlap(self) -> None:
        """Test with multiple overlapping files."""
        issues = [
            make_issue("FEAT-001", priority="P1"),
            make_issue("FEAT-002", priority="P2"),
        ]
        contents = {
            "FEAT-001": "Fix `scripts/config.py` and `scripts/utils.py`",
            "FEAT-002": "Update `scripts/config.py` and `scripts/utils.py` and `scripts/extra.py`",
        }
        proposals = find_file_overlaps(issues, contents)
        assert len(proposals) == 1
        assert len(proposals[0].overlapping_files) == 2

    def test_skips_existing_dependency(self) -> None:
        """Test that existing dependencies are not re-proposed."""
        issues = [
            make_issue("FEAT-001", priority="P1"),
            make_issue("FEAT-002", priority="P2", blocked_by=["FEAT-001"]),
        ]
        contents = {
            "FEAT-001": "Fix `scripts/config.py`",
            "FEAT-002": "Update `scripts/config.py`",
        }
        proposals = find_file_overlaps(issues, contents)
        assert len(proposals) == 0

    def test_priority_ordering(self) -> None:
        """Test that higher priority issue becomes the blocker."""
        issues = [
            make_issue("FEAT-002", priority="P2"),
            make_issue("FEAT-001", priority="P0"),
        ]
        contents = {
            "FEAT-001": "Fix `scripts/config.py`",
            "FEAT-002": "Update `scripts/config.py`",
        }
        proposals = find_file_overlaps(issues, contents)
        assert len(proposals) == 1
        assert proposals[0].target_id == "FEAT-001"  # P0 = blocker
        assert proposals[0].source_id == "FEAT-002"  # P2 = blocked

    def test_same_priority_uses_id_order(self) -> None:
        """Test that same-priority uses ID ordering."""
        issues = [
            make_issue("FEAT-002", priority="P1"),
            make_issue("FEAT-001", priority="P1"),
        ]
        contents = {
            "FEAT-001": "Fix `scripts/config.py`",
            "FEAT-002": "Update `scripts/config.py`",
        }
        proposals = find_file_overlaps(issues, contents)
        assert len(proposals) == 1
        assert proposals[0].target_id == "FEAT-001"  # Earlier ID = blocker
        assert proposals[0].source_id == "FEAT-002"

    def test_confidence_calculation(self) -> None:
        """Test that confidence is calculated correctly."""
        issues = [
            make_issue("FEAT-001", priority="P1"),
            make_issue("FEAT-002", priority="P2"),
        ]
        contents = {
            "FEAT-001": "Fix `scripts/config.py` and `scripts/utils.py`",
            "FEAT-002": "Update `scripts/config.py`",  # 1 of 1 overlap
        }
        proposals = find_file_overlaps(issues, contents)
        assert len(proposals) == 1
        # Overlap = 1, min paths = 1 → confidence = 1.0
        assert proposals[0].confidence == 1.0

    def test_empty_issues(self) -> None:
        """Test with no issues."""
        assert find_file_overlaps([], {}) == []

    def test_issues_with_no_paths(self) -> None:
        """Test with issues that have no file paths in content."""
        issues = [
            make_issue("FEAT-001"),
            make_issue("FEAT-002"),
        ]
        contents = {
            "FEAT-001": "This has no paths",
            "FEAT-002": "Neither does this",
        }
        proposals = find_file_overlaps(issues, contents)
        assert len(proposals) == 0

    def test_skips_reverse_existing_dependency(self) -> None:
        """Test that reverse existing dependencies are also skipped."""
        issues = [
            make_issue("FEAT-001", priority="P1", blocks=["FEAT-002"]),
            make_issue("FEAT-002", priority="P2", blocked_by=["FEAT-001"]),
        ]
        contents = {
            "FEAT-001": "Fix `scripts/config.py`",
            "FEAT-002": "Update `scripts/config.py`",
        }
        proposals = find_file_overlaps(issues, contents)
        assert len(proposals) == 0


# =============================================================================
# validate_dependencies tests
# =============================================================================


class TestValidateDependencies:
    """Tests for dependency reference validation."""

    def test_valid_dependencies(self) -> None:
        """Test with all valid dependency references."""
        issues = [
            make_issue("FEAT-001", blocks=["FEAT-002"]),
            make_issue("FEAT-002", blocked_by=["FEAT-001"]),
        ]
        result = validate_dependencies(issues)
        assert not result.has_issues

    def test_broken_ref(self) -> None:
        """Test detection of broken references."""
        issues = [
            make_issue("FEAT-001", blocked_by=["BUG-999"]),
        ]
        result = validate_dependencies(issues)
        assert ("FEAT-001", "BUG-999") in result.broken_refs

    def test_missing_backlink(self) -> None:
        """Test detection of missing backlinks."""
        issues = [
            make_issue("FEAT-001"),  # No blocks entry for FEAT-002
            make_issue("FEAT-002", blocked_by=["FEAT-001"]),
        ]
        result = validate_dependencies(issues)
        assert ("FEAT-002", "FEAT-001") in result.missing_backlinks

    def test_cycle_detection(self) -> None:
        """Test detection of dependency cycles."""
        issues = [
            make_issue("FEAT-001", blocked_by=["FEAT-002"]),
            make_issue("FEAT-002", blocked_by=["FEAT-001"]),
        ]
        result = validate_dependencies(issues)
        assert len(result.cycles) > 0

    def test_stale_completed_ref(self) -> None:
        """Test detection of references to completed issues."""
        issues = [
            make_issue("FEAT-002", blocked_by=["FEAT-001"]),
        ]
        result = validate_dependencies(issues, completed_ids={"FEAT-001"})
        assert ("FEAT-002", "FEAT-001") in result.stale_completed_refs

    def test_no_issues(self) -> None:
        """Test with empty issue list."""
        result = validate_dependencies([])
        assert not result.has_issues

    def test_no_dependencies(self) -> None:
        """Test issues with no dependency references."""
        issues = [
            make_issue("FEAT-001"),
            make_issue("FEAT-002"),
        ]
        result = validate_dependencies(issues)
        assert not result.has_issues

    def test_valid_with_completed_blocker(self) -> None:
        """Test that completed blockers are correctly categorized as stale, not broken."""
        issues = [
            make_issue("FEAT-002", blocked_by=["FEAT-001"]),
        ]
        result = validate_dependencies(issues, completed_ids={"FEAT-001"})
        assert len(result.broken_refs) == 0
        assert ("FEAT-002", "FEAT-001") in result.stale_completed_refs


# =============================================================================
# analyze_dependencies tests
# =============================================================================


class TestAnalyzeDependencies:
    """Integration tests for full analysis pipeline."""

    def test_empty_issues(self) -> None:
        """Test with no issues."""
        report = analyze_dependencies([], {})
        assert report.issue_count == 0
        assert report.existing_dep_count == 0
        assert len(report.proposals) == 0

    def test_full_analysis_with_overlaps_and_validation(self) -> None:
        """Test full pipeline with both overlaps and validation issues."""
        issues = [
            make_issue("FEAT-001", priority="P1"),
            make_issue("FEAT-002", priority="P2", blocked_by=["BUG-999"]),
        ]
        contents = {
            "FEAT-001": "Fix `scripts/config.py`",
            "FEAT-002": "Update `scripts/config.py`",
        }
        report = analyze_dependencies(issues, contents)
        assert report.issue_count == 2
        assert report.existing_dep_count == 1  # FEAT-002 has 1 blocked_by
        assert len(report.proposals) == 1  # File overlap proposal
        assert report.validation.has_issues  # Broken ref to BUG-999


# =============================================================================
# format_report tests
# =============================================================================


class TestFormatReport:
    """Tests for report formatting."""

    def test_format_with_proposals(self) -> None:
        """Test formatting a report with proposals."""
        report = DependencyReport(
            proposals=[
                DependencyProposal(
                    source_id="FEAT-002",
                    target_id="FEAT-001",
                    reason="file_overlap",
                    confidence=0.75,
                    rationale="Both reference config.py",
                    overlapping_files=["scripts/config.py"],
                )
            ],
            issue_count=2,
            existing_dep_count=0,
        )
        text = format_report(report)
        assert "Proposed Dependencies" in text
        assert "FEAT-002" in text
        assert "FEAT-001" in text
        assert "75%" in text

    def test_format_with_validation_issues(self) -> None:
        """Test formatting a report with validation problems."""
        report = DependencyReport(
            validation=ValidationResult(
                broken_refs=[("FEAT-001", "BUG-999")],
                missing_backlinks=[("FEAT-002", "FEAT-001")],
                cycles=[["FEAT-003", "FEAT-004", "FEAT-003"]],
                stale_completed_refs=[("FEAT-005", "FEAT-006")],
            ),
            issue_count=5,
        )
        text = format_report(report)
        assert "Broken References" in text
        assert "BUG-999" in text
        assert "Missing Backlinks" in text
        assert "Dependency Cycles" in text
        assert "Stale References" in text

    def test_format_empty_report(self) -> None:
        """Test formatting an empty report."""
        report = DependencyReport(issue_count=3)
        text = format_report(report)
        assert "No dependency proposals or validation issues found" in text

    def test_format_includes_summary(self) -> None:
        """Test that the report includes summary statistics."""
        report = DependencyReport(issue_count=10, existing_dep_count=5)
        text = format_report(report)
        assert "Issues analyzed**: 10" in text
        assert "Existing dependencies**: 5" in text


# =============================================================================
# format_mermaid tests
# =============================================================================


class TestFormatMermaid:
    """Tests for Mermaid diagram generation."""

    def test_simple_graph(self) -> None:
        """Test generating a simple dependency graph."""
        issues = [
            make_issue("FEAT-001", title="Auth feature"),
            make_issue("FEAT-002", title="User profile", blocked_by=["FEAT-001"]),
        ]
        mermaid = format_mermaid(issues)
        assert "```mermaid" in mermaid
        assert "graph TD" in mermaid
        assert 'FEAT-001["FEAT-001: Auth feature"]' in mermaid
        assert "FEAT-001 --> FEAT-002" in mermaid

    def test_graph_with_proposals(self) -> None:
        """Test that proposed edges use dashed arrows."""
        issues = [
            make_issue("FEAT-001"),
            make_issue("FEAT-002"),
        ]
        proposals = [
            DependencyProposal(
                source_id="FEAT-002",
                target_id="FEAT-001",
                reason="file_overlap",
                confidence=0.8,
                rationale="test",
            )
        ]
        mermaid = format_mermaid(issues, proposals)
        assert "FEAT-001 -.-> FEAT-002" in mermaid

    def test_empty_graph(self) -> None:
        """Test with no issues."""
        mermaid = format_mermaid([])
        assert "```mermaid" in mermaid
        assert "graph TD" in mermaid

    def test_no_edges(self) -> None:
        """Test issues with no dependencies."""
        issues = [
            make_issue("FEAT-001"),
            make_issue("FEAT-002"),
        ]
        mermaid = format_mermaid(issues)
        assert "-->" not in mermaid
        assert "-.->" not in mermaid


# =============================================================================
# apply_proposals tests
# =============================================================================


class TestApplyProposals:
    """Tests for writing proposals to issue files."""

    def test_add_blocked_by_to_issue_without_section(self, tmp_path: Path) -> None:
        """Test adding Blocked By section to an issue that doesn't have one."""
        issue_file = tmp_path / "FEAT-002.md"
        issue_file.write_text(
            "# FEAT-002: Test Issue\n\n"
            "## Summary\n\nTest summary.\n\n"
            "## Labels\n\n`feature`\n"
        )

        blocker_file = tmp_path / "FEAT-001.md"
        blocker_file.write_text(
            "# FEAT-001: Blocker Issue\n\n"
            "## Summary\n\nBlocker summary.\n\n"
            "## Labels\n\n`feature`\n"
        )

        proposals = [
            DependencyProposal(
                source_id="FEAT-002",
                target_id="FEAT-001",
                reason="file_overlap",
                confidence=0.8,
                rationale="test",
            )
        ]
        issue_files = {"FEAT-002": issue_file, "FEAT-001": blocker_file}
        modified = apply_proposals(proposals, issue_files)

        assert len(modified) == 2
        content_source = issue_file.read_text()
        assert "## Blocked By" in content_source
        assert "- FEAT-001" in content_source

        content_target = blocker_file.read_text()
        assert "## Blocks" in content_target
        assert "- FEAT-002" in content_target

    def test_append_to_existing_blocked_by_section(self, tmp_path: Path) -> None:
        """Test appending to an existing Blocked By section."""
        issue_file = tmp_path / "FEAT-003.md"
        issue_file.write_text(
            "# FEAT-003: Test Issue\n\n"
            "## Blocked By\n\n"
            "- FEAT-001\n\n"
            "## Labels\n\n`feature`\n"
        )

        proposals = [
            DependencyProposal(
                source_id="FEAT-003",
                target_id="FEAT-002",
                reason="file_overlap",
                confidence=0.7,
                rationale="test",
            )
        ]
        # Only source exists, target doesn't — should still modify source
        issue_files = {"FEAT-003": issue_file}
        modified = apply_proposals(proposals, issue_files)

        assert len(modified) == 1
        content = issue_file.read_text()
        assert "- FEAT-001" in content
        assert "- FEAT-002" in content

    def test_does_not_duplicate_existing_entry(self, tmp_path: Path) -> None:
        """Test that applying a proposal with an already-present ID is a no-op."""
        issue_file = tmp_path / "FEAT-002.md"
        issue_file.write_text(
            "# FEAT-002: Test Issue\n\n"
            "## Blocked By\n\n"
            "- FEAT-001\n\n"
            "## Labels\n\n`feature`\n"
        )

        proposals = [
            DependencyProposal(
                source_id="FEAT-002",
                target_id="FEAT-001",
                reason="file_overlap",
                confidence=0.8,
                rationale="test",
            )
        ]
        issue_files = {"FEAT-002": issue_file}
        apply_proposals(proposals, issue_files)

        content = issue_file.read_text()
        assert content.count("FEAT-001") == 1

    def test_adds_backlink_blocks_section(self, tmp_path: Path) -> None:
        """Test that the target issue gets a Blocks section."""
        source_file = tmp_path / "FEAT-002.md"
        source_file.write_text("# FEAT-002: Source\n\n## Summary\n\nTest.\n")

        target_file = tmp_path / "FEAT-001.md"
        target_file.write_text("# FEAT-001: Target\n\n## Summary\n\nTest.\n")

        proposals = [
            DependencyProposal(
                source_id="FEAT-002",
                target_id="FEAT-001",
                reason="file_overlap",
                confidence=0.8,
                rationale="test",
            )
        ]
        issue_files = {"FEAT-002": source_file, "FEAT-001": target_file}
        apply_proposals(proposals, issue_files)

        target_content = target_file.read_text()
        assert "## Blocks" in target_content
        assert "- FEAT-002" in target_content

    def test_empty_proposals(self, tmp_path: Path) -> None:
        """Test with no proposals to apply."""
        modified = apply_proposals([], {})
        assert modified == []

    def test_missing_file(self, tmp_path: Path) -> None:
        """Test graceful handling when issue file doesn't exist."""
        proposals = [
            DependencyProposal(
                source_id="FEAT-002",
                target_id="FEAT-001",
                reason="file_overlap",
                confidence=0.8,
                rationale="test",
            )
        ]
        # Files don't exist in the mapping
        modified = apply_proposals(proposals, {})
        assert modified == []
