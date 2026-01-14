"""Tests for merge coordinator stash and conflict handling."""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from little_loops.parallel.merge_coordinator import MergeCoordinator
from little_loops.parallel.types import MergeRequest, MergeStatus, ParallelConfig, WorkerResult


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


class TestStashPopFailureTracking:
    """Tests for stash pop failure tracking."""

    def test_tracks_stash_pop_failure(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should track stash pop failure with issue ID."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create a stash
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("modified content")
        coordinator._stash_local_changes()

        # Simulate stash pop failure by creating a conflicting change
        # First, modify the same file differently
        test_file.write_text("conflicting content")

        # Set the current issue ID (normally set by _process_merge)
        coordinator._current_issue_id = "TEST-001"

        # Attempt pop (will fail due to conflict)
        result = coordinator._pop_stash()

        # Should return False and track the failure
        assert result is False
        assert "TEST-001" in coordinator.stash_pop_failures
        assert "manually" in coordinator.stash_pop_failures["TEST-001"].lower()

    def test_stash_pop_failures_property_is_thread_safe(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Property should return a copy to prevent external modification."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Manually add a failure
        coordinator._stash_pop_failures["TEST-001"] = "test message"

        # Get the property
        failures = coordinator.stash_pop_failures

        # Modify the returned dict
        failures["TEST-002"] = "should not appear"

        # Original should be unchanged
        assert "TEST-002" not in coordinator.stash_pop_failures

    def test_no_tracking_without_current_issue_id(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should not track failure if no current issue ID is set."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create a stash
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("modified content")
        coordinator._stash_local_changes()

        # Create conflict
        test_file.write_text("conflicting content")

        # Do NOT set current issue ID
        coordinator._current_issue_id = None

        # Attempt pop (will fail but shouldn't track)
        result = coordinator._pop_stash()

        # Should return False but no tracking
        assert result is False
        assert len(coordinator.stash_pop_failures) == 0


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


class TestLifecycleFileMoveExclusion:
    """Tests for excluding lifecycle file moves from stashing."""

    def test_is_lifecycle_file_move_detects_rename_to_completed(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should detect rename entries moving files to completed directory."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Rename to completed should be detected (with dot prefix)
        assert coordinator._is_lifecycle_file_move(
            "R  .issues/bugs/P1-BUG-001.md -> .issues/completed/P1-BUG-001.md"
        )
        assert coordinator._is_lifecycle_file_move(
            "R  .issues/enhancements/P2-ENH-123.md -> .issues/completed/P2-ENH-123.md"
        )
        assert coordinator._is_lifecycle_file_move(
            "R  .issues/features/P3-FEAT-456.md -> .issues/completed/P3-FEAT-456.md"
        )

    def test_is_lifecycle_file_move_handles_path_variants(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should detect renames to completed directory with or without dot prefix."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Without dot prefix (used by external repositories)
        assert coordinator._is_lifecycle_file_move(
            "R  issues/bugs/P1-BUG-001.md -> issues/completed/P1-BUG-001.md"
        )
        assert coordinator._is_lifecycle_file_move(
            "R  issues/enhancements/P2-ENH-123.md -> issues/completed/P2-ENH-123.md"
        )

        # Cross-variant moves (from dotted to non-dotted or vice versa)
        assert coordinator._is_lifecycle_file_move(
            "R  .issues/bugs/P1-BUG-001.md -> issues/completed/P1-BUG-001.md"
        )
        assert coordinator._is_lifecycle_file_move(
            "R  issues/bugs/P1-BUG-001.md -> .issues/completed/P1-BUG-001.md"
        )

        # Non-lifecycle moves should still return False
        assert not coordinator._is_lifecycle_file_move("R  src/old.py -> src/new.py")

    def test_is_lifecycle_file_move_ignores_other_renames(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should not detect renames to other directories."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Rename to other directory should not be detected
        assert not coordinator._is_lifecycle_file_move("R  src/old.py -> src/new.py")
        assert not coordinator._is_lifecycle_file_move(
            "R  .issues/bugs/P1-BUG-001.md -> .issues/bugs/P1-BUG-001-renamed.md"
        )
        assert not coordinator._is_lifecycle_file_move("R  docs/old.md -> docs/archive/old.md")

    def test_is_lifecycle_file_move_ignores_non_renames(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should not detect non-rename entries."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Modified files should not be detected
        assert not coordinator._is_lifecycle_file_move("M  .issues/completed/P1-BUG-001.md")
        assert not coordinator._is_lifecycle_file_move("A  .issues/completed/P1-BUG-001.md")
        assert not coordinator._is_lifecycle_file_move("D  .issues/bugs/P1-BUG-001.md")
        assert not coordinator._is_lifecycle_file_move("?? .issues/completed/new.md")

    def test_stash_excludes_lifecycle_file_moves(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Stash should exclude lifecycle file moves from being stashed."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create an issue file and commit it
        issues_dir = temp_git_repo / ".issues" / "bugs"
        issues_dir.mkdir(parents=True, exist_ok=True)
        issue_file = issues_dir / "P1-BUG-TEST.md"
        issue_file.write_text("# Test issue")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add issue"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        # Create completed directory and move the file (simulating lifecycle completion)
        completed_dir = temp_git_repo / ".issues" / "completed"
        completed_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "mv", str(issue_file), str(completed_dir / "P1-BUG-TEST.md")],
            cwd=temp_git_repo,
            capture_output=True,
        )

        # Also create a regular change that should be stashed
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("modified content")

        # Stash should succeed and stash test.txt but NOT the lifecycle move
        result = coordinator._stash_local_changes()

        # Since we have a regular change, result should be True
        assert result is True

        # After stash, test.txt should be reverted (stashed)
        assert test_file.read_text() == "initial content"

        # The git mv should still be staged (not stashed)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
        )
        # Should still have the rename entry (R means renamed)
        assert "R  " in status.stdout or "-> .issues/completed" in status.stdout

        # Pop the stash to restore test.txt
        coordinator._pop_stash()
        assert test_file.read_text() == "modified content"

    def test_stash_excludes_completed_directory_files(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Stash should exclude files in completed directory."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create completed directory and a file in it, then commit
        completed_dir = temp_git_repo / ".issues" / "completed"
        completed_dir.mkdir(parents=True, exist_ok=True)
        completed_file = completed_dir / "P1-BUG-OLD.md"
        completed_file.write_text("# Old completed issue")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add completed issue"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        # Modify the completed file (simulating an update)
        completed_file.write_text("# Old completed issue\n\nUpdated content")

        # Also modify test.txt which should be stashed
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("modified content")

        # Stash should succeed and stash test.txt but NOT the completed file
        result = coordinator._stash_local_changes()

        assert result is True

        # test.txt should be reverted (stashed)
        assert test_file.read_text() == "initial content"

        # completed file should NOT be reverted (not stashed)
        assert "Updated content" in completed_file.read_text()

    def test_stash_with_only_lifecycle_changes_returns_false(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Stash should return False when only lifecycle changes exist."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create an issue file and commit it
        issues_dir = temp_git_repo / ".issues" / "bugs"
        issues_dir.mkdir(parents=True, exist_ok=True)
        issue_file = issues_dir / "P1-BUG-TEST.md"
        issue_file.write_text("# Test issue")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add issue"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        # Move the file to completed (lifecycle change only)
        completed_dir = temp_git_repo / ".issues" / "completed"
        completed_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "mv", str(issue_file), str(completed_dir / "P1-BUG-TEST.md")],
            cwd=temp_git_repo,
            capture_output=True,
        )

        # Stash should return False since only lifecycle changes exist
        result = coordinator._stash_local_changes()

        assert result is False
        assert coordinator._stash_active is False


class TestCommitPendingLifecycleMoves:
    """Tests for _commit_pending_lifecycle_moves functionality (BUG-018 fix)."""

    def test_returns_true_when_no_lifecycle_moves(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should return True when no lifecycle moves exist."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)
        result = coordinator._commit_pending_lifecycle_moves()
        assert result is True

    def test_commits_staged_lifecycle_move(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should commit staged lifecycle file moves."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create and commit an issue file
        issues_dir = temp_git_repo / ".issues" / "bugs"
        completed_dir = temp_git_repo / ".issues" / "completed"
        issues_dir.mkdir(parents=True)
        completed_dir.mkdir(parents=True)

        issue_file = issues_dir / "P1-BUG-001-test.md"
        issue_file.write_text("# Test issue")

        subprocess.run(["git", "add", "."], cwd=temp_git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add issue"],
            cwd=temp_git_repo,
            check=True,
        )

        # Move file with git mv (stages the rename)
        subprocess.run(
            ["git", "mv", str(issue_file), str(completed_dir / issue_file.name)],
            cwd=temp_git_repo,
            check=True,
        )

        # Verify the rename is staged
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
        )
        assert "R " in status.stdout or "-> .issues/completed" in status.stdout

        # Run the method
        result = coordinator._commit_pending_lifecycle_moves()

        assert result is True

        # Verify the rename is now committed (no uncommitted changes)
        status_after = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
        )
        assert status_after.stdout.strip() == ""

        # Verify commit message
        log = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
        )
        assert "lifecycle" in log.stdout.lower()

    def test_ignores_non_lifecycle_moves(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should return True and not commit non-lifecycle file moves."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create and commit a file in docs
        docs_dir = temp_git_repo / "docs"
        docs_dir.mkdir(parents=True)
        doc_file = docs_dir / "old.md"
        doc_file.write_text("# Old doc")

        subprocess.run(["git", "add", "."], cwd=temp_git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add doc"],
            cwd=temp_git_repo,
            check=True,
        )

        # Move file with git mv (stages a non-lifecycle rename)
        subprocess.run(
            ["git", "mv", str(doc_file), str(docs_dir / "new.md")],
            cwd=temp_git_repo,
            check=True,
        )

        # Run the method - should return True but not commit
        result = coordinator._commit_pending_lifecycle_moves()

        assert result is True

        # The rename should still be staged (not committed)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
        )
        assert "R " in status.stdout

    def test_commits_multiple_lifecycle_moves(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should commit multiple lifecycle file moves in one commit."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create and commit multiple issue files
        issues_dir = temp_git_repo / ".issues" / "bugs"
        completed_dir = temp_git_repo / ".issues" / "completed"
        issues_dir.mkdir(parents=True)
        completed_dir.mkdir(parents=True)

        issue1 = issues_dir / "P1-BUG-001.md"
        issue2 = issues_dir / "P2-BUG-002.md"
        issue1.write_text("# Test issue 1")
        issue2.write_text("# Test issue 2")

        subprocess.run(["git", "add", "."], cwd=temp_git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add issues"],
            cwd=temp_git_repo,
            check=True,
        )

        # Move both files with git mv
        subprocess.run(
            ["git", "mv", str(issue1), str(completed_dir / issue1.name)],
            cwd=temp_git_repo,
            check=True,
        )
        subprocess.run(
            ["git", "mv", str(issue2), str(completed_dir / issue2.name)],
            cwd=temp_git_repo,
            check=True,
        )

        # Run the method
        result = coordinator._commit_pending_lifecycle_moves()

        assert result is True

        # Verify both are committed
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
        )
        assert status.stdout.strip() == ""

    def test_handles_lifecycle_move_with_content_changes(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should commit lifecycle move even with content modifications."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create and commit an issue file
        issues_dir = temp_git_repo / ".issues" / "bugs"
        completed_dir = temp_git_repo / ".issues" / "completed"
        issues_dir.mkdir(parents=True)
        completed_dir.mkdir(parents=True)

        issue_file = issues_dir / "P1-BUG-001.md"
        issue_file.write_text("# Test issue")

        subprocess.run(["git", "add", "."], cwd=temp_git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add issue"],
            cwd=temp_git_repo,
            check=True,
        )

        # Move file with git mv
        new_path = completed_dir / issue_file.name
        subprocess.run(
            ["git", "mv", str(issue_file), str(new_path)],
            cwd=temp_git_repo,
            check=True,
        )

        # Also modify the content (simulating resolution section being added)
        new_path.write_text("# Test issue\n\n## Resolution\nCompleted!")

        # Run the method
        result = coordinator._commit_pending_lifecycle_moves()

        assert result is True

        # Verify committed
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
        )
        assert status.stdout.strip() == ""


class TestWaitForCompletion:
    """Tests for wait_for_completion method (BUG-019 fix)."""

    def test_returns_true_when_queue_empty_and_no_active_processing(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should return True immediately when queue is empty and no processing."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Queue is empty by default, no active processing
        assert coordinator._queue.empty()
        assert coordinator._current_issue_id is None

        result = coordinator.wait_for_completion(timeout=0.5)
        assert result is True

    def test_waits_for_active_processing_to_complete(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should wait until _current_issue_id is cleared (BUG-019 fix)."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Simulate active processing: queue is empty but merge is in progress
        assert coordinator._queue.empty()
        coordinator._current_issue_id = "BUG-001"

        # wait_for_completion should timeout because processing is active
        result = coordinator.wait_for_completion(timeout=0.3)

        # Should return False (timeout) because _current_issue_id is still set
        assert result is False

    def test_returns_true_after_processing_completes(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should return True once _current_issue_id is cleared."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Queue empty, no active processing
        coordinator._current_issue_id = None

        result = coordinator.wait_for_completion(timeout=0.3)
        assert result is True

    def test_waits_for_both_queue_and_processing(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should wait for both queue to empty AND processing to complete."""
        import threading
        import time

        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create a worker result to put in queue
        worker_result = WorkerResult(
            issue_id="BUG-001",
            branch_name="parallel/bug-001",
            worktree_path=temp_git_repo / ".worktrees" / "fake",
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)
        coordinator._queue.put(request)

        # Also set processing active
        coordinator._current_issue_id = "BUG-002"

        # In a separate thread, clear both after a short delay
        def clear_state() -> None:
            time.sleep(0.1)
            coordinator._queue.get()  # Clear queue
            time.sleep(0.1)
            coordinator._current_issue_id = None  # Clear processing

        thread = threading.Thread(target=clear_state)
        thread.start()

        # wait_for_completion should wait for both
        result = coordinator.wait_for_completion(timeout=1.0)

        thread.join()

        # Should return True after both are cleared
        assert result is True


class TestUnmergedFilesHandling:
    """Tests for handling unmerged files during merge operations."""

    def test_unmerged_files_from_current_merge_routes_to_conflict_handler(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Unmerged files from current merge attempt should route to conflict handler.

        This test verifies the BUG-018 reopened fix: genuine merge conflicts
        should go through the conflict handler's rebase retry flow, not the
        confusing retry-after-reset path.
        """
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create a worktree
        worktree_path = temp_git_repo / ".worktrees" / "test-branch"
        worktree_path.mkdir(parents=True, exist_ok=True)

        # Create a branch in the worktree
        subprocess.run(
            ["git", "worktree", "add", "-b", "parallel/test-branch", str(worktree_path)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        # Create a conflicting change in the worktree
        test_file = worktree_path / "test.txt"
        test_file.write_text("conflicting content from branch")
        subprocess.run(
            ["git", "add", "."],
            cwd=worktree_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "conflicting change"],
            cwd=worktree_path,
            capture_output=True,
            check=True,
        )

        # Create a conflicting change on main
        main_test_file = temp_git_repo / "test.txt"
        main_test_file.write_text("conflicting content from main")
        subprocess.run(
            ["git", "add", "."],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "conflicting change on main"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        # Create a merge request
        worker_result = WorkerResult(
            issue_id="ENH-724",
            branch_name="parallel/test-branch",
            worktree_path=worktree_path,
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)

        # Mock _handle_conflict to verify it's called instead of retry-after-reset
        handle_conflict_called = []

        def mock_handle_conflict(req: MergeRequest) -> None:
            handle_conflict_called.append(req)
            # Don't actually run rebase, just mark as failed to avoid infinite loop
            coordinator._handle_failure(req, "Test: conflict handler was called")

        coordinator._handle_conflict = mock_handle_conflict

        # Mock _check_and_recover_index to verify it's called at start but not during conflict
        index_recovery_count = []

        original_check_and_recover_index = coordinator._check_and_recover_index

        def mock_check_and_recover_index() -> bool:
            index_recovery_count.append(len(index_recovery_count))
            return original_check_and_recover_index()

        coordinator._check_and_recover_index = mock_check_and_recover_index

        # Process the merge (it should fail but call the right handlers)
        coordinator._process_merge(request)

        # Verify _check_and_recover_index was called at the start (before merge)
        assert len(index_recovery_count) >= 1, "Index recovery should be called at start"

        # Verify _handle_conflict was called (not retry-after-reset)
        assert len(handle_conflict_called) == 1, "Conflict handler should be called once"
        assert handle_conflict_called[0] is request

        # Verify the issue was marked as failed
        assert request.status == MergeStatus.FAILED
        assert "conflict handler was called" in request.error

    def test_pre_existing_unmerged_files_cleaned_before_merge(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Pre-existing unmerged files from previous operations should be cleaned up.

        This verifies the fix doesn't break recovery for genuine index corruption.
        """
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create a branch and worktree
        worktree_path = temp_git_repo / ".worktrees" / "clean-branch"
        worktree_path.mkdir(parents=True, exist_ok=True)

        subprocess.run(
            ["git", "worktree", "add", "-b", "parallel/clean-branch", str(worktree_path)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        # Make a simple change in the worktree
        test_file = worktree_path / "test.txt"
        test_file.write_text("branch content")
        subprocess.run(
            ["git", "add", "."],
            cwd=worktree_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "branch change"],
            cwd=worktree_path,
            capture_output=True,
            check=True,
        )

        # Simulate a previous incomplete merge by creating MERGE_HEAD
        merge_head = temp_git_repo / ".git" / "MERGE_HEAD"
        merge_head.write_text("abc123")

        # Create a merge request
        worker_result = WorkerResult(
            issue_id="BUG-999",
            branch_name="parallel/clean-branch",
            worktree_path=worktree_path,
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)

        # Process the merge
        coordinator._process_merge(request)

        # Verify the incomplete merge was cleaned up (MERGE_HEAD should be gone)
        assert not merge_head.exists(), "MERGE_HEAD should be cleaned up"

        # Verify the merge succeeded (no conflict in this case)
        assert request.status == MergeStatus.SUCCESS
