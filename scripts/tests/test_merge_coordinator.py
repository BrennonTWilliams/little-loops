"""Tests for merge coordinator stash and conflict handling."""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from little_loops.parallel.merge_coordinator import MergeCoordinator
from little_loops.parallel.types import MergeRequest, ParallelConfig, WorkerResult


@pytest.fixture
def temp_git_repo() -> Generator[Path, None, None]:
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
        worktree_base=Path(".worktrees"),
        state_file=Path(".parallel-state.json"),
        timeout_per_issue=1800,
        max_merge_retries=2,
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

        error_message = "Please commit your changes or stash them before you merge."

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


class TestIsUntrackedFilesError:
    """Tests for _is_untracked_files_error detection."""

    def test_detects_untracked_files_error(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should detect 'untracked working tree files would be overwritten' error."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        error_message = """error: The following untracked working tree files would be overwritten by merge:
        tests/unit/ai/ooda/test_constraint_validator.py
Please move or remove them before you merge.
Aborting
Merge with strategy ort failed."""

        assert coordinator._is_untracked_files_error(error_message) is True

    def test_detects_move_or_remove_suggestion(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should detect error suggesting to move or remove files."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        error_message = "Please move or remove them before you merge."

        assert coordinator._is_untracked_files_error(error_message) is True

    def test_does_not_match_local_changes_error(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should not match local changes (tracked files) error."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        error_message = "Your local changes to the following files would be overwritten"

        assert coordinator._is_untracked_files_error(error_message) is False

    def test_does_not_match_unrelated_error(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should not match unrelated git errors."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        error_message = "fatal: not a git repository"

        assert coordinator._is_untracked_files_error(error_message) is False


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

    def test_ignores_untracked_files(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should not stash untracked files (only tracked changes are stashed).

        Untracked files are intentionally not stashed because git stash -u with
        pathspec exclusions doesn't work reliably. Untracked file conflicts
        during merge are handled by _handle_untracked_conflict instead.
        """
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create untracked file only (no tracked changes)
        new_file = temp_git_repo / "new_file.txt"
        new_file.write_text("new content")

        result = coordinator._stash_local_changes()

        # Should return False since only untracked files exist
        assert result is False
        assert coordinator._stash_active is False

        # Verify file still exists (not stashed)
        assert new_file.exists()
        assert new_file.read_text() == "new content"

    def test_excludes_state_file_from_stash(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should exclude state file from stash to prevent pop conflicts.

        The state file is managed by the orchestrator and can change during
        merge operations. Stashing it causes conflicts when popping after merge.
        """
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create the state file as a tracked file
        state_file = temp_git_repo / default_config.state_file
        state_file.write_text('{"initial": true}')
        subprocess.run(["git", "add", str(state_file)], cwd=temp_git_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add state file"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        # Modify both the state file and another tracked file
        state_file.write_text('{"modified": true}')
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("modified content")

        result = coordinator._stash_local_changes()

        # Should stash the test.txt but NOT the state file
        assert result is True
        assert coordinator._stash_active is True

        # test.txt should be reverted (stashed)
        assert test_file.read_text() == "initial content"

        # State file should NOT be reverted (excluded from stash)
        assert state_file.read_text() == '{"modified": true}'


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


class TestHandleUntrackedConflict:
    """Tests for _handle_untracked_conflict functionality."""

    def test_parses_and_backs_up_conflicting_files(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should parse file paths from error and back them up."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create an untracked file that would conflict
        test_dir = temp_git_repo / "tests" / "unit"
        test_dir.mkdir(parents=True)
        conflicting_file = test_dir / "test_example.py"
        conflicting_file.write_text("# untracked test file")

        # Create fake worktree
        fake_worktree = temp_git_repo / ".worktrees" / "fake"
        fake_worktree.mkdir(parents=True)

        worker_result = WorkerResult(
            issue_id="TEST-001",
            branch_name="parallel/test-branch",
            worktree_path=fake_worktree,
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)

        error_output = """error: The following untracked working tree files would be overwritten by merge:
        tests/unit/test_example.py
Please move or remove them before you merge.
Aborting"""

        # Handle the conflict
        coordinator._handle_untracked_conflict(request, error_output)

        # Original file should be moved
        assert not conflicting_file.exists()

        # Backup should exist
        backup_file = (
            temp_git_repo / ".ll-backup" / "TEST-001" / "tests" / "unit" / "test_example.py"
        )
        assert backup_file.exists()
        assert backup_file.read_text() == "# untracked test file"

        # Request should be re-queued
        assert request.retry_count == 1
        assert coordinator._queue.qsize() == 1

    def test_respects_max_retries(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should fail after max retries exceeded."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        fake_worktree = temp_git_repo / ".worktrees" / "fake"
        fake_worktree.mkdir(parents=True)

        worker_result = WorkerResult(
            issue_id="TEST-001",
            branch_name="parallel/test-branch",
            worktree_path=fake_worktree,
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)
        request.retry_count = default_config.max_merge_retries  # Already at max

        error_output = """error: The following untracked working tree files would be overwritten by merge:
        tests/unit/test_example.py
Please move or remove them before you merge."""

        coordinator._handle_untracked_conflict(request, error_output)

        # Should not be re-queued
        assert coordinator._queue.qsize() == 0
        # Should be marked as failed
        assert "TEST-001" in coordinator._failed
