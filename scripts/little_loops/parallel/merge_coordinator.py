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

from little_loops.parallel.git_lock import GitLock
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
        git_lock: GitLock | None = None,
    ) -> None:
        """Initialize the merge coordinator.

        Args:
            config: Parallel processing configuration
            logger: Logger for merge output
            repo_path: Path to the git repository (default: current directory)
            git_lock: Shared lock for git operations (created if not provided)
        """
        self.config = config
        self.logger = logger
        self.repo_path = repo_path or Path.cwd()
        self._git_lock = git_lock or GitLock(logger)
        self._queue: Queue[MergeRequest] = Queue()
        self._thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()
        self._merged: list[str] = []
        self._failed: dict[str, str] = {}
        self._lock = threading.Lock()
        self._stash_active = False  # Track if we have an active stash
        self._consecutive_failures = 0  # Circuit breaker counter
        self._paused = False  # Set when circuit breaker trips
        self._assume_unchanged_active = False  # Track if state file is marked assume-unchanged
        self._stash_pop_failures: dict[str, str] = {}  # issue_id -> failure message
        self._current_issue_id: str | None = (
            None  # Track current issue for stash failure attribution
        )

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
        """Stash any uncommitted tracked changes in the main repo.

        Only stashes tracked file modifications. Untracked files are not stashed
        because git stash pathspec exclusions don't work reliably with -u flag.
        Untracked file conflicts during merge are handled by _handle_untracked_conflict.

        The following are explicitly excluded from stashing:
        1. State file - managed by orchestrator and continuously updated
        2. Lifecycle file moves - issue files being moved to completed/ directory
        3. Files in completed directory - lifecycle-managed files

        These exclusions prevent stash pop conflicts after merge, since the merge
        may change HEAD and create conflicts with stashed rename operations.

        Returns:
            True if changes were stashed, False if working tree was clean
        """
        state_file_path = Path(self.config.state_file)
        state_file_str = str(state_file_path)
        state_file_name = state_file_path.name

        # Check if there are any tracked changes to stash.
        # We only look at tracked files (exclude untracked with grep -v '??')
        # since we can only reliably stash tracked changes.
        status_result = self._git_lock.run(
            ["status", "--porcelain"],
            cwd=self.repo_path,
            timeout=30,
        )

        # Filter to only tracked changes (lines not starting with ??)
        # and exclude orchestrator-managed files to prevent stash pop conflicts
        tracked_changes = []
        files_to_stash = []
        # Note: Don't use .strip() on the full output - it removes leading spaces
        # from the first line which are significant in git status porcelain format
        for line in status_result.stdout.splitlines():
            if not line or line.startswith("??"):
                continue
            # Skip lifecycle file moves (issue files moved to completed/)
            # These are managed by orchestrator and cause stash pop conflicts
            if self._is_lifecycle_file_move(line):
                self.logger.debug(f"Skipping lifecycle file move from stash: {line}")
                continue
            # Extract file path from porcelain format (XY filename or XY -> filename for renames)
            # Format: XY filename  or  XY old -> new (XY is exactly 2 chars + 1 space)
            file_path = line[3:].split(" -> ")[-1].strip()
            if file_path == state_file_str or file_path.endswith(state_file_name):
                continue  # Skip state file - orchestrator manages it independently
            # Skip files in completed directory - these are lifecycle-managed
            if ".issues/completed/" in file_path or file_path.startswith(
                ".issues/completed/"
            ):
                self.logger.debug(
                    f"Skipping completed directory file from stash: {file_path}"
                )
                continue
            tracked_changes.append(line)
            files_to_stash.append(file_path)

        if not files_to_stash:
            return False  # No tracked changes to stash (excluding state file)

        # Log files to be stashed for debugging
        self.logger.debug(f"Tracked files to stash: {tracked_changes[:10]}")

        # Stash only specific files, explicitly excluding the state file.
        # Using explicit file list avoids race conditions where the orchestrator
        # modifies the state file between a checkout and stash-all operation.
        # Note: gitignored files are never stashed anyway.
        stash_result = self._git_lock.run(
            [
                "stash",
                "push",
                "-m",
                "ll-parallel: auto-stash before merge",
                "--",
                *files_to_stash,
            ],
            cwd=self.repo_path,
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

        pop_result = self._git_lock.run(
            ["stash", "pop"],
            cwd=self.repo_path,
            timeout=30,
        )

        if pop_result.returncode != 0:
            self.logger.warning(f"Failed to pop stash: {pop_result.stderr.strip()}")

            # Check if it's a conflict issue - in that case, stash pop may have
            # partially applied. We need to clean up the index but preserve the merge.
            status_result = self._git_lock.run(
                ["status", "--porcelain"],
                cwd=self.repo_path,
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
                self._git_lock.run(
                    ["checkout", "--theirs", "."],
                    cwd=self.repo_path,
                    timeout=30,
                )
                self._git_lock.run(
                    ["reset", "HEAD"],
                    cwd=self.repo_path,
                    timeout=30,
                )
                self.logger.info("Cleaned up conflicted stash pop, merge preserved")

            # Leave the stash intact for manual recovery
            self._stash_active = False

            # Record this failure for reporting in final summary
            if self._current_issue_id:
                with self._lock:
                    self._stash_pop_failures[self._current_issue_id] = (
                        "Local changes could not be restored after merge. "
                        "Run 'git stash list' and 'git stash pop' to recover manually."
                    )

            self.logger.warning(
                "Stash could not be restored - your changes are saved in 'git stash list'. "
                "Run 'git stash show' to view and 'git stash pop' to retry manually."
            )
            return False

        self._stash_active = False
        self.logger.info("Restored stashed local changes")
        return True

    def _mark_state_file_assume_unchanged(self) -> bool:
        """Mark the state file as assume-unchanged to prevent git from seeing modifications.

        This allows git pull --rebase to proceed even when the state file is modified,
        since the orchestrator continuously updates it during processing.

        Returns:
            True if successfully marked, False otherwise
        """
        state_file = str(self.config.state_file)

        # Check if file exists and is tracked
        ls_files = self._git_lock.run(
            ["ls-files", state_file],
            cwd=self.repo_path,
            timeout=10,
        )

        if not ls_files.stdout.strip():
            # File not tracked, nothing to do
            return True

        result = self._git_lock.run(
            ["update-index", "--assume-unchanged", state_file],
            cwd=self.repo_path,
            timeout=10,
        )

        if result.returncode == 0:
            self._assume_unchanged_active = True
            self.logger.debug(f"Marked {state_file} as assume-unchanged")
            return True

        self.logger.warning(f"Failed to mark state file assume-unchanged: {result.stderr}")
        return False

    def _restore_state_file_tracking(self) -> bool:
        """Restore normal tracking for the state file.

        Returns:
            True if successfully restored, False otherwise
        """
        if not self._assume_unchanged_active:
            return True

        state_file = str(self.config.state_file)

        result = self._git_lock.run(
            ["update-index", "--no-assume-unchanged", state_file],
            cwd=self.repo_path,
            timeout=10,
        )

        self._assume_unchanged_active = False

        if result.returncode != 0:
            self.logger.warning(f"Failed to restore state file tracking: {result.stderr}")
            return False

        self.logger.debug(f"Restored tracking for {state_file}")
        return True

    def _is_lifecycle_file_move(self, porcelain_line: str) -> bool:
        """Check if a porcelain status line represents a lifecycle file move.

        Lifecycle file moves are issue files being moved to completed/ directory.
        These are managed by the orchestrator and should not be stashed, as they
        will conflict with the merge when popping.

        Args:
            porcelain_line: A line from `git status --porcelain` output

        Returns:
            True if this is a lifecycle file move that should be excluded from stash
        """
        # Rename entries have format: R  old_path -> new_path
        if not porcelain_line.startswith("R"):
            return False

        # Check if it's a move to completed/ directory
        if " -> " not in porcelain_line:
            return False

        # Extract destination path (after " -> ")
        parts = porcelain_line[3:].split(" -> ")
        if len(parts) != 2:
            return False

        dest_path = parts[1].strip()

        # Check if destination is in .issues/completed/
        return ".issues/completed/" in dest_path or dest_path.startswith(
            ".issues/completed/"
        )

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

    def _is_rebase_in_progress(self) -> bool:
        """Check if a rebase is currently in progress.

        Returns:
            True if rebase is in progress (rebase-merge or rebase-apply exists)
        """
        rebase_merge = self.repo_path / ".git" / "rebase-merge"
        rebase_apply = self.repo_path / ".git" / "rebase-apply"
        return rebase_merge.exists() or rebase_apply.exists()

    def _abort_rebase_if_in_progress(self) -> bool:
        """Abort any in-progress rebase operation.

        Returns:
            True if rebase was aborted or none was in progress,
            False if abort failed
        """
        if not self._is_rebase_in_progress():
            return True

        self.logger.warning("Detected rebase in progress, aborting...")
        abort_result = self._git_lock.run(
            ["rebase", "--abort"],
            cwd=self.repo_path,
            timeout=30,
        )

        if abort_result.returncode != 0:
            self.logger.error(f"Failed to abort rebase: {abort_result.stderr}")
            # Force hard reset as last resort
            return self._attempt_hard_reset()

        self.logger.info("Aborted incomplete rebase from pull")
        return True

    def _is_unmerged_files_error(self, error_output: str) -> bool:
        """Check if the error is due to pre-existing unmerged files.

        Args:
            error_output: The stderr/stdout from the failed git command

        Returns:
            True if the error indicates unmerged files blocking the operation
        """
        indicators = [
            "you have unmerged files",
            "Merging is not possible because you have unmerged files",
            "fix conflicts and then commit the result",
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
            abort_result = self._git_lock.run(
                ["merge", "--abort"],
                cwd=self.repo_path,
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
            abort_result = self._git_lock.run(
                ["rebase", "--abort"],
                cwd=self.repo_path,
                timeout=30,
            )
            if abort_result.returncode != 0:
                self.logger.error(f"Failed to abort rebase: {abort_result.stderr}")
                return False
            self.logger.info("Aborted incomplete rebase")
            # Force reset after rebase abort - the abort can leave index in dirty state
            # This is defensive since unmerged file detection below may not trigger
            if not self._attempt_hard_reset():
                return False

        # Check for unmerged files in the index (UU, AA, DD, AU, UA, DU, UD prefixes)
        # These can persist even after merge --abort in some edge cases
        status_result = self._git_lock.run(
            ["status", "--porcelain"],
            cwd=self.repo_path,
            timeout=30,
        )

        if status_result.returncode != 0:
            self.logger.error(f"git status failed: {status_result.stderr}")
            return self._attempt_hard_reset()

        # Debug logging to diagnose unmerged detection issues
        if status_result.stdout.strip():
            self.logger.debug(f"Git status output: {status_result.stdout[:500]}")

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

        # Final safety check - if MERGE_HEAD still exists, force reset
        # This catches edge cases where abort succeeded but state is still dirty
        if merge_head.exists():
            self.logger.warning("MERGE_HEAD persists after recovery attempts, forcing reset")
            if not self._attempt_hard_reset():
                return False

        return True

    def _attempt_hard_reset(self) -> bool:
        """Attempt a hard reset to recover from index issues.

        Returns:
            True if reset succeeded, False otherwise
        """
        self.logger.warning("Attempting hard reset to recover...")
        reset_result = self._git_lock.run(
            ["reset", "--hard", "HEAD"],
            cwd=self.repo_path,
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
        self._current_issue_id = result.issue_id
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

        # Mark state file as assume-unchanged to prevent pull --rebase conflicts
        # The orchestrator continuously updates the state file during processing
        self._mark_state_file_assume_unchanged()

        # Stash any local changes before merge operations
        had_local_changes = self._stash_local_changes()

        try:
            # Ensure we're on main branch in the main repo
            checkout_result = self._git_lock.run(
                ["checkout", "main"],
                cwd=self.repo_path,
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
                        checkout_result = self._git_lock.run(
                            ["checkout", "main"],
                            cwd=self.repo_path,
                            timeout=30,
                        )
                        if checkout_result.returncode == 0:
                            self.logger.info("Recovered from index error, checkout succeeded")
                        else:
                            raise RuntimeError(
                                f"Failed to checkout main after recovery: {checkout_result.stderr}"
                            )
                    else:
                        raise RuntimeError(f"Failed to checkout main: {checkout_result.stderr}")
                else:
                    raise RuntimeError(f"Failed to checkout main: {checkout_result.stderr}")

            # Pull latest changes
            pull_result = self._git_lock.run(
                ["pull", "--rebase", "origin", "main"],
                cwd=self.repo_path,
                timeout=60,
            )

            # Handle pull failures
            if pull_result.returncode != 0:
                error_output = pull_result.stderr + pull_result.stdout

                # Check if rebase conflicted - must abort before continuing
                if self._is_rebase_in_progress():
                    self.logger.warning(
                        f"Pull --rebase failed with conflicts: {error_output[:200]}"
                    )
                    if not self._abort_rebase_if_in_progress():
                        raise RuntimeError("Failed to recover from rebase conflict during pull")
                    # After aborting rebase, we're back to pre-pull state
                    # Continue without the pull - merge may still work or conflict
                    self.logger.info("Continuing without pull after rebase abort")

                elif self._is_local_changes_error(error_output):
                    self.logger.warning(
                        f"Pull failed due to local changes, attempting re-stash: {error_output[:200]}"
                    )
                    # Re-stash any local changes that appeared during pull
                    if self._stash_local_changes():
                        self.logger.info("Re-stashed local changes after pull conflict")
                        had_local_changes = True
                # For other pull failures, continue - merge will handle or fail

            # Safety check: ensure no unmerged files before merge attempt
            # This catches edge cases where previous operations left dirty state
            if not self._check_and_recover_index():
                raise RuntimeError(
                    "Git index has unresolved conflicts before merge - recovery failed"
                )

            # Attempt merge with no-ff
            merge_result = self._git_lock.run(
                [
                    "merge",
                    result.branch_name,
                    "--no-ff",
                    "-m",
                    f"feat: parallel merge {result.issue_id}\n\n"
                    f"Automated merge from parallel issue processing.",
                ],
                cwd=self.repo_path,
                timeout=60,
            )

            if merge_result.returncode != 0:
                error_output = merge_result.stderr + merge_result.stdout

                # Check for local changes error (shouldn't happen after stash)
                if self._is_local_changes_error(error_output):
                    self.logger.warning(
                        f"Merge blocked by local changes despite stash: {error_output[:200]}"
                    )
                    raise RuntimeError(f"Merge failed due to local changes: {error_output[:200]}")

                # Check for untracked files blocking merge
                if self._is_untracked_files_error(error_output):
                    self._handle_untracked_conflict(request, error_output)
                    return

                # Check for pre-existing unmerged files (dirty index)
                if self._is_unmerged_files_error(error_output):
                    self.logger.warning(
                        f"Merge blocked by unmerged files in index: {error_output[:200]}"
                    )
                    # Attempt recovery and retry once
                    if request.retry_count < 1 and self._check_and_recover_index():
                        request.retry_count += 1
                        self.logger.info("Recovered from unmerged files, retrying merge")
                        self._queue.put(request)
                        return
                    raise RuntimeError(f"Merge failed due to unmerged files: {error_output[:200]}")

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
            # Always restore state file tracking
            self._restore_state_file_tracking()
            # Clear current issue tracking
            self._current_issue_id = None

    def _handle_conflict(self, request: MergeRequest) -> None:
        """Handle a merge conflict with retry logic.

        Args:
            request: The merge request that conflicted
        """
        result = request.worker_result
        request.retry_count += 1

        # Abort the failed merge
        self._git_lock.run(
            ["merge", "--abort"],
            cwd=self.repo_path,
            timeout=10,
        )

        if request.retry_count <= self.config.max_merge_retries:
            # Attempt rebase in the worktree
            self.logger.warning(
                f"Merge conflict for {result.issue_id}, "
                f"attempting rebase (retry {request.retry_count}/{self.config.max_merge_retries})"
            )

            request.status = MergeStatus.RETRYING

            # Check for and stash any unstaged changes in the worktree before rebase
            worktree_status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=result.worktree_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            worktree_has_changes = bool(worktree_status.stdout.strip())

            if worktree_has_changes:
                self.logger.debug(
                    f"Stashing worktree changes before rebase: {worktree_status.stdout[:200]}"
                )
                stash_result = subprocess.run(
                    ["git", "stash", "push", "-m", "ll-parallel: auto-stash before rebase"],
                    cwd=result.worktree_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if stash_result.returncode != 0:
                    self.logger.warning(f"Failed to stash worktree changes: {stash_result.stderr}")

            # Rebase the branch onto current main
            rebase_result = subprocess.run(
                ["git", "rebase", "main"],
                cwd=result.worktree_path,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if rebase_result.returncode == 0:
                # Rebase succeeded, restore stash if we made one, then retry merge
                if worktree_has_changes:
                    subprocess.run(
                        ["git", "stash", "pop"],
                        cwd=result.worktree_path,
                        capture_output=True,
                        timeout=30,
                    )
                self._queue.put(request)
            else:
                # Rebase also failed - abort and restore stash
                subprocess.run(
                    ["git", "rebase", "--abort"],
                    cwd=result.worktree_path,
                    capture_output=True,
                    timeout=10,
                )
                if worktree_has_changes:
                    subprocess.run(
                        ["git", "stash", "pop"],
                        cwd=result.worktree_path,
                        capture_output=True,
                        timeout=30,
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

    def _handle_untracked_conflict(self, request: MergeRequest, error_output: str) -> None:
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
        self._git_lock.run(
            ["worktree", "remove", "--force", str(worktree_path)],
            cwd=self.repo_path,
            timeout=30,
        )

        # Force delete directory if still exists
        if worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)

        # Delete the branch
        if branch_name.startswith("parallel/"):
            self._git_lock.run(
                ["branch", "-D", branch_name],
                cwd=self.repo_path,
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

    @property
    def stash_pop_failures(self) -> dict[str, str]:
        """Mapping of issue IDs to stash pop failure messages.

        These represent issues where the merge succeeded but the user's
        local changes could not be automatically restored and need manual
        recovery via 'git stash pop'.
        """
        with self._lock:
            return dict(self._stash_pop_failures)

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
