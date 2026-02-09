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
    """Create a temporary directory with .claude config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        claude_dir = repo_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "ll-config.json").write_text("{}")
        (claude_dir / "settings.local.json").write_text('{"model": "claude-sonnet-4"}')

        # Create worktree base
        worktree_base = repo_path / ".worktrees"
        worktree_base.mkdir()

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

    def test_interrupted_defaults_to_false(self) -> None:
        """WorkerResult.interrupted defaults to False."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
        )

        assert result.interrupted is False

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

    def test_init_sets_attributes(
        self,
        default_parallel_config: ParallelConfig,
        br_config: BRConfig,
        mock_logger: MagicMock,
        temp_repo_with_config: Path,
    ) -> None:
        """WorkerPool initializes with correct attributes."""
        pool = WorkerPool(
            parallel_config=default_parallel_config,
            br_config=br_config,
            logger=mock_logger,
            repo_path=temp_repo_with_config,
        )

        assert pool.parallel_config == default_parallel_config
        assert pool.br_config == br_config
        assert pool.logger == mock_logger
        assert pool.repo_path == temp_repo_with_config
        assert pool._executor is None
        assert pool._active_workers == {}
        assert pool._active_processes == {}

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
        worktree_path.mkdir(parents=True)
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
        worktree_path.mkdir(parents=True)

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
        worktree_path.mkdir(parents=True)

        captured_commands: list[list[str]] = []

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            captured_commands.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            with patch("subprocess.run") as mock_subprocess:
                # Return parallel branch name
                mock_subprocess.return_value = subprocess.CompletedProcess(
                    [], 0, "parallel/bug-001\n", ""
                )
                with patch("shutil.rmtree"):
                    worker_pool._cleanup_worktree(worktree_path)

        # Should have called branch -D
        branch_cmds = [c for c in captured_commands if "branch" in c and "-D" in c]
        assert len(branch_cmds) >= 1

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
        """cleanup_all_worktrees() removes all worker-* directories."""
        worktree_base = temp_repo_with_config / ".worktrees"
        (worktree_base / "worker-bug-001").mkdir()
        (worktree_base / "worker-bug-002").mkdir()
        (worktree_base / "other-dir").mkdir()  # Should not be removed

        cleanup_calls: list[Path] = []

        def mock_cleanup(path: Path) -> None:
            cleanup_calls.append(path)

        with patch.object(worker_pool, "_cleanup_worktree", side_effect=mock_cleanup):
            worker_pool.cleanup_all_worktrees()

        # Should have cleaned up 2 worker directories
        assert len(cleanup_calls) == 2
        cleaned_names = [p.name for p in cleanup_calls]
        assert "worker-bug-001" in cleaned_names
        assert "worker-bug-002" in cleaned_names
        assert "other-dir" not in cleaned_names


class TestActiveWorktreeProtection:
    """Tests for BUG-142: Prevent cleanup of worktrees in active use."""

    def test_cleanup_worktree_skips_active_worktree(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_cleanup_worktree() should skip worktrees in _active_worktrees set."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker-test-001"
        worktree_path.mkdir(parents=True)

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
        worktree_path.mkdir(parents=True)

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
        active_path.mkdir()
        inactive_path.mkdir()

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

        def setup_and_capture(path: Path, branch: str) -> None:
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
        """_process_issue() returns failure when ready_issue fails."""
        with patch.object(worker_pool, "_setup_worktree"):
            with patch.object(worker_pool, "_get_main_repo_baseline", return_value=set()):
                with patch.object(worker_pool, "_run_claude_command") as mock_run:
                    mock_run.return_value = subprocess.CompletedProcess(
                        [], 1, "", "ready_issue failed"
                    )

                    result = worker_pool._process_issue(mock_issue)

        assert result.success is False
        assert "ready_issue failed" in (result.error or "")

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

    def test_set_and_get_worker_stage(
        self, worker_pool: WorkerPool
    ) -> None:
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
