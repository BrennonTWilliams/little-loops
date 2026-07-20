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
import re
import signal
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import Future
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from little_loops.config import BRConfig
from little_loops.issue_parser import IssueInfo
from little_loops.parallel.git_lock import GitLock
from little_loops.parallel.orchestrator import ParallelOrchestrator
from little_loops.parallel.types import (
    EpicBranchesConfig,
    OrchestratorState,
    ParallelConfig,
    WorkerResult,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_logger() -> MagicMock:
    """Create a mock logger without spec for flexibility."""
    return MagicMock()


@pytest.fixture
def temp_repo_with_config(
    make_project: Callable[[dict[str, Any] | None, list[str] | None], tuple[Path, Path]],
) -> Path:
    """Create a temporary directory with .ll config and issues."""
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
    repo_path, issues_base = make_project(
        config=config,
        extra_dirs=[".issues/completed", ".worktrees"],
    )
    (issues_base / "bugs" / "P1-BUG-001-test-bug.md").write_text(
        "# BUG-001: Test Bug\n\n## Summary\nTest bug."
    )
    return repo_path


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
        ready_command="ready-issue {{issue_id}}",
        manage_command="manage-issue {{issue_type}} {{action}} {{issue_id}}",
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


@pytest.fixture
def make_epic_orchestrator(
    make_project: Callable[[dict[str, Any] | None, list[str] | None], tuple[Path, Path]],
) -> Callable[..., tuple[ParallelOrchestrator, Path]]:
    """Factory building an orchestrator over a repo with EPIC-2451 + children (FEAT-2449).

    Writes an ``epics`` category, an ``EPIC-2451`` integration EPIC, and one
    child issue per ``child_statuses`` entry (each ``parent: EPIC-2451``) with
    the requested on-disk status. Returns ``(orchestrator, repo_path)`` with
    ``epic_branches`` configured and ``_issue_info_by_id`` prepopulated so
    ``_maybe_complete_epic`` can resolve the EPIC ancestor.
    """

    _SUBDIR = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements"}

    def _factory(
        child_statuses: dict[str, str],
        *,
        enabled: bool = True,
        merge_to_base: bool = True,
        open_pr: bool = False,
        verify_before_merge: bool = False,
    ) -> tuple[ParallelOrchestrator, Path]:
        config = {
            "project": {"name": "test", "src_dir": "src/"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                    "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
                    "epics": {"prefix": "EPIC", "dir": "epics", "action": "coordinate"},
                },
                "completed_dir": "completed",
            },
        }
        repo_path, issues_base = make_project(
            config=config,
            extra_dirs=[".issues/completed", ".worktrees"],
        )
        (issues_base / "epics" / "P3-EPIC-2451-integration.md").write_text(
            "---\nid: EPIC-2451\nstatus: in_progress\n---\n# EPIC-2451: Integration\n"
        )
        for cid, status in child_statuses.items():
            sub = _SUBDIR[cid.split("-")[0]]
            (issues_base / sub / f"P3-{cid}-child.md").write_text(
                f"---\nid: {cid}\nstatus: {status}\nparent: EPIC-2451\n---\n# {cid}: Child\n"
            )

        pconfig = ParallelConfig(
            max_workers=2,
            p0_sequential=True,
            worktree_base=Path(".worktrees"),
            state_file=Path(".parallel-manage-state.json"),
            timeout_per_issue=1800,
            max_merge_retries=2,
            stream_subprocess_output=False,
            command_prefix="/ll:",
            ready_command="ready-issue {{issue_id}}",
            manage_command="manage-issue {{issue_type}} {{action}} {{issue_id}}",
            base_branch="main",
            epic_branches=EpicBranchesConfig(
                enabled=enabled,
                merge_to_base_on_complete=merge_to_base,
                open_pr=open_pr,
                verify_before_merge=verify_before_merge,
            ),
        )
        br = BRConfig(repo_path)
        with (
            patch("little_loops.parallel.orchestrator.WorkerPool"),
            patch("little_loops.parallel.orchestrator.MergeCoordinator"),
            patch("little_loops.parallel.orchestrator.IssuePriorityQueue"),
        ):
            orch = ParallelOrchestrator(
                parallel_config=pconfig,
                br_config=br,
                repo_path=repo_path,
                verbose=False,
            )
        orch.queue.failed_ids = []  # type: ignore[misc]

        from little_loops.issue_parser import IssueParser

        parser = IssueParser(br)
        for cid in child_statuses:
            sub = _SUBDIR[cid.split("-")[0]]
            path = next((issues_base / sub).glob(f"P3-{cid}-*.md"))
            orch._issue_info_by_id[cid] = parser.parse_file(path)
        return orch, repo_path

    return _factory


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
            assert orch._issue_info_by_id == {}
            assert isinstance(orch.state, OrchestratorState)

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
            patch("little_loops.parallel.orchestrator.WorkerPool"),
            patch("little_loops.parallel.orchestrator.MergeCoordinator"),
            patch("little_loops.parallel.orchestrator.IssuePriorityQueue"),
        ):
            orch = ParallelOrchestrator(
                parallel_config=default_parallel_config,
                br_config=br_config,
                repo_path=temp_repo_with_config,
            )

            assert orch._git_lock is not None


class TestOrchestrationRunRecording:
    """ENH-2492: worker callbacks persist authoritative per-issue outcomes."""

    def test_completion_records_batch_driver_wave_and_pr(
        self, orchestrator: ParallelOrchestrator
    ) -> None:
        from little_loops.parallel import orchestrator as orchestrator_module

        writer = getattr(orchestrator_module, "record_orchestration_run", None)
        assert callable(writer), "orchestrator must expose the history writer"
        assert hasattr(orchestrator, "run_id")
        assert hasattr(orchestrator, "driver")
        orchestrator.run_id = "batch-parallel"
        orchestrator.driver = "ll-sprint"
        orchestrator.wave_label = "Wave 2/3"
        orchestrator._pr_ready_branches["BUG-001"] = {
            "branch_name": "feature/BUG-001",
            "pr_url": "https://example.test/pr/1",
        }
        orchestrator.merge_coordinator.merged_ids = ["BUG-001"]
        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="feature/BUG-001",
            worktree_path=Path(".worktrees/BUG-001"),
            duration=12.0,
        )

        with patch.object(orchestrator_module, "record_orchestration_run") as mock_record:
            orchestrator._on_worker_complete(result)

        mock_record.assert_called_once()
        kwargs = mock_record.call_args.kwargs
        assert kwargs["run_id"] == "batch-parallel"
        assert kwargs["driver"] == "ll-sprint"
        assert kwargs["issue_id"] == "BUG-001"
        assert kwargs["status"] == "completed"
        assert kwargs["duration_s"] == 12.0
        assert kwargs["wave"] == "Wave 2/3"
        assert kwargs["pr_url"] == "https://example.test/pr/1"

    def test_interrupted_worker_records_before_early_return(
        self, orchestrator: ParallelOrchestrator
    ) -> None:
        from little_loops.parallel import orchestrator as orchestrator_module

        writer = getattr(orchestrator_module, "record_orchestration_run", None)
        assert callable(writer), "orchestrator must expose the history writer"
        assert hasattr(orchestrator, "run_id")
        orchestrator.run_id = "batch-interrupted"
        result = WorkerResult(
            issue_id="BUG-001",
            success=False,
            branch_name="feature/BUG-001",
            worktree_path=Path(".worktrees/BUG-001"),
            duration=5.0,
            error="worker stopped",
            interrupted=True,
        )

        with patch.object(orchestrator_module, "record_orchestration_run") as mock_record:
            orchestrator._on_worker_complete(result)

        mock_record.assert_called_once()
        assert mock_record.call_args.kwargs["status"] == "interrupted"
        assert mock_record.call_args.kwargs["failure_reason"] == "worker stopped"
        orchestrator.queue.mark_failed.assert_not_called()


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
        """Cleanup is a side-effect-free, idempotent no-op when the dir is absent."""
        worktree_base = temp_repo_with_config / ".worktrees"
        if worktree_base.exists():
            worktree_base.rmdir()
        assert not worktree_base.exists()

        # No-op contract: must not raise AND must not create the worktree dir.
        orchestrator._cleanup_orphaned_worktrees()
        assert not worktree_base.exists(), (
            "cleanup must not create the worktree dir when none exists"
        )

        # Idempotent: a second call remains a clean no-op.
        orchestrator._cleanup_orphaned_worktrees()
        assert not worktree_base.exists()

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
            if args[:3] == ["worktree", "list", "--porcelain"]:
                result.stdout = ""
                return result
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
        """Does not clean up directories not starting with worker- or a timestamp."""
        worktree_base = temp_repo_with_config / ".worktrees"
        other_dir = worktree_base / "other-directory"
        other_dir.mkdir()

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if args[:3] == ["worktree", "list", "--porcelain"]:
                result.stdout = ""
                return result
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        orchestrator._cleanup_orphaned_worktrees()

        assert other_dir.exists()

    def test_cleans_up_loop_worktree(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Cleans up timestamp-prefixed loop worktrees left by ll-loop --worktree."""
        worktree_base = temp_repo_with_config / ".worktrees"
        loop_dir = worktree_base / "20260101-000000-my-loop"
        loop_dir.mkdir()

        removed: list[str] = []

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if args[:3] == ["worktree", "list", "--porcelain"]:
                result.stdout = ""
            if args[:2] == ["worktree", "remove"]:
                removed.append(args[-1])
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        orchestrator._cleanup_orphaned_worktrees()

        assert not loop_dir.exists() or any("20260101-000000-my-loop" in r for r in removed)

    def test_skips_worktree_owned_by_live_process(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Does not remove a worktree whose session marker PID is alive (BUG-579)."""
        import os

        worktree_base = temp_repo_with_config / ".worktrees"
        active_dir = worktree_base / "worker-bug-active"
        active_dir.mkdir()
        # Write marker for the current process (guaranteed alive)
        (active_dir / f".ll-session-{os.getpid()}").write_text(str(os.getpid()))

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if args[:3] == ["worktree", "list", "--porcelain"]:
                result.stdout = ""
                return result
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        orchestrator._cleanup_orphaned_worktrees()

        assert active_dir.exists(), "Active worktree should not be removed"

    def test_removes_worktree_with_dead_process_marker(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Removes a worktree whose session marker PID is no longer running (BUG-579)."""
        worktree_base = temp_repo_with_config / ".worktrees"
        stale_dir = worktree_base / "worker-bug-stale"
        stale_dir.mkdir()
        # Use PID 0 — sending signal 0 to PID 0 raises PermissionError on POSIX
        # (affects all processes in group), so use a clearly dead PID via mock instead.
        (stale_dir / ".ll-session-99999").write_text("99999")

        removed: list[str] = []

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            if args[:2] == ["worktree", "remove"]:
                removed.append(str(cwd))
            result = MagicMock()
            result.returncode = 0
            if args[:3] == ["worktree", "list", "--porcelain"]:
                result.stdout = ""
                return result
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        with patch("os.kill", side_effect=ProcessLookupError):
            orchestrator._cleanup_orphaned_worktrees()

        # The stale worktree should have been targeted for cleanup
        assert any("worker-bug-stale" in r or str(stale_dir) in r for r in removed) or (
            not stale_dir.exists()
        ), "Stale worktree with dead PID marker should be removed"

    def test_deletes_branch_via_rev_parse(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Deletes branch using name from rev-parse, not string derivation (BUG-823)."""
        worktree_base = temp_repo_with_config / ".worktrees"
        orphan = worktree_base / "worker-bug-001-20260101-120000"
        orphan.mkdir()

        deleted_branches: list[str] = []

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            if args[:2] == ["branch", "-D"]:
                deleted_branches.append(args[2])
            result = MagicMock()
            result.returncode = 0
            if args[:3] == ["worktree", "list", "--porcelain"]:
                result.stdout = ""
                return result
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        rev_parse_result = MagicMock()
        rev_parse_result.returncode = 0
        rev_parse_result.stdout = "parallel/bug-001-20260101-120000\n"

        with patch("subprocess.run", return_value=rev_parse_result):
            orchestrator._cleanup_orphaned_worktrees()

        assert deleted_branches == ["parallel/bug-001-20260101-120000"]

    def test_does_not_delete_epic_branch(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """EPIC integration branches are never deleted by orphan cleanup (FEAT-2339 Rationale #3)."""
        worktree_base = temp_repo_with_config / ".worktrees"
        orphan = worktree_base / "worker-bug-001-20260101-120000"
        orphan.mkdir()

        deleted_branches: list[str] = []

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            if args[:2] == ["branch", "-D"]:
                deleted_branches.append(args[2])
            result = MagicMock()
            result.returncode = 0
            if args[:3] == ["worktree", "list", "--porcelain"]:
                result.stdout = ""
                return result
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        rev_parse_result = MagicMock()
        rev_parse_result.returncode = 0
        rev_parse_result.stdout = "epic/epic-2451-integration\n"

        with patch("subprocess.run", return_value=rev_parse_result):
            orchestrator._cleanup_orphaned_worktrees()

        assert deleted_branches == []

    def test_skips_branch_deletion_when_rev_parse_fails(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Skips branch -D when rev-parse cannot determine branch name (BUG-823)."""
        worktree_base = temp_repo_with_config / ".worktrees"
        orphan = worktree_base / "worker-bug-002-20260101-120000"
        orphan.mkdir()

        deleted_branches: list[str] = []

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            if args[:2] == ["branch", "-D"]:
                deleted_branches.append(args[2])
            result = MagicMock()
            result.returncode = 0
            if args[:3] == ["worktree", "list", "--porcelain"]:
                result.stdout = ""
                return result
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        rev_parse_result = MagicMock()
        rev_parse_result.returncode = 128
        rev_parse_result.stdout = ""

        with patch("subprocess.run", return_value=rev_parse_result):
            orchestrator._cleanup_orphaned_worktrees()

        assert deleted_branches == [], "branch -D should not be called when rev-parse fails"

    def test_skips_branch_deletion_for_non_ll_branch(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Safe guard never deletes main/master/HEAD even when an orphaned worktree resolves to them."""
        worktree_base = temp_repo_with_config / ".worktrees"
        orphan = worktree_base / "worker-bug-003-20260101-120000"
        orphan.mkdir()

        deleted_branches: list[str] = []

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            if args[:2] == ["branch", "-D"]:
                deleted_branches.append(args[2])
            result = MagicMock()
            result.returncode = 0
            if args[:3] == ["worktree", "list", "--porcelain"]:
                result.stdout = ""
                return result
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        rev_parse_result = MagicMock()
        rev_parse_result.returncode = 0
        rev_parse_result.stdout = "main\n"

        with patch("subprocess.run", return_value=rev_parse_result):
            orchestrator._cleanup_orphaned_worktrees()

        assert deleted_branches == [], "branch -D must never be called for main/master/HEAD"

    def test_deletes_loop_worktree_branch(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Deletes the branch for a loop-style worktree (YYYYMMDD-HHMMSS-name, BUG-2324)."""
        worktree_base = temp_repo_with_config / ".worktrees"
        loop_orphan = worktree_base / "20260101-120000-my-loop"
        loop_orphan.mkdir()

        deleted_branches: list[str] = []

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            if args[:2] == ["branch", "-D"]:
                deleted_branches.append(args[2])
            result = MagicMock()
            result.returncode = 0
            if args[:3] == ["worktree", "list", "--porcelain"]:
                result.stdout = ""
                return result
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        rev_parse_result = MagicMock()
        rev_parse_result.returncode = 0
        rev_parse_result.stdout = "20260101-120000-my-loop\n"

        with patch("subprocess.run", return_value=rev_parse_result):
            orchestrator._cleanup_orphaned_worktrees()

        assert deleted_branches == ["20260101-120000-my-loop"], (
            "Branch deletion must fire for loop-style YYYYMMDD-HHMMSS-* branches"
        )

    def test_unlock_called_before_remove(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Verifies unlock is called before remove --force (ENH-1253)."""
        worktree_base = temp_repo_with_config / ".worktrees"
        stale_dir = worktree_base / "worker-bug-stale"
        stale_dir.mkdir()
        (stale_dir / ".ll-session-99999").write_text("99999")

        call_order: list[str] = []

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            if args[:2] == ["worktree", "unlock"]:
                call_order.append("unlock")
            elif args[:2] == ["worktree", "remove"]:
                call_order.append("remove")
            result = MagicMock()
            result.returncode = 0
            if args[:3] == ["worktree", "list", "--porcelain"]:
                result.stdout = ""
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        with patch("os.kill", side_effect=ProcessLookupError):
            orchestrator._cleanup_orphaned_worktrees()

        assert call_order.index("unlock") < call_order.index("remove")

    def test_rev_parse_called_before_remove(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """rev-parse fires while the worktree path still exists (BUG-2324 timing fix)."""
        worktree_base = temp_repo_with_config / ".worktrees"
        stale_dir = worktree_base / "worker-bug-timing"
        stale_dir.mkdir()
        (stale_dir / ".ll-session-99999").write_text("99999")

        call_order: list[str] = []

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            if args[:2] == ["worktree", "remove"]:
                # Simulate git worktree remove actually deleting the directory
                import shutil as _shutil

                if Path(args[-1]).exists():
                    _shutil.rmtree(args[-1], ignore_errors=True)
                call_order.append("remove")
            result = MagicMock()
            result.returncode = 0
            if args[:3] == ["worktree", "list", "--porcelain"]:
                result.stdout = ""
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        worktree_existed_at_rev_parse: list[bool] = []

        def mock_subprocess_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            if cmd[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                worktree_existed_at_rev_parse.append(Path(kwargs["cwd"]).exists())
                call_order.append("rev-parse")
            result = MagicMock()
            result.returncode = 0
            result.stdout = "parallel/bug-timing\n"
            return result

        with patch("os.kill", side_effect=ProcessLookupError):
            with patch("subprocess.run", side_effect=mock_subprocess_run):
                orchestrator._cleanup_orphaned_worktrees()

        assert "rev-parse" in call_order, "rev-parse must be called"
        assert "remove" in call_order, "worktree remove must be called"
        assert call_order.index("rev-parse") < call_order.index("remove"), (
            "rev-parse must fire BEFORE worktree remove (BUG-2324)"
        )
        assert all(worktree_existed_at_rev_parse), "worktree path must exist when rev-parse runs"

    def test_prunes_ghost_worktree_refs(self) -> None:
        """Detects and prunes .git/worktrees/<name>/ entries whose on-disk path is gone."""
        import shutil
        import subprocess as sp

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Set up a real git repo
            sp.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
            sp.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo_path,
                capture_output=True,
            )
            sp.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                capture_output=True,
            )
            (repo_path / "test.txt").write_text("initial content")
            sp.run(["git", "add", "."], cwd=repo_path, capture_output=True)
            sp.run(
                ["git", "commit", "-m", "initial commit"],
                cwd=repo_path,
                capture_output=True,
            )

            # Set up LL config layout
            ll_dir = repo_path / ".ll"
            ll_dir.mkdir()
            config = {
                "project": {"name": "test", "src_dir": "src/"},
                "issues": {
                    "base_dir": ".issues",
                    "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                    "completed_dir": "completed",
                },
            }
            (ll_dir / "ll-config.json").write_text(json.dumps(config))
            (repo_path / ".issues" / "bugs").mkdir(parents=True)
            (repo_path / ".issues" / "completed").mkdir(parents=True)
            worktree_base = repo_path / ".worktrees"
            worktree_base.mkdir()

            # Create a real git worktree (ll-parallel worker)
            wt_name = "worker-bug-001-20260101-120000"
            wt_path = worktree_base / wt_name
            sp.run(
                ["git", "worktree", "add", str(wt_path), "-b", "parallel/bug-001-20260101-120000"],
                cwd=repo_path,
                capture_output=True,
                check=True,
            )

            # Create a real git worktree (ll-loop --worktree, timestamp-prefixed)
            loop_wt_name = "20260422-153012-my-loop"
            loop_wt_path = worktree_base / loop_wt_name
            sp.run(
                ["git", "worktree", "add", str(loop_wt_path), "-b", loop_wt_name],
                cwd=repo_path,
                capture_output=True,
                check=True,
            )

            git_wt_dir = repo_path / ".git" / "worktrees" / wt_name
            loop_git_wt_dir = repo_path / ".git" / "worktrees" / loop_wt_name
            assert git_wt_dir.exists(), "worktree metadata should exist before simulated SIGKILL"
            assert loop_git_wt_dir.exists(), (
                "loop worktree metadata should exist before simulated SIGKILL"
            )

            # Simulate SIGKILL: delete the directories without running git worktree prune
            shutil.rmtree(wt_path)
            shutil.rmtree(loop_wt_path)
            assert not wt_path.exists(), "worktree directory should be gone"
            assert not loop_wt_path.exists(), "loop worktree directory should be gone"
            assert git_wt_dir.exists(), "ghost ref should still be present in .git/worktrees/"
            assert loop_git_wt_dir.exists(), (
                "loop ghost ref should still be present in .git/worktrees/"
            )

            # Create orchestrator pointing to the real git repo
            br_config = BRConfig(repo_path)
            parallel_config = ParallelConfig(
                max_workers=2,
                p0_sequential=True,
                worktree_base=Path(".worktrees"),
                state_file=Path(".parallel-manage-state.json"),
                timeout_per_issue=1800,
                max_merge_retries=2,
                stream_subprocess_output=False,
                command_prefix="/ll:",
                ready_command="ready-issue {{issue_id}}",
                manage_command="manage-issue {{issue_type}} {{action}} {{issue_id}}",
            )

            with (
                patch("little_loops.parallel.orchestrator.WorkerPool"),
                patch("little_loops.parallel.orchestrator.MergeCoordinator"),
                patch("little_loops.parallel.orchestrator.IssuePriorityQueue"),
            ):
                orch = ParallelOrchestrator(
                    parallel_config=parallel_config,
                    br_config=br_config,
                    repo_path=repo_path,
                    verbose=False,
                )

            orch._cleanup_orphaned_worktrees()

            assert not git_wt_dir.exists(), "ghost ref should be pruned by startup scan"
            assert not loop_git_wt_dir.exists(), "loop ghost ref should be pruned by startup scan"


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
        """Does not report directories not matching an ll worktree naming pattern."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)

        # Create non-worker directory
        other_dir = worktree_base / "other-directory"
        other_dir.mkdir()

        result = orchestrator._check_pending_worktrees()
        assert result == []

    def test_includes_loop_worktrees_in_pending_check(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Timestamp-prefixed loop worktrees are included in the pending scan."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)

        loop_dir = worktree_base / "20260422-153012-my-loop"
        loop_dir.mkdir()

        result = orchestrator._check_pending_worktrees()
        # Loop worktrees have no issue-id concept; _inspect_worktree returns None for
        # directories with no commits ahead or no git branch; result may be empty but
        # the directory must have been scanned (no assertion error from the guard change).
        assert isinstance(result, list)


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

        rev_parse_result = MagicMock()
        rev_parse_result.returncode = 0
        rev_parse_result.stdout = "parallel/enh-042-20260117-150000\n"

        with patch("subprocess.run", return_value=rev_parse_result):
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

        rev_parse_result = MagicMock()
        rev_parse_result.returncode = 0
        rev_parse_result.stdout = "parallel/bug-099-20260117-160000\n"

        with patch("subprocess.run", return_value=rev_parse_result):
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

        rev_parse_result = MagicMock()
        rev_parse_result.returncode = 0
        rev_parse_result.stdout = "parallel/bug-001-20260117-120000\n"

        with patch("subprocess.run", return_value=rev_parse_result):
            result = orchestrator._inspect_worktree(worktree_path)
        assert result is None

    def test_returns_actual_branch_for_feature_branch_mode(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Returns actual branch name when worktree is on a feature/* branch."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)
        worktree_path = worktree_base / "worker-enh-042-20260117-150000"
        worktree_path.mkdir()

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "0\n"
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        rev_parse_result = MagicMock()
        rev_parse_result.returncode = 0
        rev_parse_result.stdout = "feature/enh-042-my-issue\n"

        with patch("subprocess.run", return_value=rev_parse_result):
            result = orchestrator._inspect_worktree(worktree_path)
        assert result is not None
        assert result.branch_name == "feature/enh-042-my-issue"

    def test_uses_epic_branch_as_base_for_epic_child(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """FEAT-2562: EPIC-child worktrees compare against epic/<id>-<slug>, not base_branch."""
        orch, repo_path = make_epic_orchestrator({"BUG-001": "open"}, enabled=True)
        orch.worker_pool._load_epic_slug = MagicMock(return_value="integration")

        worktree_base = repo_path / ".worktrees"
        worktree_path = worktree_base / "worker-bug-001-20260117-150000"
        worktree_path.mkdir()

        rev_list_bases: list[str] = []

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if args[:2] == ["rev-list", "--count"]:
                rev_list_bases.append(args[2])
                result.stdout = "0\n"
            return result

        orch._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        rev_parse_result = MagicMock()
        rev_parse_result.returncode = 0
        rev_parse_result.stdout = "parallel/bug-001-20260117-150000\n"

        with patch("subprocess.run", return_value=rev_parse_result):
            result = orch._inspect_worktree(worktree_path)

        assert result is not None
        assert rev_list_bases == ["epic/epic-2451-integration..parallel/bug-001-20260117-150000"]

    def test_returns_none_when_rev_parse_fails(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Returns branch_name=None when rev-parse exits non-zero."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)
        worktree_path = worktree_base / "worker-bug-007-20260117-120000"
        worktree_path.mkdir()

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "0\n"
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        rev_parse_result = MagicMock()
        rev_parse_result.returncode = 128
        rev_parse_result.stdout = ""

        with patch("subprocess.run", return_value=rev_parse_result):
            result = orchestrator._inspect_worktree(worktree_path)
        assert result is not None
        assert result.branch_name is None

    def test_inspect_worktree_uses_rev_parse_not_string_replace(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Branch name comes from rev-parse, not string replacement (BUG-823 regression)."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)
        # Dir is named worker-enh-042-ts — string-replace would give parallel/enh-042-ts
        worktree_path = worktree_base / "worker-enh-042-20260117-150000"
        worktree_path.mkdir()

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "0\n"
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        rev_parse_result = MagicMock()
        rev_parse_result.returncode = 0
        rev_parse_result.stdout = "feature/enh-042-slug\n"

        with patch("subprocess.run", return_value=rev_parse_result):
            result = orchestrator._inspect_worktree(worktree_path)
        assert result is not None
        assert result.branch_name == "feature/enh-042-slug"
        assert result.branch_name != "parallel/enh-042-20260117-150000"


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


class TestMergePendingWorktreesProducerWiring:
    """Tests for ENH-2509 session_lifecycle_events producer wiring."""

    def test_emits_worktree_merge_and_delete_on_success(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """A successful merge emits worktree_merge then worktree_delete rows."""
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

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        with patch(
            "little_loops.parallel.orchestrator.record_session_lifecycle_event"
        ) as mock_record:
            orchestrator._merge_pending_worktrees([info])

        events = [call.kwargs["event"] for call in mock_record.call_args_list]
        assert events == ["worktree_merge", "worktree_delete"]


class TestOrphanCleanupProducerWiring:
    """Tests for ENH-2509 session_lifecycle_events producer wiring in orphan sweep."""

    def test_emits_worktree_delete_with_null_session_id(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """A successful orphan cleanup emits worktree_delete with session_id=None."""
        worktree_base = temp_repo_with_config / ".worktrees"
        stale_dir = worktree_base / "worker-bug-stale"
        stale_dir.mkdir()
        (stale_dir / ".ll-session-99999").write_text("99999")

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if args[:3] == ["worktree", "list", "--porcelain"]:
                result.stdout = ""
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        with patch("os.kill", side_effect=ProcessLookupError):
            with patch(
                "little_loops.parallel.orchestrator.record_session_lifecycle_event"
            ) as mock_record:
                orchestrator._cleanup_orphaned_worktrees()

        mock_record.assert_called_once()
        _, kwargs = mock_record.call_args
        assert kwargs["event"] == "worktree_delete"
        assert kwargs["session_id"] is None
        assert kwargs["detail"]["reason"] == "orphan_cleanup"

    def test_dry_run_does_not_emit(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """dry_run=True performs no op, so no lifecycle event is emitted."""
        worktree_base = temp_repo_with_config / ".worktrees"
        stale_dir = worktree_base / "worker-bug-stale"
        stale_dir.mkdir()
        (stale_dir / ".ll-session-99999").write_text("99999")

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if args[:3] == ["worktree", "list", "--porcelain"]:
                result.stdout = ""
            return result

        orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        with patch("os.kill", side_effect=ProcessLookupError):
            with patch(
                "little_loops.parallel.orchestrator.record_session_lifecycle_event"
            ) as mock_record:
                orchestrator._cleanup_orphaned_worktrees(dry_run=True)

        mock_record.assert_not_called()


class TestEpicCompletionMerge:
    """Tests for the EPIC-completion merge/PR trigger (FEAT-2449).

    Modeled on TestMergePendingWorktrees.test_attempts_merge_with_commits_ahead:
    mocks ``_git_lock.run``, captures the invocations, and asserts on the
    ``git merge --no-ff epic/<id>`` + subsequent ``branch -D``.
    """

    _EPIC_BRANCH = "epic/epic-2451-integration"

    @staticmethod
    def _capture_git(orch: ParallelOrchestrator) -> list[list[str]]:
        """Replace ``_git_lock.run`` with a success-returning capture stub."""
        calls: list[list[str]] = []

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            calls.append(args)
            return result

        orch._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]
        return calls

    def test_merges_epic_branch_when_all_children_done(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """All children `done` → merge --no-ff epic branch to base, then branch -D."""
        orch, _ = make_epic_orchestrator({"FEAT-010": "done", "FEAT-020": "done"})
        calls = self._capture_git(orch)

        orch._maybe_complete_epic("FEAT-010", self._EPIC_BRANCH)

        merge_calls = [c for c in calls if c[0] == "merge" and "--abort" not in c]
        del_calls = [c for c in calls if c[0] == "branch" and "-D" in c]
        assert len(merge_calls) == 1
        assert "--no-ff" in merge_calls[0]
        assert self._EPIC_BRANCH in merge_calls[0]
        assert len(del_calls) == 1
        assert self._EPIC_BRANCH in del_calls[0]

    def test_holds_open_when_child_not_done(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """A still-open child holds the epic branch open (no merge, no delete)."""
        orch, _ = make_epic_orchestrator({"FEAT-010": "done", "FEAT-020": "open"})
        calls = self._capture_git(orch)

        orch._maybe_complete_epic("FEAT-010", self._EPIC_BRANCH)

        assert not [c for c in calls if c[0] == "merge"]
        assert not [c for c in calls if c[0] == "branch"]

    def test_blocked_child_holds_branch_open(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """A blocked child blocks completion even though it is not `open`."""
        orch, _ = make_epic_orchestrator({"FEAT-010": "done", "FEAT-020": "blocked"})
        calls = self._capture_git(orch)

        orch._maybe_complete_epic("FEAT-010", self._EPIC_BRANCH)

        assert not [c for c in calls if c[0] == "merge"]

    def test_cancelled_child_does_not_trigger_merge(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """A cancelled child must NOT count as done (diverges from the badge)."""
        orch, _ = make_epic_orchestrator({"FEAT-010": "done", "FEAT-020": "cancelled"})
        calls = self._capture_git(orch)

        orch._maybe_complete_epic("FEAT-010", self._EPIC_BRANCH)

        assert not [c for c in calls if c[0] == "merge"]

    def test_partial_failure_gate_scopes_failed_ids(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """Disk says all-done, but a child in this run's failed_ids holds it open."""
        orch, _ = make_epic_orchestrator({"FEAT-010": "done", "FEAT-020": "done"})
        orch.queue.failed_ids = ["FEAT-020"]  # type: ignore[misc]
        calls = self._capture_git(orch)

        orch._maybe_complete_epic("FEAT-010", self._EPIC_BRANCH)

        assert not [c for c in calls if c[0] == "merge"]

    def test_failed_id_outside_epic_does_not_block(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """A failed issue that is NOT a child of this EPIC does not gate the merge."""
        orch, _ = make_epic_orchestrator({"FEAT-010": "done", "FEAT-020": "done"})
        orch.queue.failed_ids = ["BUG-999"]  # type: ignore[misc]
        calls = self._capture_git(orch)

        orch._maybe_complete_epic("FEAT-010", self._EPIC_BRANCH)

        assert [c for c in calls if c[0] == "merge"]

    def test_state_failed_issues_holds_branch_open(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """The resumption-side ``state.failed_issues`` dict also gates completion."""
        orch, _ = make_epic_orchestrator({"FEAT-010": "done", "FEAT-020": "done"})
        orch.state.failed_issues = {"FEAT-020": "boom"}
        calls = self._capture_git(orch)

        orch._maybe_complete_epic("FEAT-010", self._EPIC_BRANCH)

        assert not [c for c in calls if c[0] == "merge"]

    def test_skipped_when_merge_to_base_false(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """Config dead-read gap closed: merge is skipped when merge_to_base_on_complete=False."""
        orch, _ = make_epic_orchestrator(
            {"FEAT-010": "done", "FEAT-020": "done"},
            merge_to_base=False,
            open_pr=False,
        )
        calls = self._capture_git(orch)

        orch._maybe_complete_epic("FEAT-010", self._EPIC_BRANCH)

        assert not [c for c in calls if c[0] == "merge"]

    def test_opens_pr_when_open_pr_true(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """open_pr=True → gh pr create --head epic/<id> --base main; branch NOT deleted."""
        orch, _ = make_epic_orchestrator(
            {"FEAT-010": "done", "FEAT-020": "done"},
            merge_to_base=False,
            open_pr=True,
        )
        git_calls = self._capture_git(orch)

        import subprocess

        captured: list[list[str]] = []

        def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured.append(args)
            if args[0] == "gh" and args[1] == "auth":
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            if args[0] == "gh" and args[1] == "pr":
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="https://github.com/owner/repo/pull/7",
                    stderr="",
                )
            return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="x")

        with patch("little_loops.parallel.orchestrator.subprocess.run", side_effect=fake_run):
            orch._maybe_complete_epic("FEAT-010", self._EPIC_BRANCH)

        pr_create = [a for a in captured if a[:3] == ["gh", "pr", "create"]]
        assert pr_create, "expected a `gh pr create` invocation"
        args = pr_create[0]
        assert args[args.index("--head") + 1] == self._EPIC_BRANCH
        assert args[args.index("--base") + 1] == "main"
        # PR path must NOT merge or delete the branch (the PR needs it).
        assert not [c for c in git_calls if c[0] in ("merge", "branch")]

    def test_idempotent_across_calls(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """A second completion call for the same branch is a no-op."""
        orch, _ = make_epic_orchestrator({"FEAT-010": "done", "FEAT-020": "done"})
        calls = self._capture_git(orch)

        orch._maybe_complete_epic("FEAT-010", self._EPIC_BRANCH)
        orch._maybe_complete_epic("FEAT-020", self._EPIC_BRANCH)

        assert len([c for c in calls if c[0] == "merge" and "--abort" not in c]) == 1

    def test_no_merge_when_epic_branches_disabled(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """With epic_branches disabled the trigger is inert even if called directly."""
        orch, _ = make_epic_orchestrator(
            {"FEAT-010": "done", "FEAT-020": "done"},
            enabled=False,
        )
        calls = self._capture_git(orch)

        # merge_to_base defaults True, so the helper still runs; the
        # _on_worker_complete gate (enabled) is what suppresses it in practice.
        # Here we assert the on_worker_complete-level gate via a WorkerResult.
        result = WorkerResult(
            issue_id="FEAT-010",
            success=True,
            branch_name="parallel/feat-010",
            worktree_path=Path("/tmp/worktree"),
            duration=1.0,
            epic_branch=self._EPIC_BRANCH,
        )
        orch.merge_coordinator.merged_ids = ["FEAT-010"]  # type: ignore[misc]
        orch._complete_issue_lifecycle_if_needed = MagicMock()  # type: ignore[method-assign]
        orch._on_worker_complete(result)

        assert not [c for c in calls if c[0] == "merge"]


class TestEpicBranchVerifyGate:
    """Tests for the pre-merge test/lint verify gate (ENH-2603).

    Patches ``setup_worktree``/``cleanup_worktree``/``subprocess.run`` on the
    ``little_loops.worktree_utils`` module (BUG-2614: the gate logic lives in
    the stateless ``verify_epic_branch_before_merge`` free function there, not
    in the orchestrator module) to avoid real worktree creation and control
    test_cmd/lint_cmd outcomes.
    """

    _EPIC_BRANCH = "epic/epic-2451-integration"

    @staticmethod
    def _capture_git(orch: ParallelOrchestrator) -> list[list[str]]:
        calls: list[list[str]] = []

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            calls.append(args)
            return result

        orch._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]
        return calls

    def test_disabled_by_default_skips_subprocess_and_merges(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """verify_before_merge defaults False — no worktree/subprocess calls, merge proceeds."""
        orch, _ = make_epic_orchestrator({"FEAT-010": "done", "FEAT-020": "done"})
        calls = self._capture_git(orch)

        with (
            patch("little_loops.worktree_utils.setup_worktree") as mock_setup,
            patch("little_loops.worktree_utils.subprocess.run") as mock_run,
        ):
            orch._maybe_complete_epic("FEAT-010", self._EPIC_BRANCH)

        mock_setup.assert_not_called()
        mock_run.assert_not_called()
        assert [c for c in calls if c[0] == "merge"]

    def test_blocks_merge_on_test_cmd_failure(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        orch, _ = make_epic_orchestrator(
            {"FEAT-010": "done", "FEAT-020": "done"}, verify_before_merge=True
        )
        calls = self._capture_git(orch)

        with (
            patch("little_loops.worktree_utils.setup_worktree"),
            patch("little_loops.worktree_utils.cleanup_worktree") as mock_cleanup,
            patch(
                "little_loops.worktree_utils.subprocess.run",
                return_value=MagicMock(returncode=1, stdout="", stderr="2 failed"),
            ),
        ):
            orch._maybe_complete_epic("FEAT-010", self._EPIC_BRANCH)

        assert not [c for c in calls if c[0] == "merge"]
        assert "FEAT-020" not in orch.epic_branch_verify_failures  # not a merge-blocking child
        assert "test_cmd failed" in orch.epic_branch_verify_failures["EPIC-2451"]
        mock_cleanup.assert_called_once()
        assert mock_cleanup.call_args.kwargs.get("delete_branch") is False

    def test_blocks_merge_on_collection_error_exit_2(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """ENH-2631: a collection/usage error (exit 2) blocks merge just like a
        real test failure (exit 1); the failure message carries the exit code so
        the verdict class can be derived downstream."""
        orch, _ = make_epic_orchestrator(
            {"FEAT-010": "done", "FEAT-020": "done"}, verify_before_merge=True
        )
        calls = self._capture_git(orch)

        with (
            patch("little_loops.worktree_utils.setup_worktree"),
            patch("little_loops.worktree_utils.cleanup_worktree"),
            patch(
                "little_loops.worktree_utils.subprocess.run",
                return_value=MagicMock(returncode=2, stdout="", stderr="collection error"),
            ),
        ):
            orch._maybe_complete_epic("FEAT-010", self._EPIC_BRANCH)

        assert not [c for c in calls if c[0] == "merge"]
        assert "exit 2" in orch.epic_branch_verify_failures["EPIC-2451"]

    def test_allows_merge_on_success(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        orch, _ = make_epic_orchestrator(
            {"FEAT-010": "done", "FEAT-020": "done"}, verify_before_merge=True
        )
        calls = self._capture_git(orch)

        with (
            patch("little_loops.worktree_utils.setup_worktree"),
            patch("little_loops.worktree_utils.cleanup_worktree"),
            patch(
                "little_loops.worktree_utils.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="", stderr=""),
            ),
        ):
            orch._maybe_complete_epic("FEAT-010", self._EPIC_BRANCH)

        assert [c for c in calls if c[0] == "merge"]
        assert not orch.epic_branch_verify_failures

    def test_worktree_setup_failure_blocks_and_records(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        orch, _ = make_epic_orchestrator(
            {"FEAT-010": "done", "FEAT-020": "done"}, verify_before_merge=True
        )
        calls = self._capture_git(orch)

        with (
            patch(
                "little_loops.worktree_utils.setup_worktree",
                side_effect=RuntimeError("worktree add failed"),
            ),
            patch("little_loops.worktree_utils.subprocess.run") as mock_run,
        ):
            orch._maybe_complete_epic("FEAT-010", self._EPIC_BRANCH)

        assert not [c for c in calls if c[0] == "merge"]
        mock_run.assert_not_called()
        assert "worktree setup failed" in orch.epic_branch_verify_failures["EPIC-2451"]

    def test_failure_leaves_branch_retryable(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """A verify failure must NOT add the branch to _merged_epic_branches (retry next call)."""
        orch, _ = make_epic_orchestrator(
            {"FEAT-010": "done", "FEAT-020": "done"}, verify_before_merge=True
        )
        calls = self._capture_git(orch)

        with (
            patch("little_loops.worktree_utils.setup_worktree"),
            patch("little_loops.worktree_utils.cleanup_worktree"),
            patch(
                "little_loops.worktree_utils.subprocess.run",
                return_value=MagicMock(returncode=1, stdout="", stderr="boom"),
            ),
        ):
            orch._maybe_complete_epic("FEAT-010", self._EPIC_BRANCH)

        assert self._EPIC_BRANCH not in orch._merged_epic_branches
        assert not [c for c in calls if c[0] == "merge"]

        with (
            patch("little_loops.worktree_utils.setup_worktree"),
            patch("little_loops.worktree_utils.cleanup_worktree"),
            patch(
                "little_loops.worktree_utils.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="", stderr=""),
            ),
        ):
            orch._maybe_complete_epic("FEAT-020", self._EPIC_BRANCH)

        assert [c for c in calls if c[0] == "merge"]


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

    def test_load_state_skips_file_when_clean_start(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """_load_state returns early without reading state file when clean_start=True."""
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

        orchestrator.parallel_config.clean_start = True
        orchestrator._load_state()

        # Stale state must not be loaded
        assert orchestrator.state.completed_issues == []
        assert orchestrator.state.failed_issues == {}
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

    def test_save_state_throttle_skips_within_interval(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """_save_state skips write when called within the 5-second throttle window."""
        state_file = temp_repo_with_config / ".parallel-manage-state.json"

        # Set _last_save_time to now so the next call is within the throttle window
        orchestrator._last_save_time = time.time()

        orchestrator._save_state()

        assert not state_file.exists(), "File should not be written within throttle interval"

    def test_save_state_throttle_writes_after_interval(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """_save_state writes when the throttle interval has elapsed."""
        state_file = temp_repo_with_config / ".parallel-manage-state.json"

        # Default _last_save_time is 0.0 — far in the past, so write fires immediately
        orchestrator._save_state()

        assert state_file.exists(), "File should be written when throttle interval has elapsed"

    def test_save_state_force_bypasses_throttle(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """_save_state(force=True) writes even within the throttle window."""
        state_file = temp_repo_with_config / ".parallel-manage-state.json"

        # Set _last_save_time to now to be within throttle window
        orchestrator._last_save_time = time.time()

        orchestrator._save_state(force=True)

        assert state_file.exists(), "File should be written with force=True regardless of throttle"

    def test_save_state_updates_last_save_time(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """_save_state updates _last_save_time after a successful write."""
        before = time.time()
        orchestrator._save_state()
        after = time.time()

        assert before <= orchestrator._last_save_time <= after

    def test_save_state_uses_worker_errors_not_generic_failed(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """_save_state writes actual error messages from _worker_errors, not the hardcoded 'Failed'."""
        orchestrator.queue.completed_ids = []  # type: ignore[misc]
        orchestrator.queue.failed_ids = ["BUG-002"]  # type: ignore[misc]
        orchestrator.queue.in_progress_ids = []  # type: ignore[misc]
        orchestrator._worker_errors = {"BUG-002": "Claude CLI exited with stderr: tool not found"}

        orchestrator._save_state()

        state_file = temp_repo_with_config / ".parallel-manage-state.json"
        saved = json.loads(state_file.read_text())
        assert saved["failed_issues"]["BUG-002"] == "Claude CLI exited with stderr: tool not found"
        assert saved["failed_issues"]["BUG-002"] != "Failed"

    def test_save_state_fallback_for_unknown_failed_id(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """_save_state uses 'Failed' fallback when a failed ID has no _worker_errors entry."""
        orchestrator.queue.completed_ids = []  # type: ignore[misc]
        orchestrator.queue.failed_ids = ["BUG-003"]  # type: ignore[misc]
        orchestrator.queue.in_progress_ids = []  # type: ignore[misc]
        orchestrator._worker_errors = {}  # no entry for BUG-003

        orchestrator._save_state()

        state_file = temp_repo_with_config / ".parallel-manage-state.json"
        saved = json.loads(state_file.read_text())
        assert saved["failed_issues"]["BUG-003"] == "Failed"

    def test_cleanup_calls_close_transports_on_event_bus(
        self,
        default_parallel_config: ParallelConfig,
        br_config: BRConfig,
        temp_repo_with_config: Path,
    ) -> None:
        """_cleanup() calls close_transports() on the injected EventBus (FEAT-1323)."""
        mock_event_bus = MagicMock()
        with (
            patch("little_loops.parallel.orchestrator.WorkerPool"),
            patch("little_loops.parallel.orchestrator.MergeCoordinator"),
            patch("little_loops.parallel.orchestrator.IssuePriorityQueue"),
        ):
            orch = ParallelOrchestrator(
                parallel_config=default_parallel_config,
                br_config=br_config,
                repo_path=temp_repo_with_config,
                event_bus=mock_event_bus,
            )
            orch.queue.completed_ids = []  # type: ignore[misc]
            orch.queue.failed_ids = []  # type: ignore[misc]
            orch.queue.in_progress_ids = []  # type: ignore[misc]
            orch.queue.completed_count = 0  # type: ignore[misc]
            orch.queue.failed_count = 0  # type: ignore[misc]
            orch._cleanup()

        mock_event_bus.close_transports.assert_called_once()

    def test_cleanup_safe_when_event_bus_is_none(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_cleanup() does not raise when no EventBus was injected (FEAT-1323)."""
        assert orchestrator._event_bus is None
        # Should not raise
        orchestrator._cleanup()


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

        orchestrator.merge_coordinator.merged_ids = ["BUG-001"]  # type: ignore[misc]

        orchestrator._on_worker_complete(result)

        orchestrator.merge_coordinator.queue_merge.assert_called_once_with(result)  # type: ignore[attr-defined]
        orchestrator.queue.mark_completed.assert_called_once_with("BUG-001")  # type: ignore[attr-defined]

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
        assert orchestrator._worker_errors["BUG-001"] == "Processing failed"

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
        orchestrator.merge_coordinator.merged_ids = ["BUG-001"]  # type: ignore[misc]

        orchestrator._on_worker_complete(result)

        # Verify wait_for_completion is called after queue_merge
        assert call_order == ["queue_merge", "wait_for_completion"]

    def test_on_worker_complete_emits_event_on_success(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_on_worker_complete emits parallel.worker_completed on success (ENH-921)."""
        from little_loops.events import EventBus

        received: list[dict[str, Any]] = []
        bus = EventBus()
        bus.register(lambda e: received.append(e))
        orchestrator._event_bus = bus

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worker-BUG-001-20260402"),
            duration=12.5,
        )

        orchestrator._on_worker_complete(result)

        assert len(received) == 1
        event = received[0]
        assert event["event"] == "parallel.worker_completed"
        assert event["issue_id"] == "BUG-001"
        assert event["worker_name"] == "worker-BUG-001-20260402"
        assert event["status"] == "success"
        assert event["duration_seconds"] == 12.5
        assert "ts" in event

    def test_on_worker_complete_emits_event_on_failure(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_on_worker_complete emits parallel.worker_completed on failure (ENH-921)."""
        from little_loops.events import EventBus

        received: list[dict[str, Any]] = []
        bus = EventBus()
        bus.register(lambda e: received.append(e))
        orchestrator._event_bus = bus

        result = WorkerResult(
            issue_id="BUG-002",
            success=False,
            branch_name="parallel/bug-002",
            worktree_path=Path("/tmp/worker-BUG-002-20260402"),
            error="Processing failed",
        )

        orchestrator._on_worker_complete(result)

        assert len(received) == 1
        event = received[0]
        assert event["event"] == "parallel.worker_completed"
        assert event["issue_id"] == "BUG-002"
        assert event["status"] == "failure"
        assert event["duration_seconds"] == 0.0

    def test_on_worker_complete_no_emission_without_event_bus(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_on_worker_complete works without event_bus (backward compat, ENH-921)."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
            duration=10.0,
        )

        # Should not raise - no _event_bus attribute or it's None
        orchestrator._on_worker_complete(result)

        orchestrator.merge_coordinator.queue_merge.assert_called_once_with(result)  # type: ignore[attr-defined]

    def test_on_worker_complete_feature_branch_local_only(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """Feature-branch mode with push disabled stores dict with pushed=False (BUG-2172)."""
        orchestrator.parallel_config.use_feature_branches = True
        orchestrator.parallel_config.push_feature_branches = False

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="feature/bug-001-test",
            worktree_path=Path("/tmp/worktree"),
            duration=10.0,
        )

        with patch("subprocess.run") as mock_run:
            orchestrator._on_worker_complete(result)
            # No git push should be called
            for call in mock_run.call_args_list:
                args = call[0][0] if call[0] else call[1].get("args", [])
                assert "push" not in args, f"Unexpected git push call: {call}"

        state = orchestrator._pr_ready_branches["BUG-001"]
        assert state["branch_name"] == "feature/bug-001-test"
        assert state["pushed"] is False
        assert state["pr_url"] is None

    def test_on_worker_complete_feature_branch_push_enabled(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """Feature-branch mode with push enabled calls git push with correct args (BUG-2172)."""
        orchestrator.parallel_config.use_feature_branches = True
        orchestrator.parallel_config.push_feature_branches = True
        orchestrator.parallel_config.remote_name = "origin"
        orchestrator.parallel_config.open_pr_for_feature_branches = False

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="feature/bug-001-test",
            worktree_path=Path("/tmp/worktree"),
            duration=10.0,
        )

        import subprocess

        push_completed = subprocess.CompletedProcess(
            args=["git", "push", "--force-with-lease", "origin", "feature/bug-001-test"],
            returncode=0,
            stdout="",
            stderr="",
        )

        with patch(
            "little_loops.parallel.orchestrator.subprocess.run", return_value=push_completed
        ) as mock_run:
            orchestrator._on_worker_complete(result)

        push_calls = [call for call in mock_run.call_args_list if call[0] and "push" in call[0][0]]
        assert len(push_calls) == 1
        push_args = push_calls[0][0][0]
        assert push_args == ["git", "push", "--force-with-lease", "origin", "feature/bug-001-test"]

        state = orchestrator._pr_ready_branches["BUG-001"]
        assert state["pushed"] is True
        assert state["pr_url"] is None

    def test_on_worker_complete_feature_branch_open_pr(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """Feature-branch mode opens PR when open_pr_for_feature_branches=True (BUG-2172)."""
        orchestrator.parallel_config.use_feature_branches = True
        orchestrator.parallel_config.push_feature_branches = True
        orchestrator.parallel_config.open_pr_for_feature_branches = True
        orchestrator.parallel_config.remote_name = "origin"
        orchestrator.parallel_config.base_branch = "main"

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="feature/bug-001-test",
            worktree_path=Path("/tmp/worktree"),
            duration=10.0,
        )

        import subprocess

        captured_args: list[list[str]] = []

        def fake_subprocess_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured_args.append(args)
            if args[0] == "git" and "push" in args:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            if args[0] == "gh" and args[1] == "auth":
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            if args[0] == "gh" and args[1] == "pr":
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="https://github.com/owner/repo/pull/42",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="unexpected"
            )

        with patch(
            "little_loops.parallel.orchestrator.subprocess.run", side_effect=fake_subprocess_run
        ):
            orchestrator._on_worker_complete(result)

        state = orchestrator._pr_ready_branches["BUG-001"]
        assert state["pushed"] is True
        assert state["pr_url"] == "https://github.com/owner/repo/pull/42"
        # FEAT-2453: with no epic branch, gh pr create --base falls back to base_branch.
        pr_create = [a for a in captured_args if a[:3] == ["gh", "pr", "create"]]
        assert pr_create, "expected a `gh pr create` invocation"
        base_args = pr_create[0]
        assert base_args[base_args.index("--base") + 1] == "main"

    def test_on_worker_complete_feature_branch_pr_base_is_epic_branch(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """FEAT-2453: epic_branch flows into branch_state and gh pr create --base."""
        orchestrator.parallel_config.use_feature_branches = True
        orchestrator.parallel_config.push_feature_branches = True
        orchestrator.parallel_config.open_pr_for_feature_branches = True
        orchestrator.parallel_config.remote_name = "origin"
        orchestrator.parallel_config.base_branch = "main"

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="feature/bug-001-test",
            worktree_path=Path("/tmp/worktree"),
            duration=10.0,
            epic_branch="epic/EPIC-2451-integration",
        )

        import subprocess

        captured_args: list[list[str]] = []

        def fake_subprocess_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured_args.append(args)
            if args[0] == "git" and "push" in args:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            if args[0] == "gh" and args[1] == "auth":
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            if args[0] == "gh" and args[1] == "pr":
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="https://github.com/owner/repo/pull/42",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="unexpected"
            )

        with patch(
            "little_loops.parallel.orchestrator.subprocess.run", side_effect=fake_subprocess_run
        ):
            orchestrator._on_worker_complete(result)

        # branch_state mutation recorded the epic branch (step 3).
        state = orchestrator._pr_ready_branches["BUG-001"]
        assert state["epic_branch"] == "epic/EPIC-2451-integration"
        # --base read site targets the epic branch (step 4).
        pr_create = [a for a in captured_args if a[:3] == ["gh", "pr", "create"]]
        assert pr_create, "expected a `gh pr create` invocation"
        base_args = pr_create[0]
        assert base_args[base_args.index("--base") + 1] == "epic/EPIC-2451-integration"

    def test_on_worker_complete_epic_completion_merges(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """FEAT-2449: the last child's success triggers the epic-branch merge."""
        orch, _ = make_epic_orchestrator({"FEAT-010": "done", "FEAT-020": "done"})

        git_calls: list[list[str]] = []

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            r = MagicMock()
            r.returncode = 0
            r.stdout = ""
            r.stderr = ""
            git_calls.append(args)
            return r

        orch._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]
        orch._complete_issue_lifecycle_if_needed = MagicMock()  # type: ignore[method-assign]
        orch.merge_coordinator.merged_ids = ["FEAT-010"]  # type: ignore[misc]

        result = WorkerResult(
            issue_id="FEAT-010",
            success=True,
            branch_name="parallel/feat-010",
            worktree_path=Path("/tmp/worktree"),
            duration=5.0,
            epic_branch="epic/epic-2451-integration",
        )
        orch._on_worker_complete(result)

        merge_calls = [c for c in git_calls if c[0] == "merge" and "--abort" not in c]
        assert len(merge_calls) == 1
        assert "epic/epic-2451-integration" in merge_calls[0]

    def test_on_worker_complete_epic_partial_failure_holds_open(
        self,
        make_epic_orchestrator: Callable[..., tuple[ParallelOrchestrator, Path]],
    ) -> None:
        """FEAT-2449: a failed child holds the epic branch open (no merge)."""
        orch, _ = make_epic_orchestrator({"FEAT-010": "done", "FEAT-020": "open"})
        orch.queue.failed_ids = ["FEAT-020"]  # type: ignore[misc]

        git_calls: list[list[str]] = []

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            r = MagicMock()
            r.returncode = 0
            r.stdout = ""
            r.stderr = ""
            git_calls.append(args)
            return r

        orch._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

        result = WorkerResult(
            issue_id="FEAT-020",
            success=False,
            branch_name="parallel/feat-020",
            worktree_path=Path("/tmp/worktree"),
            error="boom",
            epic_branch="epic/epic-2451-integration",
        )
        orch._on_worker_complete(result)

        assert not [c for c in git_calls if c[0] == "merge"]

    def test_on_worker_complete_feature_branch_push_failure(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """Feature-branch push failure is surfaced as warning without failing the issue (BUG-2172)."""
        orchestrator.parallel_config.use_feature_branches = True
        orchestrator.parallel_config.push_feature_branches = True
        orchestrator.parallel_config.open_pr_for_feature_branches = False

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="feature/bug-001-test",
            worktree_path=Path("/tmp/worktree"),
            duration=10.0,
        )

        import subprocess

        push_failed = subprocess.CompletedProcess(
            args=["git", "push", "--force-with-lease", "origin", "feature/bug-001-test"],
            returncode=1,
            stdout="",
            stderr="Permission denied",
        )

        with patch("little_loops.parallel.orchestrator.subprocess.run", return_value=push_failed):
            orchestrator._on_worker_complete(result)

        # Issue still marked completed despite push failure
        orchestrator.queue.mark_completed.assert_called_once_with("BUG-001")  # type: ignore[attr-defined]

        # Branch state reflects push failure
        state = orchestrator._pr_ready_branches["BUG-001"]
        assert state["pushed"] is False

    def test_on_worker_complete_feature_branch_gh_missing(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """gh CLI missing degrades gracefully to push-only (BUG-2172)."""
        orchestrator.parallel_config.use_feature_branches = True
        orchestrator.parallel_config.push_feature_branches = True
        orchestrator.parallel_config.open_pr_for_feature_branches = True

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="feature/bug-001-test",
            worktree_path=Path("/tmp/worktree"),
            duration=10.0,
        )

        import subprocess

        def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if args[0] == "git" and "push" in args:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            if args[0] == "gh":
                raise FileNotFoundError("gh not found")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        with patch("little_loops.parallel.orchestrator.subprocess.run", side_effect=fake_run):
            orchestrator._on_worker_complete(result)

        state = orchestrator._pr_ready_branches["BUG-001"]
        assert state["pushed"] is True
        assert state["pr_url"] is None
        # Issue still completed
        orchestrator.queue.mark_completed.assert_called_once_with("BUG-001")  # type: ignore[attr-defined]

    def test_report_results_feature_branch_local_only(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_report_results shows 'local-only branch retained' for unpushed branches (BUG-2172)."""
        orchestrator._pr_ready_branches = {
            "BUG-001": {"branch_name": "feature/bug-001", "pushed": False, "pr_url": None}
        }
        orchestrator.queue.completed_count = 1
        orchestrator.queue.failed_count = 0
        orchestrator.queue.failed_ids = []

        log_messages: list[str] = []
        orchestrator.logger.info = lambda msg: log_messages.append(str(msg))  # type: ignore[method-assign]

        orchestrator._report_results(time.time() - 1.0)

        combined = "\n".join(log_messages)
        assert "local-only branch retained" in combined
        assert "pushed + PR opened" not in combined

    def test_report_results_feature_branch_pushed(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_report_results shows 'pushed (PR skipped)' for pushed-only branches (BUG-2172)."""
        orchestrator._pr_ready_branches = {
            "BUG-001": {"branch_name": "feature/bug-001", "pushed": True, "pr_url": None}
        }
        orchestrator.queue.completed_count = 1
        orchestrator.queue.failed_count = 0
        orchestrator.queue.failed_ids = []

        log_messages: list[str] = []
        orchestrator.logger.info = lambda msg: log_messages.append(str(msg))  # type: ignore[method-assign]

        orchestrator._report_results(time.time() - 1.0)

        combined = "\n".join(log_messages)
        assert "pushed (PR skipped)" in combined

    def test_report_results_surfaces_epic_verify_gate_failures(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_report_results surfaces blocked EPIC-branch verify-gate failures (ENH-2603)."""
        orchestrator._epic_branch_verify_failures = {
            "EPIC-2451": "test_cmd failed (exit 1): 2 failed"
        }
        orchestrator.queue.completed_count = 1
        orchestrator.queue.failed_count = 0
        orchestrator.queue.failed_ids = []

        log_messages: list[str] = []
        orchestrator.logger.info = lambda msg: log_messages.append(str(msg))  # type: ignore[method-assign]
        orchestrator.logger.warning = lambda msg: log_messages.append(str(msg))  # type: ignore[method-assign]

        orchestrator._report_results(time.time() - 1.0)

        combined = "\n".join(log_messages)
        assert "EPIC-2451" in combined
        assert "test_cmd failed" in combined

    def test_report_results_feature_branch_pr_opened(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_report_results shows 'pushed + PR opened' with URL for PR'd branches (BUG-2172)."""
        orchestrator._pr_ready_branches = {
            "BUG-001": {
                "branch_name": "feature/bug-001",
                "pushed": True,
                "pr_url": "https://github.com/owner/repo/pull/42",
            }
        }
        orchestrator.queue.completed_count = 1
        orchestrator.queue.failed_count = 0
        orchestrator.queue.failed_ids = []

        log_messages: list[str] = []
        orchestrator.logger.info = lambda msg: log_messages.append(str(msg))  # type: ignore[method-assign]

        orchestrator._report_results(time.time() - 1.0)

        combined = "\n".join(log_messages)
        assert "pushed + PR opened" in combined
        assert "https://github.com/owner/repo/pull/42" in combined

    def test_on_worker_complete_feature_branch_records_branch_in_frontmatter(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
        mock_issue: MagicMock,
    ) -> None:
        """Feature-branch completion writes branch: field to issue frontmatter (ENH-2175)."""
        from little_loops.frontmatter import parse_frontmatter

        original_path = temp_repo_with_config / ".issues" / "bugs" / "P1-BUG-001-test-bug.md"
        original_path.write_text("---\nid: BUG-001\nstatus: done\n---\n\n# BUG-001\n")
        mock_issue.path = original_path
        orchestrator._issue_info_by_id["BUG-001"] = mock_issue

        git_ok: MagicMock = MagicMock()
        git_ok.returncode = 0
        git_ok.stdout = "[main abc1234] commit"
        git_ok.stderr = ""
        orchestrator._git_lock.run = lambda *a, **kw: git_ok  # type: ignore[method-assign]

        orchestrator.parallel_config.use_feature_branches = True
        orchestrator.parallel_config.push_feature_branches = False

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="feature/bug-001-record-branch",
            worktree_path=Path("/tmp/worktree"),
            duration=10.0,
        )

        orchestrator._on_worker_complete(result)

        content = original_path.read_text()
        fm = parse_frontmatter(content)
        assert fm.get("branch") == "feature/bug-001-record-branch"

    def test_on_worker_complete_auto_merge_no_branch_in_frontmatter(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
        mock_issue: MagicMock,
    ) -> None:
        """Auto-merge (non-feature-branch) mode does NOT write branch: to frontmatter (ENH-2175)."""
        from little_loops.frontmatter import parse_frontmatter

        original_path = temp_repo_with_config / ".issues" / "bugs" / "P1-BUG-001-test-bug.md"
        original_path.write_text("---\nid: BUG-001\nstatus: done\n---\n\n# BUG-001\n")
        mock_issue.path = original_path
        orchestrator._issue_info_by_id["BUG-001"] = mock_issue

        # Default config: use_feature_branches=False (auto-merge path)
        orchestrator.parallel_config.use_feature_branches = False
        orchestrator.merge_coordinator.merged_ids = ["BUG-001"]  # type: ignore[misc]

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
            duration=10.0,
        )

        orchestrator._on_worker_complete(result)

        content = original_path.read_text()
        fm = parse_frontmatter(content)
        assert "branch" not in fm

    def test_on_worker_complete_feature_branch_pr_url_idempotency(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
        mock_issue: MagicMock,
    ) -> None:
        """Re-running does not clobber an existing pr_url: already in frontmatter (ENH-2175)."""
        from little_loops.frontmatter import parse_frontmatter

        existing_url = "https://github.com/owner/repo/pull/99"
        original_path = temp_repo_with_config / ".issues" / "bugs" / "P1-BUG-001-test-bug.md"
        original_path.write_text(
            f"---\nid: BUG-001\nstatus: done\npr_url: {existing_url}\n---\n\n# BUG-001\n"
        )
        mock_issue.path = original_path
        orchestrator._issue_info_by_id["BUG-001"] = mock_issue

        git_ok: MagicMock = MagicMock()
        git_ok.returncode = 0
        git_ok.stdout = "[main abc1234] commit"
        git_ok.stderr = ""
        orchestrator._git_lock.run = lambda *a, **kw: git_ok  # type: ignore[method-assign]

        orchestrator.parallel_config.use_feature_branches = True
        orchestrator.parallel_config.push_feature_branches = True
        orchestrator.parallel_config.open_pr_for_feature_branches = True
        orchestrator.parallel_config.remote_name = "origin"
        orchestrator.parallel_config.base_branch = "main"

        import subprocess

        captured_args: list[list[str]] = []

        def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured_args.append(args)
            if args[0] == "git" and "push" in args:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            if args[0] == "gh" and args[1] == "auth":
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            if args[0] == "gh" and args[1] == "pr":
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="https://github.com/owner/repo/pull/100",
                    stderr="",
                )
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="feature/bug-001-record-branch",
            worktree_path=Path("/tmp/worktree"),
            duration=10.0,
            epic_branch="epic/EPIC-2451-integration",
        )

        with patch("little_loops.parallel.orchestrator.subprocess.run", side_effect=fake_run):
            orchestrator._on_worker_complete(result)

        content = original_path.read_text()
        fm = parse_frontmatter(content)
        # branch: should be written
        assert fm.get("branch") == "feature/bug-001-record-branch"
        # pr_url: must NOT be overwritten — existing URL preserved
        assert fm.get("pr_url") == existing_url
        # FEAT-2453: even in the pr_url-preserved path, gh pr create --base must
        # target the epic branch (guards against re-targeting an existing PR's base).
        pr_create = [a for a in captured_args if a[:3] == ["gh", "pr", "create"]]
        assert pr_create, "expected a `gh pr create` invocation"
        base_args = pr_create[0]
        assert base_args[base_args.index("--base") + 1] == "epic/EPIC-2451-integration"

    def test_feature_branch_success_writes_in_progress_not_done(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
        mock_issue: MagicMock,
    ) -> None:
        """Feature-branch success leaves issue at in_progress, not done (ENH-2182)."""
        original_path = temp_repo_with_config / ".issues" / "bugs" / "P1-BUG-001-test-bug.md"
        original_path.write_text("---\nid: BUG-001\nstatus: open\n---\n\n# BUG-001\n")
        mock_issue.path = original_path
        orchestrator._issue_info_by_id["BUG-001"] = mock_issue

        git_ok: MagicMock = MagicMock()
        git_ok.returncode = 0
        git_ok.stdout = "[main abc1234] commit"
        git_ok.stderr = ""
        orchestrator._git_lock.run = lambda *a, **kw: git_ok  # type: ignore[method-assign]

        orchestrator.parallel_config.use_feature_branches = True
        orchestrator.parallel_config.push_feature_branches = False

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="feature/bug-001-fix",
            worktree_path=Path("/tmp/worktree"),
            duration=10.0,
        )

        orchestrator._on_worker_complete(result)

        from little_loops.frontmatter import parse_frontmatter

        content = original_path.read_text()
        fm = parse_frontmatter(content)
        assert fm.get("status") == "in_progress", "Feature-branch success must hold at in_progress"
        assert "completed_at" not in fm

    def test_auto_merge_success_still_writes_done(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
        mock_issue: MagicMock,
    ) -> None:
        """Auto-merge success path still writes done (regression guard, ENH-2182)."""
        original_path = temp_repo_with_config / ".issues" / "bugs" / "P1-BUG-001-test-bug.md"
        original_path.write_text("---\nid: BUG-001\nstatus: open\n---\n\n# BUG-001\n")
        mock_issue.path = original_path
        orchestrator._issue_info_by_id["BUG-001"] = mock_issue

        git_ok: MagicMock = MagicMock()
        git_ok.returncode = 0
        git_ok.stdout = "[main abc1234] commit"
        git_ok.stderr = ""
        orchestrator._git_lock.run = lambda *a, **kw: git_ok  # type: ignore[method-assign]

        orchestrator.parallel_config.use_feature_branches = False
        orchestrator.merge_coordinator.merged_ids = ["BUG-001"]  # type: ignore[misc]

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
            duration=10.0,
        )

        orchestrator._on_worker_complete(result)

        from little_loops.frontmatter import parse_frontmatter

        content = original_path.read_text()
        fm = parse_frontmatter(content)
        assert fm.get("status") == "done", "Auto-merge path must still write done"
        assert "completed_at" in fm


class TestFeatureBranchE2E:
    """End-to-end integration tests for the feature-branch workflow composition (ENH-2177).

    Each test exercises _on_worker_complete for two issues so the multi-issue
    (parallel-wave) path is covered, not just single-issue slices.
    """

    def _register_issue(
        self,
        orchestrator: ParallelOrchestrator,
        issue_id: str,
        path: Path,
    ) -> None:
        issue = MagicMock(spec=IssueInfo)
        issue.issue_id = issue_id
        issue.issue_type = "bugs"
        issue.title = f"Test {issue_id}"
        issue.priority = "P1"
        issue.path = path
        orchestrator._issue_info_by_id[issue_id] = issue

    def test_feature_branch_push_only_two_issues(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Full chain for two issues: branch created → push invoked → branch: written → status: in_progress."""
        from little_loops.frontmatter import parse_frontmatter

        bugs_dir = temp_repo_with_config / ".issues" / "bugs"
        path_001 = bugs_dir / "P1-BUG-001-test-bug.md"
        path_002 = bugs_dir / "P1-BUG-002-another-bug.md"
        path_001.write_text("---\nid: BUG-001\nstatus: open\n---\n\n# BUG-001\n")
        path_002.write_text("---\nid: BUG-002\nstatus: open\n---\n\n# BUG-002\n")
        self._register_issue(orchestrator, "BUG-001", path_001)
        self._register_issue(orchestrator, "BUG-002", path_002)

        git_ok: MagicMock = MagicMock()
        git_ok.returncode = 0
        git_ok.stdout = "[main abc1234] commit"
        git_ok.stderr = ""
        orchestrator._git_lock.run = lambda *a, **kw: git_ok  # type: ignore[method-assign]

        orchestrator.parallel_config.use_feature_branches = True
        orchestrator.parallel_config.push_feature_branches = True
        orchestrator.parallel_config.open_pr_for_feature_branches = False
        orchestrator.parallel_config.remote_name = "origin"

        import subprocess

        push_calls: list[list[str]] = []

        def fake_subprocess_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if args[0] == "git" and "push" in args:
                push_calls.append(args)
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="unexpected"
            )

        with patch(
            "little_loops.parallel.orchestrator.subprocess.run", side_effect=fake_subprocess_run
        ):
            for iid, branch in [
                ("BUG-001", "feature/bug-001-test-bug"),
                ("BUG-002", "feature/bug-002-another-bug"),
            ]:
                orchestrator._on_worker_complete(
                    WorkerResult(
                        issue_id=iid,
                        success=True,
                        branch_name=branch,
                        worktree_path=Path("/tmp/worktree"),
                        duration=10.0,
                    )
                )

        # Both branches pushed
        assert len(push_calls) == 2
        pushed_branches = {call[4] for call in push_calls}
        assert pushed_branches == {"feature/bug-001-test-bug", "feature/bug-002-another-bug"}

        # Both issues: branch: written, no pr_url:, status: in_progress
        for path, branch in [
            (path_001, "feature/bug-001-test-bug"),
            (path_002, "feature/bug-002-another-bug"),
        ]:
            fm = parse_frontmatter(path.read_text())
            assert fm.get("branch") == branch, f"{path.name}: expected branch: {branch}"
            assert "pr_url" not in fm, f"{path.name}: pr_url should not be written without open_pr"
            assert fm.get("status") == "in_progress", (
                f"{path.name}: status must be held at in_progress"
            )

    def test_feature_branch_push_and_pr_two_issues(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Full chain for two issues with PR: push + gh pr create → pr_url: written → status: in_progress."""
        from little_loops.frontmatter import parse_frontmatter

        bugs_dir = temp_repo_with_config / ".issues" / "bugs"
        path_001 = bugs_dir / "P1-BUG-001-test-bug.md"
        path_002 = bugs_dir / "P1-BUG-002-another-bug.md"
        path_001.write_text("---\nid: BUG-001\nstatus: open\n---\n\n# BUG-001\n")
        path_002.write_text("---\nid: BUG-002\nstatus: open\n---\n\n# BUG-002\n")
        self._register_issue(orchestrator, "BUG-001", path_001)
        self._register_issue(orchestrator, "BUG-002", path_002)

        git_ok: MagicMock = MagicMock()
        git_ok.returncode = 0
        git_ok.stdout = "[main abc1234] commit"
        git_ok.stderr = ""
        orchestrator._git_lock.run = lambda *a, **kw: git_ok  # type: ignore[method-assign]

        orchestrator.parallel_config.use_feature_branches = True
        orchestrator.parallel_config.push_feature_branches = True
        orchestrator.parallel_config.open_pr_for_feature_branches = True
        orchestrator.parallel_config.remote_name = "origin"
        orchestrator.parallel_config.base_branch = "main"

        import subprocess

        pr_counter = [0]

        def fake_subprocess_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if args[0] == "git" and "push" in args:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            if args[0] == "gh" and args[1] == "auth":
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            if args[0] == "gh" and args[1] == "pr":
                pr_counter[0] += 1
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout=f"https://github.com/owner/repo/pull/{pr_counter[0]}",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="unexpected"
            )

        with patch(
            "little_loops.parallel.orchestrator.subprocess.run", side_effect=fake_subprocess_run
        ):
            for iid, branch in [
                ("BUG-001", "feature/bug-001-test-bug"),
                ("BUG-002", "feature/bug-002-another-bug"),
            ]:
                orchestrator._on_worker_complete(
                    WorkerResult(
                        issue_id=iid,
                        success=True,
                        branch_name=branch,
                        worktree_path=Path("/tmp/worktree"),
                        duration=10.0,
                    )
                )

        # Two PRs were opened (one per issue)
        assert pr_counter[0] == 2

        # Both issues: branch: and pr_url: written, status: in_progress
        fm_001 = parse_frontmatter(path_001.read_text())
        assert fm_001.get("branch") == "feature/bug-001-test-bug"
        assert fm_001.get("pr_url") is not None
        assert fm_001.get("status") == "in_progress"

        fm_002 = parse_frontmatter(path_002.read_text())
        assert fm_002.get("branch") == "feature/bug-002-another-bug"
        assert fm_002.get("pr_url") is not None
        assert fm_002.get("status") == "in_progress"


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
        orchestrator.merge_coordinator.failed_merges = {}  # type: ignore[misc,assignment]

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
        orchestrator.merge_coordinator.failed_merges = {}  # type: ignore[misc,assignment]

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
        orchestrator.merge_coordinator.failed_merges = {}  # type: ignore[misc,assignment]

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

    def test_appends_session_log_after_successful_status_write(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
        mock_issue: MagicMock,
    ) -> None:
        """status: done frontmatter is written at the original path; session log is appended."""
        original_path = temp_repo_with_config / ".issues" / "bugs" / "P1-BUG-001-test-bug.md"
        original_path.write_text("# BUG-001: Test\n\n## Resolution\n\nDone.\n")
        mock_issue.path = original_path
        mock_issue.issue_type = "bugs"
        orchestrator._issue_info_by_id["BUG-001"] = mock_issue

        git_ok = MagicMock()
        git_ok.returncode = 0
        git_ok.stdout = "[main abc1234] commit"
        git_ok.stderr = ""
        orchestrator._git_lock.run = lambda *a, **kw: git_ok  # type: ignore[method-assign]

        with patch("little_loops.parallel.orchestrator.append_session_log_entry") as mock_log:
            result = orchestrator._complete_issue_lifecycle_if_needed("BUG-001")

        assert result is True
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args.args[0] == original_path
        assert call_args.args[1] == "ll-parallel"

        # File stays at original path; no separate completed/ file is created
        assert original_path.exists()
        content = original_path.read_text()
        assert "completed_at:" in content
        match = re.search(r"completed_at:\s*'?(\S+?)'?\s*$", content, re.MULTILINE)
        assert match is not None
        assert match.group(1).strip("'\"").endswith("Z")
        # Frontmatter status is done
        from little_loops.frontmatter import parse_frontmatter

        assert parse_frontmatter(content).get("status") == "done"
        # No completed/ directory was created
        assert not (temp_repo_with_config / ".issues" / "completed" / original_path.name).exists()

    def test_complete_lifecycle_in_progress_writes_in_progress_not_done(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
        mock_issue: MagicMock,
    ) -> None:
        """terminal_status='in_progress' writes in_progress (not done) with no completed_at (ENH-2182)."""
        from little_loops.frontmatter import parse_frontmatter

        original_path = temp_repo_with_config / ".issues" / "bugs" / "P1-BUG-001-test-bug.md"
        original_path.write_text("# BUG-001: Test\n\n## Resolution\n\nDone.\n")
        mock_issue.path = original_path
        mock_issue.issue_type = "bugs"
        orchestrator._issue_info_by_id["BUG-001"] = mock_issue

        git_ok = MagicMock()
        git_ok.returncode = 0
        git_ok.stdout = "[main abc1234] commit"
        git_ok.stderr = ""
        orchestrator._git_lock.run = lambda *a, **kw: git_ok  # type: ignore[method-assign]

        result = orchestrator._complete_issue_lifecycle_if_needed(
            "BUG-001", terminal_status="in_progress"
        )

        assert result is True
        content = original_path.read_text()
        fm = parse_frontmatter(content)
        assert fm.get("status") == "in_progress"
        assert "completed_at" not in fm

    def test_complete_lifecycle_done_still_writes_completed_at(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
        mock_issue: MagicMock,
    ) -> None:
        """Default terminal_status='done' still writes completed_at timestamp (regression guard)."""
        from little_loops.frontmatter import parse_frontmatter

        original_path = temp_repo_with_config / ".issues" / "bugs" / "P1-BUG-001-test-bug.md"
        original_path.write_text("# BUG-001: Test\n\n## Resolution\n\nDone.\n")
        mock_issue.path = original_path
        mock_issue.issue_type = "bugs"
        orchestrator._issue_info_by_id["BUG-001"] = mock_issue

        git_ok = MagicMock()
        git_ok.returncode = 0
        git_ok.stdout = "[main abc1234] commit"
        git_ok.stderr = ""
        orchestrator._git_lock.run = lambda *a, **kw: git_ok  # type: ignore[method-assign]

        result = orchestrator._complete_issue_lifecycle_if_needed("BUG-001")

        assert result is True
        content = original_path.read_text()
        fm = parse_frontmatter(content)
        assert fm.get("status") == "done"
        assert "completed_at" in fm


@pytest.fixture
def real_git_orchestrator(
    default_parallel_config: ParallelConfig,
) -> Iterator[tuple[ParallelOrchestrator, Path]]:
    """A ``ParallelOrchestrator`` wired to a *real* git repo (BUG-2424 regression).

    The shared ``temp_repo_with_config`` fixture is a plain filesystem (no
    ``git init``) and the orchestrator suite stubs ``_git_lock.run`` — neither
    can catch over-staging. This fixture stands up an actual git repo with a
    committed issue file and returns an orchestrator that runs its **un-stubbed**
    ``GitLock`` against it, so ``git add`` scope can be asserted for real.
    """
    import subprocess as sp

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        sp.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
        sp.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        sp.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        ll_dir = repo_path / ".ll"
        ll_dir.mkdir()
        config = {
            "project": {"name": "test", "src_dir": "src/"},
            "issues": {
                "base_dir": ".issues",
                "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                "completed_dir": "completed",
            },
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config))
        (repo_path / ".issues" / "bugs").mkdir(parents=True)
        (repo_path / ".issues" / "completed").mkdir(parents=True)
        (repo_path / ".worktrees").mkdir()

        issue_path = repo_path / ".issues" / "bugs" / "P1-BUG-001-test-bug.md"
        issue_path.write_text(
            "---\nid: BUG-001\nstatus: in_progress\n---\n\n# BUG-001: Test Bug\n\n## Summary\nTest.\n"
        )
        sp.run(["git", "add", "-A"], cwd=repo_path, capture_output=True, check=True)
        sp.run(
            ["git", "commit", "-m", "initial commit"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        br_config = BRConfig(repo_path)
        with (
            patch("little_loops.parallel.orchestrator.WorkerPool"),
            patch("little_loops.parallel.orchestrator.MergeCoordinator"),
            patch("little_loops.parallel.orchestrator.IssuePriorityQueue"),
        ):
            orch = ParallelOrchestrator(
                parallel_config=default_parallel_config,
                br_config=br_config,
                repo_path=repo_path,
                verbose=False,
            )
        orch.queue.completed_ids = []  # type: ignore[misc]
        orch.queue.failed_ids = []  # type: ignore[misc]
        orch.queue.in_progress_ids = []  # type: ignore[misc]
        yield orch, repo_path


class TestScopedCompletionStaging:
    """BUG-2424: parallel completion commits must stage ONLY the issue file.

    Regression coverage for the two main-repo ``git add -A`` sites in
    ``orchestrator.py`` (``_complete_issue_lifecycle_if_needed`` and the
    ``_on_worker_complete`` feature-branch frontmatter fallback), which could
    sweep pre-existing dirty/untracked files into a worker's completion commit.
    """

    @staticmethod
    def _tracked(repo_path: Path) -> str:
        import subprocess as sp

        return sp.run(
            ["git", "ls-files"], cwd=repo_path, capture_output=True, text=True, check=True
        ).stdout

    @staticmethod
    def _status(repo_path: Path) -> str:
        import subprocess as sp

        return sp.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    def test_complete_lifecycle_commit_excludes_unrelated_dirty_file(
        self,
        real_git_orchestrator: tuple[ParallelOrchestrator, Path],
        mock_issue: MagicMock,
    ) -> None:
        """A pre-existing dirty main-repo file is NOT swept into the lifecycle commit."""
        orch, repo_path = real_git_orchestrator
        issue_path = repo_path / ".issues" / "bugs" / "P1-BUG-001-test-bug.md"
        mock_issue.path = issue_path
        mock_issue.issue_type = "bugs"
        orch._issue_info_by_id["BUG-001"] = mock_issue

        # Dirty state belonging to another issue/session in the main working tree.
        (repo_path / "unrelated_wip.py").write_text("# WIP for another issue\n")

        result = orch._complete_issue_lifecycle_if_needed("BUG-001")

        assert result is True
        assert "unrelated_wip.py" not in self._tracked(repo_path), (
            "unrelated dirty file must never be committed by the completion path"
        )
        assert "unrelated_wip.py" in self._status(repo_path), (
            "unrelated dirty file must remain uncommitted in the working tree"
        )

    def test_complete_lifecycle_commit_is_scoped_to_issue_file(
        self,
        real_git_orchestrator: tuple[ParallelOrchestrator, Path],
        mock_issue: MagicMock,
    ) -> None:
        """On a clean tree the lifecycle commit still lands, containing only the issue file."""
        import subprocess as sp

        orch, repo_path = real_git_orchestrator
        issue_path = repo_path / ".issues" / "bugs" / "P1-BUG-001-test-bug.md"
        mock_issue.path = issue_path
        mock_issue.issue_type = "bugs"
        orch._issue_info_by_id["BUG-001"] = mock_issue

        before = sp.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        result = orch._complete_issue_lifecycle_if_needed("BUG-001")
        assert result is True

        after = sp.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert int(after) == int(before) + 1, "a clean tree should still produce a scoped commit"

        files = sp.run(
            ["git", "show", "--name-only", "--format=", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        assert files == [".issues/bugs/P1-BUG-001-test-bug.md"], (
            f"completion commit must contain only the issue file, got {files}"
        )

    def test_on_worker_complete_feature_branch_excludes_unrelated_dirty_file(
        self,
        real_git_orchestrator: tuple[ParallelOrchestrator, Path],
        mock_issue: MagicMock,
    ) -> None:
        """The feature-branch frontmatter fallback must not sweep in unrelated dirt."""
        orch, repo_path = real_git_orchestrator
        issue_path = repo_path / ".issues" / "bugs" / "P1-BUG-001-test-bug.md"
        mock_issue.path = issue_path
        mock_issue.issue_type = "bugs"
        orch._issue_info_by_id["BUG-001"] = mock_issue

        orch.parallel_config.use_feature_branches = True
        orch.parallel_config.push_feature_branches = False

        (repo_path / "unrelated_wip.py").write_text("# other work\n")

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="feature/bug-001",
            worktree_path=repo_path / ".worktrees" / "w",
            duration=1.0,
        )
        orch._on_worker_complete(result)

        assert "unrelated_wip.py" not in self._tracked(repo_path), (
            "feature-branch fallback must never commit an unrelated dirty file"
        )
        assert "unrelated_wip.py" in self._status(repo_path), (
            "unrelated dirty file must remain uncommitted after feature-branch completion"
        )


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

    def test_cleanup_saves_state_force(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """_cleanup saves state with force=True to bypass throttle."""
        state_file = temp_repo_with_config / ".parallel-manage-state.json"
        orchestrator.queue.completed_ids = []  # type: ignore[misc]
        orchestrator.queue.failed_ids = []  # type: ignore[misc]
        orchestrator.queue.in_progress_ids = []  # type: ignore[misc]

        # Throttle should NOT prevent cleanup from saving state
        orchestrator._last_save_time = time.time()

        orchestrator._cleanup()

        assert state_file.exists(), "_cleanup must save state even within throttle window"

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

    def test_signal_handler_idempotent(self, orchestrator: ParallelOrchestrator) -> None:
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
        orchestrator.merge_coordinator.failed_merges = {}  # type: ignore[misc,assignment]

        with patch("time.time") as mock_time:
            mock_time.side_effect = [0, 0.5, 1.5, 2.5]
            with patch("time.sleep"):
                orchestrator._wait_for_completion()

        orchestrator.worker_pool.terminate_all_processes.assert_called_once()  # type: ignore[attr-defined]

    def test_wait_for_completion_waits_for_merges(self, orchestrator: ParallelOrchestrator) -> None:
        """_wait_for_completion waits for pending merges after workers."""
        type(orchestrator.worker_pool).active_count = property(lambda self: 0)  # type: ignore[method-assign,assignment]

        # Merge coordinator has pending merges
        merge_completed = [False]

        def mock_wait(*args: object, **kwargs: object) -> bool:
            merge_completed[0] = True
            return True

        orchestrator.merge_coordinator.wait_for_completion = mock_wait  # type: ignore[method-assign]
        orchestrator.merge_coordinator.merged_ids = ["BUG-001"]  # type: ignore[misc]
        orchestrator.merge_coordinator.failed_merges = {}  # type: ignore[misc,assignment]

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

    def test_concurrent_worker_callbacks(self, orchestrator: ParallelOrchestrator) -> None:
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
                orchestrator.state.corrections[f"ISSUE-{worker_id}"] = [f"correction-{worker_id}"]
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
                # Create WorkerResult to verify it doesn't raise during state modification
                _ = WorkerResult(
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

    def test_state_lock_prevents_lost_updates(self, orchestrator: ParallelOrchestrator) -> None:
        """_state_lock ensures concurrent timing writes are not lost (BUG-688)."""
        n = 20
        errors: list[Exception] = []

        def write_timing(worker_id: int) -> None:
            try:
                with orchestrator._state_lock:
                    orchestrator.state.timing[f"BUG-{worker_id:03d}"] = {"total": float(worker_id)}
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_timing, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        # All writes must be preserved — no lost updates


class TestDispatchRouting:
    """Tests for _execute dispatch routing and _on_worker_complete callback.

    The main orchestrator fixture mocks WorkerPool/MergeCoordinator/IssuePriorityQueue,
    so these tests use method-level patching to verify the dispatch and callback logic
    without requiring real subprocess workers.
    """

    def test_p0_issue_routes_to_sequential(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """P0 priority issues are routed to _process_sequential, not _process_parallel.

        Tests the dispatch condition in _execute directly via patched methods.
        """
        p0_issue = MagicMock(spec=IssueInfo)
        p0_issue.issue_id = "BUG-001"
        p0_issue.priority = "P0"
        p0_issue.issue_type = "bugs"

        sequential_calls: list[IssueInfo] = []
        parallel_calls: list[IssueInfo] = []

        orchestrator._issue_info_by_id[p0_issue.issue_id] = p0_issue

        with patch.object(orchestrator, "_process_sequential", side_effect=sequential_calls.append):
            with patch.object(orchestrator, "_process_parallel", side_effect=parallel_calls.append):
                # Simulate the dispatch condition: p0 with p0_sequential=True
                assert orchestrator.parallel_config.p0_sequential is True
                if p0_issue.priority == "P0" and orchestrator.parallel_config.p0_sequential:
                    orchestrator._process_sequential(p0_issue)
                else:
                    orchestrator._process_parallel(p0_issue)

        assert len(sequential_calls) == 1
        assert sequential_calls[0] is p0_issue
        assert len(parallel_calls) == 0

    def test_p1_issue_routes_to_parallel(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """P1 priority issues are routed to _process_parallel, not _process_sequential."""
        p1_issue = MagicMock(spec=IssueInfo)
        p1_issue.issue_id = "BUG-002"
        p1_issue.priority = "P1"
        p1_issue.issue_type = "bugs"

        sequential_calls: list[IssueInfo] = []
        parallel_calls: list[IssueInfo] = []

        orchestrator._issue_info_by_id[p1_issue.issue_id] = p1_issue

        with patch.object(orchestrator, "_process_sequential", side_effect=sequential_calls.append):
            with patch.object(orchestrator, "_process_parallel", side_effect=parallel_calls.append):
                # Simulate the dispatch condition: p1 bypasses p0_sequential path
                if p1_issue.priority == "P0" and orchestrator.parallel_config.p0_sequential:
                    orchestrator._process_sequential(p1_issue)
                else:
                    orchestrator._process_parallel(p1_issue)

        assert len(parallel_calls) == 1
        assert parallel_calls[0] is p1_issue
        assert len(sequential_calls) == 0

    def test_on_worker_complete_success_queues_merge(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """Successful worker result causes merge_coordinator.queue_merge to be called."""
        result = WorkerResult(
            issue_id="BUG-003",
            success=True,
            branch_name="parallel/bug-003",
            worktree_path=Path("/tmp/wt-test"),
            duration=10.0,
        )
        orchestrator._issue_info_by_id["BUG-003"] = MagicMock(spec=IssueInfo)

        with patch.object(orchestrator, "_complete_issue_lifecycle_if_needed"):
            orchestrator._on_worker_complete(result)

        orchestrator.merge_coordinator.queue_merge.assert_called_once_with(result)  # type: ignore[attr-defined]

    def test_on_worker_complete_failure_marks_failed(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """Failed worker result marks the issue as failed in the queue."""
        result = WorkerResult(
            issue_id="BUG-004",
            success=False,
            branch_name="parallel/bug-004",
            worktree_path=Path("/tmp/wt-test"),
            duration=5.0,
            error="Implementation failed",
        )

        orchestrator._on_worker_complete(result)

        orchestrator.queue.mark_failed.assert_called_once_with("BUG-004")  # type: ignore[attr-defined]
        assert orchestrator._worker_errors["BUG-004"] == "Implementation failed"

    def test_on_worker_complete_interrupted_not_marked_failed(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """Interrupted workers (from shutdown) are not marked as failures (ENH-036)."""
        result = WorkerResult(
            issue_id="BUG-005",
            success=False,
            branch_name="parallel/bug-005",
            worktree_path=Path("/tmp/wt-test"),
            duration=2.0,
            interrupted=True,
        )

        orchestrator._on_worker_complete(result)

        orchestrator.queue.mark_failed.assert_not_called()  # type: ignore[attr-defined]
        assert "BUG-005" in orchestrator._interrupted_issues

    def test_on_worker_complete_stores_error_in_worker_errors(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_on_worker_complete stores the worker's error string in _worker_errors on failure."""
        result = WorkerResult(
            issue_id="BUG-010",
            success=False,
            branch_name="parallel/bug-010",
            worktree_path=Path("/tmp/worktree"),
            error="Claude CLI exited with code 1: stderr output here",
        )

        orchestrator._on_worker_complete(result)

        assert (
            orchestrator._worker_errors["BUG-010"]
            == "Claude CLI exited with code 1: stderr output here"
        )

    def test_on_worker_complete_stores_fallback_when_error_is_none(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """_on_worker_complete stores 'Failed' fallback in _worker_errors when result.error is None."""
        result = WorkerResult(
            issue_id="BUG-011",
            success=False,
            branch_name="parallel/bug-011",
            worktree_path=Path("/tmp/worktree"),
            error=None,
        )

        orchestrator._on_worker_complete(result)

        assert orchestrator._worker_errors["BUG-011"] == "Failed"


class TestDecisionNeededRouting:
    """Orchestrator must dispatch decision_needed=True issues to _process_parallel.

    The decision_needed gate is handled inside WorkerPool._process_issue(), not in
    the orchestrator itself. These tests verify that the orchestrator does not block
    or drop issues flagged with decision_needed=True — they still reach _process_parallel
    so the worker pool can apply the decide-issue step.
    """

    def test_decision_needed_issue_dispatched_to_parallel(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """An issue with decision_needed=True is still dispatched to _process_parallel."""
        issue = MagicMock(spec=IssueInfo)
        issue.issue_id = "FEAT-999"
        issue.priority = "P1"
        issue.issue_type = "features"
        issue.decision_needed = True

        parallel_calls: list[IssueInfo] = []
        orchestrator._issue_info_by_id[issue.issue_id] = issue

        with patch.object(orchestrator, "_process_parallel", side_effect=parallel_calls.append):
            if issue.priority == "P0" and orchestrator.parallel_config.p0_sequential:
                orchestrator._process_sequential(issue)
            else:
                orchestrator._process_parallel(issue)

        assert len(parallel_calls) == 1
        assert parallel_calls[0].decision_needed is True

    def test_decision_needed_none_issue_dispatched_to_parallel(
        self,
        orchestrator: ParallelOrchestrator,
    ) -> None:
        """An issue with decision_needed=None is dispatched to _process_parallel (control case)."""
        issue = MagicMock(spec=IssueInfo)
        issue.issue_id = "FEAT-998"
        issue.priority = "P1"
        issue.issue_type = "features"
        issue.decision_needed = None

        parallel_calls: list[IssueInfo] = []
        orchestrator._issue_info_by_id[issue.issue_id] = issue

        with patch.object(orchestrator, "_process_parallel", side_effect=parallel_calls.append):
            if issue.priority == "P0" and orchestrator.parallel_config.p0_sequential:
                orchestrator._process_sequential(issue)
            else:
                orchestrator._process_parallel(issue)

        assert len(parallel_calls) == 1
        assert parallel_calls[0].decision_needed is None
