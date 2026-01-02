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

        Returns:
            True if changes were stashed, False if working tree was clean
        """
        # Check if there are any changes to stash
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if not status_result.stdout.strip():
            return False  # Working tree is clean

        # Stash the changes
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

    def _pop_stash(self) -> None:
        """Restore stashed changes if any were stashed."""
        if not self._stash_active:
            return

        pop_result = subprocess.run(
            ["git", "stash", "pop"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self._stash_active = False

        if pop_result.returncode != 0:
            self.logger.warning(
                f"Failed to pop stash (may need manual recovery): {pop_result.stderr}"
            )
        else:
            self.logger.debug("Restored stashed local changes")

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

        request.status = MergeStatus.IN_PROGRESS

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
