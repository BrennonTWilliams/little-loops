"""Tests for work_verification.py - work verification utilities.

Tests cover:
- filter_excluded_files function
- verify_work_was_done with provided changed_files
- verify_work_was_done with git-based detection
- Edge cases and exception handling
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from little_loops.work_verification import (
    EXCLUDED_DIRECTORIES,
    filter_excluded_files,
    verify_work_was_done,
)


class TestExcludedDirectories:
    """Tests for EXCLUDED_DIRECTORIES constant."""

    def test_excluded_directories_contains_issues(self) -> None:
        """EXCLUDED_DIRECTORIES includes .issues/ directory."""
        assert ".issues/" in EXCLUDED_DIRECTORIES

    def test_excluded_directories_contains_thoughts(self) -> None:
        """EXCLUDED_DIRECTORIES includes thoughts/ directory."""
        assert "thoughts/" in EXCLUDED_DIRECTORIES

    def test_excluded_directories_contains_worktrees(self) -> None:
        """EXCLUDED_DIRECTORIES includes .worktrees/ directory."""
        assert ".worktrees/" in EXCLUDED_DIRECTORIES

    def test_excluded_directories_contains_speckit(self) -> None:
        """EXCLUDED_DIRECTORIES includes .speckit/ directory."""
        assert ".speckit/" in EXCLUDED_DIRECTORIES

    def test_excluded_directories_contains_auto_manage(self) -> None:
        """EXCLUDED_DIRECTORIES includes .auto-manage directory."""
        assert ".auto-manage" in EXCLUDED_DIRECTORIES


class TestFilterExcludedFiles:
    """Tests for filter_excluded_files function."""

    def test_filters_issues_directory(self) -> None:
        """Files in .issues/ directory are filtered out."""
        files = [".issues/bugs/BUG-001.md", "src/main.py"]
        result = filter_excluded_files(files)
        assert result == ["src/main.py"]

    def test_filters_thoughts_directory(self) -> None:
        """Files in thoughts/ directory are filtered out."""
        files = ["thoughts/notes.md", "src/main.py"]
        result = filter_excluded_files(files)
        assert result == ["src/main.py"]

    def test_filters_worktrees_directory(self) -> None:
        """Files in .worktrees/ directory are filtered out."""
        files = [".worktrees/worker-001/file.py", "src/main.py"]
        result = filter_excluded_files(files)
        assert result == ["src/main.py"]

    def test_filters_speckit_directory(self) -> None:
        """Files in .speckit/ directory are filtered out."""
        files = [".speckit/config.yaml", "src/main.py"]
        result = filter_excluded_files(files)
        assert result == ["src/main.py"]

    def test_filters_auto_manage_directory(self) -> None:
        """Files in .auto-manage directory are filtered out."""
        files = [".auto-manage/state.json", "src/main.py"]
        result = filter_excluded_files(files)
        assert result == ["src/main.py"]

    def test_keeps_non_excluded_files(self) -> None:
        """Non-excluded files are kept in the result."""
        files = ["src/main.py", "tests/test_main.py", "README.md"]
        result = filter_excluded_files(files)
        assert result == ["src/main.py", "tests/test_main.py", "README.md"]

    def test_filters_multiple_excluded_dirs(self) -> None:
        """Multiple files in excluded directories are all filtered out."""
        files = [
            ".issues/bugs/BUG-001.md",
            "thoughts/notes.md",
            ".worktrees/worker/file.py",
            "src/main.py",
        ]
        result = filter_excluded_files(files)
        assert result == ["src/main.py"]

    def test_empty_list_returns_empty(self) -> None:
        """Empty input list returns empty list."""
        result = filter_excluded_files([])
        assert result == []

    def test_all_excluded_returns_empty(self) -> None:
        """List with only excluded files returns empty list."""
        files = [".issues/bugs/BUG-001.md", "thoughts/notes.md"]
        result = filter_excluded_files(files)
        assert result == []

    def test_filters_empty_strings(self) -> None:
        """Empty strings in input are filtered out."""
        files = ["", "src/main.py", ""]
        result = filter_excluded_files(files)
        assert result == ["src/main.py"]

    def test_nested_excluded_paths(self) -> None:
        """Deeply nested paths in excluded directories are filtered."""
        files = [
            ".issues/completed/archived/old/BUG-001.md",
            "thoughts/scratch/deep/nested/notes.md",
            "src/deep/nested/module.py",
        ]
        result = filter_excluded_files(files)
        assert result == ["src/deep/nested/module.py"]

    def test_similar_but_not_excluded_paths(self) -> None:
        """Paths similar to excluded directories but not starting with them are kept."""
        files = [
            "my_issues/BUG-001.md",
            "my_thoughts/notes.md",
            "data/.issues_backup/file.md",
        ]
        result = filter_excluded_files(files)
        assert result == files  # All should be kept


class TestVerifyWorkWasDoneWithProvidedFiles:
    """Tests for verify_work_was_done when changed_files is provided."""

    @pytest.fixture
    def mock_logger(self) -> MagicMock:
        """Create a mock logger."""
        return MagicMock()

    def test_with_meaningful_changes_returns_true(self, mock_logger: MagicMock) -> None:
        """Returns True when meaningful changes are provided."""
        changed_files = ["src/main.py", "tests/test_main.py"]
        result = verify_work_was_done(mock_logger, changed_files)
        assert result is True
        mock_logger.info.assert_called()

    def test_only_excluded_files_returns_false(self, mock_logger: MagicMock) -> None:
        """Returns False when only excluded files are changed."""
        changed_files = [".issues/bugs/BUG-001.md", "thoughts/notes.md"]
        result = verify_work_was_done(mock_logger, changed_files)
        assert result is False
        mock_logger.warning.assert_called()

    def test_warning_includes_excluded_files(self, mock_logger: MagicMock) -> None:
        """Warning message includes which excluded files were detected."""
        changed_files = [".issues/bugs/BUG-001.md", "thoughts/notes.md"]
        verify_work_was_done(mock_logger, changed_files)
        mock_logger.warning.assert_called()
        call_args = str(mock_logger.warning.call_args)
        assert ".issues/bugs/BUG-001.md" in call_args
        assert "thoughts/notes.md" in call_args

    def test_warning_truncates_long_file_list(self, mock_logger: MagicMock) -> None:
        """Warning truncates file list to first 10 when many excluded files."""
        changed_files = [f".issues/bugs/BUG-{i:03d}.md" for i in range(15)]
        verify_work_was_done(mock_logger, changed_files)
        mock_logger.warning.assert_called()
        call_args = str(mock_logger.warning.call_args)
        # Should only show first 10
        assert "BUG-000" in call_args
        assert "BUG-009" in call_args
        # Should NOT include files beyond the first 10
        assert "BUG-014" not in call_args

    def test_empty_list_returns_false(self, mock_logger: MagicMock) -> None:
        """Returns False when empty list is provided."""
        result = verify_work_was_done(mock_logger, [])
        assert result is False
        mock_logger.warning.assert_called()

    def test_mixed_files_returns_true(self, mock_logger: MagicMock) -> None:
        """Returns True when mix of excluded and meaningful files."""
        changed_files = [".issues/bugs/BUG-001.md", "src/main.py"]
        result = verify_work_was_done(mock_logger, changed_files)
        assert result is True

    def test_logs_info_with_file_count(self, mock_logger: MagicMock) -> None:
        """Logs info message with count of changed files."""
        changed_files = ["src/main.py", "src/utils.py", "tests/test_main.py"]
        verify_work_was_done(mock_logger, changed_files)
        mock_logger.info.assert_called()
        call_args = str(mock_logger.info.call_args)
        assert "3" in call_args

    def test_truncates_file_list_in_log(self, mock_logger: MagicMock) -> None:
        """File list in log message is truncated to 5 files."""
        changed_files = [
            "src/a.py",
            "src/b.py",
            "src/c.py",
            "src/d.py",
            "src/e.py",
            "src/f.py",
            "src/g.py",
        ]
        verify_work_was_done(mock_logger, changed_files)
        mock_logger.info.assert_called()
        call_args = str(mock_logger.info.call_args)
        # Should show 7 files changed but only list first 5
        assert "7" in call_args

    def test_single_file_returns_true(self, mock_logger: MagicMock) -> None:
        """Returns True with single meaningful file."""
        result = verify_work_was_done(mock_logger, ["src/main.py"])
        assert result is True


class TestVerifyWorkWasDoneWithGitDetection:
    """Tests for verify_work_was_done when using git-based detection."""

    @pytest.fixture
    def mock_logger(self) -> MagicMock:
        """Create a mock logger."""
        return MagicMock()

    def test_unstaged_changes_detected(self, mock_logger: MagicMock) -> None:
        """Returns True when unstaged changes are detected via git diff."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="src/main.py\nsrc/utils.py\n", stderr=""
            )

            result = verify_work_was_done(mock_logger)

        assert result is True
        mock_logger.info.assert_called()
        mock_run.assert_called()

    def test_staged_changes_detected(self, mock_logger: MagicMock) -> None:
        """Returns True when staged changes are detected via git diff --cached."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                # First call: git diff --name-only (no unstaged changes)
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
                # Second call: git diff --cached --name-only (staged changes)
                subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="src/feature.py\n", stderr=""
                ),
            ]

            result = verify_work_was_done(mock_logger)

        assert result is True
        mock_logger.info.assert_called()

    def test_no_changes_returns_false(self, mock_logger: MagicMock) -> None:
        """Returns False when no changes detected in git."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

            result = verify_work_was_done(mock_logger)

        assert result is False
        mock_logger.warning.assert_called()
        call_args = str(mock_logger.warning.call_args)
        assert "no files modified" in call_args

    def test_only_excluded_files_in_git_returns_false(self, mock_logger: MagicMock) -> None:
        """Returns False when git only shows excluded files changed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=".issues/bugs/BUG-001.md\nthoughts/notes.md\n",
                stderr="",
            )

            result = verify_work_was_done(mock_logger)

        assert result is False

    def test_git_warning_includes_excluded_files(self, mock_logger: MagicMock) -> None:
        """Warning message from git detection includes excluded file names."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=".issues/bugs/BUG-123.md\nthoughts/plan.md\n",
                stderr="",
            )

            verify_work_was_done(mock_logger)

        mock_logger.warning.assert_called()
        call_args = str(mock_logger.warning.call_args)
        assert ".issues/bugs/BUG-123.md" in call_args
        assert "thoughts/plan.md" in call_args

    def test_git_diff_command_is_called_correctly(self, mock_logger: MagicMock) -> None:
        """Verifies correct git diff commands are executed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

            verify_work_was_done(mock_logger)

        # Should be called twice: unstaged and staged
        assert mock_run.call_count == 2
        calls = mock_run.call_args_list
        # First call: git diff --name-only
        assert calls[0][0][0] == ["git", "diff", "--name-only"]
        # Second call: git diff --cached --name-only
        assert calls[1][0][0] == ["git", "diff", "--cached", "--name-only"]

    def test_git_error_returns_false(self, mock_logger: MagicMock) -> None:
        """Returns False when git command fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=128, stdout="", stderr="fatal: not a git repository"
            )

            result = verify_work_was_done(mock_logger)

        assert result is False

    def test_exception_returns_false(self, mock_logger: MagicMock) -> None:
        """Returns False when an exception occurs during git operations."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = OSError("Git not found")

            result = verify_work_was_done(mock_logger)

        assert result is False
        mock_logger.error.assert_called()

    def test_file_not_found_exception_returns_false(self, mock_logger: MagicMock) -> None:
        """Returns False when git binary is not found."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("git not found")

            result = verify_work_was_done(mock_logger)

        assert result is False
        mock_logger.error.assert_called()

    def test_logs_error_on_exception(self, mock_logger: MagicMock) -> None:
        """Error message is logged when exception occurs."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = OSError("Permission denied")

            verify_work_was_done(mock_logger)

        mock_logger.error.assert_called()
        call_args = str(mock_logger.error.call_args)
        assert "Permission denied" in call_args

    def test_markdown_files_count_as_work(self, mock_logger: MagicMock) -> None:
        """Markdown files outside excluded dirs count as meaningful work."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="README.md\nCHANGELOG.md\n", stderr=""
            )

            result = verify_work_was_done(mock_logger)

        assert result is True

    def test_first_diff_has_changes_skips_second(self, mock_logger: MagicMock) -> None:
        """When unstaged changes are found, staged check may not be needed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="src/main.py\n", stderr=""
            )

            result = verify_work_was_done(mock_logger)

        assert result is True
        # Only called once since first check found changes
        assert mock_run.call_count == 1

    def test_handles_whitespace_only_output(self, mock_logger: MagicMock) -> None:
        """Handles git output that is just whitespace."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="\n\n  \n", stderr=""
            )

            result = verify_work_was_done(mock_logger)

        assert result is False

    def test_mixed_unstaged_and_staged(self, mock_logger: MagicMock) -> None:
        """Returns True when only excluded unstaged but meaningful staged."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                # First call: only excluded files unstaged
                subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=".issues/bugs/BUG-001.md\n", stderr=""
                ),
                # Second call: meaningful staged files
                subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="src/fix.py\n", stderr=""
                ),
            ]

            result = verify_work_was_done(mock_logger)

        assert result is True


class TestVerifyWorkWasDoneIntegration:
    """Integration-style tests for verify_work_was_done."""

    @pytest.fixture
    def mock_logger(self) -> MagicMock:
        """Create a mock logger."""
        return MagicMock()

    def test_none_changed_files_triggers_git_detection(self, mock_logger: MagicMock) -> None:
        """When changed_files is None, git-based detection is used."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="src/main.py\n", stderr=""
            )

            result = verify_work_was_done(mock_logger, changed_files=None)

        assert result is True
        mock_run.assert_called()

    def test_explicit_empty_list_does_not_trigger_git(self, mock_logger: MagicMock) -> None:
        """When changed_files is empty list, git is not called."""
        with patch("subprocess.run") as mock_run:
            result = verify_work_was_done(mock_logger, changed_files=[])

        assert result is False
        mock_run.assert_not_called()
