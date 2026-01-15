"""Tests for gitignore suggestion functionality."""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.git_operations import (
    GitignorePattern,
    GitignoreSuggestion,
    _file_matches_pattern,
    _is_already_ignored,
    _read_existing_gitignore,
    add_patterns_to_gitignore,
    suggest_gitignore_patterns,
)


class TestGitignorePattern:
    """Test GitignorePattern dataclass."""

    def test_creation(self) -> None:
        """Test basic pattern creation."""
        pattern = GitignorePattern(
            pattern="*.log",
            category="logs",
            description="Log files",
        )
        assert pattern.pattern == "*.log"
        assert pattern.category == "logs"
        assert pattern.is_wildcard is True
        assert pattern.is_directory is False

    def test_directory_pattern(self) -> None:
        """Test directory pattern detection."""
        pattern = GitignorePattern(
            pattern="node_modules/",
            category="nodejs",
            description="Node deps",
        )
        assert pattern.is_directory is True

    def test_empty_pattern_raises(self) -> None:
        """Test that empty pattern raises ValueError."""
        with pytest.raises(ValueError, match="Pattern cannot be empty"):
            GitignorePattern(pattern="", category="test", description="test")


class TestGitignoreSuggestion:
    """Test GitignoreSuggestion dataclass."""

    def test_empty_suggestion(self) -> None:
        """Test empty suggestion has no suggestions."""
        suggestion = GitignoreSuggestion()
        assert not suggestion.has_suggestions
        assert suggestion.files_to_ignore == []
        assert "No .gitignore suggestions needed" in suggestion.summary

    def test_suggestion_with_patterns(self) -> None:
        """Test suggestion with patterns."""
        pattern1 = GitignorePattern(
            pattern="*.log",
            category="logs",
            description="Log files",
            files_matched=["debug.log", "error.log"],
        )
        pattern2 = GitignorePattern(
            pattern="coverage.json",
            category="coverage",
            description="Coverage report",
            files_matched=["coverage.json"],
        )
        suggestion = GitignoreSuggestion(
            patterns=[pattern1, pattern2],
            total_files=3,
        )
        assert suggestion.has_suggestions
        assert len(suggestion.files_to_ignore) == 3
        assert "3 file(s)" in suggestion.summary


class TestFileMatchesPattern:
    """Test pattern matching logic."""

    @pytest.mark.parametrize(
        "file,pattern,expected",
        [
            # Exact matches
            ("coverage.json", "coverage.json", True),
            ("debug.log", "*.log", True),
            ("error.log", "*.log", True),
            ("test.py", "*.log", False),
            # Directory patterns
            ("node_modules/lodash/index.js", "node_modules/", True),
            ("node_modules/", "node_modules/", True),
            ("other/file.js", "node_modules/", False),
            # Root-anchored patterns
            ("/.env", ".env", True),
            ("config/.env", "/.env", False),
            # Wildcards in path
            ("test.pyc", "*.pyc", True),
            ("src/test.pyc", "*.pyc", True),
            # Basename matching (no / in pattern)
            ("debug.log", "*.log", True),
            ("logs/debug.log", "*.log", True),
            # Exact file vs wildcard
            (".env.local", ".env.local", True),
            (".env.local", ".env.*", True),
        ],
    )
    def test_matches(self, file: str, pattern: str, expected: bool) -> None:
        """Test various pattern matching scenarios."""
        assert _file_matches_pattern(file, pattern) is expected


class TestReadExistingGitignore:
    """Test reading .gitignore file."""

    def test_no_gitignore(self, tmp_path: Path) -> None:
        """Test with no .gitignore file."""
        patterns = _read_existing_gitignore(tmp_path)
        assert patterns == []

    def test_empty_gitignore(self, tmp_path: Path) -> None:
        """Test with empty .gitignore file."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("")
        patterns = _read_existing_gitignore(tmp_path)
        assert patterns == []

    def test_gitignore_with_comments_and_empty_lines(self, tmp_path: Path) -> None:
        """Test .gitignore with comments and empty lines."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text(
            "# Comment\n\n*.log\n\n# Another comment\nnode_modules/\n"
        )
        patterns = _read_existing_gitignore(tmp_path)
        assert patterns == ["*.log", "node_modules/"]

    def test_gitignore_with_patterns(self, tmp_path: Path) -> None:
        """Test .gitignore with patterns."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\nnode_modules/\n.env\n")
        patterns = _read_existing_gitignore(tmp_path)
        assert patterns == ["*.log", "node_modules/", ".env"]


class TestSuggestGitignorePatterns:
    """Test main suggestion function."""

    def test_no_untracked_files(self, tmp_path: Path) -> None:
        """Test with no untracked files."""
        result = suggest_gitignore_patterns(
            untracked_files=[],
            repo_root=tmp_path,
        )
        assert not result.has_suggestions
        assert result.total_files == 0

    def test_coverage_json(self, tmp_path: Path) -> None:
        """Test coverage.json suggestion."""
        result = suggest_gitignore_patterns(
            untracked_files=["coverage.json"],
            repo_root=tmp_path,
        )
        assert result.has_suggestions
        assert len(result.patterns) == 1
        assert result.patterns[0].pattern == "coverage.json"
        assert "coverage.json" in result.patterns[0].files_matched

    def test_multiple_files_same_category(self, tmp_path: Path) -> None:
        """Test multiple log files suggest single *.log pattern."""
        result = suggest_gitignore_patterns(
            untracked_files=["debug.log", "error.log", "access.log"],
            repo_root=tmp_path,
        )
        assert result.has_suggestions
        log_patterns = [p for p in result.patterns if p.category == "logs"]
        assert len(log_patterns) == 1
        assert log_patterns[0].pattern == "*.log"
        assert len(log_patterns[0].files_matched) == 3

    def test_already_ignored(self, tmp_path: Path) -> None:
        """Test that existing .gitignore patterns are respected."""
        # Create .gitignore with *.log pattern
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\n")

        result = suggest_gitignore_patterns(
            untracked_files=["debug.log", "coverage.json"],
            repo_root=tmp_path,
        )
        assert result.has_suggestions
        # Only coverage.json should be suggested
        assert len(result.patterns) == 1
        assert result.patterns[0].pattern == "coverage.json"
        assert "debug.log" in result.already_ignored

    def test_multiple_categories(self, tmp_path: Path) -> None:
        """Test files from different categories."""
        result = suggest_gitignore_patterns(
            untracked_files=["coverage.json", "debug.log", ".env"],
            repo_root=tmp_path,
        )
        assert result.has_suggestions
        # Should have patterns for each category
        categories = {p.category for p in result.patterns}
        assert "coverage" in categories
        assert "logs" in categories
        assert "environment" in categories


class TestAddPatternsToGitignore:
    """Test adding patterns to .gitignore."""

    def test_create_new_gitignore(self, tmp_path: Path) -> None:
        """Test creating new .gitignore file."""
        success = add_patterns_to_gitignore(
            patterns=["*.log", "coverage.json"],
            repo_root=tmp_path,
            logger=None,
        )
        assert success

        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()
        assert "*.log" in content
        assert "coverage.json" in content

    def test_append_to_existing(self, tmp_path: Path) -> None:
        """Test appending to existing .gitignore."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("node_modules/\n")

        success = add_patterns_to_gitignore(
            patterns=["*.log"],
            repo_root=tmp_path,
            logger=None,
        )
        assert success

        content = gitignore.read_text()
        assert "node_modules/" in content
        assert "*.log" in content

    def test_skip_duplicates(self, tmp_path: Path) -> None:
        """Test that duplicate patterns are skipped."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\n")

        success = add_patterns_to_gitignore(
            patterns=["*.log", "coverage.json"],
            repo_root=tmp_path,
            logger=None,
        )
        assert success

        content = gitignore.read_text()
        # Should only have one *.log
        assert content.count("*.log") == 1
        assert "coverage.json" in content

    def test_backup_creation(self, tmp_path: Path) -> None:
        """Test that backup is created when requested."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("node_modules/\n")

        success = add_patterns_to_gitignore(
            patterns=["*.log"],
            repo_root=tmp_path,
            logger=None,
            backup=True,
        )
        assert success

        backup = tmp_path / ".gitignore.backup"
        assert backup.exists()
        assert backup.read_text() == "node_modules/\n"


class TestNegationPatterns:
    """Test gitignore negation pattern support."""

    def test_file_matches_negation_pattern(self) -> None:
        """Test that _file_matches_pattern handles negation patterns correctly."""
        # Negation patterns should match the same as their base pattern
        assert _file_matches_pattern("important.log", "!important.log") is True
        assert _file_matches_pattern("debug.log", "!important.log") is False
        assert _file_matches_pattern("important.log", "!*.log") is True

    def test_is_already_ignored_simple_negation(self) -> None:
        """Test simple negation pattern: *.log but !important.log."""
        patterns = ["*.log", "!important.log"]

        # debug.log should be ignored (matches *.log, no negation matches)
        assert _is_already_ignored("debug.log", patterns) is True

        # important.log should NOT be ignored (matches *.log, then negated)
        assert _is_already_ignored("important.log", patterns) is False

        # test.py should NOT be ignored (doesn't match *.log at all)
        assert _is_already_ignored("test.py", patterns) is False

    def test_is_already_ignored_negation_only_applies_if_base_matches(self) -> None:
        """Test that negation only applies if the base pattern would match."""
        patterns = ["*.log", "!important.log"]

        # A file that doesn't match *.log is not affected by negation
        assert _is_already_ignored("README.md", patterns) is False
        assert _is_already_ignored("notes.txt", patterns) is False

    def test_is_already_ignored_wildcard_negation(self) -> None:
        """Test wildcard negation patterns."""
        patterns = ["*.log", "!important*.log"]

        # debug.log should be ignored
        assert _is_already_ignored("debug.log", patterns) is True

        # important.log should NOT be ignored (negated by wildcard)
        assert _is_already_ignored("important.log", patterns) is False

        # important-debug.log should also NOT be ignored
        assert _is_already_ignored("important-debug.log", patterns) is False

        # build.log should be ignored
        assert _is_already_ignored("build.log", patterns) is True

    def test_is_already_ignored_directory_negation(self) -> None:
        """Test directory negation patterns."""
        patterns = ["logs/", "!logs/important/"]

        # logs/debug.log should be ignored
        assert _is_already_ignored("logs/debug.log", patterns) is True

        # logs/important/file.txt should NOT be ignored
        assert _is_already_ignored("logs/important/file.txt", patterns) is False

        # other/file.txt should NOT be ignored
        assert _is_already_ignored("other/file.txt", patterns) is False

    def test_is_already_ignored_multiple_negations(self) -> None:
        """Test multiple negation patterns in sequence."""
        patterns = ["*.log", "!important.log", "!debug.log"]

        # error.log should be ignored
        assert _is_already_ignored("error.log", patterns) is True

        # important.log should NOT be ignored
        assert _is_already_ignored("important.log", patterns) is False

        # debug.log should NOT be ignored
        assert _is_already_ignored("debug.log", patterns) is False

    def test_is_already_ignored_ignore_after_negation(self) -> None:
        """Test that an ignore pattern after negation can re-ignore."""
        patterns = ["*.log", "!important.log", "*.log"]

        # With duplicate *.log, important.log ends up ignored again
        # because the last *.log pattern re-matches it
        assert _is_already_ignored("important.log", patterns) is True

        # debug.log is still ignored
        assert _is_already_ignored("debug.log", patterns) is True

    def test_is_already_ignored_root_anchored_negation(self) -> None:
        """Test root-anchored negation patterns."""
        patterns = ["*.log", "!/important.log"]

        # important.log at root should NOT be ignored
        assert _is_already_ignored("important.log", patterns) is False

        # logs/important.log should still be ignored (negation is root-anchored)
        assert _is_already_ignored("logs/important.log", patterns) is True

    def test_is_already_ignored_empty_pattern_list(self) -> None:
        """Test with empty pattern list."""
        assert _is_already_ignored("any-file.log", []) is False
        assert _is_already_ignored("important.log", []) is False

    def test_is_already_ignored_only_negation_patterns(self) -> None:
        """Test with only negation patterns (no base ignore patterns)."""
        patterns = ["!important.log", "!debug.log"]

        # With only negation patterns, nothing is ignored
        assert _is_already_ignored("important.log", patterns) is False
        assert _is_already_ignored("debug.log", patterns) is False
        assert _is_already_ignored("error.log", patterns) is False

    def test_suggest_respects_negation_patterns(self, tmp_path: Path) -> None:
        """Test that suggest_gitignore_patterns respects negation patterns."""
        # Create .gitignore with negation pattern
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\n!important.log\n")

        result = suggest_gitignore_patterns(
            untracked_files=["debug.log", "important.log", "test.log"],
            repo_root=tmp_path,
        )

        # debug.log and test.log should be in already_ignored
        assert "debug.log" in result.already_ignored
        assert "test.log" in result.already_ignored

        # important.log should NOT be in already_ignored (negated)
        assert "important.log" not in result.already_ignored

    def test_negation_pattern_detection_in_matches(self) -> None:
        """Test that negation patterns are detected correctly during matching."""
        # Test the basic pattern matching with negation prefix
        # The function should return True for match (regardless of ! prefix)
        assert _file_matches_pattern("file.log", "!*.log") is True
        assert _file_matches_pattern("file.txt", "!*.log") is False
        assert _file_matches_pattern("important.log", "!important.log") is True
