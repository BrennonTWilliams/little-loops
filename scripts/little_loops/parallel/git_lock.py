"""Thread-safe git operations with retry logic for parallel processing.

Provides a shared lock for git operations on the main repository to prevent
concurrent operations from conflicting over .git/index.lock.

The index.lock race condition occurs when:
- MergeCoordinator runs stash/merge/pull operations
- WorkerPool captures baseline git status or cleans up leaked files
- Both touch the main repo's git index simultaneously

This module provides:
- A threading lock to serialize git operations on the main repo
- Retry logic with exponential backoff for transient index.lock errors
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.logger import Logger


class GitLock:
    """Thread-safe wrapper for git operations on a repository.

    Serializes all git operations through a single lock to prevent
    index.lock conflicts. Provides automatic retry with exponential
    backoff for transient lock errors.

    Example:
        >>> git_lock = GitLock(logger)
        >>> # Use context manager for custom operations
        >>> with git_lock:
        ...     subprocess.run(["git", "status"], cwd=repo_path)
        >>> # Or use the run method for automatic retry
        >>> result = git_lock.run(["status"], cwd=repo_path)
    """

    def __init__(
        self,
        logger: Logger | None = None,
        max_retries: int = 3,
        initial_backoff: float = 0.5,
        max_backoff: float = 8.0,
    ) -> None:
        """Initialize the git lock.

        Args:
            logger: Optional logger for retry messages
            max_retries: Maximum number of retries on index.lock error
            initial_backoff: Initial backoff delay in seconds
            max_backoff: Maximum backoff delay in seconds
        """
        # RLock allows same thread to acquire lock multiple times
        # (needed for nested git operations within a single method)
        self._lock = threading.RLock()
        self._logger = logger
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff

    def __enter__(self) -> GitLock:
        """Acquire the lock for manual git operations."""
        self._lock.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Release the lock."""
        self._lock.release()

    def run(
        self,
        args: list[str],
        cwd: Path,
        timeout: float = 30,
        capture_output: bool = True,
        text: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command with lock and retry logic.

        Args:
            args: Git command arguments (without 'git' prefix)
            cwd: Working directory for the command
            timeout: Command timeout in seconds
            capture_output: Whether to capture stdout/stderr
            text: Whether to decode output as text

        Returns:
            CompletedProcess with command result
        """
        with self._lock:
            return self._run_with_retry(
                args=args,
                cwd=cwd,
                timeout=timeout,
                capture_output=capture_output,
                text=text,
            )

    def _run_with_retry(
        self,
        args: list[str],
        cwd: Path,
        timeout: float,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        """Run git command with retry on index.lock errors.

        Args:
            args: Git command arguments (without 'git' prefix)
            cwd: Working directory
            timeout: Command timeout
            capture_output: Whether to capture output
            text: Whether to decode as text

        Returns:
            CompletedProcess with result
        """
        cmd = ["git"] + args
        backoff = self.initial_backoff
        last_result: subprocess.CompletedProcess[str] | None = None

        for attempt in range(self.max_retries + 1):
            try:
                result = subprocess.run(
                    cmd,
                    cwd=cwd,
                    timeout=timeout,
                    capture_output=capture_output,
                    text=text,
                )

                # Check for index.lock error
                if result.returncode != 0 and self._is_index_lock_error(result.stderr or ""):
                    last_result = result
                    if attempt < self.max_retries:
                        if self._logger:
                            self._logger.debug(
                                f"Git index.lock conflict, retrying in {backoff:.1f}s "
                                f"(attempt {attempt + 1}/{self.max_retries})"
                            )
                        time.sleep(backoff)
                        backoff = min(backoff * 2, self.max_backoff)
                        continue

                return result

            except subprocess.TimeoutExpired:
                if attempt < self.max_retries:
                    if self._logger:
                        self._logger.debug(
                            f"Git command timed out, retrying in {backoff:.1f}s "
                            f"(attempt {attempt + 1}/{self.max_retries})"
                        )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, self.max_backoff)
                else:
                    raise

        # Return last result if we exhausted retries
        if last_result is not None:
            if self._logger:
                self._logger.warning(
                    f"Git command failed after {self.max_retries} retries: "
                    f"{last_result.stderr[:200] if last_result.stderr else 'unknown error'}"
                )
            return last_result

        # Should not reach here, but provide fallback
        raise RuntimeError(f"Git command failed after {self.max_retries} retries")

    @staticmethod
    def _is_index_lock_error(stderr: str) -> bool:
        """Check if error is due to index.lock conflict.

        Args:
            stderr: Error output from git command

        Returns:
            True if this is an index.lock error that may be retried
        """
        if not stderr:
            return False

        indicators = [
            "index.lock",
            "Unable to create",
            "Another git process seems to be running",
            "File exists",
        ]

        return any(indicator in stderr for indicator in indicators)
