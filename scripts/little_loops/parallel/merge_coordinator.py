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

        Includes untracked files (except the state file) to prevent merge
        conflicts with newly created files from other workers.

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

        # Log files to be stashed for debugging
        self.logger.debug(f"Files to stash: {status_result.stdout.strip()[:500]}")

        # Stash the changes including untracked files (-u) to prevent
        # "untracked working tree files would be overwritten" errors.
        # Use pathspec to exclude the state file from the stash.
        stash_result = subprocess.run(
            [
                "git",
                "stash",
                "push",
                "-u",  # Include untracked files
                "-m",
                "ll-parallel: auto-stash before merge",
                "--",
                ".",
                f":(exclude){state_file_path}",
            ],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if stash_result.returncode == 0:
            self._stash_active = True
            self.logger.info("Stashed local changes before merge")
            return True

        self.logger.error(f"Failed to stash local changes: {stash_result.stderr}")
        return False

    def _pop_stash(self) -> bool:
        """Restore stashed changes if any were stashed.

        Important: This method preserves the merge even if stash pop fails.
        We never reset --hard HEAD here because that would undo a successful merge.

        Returns:
            True if stash was successfully popped or no stash was active,
            False if pop failed (stash is left for manual recovery).
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

            # Check if it's a conflict issue - in that case, stash pop may have
            # partially applied. We need to clean up the index but preserve the merge.
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Check for unmerged entries from the stash pop attempt
            unmerged_prefixes = ("UU", "AA", "DD", "AU", "UA", "DU", "UD")
            has_unmerged = any(
                line[:2] in unmerged_prefixes
                for line in status_result.stdout.splitlines()
                if len(line) >= 2
            )

            if has_unmerged:
                # Clean up the conflicted stash pop without affecting the merge
                # Use checkout to restore conflicted files to their post-merge state
                subprocess.run(
                    ["git", "checkout", "--theirs", "."],
                    cwd=self.repo_path,
                    capture_output=True,
                    timeout=30,
                )
                subprocess.run(
                    ["git", "reset", "HEAD"],
                    cwd=self.repo_path,
                    capture_output=True,
                    timeout=30,
                )
                self.logger.info("Cleaned up conflicted stash pop, merge preserved")

            # Leave the stash intact for manual recovery
            self._stash_active = False
            self.logger.warning(
                "Stash could not be restored - your changes are saved in 'git stash list'. "
                "Run 'git stash show' to view and 'git stash pop' to retry manually."
            )
            return False

        self._stash_active = False
        self.logger.info("Restored stashed local changes")
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

    def _is_untracked_files_error(self, error_output: str) -> bool:
        """Check if the error is due to untracked files blocking merge.

        Args:
            error_output: The stderr/stdout from the failed git command

        Returns:
            True if the error indicates untracked files would be overwritten
        """
        indicators = [
            "untracked working tree files would be overwritten by merge",
            "Please move or remove them before you merge",
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

        # Check for unmerged files in the index (UU, AA, DD, AU, UA, DU, UD prefixes)
        # These can persist even after merge --abort in some edge cases
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if status_result.returncode != 0:
            self.logger.error(f"git status failed: {status_result.stderr}")
            return self._attempt_hard_reset()

        # Check for unmerged entries (first two chars indicate index/worktree status)
        # Unmerged states: UU (both modified), AA (both added), DD (both deleted),
        # AU/UA (added by us/them), DU/UD (deleted by us/them)
        unmerged_prefixes = ("UU", "AA", "DD", "AU", "UA", "DU", "UD")
        has_unmerged = any(
            line[:2] in unmerged_prefixes
            for line in status_result.stdout.splitlines()
            if len(line) >= 2
        )

        if has_unmerged:
            self.logger.warning("Detected unmerged files in index, resetting...")
            if not self._attempt_hard_reset():
                return False
            self.logger.info("Cleared unmerged files from index")

        return True

    def _attempt_hard_reset(self) -> bool:
        """Attempt a hard reset to recover from index issues.

        Returns:
            True if reset succeeded, False otherwise
        """
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
                        f"Pull failed due to local changes, attempting re-stash: {error_output[:200]}"
                    )
                    # Re-stash any local changes that appeared during pull
                    if self._stash_local_changes():
                        self.logger.info("Re-stashed local changes after pull conflict")
                        had_local_changes = True
                # Continue - merge will fail if there's still an issue

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

                # Check for untracked files blocking merge
                if self._is_untracked_files_error(error_output):
                    self._handle_untracked_conflict(request, error_output)
                    return

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

    def _handle_untracked_conflict(
        self, request: MergeRequest, error_output: str
    ) -> None:
        """Handle untracked files that would be overwritten by merge.

        Backs up conflicting untracked files and retries the merge.

        Args:
            request: The merge request that failed
            error_output: Git error message containing file list
        """
        result = request.worker_result
        request.retry_count += 1

        if request.retry_count > self.config.max_merge_retries:
            self._handle_failure(
                request,
                f"Untracked file conflict after {request.retry_count} retries",
            )
            return

        # Parse conflicting files from error message
        # Format: "error: The following untracked working tree files would be overwritten..."
        # followed by file paths, then "Please move or remove them..."
        conflicting_files = []
        in_file_list = False
        for line in error_output.splitlines():
            line = line.strip()
            if "untracked working tree files would be overwritten" in line:
                in_file_list = True
                continue
            if "Please move or remove them" in line:
                in_file_list = False
                continue
            if in_file_list and line and not line.startswith("error:"):
                conflicting_files.append(line)

        if not conflicting_files:
            self._handle_failure(
                request,
                f"Could not parse conflicting files from: {error_output[:200]}",
            )
            return

        # Create backup directory
        backup_dir = self.repo_path / ".ll-backup" / result.issue_id
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Move conflicting files to backup
        moved_files = []
        for file_path in conflicting_files:
            src = self.repo_path / file_path
            if src.exists():
                dst = backup_dir / file_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                moved_files.append(file_path)

        if moved_files:
            self.logger.info(
                f"Backed up {len(moved_files)} conflicting untracked file(s) to {backup_dir}"
            )

        # Retry the merge
        self.logger.warning(
            f"Untracked files conflict for {result.issue_id}, "
            f"retrying after backup (attempt {request.retry_count}/{self.config.max_merge_retries})"
        )
        request.status = MergeStatus.RETRYING
        self._queue.put(request)

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
