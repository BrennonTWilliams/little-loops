"""Tests for git_operations module - specifically get_untracked_files."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.git_operations import get_untracked_files


class TestGetUntrackedFiles:
    """Tests for get_untracked_files function."""

    def test_returns_empty_list_when_no_untracked_files(self, tmp_path: Path) -> None:
        """Returns empty list when git status shows no untracked files."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

            result = get_untracked_files(tmp_path)

        assert result == []

    def test_returns_untracked_files(self, tmp_path: Path) -> None:
        """Returns list of untracked files from git status."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="?? file1.txt\n?? file2.py\n?? dir/file3.md\n",
                stderr="",
            )

            result = get_untracked_files(tmp_path)

        assert result == ["dir/file3.md", "file1.txt", "file2.py"]

    def test_handles_files_with_spaces(self, tmp_path: Path) -> None:
        """Handles quoted filenames containing spaces."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            # Git quotes filenames with spaces
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='?? "file with spaces.txt"\n?? normal.txt\n',
                stderr="",
            )

            result = get_untracked_files(tmp_path)

        assert "file with spaces.txt" in result
        assert "normal.txt" in result

    def test_handles_special_characters(self, tmp_path: Path) -> None:
        """Handles files with special characters in names."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="?? file-with-dash.txt\n?? file_underscore.py\n?? file.multiple.dots.md\n",
                stderr="",
            )

            result = get_untracked_files(tmp_path)

        assert "file-with-dash.txt" in result
        assert "file_underscore.py" in result
        assert "file.multiple.dots.md" in result

    def test_ignores_non_untracked_status(self, tmp_path: Path) -> None:
        """Only extracts files with ?? status (untracked), ignores others."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            # Git porcelain format includes various status codes:
            # M = modified, A = added, D = deleted, ?? = untracked
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=" M modified.txt\nA  staged.txt\n D deleted.txt\n?? untracked.txt\nAM both.py\n",
                stderr="",
            )

            result = get_untracked_files(tmp_path)

        assert result == ["untracked.txt"]

    def test_returns_empty_on_git_failure(self, tmp_path: Path) -> None:
        """Returns empty list when git command fails."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=128, cmd=["git", "status", "--porcelain"]
            )

            result = get_untracked_files(tmp_path)

        assert result == []

    def test_returns_empty_on_file_not_found(self, tmp_path: Path) -> None:
        """Returns empty list when git executable is not found."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("git not found")

            result = get_untracked_files(tmp_path)

        assert result == []

    def test_returns_sorted_files(self, tmp_path: Path) -> None:
        """Returns files in sorted order."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="?? zebra.txt\n?? alpha.txt\n?? middle.txt\n",
                stderr="",
            )

            result = get_untracked_files(tmp_path)

        assert result == ["alpha.txt", "middle.txt", "zebra.txt"]

    def test_uses_correct_cwd(self, tmp_path: Path) -> None:
        """Verifies repo_root is used as the working directory."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

            get_untracked_files(tmp_path)

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == tmp_path.resolve()

    def test_handles_empty_lines_in_output(self, tmp_path: Path) -> None:
        """Handles empty lines in git output gracefully."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="\n?? file.txt\n\n?? other.txt\n\n",
                stderr="",
            )

            result = get_untracked_files(tmp_path)

        assert result == ["file.txt", "other.txt"]

    def test_default_repo_root(self) -> None:
        """Uses current directory when repo_root not specified."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

            get_untracked_files()

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == Path(".").resolve()

    def test_correct_git_command(self, tmp_path: Path) -> None:
        """Verifies correct git command is executed."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

            get_untracked_files(tmp_path)

        call_args = mock_run.call_args[0][0]
        assert call_args == ["git", "status", "--porcelain"]

    @pytest.mark.parametrize(
        "stdout,expected",
        [
            ("", []),
            ("?? single.txt\n", ["single.txt"]),
            ("?? a.txt\n?? b.txt\n", ["a.txt", "b.txt"]),
            ('?? "has spaces.txt"\n', ["has spaces.txt"]),
            (" M modified.txt\n", []),
        ],
        ids=["empty", "single", "multiple", "quoted", "modified_only"],
    )
    def test_various_outputs(
        self, tmp_path: Path, stdout: str, expected: list[str]
    ) -> None:
        """Parametrized test for various git output scenarios."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=stdout, stderr=""
            )

            result = get_untracked_files(tmp_path)

        assert result == expected
