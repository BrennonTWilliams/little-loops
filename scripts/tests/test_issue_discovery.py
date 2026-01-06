"""Tests for little_loops.issue_discovery module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from little_loops.config import BRConfig
from little_loops.issue_discovery import (
    FindingMatch,
    _calculate_word_overlap,
    _extract_file_paths,
    _extract_line_numbers,
    _extract_words,
    _normalize_text,
    find_existing_issue,
    reopen_issue,
    search_issues_by_content,
    search_issues_by_file_path,
    update_existing_issue,
)
from little_loops.logger import Logger


@pytest.fixture
def sample_config_with_enh() -> dict[str, Any]:
    """Sample configuration with all three issue categories."""
    return {
        "project": {
            "name": "test-project",
            "src_dir": "src/",
            "test_cmd": "pytest tests/",
            "lint_cmd": "ruff check .",
            "type_cmd": "mypy src/",
            "format_cmd": "ruff format .",
            "build_cmd": None,
        },
        "issues": {
            "base_dir": ".issues",
            "categories": {
                "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
            },
            "completed_dir": "completed",
            "priorities": ["P0", "P1", "P2", "P3", "P4", "P5"],
        },
        "automation": {
            "timeout_seconds": 1800,
            "state_file": ".test-state.json",
            "worktree_base": ".worktrees",
            "max_workers": 2,
            "stream_output": False,
        },
        "parallel": {
            "max_workers": 3,
            "p0_sequential": True,
            "worktree_base": ".worktrees",
            "state_file": ".parallel-state.json",
            "timeout_seconds": 1800,
            "max_merge_retries": 2,
            "stream_output": False,
            "command_prefix": "/ll:",
            "ready_command": "ready_issue {{issue_id}}",
            "manage_command": "manage_issue {{issue_type}} {{action}} {{issue_id}}",
        },
    }


@pytest.fixture
def issues_with_content(temp_project_dir: Path, sample_config_with_enh: dict[str, Any]) -> Path:
    """Create issue directories with sample issues containing detailed content."""
    # Write config
    config_path = temp_project_dir / ".claude" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config_with_enh))

    issues_base = temp_project_dir / ".issues"
    bugs_dir = issues_base / "bugs"
    enh_dir = issues_base / "enhancements"
    features_dir = issues_base / "features"
    completed_dir = issues_base / "completed"

    bugs_dir.mkdir(parents=True)
    enh_dir.mkdir(parents=True)
    features_dir.mkdir(parents=True)
    completed_dir.mkdir(parents=True)

    # Bug with file path reference
    (
        bugs_dir / "P1-BUG-001-circular-dependency.md"
    ).write_text("""# BUG-001: Circular dependency in auth module

## Summary
There is a circular import between auth.py and users.py.

## Location
- **File**: `src/auth.py`
- **Line(s)**: 15-20

## Current Behavior
ImportError when loading auth module.
""")

    # Enhancement with code snippet
    (enh_dir / "P2-ENH-001-refactor-services.md").write_text("""# ENH-001: Refactor services.py

## Summary
The services.py file has grown too large and should be split.

## Location
- **File**: `src/services.py`
- **Line(s)**: 1-850

## Proposed Fix
Split into smaller modules by responsibility.
""")

    # Completed issue
    (completed_dir / "P2-ENH-002-old-refactor.md").write_text("""# ENH-002: Old refactoring task

## Summary
This was a previous refactoring task for utils.py.

## Location
- **File**: `src/utils.py`

## Resolution
Completed on 2024-01-01.
""")

    return issues_base


class TestFindingMatch:
    """Tests for FindingMatch dataclass."""

    def test_should_skip_high_score(self) -> None:
        """Test should_skip returns True for high score."""
        match = FindingMatch(
            issue_path=Path("test.md"),
            match_type="exact",
            match_score=0.85,
        )
        assert match.should_skip is True
        assert match.should_update is False
        assert match.should_create is False

    def test_should_update_medium_score(self) -> None:
        """Test should_update returns True for medium score."""
        match = FindingMatch(
            issue_path=Path("test.md"),
            match_type="similar",
            match_score=0.6,
        )
        assert match.should_skip is False
        assert match.should_update is True
        assert match.should_create is False

    def test_should_create_low_score(self) -> None:
        """Test should_create returns True for low score."""
        match = FindingMatch(
            issue_path=None,
            match_type="none",
            match_score=0.2,
        )
        assert match.should_skip is False
        assert match.should_update is False
        assert match.should_create is True

    def test_should_reopen_completed_with_score(self) -> None:
        """Test should_reopen for completed issues with sufficient score."""
        match = FindingMatch(
            issue_path=Path("completed/test.md"),
            match_type="exact",
            match_score=0.7,
            is_completed=True,
        )
        assert match.should_reopen is True

    def test_should_not_reopen_active_issue(self) -> None:
        """Test should_reopen returns False for active issues."""
        match = FindingMatch(
            issue_path=Path("bugs/test.md"),
            match_type="exact",
            match_score=0.9,
            is_completed=False,
        )
        assert match.should_reopen is False


class TestTextHelpers:
    """Tests for text processing helper functions."""

    def test_normalize_text(self) -> None:
        """Test text normalization."""
        assert _normalize_text("  Hello   World  ") == "hello world"
        assert _normalize_text("UPPERCASE") == "uppercase"

    def test_extract_words(self) -> None:
        """Test word extraction."""
        words = _extract_words("The quick brown fox jumps over the lazy dog")
        assert "quick" in words
        assert "brown" in words
        assert "fox" in words
        # Common words should be filtered
        assert "the" not in words
        # Short words filtered
        assert "is" not in words

    def test_extract_words_filters_common(self) -> None:
        """Test that common words are filtered out."""
        words = _extract_words("This is a test file with code and issues")
        assert "test" in words
        # "file", "code", "issue" are in common words list
        assert "file" not in words
        assert "code" not in words

    def test_calculate_word_overlap_identical(self) -> None:
        """Test word overlap for identical sets."""
        words = {"quick", "brown", "fox"}
        assert _calculate_word_overlap(words, words) == 1.0

    def test_calculate_word_overlap_disjoint(self) -> None:
        """Test word overlap for disjoint sets."""
        words1 = {"quick", "brown"}
        words2 = {"slow", "green"}
        assert _calculate_word_overlap(words1, words2) == 0.0

    def test_calculate_word_overlap_partial(self) -> None:
        """Test word overlap for partial matches."""
        words1 = {"quick", "brown", "fox"}
        words2 = {"quick", "red", "fox"}
        # Intersection: {quick, fox}, Union: {quick, brown, fox, red}
        # 2/4 = 0.5
        assert _calculate_word_overlap(words1, words2) == 0.5

    def test_calculate_word_overlap_empty(self) -> None:
        """Test word overlap with empty sets."""
        assert _calculate_word_overlap(set(), {"word"}) == 0.0
        assert _calculate_word_overlap({"word"}, set()) == 0.0

    def test_extract_file_paths(self) -> None:
        """Test file path extraction from text."""
        text = """
        The bug is in `src/module.py` at line 42.
        **File**: `path/to/file.js`
        Also check src/utils.py for related code.
        """
        paths = _extract_file_paths(text)
        assert "src/module.py" in paths
        assert "path/to/file.js" in paths
        assert "src/utils.py" in paths

    def test_extract_line_numbers(self) -> None:
        """Test line number extraction from text."""
        text = """
        **Line(s)**: 42-45
        See line 100 for details.
        Also check src/file.py:20-30
        """
        numbers = _extract_line_numbers(text)
        assert 42 in numbers
        assert 45 in numbers
        assert 100 in numbers
        assert 20 in numbers
        assert 30 in numbers


class TestSearchIssuesByFilePath:
    """Tests for search_issues_by_file_path function."""

    def test_find_issue_by_exact_path(
        self, temp_project_dir: Path, issues_with_content: Path
    ) -> None:
        """Test finding issue by exact file path."""
        config = BRConfig(temp_project_dir)

        results = search_issues_by_file_path(config, "src/auth.py")

        assert len(results) >= 1
        paths = [str(r[0]) for r in results]
        assert any("BUG-001" in p for p in paths)

    def test_find_issue_by_filename_only(
        self, temp_project_dir: Path, issues_with_content: Path
    ) -> None:
        """Test finding issue by filename without full path."""
        config = BRConfig(temp_project_dir)

        results = search_issues_by_file_path(config, "services.py")

        assert len(results) >= 1
        paths = [str(r[0]) for r in results]
        assert any("ENH-001" in p for p in paths)

    def test_includes_completed_by_default(
        self, temp_project_dir: Path, issues_with_content: Path
    ) -> None:
        """Test that completed issues are included by default."""
        config = BRConfig(temp_project_dir)

        results = search_issues_by_file_path(config, "utils.py", include_completed=True)

        assert len(results) >= 1
        # Should find the completed ENH-002
        paths = [str(r[0]) for r in results]
        assert any("ENH-002" in p for p in paths)

    def test_excludes_completed_when_requested(
        self, temp_project_dir: Path, issues_with_content: Path
    ) -> None:
        """Test excluding completed issues."""
        config = BRConfig(temp_project_dir)

        results = search_issues_by_file_path(config, "utils.py", include_completed=False)

        # Should not find ENH-002 since it's completed
        paths = [str(r[0]) for r in results]
        assert not any("ENH-002" in p for p in paths)


class TestSearchIssuesByContent:
    """Tests for search_issues_by_content function."""

    def test_find_issue_by_content_terms(
        self, temp_project_dir: Path, issues_with_content: Path
    ) -> None:
        """Test finding issues by content search terms."""
        config = BRConfig(temp_project_dir)

        results = search_issues_by_content(config, ["circular", "import", "dependency"])

        assert len(results) >= 1
        # BUG-001 should rank high
        top_path = str(results[0][0])
        assert "BUG-001" in top_path

    def test_results_sorted_by_relevance(
        self, temp_project_dir: Path, issues_with_content: Path
    ) -> None:
        """Test that results are sorted by score descending."""
        config = BRConfig(temp_project_dir)

        results = search_issues_by_content(config, ["refactor", "split", "services"])

        if len(results) > 1:
            scores = [r[1] for r in results]
            assert scores == sorted(scores, reverse=True)


class TestFindExistingIssue:
    """Tests for find_existing_issue function."""

    def test_exact_path_match(self, temp_project_dir: Path, issues_with_content: Path) -> None:
        """Test finding issue with exact file path match."""
        config = BRConfig(temp_project_dir)

        match = find_existing_issue(
            config,
            finding_type="BUG",
            file_path="src/auth.py",
            finding_title="Auth circular dependency",
            finding_content="ImportError in auth module",
        )

        assert match.match_type == "exact"
        assert match.match_score >= 0.8
        assert match.issue_path is not None
        assert "BUG-001" in str(match.issue_path)

    def test_no_match_for_new_finding(
        self, temp_project_dir: Path, issues_with_content: Path
    ) -> None:
        """Test no match for completely new finding."""
        config = BRConfig(temp_project_dir)

        match = find_existing_issue(
            config,
            finding_type="BUG",
            file_path="src/brand_new_file.py",
            finding_title="Completely new issue",
            finding_content="This is a brand new problem nobody has seen.",
        )

        assert match.match_score < 0.5
        assert match.should_create is True

    def test_finds_completed_issue_for_reopen(
        self, temp_project_dir: Path, issues_with_content: Path
    ) -> None:
        """Test finding a completed issue that might need reopening."""
        config = BRConfig(temp_project_dir)

        match = find_existing_issue(
            config,
            finding_type="ENH",
            file_path="src/utils.py",
            finding_title="Refactor utils module",
            finding_content="The utils.py needs refactoring again.",
        )

        # Should find the completed ENH-002
        if match.issue_path and "ENH-002" in str(match.issue_path):
            assert match.is_completed is True


class TestReopenIssue:
    """Tests for reopen_issue function."""

    def test_reopen_moves_to_active_dir(
        self, temp_project_dir: Path, issues_with_content: Path
    ) -> None:
        """Test that reopening moves issue from completed to active."""
        config = BRConfig(temp_project_dir)
        logger = Logger()

        completed_path = temp_project_dir / ".issues" / "completed" / "P2-ENH-002-old-refactor.md"
        assert completed_path.exists()

        new_path = reopen_issue(
            config,
            completed_path,
            reopen_reason="Problem recurred",
            new_context="The utils.py file has grown again.",
            source_command="audit_architecture",
            logger=logger,
        )

        assert new_path is not None
        assert new_path.exists()
        assert "enhancements" in str(new_path)
        assert not completed_path.exists()

    def test_reopen_adds_section(self, temp_project_dir: Path, issues_with_content: Path) -> None:
        """Test that reopening adds a Reopened section."""
        config = BRConfig(temp_project_dir)
        logger = Logger()

        completed_path = temp_project_dir / ".issues" / "completed" / "P2-ENH-002-old-refactor.md"

        new_path = reopen_issue(
            config,
            completed_path,
            reopen_reason="Regression detected",
            new_context="New findings here.",
            source_command="audit_docs",
            logger=logger,
        )

        assert new_path is not None
        content = new_path.read_text()
        assert "## Reopened" in content
        assert "Regression detected" in content
        assert "New findings here." in content

    def test_reopen_nonexistent_fails(
        self, temp_project_dir: Path, issues_with_content: Path
    ) -> None:
        """Test that reopening nonexistent file returns None."""
        config = BRConfig(temp_project_dir)
        logger = Logger()

        nonexistent = temp_project_dir / ".issues" / "completed" / "P0-BUG-999-fake.md"

        result = reopen_issue(
            config,
            nonexistent,
            reopen_reason="Test",
            new_context="Test",
            source_command="test",
            logger=logger,
        )

        assert result is None


class TestUpdateExistingIssue:
    """Tests for update_existing_issue function."""

    def test_update_adds_section(self, temp_project_dir: Path, issues_with_content: Path) -> None:
        """Test that updating adds a new section."""
        config = BRConfig(temp_project_dir)
        logger = Logger()

        issue_path = temp_project_dir / ".issues" / "bugs" / "P1-BUG-001-circular-dependency.md"

        result = update_existing_issue(
            config,
            issue_path,
            update_section_name="Architecture Audit Results",
            update_content="Found additional context about this issue.",
            source_command="audit_architecture",
            logger=logger,
        )

        assert result is True
        content = issue_path.read_text()
        assert "## Architecture Audit Results" in content
        assert "Found additional context" in content

    def test_update_skips_existing_section(
        self, temp_project_dir: Path, issues_with_content: Path
    ) -> None:
        """Test that updating doesn't duplicate sections."""
        config = BRConfig(temp_project_dir)
        logger = Logger()

        issue_path = temp_project_dir / ".issues" / "bugs" / "P1-BUG-001-circular-dependency.md"

        # First update
        update_existing_issue(
            config,
            issue_path,
            update_section_name="Test Section",
            update_content="First update",
            source_command="test",
            logger=logger,
        )

        # Second update with same section name
        update_existing_issue(
            config,
            issue_path,
            update_section_name="Test Section",
            update_content="Second update",
            source_command="test",
            logger=logger,
        )

        content = issue_path.read_text()
        # Should only have one Test Section
        assert content.count("## Test Section") == 1
