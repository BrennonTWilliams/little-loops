"""Tests for merge coordinator stash and conflict handling."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.parallel.merge_coordinator import MergeCoordinator
from little_loops.parallel.types import MergeRequest, ParallelConfig, WorkerResult


@pytest.fixture
def temp_git_repo() -> Path:
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            capture_output=True,
        )

        # Create initial commit
        test_file = repo_path / "test.txt"
        test_file.write_text("initial content")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial commit"],
            cwd=repo_path,
            capture_output=True,
        )

        yield repo_path


@pytest.fixture
def mock_logger() -> MagicMock:
    """Create a mock logger."""
    logger = MagicMock()
    return logger


@pytest.fixture
def default_config() -> ParallelConfig:
    """Create default parallel config."""
    return ParallelConfig(
        max_workers=2,
        p0_sequential=True,
        worktree_base=".worktrees",
        state_file=".parallel-state.json",
        timeout_per_issue=1800,
        max_merge_retries=2,
        include_p0=False,
        stream_subprocess_output=False,
        command_prefix="/ll:",
        ready_command="ready_issue {{issue_id}}",
        manage_command="manage_issue {{issue_type}} {{action}} {{issue_id}}",
    )


class TestIsLocalChangesError:
    """Tests for _is_local_changes_error detection."""

    def test_detects_local_changes_overwritten_error(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should detect 'local changes would be overwritten' error."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        error_message = """error: Your local changes to the following files would be overwritten by merge:
        docs/blender-abstractions.md
Please commit your changes or stash them before you merge.
Aborting
Merge with strategy ort failed."""

        assert coordinator._is_local_changes_error(error_message) is True

    def test_detects_stash_suggestion_error(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should detect error suggesting to stash changes."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        error_message = (
            "Please commit your changes or stash them before you merge."
        )

        assert coordinator._is_local_changes_error(error_message) is True

    def test_detects_unstaged_changes_error(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should detect rebase error due to unstaged changes."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        error_message = "error: cannot pull with rebase: You have unstaged changes"

        assert coordinator._is_local_changes_error(error_message) is True

    def test_does_not_match_unrelated_error(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should not match unrelated git errors."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        error_message = "fatal: not a git repository"

        assert coordinator._is_local_changes_error(error_message) is False

    def test_does_not_match_conflict_error(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should not match merge conflict errors."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        error_message = "CONFLICT (content): Merge conflict in file.txt"

        assert coordinator._is_local_changes_error(error_message) is False


class TestStashLocalChanges:
    """Tests for _stash_local_changes functionality."""

    def test_returns_false_when_clean(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should return False when working tree is clean."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        result = coordinator._stash_local_changes()

        assert result is False
        assert coordinator._stash_active is False

    def test_stashes_uncommitted_changes(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should stash uncommitted changes and return True."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create uncommitted change
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("modified content")

        result = coordinator._stash_local_changes()

        assert result is True
        assert coordinator._stash_active is True

        # Verify file was reverted
        assert test_file.read_text() == "initial content"

    def test_stashes_untracked_files(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should handle untracked files (they appear in porcelain output)."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create untracked file
        new_file = temp_git_repo / "new_file.txt"
        new_file.write_text("new content")

        result = coordinator._stash_local_changes()

        # Untracked files are detected but may not be stashed by default
        # The important thing is we don't error
        assert isinstance(result, bool)


class TestPopStash:
    """Tests for _pop_stash functionality."""

    def test_does_nothing_when_no_stash(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should do nothing when stash is not active."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)
        coordinator._stash_active = False

        # Should not raise
        coordinator._pop_stash()

        assert coordinator._stash_active is False

    def test_restores_stashed_changes(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should restore stashed changes."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create and stash change
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("modified content")
        coordinator._stash_local_changes()

        # Verify stashed
        assert test_file.read_text() == "initial content"

        # Pop stash
        coordinator._pop_stash()

        # Verify restored
        assert test_file.read_text() == "modified content"
        assert coordinator._stash_active is False


class TestProcessMergeStashIntegration:
    """Integration tests for stash handling in _process_merge."""

    def test_stash_popped_on_success(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Stash should be popped even after successful merge."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create a feature branch with changes
        subprocess.run(
            ["git", "checkout", "-b", "parallel/test-branch"],
            cwd=temp_git_repo,
            capture_output=True,
        )
        feature_file = temp_git_repo / "feature.txt"
        feature_file.write_text("feature content")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add feature"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        # Go back to main and create local change
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=temp_git_repo,
            capture_output=True,
        )
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("local modification")

        # Create a fake worktree path (different from repo to avoid cleanup issues)
        fake_worktree = temp_git_repo / ".worktrees" / "fake-worktree"
        fake_worktree.mkdir(parents=True)

        # Create mock worker result
        worker_result = WorkerResult(
            issue_id="TEST-001",
            branch_name="parallel/test-branch",
            worktree_path=fake_worktree,
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)

        # Process merge
        coordinator._process_merge(request)

        # Local changes should be restored
        assert test_file.read_text() == "local modification"
        assert coordinator._stash_active is False

    def test_stash_popped_on_failure(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Stash should be popped even after failed merge."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create local change
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("local modification")

        # Create a fake worktree path
        fake_worktree = temp_git_repo / ".worktrees" / "fake-worktree"
        fake_worktree.mkdir(parents=True)

        # Create mock worker result with non-existent branch
        worker_result = WorkerResult(
            issue_id="TEST-001",
            branch_name="parallel/nonexistent-branch",
            worktree_path=fake_worktree,
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)

        # Process merge (will fail)
        coordinator._process_merge(request)

        # Local changes should still be restored
        assert test_file.read_text() == "local modification"
        assert coordinator._stash_active is False
