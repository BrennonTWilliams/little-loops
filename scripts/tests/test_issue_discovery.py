"""Tests for little_loops.issue_discovery module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from little_loops.config import BRConfig
from little_loops.issue_discovery import (
    FindingMatch,
    MatchClassification,
    RegressionEvidence,
    _calculate_word_overlap,
    _extract_completion_date,
    _extract_file_paths,
    _extract_files_changed,
    _extract_fix_commit,
    _extract_line_numbers,
    _extract_words,
    _matches_issue_type,
    _normalize_text,
    detect_regression_or_duplicate,
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
            "run_cmd": None,
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
            "ready_command": "ready-issue {{issue_id}}",
            "manage_command": "manage-issue {{issue_type}} {{action}} {{issue_id}}",
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

## Proposed Solution
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
            source_command="audit-architecture",
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
            source_command="audit-docs",
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
            source_command="audit-architecture",
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


class TestMatchesIssueType:
    """Tests for _matches_issue_type helper function."""

    def test_matches_bug_type(self, temp_project_dir: Path) -> None:
        """Test matching BUG type to bugs directory."""
        config = BRConfig(temp_project_dir)

        bug_path = temp_project_dir / ".issues/bugs/P1-BUG-001-test.md"
        assert _matches_issue_type("BUG", bug_path, config, False) is True
        assert _matches_issue_type("FEAT", bug_path, config, False) is False
        assert _matches_issue_type("ENH", bug_path, config, False) is False

    def test_matches_feat_type(self, temp_project_dir: Path) -> None:
        """Test matching FEAT type to features directory."""
        config = BRConfig(temp_project_dir)

        feat_path = temp_project_dir / ".issues/features/P2-FEAT-001-test.md"
        assert _matches_issue_type("FEAT", feat_path, config, False) is True
        assert _matches_issue_type("BUG", feat_path, config, False) is False
        assert _matches_issue_type("ENH", feat_path, config, False) is False

    def test_matches_enh_type(self, temp_project_dir: Path) -> None:
        """Test matching ENH type to enhancements directory."""
        config = BRConfig(temp_project_dir)

        enh_path = temp_project_dir / ".issues/enhancements/P2-ENH-001-test.md"
        assert _matches_issue_type("ENH", enh_path, config, False) is True
        assert _matches_issue_type("BUG", enh_path, config, False) is False
        assert _matches_issue_type("FEAT", enh_path, config, False) is False

    def test_completed_always_matches(self, temp_project_dir: Path) -> None:
        """Test that completed issues match any type."""
        config = BRConfig(temp_project_dir)

        completed_path = temp_project_dir / ".issues/completed/P1-BUG-001-test.md"

        # Any type matches when is_completed=True
        assert _matches_issue_type("BUG", completed_path, config, True) is True
        assert _matches_issue_type("FEAT", completed_path, config, True) is True
        assert _matches_issue_type("ENH", completed_path, config, True) is True
        assert _matches_issue_type("CUSTOM", completed_path, config, True) is True

    def test_custom_type_with_custom_config(self, temp_project_dir: Path) -> None:
        """Test matching custom DOC type with configured category."""
        # Create config with custom DOC category
        config_data = {
            "issues": {
                "categories": {
                    "documentation": {
                        "prefix": "DOC",
                        "dir": "documentation",
                        "action": "document",
                    },
                }
            }
        }
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config_data))

        config = BRConfig(temp_project_dir)
        doc_path = temp_project_dir / ".issues/documentation/P2-DOC-001-readme.md"

        # DOC matches documentation dir
        assert _matches_issue_type("DOC", doc_path, config, False) is True
        # Other types don't match
        assert _matches_issue_type("BUG", doc_path, config, False) is False
        assert _matches_issue_type("FEAT", doc_path, config, False) is False

        # Required categories still work
        bug_path = temp_project_dir / ".issues/bugs/P1-BUG-001-test.md"
        assert _matches_issue_type("BUG", bug_path, config, False) is True

    def test_unknown_type_no_match(self, temp_project_dir: Path) -> None:
        """Test that unknown types don't match any directory."""
        config = BRConfig(temp_project_dir)

        bug_path = temp_project_dir / ".issues/bugs/P1-BUG-001-test.md"
        feat_path = temp_project_dir / ".issues/features/P2-FEAT-001-test.md"

        # Unknown type doesn't match anything
        assert _matches_issue_type("UNKNOWN", bug_path, config, False) is False
        assert _matches_issue_type("UNKNOWN", feat_path, config, False) is False


class TestMatchClassification:
    """Tests for MatchClassification enum."""

    def test_classification_values(self) -> None:
        """Test classification enum values."""
        assert MatchClassification.NEW_ISSUE.value == "new_issue"
        assert MatchClassification.DUPLICATE.value == "duplicate"
        assert MatchClassification.REGRESSION.value == "regression"
        assert MatchClassification.INVALID_FIX.value == "invalid_fix"
        assert MatchClassification.UNVERIFIED.value == "unverified"


class TestRegressionEvidence:
    """Tests for RegressionEvidence dataclass."""

    def test_default_values(self) -> None:
        """Test default values for RegressionEvidence."""
        evidence = RegressionEvidence()
        assert evidence.fix_commit_sha is None
        assert evidence.fix_commit_exists is True
        assert evidence.files_modified_since_fix == []
        assert evidence.days_since_fix == 0
        assert evidence.related_commits == []

    def test_with_values(self) -> None:
        """Test RegressionEvidence with values."""
        evidence = RegressionEvidence(
            fix_commit_sha="abc123",
            fix_commit_exists=True,
            files_modified_since_fix=["src/module.py"],
            days_since_fix=30,
            related_commits=["def456"],
        )
        assert evidence.fix_commit_sha == "abc123"
        assert evidence.fix_commit_exists is True
        assert evidence.files_modified_since_fix == ["src/module.py"]
        assert evidence.days_since_fix == 30
        assert evidence.related_commits == ["def456"]


class TestFindingMatchRegressionProperties:
    """Tests for FindingMatch regression-related properties."""

    def test_should_reopen_as_regression(self) -> None:
        """Test should_reopen_as_regression property."""
        match = FindingMatch(
            issue_path=Path("completed/test.md"),
            match_type="exact",
            match_score=0.85,
            is_completed=True,
            classification=MatchClassification.REGRESSION,
        )
        assert match.should_reopen_as_regression is True
        assert match.should_reopen_as_invalid_fix is False
        assert match.is_unverified is False

    def test_should_reopen_as_invalid_fix(self) -> None:
        """Test should_reopen_as_invalid_fix property."""
        match = FindingMatch(
            issue_path=Path("completed/test.md"),
            match_type="exact",
            match_score=0.85,
            is_completed=True,
            classification=MatchClassification.INVALID_FIX,
        )
        assert match.should_reopen_as_regression is False
        assert match.should_reopen_as_invalid_fix is True
        assert match.is_unverified is False

    def test_is_unverified(self) -> None:
        """Test is_unverified property."""
        match = FindingMatch(
            issue_path=Path("completed/test.md"),
            match_type="exact",
            match_score=0.85,
            is_completed=True,
            classification=MatchClassification.UNVERIFIED,
        )
        assert match.should_reopen_as_regression is False
        assert match.should_reopen_as_invalid_fix is False
        assert match.is_unverified is True

    def test_active_issue_not_regression(self) -> None:
        """Test that active issues don't trigger regression properties."""
        match = FindingMatch(
            issue_path=Path("bugs/test.md"),
            match_type="exact",
            match_score=0.85,
            is_completed=False,
            classification=MatchClassification.DUPLICATE,
        )
        assert match.should_reopen_as_regression is False
        assert match.should_reopen_as_invalid_fix is False
        assert match.is_unverified is False

    def test_low_score_not_regression(self) -> None:
        """Test that low-score matches don't trigger regression properties."""
        match = FindingMatch(
            issue_path=Path("completed/test.md"),
            match_type="content",
            match_score=0.3,
            is_completed=True,
            classification=MatchClassification.REGRESSION,
        )
        # Score is too low (< 0.5) so should_reopen is False
        assert match.should_reopen_as_regression is False


class TestGitHistoryExtraction:
    """Tests for git history extraction helper functions."""

    def test_extract_fix_commit_found(self) -> None:
        """Test extracting fix commit SHA from content."""
        content = """## Resolution
- **Fix Commit**: abc123def456
- **Completed**: 2024-01-15
"""
        assert _extract_fix_commit(content) == "abc123def456"

    def test_extract_fix_commit_short_sha(self) -> None:
        """Test extracting short fix commit SHA."""
        content = "- **Fix Commit**: abc1234"
        assert _extract_fix_commit(content) == "abc1234"

    def test_extract_fix_commit_not_found(self) -> None:
        """Test when fix commit is not present."""
        content = """## Resolution
- **Completed**: 2024-01-15
"""
        assert _extract_fix_commit(content) is None

    def test_extract_files_changed(self) -> None:
        """Test extracting files changed from content."""
        content = """### Files Changed
  - `src/module.py`
  - `src/utils.py`
  - `tests/test_module.py`
"""
        files = _extract_files_changed(content)
        assert "src/module.py" in files
        assert "src/utils.py" in files
        assert "tests/test_module.py" in files

    def test_extract_files_changed_empty(self) -> None:
        """Test when no files changed section exists."""
        content = """## Resolution
- **Completed**: 2024-01-15
"""
        files = _extract_files_changed(content)
        assert files == []

    def test_extract_files_changed_skips_placeholder(self) -> None:
        """Test that placeholder text is skipped."""
        content = """### Files Changed
- See git history for details
"""
        files = _extract_files_changed(content)
        assert files == []

    def test_extract_completion_date_completed(self) -> None:
        """Test extracting completion date."""
        content = "- **Completed**: 2024-01-15"
        date = _extract_completion_date(content)
        assert date is not None
        assert date.year == 2024
        assert date.month == 1
        assert date.day == 15

    def test_extract_completion_date_closed(self) -> None:
        """Test extracting closed date."""
        content = "- **Closed**: 2024-06-30"
        date = _extract_completion_date(content)
        assert date is not None
        assert date.year == 2024
        assert date.month == 6
        assert date.day == 30

    def test_extract_completion_date_not_found(self) -> None:
        """Test when no completion date exists."""
        content = "No date here"
        assert _extract_completion_date(content) is None


class TestDetectRegressionOrDuplicate:
    """Tests for detect_regression_or_duplicate function."""

    @pytest.fixture
    def completed_issue_with_fix(self, temp_project_dir: Path) -> Path:
        """Create a completed issue with fix commit metadata."""
        completed_dir = temp_project_dir / ".issues" / "completed"
        completed_dir.mkdir(parents=True, exist_ok=True)

        issue_path = completed_dir / "P1-BUG-010-test-fix.md"
        issue_path.write_text("""# BUG-010: Test issue with fix

## Summary
A test issue that was fixed.

---

## Resolution

- **Action**: fix
- **Completed**: 2024-01-15
- **Status**: Completed
- **Fix Commit**: abc123def456789

### Files Changed
  - `src/module.py`
  - `src/utils.py`
""")
        return issue_path

    @pytest.fixture
    def completed_issue_no_fix_commit(self, temp_project_dir: Path) -> Path:
        """Create a completed issue without fix commit metadata."""
        completed_dir = temp_project_dir / ".issues" / "completed"
        completed_dir.mkdir(parents=True, exist_ok=True)

        issue_path = completed_dir / "P2-BUG-011-no-fix-commit.md"
        issue_path.write_text("""# BUG-011: Old issue without fix tracking

## Summary
An old issue that was fixed before fix tracking was added.

---

## Resolution

- **Action**: fix
- **Completed**: 2023-06-01
- **Status**: Completed

### Files Changed
- See git history for details
""")
        return issue_path

    def test_unverified_when_no_fix_commit(
        self, temp_project_dir: Path, completed_issue_no_fix_commit: Path
    ) -> None:
        """Test UNVERIFIED classification when no fix commit tracked."""
        config = BRConfig(temp_project_dir)

        classification, evidence = detect_regression_or_duplicate(
            config, completed_issue_no_fix_commit
        )

        assert classification == MatchClassification.UNVERIFIED
        assert evidence.fix_commit_sha is None

    def test_invalid_fix_when_commit_not_in_history(self, temp_project_dir: Path) -> None:
        """Test INVALID_FIX when fix commit doesn't exist in git history."""
        completed_dir = temp_project_dir / ".issues" / "completed"
        completed_dir.mkdir(parents=True, exist_ok=True)

        issue_path = completed_dir / "P2-BUG-012-no-files.md"
        issue_path.write_text("""# BUG-012: Issue with non-existent fix commit

---

## Resolution

- **Fix Commit**: abc123def
- **Completed**: 2024-01-15

### Files Changed
  - `src/module.py`
""")

        config = BRConfig(temp_project_dir)
        classification, evidence = detect_regression_or_duplicate(config, issue_path)

        # Fix commit exists in metadata but not in git history = INVALID_FIX
        # (the fix was never merged or was rebased away)
        assert classification == MatchClassification.INVALID_FIX
        assert evidence.fix_commit_sha == "abc123def"
        assert evidence.fix_commit_exists is False

    def test_evidence_populated(
        self, temp_project_dir: Path, completed_issue_with_fix: Path
    ) -> None:
        """Test that evidence is populated from issue content."""
        config = BRConfig(temp_project_dir)

        classification, evidence = detect_regression_or_duplicate(config, completed_issue_with_fix)

        # Fix commit SHA should be extracted from the issue content
        assert evidence.fix_commit_sha == "abc123def456789"
        # Classification will be INVALID_FIX since the fake SHA doesn't exist in git history
        # This is correct behavior - if the commit doesn't exist, it was never merged
        assert classification == MatchClassification.INVALID_FIX
        assert evidence.fix_commit_exists is False

    def test_nonexistent_file_returns_unverified(self, temp_project_dir: Path) -> None:
        """Test that nonexistent file returns UNVERIFIED."""
        config = BRConfig(temp_project_dir)
        fake_path = temp_project_dir / ".issues" / "completed" / "fake.md"

        classification, evidence = detect_regression_or_duplicate(config, fake_path)

        assert classification == MatchClassification.UNVERIFIED


class TestReopenIssueWithClassification:
    """Tests for reopen_issue with classification support."""

    def test_reopen_as_regression_adds_section(
        self, temp_project_dir: Path, issues_with_content: Path
    ) -> None:
        """Test that reopening as regression adds proper section."""
        config = BRConfig(temp_project_dir)
        logger = Logger()

        # Create a new completed issue for this test
        completed_dir = temp_project_dir / ".issues" / "completed"
        completed_path = completed_dir / "P1-BUG-020-regression-test.md"
        completed_path.write_text("""# BUG-020: Regression test issue

## Summary
Test issue for regression reopening.
""")

        evidence = RegressionEvidence(
            fix_commit_sha="abc123",
            files_modified_since_fix=["src/module.py"],
            related_commits=["def456"],
            days_since_fix=30,
        )

        new_path = reopen_issue(
            config,
            completed_path,
            reopen_reason="Bug reappeared after refactoring",
            new_context="Error occurs again in production.",
            source_command="verify-issues",
            logger=logger,
            classification=MatchClassification.REGRESSION,
            regression_evidence=evidence,
        )

        assert new_path is not None
        content = new_path.read_text()
        assert "## Regression" in content
        assert "Regression (fix was broken by later changes)" in content
        assert "Original Fix Commit" in content
        assert "abc123" in content
        assert "Files Modified Since Fix" in content
        assert "src/module.py" in content

    def test_reopen_as_invalid_fix_adds_section(
        self, temp_project_dir: Path, issues_with_content: Path
    ) -> None:
        """Test that reopening as invalid fix adds proper section."""
        config = BRConfig(temp_project_dir)
        logger = Logger()

        # Create a new completed issue for this test
        completed_dir = temp_project_dir / ".issues" / "completed"
        completed_path = completed_dir / "P1-BUG-021-invalid-fix-test.md"
        completed_path.write_text("""# BUG-021: Invalid fix test issue

## Summary
Test issue for invalid fix reopening.
""")

        evidence = RegressionEvidence(
            fix_commit_sha="xyz789",
            fix_commit_exists=False,
        )

        new_path = reopen_issue(
            config,
            completed_path,
            reopen_reason="Original fix never worked",
            new_context="Bug was never actually fixed.",
            source_command="ready-issue",
            logger=logger,
            classification=MatchClassification.INVALID_FIX,
            regression_evidence=evidence,
        )

        assert new_path is not None
        content = new_path.read_text()
        assert "## Reopened (Invalid Fix)" in content
        assert "Invalid Fix (original fix never resolved the issue)" in content
        assert "Fix commit not found in history" in content
