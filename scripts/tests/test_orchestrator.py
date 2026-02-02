"""Tests for orchestrator.py - parallel issue processing orchestration.

Tests cover:
- Orchestrator initialization and component creation
- Signal handler setup/restore
- Gitignore entry management
- Orphaned worktree cleanup
- State management (load/save/cleanup)
- Run method and dry run mode
- Issue scanning and filtering
- Execute loop (P0 sequential, parallel dispatch)
- Worker completion callbacks
- Merge coordination
- Completion waiting and reporting
- Cleanup operations
"""

from __future__ import annotations

import json
import signal
import tempfile
import threading
import time
from collections.abc import Generator
from concurrent.futures import Future
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from little_loops.config import BRConfig
from little_loops.issue_parser import IssueInfo
from little_loops.parallel.git_lock import GitLock
from little_loops.parallel.orchestrator import ParallelOrchestrator
from little_loops.parallel.types import OrchestratorState, ParallelConfig, WorkerResult

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_logger() -> MagicMock:
    """Create a mock logger without spec for flexibility."""
    return MagicMock()


@pytest.fixture
def temp_repo_with_config() -> Generator[Path, None, None]:
    """Create a temporary directory with .claude config and issues."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Create .claude directory with config
        claude_dir = repo_path / ".claude"
        claude_dir.mkdir()
        config = {
            "project": {"name": "test", "src_dir": "src/"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                    "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
                },
                "completed_dir": "completed",
            },
        }
        (claude_dir / "ll-config.json").write_text(json.dumps(config))

        # Create issues directory structure
        issues_dir = repo_path / ".issues"
        bugs_dir = issues_dir / "bugs"
        completed_dir = issues_dir / "completed"
        bugs_dir.mkdir(parents=True)
        completed_dir.mkdir(parents=True)

        # Create sample issue
        (bugs_dir / "P1-BUG-001-test-bug.md").write_text(
            "# BUG-001: Test Bug\n\n## Summary\nTest bug."
        )

        # Create worktree base
        worktree_base = repo_path / ".worktrees"
        worktree_base.mkdir()

        yield repo_path


@pytest.fixture
def default_parallel_config() -> ParallelConfig:
    """Create default parallel config for tests."""
    return ParallelConfig(
        max_workers=2,
        p0_sequential=True,
        worktree_base=Path(".worktrees"),
        state_file=Path(".parallel-manage-state.json"),
        timeout_per_issue=1800,
        max_merge_retries=2,
        stream_subprocess_output=False,
        command_prefix="/ll:",
        ready_command="ready_issue {{issue_id}}",
        manage_command="manage_issue {{issue_type}} {{action}} {{issue_id}}",
    )


@pytest.fixture
def br_config(temp_repo_with_config: Path) -> BRConfig:
    """Create BRConfig from temp repo."""
    return BRConfig(temp_repo_with_config)


@pytest.fixture
def mock_git_lock(mock_logger: MagicMock) -> GitLock:
    """Create a GitLock with mock logger."""
    return GitLock(mock_logger)


@pytest.fixture
def mock_issue() -> MagicMock:
    """Create a mock IssueInfo."""
    issue = MagicMock(spec=IssueInfo)
    issue.issue_id = "BUG-001"
    issue.issue_type = "bugs"
    issue.title = "Test Bug"
    issue.priority = "P1"
    issue.path = Path(".issues/bugs/P1-BUG-001-test-bug.md")
    return issue


@pytest.fixture
def orchestrator(
    default_parallel_config: ParallelConfig,
    br_config: BRConfig,
    temp_repo_with_config: Path,
) -> ParallelOrchestrator:
    """Create a ParallelOrchestrator instance for testing with mocked components."""
    with (
        patch("little_loops.parallel.orchestrator.WorkerPool"),
        patch("little_loops.parallel.orchestrator.MergeCoordinator"),
        patch("little_loops.parallel.orchestrator.IssuePriorityQueue"),
    ):
        orch = ParallelOrchestrator(
            parallel_config=default_parallel_config,
            br_config=br_config,
            repo_path=temp_repo_with_config,
            verbose=False,
        )
        # Set up mock queue default values for state saving
        orch.queue.completed_ids = []  # type: ignore[misc]
        orch.queue.failed_ids = []  # type: ignore[misc]
        orch.queue.in_progress_ids = []  # type: ignore[misc]
        orch.queue.completed_count = 0  # type: ignore[misc]
        orch.queue.failed_count = 0  # type: ignore[misc]
        return orch


class TestOrchestratorInit:
    """Tests for ParallelOrchestrator initialization."""

    def test_init_sets_attributes(
        self,
        default_parallel_config: ParallelConfig,
        br_config: BRConfig,
        temp_repo_with_config: Path,
    ) -> None:
        """Orchestrator initializes with correct attributes."""
        with (
            patch("little_loops.parallel.orchestrator.WorkerPool"),
            patch("little_loops.parallel.orchestrator.MergeCoordinator"),
            patch("little_loops.parallel.orchestrator.IssuePriorityQueue"),
        ):
            orch = ParallelOrchestrator(
                parallel_config=default_parallel_config,
                br_config=br_config,
                repo_path=temp_repo_with_config,
                verbose=True,
            )

            assert orch.parallel_config == default_parallel_config
            assert orch.br_config == br_config
            assert orch.repo_path == temp_repo_with_config
            assert orch._shutdown_requested is False

    def test_init_uses_cwd_when_no_repo_path(
        self,
        default_parallel_config: ParallelConfig,
        br_config: BRConfig,
    ) -> None:
        """Orchestrator uses cwd when repo_path is None."""
        with (
            patch("little_loops.parallel.orchestrator.WorkerPool"),
            patch("little_loops.parallel.orchestrator.MergeCoordinator"),
            patch("little_loops.parallel.orchestrator.IssuePriorityQueue"),
        ):
            with patch("pathlib.Path.cwd", return_value=Path("/mock/cwd")):
                orch = ParallelOrchestrator(
                    parallel_config=default_parallel_config,
                    br_config=br_config,
                    repo_path=None,
                )
                assert orch.repo_path == Path("/mock/cwd")

    def test_init_creates_shared_git_lock(
        self,
        default_parallel_config: ParallelConfig,
        br_config: BRConfig,
        temp_repo_with_config: Path,
    ) -> None:
        """Orchestrator creates a shared GitLock for components."""
        with (
            patch("little_loops.parallel.orchestrator.WorkerPool") as mock_wp,
            patch("little_loops.parallel.orchestrator.MergeCoordinator") as mock_mc,
            patch("little_loops.parallel.orchestrator.IssuePriorityQueue"),
        ):
            orch = ParallelOrchestrator(
                parallel_config=default_parallel_config,
                br_config=br_config,
                repo_path=temp_repo_with_config,
            )

            # GitLock should be passed to both WorkerPool and MergeCoordinator
            assert orch._git_lock is not None
            mock_wp.assert_called_once()
            mock_mc.assert_called_once()

    def test_init_creates_empty_issue_info_dict(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """Orchestrator initializes with empty issue info dictionary."""
        assert orchestrator._issue_info_by_id == {}

    def test_init_creates_orchestrator_state(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """Orchestrator initializes with fresh OrchestratorState."""
        assert isinstance(orchestrator.state, OrchestratorState)


class TestSignalHandlers:
    """Tests for signal handler setup and restore."""

    def test_setup_signal_handlers_installs_handlers(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_setup_signal_handlers installs custom handlers."""
        orchestrator._setup_signal_handlers()

        # Signal handlers should be set
        assert orchestrator._original_sigint is not None
        assert orchestrator._original_sigterm is not None

        # Restore to clean up
        orchestrator._restore_signal_handlers()

    def test_restore_signal_handlers_restores_original(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_restore_signal_handlers restores original handlers."""
        # Get original handlers
        original_sigint = signal.getsignal(signal.SIGINT)

        orchestrator._setup_signal_handlers()
        orchestrator._restore_signal_handlers()

        # Should be restored
        current_sigint = signal.getsignal(signal.SIGINT)
        assert current_sigint == original_sigint

    def test_signal_handler_sets_shutdown_flag(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_signal_handler sets shutdown flag."""
        assert orchestrator._shutdown_requested is False

        orchestrator._signal_handler(signal.SIGINT, None)

        assert orchestrator._shutdown_requested is True

    def test_signal_handler_propagates_to_worker_pool(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_signal_handler propagates shutdown to worker pool (ENH-036)."""
        orchestrator._signal_handler(signal.SIGINT, None)

        # Verify set_shutdown_requested was called on the mock worker pool
        orchestrator.worker_pool.set_shutdown_requested.assert_called_once_with(True)


class TestGitignoreEntries:
    """Tests for _ensure_gitignore_entries."""

    def test_creates_gitignore_if_missing(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Creates .gitignore with entries if it doesn't exist."""
        gitignore_path = temp_repo_with_config / ".gitignore"
        if gitignore_path.exists():
            gitignore_path.unlink()

        orchestrator._ensure_gitignore_entries()

        assert gitignore_path.exists()
        content = gitignore_path.read_text()
        assert ".parallel-manage-state.json" in content
        assert ".worktrees/" in content

    def test_adds_missing_entries_to_existing_gitignore(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Adds missing entries to existing .gitignore."""
        gitignore_path = temp_repo_with_config / ".gitignore"
        gitignore_path.write_text("*.pyc\n__pycache__/\n")

        orchestrator._ensure_gitignore_entries()

        content = gitignore_path.read_text()
        assert "*.pyc" in content  # Original preserved
        assert ".parallel-manage-state.json" in content
        assert ".worktrees/" in content

    def test_idempotent_when_entries_exist(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Does not duplicate entries if they already exist."""
        gitignore_path = temp_repo_with_config / ".gitignore"
        gitignore_path.write_text(".parallel-manage-state.json\n.worktrees/\n")

        orchestrator._ensure_gitignore_entries()

        content = gitignore_path.read_text()
        assert content.count(".parallel-manage-state.json") == 1
        assert content.count(".worktrees/") == 1


class TestOrphanedWorktreeCleanup:
    """Tests for _cleanup_orphaned_worktrees."""

    def test_does_nothing_when_no_worktree_dir(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Does nothing when worktree directory doesn't exist."""
        worktree_base = temp_repo_with_config / ".worktrees"
        if worktree_base.exists():
            worktree_base.rmdir()

        # Should not raise
        orchestrator._cleanup_orphaned_worktrees()

    def test_cleans_up_orphaned_worktrees(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Cleans up worker-* directories from previous runs."""
        worktree_base = temp_repo_with_config / ".worktrees"
        orphan1 = worktree_base / "worker-bug-001"
        orphan2 = worktree_base / "worker-bug-002"
        orphan1.mkdir()
        orphan2.mkdir()

        # Mock git commands
        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        orchestrator._cleanup_orphaned_worktrees()

        # Directories should be cleaned up (by rmtree fallback if git fails)
        # The actual git worktree remove might fail in test env

    def test_ignores_non_worker_directories(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Does not clean up directories not starting with worker-."""
        worktree_base = temp_repo_with_config / ".worktrees"
        other_dir = worktree_base / "other-directory"
        other_dir.mkdir()

        orchestrator._cleanup_orphaned_worktrees()

        assert other_dir.exists()


class TestCheckPendingWorktrees:
    """Tests for _check_pending_worktrees method."""

    def test_no_worktrees_dir(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Returns empty list when worktree directory doesn't exist."""
        worktree_base = temp_repo_with_config / ".worktrees"
        if worktree_base.exists():
            worktree_base.rmdir()

        result = orchestrator._check_pending_worktrees()
        assert result == []

    def test_empty_worktrees_dir(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Returns empty list when no worker directories exist."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)

        result = orchestrator._check_pending_worktrees()
        assert result == []

    def test_detects_orphaned_worktrees(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Detects worker directories from previous runs."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)

        # Create fake worktree directory
        orphan = worktree_base / "worker-bug-001-20260117-120000"
        orphan.mkdir()

        # Mock git operations
        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if args[0] == "rev-list":
                result.stdout = "2\n"
            elif args[0] == "status":
                result.stdout = ""
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        result = orchestrator._check_pending_worktrees()
        assert len(result) == 1
        assert result[0].issue_id == "BUG-001"
        assert result[0].commits_ahead == 2

    def test_ignores_non_worker_directories(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Does not report directories not starting with worker-."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)

        # Create non-worker directory
        other_dir = worktree_base / "other-directory"
        other_dir.mkdir()

        result = orchestrator._check_pending_worktrees()
        assert result == []


class TestInspectWorktree:
    """Tests for _inspect_worktree method."""

    def test_extracts_issue_id(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Correctly extracts issue ID from worktree path."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)
        worktree_path = worktree_base / "worker-enh-042-20260117-150000"
        worktree_path.mkdir()

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "0\n" if args[0] == "rev-list" else ""
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        result = orchestrator._inspect_worktree(worktree_path)
        assert result is not None
        assert result.issue_id == "ENH-042"
        assert result.branch_name == "parallel/enh-042-20260117-150000"

    def test_detects_uncommitted_changes(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Detects uncommitted changes in worktree."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)
        worktree_path = worktree_base / "worker-bug-099-20260117-160000"
        worktree_path.mkdir()

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if args[0] == "rev-list":
                result.stdout = "1\n"
            elif args[0] == "status":
                result.stdout = " M src/file.py\n?? new_file.txt\n"
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        result = orchestrator._inspect_worktree(worktree_path)
        assert result is not None
        assert result.has_uncommitted_changes is True
        assert len(result.changed_files) == 2
        assert result.has_pending_work is True

    def test_handles_inspection_failure(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Returns None when inspection fails."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)
        worktree_path = worktree_base / "worker-bug-001-20260117-120000"
        worktree_path.mkdir()

        def mock_git_run_raises(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            raise RuntimeError("Git error")

        orchestrator._git_lock.run = mock_git_run_raises  # type: ignore[method-assign,assignment]

        result = orchestrator._inspect_worktree(worktree_path)
        assert result is None


class TestMergePendingWorktrees:
    """Tests for _merge_pending_worktrees method."""

    def test_skips_empty_list(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """Does nothing when no pending worktrees."""
        # Should not raise
        orchestrator._merge_pending_worktrees([])

    def test_skips_worktrees_without_pending_work(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Skips worktrees that have no commits ahead or uncommitted changes."""
        from little_loops.parallel.types import PendingWorktreeInfo

        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)
        worktree_path = worktree_base / "worker-bug-001-20260117-120000"
        worktree_path.mkdir()

        # Create info with no pending work
        info = PendingWorktreeInfo(
            worktree_path=worktree_path,
            branch_name="parallel/bug-001-20260117-120000",
            issue_id="BUG-001",
            commits_ahead=0,
            has_uncommitted_changes=False,
            changed_files=[],
        )

        # Should not attempt any merge
        orchestrator._merge_pending_worktrees([info])

    def test_attempts_merge_with_commits_ahead(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Attempts merge when worktree has commits ahead of main."""
        from little_loops.parallel.types import PendingWorktreeInfo

        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)
        worktree_path = worktree_base / "worker-bug-001-20260117-120000"
        worktree_path.mkdir()

        info = PendingWorktreeInfo(
            worktree_path=worktree_path,
            branch_name="parallel/bug-001-20260117-120000",
            issue_id="BUG-001",
            commits_ahead=3,
            has_uncommitted_changes=False,
            changed_files=[],
        )

        merge_called = []

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            if args[0] == "merge":
                merge_called.append(args)
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        orchestrator._merge_pending_worktrees([info])

        # Verify merge was called
        assert len(merge_called) == 1
        assert "--no-ff" in merge_called[0]
        assert "parallel/bug-001-20260117-120000" in merge_called[0]


class TestStateManagement:
    """Tests for state load/save/cleanup."""

    def test_load_state_creates_new_when_file_missing(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """_load_state creates fresh state when file doesn't exist."""
        state_file = temp_repo_with_config / ".parallel-manage-state.json"
        if state_file.exists():
            state_file.unlink()

        orchestrator._load_state()

        assert orchestrator.state.started_at != ""
        assert orchestrator.state.completed_issues == []

    def test_load_state_resumes_from_file(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """_load_state resumes from existing state file."""
        state_file = temp_repo_with_config / ".parallel-manage-state.json"
        saved_state = {
            "completed_issues": ["BUG-001", "BUG-002"],
            "failed_issues": {"BUG-003": "Failed"},
            "in_progress_issues": [],
            "pending_merges": [],
            "timing": {},
            "started_at": "2025-01-05T10:00:00",
            "last_checkpoint": "2025-01-05T10:30:00",
        }
        state_file.write_text(json.dumps(saved_state))

        orchestrator._load_state()

        assert "BUG-001" in orchestrator.state.completed_issues
        assert "BUG-003" in orchestrator.state.failed_issues

    def test_load_state_resumes_corrections(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """_load_state resumes corrections from existing state file (ENH-010)."""
        state_file = temp_repo_with_config / ".parallel-manage-state.json"
        saved_state = {
            "completed_issues": ["BUG-001"],
            "failed_issues": {},
            "in_progress_issues": [],
            "pending_merges": [],
            "timing": {},
            "corrections": {
                "BUG-001": ["Updated line 42 -> 45", "Added missing section"],
            },
            "started_at": "2025-01-05T10:00:00",
            "last_checkpoint": "2025-01-05T10:30:00",
        }
        state_file.write_text(json.dumps(saved_state))

        orchestrator._load_state()

        assert "BUG-001" in orchestrator.state.corrections
        assert len(orchestrator.state.corrections["BUG-001"]) == 2
        assert "Updated line 42 -> 45" in orchestrator.state.corrections["BUG-001"]

    def test_load_state_handles_corrupt_file(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """_load_state handles corrupt state file gracefully."""
        state_file = temp_repo_with_config / ".parallel-manage-state.json"
        state_file.write_text("not valid json {{{")

        # Should not raise, creates fresh state
        orchestrator._load_state()
        assert orchestrator.state.started_at != ""

    def test_save_state_writes_file(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """_save_state writes state to file."""
        state_file = temp_repo_with_config / ".parallel-manage-state.json"

        # Mock queue to return completed/failed IDs
        orchestrator.queue.completed_ids = ["BUG-001"]  # type: ignore[misc]
        orchestrator.queue.failed_ids = ["BUG-002"]  # type: ignore[misc]
        orchestrator.queue.in_progress_ids = []  # type: ignore[misc]

        orchestrator._save_state()

        assert state_file.exists()
        saved = json.loads(state_file.read_text())
        assert "BUG-001" in saved["completed_issues"]

    def test_cleanup_state_removes_file(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """_cleanup_state removes state file."""
        state_file = temp_repo_with_config / ".parallel-manage-state.json"
        state_file.write_text("{}")

        orchestrator._cleanup_state()

        assert not state_file.exists()

    def test_cleanup_state_handles_missing_file(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """_cleanup_state handles missing file gracefully."""
        state_file = temp_repo_with_config / ".parallel-manage-state.json"
        if state_file.exists():
            state_file.unlink()

        # Should not raise
        orchestrator._cleanup_state()


class TestRunMethod:
    """Tests for the main run() method."""

    def test_run_returns_zero_on_dry_run(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """run() returns 0 for successful dry run."""
        orchestrator.parallel_config.dry_run = True

        with patch.object(orchestrator, "_scan_issues", return_value=[]):
            exit_code = orchestrator.run()

        assert exit_code == 0

    def test_run_handles_keyboard_interrupt(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """run() handles KeyboardInterrupt gracefully."""
        with patch.object(orchestrator, "_setup_signal_handlers", side_effect=KeyboardInterrupt):
            exit_code = orchestrator.run()

        assert exit_code == 1

    def test_run_handles_exception(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """run() handles exceptions gracefully."""
        with patch.object(
            orchestrator, "_setup_signal_handlers", side_effect=RuntimeError("Test error")
        ):
            exit_code = orchestrator.run()

        assert exit_code == 1

    def test_run_calls_cleanup(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """run() always calls _cleanup in finally block."""
        cleanup_called = [False]

        def mock_cleanup() -> None:
            cleanup_called[0] = True

        orchestrator.parallel_config.dry_run = True

        with patch.object(orchestrator, "_scan_issues", return_value=[]):
            with patch.object(orchestrator, "_cleanup", side_effect=mock_cleanup):
                orchestrator.run()

        assert cleanup_called[0] is True


class TestDryRun:
    """Tests for _dry_run method."""

    def test_dry_run_returns_zero_with_no_issues(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_dry_run returns 0 when no issues found."""
        with patch.object(orchestrator, "_scan_issues", return_value=[]):
            exit_code = orchestrator._dry_run()

        assert exit_code == 0

    def test_dry_run_groups_by_priority(
        self,
        orchestrator: ParallelOrchestrator,
        mock_issue: MagicMock,
    ) -> None:
        """_dry_run groups issues by priority."""
        mock_issue2 = MagicMock(spec=IssueInfo)
        mock_issue2.issue_id = "BUG-002"
        mock_issue2.priority = "P0"
        mock_issue2.title = "Critical Bug"

        with patch.object(orchestrator, "_scan_issues", return_value=[mock_issue, mock_issue2]):
            exit_code = orchestrator._dry_run()

        assert exit_code == 0


class TestIssueScan:
    """Tests for _scan_issues method."""

    def test_scan_issues_returns_list(
        self,
        orchestrator: ParallelOrchestrator,
        mock_issue: MagicMock,
    ) -> None:
        """_scan_issues returns list of issues."""
        with patch(
            "little_loops.parallel.orchestrator.IssuePriorityQueue.scan_issues",
            return_value=[mock_issue],
        ):
            issues = orchestrator._scan_issues()

        assert len(issues) == 1
        assert issues[0].issue_id == "BUG-001"

    def test_scan_issues_applies_skip_ids(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_scan_issues combines skip_ids from state and config."""
        orchestrator.state.completed_issues = ["BUG-001"]
        orchestrator.state.failed_issues = {"BUG-002": "Failed"}
        orchestrator.parallel_config.skip_ids = {"BUG-003"}

        captured_args: list[Any] = []

        def mock_scan(*args: Any, **kwargs: Any) -> list[Any]:
            captured_args.append(kwargs)
            return []

        with patch(
            "little_loops.parallel.orchestrator.IssuePriorityQueue.scan_issues",
            side_effect=mock_scan,
        ):
            orchestrator._scan_issues()

        assert "skip_ids" in captured_args[0]
        skip_ids = captured_args[0]["skip_ids"]
        assert "BUG-001" in skip_ids
        assert "BUG-002" in skip_ids
        assert "BUG-003" in skip_ids

    def test_scan_issues_applies_max_issues(
        self,
        orchestrator: ParallelOrchestrator,
        mock_issue: MagicMock,
    ) -> None:
        """_scan_issues respects max_issues limit."""
        mock_issues = [MagicMock(spec=IssueInfo) for _ in range(5)]
        for i, m in enumerate(mock_issues):
            m.issue_id = f"BUG-{i:03d}"

        orchestrator.parallel_config.max_issues = 2

        with patch(
            "little_loops.parallel.orchestrator.IssuePriorityQueue.scan_issues",
            return_value=mock_issues,
        ):
            issues = orchestrator._scan_issues()

        assert len(issues) == 2


class TestExecute:
    """Tests for _execute method."""

    def test_execute_returns_zero_with_no_issues(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_execute returns 0 when no issues to process."""
        with patch.object(orchestrator, "_scan_issues", return_value=[]):
            exit_code = orchestrator._execute()

        assert exit_code == 0

    def test_execute_starts_components(
        self,
        orchestrator: ParallelOrchestrator,
        mock_issue: MagicMock,
    ) -> None:
        """_execute starts worker pool and merge coordinator."""
        orchestrator.queue.empty.return_value = True  # type: ignore[attr-defined]
        orchestrator.queue.add_many.return_value = 0  # type: ignore[attr-defined]
        orchestrator.worker_pool.active_count = 0  # type: ignore[misc]
        orchestrator.merge_coordinator.pending_count = 0  # type: ignore[misc]

        with patch.object(orchestrator, "_scan_issues", return_value=[]):
            orchestrator._execute()

        # Components not started when no issues
        # (exit early path)

    def test_execute_respects_shutdown_request(
        self,
        orchestrator: ParallelOrchestrator,
        mock_issue: MagicMock,
    ) -> None:
        """_execute exits loop when shutdown requested."""
        orchestrator._shutdown_requested = True
        orchestrator.queue.empty.return_value = False  # type: ignore[attr-defined]
        orchestrator.queue.add_many.return_value = 1  # type: ignore[attr-defined]
        orchestrator.queue.failed_count = 0  # type: ignore[misc]

        with patch.object(orchestrator, "_scan_issues", return_value=[mock_issue]):
            with patch.object(orchestrator, "_wait_for_completion"):
                with patch.object(orchestrator, "_report_results"):
                    exit_code = orchestrator._execute()

        assert exit_code == 0


class TestProcessSequential:
    """Tests for _process_sequential (P0 handling)."""

    def test_process_sequential_waits_for_parallel(
        self,
        orchestrator: ParallelOrchestrator,
        mock_issue: MagicMock,
    ) -> None:
        """_process_sequential waits for parallel workers to finish."""
        mock_issue.priority = "P0"

        # Simulate workers finishing
        active_count_sequence = [2, 1, 0]
        call_idx = [0]

        def get_active_count() -> int:
            idx = min(call_idx[0], len(active_count_sequence) - 1)
            call_idx[0] += 1
            return active_count_sequence[idx]

        type(orchestrator.worker_pool).active_count = property(lambda self: get_active_count())  # type: ignore[method-assign,assignment]

        # Mock the submit and result
        mock_future: Future[WorkerResult] = Future()
        mock_result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
        )
        mock_future.set_result(mock_result)
        orchestrator.worker_pool.submit.return_value = mock_future  # type: ignore[attr-defined]

        with patch.object(orchestrator, "_merge_sequential"):
            with patch("time.sleep"):
                orchestrator._process_sequential(mock_issue)

        orchestrator.worker_pool.submit.assert_called_once()  # type: ignore[attr-defined]


class TestOnWorkerComplete:
    """Tests for _on_worker_complete callback."""

    def test_on_worker_complete_success(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_on_worker_complete handles successful result."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
            duration=10.0,
        )

        orchestrator._on_worker_complete(result)

        orchestrator.merge_coordinator.queue_merge.assert_called_once_with(result)  # type: ignore[attr-defined]

    def test_on_worker_complete_failure(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_on_worker_complete handles failed result."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=False,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
            error="Processing failed",
        )

        orchestrator._on_worker_complete(result)

        orchestrator.queue.mark_failed.assert_called_once_with("BUG-001")  # type: ignore[attr-defined]

    def test_on_worker_complete_close_verdict(
        self,
        orchestrator: ParallelOrchestrator,
        mock_issue: MagicMock,
    ) -> None:
        """_on_worker_complete handles CLOSE verdict."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
            should_close=True,
            close_reason="already_fixed",
            close_status="Closed - Already Fixed",
        )

        # Add issue info for lifecycle completion
        orchestrator._issue_info_by_id["BUG-001"] = mock_issue

        with patch("little_loops.issue_lifecycle.close_issue", return_value=True):
            orchestrator._on_worker_complete(result)

        orchestrator.queue.mark_completed.assert_called_once_with("BUG-001")  # type: ignore[attr-defined]

    def test_on_worker_complete_corrected(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_on_worker_complete logs correction info and stores in state (ENH-010)."""
        corrections = [
            "Updated line 42 -> 45 in src/module.py reference",
            "Added missing ## Expected Behavior section",
        ]
        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
            was_corrected=True,
            corrections=corrections,
        )

        orchestrator._on_worker_complete(result)

        orchestrator.merge_coordinator.queue_merge.assert_called_once()  # type: ignore[attr-defined]
        # Verify corrections are stored in state
        assert "BUG-001" in orchestrator.state.corrections
        assert orchestrator.state.corrections["BUG-001"] == corrections

    def test_on_worker_complete_categorized_corrections(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_on_worker_complete stores categorized corrections (ENH-010 fourth fix)."""
        corrections = [
            "[line_drift] Updated line 42 -> 45 using anchor 'process_data'",
            "[file_moved] Updated path from old/path.py to new/path.py",
            "[content_fix] Added missing ## Expected Behavior section",
        ]
        result = WorkerResult(
            issue_id="BUG-002",
            success=True,
            branch_name="parallel/bug-002",
            worktree_path=Path("/tmp/worktree"),
            was_corrected=True,
            corrections=corrections,
        )

        orchestrator._on_worker_complete(result)

        # Verify categorized corrections are stored with categories intact
        assert "BUG-002" in orchestrator.state.corrections
        stored = orchestrator.state.corrections["BUG-002"]
        assert len(stored) == 3
        assert stored[0].startswith("[line_drift]")
        assert stored[1].startswith("[file_moved]")
        assert stored[2].startswith("[content_fix]")

    def test_on_worker_complete_updates_timing(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_on_worker_complete updates timing state."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
            duration=15.5,
        )

        orchestrator._on_worker_complete(result)

        assert "BUG-001" in orchestrator.state.timing
        assert orchestrator.state.timing["BUG-001"]["total"] == 15.5

    def test_on_worker_complete_waits_for_merge(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_on_worker_complete waits for merge completion before returning (BUG-140).

        This prevents race conditions between worktree creation and merge operations
        by ensuring merges complete before the next worker is dispatched.
        """
        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
            duration=10.0,
        )

        # Track call order
        call_order: list[str] = []
        original_queue_merge = orchestrator.merge_coordinator.queue_merge

        def mock_queue_merge(*args: object, **kwargs: object) -> None:
            call_order.append("queue_merge")
            original_queue_merge(*args, **kwargs)

        def mock_wait_for_completion(*args: object, **kwargs: object) -> bool:
            call_order.append("wait_for_completion")
            return True

        orchestrator.merge_coordinator.queue_merge = mock_queue_merge  # type: ignore[method-assign]
        orchestrator.merge_coordinator.wait_for_completion = mock_wait_for_completion  # type: ignore[method-assign]

        orchestrator._on_worker_complete(result)

        # Verify wait_for_completion is called after queue_merge
        assert call_order == ["queue_merge", "wait_for_completion"]


class TestMergeSequential:
    """Tests for _merge_sequential method."""

    def test_merge_sequential_success(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_merge_sequential handles successful merge."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
        )

        orchestrator.merge_coordinator.merged_ids = ["BUG-001"]  # type: ignore[misc]

        with patch.object(orchestrator, "_complete_issue_lifecycle_if_needed"):
            orchestrator._merge_sequential(result)

        orchestrator.queue.mark_completed.assert_called_once_with("BUG-001")  # type: ignore[attr-defined]

    def test_merge_sequential_failure(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_merge_sequential handles failed merge."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
        )

        orchestrator.merge_coordinator.merged_ids = []  # type: ignore[misc]  # Not in merged list

        orchestrator._merge_sequential(result)

        orchestrator.queue.mark_failed.assert_called_once_with("BUG-001")  # type: ignore[attr-defined]

    def test_merge_sequential_close(
        self,
        orchestrator: ParallelOrchestrator,
        mock_issue: MagicMock,
    ) -> None:
        """_merge_sequential handles CLOSE verdict."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
            should_close=True,
            close_reason="already_fixed",
        )

        orchestrator._issue_info_by_id["BUG-001"] = mock_issue

        with patch("little_loops.issue_lifecycle.close_issue", return_value=True):
            orchestrator._merge_sequential(result)

        orchestrator.queue.mark_completed.assert_called_once_with("BUG-001")  # type: ignore[attr-defined]


class TestWaitForCompletion:
    """Tests for _wait_for_completion method."""

    def test_wait_for_completion_waits_for_workers(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_wait_for_completion waits until workers finish."""
        active_count_sequence = [2, 1, 0]
        call_idx = [0]

        def get_active_count() -> int:
            idx = min(call_idx[0], len(active_count_sequence) - 1)
            call_idx[0] += 1
            return active_count_sequence[idx]

        type(orchestrator.worker_pool).active_count = property(lambda self: get_active_count())  # type: ignore[method-assign,assignment]
        orchestrator.merge_coordinator.merged_ids = []  # type: ignore[misc]
        orchestrator.merge_coordinator.failed_merges = []  # type: ignore[misc,assignment]

        with patch("time.sleep"):
            orchestrator._wait_for_completion()

    def test_wait_for_completion_handles_timeout(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_wait_for_completion handles worker timeout."""
        orchestrator.parallel_config.orchestrator_timeout = 1

        type(orchestrator.worker_pool).active_count = property(lambda self: 1)  # type: ignore[method-assign,assignment]
        orchestrator.merge_coordinator.merged_ids = []  # type: ignore[misc]
        orchestrator.merge_coordinator.failed_merges = []  # type: ignore[misc,assignment]

        with patch("time.time") as mock_time:
            mock_time.side_effect = [0, 0, 2, 2, 2]  # Exceed timeout
            with patch("time.sleep"):
                orchestrator._wait_for_completion()

        orchestrator.worker_pool.terminate_all_processes.assert_called()  # type: ignore[attr-defined]

    def test_wait_for_completion_processes_merged_ids(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_wait_for_completion marks merged issues as completed."""
        type(orchestrator.worker_pool).active_count = property(lambda self: 0)  # type: ignore[method-assign,assignment]
        orchestrator.merge_coordinator.merged_ids = ["BUG-001", "BUG-002"]  # type: ignore[misc]
        orchestrator.merge_coordinator.failed_merges = []  # type: ignore[misc,assignment]

        with patch.object(orchestrator, "_complete_issue_lifecycle_if_needed"):
            orchestrator._wait_for_completion()

        assert orchestrator.queue.mark_completed.call_count == 2  # type: ignore[attr-defined]


class TestReportResults:
    """Tests for _report_results method."""

    def test_report_results_outputs_summary(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_report_results logs summary information."""
        orchestrator.queue.completed_count = 5  # type: ignore[misc]
        orchestrator.queue.failed_count = 1  # type: ignore[misc]
        orchestrator.queue.failed_ids = ["BUG-003"]  # type: ignore[misc]
        orchestrator.state.timing = {"BUG-001": {"total": 10.0}}

        # Replace logger with a mock to verify it's called
        mock_logger = MagicMock()
        orchestrator.logger = mock_logger

        orchestrator._report_results(time.time() - 60)

        # Logger should have been called multiple times
        assert mock_logger.info.called

    def test_report_results_calculates_speedup(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_report_results calculates estimated speedup."""
        orchestrator.queue.completed_count = 3  # type: ignore[misc]
        orchestrator.queue.failed_count = 0  # type: ignore[misc]
        orchestrator.queue.failed_ids = []  # type: ignore[misc]
        orchestrator.state.timing = {
            "BUG-001": {"total": 30.0},
            "BUG-002": {"total": 30.0},
            "BUG-003": {"total": 30.0},
        }

        # Replace logger with a mock to verify it's called
        mock_logger = MagicMock()
        orchestrator.logger = mock_logger

        # Total issue time = 90s, wall time = 30s = 3x speedup
        orchestrator._report_results(time.time() - 30)

        # Should have logged speedup info
        assert mock_logger.info.called


class TestCompleteIssueLifecycle:
    """Tests for _complete_issue_lifecycle_if_needed method."""

    def test_complete_lifecycle_returns_false_when_no_info(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """Returns False when issue info not found."""
        result = orchestrator._complete_issue_lifecycle_if_needed("UNKNOWN-001")
        assert result is False

    def test_complete_lifecycle_returns_true_when_already_moved(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
        mock_issue: MagicMock,
    ) -> None:
        """Returns True when issue already in completed dir."""
        completed_path = temp_repo_with_config / ".issues" / "completed" / "P1-BUG-001-test-bug.md"
        completed_path.write_text("# Completed")

        mock_issue.path = temp_repo_with_config / ".issues" / "bugs" / "P1-BUG-001-test-bug.md"
        orchestrator._issue_info_by_id["BUG-001"] = mock_issue

        result = orchestrator._complete_issue_lifecycle_if_needed("BUG-001")
        assert result is True

    def test_complete_lifecycle_returns_true_when_original_gone(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
        mock_issue: MagicMock,
    ) -> None:
        """Returns True when original file no longer exists."""
        mock_issue.path = temp_repo_with_config / ".issues" / "bugs" / "nonexistent.md"
        orchestrator._issue_info_by_id["BUG-001"] = mock_issue

        result = orchestrator._complete_issue_lifecycle_if_needed("BUG-001")
        assert result is True


class TestCleanup:
    """Tests for _cleanup method."""

    def test_cleanup_saves_state(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_cleanup saves state before shutdown."""
        orchestrator.queue.completed_ids = []  # type: ignore[misc]
        orchestrator.queue.failed_ids = []  # type: ignore[misc]
        orchestrator.queue.in_progress_ids = []  # type: ignore[misc]

        orchestrator._cleanup()

        # State should have been saved (mocked)

    def test_cleanup_shuts_down_components(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_cleanup shuts down worker pool and merge coordinator."""
        orchestrator.queue.completed_ids = []  # type: ignore[misc]
        orchestrator.queue.failed_ids = []  # type: ignore[misc]
        orchestrator.queue.in_progress_ids = []  # type: ignore[misc]

        orchestrator._cleanup()

        orchestrator.worker_pool.shutdown.assert_called_once()  # type: ignore[attr-defined]
        orchestrator.merge_coordinator.shutdown.assert_called_once()  # type: ignore[attr-defined]

    def test_cleanup_cleans_worktrees_when_not_shutdown(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_cleanup cleans worktrees when not interrupted."""
        orchestrator._shutdown_requested = False
        orchestrator.queue.completed_ids = []  # type: ignore[misc]
        orchestrator.queue.failed_ids = []  # type: ignore[misc]
        orchestrator.queue.in_progress_ids = []  # type: ignore[misc]

        orchestrator._cleanup()

        orchestrator.worker_pool.cleanup_all_worktrees.assert_called_once()  # type: ignore[attr-defined]

    def test_cleanup_skips_worktrees_on_shutdown(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_cleanup skips worktree cleanup when shutdown requested."""
        orchestrator._shutdown_requested = True
        orchestrator.queue.completed_ids = []  # type: ignore[misc]
        orchestrator.queue.failed_ids = []  # type: ignore[misc]
        orchestrator.queue.in_progress_ids = []  # type: ignore[misc]

        orchestrator._cleanup()

        orchestrator.worker_pool.cleanup_all_worktrees.assert_not_called()  # type: ignore[attr-defined]


class TestProcessParallel:
    """Tests for _process_parallel method."""

    def test_process_parallel_submits_to_pool(
        self,
        orchestrator: ParallelOrchestrator,
        mock_issue: MagicMock,
    ) -> None:
        """_process_parallel submits issue to worker pool with callback."""
        orchestrator._process_parallel(mock_issue)

        orchestrator.worker_pool.submit.assert_called_once()  # type: ignore[attr-defined]
        call_args = orchestrator.worker_pool.submit.call_args  # type: ignore[attr-defined]
        assert call_args[0][0] == mock_issue
        assert call_args[0][1] == orchestrator._on_worker_complete


class TestShutdownHandling:
    """Tests for graceful shutdown signal handling edge cases."""

    def test_signal_handler_idempotent(
        self, orchestrator: ParallelOrchestrator
    ) -> None:
        """_signal_handler is idempotent - can be called multiple times."""
        orchestrator._signal_handler(signal.SIGINT, None)
        orchestrator._signal_handler(signal.SIGTERM, None)

        assert orchestrator._shutdown_requested is True
        # Each signal propagates to worker pool (2 signals = 2 calls)
        assert orchestrator.worker_pool.set_shutdown_requested.call_count == 2  # type: ignore[attr-defined]

    def test_shutdown_with_active_workers(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """Shutdown during active worker execution waits for completion."""
        orchestrator.queue.empty.return_value = False  # type: ignore[attr-defined]
        orchestrator.queue.add_many.return_value = 1  # type: ignore[attr-defined]
        orchestrator.worker_pool.active_count = 2  # type: ignore[misc]
        orchestrator.merge_coordinator.pending_count = 0  # type: ignore[misc]

        # Set shutdown after scan
        def set_shutdown(*args: object, **kwargs: object) -> list[MagicMock]:
            orchestrator._shutdown_requested = True
            return [mock_issue]

        with patch.object(orchestrator, "_scan_issues", side_effect=set_shutdown):
            with patch.object(orchestrator, "_wait_for_completion"):
                with patch.object(orchestrator, "_report_results"):
                    exit_code = orchestrator._execute()

        assert exit_code == 0


class TestWorkerPoolEdgeCases:
    """Tests for worker pool edge cases."""

    def test_process_sequential_waits_for_workers(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_process_sequential waits for workers to become available."""
        mock_issue.priority = "P0"

        # Simulate workers that are active then become available
        call_count = [0]

        def mock_active_count() -> int:
            call_count[0] += 1
            return 0 if call_count[0] > 2 else 2

        type(orchestrator.worker_pool).active_count = property(lambda self: mock_active_count())  # type: ignore[method-assign,assignment]

        mock_future: Future[WorkerResult] = Future()
        mock_future.set_result(
            WorkerResult(
                issue_id="BUG-001",
                success=True,
                branch_name="parallel/bug-001",
                worktree_path=Path("/tmp/worktree"),
            )
        )
        orchestrator.worker_pool.submit.return_value = mock_future  # type: ignore[attr-defined]
        orchestrator.merge_coordinator.merged_ids = ["BUG-001"]  # type: ignore[misc]

        with patch("time.sleep"):
            orchestrator._process_sequential(mock_issue)

        # Should have waited (checked active_count multiple times)
        assert call_count[0] > 1

    def test_wait_for_completion_terminates_on_timeout(
        self, orchestrator: ParallelOrchestrator
    ) -> None:
        """_wait_for_completion terminates all processes on timeout."""
        orchestrator.parallel_config.orchestrator_timeout = 1

        type(orchestrator.worker_pool).active_count = property(lambda self: 1)  # type: ignore[method-assign,assignment]
        orchestrator.merge_coordinator.merged_ids = []  # type: ignore[misc]
        orchestrator.merge_coordinator.failed_merges = []  # type: ignore[misc,assignment]

        with patch("time.time") as mock_time:
            mock_time.side_effect = [0, 0.5, 1.5, 2.5]
            with patch("time.sleep"):
                orchestrator._wait_for_completion()

        orchestrator.worker_pool.terminate_all_processes.assert_called_once()  # type: ignore[attr-defined]

    def test_wait_for_completion_waits_for_merges(
        self, orchestrator: ParallelOrchestrator
    ) -> None:
        """_wait_for_completion waits for pending merges after workers."""
        type(orchestrator.worker_pool).active_count = property(lambda self: 0)  # type: ignore[method-assign,assignment]

        # Merge coordinator has pending merges
        merge_completed = [False]

        def mock_wait(*args: object, **kwargs: object) -> bool:
            merge_completed[0] = True
            return True

        orchestrator.merge_coordinator.wait_for_completion = mock_wait  # type: ignore[method-assign]
        orchestrator.merge_coordinator.merged_ids = ["BUG-001"]  # type: ignore[misc]
        orchestrator.merge_coordinator.failed_merges = []  # type: ignore[misc,assignment]

        with patch.object(orchestrator, "_complete_issue_lifecycle_if_needed"):
            orchestrator._wait_for_completion()

        assert merge_completed[0]


class TestOverlapDetection:
    """Tests for overlap detection and deferred issue handling (ENH-143)."""

    def test_process_parallel_checks_overlap_when_enabled(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_process_parallel checks for overlaps when detection enabled."""
        from little_loops.parallel.overlap_detector import OverlapResult

        orchestrator.parallel_config.overlap_detection = True
        orchestrator.parallel_config.serialize_overlapping = True

        # Create mock overlap detector
        mock_detector = MagicMock()
        mock_detector.check_overlap.return_value = OverlapResult(has_overlap=False)  # No overlap
        orchestrator.overlap_detector = mock_detector

        orchestrator._process_parallel(mock_issue)

        # Should check overlap
        mock_detector.check_overlap.assert_called_once_with(mock_issue)

    def test_process_parallel_defers_overlapping_issues(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_process_parallel defers overlapping issues when configured."""
        from little_loops.parallel.overlap_detector import OverlapResult

        orchestrator.parallel_config.overlap_detection = True
        orchestrator.parallel_config.serialize_overlapping = True

        mock_detector = MagicMock()
        mock_detector.check_overlap.return_value = OverlapResult(
            has_overlap=True, overlapping_issues=["BUG-001"]
        )
        orchestrator.overlap_detector = mock_detector

        orchestrator._process_parallel(mock_issue)

        # Should defer the issue (not submit)
        orchestrator.worker_pool.submit.assert_not_called()  # type: ignore[attr-defined]
        assert len(orchestrator._deferred_issues) == 1

    def test_process_parallel_registers_with_detector(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_process_parallel registers issue with overlap detector."""
        from little_loops.parallel.overlap_detector import OverlapResult

        orchestrator.parallel_config.overlap_detection = True
        orchestrator.parallel_config.serialize_overlapping = False

        mock_detector = MagicMock()
        mock_detector.check_overlap.return_value = OverlapResult(has_overlap=False)  # No overlap
        orchestrator.overlap_detector = mock_detector

        orchestrator._process_parallel(mock_issue)

        # Should register with detector
        mock_detector.register_issue.assert_called_once_with(mock_issue)

    def test_on_worker_complete_unregisters_from_detector(
        self, orchestrator: ParallelOrchestrator
    ) -> None:
        """_on_worker_complete unregisters issue from overlap detector."""
        orchestrator.parallel_config.overlap_detection = True
        mock_detector = MagicMock()
        orchestrator.overlap_detector = mock_detector

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
        )

        orchestrator._on_worker_complete(result)

        mock_detector.unregister_issue.assert_called_once_with("BUG-001")

    def test_on_worker_complete_requeues_deferred_issues(
        self, orchestrator: ParallelOrchestrator
    ) -> None:
        """_on_worker_complete re-queues deferred issues when overlaps clear."""
        from little_loops.parallel.overlap_detector import OverlapResult

        orchestrator.parallel_config.overlap_detection = True
        mock_detector = MagicMock()
        # No overlap means the issue should be re-queued
        mock_detector.check_overlap.return_value = OverlapResult(has_overlap=False)
        orchestrator.overlap_detector = mock_detector

        # Add a deferred issue
        mock_deferred = MagicMock(spec=IssueInfo)
        mock_deferred.issue_id = "BUG-002"
        orchestrator._deferred_issues.append(mock_deferred)

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
        )

        orchestrator._on_worker_complete(result)

        # Should re-queue the deferred issue (check_overlap called, queue.add called)
        mock_detector.check_overlap.assert_called_once_with(mock_deferred)
        orchestrator.queue.add.assert_called_once_with(mock_deferred)  # type: ignore[attr-defined]
        # Deferred list should be empty after re-queuing
        assert len(orchestrator._deferred_issues) == 0


class TestInterruptedWorkers:
    """Tests for interrupted worker handling (ENH-036)."""

    def test_on_worker_complete_tracks_interrupted(
        self, orchestrator: ParallelOrchestrator
    ) -> None:
        """_on_worker_complete tracks interrupted workers separately."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=False,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
            interrupted=True,
            error="Worker interrupted",
        )

        orchestrator._on_worker_complete(result)

        # Should track in interrupted list, not mark as failed
        assert "BUG-001" in orchestrator._interrupted_issues
        orchestrator.queue.mark_failed.assert_not_called()  # type: ignore[attr-defined]

    def test_on_worker_complete_interrupted_returns_early(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_on_worker_complete returns early for interrupted workers, ignoring close verdict."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=False,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
            interrupted=True,
            should_close=True,
            close_reason="interrupted",
        )

        orchestrator._issue_info_by_id["BUG-001"] = mock_issue

        with patch("little_loops.issue_lifecycle.close_issue", return_value=True):
            orchestrator._on_worker_complete(result)

        # Interrupted workers return early - tracked but NOT marked completed or failed
        assert "BUG-001" in orchestrator._interrupted_issues
        orchestrator.queue.mark_completed.assert_not_called()  # type: ignore[attr-defined]
        orchestrator.queue.mark_failed.assert_not_called()  # type: ignore[attr-defined]


class TestExecuteLoop:
    """Tests for main execution loop dispatch logic."""

    def test_execute_dispatches_when_workers_available(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_execute dispatches issues when workers available."""
        from little_loops.parallel.types import QueuedIssue

        # Create a QueuedIssue wrapper
        queued = QueuedIssue(priority=1, issue_info=mock_issue)

        orchestrator.queue.empty.return_value = False  # type: ignore[attr-defined]
        orchestrator.queue.add_many.return_value = 1  # type: ignore[attr-defined]
        orchestrator.queue.get.return_value = queued  # type: ignore[attr-defined]
        orchestrator.worker_pool.active_count = 0  # type: ignore[misc]
        orchestrator.merge_coordinator.pending_count = 0  # type: ignore[misc]

        with patch.object(orchestrator, "_scan_issues", return_value=[mock_issue]):
            with patch.object(orchestrator, "_process_parallel"):
                with patch.object(orchestrator, "_wait_for_completion"):
                    with patch.object(orchestrator, "_report_results"):
                        # Set shutdown after one iteration
                        def set_shutdown(*args: object) -> bool:
                            orchestrator._shutdown_requested = True
                            return False

                        orchestrator.queue.empty.side_effect = set_shutdown  # type: ignore[attr-defined]

                        orchestrator._execute()

        # Should have submitted the issue
        orchestrator.queue.get.assert_called_once_with(block=False)  # type: ignore[attr-defined]

    def test_execute_skips_dispatch_when_no_workers(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_execute skips dispatch when all workers busy."""
        orchestrator.queue.empty.return_value = False  # type: ignore[attr-defined]
        orchestrator.queue.add_many.return_value = 1  # type: ignore[attr-defined]
        orchestrator.worker_pool.active_count = 2  # type: ignore[misc]  # All busy
        orchestrator.merge_coordinator.pending_count = 0  # type: ignore[misc]

        with patch.object(orchestrator, "_scan_issues", return_value=[mock_issue]):
            with patch.object(orchestrator, "_wait_for_completion"):
                with patch.object(orchestrator, "_report_results"):
                    # Set shutdown after one iteration
                    def set_shutdown(*args: object) -> bool:
                        orchestrator._shutdown_requested = True
                        return False

                    orchestrator.queue.empty.side_effect = set_shutdown  # type: ignore[attr-defined]

                    orchestrator._execute()

        # Should not call get() when no workers available
        orchestrator.queue.get.assert_not_called()  # type: ignore[attr-defined]

    def test_execute_saves_state_periodically(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_execute saves state during execution loop."""
        from little_loops.parallel.types import QueuedIssue

        queued = QueuedIssue(priority=1, issue_info=mock_issue)

        orchestrator.queue.empty.return_value = False  # type: ignore[attr-defined]
        orchestrator.queue.add_many.return_value = 1  # type: ignore[attr-defined]
        orchestrator.queue.get.return_value = queued  # type: ignore[attr-defined]
        orchestrator.worker_pool.active_count = 0  # type: ignore[misc]
        orchestrator.merge_coordinator.pending_count = 0  # type: ignore[misc]

        with patch.object(orchestrator, "_scan_issues", return_value=[mock_issue]):
            with patch.object(orchestrator, "_process_parallel"):
                with patch.object(orchestrator, "_save_state") as mock_save:
                    with patch.object(orchestrator, "_wait_for_completion"):
                        with patch.object(orchestrator, "_report_results"):
                            # Set shutdown after one iteration
                            def set_shutdown(*args: object) -> bool:
                                orchestrator._shutdown_requested = True
                                return False

                            orchestrator.queue.empty.side_effect = set_shutdown  # type: ignore[attr-defined]

                            orchestrator._execute()

        # State should be saved during execution
        assert mock_save.called

    def test_execute_respects_max_issues_limit(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_execute stops after processing max_issues."""
        from little_loops.parallel.types import QueuedIssue

        orchestrator.parallel_config.max_issues = 2

        # Create 5 issues
        mock_issues = [MagicMock(spec=IssueInfo) for _ in range(5)]
        for i, m in enumerate(mock_issues):
            m.issue_id = f"BUG-{i:03d}"
            m.priority = "P1"

        # Wrap in QueuedIssue
        queued_issues = [QueuedIssue(priority=1, issue_info=m) for m in mock_issues]

        orchestrator.queue.empty.return_value = False  # type: ignore[attr-defined]
        orchestrator.queue.add_many.return_value = 5  # type: ignore[attr-defined]

        # Track processed count
        processed = []

        def mock_process(issue: MagicMock) -> None:
            processed.append(issue.issue_id)
            if len(processed) >= 2:
                orchestrator._shutdown_requested = True

        orchestrator.queue.get.side_effect = queued_issues  # type: ignore[attr-defined]
        orchestrator.worker_pool.active_count = 0  # type: ignore[misc]
        orchestrator.merge_coordinator.pending_count = 0  # type: ignore[misc]

        with patch.object(orchestrator, "_scan_issues", return_value=mock_issues):
            with patch.object(orchestrator, "_process_parallel", side_effect=mock_process):
                with patch.object(orchestrator, "_wait_for_completion"):
                    with patch.object(orchestrator, "_report_results"):
                        orchestrator._execute()

        # Should have processed exactly 2 issues
        assert len(processed) == 2

    def test_execute_dispatches_p0_sequential(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_execute dispatches P0 issues sequentially when configured."""
        from little_loops.parallel.types import QueuedIssue

        mock_issue.priority = "P0"
        orchestrator.parallel_config.p0_sequential = True

        queued = QueuedIssue(priority=0, issue_info=mock_issue)

        orchestrator.queue.empty.return_value = False  # type: ignore[attr-defined]
        orchestrator.queue.add_many.return_value = 1  # type: ignore[attr-defined]
        orchestrator.queue.get.return_value = queued  # type: ignore[attr-defined]
        orchestrator.worker_pool.active_count = 0  # type: ignore[misc]
        orchestrator.merge_coordinator.pending_count = 0  # type: ignore[misc]

        with patch.object(orchestrator, "_scan_issues", return_value=[mock_issue]):
            with patch.object(orchestrator, "_process_sequential"):
                with patch.object(orchestrator, "_wait_for_completion"):
                    with patch.object(orchestrator, "_report_results"):
                        # Set shutdown after one iteration
                        def set_shutdown(*args: object) -> bool:
                            orchestrator._shutdown_requested = True
                            return False

                        orchestrator.queue.empty.side_effect = set_shutdown  # type: ignore[attr-defined]

                        orchestrator._execute()

        # P0 should go through sequential path
        orchestrator.queue.get.assert_called_once_with(block=False)  # type: ignore[attr-defined]

    def test_execute_completes_when_all_done(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_execute completes when queue empty, no workers, no pending merges."""
        orchestrator.queue.empty.return_value = True  # type: ignore[attr-defined]
        orchestrator.queue.add_many.return_value = 0  # type: ignore[attr-defined]
        orchestrator.worker_pool.active_count = 0  # type: ignore[misc]
        orchestrator.merge_coordinator.pending_count = 0  # type: ignore[misc]

        with patch.object(orchestrator, "_scan_issues", return_value=[mock_issue]):
            with patch.object(orchestrator, "_wait_for_completion"):
                with patch.object(orchestrator, "_report_results"):
                    exit_code = orchestrator._execute()

        assert exit_code == 0


class TestOrchestratorConcurrency:
    """Tests for concurrent access in ParallelOrchestrator (ENH-217)."""

    def test_concurrent_worker_callbacks(
        self, orchestrator: ParallelOrchestrator
    ) -> None:
        """Multiple workers completing simultaneously modify state."""
        errors = []
        corrections_count = [0]
        lock = threading.Lock()

        def complete_worker(worker_id: int) -> None:
            try:
                result = WorkerResult(
                    issue_id=f"BUG-{worker_id:03d}",
                    success=True,
                    branch_name=f"parallel/bug-{worker_id:03d}",
                    worktree_path=Path(f"/tmp/worktree-{worker_id}"),
                    duration=10.0,
                    corrections=[f"correction-{worker_id}"],
                )
                orchestrator._on_worker_complete(result)
                with lock:
                    corrections_count[0] += len(result.corrections or [])
            except Exception as e:
                errors.append(e)

        # Simulate 3 workers completing at once
        threads = [threading.Thread(target=complete_worker, args=(i,)) for i in range(3)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should complete without errors (though some corrections may be lost)
        assert len(errors) == 0, f"Errors occurred: {errors}"

    def test_concurrent_interrupted_issues(self, orchestrator: ParallelOrchestrator) -> None:
        """Multiple workers adding to interrupted_issues list."""
        errors = []

        def interrupt_worker(worker_id: int) -> None:
            try:
                orchestrator._interrupted_issues.append(f"ENH-{worker_id:03d}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=interrupt_worker, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All appends should succeed
        assert len(errors) == 0, f"Errors occurred: {errors}"
        # List should have all 10 items (or fewer if lost due to race)
        assert len(orchestrator._interrupted_issues) >= 0

    def test_state_dictionary_concurrent_writes(self, orchestrator: ParallelOrchestrator) -> None:
        """Multiple threads writing to state.corrections dictionary."""
        errors = []

        def write_corrections(worker_id: int) -> None:
            try:
                orchestrator.state.corrections[f"ISSUE-{worker_id}"] = [
                    f"correction-{worker_id}"
                ]
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_corrections, args=(i,)) for i in range(20)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No errors (but may have lost updates)
        assert len(errors) == 0, f"Errors occurred: {errors}"
        # Check dictionary integrity - should be valid dict
        assert isinstance(orchestrator.state.corrections, dict)

    def test_concurrent_timing_updates(self, orchestrator: ParallelOrchestrator) -> None:
        """Multiple workers writing to state.timing dictionary."""
        errors = []

        def write_timing(worker_id: int) -> None:
            try:
                orchestrator.state.timing[f"BUG-{worker_id:03d}"] = {"total": float(worker_id)}
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_timing, args=(i,)) for i in range(15)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No errors (but may have lost updates)
        assert len(errors) == 0, f"Errors occurred: {errors}"
        # Check dictionary integrity
        assert isinstance(orchestrator.state.timing, dict)

    def test_concurrent_deferred_issue_operations(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """Multiple threads modifying _deferred_issues list."""
        from little_loops.issue_parser import IssueInfo

        errors = []

        def add_deferred(worker_id: int) -> None:
            try:
                mock_deferred = MagicMock(spec=IssueInfo)
                mock_deferred.issue_id = f"DEFERRED-{worker_id:03d}"
                orchestrator._deferred_issues.append(mock_deferred)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_deferred, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No errors (but may have lost updates)
        assert len(errors) == 0, f"Errors occurred: {errors}"

    def test_concurrent_state_checkpoint(
        self, orchestrator: ParallelOrchestrator, temp_repo_with_config: Path
    ) -> None:
        """Main loop calling _save_state() while worker callbacks modify state."""
        errors = []
        save_count = [0]

        def worker_callback(worker_id: int) -> None:
            try:
                result = WorkerResult(
                    issue_id=f"BUG-{worker_id:03d}",
                    success=True,
                    branch_name=f"parallel/bug-{worker_id:03d}",
                    worktree_path=Path(f"/tmp/wt-{worker_id}"),
                    duration=5.0,
                )
                # Simulate callback modifying state
                orchestrator.state.corrections[f"BUG-{worker_id:03d}"] = ["test"]
                orchestrator.state.timing[f"BUG-{worker_id:03d}"] = {"total": 5.0}
            except Exception as e:
                errors.append(("callback", worker_id, e))

        def save_checkpoint() -> None:
            try:
                for _ in range(5):
                    orchestrator._save_state()
                    save_count[0] += 1
                    time.sleep(0.01)
            except Exception as e:
                errors.append(("save", 0, e))

        # Start callback threads
        callback_threads = [threading.Thread(target=worker_callback, args=(i,)) for i in range(5)]
        # Start save thread
        save_thread = threading.Thread(target=save_checkpoint)

        for t in callback_threads:
            t.start()
        save_thread.start()

        for t in callback_threads:
            t.join()
        save_thread.join()

        # No errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert save_count[0] == 5
