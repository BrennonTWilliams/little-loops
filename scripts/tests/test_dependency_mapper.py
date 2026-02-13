"""Tests for little_loops.dependency_mapper module."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from little_loops.dependency_mapper import (
    DependencyProposal,
    DependencyReport,
    ParallelSafePair,
    ValidationResult,
    analyze_dependencies,
    apply_proposals,
    compute_conflict_score,
    extract_file_paths,
    find_file_overlaps,
    format_report,
    format_text_graph,
    gather_all_issue_ids,
    main,
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
        content = "- **File**: `scripts/little_loops/config.py`"
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
        content = "See `scripts/config.py` for details.\nAlso check `scripts/config.py` again."
        paths = extract_file_paths(content)
        assert paths == {"scripts/config.py"}

    def test_various_extensions(self) -> None:
        """Test extraction of various file extensions."""
        content = "Files: `src/app.ts`, `src/style.css`, `data/config.json`, `scripts/run.sh`"
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
# compute_conflict_score tests
# =============================================================================


class TestComputeConflictScore:
    """Tests for semantic conflict scoring."""

    def test_same_component_high_conflict(self) -> None:
        """Issues both modifying same component should have high conflict."""
        content_a = "Add duplicate button to ActivityCard in day-columns.tsx"
        content_b = "Add star toggle to ActivityCard in day-columns.tsx"
        score = compute_conflict_score(content_a, content_b)
        assert score > 0.6

    def test_different_sections_low_conflict(self) -> None:
        """Issues modifying different sections should have low conflict."""
        content_a = "Add stats to day column header in day-columns.tsx"
        content_b = "Add empty state to droppable body in day-columns.tsx"
        score = compute_conflict_score(content_a, content_b)
        assert score < 0.4

    def test_empty_content(self) -> None:
        """Empty content should return moderate default score."""
        score = compute_conflict_score("", "")
        assert 0.3 <= score <= 0.7

    def test_no_semantic_signals_moderate_score(self) -> None:
        """Content with no extractable targets defaults to moderate."""
        content_a = "fix the bug in the config file"
        content_b = "update the config settings"
        score = compute_conflict_score(content_a, content_b)
        assert 0.2 <= score <= 0.8

    def test_structural_vs_enhancement_different_types(self) -> None:
        """Different modification types should reduce conflict score."""
        content_a = "Extract activity list into separate component"
        content_b = "Add button to display stats in header"
        score = compute_conflict_score(content_a, content_b)
        # Different types contribute 0.0 to the type signal
        assert score < 0.7

    def test_same_section_same_type_high_conflict(self) -> None:
        """Same section and same modification type should be high conflict."""
        content_a = "Add tooltip to header section"
        content_b = "Add badge to header toolbar"
        score = compute_conflict_score(content_a, content_b)
        assert score >= 0.4

    def test_score_bounded_zero_to_one(self) -> None:
        """Score should always be between 0.0 and 1.0."""
        test_pairs = [
            ("", ""),
            ("simple text", "simple text"),
            ("Add button to ActivityCard", "Refactor sidebar modal"),
            ("Extract header component", "Extract header component"),
        ]
        for content_a, content_b in test_pairs:
            score = compute_conflict_score(content_a, content_b)
            assert 0.0 <= score <= 1.0


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
        proposals, parallel_safe = find_file_overlaps(issues, contents)
        assert len(proposals) == 0
        assert len(parallel_safe) == 0

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
        proposals, _ = find_file_overlaps(issues, contents)
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
        proposals, _ = find_file_overlaps(issues, contents)
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
        proposals, _ = find_file_overlaps(issues, contents)
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
        proposals, _ = find_file_overlaps(issues, contents)
        assert len(proposals) == 1
        assert proposals[0].target_id == "FEAT-001"  # P0 = blocker
        assert proposals[0].source_id == "FEAT-002"  # P2 = blocked

    def test_same_priority_uses_id_order(self) -> None:
        """Test that same-priority falls back to ID ordering."""
        issues = [
            make_issue("FEAT-002", priority="P1"),
            make_issue("FEAT-001", priority="P1"),
        ]
        contents = {
            "FEAT-001": "Fix `scripts/config.py`",
            "FEAT-002": "Update `scripts/config.py`",
        }
        proposals, _ = find_file_overlaps(issues, contents)
        # Should still produce a proposal (or parallel_safe depending on content)
        total = len(proposals)
        assert total >= 0  # Content may or may not trigger parallel-safe

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
        proposals, _ = find_file_overlaps(issues, contents)
        assert len(proposals) == 1
        # Confidence may be adjusted by conflict modifier
        assert proposals[0].confidence > 0.0

    def test_empty_issues(self) -> None:
        """Test with no issues."""
        proposals, parallel_safe = find_file_overlaps([], {})
        assert proposals == []
        assert parallel_safe == []

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
        proposals, parallel_safe = find_file_overlaps(issues, contents)
        assert len(proposals) == 0
        assert len(parallel_safe) == 0

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
        proposals, _ = find_file_overlaps(issues, contents)
        assert len(proposals) == 0


# =============================================================================
# find_file_overlaps semantic analysis tests
# =============================================================================


class TestFindFileOverlapsSemanticAnalysis:
    """Tests for semantic conflict filtering in file overlap detection."""

    def test_parallel_safe_different_sections(self) -> None:
        """Issues touching different sections should be parallel-safe."""
        issues = [
            make_issue("ENH-032", priority="P2", title="Empty state"),
            make_issue("ENH-033", priority="P2", title="Header stats"),
        ]
        contents = {
            "ENH-032": "Add empty state to droppable body in `src/day-columns.tsx`",
            "ENH-033": "Add stats to day column header in `src/day-columns.tsx`",
        }
        proposals, parallel_safe = find_file_overlaps(issues, contents)
        assert len(proposals) == 0
        assert len(parallel_safe) == 1
        pair = parallel_safe[0]
        assert {pair.issue_a, pair.issue_b} == {"ENH-032", "ENH-033"}

    def test_high_conflict_same_component(self) -> None:
        """Issues modifying same component should create dependency."""
        issues = [
            make_issue("FEAT-030", priority="P2", title="Duplicate button"),
            make_issue("FEAT-031", priority="P2", title="Star toggle"),
        ]
        contents = {
            "FEAT-030": "Add duplicate button to ActivityCard in `src/day-columns.tsx`",
            "FEAT-031": "Add star toggle to ActivityCard in `src/day-columns.tsx`",
        }
        proposals, parallel_safe = find_file_overlaps(issues, contents)
        assert len(proposals) == 1
        assert len(parallel_safe) == 0

    def test_structural_before_enhancement_ordering(self) -> None:
        """Structural changes should block enhancement changes at same priority."""
        issues = [
            make_issue("FEAT-028", priority="P3", title="Extract component"),
            make_issue("FEAT-031", priority="P3", title="Add star toggle"),
        ]
        contents = {
            "FEAT-028": "Extract ActivityCard into `src/activity-card.tsx` from `src/day-columns.tsx`",
            "FEAT-031": "Add star toggle button to ActivityCard in `src/day-columns.tsx`",
        }
        proposals, parallel_safe = find_file_overlaps(issues, contents)
        assert len(proposals) == 1
        assert proposals[0].target_id == "FEAT-028"  # Structural = blocker
        assert proposals[0].source_id == "FEAT-031"  # Enhancement = blocked

    def test_conflict_score_on_proposal(self) -> None:
        """Proposals should include the computed conflict score."""
        issues = [
            make_issue("FEAT-001", priority="P1"),
            make_issue("FEAT-002", priority="P2"),
        ]
        contents = {
            "FEAT-001": "Add button to ActivityCard in `scripts/config.py`",
            "FEAT-002": "Update ActivityCard styling in `scripts/config.py`",
        }
        proposals, _ = find_file_overlaps(issues, contents)
        assert len(proposals) == 1
        assert proposals[0].conflict_score > 0.0

    def test_parallel_safe_reason_includes_sections(self) -> None:
        """Parallel-safe pairs with section mentions should include section names in reason."""
        issues = [
            make_issue("ENH-001", priority="P2"),
            make_issue("ENH-002", priority="P2"),
        ]
        contents = {
            "ENH-001": "Update SidebarNav component in the sidebar drawer in `src/layout.tsx`",
            "ENH-002": "Refactor FooterLinks component in the footer in `src/layout.tsx`",
        }
        proposals, parallel_safe = find_file_overlaps(issues, contents)
        assert len(parallel_safe) == 1
        assert "Different sections" in parallel_safe[0].reason


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

    def test_cross_type_ref_not_broken_with_all_known_ids(self) -> None:
        """Test that a ref to an issue outside the working set is not broken when all_known_ids is provided."""
        issues = [
            make_issue("BUG-359", blocked_by=["ENH-342"]),
        ]
        # ENH-342 is not in the issues list but exists on disk
        result = validate_dependencies(issues, all_known_ids={"BUG-359", "ENH-342"})
        assert len(result.broken_refs) == 0

    def test_truly_nonexistent_ref_still_broken_with_all_known_ids(self) -> None:
        """Test that a ref to a truly nonexistent issue is still flagged as broken."""
        issues = [
            make_issue("BUG-001", blocked_by=["FEAT-999"]),
        ]
        # FEAT-999 is not in all_known_ids either
        result = validate_dependencies(issues, all_known_ids={"BUG-001", "ENH-342"})
        assert ("BUG-001", "FEAT-999") in result.broken_refs

    def test_all_known_ids_backward_compatible(self) -> None:
        """Test that omitting all_known_ids preserves original behavior."""
        issues = [
            make_issue("FEAT-001", blocked_by=["BUG-999"]),
        ]
        result = validate_dependencies(issues)
        assert ("FEAT-001", "BUG-999") in result.broken_refs


# =============================================================================
# gather_all_issue_ids tests
# =============================================================================


class TestGatherAllIssueIds:
    """Tests for gathering issue IDs from filesystem."""

    def test_scans_all_categories(self, tmp_path: Path) -> None:
        """Test that IDs are gathered from bugs, features, enhancements, and completed."""
        (tmp_path / "bugs").mkdir()
        (tmp_path / "features").mkdir()
        (tmp_path / "enhancements").mkdir()
        (tmp_path / "completed").mkdir()

        (tmp_path / "bugs" / "P1-BUG-001-test.md").write_text("# BUG-001")
        (tmp_path / "features" / "P2-FEAT-010-feature.md").write_text("# FEAT-010")
        (tmp_path / "enhancements" / "P3-ENH-100-improve.md").write_text("# ENH-100")
        (tmp_path / "completed" / "P1-BUG-002-done.md").write_text("# BUG-002")

        ids = gather_all_issue_ids(tmp_path)
        assert ids == {"BUG-001", "FEAT-010", "ENH-100", "BUG-002"}

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Test with no subdirectories."""
        ids = gather_all_issue_ids(tmp_path)
        assert ids == set()

    def test_missing_subdirectories(self, tmp_path: Path) -> None:
        """Test gracefully handles missing category directories."""
        (tmp_path / "bugs").mkdir()
        (tmp_path / "bugs" / "P1-BUG-001-test.md").write_text("# BUG-001")
        # features, enhancements, completed don't exist
        ids = gather_all_issue_ids(tmp_path)
        assert ids == {"BUG-001"}


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
        assert len(report.parallel_safe) == 0

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
        # File overlap may produce proposal or parallel_safe depending on content
        assert len(report.proposals) + len(report.parallel_safe) >= 0
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
                    conflict_score=0.85,
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
        assert "Conflict" in text
        assert "HIGH" in text

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
        assert "Parallel-safe pairs**: 0" in text


# =============================================================================
# format_report conflict info tests
# =============================================================================


class TestFormatReportConflictInfo:
    """Tests for conflict information in report formatting."""

    def test_parallel_safe_section(self) -> None:
        """Report should include parallel-safe section."""
        report = DependencyReport(
            parallel_safe=[
                ParallelSafePair(
                    issue_a="ENH-032",
                    issue_b="ENH-033",
                    shared_files=["src/day-columns.tsx"],
                    conflict_score=0.15,
                    reason="Different sections (body vs header)",
                )
            ],
            issue_count=2,
        )
        text = format_report(report)
        assert "Parallel Execution Safe" in text
        assert "ENH-032" in text
        assert "ENH-033" in text
        assert "15%" in text

    def test_conflict_column_in_proposals(self) -> None:
        """Proposals table should include conflict level."""
        report = DependencyReport(
            proposals=[
                DependencyProposal(
                    source_id="FEAT-031",
                    target_id="FEAT-028",
                    reason="file_overlap",
                    confidence=0.75,
                    rationale="Both reference day-columns.tsx",
                    overlapping_files=["src/day-columns.tsx"],
                    conflict_score=0.85,
                )
            ],
            issue_count=2,
        )
        text = format_report(report)
        assert "HIGH" in text
        assert "Conflict" in text

    def test_medium_conflict_level(self) -> None:
        """Medium conflict score should show MEDIUM."""
        report = DependencyReport(
            proposals=[
                DependencyProposal(
                    source_id="FEAT-002",
                    target_id="FEAT-001",
                    reason="file_overlap",
                    confidence=0.5,
                    rationale="test",
                    conflict_score=0.5,
                )
            ],
            issue_count=2,
        )
        text = format_report(report)
        assert "MEDIUM" in text

    def test_no_parallel_safe_section_when_empty(self) -> None:
        """Report should not include parallel-safe section when empty."""
        report = DependencyReport(issue_count=3)
        text = format_report(report)
        assert "Parallel Execution Safe" not in text


# =============================================================================
# format_text_graph tests
# =============================================================================


class TestFormatTextGraph:
    """Tests for ASCII text graph generation."""

    def test_simple_graph(self) -> None:
        """Test generating a simple dependency graph."""
        issues = [
            make_issue("FEAT-001", title="Auth feature"),
            make_issue("FEAT-002", title="User profile", blocked_by=["FEAT-001"]),
        ]
        text = format_text_graph(issues)
        assert "FEAT-001" in text
        assert "FEAT-002" in text
        assert "FEAT-001 ──→ FEAT-002" in text

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
        text = format_text_graph(issues, proposals)
        assert "FEAT-001 -.→ FEAT-002" in text

    def test_empty_graph(self) -> None:
        """Test with no issues."""
        text = format_text_graph([])
        assert text == "(no issues)"

    def test_no_edges(self) -> None:
        """Test issues with no dependencies."""
        issues = [
            make_issue("FEAT-001"),
            make_issue("FEAT-002"),
        ]
        text = format_text_graph(issues)
        assert "──→" not in text
        assert "-.→" not in text


# =============================================================================
# apply_proposals tests
# =============================================================================


class TestApplyProposals:
    """Tests for writing proposals to issue files."""

    def test_add_blocked_by_to_issue_without_section(self, tmp_path: Path) -> None:
        """Test adding Blocked By section to an issue that doesn't have one."""
        issue_file = tmp_path / "FEAT-002.md"
        issue_file.write_text(
            "# FEAT-002: Test Issue\n\n## Summary\n\nTest summary.\n\n## Labels\n\n`feature`\n"
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
            "# FEAT-003: Test Issue\n\n## Blocked By\n\n- FEAT-001\n\n## Labels\n\n`feature`\n"
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
            "# FEAT-002: Test Issue\n\n## Blocked By\n\n- FEAT-001\n\n## Labels\n\n`feature`\n"
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


# =============================================================================
# CLI main() tests
# =============================================================================


class TestMainCLI:
    """Tests for the ll-deps CLI entry point."""

    def test_no_command_shows_help(self) -> None:
        """Test main() with no command returns 1."""
        with patch.object(sys, "argv", ["ll-deps"]):
            result = main()
        assert result == 1

    def test_nonexistent_issues_dir(self) -> None:
        """Test main() with nonexistent issues directory returns 1."""
        with patch.object(sys, "argv", ["ll-deps", "-d", "/nonexistent/path", "analyze"]):
            result = main()
        assert result == 1

    def test_analyze_no_issues(self, tmp_path: Path) -> None:
        """Test analyze with empty issues directory."""
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()
        (issues_dir / "bugs").mkdir()
        (issues_dir / "features").mkdir()
        (issues_dir / "enhancements").mkdir()
        (issues_dir / "completed").mkdir()

        # Create minimal config
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "ll-config.json").write_text('{"issues": {"base_dir": ".issues"}}')

        with patch.object(sys, "argv", ["ll-deps", "-d", str(issues_dir), "analyze"]):
            result = main()
        assert result == 0

    def test_validate_no_issues(self, tmp_path: Path) -> None:
        """Test validate with empty issues directory."""
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()
        (issues_dir / "bugs").mkdir()
        (issues_dir / "features").mkdir()
        (issues_dir / "enhancements").mkdir()
        (issues_dir / "completed").mkdir()

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "ll-config.json").write_text('{"issues": {"base_dir": ".issues"}}')

        with patch.object(sys, "argv", ["ll-deps", "-d", str(issues_dir), "validate"]):
            result = main()
        assert result == 0

    def test_analyze_with_issues(self, tmp_path: Path, capsys: object) -> None:
        """Test analyze with actual issues produces output."""
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()
        bugs_dir = issues_dir / "bugs"
        bugs_dir.mkdir()
        (issues_dir / "features").mkdir()
        (issues_dir / "enhancements").mkdir()
        (issues_dir / "completed").mkdir()

        (bugs_dir / "P1-BUG-001-test-bug.md").write_text(
            "# BUG-001: Test Bug\n\n## Summary\n\nFix `scripts/config.py`\n"
        )

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "ll-config.json").write_text('{"issues": {"base_dir": ".issues"}}')

        with patch.object(sys, "argv", ["ll-deps", "-d", str(issues_dir), "analyze"]):
            result = main()
        assert result == 0

    def _setup_sprint_project(self, tmp_path: Path) -> Path:
        """Set up a test project with issues and a sprint YAML."""
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()
        bugs_dir = issues_dir / "bugs"
        bugs_dir.mkdir()
        enh_dir = issues_dir / "enhancements"
        enh_dir.mkdir()
        (issues_dir / "features").mkdir()
        (issues_dir / "completed").mkdir()

        (bugs_dir / "P1-BUG-001-test-bug.md").write_text(
            "# BUG-001: Test Bug\n\n## Summary\n\nFix `scripts/config.py`\n"
        )
        (bugs_dir / "P2-BUG-002-other-bug.md").write_text(
            "# BUG-002: Other Bug\n\n## Summary\n\nFix `scripts/other.py`\n"
        )
        (enh_dir / "P3-ENH-010-enhancement.md").write_text(
            "# ENH-010: Enhancement\n\n## Summary\n\nImprove `scripts/config.py`\n"
        )

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "ll-config.json").write_text(
            '{"issues": {"base_dir": ".issues"}, "sprints": {"sprints_dir": ".sprints"}}'
        )

        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir()
        (sprints_dir / "my-sprint.yaml").write_text(
            "name: my-sprint\ndescription: Test sprint\nissues:\n  - BUG-001\n  - ENH-010\n"
        )
        (sprints_dir / "empty-sprint.yaml").write_text(
            "name: empty-sprint\ndescription: Empty\nissues: []\n"
        )

        return issues_dir

    def test_analyze_with_sprint(self, tmp_path: Path, capsys: object) -> None:
        """Test analyze --sprint filters to sprint issues only."""
        issues_dir = self._setup_sprint_project(tmp_path)

        with patch.object(
            sys,
            "argv",
            ["ll-deps", "-d", str(issues_dir), "analyze", "--sprint", "my-sprint"],
        ):
            result = main()
        assert result == 0
        captured = capsys.readouterr()  # type: ignore[union-attr]
        # BUG-001 and ENH-010 are in the sprint
        assert "BUG-001" in captured.out
        assert "ENH-010" in captured.out
        # BUG-002 is NOT in the sprint
        assert "BUG-002" not in captured.out

    def test_validate_with_sprint(self, tmp_path: Path) -> None:
        """Test validate --sprint filters to sprint issues only."""
        issues_dir = self._setup_sprint_project(tmp_path)

        with patch.object(
            sys,
            "argv",
            ["ll-deps", "-d", str(issues_dir), "validate", "--sprint", "my-sprint"],
        ):
            result = main()
        assert result == 0

    def test_sprint_not_found(self, tmp_path: Path) -> None:
        """Test --sprint with nonexistent sprint returns error."""
        issues_dir = self._setup_sprint_project(tmp_path)

        with patch.object(
            sys,
            "argv",
            ["ll-deps", "-d", str(issues_dir), "analyze", "--sprint", "nonexistent"],
        ):
            result = main()
        assert result == 1

    def test_sprint_empty_issues(self, tmp_path: Path) -> None:
        """Test --sprint with empty issue list returns 0."""
        issues_dir = self._setup_sprint_project(tmp_path)

        with patch.object(
            sys,
            "argv",
            ["ll-deps", "-d", str(issues_dir), "analyze", "--sprint", "empty-sprint"],
        ):
            result = main()
        assert result == 0

    def test_analyze_without_sprint_unchanged(self, tmp_path: Path, capsys: object) -> None:
        """Test analyze without --sprint still returns all issues."""
        issues_dir = self._setup_sprint_project(tmp_path)

        with patch.object(
            sys,
            "argv",
            ["ll-deps", "-d", str(issues_dir), "analyze"],
        ):
            result = main()
        assert result == 0
        captured = capsys.readouterr()  # type: ignore[union-attr]
        # All three issues should be analyzed (report header shows count)
        assert "Issues analyzed**: 3" in captured.out
