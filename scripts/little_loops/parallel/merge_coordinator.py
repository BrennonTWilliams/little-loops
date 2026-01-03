"""Merge coordinator for sequential integration of parallel worker changes.

Handles merging completed worker branches back to main with conflict detection
and automatic retry capability.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path
from queue import Queue
from typing import TYPE_CHECKING

from little_loops.parallel.types import (
    MergeRequest,
    MergeStatus,
    ParallelConfig,
    WorkerResult,
)

if TYPE_CHECKING:
    from little_loops.logger import Logger


class MergeCoordinator:
    """Sequential merge queue with conflict handling.

    Processes merge requests one at a time to avoid conflicts. Supports
    automatic rebase and retry on merge failures. Handles uncommitted local
    changes by stashing them before merge operations.

    Example:
        >>> coordinator = MergeCoordinator(config, logger, repo_path)
        >>> coordinator.start()
        >>> coordinator.queue_merge(worker_result)
        >>> # ... later ...
        >>> coordinator.shutdown()
    """

    def __init__(
        self,
        config: ParallelConfig,
        logger: Logger,
        repo_path: Path | None = None,
    ) -> None:
        """Initialize the merge coordinator.

        Args:
            config: Parallel processing configuration
            logger: Logger for merge output
            repo_path: Path to the git repository (default: current directory)
        """
        self.config = config
        self.logger = logger
        self.repo_path = repo_path or Path.cwd()
        self._queue: Queue[MergeRequest] = Queue()
        self._thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()
        self._merged: list[str] = []
        self._failed: dict[str, str] = {}
        self._lock = threading.Lock()
        self._stash_active = False  # Track if we have an active stash
        self._consecutive_failures = 0  # Circuit breaker counter
        self._paused = False  # Set when circuit breaker trips

    def start(self) -> None:
        """Start the merge coordinator background thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._shutdown_event.clear()
        self._thread = threading.Thread(
            target=self._merge_loop,
            name="merge-coordinator",
            daemon=True,
        )
        self._thread.start()
        self.logger.info("Merge coordinator started")

    def shutdown(self, wait: bool = True, timeout: float = 30.0) -> None:
        """Shutdown the merge coordinator.

        Args:
            wait: Whether to wait for pending merges to complete
            timeout: Maximum time to wait for shutdown
        """
        if self._thread is None:
            return

        self._shutdown_event.set()

        if wait and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        self._thread = None
        self.logger.info("Merge coordinator stopped")

    def queue_merge(self, worker_result: WorkerResult) -> None:
        """Queue a worker result for merging.

        Args:
            worker_result: Result from a completed worker
        """
        request = MergeRequest(worker_result=worker_result)
        self._queue.put(request)
        self.logger.info(
            f"Queued merge for {worker_result.issue_id} (branch: {worker_result.branch_name})"
        )

    def _stash_local_changes(self) -> bool:
        """Stash any uncommitted local changes in the main repo.

        Excludes the state file from the check since it's constantly updated
        during parallel execution and would cause stash/pop conflicts.

        Returns:
            True if changes were stashed, False if working tree was clean
        """
        # Check if there are any changes to stash, excluding the state file
        # which is constantly updated during execution
        state_file_path = str(self.config.state_file)
        status_result = subprocess.run(
            [
                "git",
                "status",
                "--porcelain",
                "--",
                ".",
                f":(exclude){state_file_path}",
            ],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if not status_result.stdout.strip():
            return False  # Working tree is clean (ignoring state file)

        # Stash the changes (excluding untracked files which includes state file)
        stash_result = subprocess.run(
            ["git", "stash", "push", "-m", "ll-parallel: auto-stash before merge"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if stash_result.returncode == 0:
            self._stash_active = True
            self.logger.debug("Stashed local changes before merge")
            return True

        return False

    def _pop_stash(self) -> bool:
        """Restore stashed changes if any were stashed.

        Returns:
            True if stash was successfully popped or no stash was active,
            False if pop failed and recovery was needed.
        """
        if not self._stash_active:
            return True

        pop_result = subprocess.run(
            ["git", "stash", "pop"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if pop_result.returncode != 0:
            self.logger.warning(
                f"Failed to pop stash: {pop_result.stderr.strip()}"
            )
            # Attempt recovery: reset index to HEAD to clear conflicts
            reset_result = subprocess.run(
                ["git", "reset", "--hard", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if reset_result.returncode == 0:
                self.logger.info("Reset git index after stash pop failure")
                # Stash is still in the stash list, drop it since we reset
                subprocess.run(
                    ["git", "stash", "drop"],
                    cwd=self.repo_path,
                    capture_output=True,
                    timeout=10,
                )
                self._stash_active = False
                self.logger.warning(
                    "Dropped stash after reset - local changes were lost, please re-apply manually"
                )
            else:
                self.logger.error(
                    f"Failed to reset git index: {reset_result.stderr.strip()}. "
                    "Manual recovery required: run 'git reset --hard HEAD' and 'git stash drop'"
                )
                # Mark as inactive to avoid infinite loops, but index may still be broken
                self._stash_active = False
            return False

        self._stash_active = False
        self.logger.debug("Restored stashed local changes")
        return True

    def _is_local_changes_error(self, error_output: str) -> bool:
        """Check if the error is due to uncommitted local changes.

        Args:
            error_output: The stderr/stdout from the failed git command

        Returns:
            True if the error indicates local changes would be overwritten
        """
        indicators = [
            "Your local changes to the following files would be overwritten",
            "Please commit your changes or stash them before you merge",
            "error: cannot pull with rebase: You have unstaged changes",
        ]
        return any(indicator in error_output for indicator in indicators)

    def _is_index_error(self, error_output: str) -> bool:
        """Check if the error is due to a corrupted git index.

        Args:
            error_output: The stderr/stdout from the failed git command

        Returns:
            True if the error indicates index problems
        """
        indicators = [
            "you need to resolve your current index first",
            "fatal: cannot do a partial commit during a merge",
            "error: you have not concluded your merge",
        ]
        return any(indicator in error_output for indicator in indicators)

    def _check_and_recover_index(self) -> bool:
        """Check git index health and attempt recovery if needed.

        Returns:
            True if index is healthy or was recovered, False if unrecoverable
        """
        # Check if we're in the middle of a merge
        merge_head = self.repo_path / ".git" / "MERGE_HEAD"
        if merge_head.exists():
            self.logger.warning("Detected incomplete merge, aborting...")
            abort_result = subprocess.run(
                ["git", "merge", "--abort"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if abort_result.returncode != 0:
                self.logger.error(f"Failed to abort merge: {abort_result.stderr}")
                return False
            self.logger.info("Aborted incomplete merge")

        # Check if we're in the middle of a rebase
        rebase_dir = self.repo_path / ".git" / "rebase-merge"
        rebase_apply = self.repo_path / ".git" / "rebase-apply"
        if rebase_dir.exists() or rebase_apply.exists():
            self.logger.warning("Detected incomplete rebase, aborting...")
            abort_result = subprocess.run(
                ["git", "rebase", "--abort"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if abort_result.returncode != 0:
                self.logger.error(f"Failed to abort rebase: {abort_result.stderr}")
                return False
            self.logger.info("Aborted incomplete rebase")

        # Verify index is clean
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if status_result.returncode != 0:
            self.logger.error(f"git status failed: {status_result.stderr}")
            # Try hard reset as last resort
            self.logger.warning("Attempting hard reset to recover...")
            reset_result = subprocess.run(
                ["git", "reset", "--hard", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if reset_result.returncode != 0:
                self.logger.error("Hard reset failed - manual intervention required")
                return False
            self.logger.info("Hard reset successful")

        return True

    def _merge_loop(self) -> None:
        """Background thread loop for processing merge requests."""
        while not self._shutdown_event.is_set():
            try:
                # Wait for next merge request with timeout
                try:
                    request = self._queue.get(timeout=1.0)
                except Exception:
                    continue

                # Process the merge
                self._process_merge(request)

            except Exception as e:
                self.logger.error(f"Merge loop error: {e}")
                time.sleep(1.0)

    def _process_merge(self, request: MergeRequest) -> None:
        """Process a single merge request.

        Stashes any uncommitted local changes before attempting the merge,
        and restores them afterward (regardless of success/failure).

        Args:
            request: Merge request to process
        """
        result = request.worker_result
        self.logger.info(f"Processing merge for {result.issue_id}")

        # Circuit breaker check
        if self._paused:
            self.logger.warning(
                f"Merge coordinator paused due to repeated failures. "
                f"Skipping {result.issue_id}. Manual intervention required."
            )
            self._handle_failure(request, "Merge coordinator paused - circuit breaker tripped")
            return

        request.status = MergeStatus.IN_PROGRESS

        # Health check: ensure git index is clean before proceeding
        if not self._check_and_recover_index():
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                self._paused = True
                self.logger.error(
                    f"Circuit breaker tripped after {self._consecutive_failures} consecutive failures. "
                    "Merge coordinator paused. Manual recovery required."
                )
            self._handle_failure(request, "Git index recovery failed")
            return

        # Stash any local changes before merge operations
        had_local_changes = self._stash_local_changes()

        try:
            # Ensure we're on main branch in the main repo
            checkout_result = subprocess.run(
                ["git", "checkout", "main"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if checkout_result.returncode != 0:
                error_output = checkout_result.stderr + checkout_result.stdout
                if self._is_local_changes_error(error_output):
                    # This shouldn't happen since we stashed, but handle it anyway
                    self.logger.warning(
                        "Checkout failed due to local changes despite stash attempt"
                    )
                if self._is_index_error(error_output):
                    # Try recovery
                    if self._check_and_recover_index():
                        # Retry checkout
                        checkout_result = subprocess.run(
                            ["git", "checkout", "main"],
                            cwd=self.repo_path,
                            capture_output=True,
                            text=True,
                            timeout=30,
                        )
                        if checkout_result.returncode == 0:
                            self.logger.info("Recovered from index error, checkout succeeded")
                        else:
                            raise RuntimeError(f"Failed to checkout main after recovery: {checkout_result.stderr}")
                    else:
                        raise RuntimeError(f"Failed to checkout main: {checkout_result.stderr}")
                else:
                    raise RuntimeError(f"Failed to checkout main: {checkout_result.stderr}")

            # Pull latest changes
            pull_result = subprocess.run(
                ["git", "pull", "--rebase", "origin", "main"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Check if pull failed due to local changes (edge case)
            if pull_result.returncode != 0:
                error_output = pull_result.stderr + pull_result.stdout
                if self._is_local_changes_error(error_output):
                    self.logger.warning(
                        f"Pull failed due to local changes: {error_output[:200]}"
                    )
                # Continue anyway - merge will fail if there's a real issue

            # Attempt merge with no-ff
            merge_result = subprocess.run(
                [
                    "git",
                    "merge",
                    result.branch_name,
                    "--no-ff",
                    "-m",
                    f"feat: parallel merge {result.issue_id}\n\n"
                    f"Automated merge from parallel issue processing.",
                ],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if merge_result.returncode != 0:
                error_output = merge_result.stderr + merge_result.stdout

                # Check for local changes error (shouldn't happen after stash)
                if self._is_local_changes_error(error_output):
                    self.logger.warning(
                        f"Merge blocked by local changes despite stash: {error_output[:200]}"
                    )
                    raise RuntimeError(
                        f"Merge failed due to local changes: {error_output[:200]}"
                    )

                # Check for merge conflict
                if "CONFLICT" in error_output:
                    self._handle_conflict(request)
                    return
                else:
                    raise RuntimeError(f"Merge failed: {merge_result.stderr}")

            # Merge successful
            self._finalize_merge(request)

        except Exception as e:
            self._handle_failure(request, str(e))

        finally:
            # Always restore stashed changes
            if had_local_changes:
                self._pop_stash()

    def _handle_conflict(self, request: MergeRequest) -> None:
        """Handle a merge conflict with retry logic.

        Args:
            request: The merge request that conflicted
        """
        result = request.worker_result
        request.retry_count += 1

        # Abort the failed merge
        subprocess.run(
            ["git", "merge", "--abort"],
            cwd=self.repo_path,
            capture_output=True,
            timeout=10,
        )

        if request.retry_count <= self.config.max_merge_retries:
            # Attempt rebase in the worktree
            self.logger.warning(
                f"Merge conflict for {result.issue_id}, "
                f"attempting rebase (retry {request.retry_count}/{self.config.max_merge_retries})"
            )

            request.status = MergeStatus.RETRYING

            # Rebase the branch onto current main
            rebase_result = subprocess.run(
                ["git", "rebase", "main"],
                cwd=result.worktree_path,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if rebase_result.returncode == 0:
                # Rebase succeeded, retry merge
                self._queue.put(request)
            else:
                # Rebase also failed
                subprocess.run(
                    ["git", "rebase", "--abort"],
                    cwd=result.worktree_path,
                    capture_output=True,
                    timeout=10,
                )
                self._handle_failure(
                    request,
                    f"Rebase failed after merge conflict: {rebase_result.stderr}",
                )
        else:
            self._handle_failure(
                request,
                f"Merge conflict after {request.retry_count} retries",
            )

    def _finalize_merge(self, request: MergeRequest) -> None:
        """Finalize a successful merge.

        Args:
            request: The completed merge request
        """
        result = request.worker_result
        request.status = MergeStatus.SUCCESS

        # Reset circuit breaker on success
        self._consecutive_failures = 0

        with self._lock:
            self._merged.append(result.issue_id)

        # Cleanup worktree and branch
        self._cleanup_worktree(result.worktree_path, result.branch_name)

        self.logger.success(f"Merged {result.issue_id} successfully")

    def _handle_failure(self, request: MergeRequest, error: str) -> None:
        """Handle a merge failure.

        Args:
            request: The failed merge request
            error: Error message describing the failure
        """
        result = request.worker_result
        request.status = MergeStatus.FAILED
        request.error = error

        with self._lock:
            self._failed[result.issue_id] = error

        self.logger.error(f"Merge failed for {result.issue_id}: {error}")

    def _cleanup_worktree(self, worktree_path: Path, branch_name: str) -> None:
        """Clean up a merged worktree and its branch.

        Args:
            worktree_path: Path to the worktree
            branch_name: Name of the branch to delete
        """
        if not worktree_path.exists():
            return

        # Remove worktree
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=self.repo_path,
            capture_output=True,
            timeout=30,
        )

        # Force delete directory if still exists
        if worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)

        # Delete the branch
        if branch_name.startswith("parallel/"):
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=self.repo_path,
                capture_output=True,
                timeout=10,
            )

    @property
    def merged_ids(self) -> list[str]:
        """List of successfully merged issue IDs."""
        with self._lock:
            return list(self._merged)

    @property
    def failed_merges(self) -> dict[str, str]:
        """Mapping of failed issue IDs to error messages."""
        with self._lock:
            return dict(self._failed)

    @property
    def pending_count(self) -> int:
        """Number of pending merge requests."""
        return self._queue.qsize()

    def wait_for_completion(self, timeout: float | None = None) -> bool:
        """Wait for all pending merges to complete.

        Args:
            timeout: Maximum time to wait (None = forever)

        Returns:
            True if all merges completed, False if timeout
        """
        start_time = time.time()
        while not self._queue.empty():
            if timeout and (time.time() - start_time) > timeout:
                return False
            time.sleep(0.5)
        return True
