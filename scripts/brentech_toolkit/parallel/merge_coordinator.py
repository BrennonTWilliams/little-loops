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

from brentech_toolkit.parallel.types import (
    MergeRequest,
    MergeStatus,
    ParallelConfig,
    WorkerResult,
)

if TYPE_CHECKING:
    from brentech_toolkit.logger import Logger


class MergeCoordinator:
    """Sequential merge queue with conflict handling.

    Processes merge requests one at a time to avoid conflicts. Supports
    automatic rebase and retry on merge failures.

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

        Args:
            request: Merge request to process
        """
        result = request.worker_result
        self.logger.info(f"Processing merge for {result.issue_id}")

        request.status = MergeStatus.IN_PROGRESS

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
                raise RuntimeError(f"Failed to checkout main: {checkout_result.stderr}")

            # Pull latest changes (ignore result - merge will fail if needed)
            subprocess.run(
                ["git", "pull", "--rebase", "origin", "main"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

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
                # Merge failed - check if conflict
                if "CONFLICT" in merge_result.stdout or "CONFLICT" in merge_result.stderr:
                    self._handle_conflict(request)
                    return
                else:
                    raise RuntimeError(f"Merge failed: {merge_result.stderr}")

            # Merge successful
            self._finalize_merge(request)

        except Exception as e:
            self._handle_failure(request, str(e))

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
