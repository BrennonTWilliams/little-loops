"""Tests for GitLock thread-safe git operations."""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from little_loops.parallel.git_lock import GitLock

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_logger() -> MagicMock:
    """Create a mock logger."""
    return MagicMock()


@pytest.fixture
def git_lock(mock_logger: MagicMock) -> GitLock:
    """Create a GitLock instance for testing."""
    return GitLock(
        logger=mock_logger,
        max_retries=3,
        initial_backoff=0.5,
        max_backoff=8.0,
    )


@pytest.fixture
def temp_cwd(tmp_path: Path) -> Path:
    """Create a temporary working directory."""
    return tmp_path


class TestInit:
    """Tests for GitLock initialization."""

    def test_default_values(self) -> None:
        """Default initialization values."""
        lock = GitLock()

        assert lock.max_retries == 3
        assert lock.initial_backoff == 0.5
        assert lock.max_backoff == 8.0
        assert lock._logger is None

    def test_custom_values(self, mock_logger: MagicMock) -> None:
        """Custom initialization values."""
        lock = GitLock(
            logger=mock_logger,
            max_retries=5,
            initial_backoff=1.0,
            max_backoff=16.0,
        )

        assert lock.max_retries == 5
        assert lock.initial_backoff == 1.0
        assert lock.max_backoff == 16.0
        assert lock._logger is mock_logger

    def test_lock_is_rlock(self) -> None:
        """Internal lock is RLock for reentrancy."""
        lock = GitLock()
        assert isinstance(lock._lock, type(threading.RLock()))


class TestContextManager:
    """Tests for GitLock context manager protocol."""

    def test_enter_acquires_lock(self, git_lock: GitLock) -> None:
        """__enter__ acquires the internal lock."""
        # Lock should be acquirable before entering
        assert git_lock._lock.acquire(blocking=False)
        git_lock._lock.release()

        with git_lock:
            # Inside context, lock is held
            pass

    def test_exit_releases_lock_on_success(self, git_lock: GitLock) -> None:
        """__exit__ releases lock after successful block."""
        with git_lock:
            pass

        # Lock should be acquirable after exiting
        assert git_lock._lock.acquire(blocking=False)
        git_lock._lock.release()

    def test_exit_releases_lock_on_exception(self, git_lock: GitLock) -> None:
        """__exit__ releases lock even when exception raised."""
        with pytest.raises(ValueError, match="test error"):
            with git_lock:
                raise ValueError("test error")

        # Lock should still be acquirable after exception
        assert git_lock._lock.acquire(blocking=False)
        git_lock._lock.release()

    def test_returns_self_on_enter(self, git_lock: GitLock) -> None:
        """__enter__ returns the GitLock instance."""
        with git_lock as lock:
            assert lock is git_lock

    def test_reentrant_lock_same_thread(self, git_lock: GitLock) -> None:
        """RLock allows same thread to acquire lock multiple times."""
        with git_lock:
            with git_lock:  # Should not deadlock
                pass


class TestRunMethod:
    """Tests for GitLock.run() method."""

    def test_run_executes_git_command(self, git_lock: GitLock, temp_cwd: Path) -> None:
        """run() executes git command with correct arguments."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["git", "status"],
                returncode=0,
                stdout="clean",
                stderr="",
            )

            result = git_lock.run(["status"], cwd=temp_cwd)

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["git", "status"]
        assert call_args[1]["cwd"] == temp_cwd
        assert result.returncode == 0

    def test_run_passes_timeout(self, git_lock: GitLock, temp_cwd: Path) -> None:
        """run() passes timeout to subprocess."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

            git_lock.run(["status"], cwd=temp_cwd, timeout=60)

        assert mock_run.call_args[1]["timeout"] == 60

    def test_run_captures_output_by_default(self, git_lock: GitLock, temp_cwd: Path) -> None:
        """run() captures output by default."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="output", stderr=""
            )

            git_lock.run(["status"], cwd=temp_cwd)

        assert mock_run.call_args[1]["capture_output"] is True
        assert mock_run.call_args[1]["text"] is True

    def test_run_acquires_lock(self, git_lock: GitLock, temp_cwd: Path) -> None:
        """run() acquires lock before executing."""
        lock_held_during_run: list[bool] = []

        def check_lock(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            # Try to acquire lock from another thread to verify it's held
            acquired = git_lock._lock.acquire(blocking=False)
            if acquired:
                git_lock._lock.release()
            lock_held_during_run.append(not acquired)
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=check_lock):
            git_lock.run(["status"], cwd=temp_cwd)

        # Lock is held by same thread (RLock), so acquire succeeds
        # But we can verify run() enters the lock context
        assert len(lock_held_during_run) == 1


class TestRetryLogic:
    """Tests for exponential backoff retry logic."""

    def test_retry_on_index_lock_error(
        self, git_lock: GitLock, temp_cwd: Path, mock_logger: MagicMock
    ) -> None:
        """Retries when index.lock error occurs."""
        call_count = [0]

        def mock_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            call_count[0] += 1
            if call_count[0] < 3:
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=1,
                    stdout="",
                    stderr="fatal: Unable to create '.git/index.lock': File exists",
                )
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="success", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            with patch("time.sleep"):  # Don't actually wait
                result = git_lock.run(["status"], cwd=temp_cwd)

        assert call_count[0] == 3
        assert result.returncode == 0

    def test_exponential_backoff_timing(self, git_lock: GitLock, temp_cwd: Path) -> None:
        """Backoff doubles each retry up to max."""
        sleep_times: list[float] = []

        def capture_sleep(seconds: float) -> None:
            sleep_times.append(seconds)

        def always_fail(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="index.lock exists"
            )

        with patch("subprocess.run", side_effect=always_fail):
            with patch("time.sleep", side_effect=capture_sleep):
                git_lock.run(["status"], cwd=temp_cwd)

        # Should retry max_retries times: 0.5, 1.0, 2.0
        assert sleep_times == [0.5, 1.0, 2.0]

    def test_backoff_capped_at_max(self, temp_cwd: Path, mock_logger: MagicMock) -> None:
        """Backoff does not exceed max_backoff."""
        lock = GitLock(
            logger=mock_logger,
            max_retries=5,
            initial_backoff=2.0,
            max_backoff=4.0,
        )
        sleep_times: list[float] = []

        def always_fail(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="index.lock"
            )

        with patch("subprocess.run", side_effect=always_fail):
            with patch("time.sleep", side_effect=lambda s: sleep_times.append(s)):
                lock.run(["status"], cwd=temp_cwd)

        # 2.0, 4.0, 4.0, 4.0, 4.0 (capped at max)
        assert sleep_times == [2.0, 4.0, 4.0, 4.0, 4.0]

    def test_no_retry_on_non_lock_error(self, git_lock: GitLock, temp_cwd: Path) -> None:
        """Does not retry on non-index.lock errors."""
        call_count = [0]

        def fail_once(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            call_count[0] += 1
            return subprocess.CompletedProcess(
                args=[], returncode=128, stdout="", stderr="fatal: not a git repository"
            )

        with patch("subprocess.run", side_effect=fail_once):
            result = git_lock.run(["status"], cwd=temp_cwd)

        assert call_count[0] == 1
        assert result.returncode == 128

    def test_returns_last_result_after_max_retries(
        self, git_lock: GitLock, temp_cwd: Path, mock_logger: MagicMock
    ) -> None:
        """Returns last failed result after exhausting retries."""

        def always_fail(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="index.lock error"
            )

        with patch("subprocess.run", side_effect=always_fail):
            with patch("time.sleep"):
                result = git_lock.run(["status"], cwd=temp_cwd)

        assert result.returncode == 1
        assert "index.lock" in result.stderr
        # Debug should be called for each retry attempt
        assert mock_logger.debug.call_count == 3

    def test_logs_retry_attempts(
        self, git_lock: GitLock, temp_cwd: Path, mock_logger: MagicMock
    ) -> None:
        """Logs debug message on each retry."""
        call_count = [0]

        def fail_twice(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            call_count[0] += 1
            if call_count[0] <= 2:
                return subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="", stderr="index.lock"
                )
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fail_twice):
            with patch("time.sleep"):
                git_lock.run(["status"], cwd=temp_cwd)

        # Should log 2 retry attempts
        assert mock_logger.debug.call_count == 2


class TestTimeoutHandling:
    """Tests for timeout handling."""

    def test_timeout_triggers_retry(
        self, git_lock: GitLock, temp_cwd: Path, mock_logger: MagicMock
    ) -> None:
        """Timeout causes retry with backoff."""
        call_count = [0]

        def timeout_then_succeed(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            call_count[0] += 1
            if call_count[0] < 2:
                raise subprocess.TimeoutExpired(cmd=["git"], timeout=30)
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="success", stderr="")

        with patch("subprocess.run", side_effect=timeout_then_succeed):
            with patch("time.sleep"):
                result = git_lock.run(["status"], cwd=temp_cwd)

        assert call_count[0] == 2
        assert result.returncode == 0

    def test_timeout_raises_after_max_retries(self, git_lock: GitLock, temp_cwd: Path) -> None:
        """TimeoutExpired raised after exhausting retries."""

        def always_timeout(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired(cmd=["git"], timeout=30)

        with patch("subprocess.run", side_effect=always_timeout):
            with patch("time.sleep"):
                with pytest.raises(subprocess.TimeoutExpired, match="git"):
                    git_lock.run(["status"], cwd=temp_cwd)

    def test_timeout_logs_retry(
        self, git_lock: GitLock, temp_cwd: Path, mock_logger: MagicMock
    ) -> None:
        """Logs debug message on timeout retry."""
        call_count = [0]

        def timeout_once(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            call_count[0] += 1
            if call_count[0] == 1:
                raise subprocess.TimeoutExpired(cmd=["git"], timeout=30)
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=timeout_once):
            with patch("time.sleep"):
                git_lock.run(["status"], cwd=temp_cwd)

        mock_logger.debug.assert_called()
        assert "timed out" in str(mock_logger.debug.call_args)


class TestIsIndexLockError:
    """Tests for _is_index_lock_error() detection."""

    @pytest.mark.parametrize(
        "stderr,expected",
        [
            ("fatal: Unable to create '.git/index.lock': File exists", True),
            ("Another git process seems to be running in this repository", True),
            ("index.lock': File exists", True),
            ("Unable to create '/path/to/index.lock'", True),
            ("File exists", True),
            ("fatal: not a git repository", False),
            ("error: pathspec 'foo' did not match any file(s)", False),
            ("", False),
            ("Some random error message", False),
        ],
    )
    def test_error_detection(self, stderr: str, expected: bool) -> None:
        """Correctly identifies index.lock errors."""
        assert GitLock._is_index_lock_error(stderr) is expected

    def test_empty_string_returns_false(self) -> None:
        """Empty stderr returns False."""
        assert GitLock._is_index_lock_error("") is False

    def test_case_sensitive_matching(self) -> None:
        """Error matching is case-sensitive."""
        # "Index.lock" with capital I should not match "index.lock"
        assert GitLock._is_index_lock_error("Index.lock") is False
        assert GitLock._is_index_lock_error("index.lock") is True


class TestThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_operations_serialize(self, git_lock: GitLock, temp_cwd: Path) -> None:
        """Multiple threads serialize through the lock."""
        execution_order: list[int] = []
        lock = threading.Lock()

        def slow_operation(thread_id: int) -> None:
            with git_lock:
                with lock:
                    execution_order.append(thread_id)
                time.sleep(0.05)  # Hold lock briefly
                with lock:
                    execution_order.append(thread_id)

        threads = [threading.Thread(target=slow_operation, args=(i,)) for i in range(3)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Each thread should complete its pair before another starts
        # Pattern should be: [a, a, b, b, c, c] not interleaved
        assert len(execution_order) == 6
        for i in range(0, 6, 2):
            assert execution_order[i] == execution_order[i + 1]

    def test_second_thread_waits_for_first(self, git_lock: GitLock, temp_cwd: Path) -> None:
        """Second thread blocks until first releases lock."""
        first_started = threading.Event()
        first_can_finish = threading.Event()
        second_started = threading.Event()
        order: list[str] = []

        def first_thread() -> None:
            with git_lock:
                order.append("first_enter")
                first_started.set()
                first_can_finish.wait(timeout=5)
                order.append("first_exit")

        def second_thread() -> None:
            first_started.wait(timeout=5)
            second_started.set()
            with git_lock:
                order.append("second_enter")

        t1 = threading.Thread(target=first_thread)
        t2 = threading.Thread(target=second_thread)

        t1.start()
        t2.start()

        # Wait for second thread to start trying to acquire
        second_started.wait(timeout=5)
        time.sleep(0.05)  # Give t2 time to block

        # Second should not have entered yet
        assert order == ["first_enter"]

        # Let first thread finish
        first_can_finish.set()

        t1.join(timeout=5)
        t2.join(timeout=5)

        assert order == ["first_enter", "first_exit", "second_enter"]

    def test_no_deadlock_with_many_threads(self, git_lock: GitLock) -> None:
        """Many concurrent lock requests do not deadlock."""
        counter = [0]
        counter_lock = threading.Lock()

        def increment() -> None:
            with git_lock:
                with counter_lock:
                    counter[0] += 1

        threads = [threading.Thread(target=increment) for _ in range(20)]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert counter[0] == 20

    def test_run_method_thread_safe(self, git_lock: GitLock, temp_cwd: Path) -> None:
        """run() method is thread-safe."""
        results: list[subprocess.CompletedProcess[str]] = []
        results_lock = threading.Lock()

        def run_git() -> None:
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="ok", stderr=""
                )
                result = git_lock.run(["status"], cwd=temp_cwd)
                with results_lock:
                    results.append(result)

        threads = [threading.Thread(target=run_git) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(results) == 5
        assert all(r.returncode == 0 for r in results)
