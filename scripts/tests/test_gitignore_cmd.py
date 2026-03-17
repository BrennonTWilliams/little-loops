"""Tests for cli/gitignore.py - ll-gitignore CLI entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from little_loops.cli.gitignore import main_gitignore
from little_loops.git_operations import GitignorePattern, GitignoreSuggestion


def _make_suggestion(patterns: list[GitignorePattern] | None = None) -> GitignoreSuggestion:
    """Build a GitignoreSuggestion with optional patterns."""
    return GitignoreSuggestion(
        patterns=patterns or [],
        total_files=len(patterns) if patterns else 0,
    )


class TestMainGitignoreDryRun:
    """Tests for ll-gitignore --dry-run mode."""

    def test_dry_run_no_suggestions_returns_0(self) -> None:
        """Returns 0 and exits cleanly when no suggestions found."""
        empty = _make_suggestion()
        with (
            patch("sys.argv", ["ll-gitignore", "--dry-run"]),
            patch("little_loops.cli.gitignore.suggest_gitignore_patterns", return_value=empty),
        ):
            result = main_gitignore()
        assert result == 0

    def test_dry_run_with_suggestions_returns_0(self) -> None:
        """Returns 0 and does not call add_patterns_to_gitignore in dry-run mode."""
        patterns = [
            GitignorePattern(
                pattern="*.log",
                category="logs",
                description="Log files",
                files_matched=["app.log"],
            )
        ]
        suggestion = _make_suggestion(patterns)

        with (
            patch("sys.argv", ["ll-gitignore", "--dry-run"]),
            patch("little_loops.cli.gitignore.suggest_gitignore_patterns", return_value=suggestion),
            patch("little_loops.cli.gitignore.add_patterns_to_gitignore") as mock_add,
        ):
            result = main_gitignore()

        assert result == 0
        mock_add.assert_not_called()

    def test_dry_run_does_not_modify_gitignore(self) -> None:
        """--dry-run never writes to .gitignore."""
        patterns = [
            GitignorePattern(
                pattern=".env",
                category="environment",
                description="Environment files",
                files_matched=[".env"],
            )
        ]
        suggestion = _make_suggestion(patterns)

        with (
            patch("sys.argv", ["ll-gitignore", "--dry-run"]),
            patch("little_loops.cli.gitignore.suggest_gitignore_patterns", return_value=suggestion),
            patch("little_loops.cli.gitignore.add_patterns_to_gitignore") as mock_add,
        ):
            main_gitignore()

        mock_add.assert_not_called()


class TestMainGitignoreApply:
    """Tests for ll-gitignore apply mode (no --dry-run)."""

    def test_no_suggestions_returns_0(self) -> None:
        """Returns 0 when no suggestions found without --dry-run."""
        empty = _make_suggestion()
        with (
            patch("sys.argv", ["ll-gitignore"]),
            patch("little_loops.cli.gitignore.suggest_gitignore_patterns", return_value=empty),
            patch("little_loops.cli.gitignore.add_patterns_to_gitignore") as mock_add,
        ):
            result = main_gitignore()

        assert result == 0
        mock_add.assert_not_called()

    def test_with_suggestions_calls_add_patterns(self) -> None:
        """Calls add_patterns_to_gitignore with all suggested pattern strings."""
        patterns = [
            GitignorePattern(
                pattern="*.log",
                category="logs",
                description="Log files",
                files_matched=["app.log"],
            ),
            GitignorePattern(
                pattern=".env",
                category="environment",
                description="Environment files",
                files_matched=[".env"],
            ),
        ]
        suggestion = _make_suggestion(patterns)

        with (
            patch("sys.argv", ["ll-gitignore"]),
            patch("little_loops.cli.gitignore.suggest_gitignore_patterns", return_value=suggestion),
            patch(
                "little_loops.cli.gitignore.add_patterns_to_gitignore", return_value=True
            ) as mock_add,
        ):
            result = main_gitignore()

        assert result == 0
        mock_add.assert_called_once()
        call_patterns = mock_add.call_args[0][0]
        assert call_patterns == ["*.log", ".env"]

    def test_add_failure_returns_1(self) -> None:
        """Returns 1 when add_patterns_to_gitignore fails."""
        patterns = [
            GitignorePattern(
                pattern="*.log",
                category="logs",
                description="Log files",
                files_matched=["app.log"],
            )
        ]
        suggestion = _make_suggestion(patterns)

        with (
            patch("sys.argv", ["ll-gitignore"]),
            patch("little_loops.cli.gitignore.suggest_gitignore_patterns", return_value=suggestion),
            patch("little_loops.cli.gitignore.add_patterns_to_gitignore", return_value=False),
        ):
            result = main_gitignore()

        assert result == 1

    def test_passes_repo_root_to_suggest(self) -> None:
        """Passes --config path as repo_root to suggest_gitignore_patterns."""
        empty = _make_suggestion()

        with (
            patch("sys.argv", ["ll-gitignore", "--config", "/some/path"]),
            patch(
                "little_loops.cli.gitignore.suggest_gitignore_patterns", return_value=empty
            ) as mock_suggest,
        ):
            main_gitignore()

        call_kwargs = mock_suggest.call_args[1]
        assert call_kwargs["repo_root"] == Path("/some/path")

    def test_passes_repo_root_to_add_patterns(self) -> None:
        """Passes --config path as repo_root to add_patterns_to_gitignore."""
        patterns = [
            GitignorePattern(
                pattern="*.log",
                category="logs",
                description="Log files",
                files_matched=["app.log"],
            )
        ]
        suggestion = _make_suggestion(patterns)

        with (
            patch("sys.argv", ["ll-gitignore", "--config", "/some/path"]),
            patch("little_loops.cli.gitignore.suggest_gitignore_patterns", return_value=suggestion),
            patch(
                "little_loops.cli.gitignore.add_patterns_to_gitignore", return_value=True
            ) as mock_add,
        ):
            main_gitignore()

        call_kwargs = mock_add.call_args[1]
        assert call_kwargs["repo_root"] == Path("/some/path")
