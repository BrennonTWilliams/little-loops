"""Tests for worker_pool.py - parallel issue processing with git worktree isolation.

Tests cover:
- WorkerPool initialization and lifecycle (start/shutdown)
- Worktree management (setup/cleanup)
- Task submission and callback handling
- Process tracking and termination
- Issue processing workflow
- Helper methods (changed files, leak detection, work verification)
- Model detection via API
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import time
from collections.abc import Generator
from concurrent.futures import Future
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from little_loops.config import BRConfig
from little_loops.fsm.schema import DEFAULT_LLM_MODEL
from little_loops.issue_parser import IssueInfo
from little_loops.parallel.git_lock import GitLock
from little_loops.parallel.types import ParallelConfig, WorkerResult, WorkerStage
from little_loops.parallel.worker_pool import WorkerPool

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_logger() -> MagicMock:
    """Create a mock logger without spec for flexibility."""
    return MagicMock()


@pytest.fixture
def temp_repo_with_config() -> Generator[Path, None, None]:
    """Create a temporary directory with .ll config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        ll_dir = repo_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (ll_dir / "ll-config.json").write_text("{}")
        claude_dir = repo_path / ".claude"
        claude_dir.mkdir(exist_ok=True)
        (claude_dir / "settings.local.json").write_text('{"model": "claude-sonnet-4"}')

        # Create worktree base
        worktree_base = repo_path / ".worktrees"
        worktree_base.mkdir(exist_ok=True)

        yield repo_path


@pytest.fixture
def default_parallel_config(temp_repo_with_config: Path) -> ParallelConfig:
    """Create default parallel config for tests."""
    return ParallelConfig(
        max_workers=2,
        p0_sequential=True,
        worktree_base=Path(".worktrees"),
        state_file=Path(".parallel-state.json"),
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
def worker_pool(
    default_parallel_config: ParallelConfig,
    br_config: BRConfig,
    mock_logger: MagicMock,
    temp_repo_with_config: Path,
    mock_git_lock: GitLock,
) -> WorkerPool:
    """Create a WorkerPool instance for testing."""
    return WorkerPool(
        parallel_config=default_parallel_config,
        br_config=br_config,
        logger=mock_logger,
        repo_path=temp_repo_with_config,
        git_lock=mock_git_lock,
    )


@pytest.fixture
def mock_issue() -> MagicMock:
    """Create a mock IssueInfo."""
    issue = MagicMock()
    issue.issue_id = "BUG-001"
    issue.issue_type = "bugs"
    issue.path = Path(".issues/bugs/P0-BUG-001-test-issue.md")
    return issue


class TestWorkerResult:
    """Tests for WorkerResult dataclass (ENH-036)."""

    def test_interrupted_can_be_set_true(self) -> None:
        """WorkerResult.interrupted can be set to True."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=False,
            interrupted=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
            error="Interrupted during shutdown",
        )

        assert result.interrupted is True
        assert result.success is False

    def test_interrupted_serialization(self) -> None:
        """WorkerResult.interrupted is serialized to/from dict."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=False,
            interrupted=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
        )

        data = result.to_dict()
        assert data["interrupted"] is True

        restored = WorkerResult.from_dict(data)
        assert restored.interrupted is True


class TestWorkerPoolInit:
    """Tests for WorkerPool initialization."""

    def test_init_creates_git_lock_if_not_provided(
        self,
        default_parallel_config: ParallelConfig,
        br_config: BRConfig,
        mock_logger: MagicMock,
        temp_repo_with_config: Path,
    ) -> None:
        """WorkerPool creates GitLock if not provided."""
        pool = WorkerPool(
            parallel_config=default_parallel_config,
            br_config=br_config,
            logger=mock_logger,
            repo_path=temp_repo_with_config,
        )

        assert pool._git_lock is not None
        assert isinstance(pool._git_lock, GitLock)

    def test_init_uses_provided_git_lock(
        self,
        default_parallel_config: ParallelConfig,
        br_config: BRConfig,
        mock_logger: MagicMock,
        temp_repo_with_config: Path,
        mock_git_lock: GitLock,
    ) -> None:
        """WorkerPool uses provided GitLock."""
        pool = WorkerPool(
            parallel_config=default_parallel_config,
            br_config=br_config,
            logger=mock_logger,
            repo_path=temp_repo_with_config,
            git_lock=mock_git_lock,
        )

        assert pool._git_lock is mock_git_lock


class TestWorkerPoolStartShutdown:
    """Tests for start() and shutdown() methods."""

    def test_start_creates_executor(
        self, worker_pool: WorkerPool, temp_repo_with_config: Path
    ) -> None:
        """start() creates ThreadPoolExecutor."""
        assert worker_pool._executor is None

        worker_pool.start()

        assert worker_pool._executor is not None
        worker_pool.shutdown()

    def test_start_creates_worktree_base_directory(
        self,
        default_parallel_config: ParallelConfig,
        br_config: BRConfig,
        mock_logger: MagicMock,
        temp_repo_with_config: Path,
    ) -> None:
        """start() creates worktree base directory if missing."""
        # Remove the worktree base
        worktree_base = temp_repo_with_config / ".worktrees"
        if worktree_base.exists():
            worktree_base.rmdir()

        pool = WorkerPool(
            parallel_config=default_parallel_config,
            br_config=br_config,
            logger=mock_logger,
            repo_path=temp_repo_with_config,
        )
        pool.start()

        assert worktree_base.exists()
        pool.shutdown()

    def test_start_is_idempotent(self, worker_pool: WorkerPool) -> None:
        """Calling start() twice is safe."""
        worker_pool.start()
        first_executor = worker_pool._executor

        worker_pool.start()
        second_executor = worker_pool._executor

        assert first_executor is second_executor
        worker_pool.shutdown()

    def test_start_logs_info(self, worker_pool: WorkerPool, mock_logger: MagicMock) -> None:
        """start() logs worker count."""
        worker_pool.start()

        mock_logger.info.assert_called()
        call_args = str(mock_logger.info.call_args)
        assert "2" in call_args or "workers" in call_args.lower()

        worker_pool.shutdown()

    def test_shutdown_terminates_executor(self, worker_pool: WorkerPool) -> None:
        """shutdown() terminates the executor."""
        worker_pool.start()
        assert worker_pool._executor is not None

        worker_pool.shutdown()

        assert worker_pool._executor is None

    def test_shutdown_does_nothing_if_not_started(self, worker_pool: WorkerPool) -> None:
        """shutdown() is safe when pool was never started."""
        worker_pool.shutdown()  # Should not raise

    def test_shutdown_without_wait_terminates_processes(self, worker_pool: WorkerPool) -> None:
        """shutdown(wait=False) calls terminate_all_processes()."""
        worker_pool.start()

        with patch.object(worker_pool, "terminate_all_processes") as mock_terminate:
            worker_pool.shutdown(wait=False)

        mock_terminate.assert_called_once()


class TestWorkerPoolTerminateProcesses:
    """Tests for terminate_all_processes()."""

    def test_terminate_all_processes_terminates_running(
        self, worker_pool: WorkerPool, mock_logger: MagicMock
    ) -> None:
        """terminate_all_processes() sends SIGTERM to running processes."""
        mock_process = Mock()
        mock_process.poll.return_value = None  # Still running
        mock_process.pid = 12345
        mock_process.wait.return_value = None

        worker_pool._active_processes["BUG-001"] = mock_process

        worker_pool.terminate_all_processes()

        mock_process.terminate.assert_called_once()
        assert len(worker_pool._active_processes) == 0

    def test_terminate_all_processes_kills_if_sigterm_fails(
        self, worker_pool: WorkerPool, mock_logger: MagicMock
    ) -> None:
        """terminate_all_processes() sends SIGKILL if SIGTERM times out."""
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        mock_process.wait.side_effect = [subprocess.TimeoutExpired("cmd", 5), None]

        worker_pool._active_processes["BUG-001"] = mock_process

        worker_pool.terminate_all_processes()

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

    def test_terminate_all_processes_skips_already_terminated(
        self, worker_pool: WorkerPool
    ) -> None:
        """terminate_all_processes() skips already terminated processes."""
        mock_process = Mock()
        mock_process.poll.return_value = 0  # Already terminated

        worker_pool._active_processes["BUG-001"] = mock_process

        worker_pool.terminate_all_processes()

        mock_process.terminate.assert_not_called()

    def test_terminate_all_processes_handles_exception(
        self, worker_pool: WorkerPool, mock_logger: MagicMock
    ) -> None:
        """terminate_all_processes() logs errors but continues."""
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        mock_process.terminate.side_effect = OSError("Permission denied")

        worker_pool._active_processes["BUG-001"] = mock_process

        worker_pool.terminate_all_processes()  # Should not raise

        mock_logger.error.assert_called()

    def test_terminate_tracks_issues_during_shutdown(
        self, worker_pool: WorkerPool, mock_logger: MagicMock
    ) -> None:
        """terminate_all_processes() tracks terminated issues when shutdown requested."""
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        mock_process.wait.return_value = None

        worker_pool._active_processes["BUG-001"] = mock_process
        worker_pool.set_shutdown_requested(True)

        worker_pool.terminate_all_processes()

        assert "BUG-001" in worker_pool._terminated_during_shutdown

    def test_terminate_does_not_track_without_shutdown_flag(
        self, worker_pool: WorkerPool, mock_logger: MagicMock
    ) -> None:
        """terminate_all_processes() doesn't track issues when not in shutdown."""
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        mock_process.wait.return_value = None

        worker_pool._active_processes["BUG-001"] = mock_process
        # Not setting shutdown_requested

        worker_pool.terminate_all_processes()

        assert "BUG-001" not in worker_pool._terminated_during_shutdown


class TestWorkerPoolShutdownFlag:
    """Tests for shutdown flag management (ENH-036)."""

    def test_set_shutdown_requested_sets_flag(self, worker_pool: WorkerPool) -> None:
        """set_shutdown_requested() sets the shutdown flag."""
        assert worker_pool._shutdown_requested is False

        worker_pool.set_shutdown_requested(True)

        assert worker_pool._shutdown_requested is True

    def test_set_shutdown_requested_can_be_reset(self, worker_pool: WorkerPool) -> None:
        """set_shutdown_requested() can reset the flag."""
        worker_pool.set_shutdown_requested(True)
        worker_pool.set_shutdown_requested(False)

        assert worker_pool._shutdown_requested is False


class TestWorkerPoolTaskSubmission:
    """Tests for submit() and callback handling."""

    def test_submit_raises_if_not_started(
        self, worker_pool: WorkerPool, mock_issue: MagicMock
    ) -> None:
        """submit() raises RuntimeError if pool not started."""
        with pytest.raises(RuntimeError, match="not started"):
            worker_pool.submit(mock_issue)

    def test_submit_returns_future(self, worker_pool: WorkerPool, mock_issue: MagicMock) -> None:
        """submit() returns a Future."""
        worker_pool.start()

        # Mock _process_issue to avoid actual processing
        with patch.object(worker_pool, "_process_issue") as mock_process:
            mock_process.return_value = WorkerResult(
                issue_id="BUG-001",
                success=True,
                branch_name="parallel/bug-001",
                worktree_path=Path("/tmp/worktree"),
            )

            future = worker_pool.submit(mock_issue)

            assert isinstance(future, Future)

        worker_pool.shutdown()

    def test_submit_tracks_active_workers(
        self, worker_pool: WorkerPool, mock_issue: MagicMock
    ) -> None:
        """submit() tracks future in _active_workers."""
        worker_pool.start()

        with patch.object(worker_pool, "_process_issue") as mock_process:
            mock_process.return_value = WorkerResult(
                issue_id="BUG-001",
                success=True,
                branch_name="parallel/bug-001",
                worktree_path=Path("/tmp/worktree"),
            )

            future = worker_pool.submit(mock_issue)

            assert "BUG-001" in worker_pool._active_workers
            assert worker_pool._active_workers["BUG-001"] is future

        worker_pool.shutdown()

    def test_submit_with_callback_invokes_callback(
        self, worker_pool: WorkerPool, mock_issue: MagicMock
    ) -> None:
        """submit() with callback invokes callback on completion."""
        worker_pool.start()
        callback_results: list[WorkerResult] = []

        def callback(result: WorkerResult) -> None:
            callback_results.append(result)

        expected_result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
        )

        with patch.object(worker_pool, "_process_issue") as mock_process:
            mock_process.return_value = expected_result

            future = worker_pool.submit(mock_issue, on_complete=callback)
            future.result(timeout=5)  # Wait for completion

            # Give callback time to execute
            time.sleep(0.1)

        assert len(callback_results) == 1
        assert callback_results[0].issue_id == "BUG-001"

        worker_pool.shutdown()

    def test_handle_completion_tracks_pending_callbacks(self, worker_pool: WorkerPool) -> None:
        """_handle_completion() tracks callbacks in _pending_callbacks."""
        callback_started = threading.Event()
        callback_done = threading.Event()

        def slow_callback(result: WorkerResult) -> None:
            callback_started.set()
            callback_done.wait(timeout=5)

        future: Future[WorkerResult] = Future()
        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
        )
        future.set_result(result)

        # Start callback in thread
        thread = threading.Thread(
            target=worker_pool._handle_completion,
            args=(future, slow_callback, "BUG-001"),
        )
        thread.start()

        callback_started.wait(timeout=5)

        # While callback is running, issue should be in pending
        assert "BUG-001" in worker_pool._pending_callbacks

        callback_done.set()
        thread.join(timeout=5)

        # After callback completes, should be removed
        assert "BUG-001" not in worker_pool._pending_callbacks

    def test_handle_completion_invokes_callback_on_future_exception(
        self, worker_pool: WorkerPool
    ) -> None:
        """_handle_completion() invokes callback with failure WorkerResult when future raises."""
        callback_results: list[WorkerResult] = []

        def callback(result: WorkerResult) -> None:
            callback_results.append(result)

        future: Future[WorkerResult] = Future()
        future.set_exception(RuntimeError("Worker exploded"))

        worker_pool._handle_completion(future, callback, "BUG-001")

        assert len(callback_results) == 1
        assert callback_results[0].success is False
        assert callback_results[0].issue_id == "BUG-001"
        assert "Worker future failed" in (callback_results[0].error or "")
        assert "BUG-001" not in worker_pool._pending_callbacks

    def test_handle_completion_invokes_callback_on_cancelled_future(
        self, worker_pool: WorkerPool
    ) -> None:
        """_handle_completion() invokes callback with failure WorkerResult when future is cancelled."""
        callback_results: list[WorkerResult] = []

        def callback(result: WorkerResult) -> None:
            callback_results.append(result)

        future: Future[WorkerResult] = Future()
        future.cancel()
        # Force the future into cancelled state for testing
        future._state = "CANCELLED"  # type: ignore[attr-defined]

        worker_pool._handle_completion(future, callback, "BUG-002")

        assert len(callback_results) == 1
        assert callback_results[0].success is False
        assert callback_results[0].issue_id == "BUG-002"
        assert "BUG-002" not in worker_pool._pending_callbacks

    def test_handle_completion_logs_callback_exception(
        self, worker_pool: WorkerPool, mock_logger: MagicMock
    ) -> None:
        """_handle_completion() logs error when callback itself raises."""

        def bad_callback(result: WorkerResult) -> None:
            raise ValueError("Callback broke")

        future: Future[WorkerResult] = Future()
        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
        )
        future.set_result(result)

        worker_pool._handle_completion(future, bad_callback, "BUG-001")

        mock_logger.error.assert_called()
        error_msg = mock_logger.error.call_args[0][0]
        assert "callback failed" in error_msg.lower()
        assert "BUG-001" not in worker_pool._pending_callbacks

    def test_active_count_includes_futures_and_callbacks(self, worker_pool: WorkerPool) -> None:
        """active_count includes running futures and pending callbacks."""
        # Add a pending callback
        worker_pool._pending_callbacks.add("BUG-001")

        # Add a running future
        running_future: Future[WorkerResult] = Future()
        worker_pool._active_workers["BUG-002"] = running_future

        # Add a completed future (should not count)
        completed_future: Future[WorkerResult] = Future()
        completed_future.set_result(
            WorkerResult(
                issue_id="BUG-003",
                success=True,
                branch_name="test",
                worktree_path=Path("/tmp"),
            )
        )
        worker_pool._active_workers["BUG-003"] = completed_future

        assert worker_pool.active_count == 2  # 1 running future + 1 pending callback


class TestWorkerPoolWorktreeManagement:
    """Tests for _setup_worktree() and _cleanup_worktree()."""

    def test_setup_worktree_creates_worktree(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
        mock_logger: MagicMock,
    ) -> None:
        """_setup_worktree() calls git worktree add with correct args."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker-bug-001"
        branch_name = "parallel/bug-001"

        captured_commands: list[list[str]] = []

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            captured_commands.append(args)
            if args[:2] == ["config", "user.email"]:
                return subprocess.CompletedProcess(args, 0, "test@test.com\n", "")
            if args[:2] == ["config", "user.name"]:
                return subprocess.CompletedProcess(args, 0, "Test User\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            with patch("subprocess.run") as mock_subprocess:
                mock_subprocess.return_value = subprocess.CompletedProcess([], 0, "", "")
                with patch("shutil.copy2"):
                    worker_pool._setup_worktree(worktree_path, branch_name)

        # Check worktree add was called
        worktree_cmds = [c for c in captured_commands if "worktree" in c and "add" in c]
        assert len(worktree_cmds) >= 1
        assert branch_name in worktree_cmds[0]

    def test_setup_worktree_copies_config_files(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
        mock_logger: MagicMock,
    ) -> None:
        """_setup_worktree() copies .claude/ directory and configured files to worktree."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker-bug-001"
        branch_name = "parallel/bug-001"

        copied_files: list[tuple[Path, Path]] = []
        copytree_calls: list[tuple[Path, Path]] = []

        def mock_copy2(src: Path, dest: Path) -> None:
            copied_files.append((Path(src), Path(dest)))

        def mock_copytree(src: Path, dest: Path) -> Path:
            copytree_calls.append((Path(src), Path(dest)))
            return Path(dest)

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            with patch("subprocess.run") as mock_subprocess:
                mock_subprocess.return_value = subprocess.CompletedProcess([], 0, "", "")
                with patch("shutil.copy2", side_effect=mock_copy2):
                    with patch("shutil.copytree", side_effect=mock_copytree):
                        worker_pool._setup_worktree(worktree_path, branch_name)

        # Should have copied .claude/ directory via copytree (BUG-007 fix)
        copytree_srcs = [str(src) for src, _ in copytree_calls]
        assert any(".claude" in src for src in copytree_srcs)

        # .claude/* files should be skipped in copy2 since .claude/ is copied via copytree
        copied_names = [src.name for src, _ in copied_files]
        assert "settings.local.json" not in copied_names

    def test_setup_worktree_removes_existing(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
        mock_logger: MagicMock,
    ) -> None:
        """_setup_worktree() removes existing worktree before creating."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker-bug-001"
        worktree_path.mkdir(parents=True, exist_ok=True)
        branch_name = "parallel/bug-001"

        cleanup_called = []

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if "remove" in args:
                cleanup_called.append(True)
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            with patch("subprocess.run") as mock_subprocess:
                mock_subprocess.return_value = subprocess.CompletedProcess([], 0, "main\n", "")
                with patch("shutil.copy2"):
                    with patch("shutil.rmtree"):
                        worker_pool._setup_worktree(worktree_path, branch_name)

        assert len(cleanup_called) >= 1

    def test_setup_worktree_raises_on_failure(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_setup_worktree() raises RuntimeError on git failure."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker-bug-001"
        branch_name = "parallel/bug-001"

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if "add" in args:
                return subprocess.CompletedProcess(args, 1, "", "fatal: error")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            with pytest.raises(RuntimeError, match="Failed to create worktree"):
                worker_pool._setup_worktree(worktree_path, branch_name)

    def test_cleanup_worktree_removes_worktree(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_cleanup_worktree() calls git worktree remove."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker-bug-001"
        worktree_path.mkdir(parents=True, exist_ok=True)

        captured_commands: list[list[str]] = []

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            captured_commands.append(args)
            if args[:2] == ["rev-parse", "--abbrev-ref"]:
                return subprocess.CompletedProcess(args, 0, "main\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            with patch("subprocess.run") as mock_subprocess:
                mock_subprocess.return_value = subprocess.CompletedProcess([], 0, "main\n", "")
                with patch("shutil.rmtree"):
                    worker_pool._cleanup_worktree(worktree_path)

        remove_cmds = [c for c in captured_commands if "remove" in c]
        assert len(remove_cmds) >= 1

    def test_cleanup_worktree_deletes_parallel_branch(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_cleanup_worktree() deletes parallel/* branches."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker-bug-001"
        worktree_path.mkdir(parents=True, exist_ok=True)

        captured_commands: list[list[str]] = []

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            captured_commands.append(args)
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return subprocess.CompletedProcess(args, 0, "parallel/bug-001\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            with patch("subprocess.run") as mock_subprocess:
                # Return parallel branch name for WorkerPool's own rev-parse
                mock_subprocess.return_value = subprocess.CompletedProcess(
                    [], 0, "parallel/bug-001\n", ""
                )
                with patch("shutil.rmtree"):
                    worker_pool._cleanup_worktree(worktree_path)

        # Should have called branch -D
        branch_cmds = [c for c in captured_commands if "branch" in c and "-D" in c]
        assert len(branch_cmds) >= 1

    def test_cleanup_worktree_deletes_loop_branch(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_cleanup_worktree() deletes loop-style YYYYMMDD-HHMMSS-* branches (BUG-2324)."""
        worktree_path = temp_repo_with_config / ".worktrees" / "20260101-120000-my-loop"
        worktree_path.mkdir(parents=True, exist_ok=True)

        captured_commands: list[list[str]] = []

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            captured_commands.append(args)
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return subprocess.CompletedProcess(args, 0, "20260101-120000-my-loop\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            with patch("subprocess.run") as mock_subprocess:
                # Return loop branch name for WorkerPool's own rev-parse
                mock_subprocess.return_value = subprocess.CompletedProcess(
                    [], 0, "20260101-120000-my-loop\n", ""
                )
                with patch("shutil.rmtree"):
                    worker_pool._cleanup_worktree(worktree_path)

        branch_cmds = [c for c in captured_commands if "branch" in c and "-D" in c]
        assert len(branch_cmds) >= 1, "branch -D must be called for loop-style branches"

    def test_cleanup_worktree_never_deletes_main_branch(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_cleanup_worktree() never deletes main/master/HEAD (safe guard)."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker-bug-main"
        worktree_path.mkdir(parents=True, exist_ok=True)

        captured_commands: list[list[str]] = []

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            captured_commands.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            with patch("subprocess.run") as mock_subprocess:
                mock_subprocess.return_value = subprocess.CompletedProcess([], 0, "main\n", "")
                with patch("shutil.rmtree"):
                    worker_pool._cleanup_worktree(worktree_path)

        branch_cmds = [c for c in captured_commands if "branch" in c and "-D" in c]
        assert not branch_cmds, "branch -D must never be called for main/master/HEAD"

    def test_cleanup_worktree_handles_nonexistent(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_cleanup_worktree() handles non-existent worktree gracefully."""
        worktree_path = temp_repo_with_config / ".worktrees" / "nonexistent"

        # Should not raise
        worker_pool._cleanup_worktree(worktree_path)

    def test_cleanup_all_worktrees_removes_all(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
        mock_logger: MagicMock,
    ) -> None:
        """cleanup_all_worktrees() removes all worker-* and timestamp-prefixed directories."""
        worktree_base = temp_repo_with_config / ".worktrees"
        (worktree_base / "worker-bug-001").mkdir(exist_ok=True)
        (worktree_base / "worker-bug-002").mkdir(exist_ok=True)
        (worktree_base / "20260101-000000-my-loop").mkdir(exist_ok=True)
        (worktree_base / "other-dir").mkdir(exist_ok=True)  # Should not be removed

        cleanup_calls: list[Path] = []

        def mock_cleanup(path: Path) -> None:
            cleanup_calls.append(path)

        with patch.object(worker_pool, "_cleanup_worktree", side_effect=mock_cleanup):
            worker_pool.cleanup_all_worktrees()

        # Should have cleaned up 3 directories (2 worker + 1 loop)
        assert len(cleanup_calls) == 3
        cleaned_names = [p.name for p in cleanup_calls]
        assert "worker-bug-001" in cleaned_names
        assert "worker-bug-002" in cleaned_names
        assert "20260101-000000-my-loop" in cleaned_names
        assert "other-dir" not in cleaned_names

    def test_setup_worktree_skips_directory_entries(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
        mock_logger: MagicMock,
    ) -> None:
        """_setup_worktree() skips directory entries in worktree_copy_files (BUG-438)."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker-bug-438"
        branch_name = "parallel/bug-438"

        # Create a directory entry in the repo (simulating node_modules)
        dir_entry = temp_repo_with_config / "node_modules"
        dir_entry.mkdir(exist_ok=True)
        (dir_entry / "package.json").write_text("{}")

        # Create a file entry that should still be copied
        file_entry = temp_repo_with_config / ".env"
        file_entry.write_text("SECRET=value")

        # Configure worktree_copy_files with both a directory and a file
        worker_pool.parallel_config.worktree_copy_files = ["node_modules", ".env"]

        copied_files: list[tuple[Path, Path]] = []

        def mock_copy2(src: Path, dest: Path) -> None:
            copied_files.append((Path(src), Path(dest)))

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            with patch("subprocess.run") as mock_subprocess:
                mock_subprocess.return_value = subprocess.CompletedProcess([], 0, "", "")
                with patch("shutil.copy2", side_effect=mock_copy2):
                    with patch("shutil.copytree"):
                        worker_pool._setup_worktree(worktree_path, branch_name)

        # Directory should be skipped, file should be copied
        copied_names = [src.name for src, _ in copied_files]
        assert "node_modules" not in copied_names
        assert ".env" in copied_names

        # Warning should be logged for directory entry
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("node_modules" in w and "directory" in w.lower() for w in warning_calls)

    def test_setup_worktree_passes_base_branch_in_feature_mode(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_setup_worktree() appends base_branch as commit-ish in worktree add args."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker-feat-001"
        branch_name = "feature/feat-001-some-feature"

        captured_commands: list[list[str]] = []

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            captured_commands.append(args)
            return subprocess.CompletedProcess(args, 0, "abc1234\n", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            with patch("subprocess.run") as mock_subprocess:
                mock_subprocess.return_value = subprocess.CompletedProcess([], 0, "", "")
                with patch("shutil.copy2"):
                    with patch("shutil.copytree"):
                        worker_pool._setup_worktree(worktree_path, branch_name, base_branch="main")

        worktree_cmds = [c for c in captured_commands if "worktree" in c and "add" in c]
        assert len(worktree_cmds) >= 1
        assert "main" in worktree_cmds[0]

    def test_setup_worktree_no_base_branch_for_parallel_path(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_setup_worktree() without base_branch does not append a commit-ish (parallel/* path)."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker-bug-001"
        branch_name = "parallel/bug-001-20260616-120000"

        captured_commands: list[list[str]] = []

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            captured_commands.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            with patch("subprocess.run") as mock_subprocess:
                mock_subprocess.return_value = subprocess.CompletedProcess([], 0, "", "")
                with patch("shutil.copy2"):
                    with patch("shutil.copytree"):
                        worker_pool._setup_worktree(worktree_path, branch_name, base_branch=None)

        worktree_cmds = [c for c in captured_commands if "worktree" in c and "add" in c]
        assert len(worktree_cmds) >= 1
        # Four-arg form: worktree add -b <branch> <path> — no extra commit-ish
        assert worktree_cmds[0] == ["worktree", "add", "-b", branch_name, str(worktree_path)]

    def test_setup_worktree_raises_on_unresolvable_base_branch(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_setup_worktree() raises RuntimeError when base_branch does not resolve."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker-feat-002"
        branch_name = "feature/feat-002-new"

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["rev-parse", "--verify"]:
                return subprocess.CompletedProcess(args, 1, "", "fatal: bad revision 'nonexistent'")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            with pytest.raises(RuntimeError, match="does not resolve"):
                worker_pool._setup_worktree(worktree_path, branch_name, base_branch="nonexistent")


class TestActiveWorktreeProtection:
    """Tests for BUG-142: Prevent cleanup of worktrees in active use."""

    def test_cleanup_worktree_skips_active_worktree(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_cleanup_worktree() should skip worktrees in _active_worktrees set."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker-test-001"
        worktree_path.mkdir(parents=True, exist_ok=True)

        # Register as active
        with worker_pool._process_lock:
            worker_pool._active_worktrees.add(worktree_path)

        # Attempt cleanup - should skip
        worker_pool._cleanup_worktree(worktree_path)

        # Worktree should still exist
        assert worktree_path.exists()

        # Cleanup
        with worker_pool._process_lock:
            worker_pool._active_worktrees.discard(worktree_path)

    def test_cleanup_worktree_logs_warning_for_active(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
        mock_logger: MagicMock,
    ) -> None:
        """_cleanup_worktree() should log warning when skipping active worktree."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker-test-002"
        worktree_path.mkdir(parents=True, exist_ok=True)

        with worker_pool._process_lock:
            worker_pool._active_worktrees.add(worktree_path)

        worker_pool._cleanup_worktree(worktree_path)

        # Check that warning was logged
        mock_logger.warning.assert_called()
        call_args = str(mock_logger.warning.call_args)
        assert "active use" in call_args.lower()

        with worker_pool._process_lock:
            worker_pool._active_worktrees.discard(worktree_path)

    def test_cleanup_all_worktrees_skips_active(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
        mock_logger: MagicMock,
    ) -> None:
        """cleanup_all_worktrees() should skip worktrees in _active_worktrees."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(parents=True, exist_ok=True)

        active_path = worktree_base / "worker-active-001"
        inactive_path = worktree_base / "worker-inactive-002"
        active_path.mkdir(exist_ok=True)
        inactive_path.mkdir(exist_ok=True)

        # Mark one as active
        with worker_pool._process_lock:
            worker_pool._active_worktrees.add(active_path)

        cleanup_calls: list[Path] = []

        def tracking_cleanup(path: Path) -> None:
            cleanup_calls.append(path)
            # Check active worktree logic
            with worker_pool._process_lock:
                if path in worker_pool._active_worktrees:
                    mock_logger.warning(
                        f"Skipping cleanup of {path.name}: worktree is in active use"
                    )
                    return
            # For inactive, simulate cleanup
            if path.exists():
                path.rmdir()

        with patch.object(worker_pool, "_cleanup_worktree", side_effect=tracking_cleanup):
            worker_pool.cleanup_all_worktrees()

        # Both should have been passed to _cleanup_worktree
        assert len(cleanup_calls) == 2

        # Active should still exist (skipped by our tracking cleanup)
        assert active_path.exists()

        # Inactive should be gone
        assert not inactive_path.exists()

        with worker_pool._process_lock:
            worker_pool._active_worktrees.discard(active_path)

    def test_process_issue_registers_and_unregisters_worktree(
        self,
        worker_pool: WorkerPool,
        mock_issue: MagicMock,
    ) -> None:
        """_process_issue() should register worktree after creation and unregister on completion."""
        # Track worktree registration during processing
        worktree_was_registered = [False]
        captured_worktree_path: list[Path] = []

        def mock_run_claude_with_check(
            cmd: str, path: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            # During processing, the worktree should be registered
            with worker_pool._process_lock:
                for wt in worker_pool._active_worktrees:
                    if "worker-" in str(wt):
                        worktree_was_registered[0] = True
                        captured_worktree_path.append(wt)
            return subprocess.CompletedProcess([], 0, "## VERDICT: **READY**", "")

        with patch.object(worker_pool, "_setup_worktree"):
            with patch.object(worker_pool, "_get_main_repo_baseline", return_value=set()):
                with patch.object(
                    worker_pool, "_run_claude_command", side_effect=mock_run_claude_with_check
                ):
                    with patch.object(
                        worker_pool, "_get_changed_files", return_value=["src/fix.py"]
                    ):
                        with patch.object(worker_pool, "_detect_main_repo_leaks", return_value=[]):
                            worker_pool._process_issue(mock_issue)

        # Worktree should have been registered during processing
        assert worktree_was_registered[0] is True

        # After processing completes, worktree should be unregistered
        with worker_pool._process_lock:
            # Check that the captured worktree is no longer in active set
            for wt in captured_worktree_path:
                assert wt not in worker_pool._active_worktrees

    def test_process_issue_unregisters_worktree_on_exception(
        self,
        worker_pool: WorkerPool,
        mock_issue: MagicMock,
    ) -> None:
        """_process_issue() should unregister worktree even when exception occurs."""
        # Capture the worktree path that gets registered
        captured_worktree_path: list[Path] = []

        def setup_and_capture(path: Path, branch: str, base_branch: str | None = None) -> None:
            # Capture the worktree path being set up
            captured_worktree_path.append(path)

        with patch.object(worker_pool, "_setup_worktree", side_effect=setup_and_capture):
            with patch.object(worker_pool, "_get_main_repo_baseline", return_value=set()):
                with patch.object(
                    worker_pool, "_run_claude_command", side_effect=Exception("Test error")
                ):
                    result = worker_pool._process_issue(mock_issue)

        # After processing (even with exception), worktree should be unregistered
        with worker_pool._process_lock:
            for wt in captured_worktree_path:
                assert wt not in worker_pool._active_worktrees

        # And the result should indicate failure
        assert result.success is False
        assert "Test error" in (result.error or "")


class TestWorkerPoolHelpers:
    """Tests for helper methods."""

    def test_get_changed_files_parses_output(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_get_changed_files() parses git diff output correctly."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                [], 0, "src/main.py\nsrc/utils.py\n", ""
            )

            files = worker_pool._get_changed_files(worktree_path)

        assert files == ["src/main.py", "src/utils.py"]

    def test_get_changed_files_returns_empty_on_error(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_get_changed_files() returns empty list on git error."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 1, "", "error")

            files = worker_pool._get_changed_files(worktree_path)

        assert files == []

    def test_verify_work_was_done_accepts_code_changes(self, worker_pool: WorkerPool) -> None:
        """_verify_work_was_done() returns True for code changes."""
        changed_files = ["src/main.py", "tests/test_main.py"]

        success, error = worker_pool._verify_work_was_done(changed_files, "BUG-001")

        assert success is True
        assert error == ""

    def test_verify_work_was_done_rejects_no_changes(self, worker_pool: WorkerPool) -> None:
        """_verify_work_was_done() returns False for no changes."""
        changed_files: list[str] = []

        success, error = worker_pool._verify_work_was_done(changed_files, "BUG-001")

        assert success is False
        assert "No files" in error

    def test_verify_work_was_done_rejects_excluded_only(self, worker_pool: WorkerPool) -> None:
        """_verify_work_was_done() returns False for excluded-only changes."""
        changed_files = [".issues/bugs/BUG-001.md", "thoughts/notes.md"]

        success, error = worker_pool._verify_work_was_done(changed_files, "BUG-001")

        assert success is False
        assert "excluded" in error.lower()

    def test_verify_work_was_done_respects_config(self, worker_pool: WorkerPool) -> None:
        """_verify_work_was_done() skips check if require_code_changes=False."""
        worker_pool.parallel_config.require_code_changes = False
        changed_files = [".issues/bugs/BUG-001.md"]

        success, error = worker_pool._verify_work_was_done(changed_files, "BUG-001")

        assert success is True

    def test_get_main_repo_baseline(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_get_main_repo_baseline() captures git status."""

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["status", "--porcelain"]:
                # Git porcelain format: XY<space>filename
                # Note: The code uses stdout.strip().split("\n") which can
                # cause issues with leading space status codes on the first line.
                # Using "M " (staged) and "??" (untracked) which parse correctly.
                return subprocess.CompletedProcess(args, 0, "M  staged.py\n?? untracked.py\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            baseline = worker_pool._get_main_repo_baseline()

        assert "staged.py" in baseline
        assert "untracked.py" in baseline

    def test_detect_main_repo_leaks_finds_leaked_files(
        self,
        worker_pool: WorkerPool,
    ) -> None:
        """_detect_main_repo_leaks() identifies leaked files."""
        baseline_status = {"existing.py"}

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["status", "--porcelain"]:
                return subprocess.CompletedProcess(
                    args, 0, "M existing.py\n?? thoughts/bug-001-notes.md\n", ""
                )
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            leaks = worker_pool._detect_main_repo_leaks("BUG-001", baseline_status)

        assert "thoughts/bug-001-notes.md" in leaks

    def test_detect_main_repo_leaks_ignores_state_file(
        self,
        worker_pool: WorkerPool,
    ) -> None:
        """_detect_main_repo_leaks() ignores state file."""
        baseline_status: set[str] = set()

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["status", "--porcelain"]:
                return subprocess.CompletedProcess(args, 0, "?? .parallel-manage-state.json\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            leaks = worker_pool._detect_main_repo_leaks("BUG-001", baseline_status)

        assert len(leaks) == 0

    def test_detect_main_repo_leaks_finds_issue_files(
        self,
        worker_pool: WorkerPool,
    ) -> None:
        """_detect_main_repo_leaks() identifies issue files in both directory variants."""
        baseline_status: set[str] = set()

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["status", "--porcelain"]:
                # Test both .issues/ (with dot) and issues/ (without dot) variants
                # Use files containing THIS worker's issue ID
                return subprocess.CompletedProcess(
                    args,
                    0,
                    "?? .issues/bugs/P1-BUG-001-desc.md\n?? issues/enhancements/P2-BUG-001-other.md\n",
                    "",
                )
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            leaks = worker_pool._detect_main_repo_leaks("BUG-001", baseline_status)

        # Both should be detected - they contain this worker's issue ID
        assert ".issues/bugs/P1-BUG-001-desc.md" in leaks
        assert "issues/enhancements/P2-BUG-001-other.md" in leaks

    def test_detect_main_repo_leaks_finds_generic_issue_files(
        self,
        worker_pool: WorkerPool,
    ) -> None:
        """_detect_main_repo_leaks() identifies generic issue files without issue IDs."""
        baseline_status: set[str] = set()

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["status", "--porcelain"]:
                # Files without specific issue IDs should still be detected
                return subprocess.CompletedProcess(
                    args,
                    0,
                    "?? .issues/README.md\n?? issues/template.md\n",
                    "",
                )
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            leaks = worker_pool._detect_main_repo_leaks("BUG-001", baseline_status)

        # Generic files (no issue ID) should be detected via directory prefix
        assert ".issues/README.md" in leaks
        assert "issues/template.md" in leaks

    def test_detect_main_repo_leaks_ignores_other_workers_issue_files(
        self,
        worker_pool: WorkerPool,
    ) -> None:
        """_detect_main_repo_leaks() does not detect other workers' issue files."""
        baseline_status: set[str] = set()

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["status", "--porcelain"]:
                # This worker is BUG-001, but ENH-002 file also appears (from another worker)
                return subprocess.CompletedProcess(
                    args,
                    0,
                    "?? .issues/bugs/P1-BUG-001-this-workers-file.md\n"
                    "?? issues/enhancements/P2-ENH-002-other-workers-file.md\n",
                    "",
                )
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            leaks = worker_pool._detect_main_repo_leaks("BUG-001", baseline_status)

        # Should detect this worker's file
        assert ".issues/bugs/P1-BUG-001-this-workers-file.md" in leaks
        # Should NOT detect other worker's file (cross-worker isolation)
        assert "issues/enhancements/P2-ENH-002-other-workers-file.md" not in leaks

    def test_detect_main_repo_leaks_uses_configured_src_dir(
        self,
        default_parallel_config: ParallelConfig,
        mock_logger: MagicMock,
        mock_git_lock: GitLock,
        tmp_path: Path,
    ) -> None:
        """_detect_main_repo_leaks() detects files in configured src_dir and test_dir."""
        # Set up a repo with non-default src_dir/test_dir not in the hardcoded fallback list
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (ll_dir / "ll-config.json").write_text(
            json.dumps({"project": {"src_dir": "scripts/", "test_dir": "custom_tests"}})
        )
        (tmp_path / ".worktrees").mkdir(exist_ok=True)

        br_config = BRConfig(tmp_path)
        pool = WorkerPool(
            parallel_config=default_parallel_config,
            br_config=br_config,
            logger=mock_logger,
            repo_path=tmp_path,
            git_lock=mock_git_lock,
        )

        baseline_status: set[str] = set()

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["status", "--porcelain"]:
                return subprocess.CompletedProcess(
                    args, 0, "?? scripts/new_module.py\n?? custom_tests/test_new.py\n", ""
                )
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(pool._git_lock, "run", side_effect=mock_git_run):
            leaks = pool._detect_main_repo_leaks("BUG-001", baseline_status)

        assert "scripts/new_module.py" in leaks
        assert "custom_tests/test_new.py" in leaks

    def test_has_other_issue_id(self, worker_pool: WorkerPool) -> None:
        """_has_other_issue_id() correctly identifies files with other issue IDs."""
        # No issue ID in filename
        assert not worker_pool._has_other_issue_id("readme.md", "bug-001")

        # Same issue ID
        assert not worker_pool._has_other_issue_id("p1-bug-001-fix.md", "bug-001")

        # Different issue ID
        assert worker_pool._has_other_issue_id("p2-enh-002-other.md", "bug-001")

        # Different issue type with same number
        assert worker_pool._has_other_issue_id("p1-feat-001-feature.md", "bug-001")

        # Multiple issue IDs, one matches
        assert not worker_pool._has_other_issue_id("bug-001-related-to-enh-002.md", "bug-001")

        # Multiple issue IDs, none match
        assert worker_pool._has_other_issue_id("enh-002-related-to-feat-003.md", "bug-001")

    def test_cleanup_leaked_files_tracked(
        self,
        worker_pool: WorkerPool,
    ) -> None:
        """_cleanup_leaked_files() discards tracked file changes."""
        leaked_files = ["src/leaked.py"]

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["status", "--porcelain"]:
                return subprocess.CompletedProcess(args, 0, "M  src/leaked.py\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            count = worker_pool._cleanup_leaked_files(leaked_files)

        assert count == 1

    def test_cleanup_leaked_files_untracked(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_cleanup_leaked_files() deletes untracked files."""
        # Create an untracked file
        leaked_file = temp_repo_with_config / "untracked.py"
        leaked_file.write_text("leaked content")

        leaked_files = ["untracked.py"]

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["status", "--porcelain"]:
                return subprocess.CompletedProcess(args, 0, "?? untracked.py\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            count = worker_pool._cleanup_leaked_files(leaked_files)

        assert count == 1
        assert not leaked_file.exists()

    def test_cleanup_leaked_files_empty_list(self, worker_pool: WorkerPool) -> None:
        """_cleanup_leaked_files() handles empty list."""
        count = worker_pool._cleanup_leaked_files([])
        assert count == 0

    def test_cleanup_leaked_files_gitignored(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_cleanup_leaked_files() deletes gitignored files not reported by git status."""
        # Create a file that simulates a gitignored leaked file
        gitignored_file = temp_repo_with_config / "issues" / "leaked.md"
        gitignored_file.parent.mkdir(parents=True, exist_ok=True)
        gitignored_file.write_text("leaked content")

        leaked_files = ["issues/leaked.md"]

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["status", "--porcelain"]:
                # Git returns empty for gitignored paths
                return subprocess.CompletedProcess(args, 0, "", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            count = worker_pool._cleanup_leaked_files(leaked_files)

        assert count == 1
        assert not gitignored_file.exists()

    def test_get_main_head_sha_returns_sha(
        self,
        worker_pool: WorkerPool,
    ) -> None:
        """_get_main_head_sha() returns the HEAD SHA on success."""
        sha = "abc123def456abc123def456abc123def456abc123"

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(args, 0, sha + "\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            result = worker_pool._get_main_head_sha()

        assert result == sha

    def test_get_main_head_sha_returns_empty_on_failure(
        self,
        worker_pool: WorkerPool,
    ) -> None:
        """_get_main_head_sha() returns empty string when git fails."""

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(args, 128, "", "not a git repository")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            result = worker_pool._get_main_head_sha()

        assert result == ""

    def test_detect_committed_leaks_no_leaks_same_sha(
        self,
        worker_pool: WorkerPool,
    ) -> None:
        """_detect_committed_leaks() returns empty list when HEAD is unchanged."""
        sha = "abc123def456"

        with patch.object(worker_pool, "_get_main_head_sha", return_value=sha):
            result = worker_pool._detect_committed_leaks(sha)

        assert result == []

    def test_detect_committed_leaks_empty_baseline(
        self,
        worker_pool: WorkerPool,
    ) -> None:
        """_detect_committed_leaks() returns empty list when baseline is empty."""
        result = worker_pool._detect_committed_leaks("")
        assert result == []

    def test_detect_committed_leaks_finds_new_commits(
        self,
        worker_pool: WorkerPool,
    ) -> None:
        """_detect_committed_leaks() returns list of new commit SHAs."""
        baseline_sha = "aaa111"
        current_sha = "ccc333"
        leaked_sha1 = "bbb222"
        leaked_sha2 = "ccc333"

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(args, 0, current_sha + "\n", "")
            if args[:2] == ["log", "--format=%H"]:
                # Return two leaked commits (newest first)
                return subprocess.CompletedProcess(args, 0, f"{leaked_sha2}\n{leaked_sha1}\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            result = worker_pool._detect_committed_leaks(baseline_sha)

        assert result == [leaked_sha2, leaked_sha1]

    def test_recover_committed_leaks_cherry_pick_success(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_recover_committed_leaks() cherry-picks commits and resets main."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker"
        leaked_commits = ["sha_newest", "sha_oldest"]  # newest first
        baseline_sha = "baseline_sha"

        cherry_pick_calls: list[list[str]] = []

        def mock_subprocess_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["git", "cherry-pick"]:
                cherry_pick_calls.append(args)
                return subprocess.CompletedProcess(args, 0, "", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(args, 0, "sha_newest\n", "")
            if args[:2] == ["reset", "--hard"]:
                return subprocess.CompletedProcess(args, 0, "", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
                result = worker_pool._recover_committed_leaks(
                    leaked_commits, worktree_path, baseline_sha, "ENH-535"
                )

        assert result is True
        # Cherry-picks should be in chronological order (oldest first)
        assert len(cherry_pick_calls) == 2
        assert cherry_pick_calls[0] == ["git", "cherry-pick", "sha_oldest"]
        assert cherry_pick_calls[1] == ["git", "cherry-pick", "sha_newest"]

    def test_recover_committed_leaks_cherry_pick_fails(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_recover_committed_leaks() returns False when cherry-pick fails."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker"
        leaked_commits = ["sha_newest"]
        baseline_sha = "baseline_sha"

        def mock_subprocess_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["git", "cherry-pick"] and "--abort" not in args:
                return subprocess.CompletedProcess(args, 1, "", "CONFLICT: merge conflict")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            result = worker_pool._recover_committed_leaks(
                leaked_commits, worktree_path, baseline_sha, "ENH-535"
            )

        assert result is False

    def test_recover_committed_leaks_rebases_when_main_advanced(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_recover_committed_leaks() attempts surgical rebase when main has advanced."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker"
        leaked_commits = ["sha_leaked"]
        baseline_sha = "baseline_sha"

        rebase_calls: list[list[str]] = []

        def mock_subprocess_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["git", "cherry-pick"]:
                return subprocess.CompletedProcess(args, 0, "", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["rev-parse", "HEAD"]:
                # Main has advanced further than the leaked commit
                return subprocess.CompletedProcess(args, 0, "sha_even_newer\n", "")
            if args[0] == "rebase":
                rebase_calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
                result = worker_pool._recover_committed_leaks(
                    leaked_commits, worktree_path, baseline_sha, "ENH-535"
                )

        assert result is True
        assert len(rebase_calls) == 1
        assert rebase_calls[0] == ["rebase", "--onto", baseline_sha, "sha_leaked"]


class TestUpdateBranchBase:
    """Tests for _update_branch_base() remote name configuration."""

    def test_update_branch_base_uses_configured_remote(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_update_branch_base() uses remote_name from config instead of hardcoded 'origin'."""
        worker_pool.parallel_config.remote_name = "upstream"
        worker_pool.parallel_config.base_branch = "main"
        worktree_path = temp_repo_with_config / ".worktrees" / "worker"
        worktree_path.mkdir(parents=True, exist_ok=True)

        captured_cmds: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured_cmds.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=mock_run):
            success, error = worker_pool._update_branch_base(worktree_path, "BUG-001")

        assert success is True
        assert error == ""
        fetch_cmds = [c for c in captured_cmds if "fetch" in c]
        assert len(fetch_cmds) == 1
        assert fetch_cmds[0] == ["git", "fetch", "upstream", "main"]
        rebase_cmds = [c for c in captured_cmds if "rebase" in c and "--abort" not in c]
        assert len(rebase_cmds) == 1
        assert rebase_cmds[0] == ["git", "rebase", "upstream/main"]

    def test_update_branch_base_fetch_failure_falls_back_to_local(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_update_branch_base() falls back to local base branch when fetch fails."""
        worker_pool.parallel_config.remote_name = "origin"
        worker_pool.parallel_config.base_branch = "main"
        worktree_path = temp_repo_with_config / ".worktrees" / "worker"
        worktree_path.mkdir(parents=True, exist_ok=True)

        captured_cmds: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured_cmds.append(cmd)
            if "fetch" in cmd:
                return subprocess.CompletedProcess(
                    cmd, 1, "", "fatal: 'origin' does not appear to be a git repository"
                )
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=mock_run):
            success, error = worker_pool._update_branch_base(worktree_path, "BUG-001")

        assert success is True
        assert error == ""
        rebase_cmds = [c for c in captured_cmds if "rebase" in c and "--abort" not in c]
        assert len(rebase_cmds) == 1
        # Should fall back to local "main" instead of "origin/main"
        assert rebase_cmds[0] == ["git", "rebase", "main"]

    def test_update_branch_base_default_remote_is_origin(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_update_branch_base() uses 'origin' when remote_name is default."""
        worker_pool.parallel_config.base_branch = "main"
        worktree_path = temp_repo_with_config / ".worktrees" / "worker"
        worktree_path.mkdir(parents=True, exist_ok=True)

        captured_cmds: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured_cmds.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=mock_run):
            worker_pool._update_branch_base(worktree_path, "BUG-001")

        fetch_cmds = [c for c in captured_cmds if "fetch" in c]
        assert fetch_cmds[0] == ["git", "fetch", "origin", "main"]


class TestWorkerPoolModelDetection:
    """Tests for _detect_worktree_model_via_api()."""

    def test_detect_model_parses_json_response(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_detect_worktree_model_via_api() parses modelUsage from JSON."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker"

        json_response = json.dumps(
            {"result": "ok", "modelUsage": {DEFAULT_LLM_MODEL: {"input": 10}}}
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0, json_response, "")

            model = worker_pool._detect_worktree_model_via_api(worktree_path)

        assert model == DEFAULT_LLM_MODEL

    def test_detect_model_returns_none_on_error(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_detect_worktree_model_via_api() returns None on command error."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 1, "", "error")

            model = worker_pool._detect_worktree_model_via_api(worktree_path)

        assert model is None

    def test_detect_model_returns_none_on_invalid_json(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_detect_worktree_model_via_api() returns None on invalid JSON."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0, "not valid json", "")

            model = worker_pool._detect_worktree_model_via_api(worktree_path)

        assert model is None

    def test_detect_model_returns_none_on_timeout(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_detect_worktree_model_via_api() returns None on timeout."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("claude", 30)

            model = worker_pool._detect_worktree_model_via_api(worktree_path)

        assert model is None

    def test_detect_model_returns_none_on_empty_model_usage(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_detect_worktree_model_via_api() returns None if modelUsage is empty."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker"

        json_response = json.dumps({"result": "ok", "modelUsage": {}})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0, json_response, "")

            model = worker_pool._detect_worktree_model_via_api(worktree_path)

        assert model is None


class TestWorkerPoolProcessIssue:
    """Integration tests for _process_issue() workflow."""

    def test_process_issue_returns_failure_on_ready_issue_failure(
        self,
        worker_pool: WorkerPool,
        mock_issue: MagicMock,
        temp_repo_with_config: Path,
    ) -> None:
        """_process_issue() returns failure when ready-issue fails."""
        with patch.object(worker_pool, "_setup_worktree"):
            with patch.object(worker_pool, "_get_main_repo_baseline", return_value=set()):
                with patch.object(worker_pool, "_run_claude_command") as mock_run:
                    mock_run.return_value = subprocess.CompletedProcess(
                        [], 1, "", "ready-issue failed"
                    )

                    result = worker_pool._process_issue(mock_issue)

        assert result.success is False
        assert "ready-issue failed" in (result.error or "")

    def test_process_issue_returns_close_verdict(
        self,
        worker_pool: WorkerPool,
        mock_issue: MagicMock,
        temp_repo_with_config: Path,
    ) -> None:
        """_process_issue() handles CLOSE verdict correctly."""
        # Format must match expected output_parsing section structure
        ready_output = """## VERDICT
CLOSE

## CLOSE_REASON
- Reason: already_fixed

## CLOSE_STATUS
Closed - Already Fixed"""

        with patch.object(worker_pool, "_setup_worktree"):
            with patch.object(worker_pool, "_get_main_repo_baseline", return_value=set()):
                with patch.object(worker_pool, "_run_claude_command") as mock_run:
                    mock_run.return_value = subprocess.CompletedProcess([], 0, ready_output, "")

                    result = worker_pool._process_issue(mock_issue)

        assert result.success is True
        assert result.should_close is True
        assert result.close_reason == "already_fixed"

    def test_process_issue_returns_not_ready_verdict(
        self,
        worker_pool: WorkerPool,
        mock_issue: MagicMock,
        temp_repo_with_config: Path,
    ) -> None:
        """_process_issue() handles NOT_READY verdict correctly."""
        ready_output = """## VERDICT: **NOT_READY**
## CONCERNS
- File does not exist"""

        with patch.object(worker_pool, "_setup_worktree"):
            with patch.object(worker_pool, "_get_main_repo_baseline", return_value=set()):
                with patch.object(worker_pool, "_run_claude_command") as mock_run:
                    mock_run.return_value = subprocess.CompletedProcess([], 0, ready_output, "")

                    result = worker_pool._process_issue(mock_issue)

        assert result.success is False
        assert "NOT_READY" in (result.error or "")

    def test_process_issue_success_flow(
        self,
        worker_pool: WorkerPool,
        mock_issue: MagicMock,
        temp_repo_with_config: Path,
    ) -> None:
        """_process_issue() completes successfully with code changes."""
        ready_output = "## VERDICT: **READY**"
        manage_output = "Issue resolved"

        call_count = [0]

        def mock_run_command(
            cmd: str, path: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            call_count[0] += 1
            if call_count[0] == 1:
                return subprocess.CompletedProcess([], 0, ready_output, "")
            return subprocess.CompletedProcess([], 0, manage_output, "")

        with patch.object(worker_pool, "_setup_worktree"):
            with patch.object(worker_pool, "_get_main_repo_baseline", return_value=set()):
                with patch.object(worker_pool, "_run_claude_command", side_effect=mock_run_command):
                    with patch.object(
                        worker_pool,
                        "_get_changed_files",
                        return_value=["src/fix.py"],
                    ):
                        with patch.object(
                            worker_pool,
                            "_detect_main_repo_leaks",
                            return_value=[],
                        ):
                            with patch.object(
                                worker_pool,
                                "_update_branch_base",
                                return_value=(True, ""),
                            ):
                                result = worker_pool._process_issue(mock_issue)

        assert result.success is True
        assert result.changed_files == ["src/fix.py"]

    def test_process_issue_handles_exception(
        self,
        worker_pool: WorkerPool,
        mock_issue: MagicMock,
    ) -> None:
        """_process_issue() returns failure on exception."""
        with patch.object(worker_pool, "_get_main_repo_baseline", return_value=set()):
            with patch.object(
                worker_pool, "_setup_worktree", side_effect=Exception("Setup failed")
            ):
                result = worker_pool._process_issue(mock_issue)

        assert result.success is False
        assert "Setup failed" in (result.error or "")

    def test_process_issue_cleans_leaked_files(
        self,
        worker_pool: WorkerPool,
        mock_issue: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        """_process_issue() cleans up leaked files."""
        ready_output = "## VERDICT: **READY**"
        manage_output = "Issue resolved"

        call_count = [0]

        def mock_run_command(
            cmd: str, path: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            call_count[0] += 1
            if call_count[0] == 1:
                return subprocess.CompletedProcess([], 0, ready_output, "")
            return subprocess.CompletedProcess([], 0, manage_output, "")

        cleanup_called = [False]

        def mock_cleanup(files: list[str]) -> int:
            cleanup_called[0] = True
            return len(files)

        with patch.object(worker_pool, "_setup_worktree"):
            with patch.object(worker_pool, "_get_main_repo_baseline", return_value=set()):
                with patch.object(worker_pool, "_run_claude_command", side_effect=mock_run_command):
                    with patch.object(
                        worker_pool,
                        "_get_changed_files",
                        return_value=["src/fix.py"],
                    ):
                        with patch.object(
                            worker_pool,
                            "_detect_main_repo_leaks",
                            return_value=["thoughts/notes.md"],
                        ):
                            with patch.object(
                                worker_pool,
                                "_cleanup_leaked_files",
                                side_effect=mock_cleanup,
                            ):
                                with patch.object(
                                    worker_pool,
                                    "_update_branch_base",
                                    return_value=(True, ""),
                                ):
                                    result = worker_pool._process_issue(mock_issue)

        assert cleanup_called[0] is True
        assert result.leaked_files == ["thoughts/notes.md"]

    def test_process_issue_captures_corrections(
        self,
        worker_pool: WorkerPool,
        mock_issue: MagicMock,
        temp_repo_with_config: Path,
    ) -> None:
        """_process_issue() captures corrections from CORRECTED verdict (ENH-010)."""
        ready_output = """## VERDICT
CORRECTED

## CORRECTIONS_MADE
- Updated line 42 -> 45 in src/module.py reference
- Added missing ## Expected Behavior section
"""
        manage_output = "Issue resolved"

        call_count = [0]

        def mock_run_command(
            cmd: str, path: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            call_count[0] += 1
            if call_count[0] == 1:
                return subprocess.CompletedProcess([], 0, ready_output, "")
            return subprocess.CompletedProcess([], 0, manage_output, "")

        with patch.object(worker_pool, "_setup_worktree"):
            with patch.object(worker_pool, "_get_main_repo_baseline", return_value=set()):
                with patch.object(worker_pool, "_run_claude_command", side_effect=mock_run_command):
                    with patch.object(
                        worker_pool,
                        "_get_changed_files",
                        return_value=["src/fix.py"],
                    ):
                        with patch.object(
                            worker_pool,
                            "_detect_main_repo_leaks",
                            return_value=[],
                        ):
                            with patch.object(
                                worker_pool,
                                "_update_branch_base",
                                return_value=(True, ""),
                            ):
                                result = worker_pool._process_issue(mock_issue)

        assert result.success is True
        assert result.was_corrected is True
        assert len(result.corrections) == 2
        assert "Updated line 42 -> 45 in src/module.py reference" in result.corrections
        assert "Added missing ## Expected Behavior section" in result.corrections

    def test_process_issue_recovers_committed_leaks(
        self,
        worker_pool: WorkerPool,
        mock_issue: MagicMock,
        temp_repo_with_config: Path,
    ) -> None:
        """_process_issue() recovers when Claude commits to main instead of worktree.

        Regression test for BUG-580: when committed_leaks are detected and
        the worktree has no changed files, recovery should be attempted.
        After recovery, changed_files should be re-fetched for verification.
        """
        ready_output = "## VERDICT: **READY**"
        manage_output = "Issue resolved"

        call_count = [0]

        def mock_run_command(
            cmd: str, path: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            call_count[0] += 1
            if call_count[0] == 1:
                return subprocess.CompletedProcess([], 0, ready_output, "")
            return subprocess.CompletedProcess([], 0, manage_output, "")

        # Simulate: worktree has no changes (committed to main instead)
        get_changed_files_calls = [0]

        def mock_get_changed_files(path: Path) -> list[str]:
            get_changed_files_calls[0] += 1
            if get_changed_files_calls[0] == 1:
                return []  # First call: worktree empty (committed to main)
            return ["scripts/fix.py"]  # Second call: after recovery

        recover_called = [False]

        def mock_recover(commits: list[str], worktree: Path, baseline: str, issue_id: str) -> bool:
            recover_called[0] = True
            return True  # Recovery succeeds

        with patch.object(worker_pool, "_setup_worktree"):
            with patch.object(worker_pool, "_get_main_repo_baseline", return_value=set()):
                with patch.object(worker_pool, "_get_main_head_sha", return_value="baseline"):
                    with patch.object(
                        worker_pool, "_run_claude_command", side_effect=mock_run_command
                    ):
                        with patch.object(
                            worker_pool, "_get_changed_files", side_effect=mock_get_changed_files
                        ):
                            with patch.object(
                                worker_pool, "_detect_main_repo_leaks", return_value=[]
                            ):
                                with patch.object(
                                    worker_pool,
                                    "_detect_committed_leaks",
                                    return_value=["abc1234"],
                                ):
                                    with patch.object(
                                        worker_pool,
                                        "_recover_committed_leaks",
                                        side_effect=mock_recover,
                                    ):
                                        with patch.object(
                                            worker_pool,
                                            "_update_branch_base",
                                            return_value=(True, ""),
                                        ):
                                            result = worker_pool._process_issue(mock_issue)

        assert recover_called[0] is True
        assert get_changed_files_calls[0] == 2  # Called twice: initial + after recovery
        assert result.success is True
        assert result.changed_files == ["scripts/fix.py"]

    def test_process_issue_uses_feature_branch_name_when_enabled(
        self,
        default_parallel_config: ParallelConfig,
        br_config: BRConfig,
        mock_logger: MagicMock,
        temp_repo_with_config: Path,
        mock_git_lock: GitLock,
    ) -> None:
        """_process_issue() uses feature/<id>-<slug> branch name when use_feature_branches=True."""
        feature_config = ParallelConfig(
            **{**default_parallel_config.to_dict(), "use_feature_branches": True}
        )
        pool = WorkerPool(
            parallel_config=feature_config,
            br_config=br_config,
            logger=mock_logger,
            repo_path=temp_repo_with_config,
            git_lock=mock_git_lock,
        )

        issue = MagicMock()
        issue.issue_id = "ENH-665"
        issue.issue_type = "enhancements"
        issue.path = Path(".issues/enhancements/P3-ENH-665-add-feature.md")
        issue.title = "Add Feature Branch Config"

        captured: list[str] = []

        def capture_setup(
            worktree_path: Path, branch_name: str, base_branch: str | None = None
        ) -> None:
            captured.append(branch_name)

        with patch.object(pool, "_setup_worktree", side_effect=capture_setup):
            with patch.object(pool, "_get_main_repo_baseline", return_value=set()):
                with patch.object(pool, "_get_main_head_sha", return_value="abc123"):
                    with patch.object(pool, "_run_claude_command") as mock_run:
                        mock_run.return_value = subprocess.CompletedProcess(
                            [], 1, "", "ready-issue failed"
                        )
                        pool._process_issue(issue)

        assert len(captured) == 1
        assert captured[0].startswith("feature/")
        assert "enh-665" in captured[0]
        assert "add-feature-branch-config" in captured[0]

    def test_process_issue_returns_failure_on_manage_issue_failure(
        self,
        worker_pool: WorkerPool,
        mock_issue: MagicMock,
        temp_repo_with_config: Path,
    ) -> None:
        """_process_issue() returns failure when manage-issue exits non-zero."""
        ready_output = "## VERDICT: **READY**"
        call_count = [0]

        def mock_run_command(
            cmd: str, path: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            call_count[0] += 1
            if call_count[0] == 1:
                return subprocess.CompletedProcess([], 0, ready_output, "")
            return subprocess.CompletedProcess([], 1, "", "manage error detail")

        with patch.object(worker_pool, "_setup_worktree"):
            with patch.object(worker_pool, "_get_main_repo_baseline", return_value=set()):
                with patch.object(worker_pool, "_run_claude_command", side_effect=mock_run_command):
                    with patch.object(worker_pool, "_get_changed_files", return_value=[]):
                        with patch.object(worker_pool, "_detect_main_repo_leaks", return_value=[]):
                            result = worker_pool._process_issue(mock_issue)

        assert result.success is False
        assert "manage-issue failed" in (result.error or "")
        assert "manage error detail" in (result.error or "")

    def test_process_issue_manage_failure_uses_stdout_when_stderr_empty(
        self,
        worker_pool: WorkerPool,
        mock_issue: MagicMock,
        temp_repo_with_config: Path,
    ) -> None:
        """_process_issue() includes stdout snippet in error when stderr is empty."""
        ready_output = "## VERDICT: **READY**"
        call_count = [0]

        def mock_run_command(
            cmd: str, path: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            call_count[0] += 1
            if call_count[0] == 1:
                return subprocess.CompletedProcess([], 0, ready_output, "")
            return subprocess.CompletedProcess([], 1, "Claude stdout content", "")

        with patch.object(worker_pool, "_setup_worktree"):
            with patch.object(worker_pool, "_get_main_repo_baseline", return_value=set()):
                with patch.object(worker_pool, "_run_claude_command", side_effect=mock_run_command):
                    with patch.object(worker_pool, "_get_changed_files", return_value=[]):
                        with patch.object(worker_pool, "_detect_main_repo_leaks", return_value=[]):
                            result = worker_pool._process_issue(mock_issue)

        assert result.success is False
        assert "Claude stdout content" in (result.error or "")

    def test_process_issue_ready_failure_uses_stdout_when_stderr_empty(
        self,
        worker_pool: WorkerPool,
        mock_issue: MagicMock,
        temp_repo_with_config: Path,
    ) -> None:
        """_process_issue() includes stdout snippet for ready-issue when stderr is empty."""
        with patch.object(worker_pool, "_setup_worktree"):
            with patch.object(worker_pool, "_get_main_repo_baseline", return_value=set()):
                with patch.object(worker_pool, "_run_claude_command") as mock_run:
                    mock_run.return_value = subprocess.CompletedProcess(
                        [], 1, "Claude JSON output here", ""
                    )
                    result = worker_pool._process_issue(mock_issue)

        assert result.success is False
        assert "Claude JSON output here" in (result.error or "")


class TestWorkerPoolRunClaudeCommand:
    """Tests for _run_claude_command()."""

    def test_run_claude_command_tracks_process(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_run_claude_command() tracks process in _active_processes."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker"

        started_processes: list[subprocess.Popen[str]] = []
        ended_processes: list[subprocess.Popen[str]] = []

        def mock_run_claude(
            command: str,
            timeout: int,
            working_dir: Path,
            stream_callback: Any,
            on_process_start: Any,
            on_process_end: Any,
            idle_timeout: int = 0,
            on_usage: Any = None,
            resume_session: bool = False,
        ) -> subprocess.CompletedProcess[str]:
            mock_proc = Mock(spec=subprocess.Popen)
            if on_process_start:
                on_process_start(mock_proc)
                started_processes.append(mock_proc)
            if on_process_end:
                on_process_end(mock_proc)
                ended_processes.append(mock_proc)
            return subprocess.CompletedProcess([], 0, "output", "")

        with patch(
            "little_loops.parallel.worker_pool._run_claude_base",
            side_effect=mock_run_claude,
        ):
            worker_pool._run_claude_command("/ll:test", worktree_path, issue_id="BUG-001")

        assert len(started_processes) == 1
        assert len(ended_processes) == 1


class TestWorkerPoolStageTracking:
    """Tests for worker stage tracking (ENH-262)."""

    def test_set_and_get_worker_stage(self, worker_pool: WorkerPool) -> None:
        """Test setting and getting worker stages."""
        # Initially no stage
        assert worker_pool.get_worker_stage("BUG-123") is None

        # Set a stage
        worker_pool.set_worker_stage("BUG-123", WorkerStage.IMPLEMENTING)
        assert worker_pool.get_worker_stage("BUG-123") == WorkerStage.IMPLEMENTING

        # Update stage
        worker_pool.set_worker_stage("BUG-123", WorkerStage.VERIFYING)
        assert worker_pool.get_worker_stage("BUG-123") == WorkerStage.VERIFYING

    def test_get_active_stages(self, worker_pool: WorkerPool) -> None:
        """Test getting active worker stages."""
        # Set stages for multiple issues
        worker_pool.set_worker_stage("BUG-123", WorkerStage.IMPLEMENTING)
        worker_pool.set_worker_stage("FEAT-456", WorkerStage.VALIDATING)
        worker_pool.set_worker_stage("ENH-789", WorkerStage.VERIFYING)

        # Since no workers are actually running, get_active_stages returns empty
        # (only returns stages for issues in _active_workers)
        assert worker_pool.get_active_stages() == {}

    def test_remove_worker_stage(self, worker_pool: WorkerPool) -> None:
        """Test removing worker stages."""
        # Set a stage
        worker_pool.set_worker_stage("BUG-123", WorkerStage.IMPLEMENTING)
        assert worker_pool.get_worker_stage("BUG-123") == WorkerStage.IMPLEMENTING

        # Remove the stage
        worker_pool.remove_worker_stage("BUG-123")
        assert worker_pool.get_worker_stage("BUG-123") is None

        # Removing non-existent stage should not raise
        worker_pool.remove_worker_stage("NONEXISTENT")


class TestRunWithContinuation:
    """Tests for WorkerPool._run_with_continuation() (BUG-819)."""

    def test_exits_cleanly_when_handoff_detected(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """When handoff is detected, exits cleanly with signal forwarded to stdout."""
        handoff_result = subprocess.CompletedProcess(
            args=["claude", "-p", "test"],
            returncode=0,
            stdout="CONTEXT_HANDOFF: Ready for fresh session\n",
            stderr="",
        )

        with patch.object(
            worker_pool, "_run_claude_command", return_value=handoff_result
        ) as mock_run:
            with patch(
                "little_loops.parallel.worker_pool.detect_context_handoff", return_value=True
            ):
                result = worker_pool._run_with_continuation(
                    "test", temp_repo_with_config, issue_id="BUG-819"
                )

        # Should call run_claude_command only once (no continuation spawned)
        mock_run.assert_called_once()
        assert result.returncode == 0
        assert "CONTEXT_HANDOFF:" in result.stdout

    def test_sentinel_triggers_explicit_handoff_instruction(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """Option E: sentinel file triggers explicit handoff instruction via --resume."""
        from little_loops.subprocess_utils import write_sentinel

        write_sentinel(temp_repo_with_config, token_count=130_000, context_limit=200_000)

        normal_result = subprocess.CompletedProcess(
            args=["claude", "-p", "test"],
            returncode=0,
            stdout="Work in progress...",
            stderr="",
        )
        handoff_result = subprocess.CompletedProcess(
            args=["claude", "-p", "handoff"],
            returncode=0,
            stdout="CONTEXT_HANDOFF: Ready for fresh session",
            stderr="",
        )
        continuation_result = subprocess.CompletedProcess(
            args=["claude", "-p", "continuation"],
            returncode=0,
            stdout="Done!",
            stderr="",
        )

        call_count = [0]
        resume_session_flags: list[bool] = []

        def mock_run_claude(command, working_dir, **kwargs):
            resume_session_flags.append(kwargs.get("resume_session", False))
            call_count[0] += 1
            if call_count[0] == 1:
                return normal_result
            elif call_count[0] == 2:
                return handoff_result
            return continuation_result

        with patch.object(worker_pool, "_run_claude_command", side_effect=mock_run_claude):
            with patch(
                "little_loops.parallel.worker_pool.detect_context_handoff",
                side_effect=lambda s: "CONTEXT_HANDOFF" in s,
            ):
                with patch(
                    "little_loops.parallel.worker_pool.read_continuation_prompt",
                    return_value="# Continuation prompt",
                ):
                    result = worker_pool._run_with_continuation(
                        "test",
                        temp_repo_with_config,
                        issue_id="BUG-1377",
                        max_continuations=3,
                    )

        # Session 1: normal run, sentinel detected → call 2 with resume_session=True
        # Session 2: explicit handoff instruction → CONTEXT_HANDOFF
        # Session 3: continuation
        assert call_count[0] == 3
        assert resume_session_flags[1] is True
        assert result.returncode == 0

    def test_guillotine_path_on_overflow(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """Option J: 'Prompt is too long' in stderr triggers fresh session with guillotine prompt."""
        overflow_result = subprocess.CompletedProcess(
            args=["claude", "-p", "test"],
            returncode=1,
            stdout="Partial work...",
            stderr="API error: Prompt is too long",
        )
        fresh_result = subprocess.CompletedProcess(
            args=["claude", "-p", "fresh"],
            returncode=0,
            stdout="Done from fresh session",
            stderr="",
        )

        call_count = [0]
        commands_received: list[str] = []

        def mock_run_claude(command, working_dir, **kwargs):
            call_count[0] += 1
            commands_received.append(command)
            return overflow_result if call_count[0] == 1 else fresh_result

        with patch.object(worker_pool, "_run_claude_command", side_effect=mock_run_claude):
            with patch(
                "little_loops.parallel.worker_pool.detect_context_handoff", return_value=False
            ):
                worker_pool._run_with_continuation(
                    "test",
                    temp_repo_with_config,
                    issue_id="BUG-1377",
                    max_continuations=3,
                    context_limit=200_000,
                )

        assert call_count[0] == 2
        assert "CONTEXT LIMIT REACHED" in commands_received[1]

    def test_guillotine_with_run_dir_writes_resume_file(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
        tmp_path: Path,
    ) -> None:
        """Option J + run_dir: writes guillotine-prompt.md and invokes /ll:resume."""
        run_dir = tmp_path / "runs" / "my-loop-20260101"
        run_dir.mkdir(parents=True, exist_ok=True)

        overflow_result = subprocess.CompletedProcess(
            args=["claude", "-p", "test"],
            returncode=1,
            stdout="Partial work...",
            stderr="API error: Prompt is too long",
        )
        fresh_result = subprocess.CompletedProcess(
            args=["claude", "-p", "fresh"],
            returncode=0,
            stdout="Done from resume",
            stderr="",
        )

        call_count = [0]
        commands_received: list[str] = []

        def mock_run_claude(command, working_dir, **kwargs):
            call_count[0] += 1
            commands_received.append(command)
            return overflow_result if call_count[0] == 1 else fresh_result

        with patch.object(worker_pool, "_run_claude_command", side_effect=mock_run_claude):
            with patch(
                "little_loops.parallel.worker_pool.detect_context_handoff", return_value=False
            ):
                worker_pool._run_with_continuation(
                    "test",
                    temp_repo_with_config,
                    issue_id="BUG-1377",
                    max_continuations=3,
                    context_limit=200_000,
                    run_dir=str(run_dir),
                )

        assert call_count[0] == 2
        assert commands_received[1].startswith("/ll:resume")
        assert "CONTEXT LIMIT REACHED" not in commands_received[1]
        guillotine_file = run_dir / "guillotine-prompt.md"
        assert guillotine_file.exists()
        content = guillotine_file.read_text()
        assert "## Intent" in content
        assert "## Next Steps" in content

    def test_guillotine_with_sprint_context_injects_framing_in_blob(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """BUG-2141: sprint_context injects framing into guillotine prompt blob (no run_dir)."""
        from little_loops.parallel.types import SprintWorkerContext

        sprint_ctx = SprintWorkerContext(issue_id="FEAT-025", branch="main")

        overflow_result = subprocess.CompletedProcess(
            args=["claude", "-p", "test"],
            returncode=1,
            stdout="Partial work...",
            stderr="API error: Prompt is too long",
        )
        fresh_result = subprocess.CompletedProcess(
            args=["claude", "-p", "fresh"],
            returncode=0,
            stdout="Done from fresh session",
            stderr="",
        )

        call_count = [0]
        commands_received: list[str] = []

        def mock_run_claude(command, working_dir, **kwargs):
            call_count[0] += 1
            commands_received.append(command)
            return overflow_result if call_count[0] == 1 else fresh_result

        with patch.object(worker_pool, "_run_claude_command", side_effect=mock_run_claude):
            with patch(
                "little_loops.parallel.worker_pool.detect_context_handoff", return_value=False
            ):
                worker_pool._run_with_continuation(
                    "test",
                    temp_repo_with_config,
                    issue_id="FEAT-025",
                    max_continuations=3,
                    context_limit=200_000,
                    sprint_context=sprint_ctx,
                )

        assert call_count[0] == 2
        fresh_cmd = commands_received[1]
        assert "Sprint Worker Context" in fresh_cmd
        assert "FEAT-025" in fresh_cmd
        assert "exit immediately" in fresh_cmd
        assert "Branch: main" in fresh_cmd

    def test_guillotine_with_sprint_context_and_run_dir_writes_framing_to_file(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
        tmp_path: Path,
    ) -> None:
        """BUG-2141: sprint_context injects framing into guillotine file when run_dir is set."""
        from little_loops.parallel.types import SprintWorkerContext

        sprint_ctx = SprintWorkerContext(issue_id="FEAT-025", branch="parallel/feat-025-ts")
        run_dir = tmp_path / "runs" / "sprint-loop-20260614"
        run_dir.mkdir(parents=True, exist_ok=True)

        overflow_result = subprocess.CompletedProcess(
            args=["claude", "-p", "test"],
            returncode=1,
            stdout="Partial work...",
            stderr="API error: Prompt is too long",
        )
        fresh_result = subprocess.CompletedProcess(
            args=["claude", "-p", "fresh"],
            returncode=0,
            stdout="Done from resume",
            stderr="",
        )

        call_count = [0]
        commands_received: list[str] = []

        def mock_run_claude(command, working_dir, **kwargs):
            call_count[0] += 1
            commands_received.append(command)
            return overflow_result if call_count[0] == 1 else fresh_result

        with patch.object(worker_pool, "_run_claude_command", side_effect=mock_run_claude):
            with patch(
                "little_loops.parallel.worker_pool.detect_context_handoff", return_value=False
            ):
                worker_pool._run_with_continuation(
                    "test",
                    temp_repo_with_config,
                    issue_id="FEAT-025",
                    max_continuations=3,
                    context_limit=200_000,
                    run_dir=str(run_dir),
                    sprint_context=sprint_ctx,
                )

        assert call_count[0] == 2
        assert commands_received[1].startswith("/ll:resume")
        guillotine_file = run_dir / "guillotine-prompt.md"
        assert guillotine_file.exists()
        content = guillotine_file.read_text()
        assert "Sprint Worker Context" in content
        assert "FEAT-025" in content
        assert "exit immediately" in content
        assert "Branch: parallel/feat-025-ts" in content
        # Sprint framing comes before the Intent section
        assert content.index("Sprint Worker Context") < content.index("## Intent")

    def test_large_cumulative_tokens_with_clean_completion_no_guillotine(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """BUG-2280: cumulative session tokens >> context window must NOT trigger Option J.

        Mirrors the issue_manager regression test for the parallel worker path.
        """
        clean_result = subprocess.CompletedProcess(
            args=["claude", "-p", "test"],
            returncode=0,
            stdout="Issue implemented and committed",
            stderr="",
        )

        call_count = [0]

        def mock_run_claude(command, working_dir, **kwargs):
            call_count[0] += 1
            on_usage = kwargs.get("on_usage")
            if on_usage:
                on_usage(989_202, 0)  # cumulative tokens far over 200K window
            return clean_result

        with patch.object(worker_pool, "_run_claude_command", side_effect=mock_run_claude):
            with patch(
                "little_loops.parallel.worker_pool.detect_context_handoff", return_value=False
            ):
                worker_pool._run_with_continuation(
                    "test",
                    temp_repo_with_config,
                    issue_id="BUG-2280",
                    max_continuations=3,
                    context_limit=200_000,
                )

        assert call_count[0] == 1, (
            f"Expected 1 call (no continuation), got {call_count[0]}: "
            "cumulative tokens must not trigger Option J"
        )

    def test_option_j_guard_skips_when_issue_already_done(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """BUG-2281: Option J guard skips continuation when issue is already done."""
        issues_dir = temp_repo_with_config / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P2-BUG-999-test.md"
        issue_file.write_text("---\nstatus: done\n---\n\n# BUG-999: Test")

        overflow_result = subprocess.CompletedProcess(
            args=["claude", "-p", "test"],
            returncode=1,
            stdout="Partial work...",
            stderr="API error: Prompt is too long",
        )

        call_count = [0]

        def mock_run_claude(command, working_dir, **kwargs):
            call_count[0] += 1
            return overflow_result

        with patch.object(worker_pool, "_run_claude_command", side_effect=mock_run_claude):
            with patch(
                "little_loops.parallel.worker_pool.detect_context_handoff", return_value=False
            ):
                result = worker_pool._run_with_continuation(
                    "test",
                    temp_repo_with_config,
                    issue_id="BUG-999",
                    max_continuations=3,
                    context_limit=200_000,
                )

        assert call_count[0] == 1, (
            f"Expected 1 call (no continuation), got {call_count[0]}: "
            "no fresh session should be spawned when issue is already done"
        )
        assert result.returncode == 0


class TestWorkerPoolDecisionNeededGate:
    """Tests for conditional decide-issue invocation when decision_needed=True."""

    def test_decide_issue_invoked_when_decision_needed(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_process_issue() calls decide-issue when issue.decision_needed=True."""
        ready_output = "## VERDICT: **READY**"
        manage_output = "Issue resolved"

        issue = MagicMock()
        issue.issue_id = "FEAT-999"
        issue.issue_type = "features"
        issue.path = Path(".issues/features/P3-FEAT-999-decide.md")
        issue.decision_needed = True

        commands_called: list[str] = []

        def mock_run_command(
            cmd: str, path: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            commands_called.append(cmd)
            if len(commands_called) == 1:
                return subprocess.CompletedProcess([], 0, ready_output, "")
            return subprocess.CompletedProcess([], 0, manage_output, "")

        with patch.object(worker_pool, "_setup_worktree"):
            with patch.object(worker_pool, "_get_main_repo_baseline", return_value=set()):
                with patch.object(worker_pool, "_run_claude_command", side_effect=mock_run_command):
                    with patch.object(
                        worker_pool, "_get_changed_files", return_value=["src/fix.py"]
                    ):
                        with patch.object(worker_pool, "_detect_main_repo_leaks", return_value=[]):
                            with patch.object(
                                worker_pool, "_update_branch_base", return_value=(True, "")
                            ):
                                worker_pool._process_issue(issue)

        # decide-issue command should be among the calls (after ready-issue, before manage-issue)
        assert len(commands_called) >= 3
        assert any("decide-issue" in cmd for cmd in commands_called)

    def test_decide_issue_skipped_when_decision_not_needed(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_process_issue() does NOT call decide-issue when decision_needed is None."""
        ready_output = "## VERDICT: **READY**"
        manage_output = "Issue resolved"

        issue = MagicMock()
        issue.issue_id = "FEAT-998"
        issue.issue_type = "features"
        issue.path = Path(".issues/features/P3-FEAT-998-no-decide.md")
        issue.decision_needed = None

        commands_called: list[str] = []

        def mock_run_command(
            cmd: str, path: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            commands_called.append(cmd)
            if len(commands_called) == 1:
                return subprocess.CompletedProcess([], 0, ready_output, "")
            return subprocess.CompletedProcess([], 0, manage_output, "")

        with patch.object(worker_pool, "_setup_worktree"):
            with patch.object(worker_pool, "_get_main_repo_baseline", return_value=set()):
                with patch.object(worker_pool, "_run_claude_command", side_effect=mock_run_command):
                    with patch.object(
                        worker_pool, "_get_changed_files", return_value=["src/fix.py"]
                    ):
                        with patch.object(worker_pool, "_detect_main_repo_leaks", return_value=[]):
                            with patch.object(
                                worker_pool, "_update_branch_base", return_value=(True, "")
                            ):
                                worker_pool._process_issue(issue)

        # decide-issue command should NOT be called
        assert not any("decide-issue" in cmd for cmd in commands_called)


class TestPruneMergedFeatureBranches:
    """Tests for WorkerPool.prune_merged_feature_branches() (ENH-2181)."""

    def _make_git_run(
        self,
        current_branch: str = "main",
        all_branches: list[str] | None = None,
        merged_branches: list[str] | None = None,
        delete_succeeds: bool = True,
    ):
        """Return a side_effect function for git_lock.run() calls."""
        all_branches = all_branches or []
        merged_branches = merged_branches or []

        def _all_branches_output() -> str:
            lines = []
            for b in all_branches:
                prefix = "* " if b == current_branch else "  "
                lines.append(f"{prefix}{b}")
            return "\n".join(lines) + ("\n" if lines else "")

        def _merged_output() -> str:
            lines = []
            for b in merged_branches:
                prefix = "* " if b == current_branch else "  "
                lines.append(f"{prefix}{b}")
            return "\n".join(lines) + ("\n" if lines else "")

        def side_effect(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return subprocess.CompletedProcess([], 0, current_branch + "\n", "")
            if args == ["branch"]:
                return subprocess.CompletedProcess([], 0, _all_branches_output(), "")
            if len(args) >= 3 and args[0] == "branch" and args[1] == "--merged":
                return subprocess.CompletedProcess([], 0, _merged_output(), "")
            if args[:2] == ["branch", "-D"]:
                if delete_succeeds:
                    return subprocess.CompletedProcess([], 0, "", "")
                return subprocess.CompletedProcess(
                    [], 1, "", f"error: Cannot delete branch '{args[2]}'"
                )
            return subprocess.CompletedProcess([], 1, "", f"unexpected: {args}")

        return side_effect

    def test_merged_feature_branch_is_deleted(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """A feature branch fully merged into base_branch is deleted."""
        side_effect = self._make_git_run(
            current_branch="main",
            all_branches=["main", "feature/bug-001-fix-null"],
            merged_branches=["main", "feature/bug-001-fix-null"],
        )
        with patch("little_loops.parallel.github_utils.is_pr_merged", return_value=False):
            with patch.object(worker_pool._git_lock, "run", side_effect=side_effect):
                pruned, skipped = worker_pool.prune_merged_feature_branches("main")

        assert pruned == ["feature/bug-001-fix-null"]
        assert skipped == []

    def test_unmerged_feature_branch_is_retained(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """A feature branch NOT merged into base_branch is left untouched."""
        side_effect = self._make_git_run(
            current_branch="main",
            all_branches=["main", "feature/enh-002-open-pr"],
            merged_branches=["main"],  # feature branch NOT in merged list
        )
        with patch("little_loops.parallel.github_utils.is_pr_merged", return_value=False):
            with patch.object(worker_pool._git_lock, "run", side_effect=side_effect):
                pruned, skipped = worker_pool.prune_merged_feature_branches("main")

        assert pruned == []
        assert skipped == []

    def test_parallel_branches_are_not_touched(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """parallel/* branches are never deleted, even if merged."""
        side_effect = self._make_git_run(
            current_branch="main",
            all_branches=["main", "parallel/bug-003-20240115", "feature/bug-001-fix"],
            merged_branches=["main", "parallel/bug-003-20240115", "feature/bug-001-fix"],
        )
        with patch("little_loops.parallel.github_utils.is_pr_merged", return_value=False):
            with patch.object(worker_pool._git_lock, "run", side_effect=side_effect) as mock_run:
                pruned, skipped = worker_pool.prune_merged_feature_branches("main")

        # Only the feature branch should be pruned; parallel branch is untouched
        assert pruned == ["feature/bug-001-fix"]
        assert skipped == []
        # Verify no branch -D call was made for the parallel branch
        delete_calls = [c for c in mock_run.call_args_list if c.args[0][:2] == ["branch", "-D"]]
        assert all("parallel/" not in str(c) for c in delete_calls)

    def test_dry_run_lists_but_does_not_delete(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """Dry-run returns candidates without issuing any branch -D command."""
        side_effect = self._make_git_run(
            current_branch="main",
            all_branches=["main", "feature/bug-004-dry-test"],
            merged_branches=["main", "feature/bug-004-dry-test"],
        )
        with patch("little_loops.parallel.github_utils.is_pr_merged", return_value=False):
            with patch.object(worker_pool._git_lock, "run", side_effect=side_effect) as mock_run:
                pruned, skipped = worker_pool.prune_merged_feature_branches("main", dry_run=True)

        assert pruned == ["feature/bug-004-dry-test"]
        assert skipped == []
        # No destructive git branch -D call issued
        delete_calls = [c for c in mock_run.call_args_list if c.args[0][:2] == ["branch", "-D"]]
        assert delete_calls == []

    def test_current_branch_is_never_deleted(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """The currently checked-out branch is never deleted, even if it matches feature/."""
        side_effect = self._make_git_run(
            current_branch="feature/bug-005-active",
            all_branches=["main", "feature/bug-005-active"],
            merged_branches=["main", "feature/bug-005-active"],
        )
        with patch("little_loops.parallel.github_utils.is_pr_merged", return_value=False):
            with patch.object(worker_pool._git_lock, "run", side_effect=side_effect):
                pruned, skipped = worker_pool.prune_merged_feature_branches("main")

        assert pruned == []
        assert skipped == []

    def test_squash_merged_branch_pruned_via_gh(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """A squash-merged branch not in git --merged list is pruned when is_pr_merged() returns True."""
        side_effect = self._make_git_run(
            current_branch="main",
            all_branches=["main", "feature/enh-006-squash"],
            merged_branches=["main"],  # git --merged misses squash merges
        )
        # Simulate gh reporting the PR as merged
        with patch("little_loops.parallel.github_utils.is_pr_merged", return_value=True):
            with patch.object(worker_pool._git_lock, "run", side_effect=side_effect):
                pruned, skipped = worker_pool.prune_merged_feature_branches("main")

        assert pruned == ["feature/enh-006-squash"]
        assert skipped == []

    def test_failed_delete_goes_to_skipped(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """Branches that fail to delete are reported in skipped, not pruned."""
        side_effect = self._make_git_run(
            current_branch="main",
            all_branches=["main", "feature/bug-007-fail"],
            merged_branches=["main", "feature/bug-007-fail"],
            delete_succeeds=False,
        )
        with patch("little_loops.parallel.github_utils.is_pr_merged", return_value=False):
            with patch.object(worker_pool._git_lock, "run", side_effect=side_effect):
                pruned, skipped = worker_pool.prune_merged_feature_branches("main")

        assert pruned == []
        assert skipped == ["feature/bug-007-fail"]


class TestPerWorktreeProofFirstGate:
    """ENH-2219: Per-worktree proof-first-task gate tests."""

    @pytest.fixture
    def lt_enabled_br_config(self, tmp_path: Path) -> BRConfig:
        """BRConfig with learning_tests.enabled=True."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        config_data = {"learning_tests": {"enabled": True, "stale_after_days": 30}}
        (ll_dir / "ll-config.json").write_text(json.dumps(config_data))
        return BRConfig(tmp_path)

    def _make_issue(
        self,
        tmp_path: Path,
        issue_id: str,
        *,
        learning_tests_required: list[str] | None = None,
    ) -> IssueInfo:
        """Create a stub IssueInfo for gate tests."""
        issue_path = tmp_path / f"P2-{issue_id}-stub.md"
        issue_path.write_text(
            f"---\nid: {issue_id}\ntitle: Stub\nstatus: open\n---\n# {issue_id}: Stub\n"
        )
        return IssueInfo(
            path=issue_path,
            issue_type="enhancements",
            priority="P2",
            issue_id=issue_id,
            title="Stub issue",
            learning_tests_required=learning_tests_required,
        )

    def _gate_ok_result(self) -> MagicMock:
        """Subprocess result simulating gate exit 0 (all terminal states)."""
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = ""
        mock.stderr = ""
        return mock

    def test_gate_skipped_when_lt_disabled(self, br_config: BRConfig, tmp_path: Path) -> None:
        """Gate subprocess not called when learning_tests.enabled=False (default)."""
        from little_loops.parallel.worker_pool import _run_per_worktree_proof_first_gate

        issue = self._make_issue(tmp_path, "ENH-001", learning_tests_required=["httpx"])

        with patch("little_loops.parallel.worker_pool.subprocess.run") as mock_sub:
            result = _run_per_worktree_proof_first_gate(
                issue,
                tmp_path,
                br_config,  # learning_tests.enabled=False by default
                ParallelConfig(),
                MagicMock(),
            )

        assert result is True
        mock_sub.assert_not_called()

    def test_gate_skipped_when_no_learning_tests_required(
        self, lt_enabled_br_config: BRConfig, tmp_path: Path
    ) -> None:
        """BUG-2320: field is None → JIT extraction runs; empty result → no subprocess.

        With the field unset the gate now resolves targets just-in-time from the
        issue text. When extraction yields nothing the gate proceeds without
        invoking ``proof-first-task`` (same outcome as before, but now an
        auditable decision rather than a silent short-circuit on ``is None``).
        """
        from little_loops.parallel.worker_pool import _run_per_worktree_proof_first_gate

        issue = self._make_issue(tmp_path, "ENH-001", learning_tests_required=None)

        with (
            patch("little_loops.parallel.worker_pool.subprocess.run") as mock_sub,
            patch(
                "little_loops.learning_tests.extractor.extract_learning_targets",
                return_value=[],
            ) as mock_extract,
        ):
            result = _run_per_worktree_proof_first_gate(
                issue,
                tmp_path,
                lt_enabled_br_config,
                ParallelConfig(),
                MagicMock(),
            )

        assert result is True
        mock_extract.assert_called_once()
        mock_sub.assert_not_called()

    def test_gate_resolves_targets_jit_when_field_none(
        self, lt_enabled_br_config: BRConfig, tmp_path: Path
    ) -> None:
        """BUG-2320: field None but issue text names an API → gate runs proof-first-task.

        The previous ``is None → return True`` short-circuit silently bypassed the
        firewall for unrefined issues. The fix resolves targets JIT, so an issue
        whose text yields targets must run the gate.
        """
        from little_loops.parallel.worker_pool import _run_per_worktree_proof_first_gate

        issue = self._make_issue(tmp_path, "ENH-004", learning_tests_required=None)

        with (
            patch(
                "little_loops.parallel.worker_pool.subprocess.run",
                return_value=self._gate_ok_result(),
            ) as mock_sub,
            patch(
                "little_loops.learning_tests.extractor.extract_learning_targets",
                return_value=["stripe"],
            ) as mock_extract,
        ):
            result = _run_per_worktree_proof_first_gate(
                issue,
                tmp_path,
                lt_enabled_br_config,
                ParallelConfig(),
                MagicMock(),
            )

        assert result is True
        mock_extract.assert_called_once()
        mock_sub.assert_called_once()
        cmd = mock_sub.call_args[0][0]
        assert "proof-first-task" in cmd
        assert f"issue_file={issue.path}" in " ".join(cmd)

    def test_gate_logs_no_external_deps_when_jit_empty(
        self, lt_enabled_br_config: BRConfig, tmp_path: Path
    ) -> None:
        """BUG-2320: empty JIT resolution logs an auditable 'no external deps' decision."""
        from little_loops.parallel.worker_pool import _run_per_worktree_proof_first_gate

        issue = self._make_issue(tmp_path, "ENH-005", learning_tests_required=None)
        logger = MagicMock()

        with (
            patch("little_loops.parallel.worker_pool.subprocess.run") as mock_sub,
            patch(
                "little_loops.learning_tests.extractor.extract_learning_targets",
                return_value=[],
            ),
        ):
            result = _run_per_worktree_proof_first_gate(
                issue,
                tmp_path,
                lt_enabled_br_config,
                ParallelConfig(),
                logger,
            )

        assert result is True
        mock_sub.assert_not_called()
        logged = " ".join(str(call) for call in logger.info.call_args_list)
        assert "no external dependencies detected" in logged

    def test_gate_threads_targets_csv_when_learning_tests_required_populated(
        self, lt_enabled_br_config: BRConfig, tmp_path: Path
    ) -> None:
        """ENH-2405: a populated learning_tests_required field must be forwarded as
        --context targets_csv=<csv> so the gate proves the registered list instead
        of re-extracting via assumption-firewall."""
        from little_loops.parallel.worker_pool import _run_per_worktree_proof_first_gate

        issue = self._make_issue(tmp_path, "ENH-006", learning_tests_required=["httpx"])

        with patch(
            "little_loops.parallel.worker_pool.subprocess.run",
            return_value=self._gate_ok_result(),
        ) as mock_sub:
            result = _run_per_worktree_proof_first_gate(
                issue,
                tmp_path,
                lt_enabled_br_config,
                ParallelConfig(),
                MagicMock(),
            )

        assert result is True
        mock_sub.assert_called_once()
        cmd = mock_sub.call_args[0][0]
        assert "targets_csv=httpx" in " ".join(cmd)

    def test_blocked_result_skips_manage_issue(
        self, lt_enabled_br_config: BRConfig, tmp_path: Path
    ) -> None:
        """Gate returning blocked state skips manage-issue; WorkerResult.success=False."""
        from little_loops.parallel.worker_pool import _run_per_worktree_proof_first_gate

        issue = self._make_issue(tmp_path, "ENH-002", learning_tests_required=["httpx"])

        # Write state file that simulates proof-first-task landing in "blocked" state
        loops_running = tmp_path / ".loops" / ".running"
        loops_running.mkdir(parents=True, exist_ok=True)
        state_data = {"current_state": "blocked", "status": "completed"}
        (loops_running / "proof-first-task.state.json").write_text(json.dumps(state_data))

        with patch(
            "little_loops.parallel.worker_pool.subprocess.run",
            return_value=self._gate_ok_result(),
        ) as mock_sub:
            result = _run_per_worktree_proof_first_gate(
                issue,
                tmp_path,
                lt_enabled_br_config,
                ParallelConfig(),
                MagicMock(),
            )

        assert result is False
        mock_sub.assert_called_once()
        cmd = mock_sub.call_args[0][0]
        assert "proof-first-task" in cmd
        assert f"issue_file={issue.path}" in " ".join(cmd)

    def test_skip_learning_gate_flag_bypasses_gate(
        self, lt_enabled_br_config: BRConfig, tmp_path: Path
    ) -> None:
        """--skip-learning-gate bypasses gate subprocess even with learning_tests_required."""
        from little_loops.parallel.worker_pool import _run_per_worktree_proof_first_gate

        issue = self._make_issue(tmp_path, "ENH-003", learning_tests_required=["httpx"])
        parallel_config = ParallelConfig(skip_learning_gate=True)

        with patch("little_loops.parallel.worker_pool.subprocess.run") as mock_sub:
            result = _run_per_worktree_proof_first_gate(
                issue,
                tmp_path,
                lt_enabled_br_config,
                parallel_config,
                MagicMock(),
            )

        assert result is True
        mock_sub.assert_not_called()
