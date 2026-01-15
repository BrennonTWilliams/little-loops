"""Tests for gitignore suggestion functionality."""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.git_operations import (
    GitignorePattern,
    GitignoreSuggestion,
    _file_matches_pattern,
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
