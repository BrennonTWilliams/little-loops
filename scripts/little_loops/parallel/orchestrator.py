"""Main orchestrator for parallel issue processing.

Coordinates the priority queue, worker pool, and merge coordinator to process
multiple issues concurrently.
"""

from __future__ import annotations

import json
import re
import shutil
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.issue_parser import IssueInfo
from little_loops.logger import Logger, format_duration
from little_loops.parallel.git_lock import GitLock
from little_loops.parallel.merge_coordinator import MergeCoordinator
from little_loops.parallel.priority_queue import IssuePriorityQueue
from little_loops.parallel.types import (
    OrchestratorState,
    ParallelConfig,
    PendingWorktreeInfo,
    WorkerResult,
)
from little_loops.parallel.worker_pool import WorkerPool

if TYPE_CHECKING:
    from little_loops.config import BRConfig


class ParallelOrchestrator:
    """Main controller for parallel issue processing.

    Coordinates:
    - Issue scanning and prioritization
    - Worker dispatch (P0 sequential, P1-P5 parallel)
    - Merge coordination
    - State persistence for resume capability
    - Graceful shutdown on signals

    Example:
        >>> from little_loops.config import BRConfig
        >>> from little_loops.parallel import ParallelConfig, ParallelOrchestrator
        >>> br_config = BRConfig(Path.cwd())
        >>> parallel_config = ParallelConfig(max_workers=2)
        >>> orchestrator = ParallelOrchestrator(parallel_config, br_config)
        >>> exit_code = orchestrator.run()
    """

    def __init__(
        self,
        parallel_config: ParallelConfig,
        br_config: BRConfig,
        repo_path: Path | None = None,
        verbose: bool = True,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            parallel_config: Parallel processing configuration
            br_config: Project configuration
            repo_path: Path to the git repository (default: current directory)
            verbose: Whether to output progress messages
        """
        self.parallel_config = parallel_config
        self.br_config = br_config
        self.repo_path = repo_path or Path.cwd()
        self.logger = Logger(verbose=verbose)

        # Create shared git lock for serializing main repo operations
        # This prevents index.lock race conditions between workers and merge coordinator
        self._git_lock = GitLock(self.logger)

        # Initialize components with shared git lock
        self.queue = IssuePriorityQueue()
        self.worker_pool = WorkerPool(
            parallel_config, br_config, self.logger, self.repo_path, self._git_lock
        )
        self.merge_coordinator = MergeCoordinator(
            parallel_config, self.logger, self.repo_path, self._git_lock
        )

        # State management
        self.state = OrchestratorState()
        self._shutdown_requested = False
        self._original_sigint: Any = None
        self._original_sigterm: Any = None

        # Track issue info for lifecycle completion after merge
        self._issue_info_by_id: dict[str, IssueInfo] = {}
        # Track interrupted issues separately from failures (ENH-036)
        self._interrupted_issues: list[str] = []

    def run(self) -> int:
        """Run the parallel issue processor.

        Returns:
            Exit code (0 = success, 1 = failure)
        """
        try:
            self._setup_signal_handlers()
            self._ensure_gitignore_entries()

            # Check for pending work from previous runs (unless clean start)
            if not self.parallel_config.clean_start:
                pending_worktrees = self._check_pending_worktrees()

                # Handle pending worktrees based on flags
                pending_with_work = [p for p in pending_worktrees if p.has_pending_work]
                if pending_with_work:
                    if self.parallel_config.merge_pending:
                        self._merge_pending_worktrees(pending_worktrees)
                    elif not self.parallel_config.ignore_pending:
                        # Default behavior: just report (cleanup happens below)
                        self.logger.info(
                            "Continuing with cleanup (use --merge-pending to merge)..."
                        )

            self._cleanup_orphaned_worktrees()
            self._load_state()

            if self.parallel_config.dry_run:
                return self._dry_run()

            return self._execute()

        except KeyboardInterrupt:
            self.logger.warning("Interrupted by user")
            return 1
        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            return 1
        finally:
            self._cleanup()
            self._restore_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        self._original_sigint = signal.signal(signal.SIGINT, self._signal_handler)
        self._original_sigterm = signal.signal(signal.SIGTERM, self._signal_handler)

    def _restore_signal_handlers(self) -> None:
        """Restore original signal handlers."""
        if self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)
        if self._original_sigterm is not None:
            signal.signal(signal.SIGTERM, self._original_sigterm)

    def _ensure_gitignore_entries(self) -> None:
        """Ensure .gitignore has entries for parallel processing artifacts.

        Adds entries for:
        - .parallel-manage-state.json (state file)
        - .worktrees/ (git worktree directory)

        This prevents these files from being tracked by git, which would cause
        conflicts during merge operations (state file is continuously updated).
        """
        gitignore_path = self.repo_path / ".gitignore"
        required_entries = [
            ".parallel-manage-state.json",
            ".worktrees/",
        ]

        existing_content = ""
        if gitignore_path.exists():
            existing_content = gitignore_path.read_text()

        # Check which entries are missing
        missing_entries = []
        for entry in required_entries:
            # Check for exact match or pattern that would cover it
            if entry not in existing_content:
                missing_entries.append(entry)

        if not missing_entries:
            return

        # Append missing entries
        addition = "\n# ll-parallel artifacts\n"
        for entry in missing_entries:
            addition += f"{entry}\n"

        # Ensure file ends with newline before adding
        if existing_content and not existing_content.endswith("\n"):
            addition = "\n" + addition

        gitignore_path.write_text(existing_content + addition)
        self.logger.info(f"Added {len(missing_entries)} entries to .gitignore")

    def _cleanup_orphaned_worktrees(self) -> None:
        """Clean up worktrees from previous interrupted runs.

        Scans the worktree base directory and removes any worktrees that are
        not from the current session. This handles cases where a previous run
        was interrupted (Ctrl+C) and worktrees were not cleaned up.
        """
        worktree_base = self.repo_path / self.parallel_config.worktree_base
        if not worktree_base.exists():
            return

        # Get list of worktree directories
        orphaned = []
        for item in worktree_base.iterdir():
            if item.is_dir() and item.name.startswith("worker-"):
                orphaned.append(item)

        if not orphaned:
            return

        self.logger.info(f"Cleaning up {len(orphaned)} orphaned worktree(s) from previous run")

        for worktree_path in orphaned:
            try:
                # Try git worktree remove first
                self._git_lock.run(
                    ["worktree", "remove", "--force", str(worktree_path)],
                    cwd=self.repo_path,
                    timeout=30,
                )

                # If git worktree remove failed, force delete the directory
                if worktree_path.exists():
                    shutil.rmtree(worktree_path, ignore_errors=True)

                # Try to delete the associated branch
                # Branch name format: parallel/<issue-id>-<timestamp>
                branch_name = worktree_path.name.replace("worker-", "parallel/")
                self._git_lock.run(
                    ["branch", "-D", branch_name],
                    cwd=self.repo_path,
                    timeout=10,
                )
            except Exception as e:
                self.logger.warning(f"Failed to clean up {worktree_path.name}: {e}")

        # Also prune git worktree references
        self._git_lock.run(
            ["worktree", "prune"],
            cwd=self.repo_path,
            timeout=30,
        )

    def _inspect_worktree(self, worktree_path: Path) -> PendingWorktreeInfo | None:
        """Inspect a worktree to determine its status.

        Args:
            worktree_path: Path to the worktree directory

        Returns:
            PendingWorktreeInfo if inspection succeeded, None if failed
        """
        try:
            # Extract branch name from worktree path
            # worker-bug-045-20260117-143022 -> parallel/bug-045-20260117-143022
            branch_name = worktree_path.name.replace("worker-", "parallel/")

            # Extract issue ID (e.g., bug-045 -> BUG-045)
            # Pattern: worker-<issue-id>-<timestamp>
            match = re.match(r"worker-([a-z]+-\d+)-\d{8}-\d{6}", worktree_path.name)
            issue_id = match.group(1).upper() if match else worktree_path.name

            # Check commits ahead of main
            result = self._git_lock.run(
                ["rev-list", "--count", f"main..{branch_name}"],
                cwd=self.repo_path,
                timeout=10,
            )
            commits_ahead = int(result.stdout.strip()) if result.returncode == 0 else 0

            # Check for uncommitted changes in worktree
            result = self._git_lock.run(
                ["status", "--porcelain"],
                cwd=worktree_path,
                timeout=10,
            )
            changed_files = []
            has_uncommitted = False
            if result.returncode == 0 and result.stdout.strip():
                has_uncommitted = True
                changed_files = [line[3:] for line in result.stdout.strip().split("\n") if line]

            return PendingWorktreeInfo(
                worktree_path=worktree_path,
                branch_name=branch_name,
                issue_id=issue_id,
                commits_ahead=commits_ahead,
                has_uncommitted_changes=has_uncommitted,
                changed_files=changed_files,
            )
        except Exception as e:
            self.logger.warning(f"Failed to inspect worktree {worktree_path.name}: {e}")
            return None

    def _check_pending_worktrees(self) -> list[PendingWorktreeInfo]:
        """Check for pending worktrees from previous runs and report status.

        Returns:
            List of pending worktree information
        """
        worktree_base = self.repo_path / self.parallel_config.worktree_base
        if not worktree_base.exists():
            return []

        # Find all worker directories
        worktrees = [
            item
            for item in worktree_base.iterdir()
            if item.is_dir() and item.name.startswith("worker-")
        ]

        if not worktrees:
            return []

        self.logger.info("Checking for pending work from previous runs...")

        # Inspect each worktree
        pending_info: list[PendingWorktreeInfo] = []
        for worktree_path in worktrees:
            info = self._inspect_worktree(worktree_path)
            if info:
                pending_info.append(info)

        # Report findings
        with_work = [p for p in pending_info if p.has_pending_work]
        if with_work:
            self.logger.warning(f"Found {len(with_work)} worktree(s) with pending work:")
            for info in with_work:
                status_parts = []
                if info.commits_ahead > 0:
                    status_parts.append(f"{info.commits_ahead} commit(s) ahead of main")
                if info.has_uncommitted_changes:
                    status_parts.append(f"{len(info.changed_files)} uncommitted file(s)")
                status = ", ".join(status_parts)
                self.logger.warning(f"  - {info.worktree_path.name}: {info.issue_id} ({status})")

            self.logger.info("")
            self.logger.info("Options:")
            self.logger.info("  --merge-pending   Attempt to merge pending work before continuing")
            self.logger.info("  --clean-start     Remove all worktrees and start fresh")
            self.logger.info(
                "  --ignore-pending  Continue without action (worktrees will be cleaned up)"
            )
        elif pending_info:
            self.logger.info(f"Found {len(pending_info)} orphaned worktree(s) with no pending work")

        return pending_info

    def _merge_pending_worktrees(self, pending: list[PendingWorktreeInfo]) -> None:
        """Attempt to merge pending worktrees from previous runs.

        Args:
            pending: List of pending worktree information
        """
        with_work = [p for p in pending if p.has_pending_work]
        if not with_work:
            return

        self.logger.info(f"Attempting to merge {len(with_work)} pending worktree(s)...")

        for info in with_work:
            try:
                # If there are uncommitted changes, commit them first
                if info.has_uncommitted_changes:
                    self.logger.info(f"  Committing uncommitted changes in {info.issue_id}...")
                    self._git_lock.run(
                        ["add", "-A"],
                        cwd=info.worktree_path,
                        timeout=30,
                    )
                    self._git_lock.run(
                        [
                            "commit",
                            "-m",
                            f"WIP: Auto-commit from interrupted session for {info.issue_id}",
                        ],
                        cwd=info.worktree_path,
                        timeout=30,
                    )

                # Attempt merge
                self.logger.info(f"  Merging {info.issue_id} ({info.branch_name})...")
                result = self._git_lock.run(
                    [
                        "merge",
                        "--no-ff",
                        info.branch_name,
                        "-m",
                        f"Merge pending work for {info.issue_id}",
                    ],
                    cwd=self.repo_path,
                    timeout=60,
                )

                if result.returncode == 0:
                    self.logger.success(f"  Successfully merged {info.issue_id}")
                    # Clean up the worktree after successful merge
                    self._git_lock.run(
                        ["worktree", "remove", "--force", str(info.worktree_path)],
                        cwd=self.repo_path,
                        timeout=30,
                    )
                    self._git_lock.run(
                        ["branch", "-D", info.branch_name],
                        cwd=self.repo_path,
                        timeout=10,
                    )
                else:
                    self.logger.warning(f"  Failed to merge {info.issue_id}: {result.stderr}")
                    # Abort the merge if it failed
                    self._git_lock.run(
                        ["merge", "--abort"],
                        cwd=self.repo_path,
                        timeout=10,
                    )

            except Exception as e:
                self.logger.warning(f"  Error merging {info.issue_id}: {e}")

    def _signal_handler(self, signum: int, frame: object) -> None:
        """Handle shutdown signals gracefully."""
        self._shutdown_requested = True
        # Propagate to worker pool for interrupted worker detection (ENH-036)
        self.worker_pool.set_shutdown_requested(True)
        self.logger.warning(f"Received signal {signum}, shutting down gracefully...")

    def _load_state(self) -> None:
        """Load state from file for resume capability."""
        state_file = self.repo_path / self.parallel_config.state_file
        if not state_file.exists():
            self.state.started_at = datetime.now().isoformat()
            return

        try:
            data = json.loads(state_file.read_text())
            self.state = OrchestratorState.from_dict(data)

            # Restore queue state
            self.queue.load_completed(self.state.completed_issues)
            self.queue.load_failed(self.state.failed_issues.keys())

            self.logger.info(
                f"Resumed from previous state: "
                f"{len(self.state.completed_issues)} completed, "
                f"{len(self.state.failed_issues)} failed"
            )
        except Exception as e:
            self.logger.warning(f"Could not load state: {e}")
            self.state.started_at = datetime.now().isoformat()

    def _save_state(self) -> None:
        """Save current state to file."""
        self.state.last_checkpoint = datetime.now().isoformat()
        self.state.completed_issues = self.queue.completed_ids
        self.state.failed_issues = dict.fromkeys(self.queue.failed_ids, "Failed")
        self.state.in_progress_issues = self.queue.in_progress_ids

        state_file = self.repo_path / self.parallel_config.state_file
        state_file.write_text(json.dumps(self.state.to_dict(), indent=2))

    def _cleanup_state(self) -> None:
        """Remove state file on successful completion."""
        state_file = self.repo_path / self.parallel_config.state_file
        if state_file.exists():
            state_file.unlink()

    def _dry_run(self) -> int:
        """Preview what would be processed without executing.

        Returns:
            Exit code (always 0 for dry run)
        """
        issues = self._scan_issues()

        self.logger.info("=" * 60)
        self.logger.info("DRY RUN - No changes will be made")
        self.logger.info("=" * 60)
        self.logger.info("")

        if not issues:
            self.logger.info("No issues found matching criteria")
            return 0

        self.logger.info(f"Found {len(issues)} issues to process:")
        self.logger.info("")

        # Group by priority
        by_priority: dict[str, list[IssueInfo]] = {}
        for issue in issues:
            by_priority.setdefault(issue.priority, []).append(issue)

        for priority in IssuePriorityQueue.DEFAULT_PRIORITIES:
            if priority not in by_priority:
                continue

            priority_issues = by_priority[priority]
            self.logger.info(f"  {priority} ({len(priority_issues)} issues):")
            for issue in priority_issues:
                mode = (
                    "sequential"
                    if priority == "P0" and self.parallel_config.p0_sequential
                    else "parallel"
                )
                self.logger.info(f"    - {issue.issue_id}: {issue.title} [{mode}]")

        self.logger.info("")
        self.logger.info("Configuration:")
        self.logger.info(f"  Workers: {self.parallel_config.max_workers}")
        self.logger.info(f"  P0 Sequential: {self.parallel_config.p0_sequential}")
        self.logger.info(f"  Max Issues: {self.parallel_config.max_issues or 'unlimited'}")
        self.logger.info(f"  Command Prefix: {self.parallel_config.command_prefix}")

        return 0

    def _execute(self) -> int:
        """Execute parallel issue processing.

        Returns:
            Exit code (0 = success, 1 = failure)
        """
        start_time = time.time()

        # Scan and queue issues
        issues = self._scan_issues()
        if not issues:
            self.logger.info("No issues to process")
            return 0

        # Store issue info for lifecycle completion after merge
        for issue in issues:
            self._issue_info_by_id[issue.issue_id] = issue

        added = self.queue.add_many(issues)
        self.logger.info(f"Queued {added} issues for processing")

        # Start components
        self.worker_pool.start()
        self.merge_coordinator.start()

        # Process issues
        issues_processed = 0
        max_issues = self.parallel_config.max_issues or float("inf")

        while not self._shutdown_requested:
            # Check if done
            if self.queue.empty() and self.worker_pool.active_count == 0:
                # Wait for pending merges
                if self.merge_coordinator.pending_count == 0:
                    break

            # Check max issues limit
            if issues_processed >= max_issues:
                self.logger.info(f"Reached max issues limit ({max_issues})")
                break

            # Get next issue if workers available
            if self.worker_pool.active_count < self.parallel_config.max_workers:
                queued = self.queue.get(block=False)
                if queued:
                    issue = queued.issue_info

                    # P0 sequential processing
                    if issue.priority == "P0" and self.parallel_config.p0_sequential:
                        self._process_sequential(issue)
                    else:
                        self._process_parallel(issue)

                    issues_processed += 1

            # Save state periodically
            self._save_state()

            # Small sleep to prevent busy loop
            time.sleep(0.1)

        # Wait for completion
        self._wait_for_completion()

        # Report results
        self._report_results(start_time)

        # Cleanup state on success
        if not self._shutdown_requested and self.queue.failed_count == 0:
            self._cleanup_state()

        return 0 if self.queue.failed_count == 0 else 1

    def _scan_issues(self) -> list[IssueInfo]:
        """Scan for issues matching criteria.

        Returns:
            List of issues sorted by priority
        """
        # Combine skip_ids from state and config
        skip_ids = set(self.state.completed_issues) | set(self.state.failed_issues.keys())
        if self.parallel_config.skip_ids:
            skip_ids |= self.parallel_config.skip_ids

        issues = IssuePriorityQueue.scan_issues(
            self.br_config,
            priority_filter=list(self.parallel_config.priority_filter),
            skip_ids=skip_ids,
            only_ids=self.parallel_config.only_ids,
        )

        # Apply max issues limit
        if self.parallel_config.max_issues > 0:
            issues = issues[: self.parallel_config.max_issues]

        return issues

    def _process_sequential(self, issue: IssueInfo) -> None:
        """Process an issue sequentially (blocking).

        Args:
            issue: Issue to process
        """
        self.logger.info(f"Processing {issue.issue_id} sequentially (P0)")

        # Wait for any parallel work to finish
        while self.worker_pool.active_count > 0:
            time.sleep(0.5)

        # Process in main repo (no worktree isolation needed)
        # Note: No callback here - _merge_sequential handles the result explicitly
        # to avoid double-processing (callback would also queue merge/close)
        future = self.worker_pool.submit(issue)

        # Wait for completion
        try:
            result = future.result(timeout=self.parallel_config.timeout_per_issue)
            if result.success:
                # Merge immediately for P0
                self._merge_sequential(result)
        except Exception as e:
            self.logger.error(f"Sequential processing failed: {e}")
            self.queue.mark_failed(issue.issue_id)

    def _process_parallel(self, issue: IssueInfo) -> None:
        """Process an issue in parallel (non-blocking).

        Args:
            issue: Issue to process
        """
        self.logger.info(f"Dispatching {issue.issue_id} to worker pool")
        self.worker_pool.submit(issue, self._on_worker_complete)

    def _on_worker_complete(self, result: WorkerResult) -> None:
        """Callback when a worker completes.

        Args:
            result: Result from the worker
        """
        # Handle interrupted workers (not counted as failed) - ENH-036
        if result.interrupted:
            self.logger.info(f"{result.issue_id} was interrupted during shutdown (can retry)")
            self._interrupted_issues.append(result.issue_id)
            # Don't mark as failed - they can be retried on next run
            return

        # Handle issue closure (no merge needed)
        if result.should_close:
            # Lazy import to avoid circular dependency
            from little_loops.issue_lifecycle import close_issue

            self.logger.info(f"{result.issue_id} should be closed: {result.close_status}")
            info = self._issue_info_by_id.get(result.issue_id)
            if info:
                if close_issue(
                    info,
                    self.br_config,
                    self.logger,
                    result.close_reason,
                    result.close_status,
                ):
                    self.queue.mark_completed(result.issue_id)
                else:
                    self.queue.mark_failed(result.issue_id)
            else:
                self.logger.warning(f"No issue info found for {result.issue_id}")
                self.queue.mark_failed(result.issue_id)
        elif result.success:
            self.logger.success(
                f"{result.issue_id} completed in {format_duration(result.duration)}"
            )
            if result.was_corrected:
                self.logger.info(f"{result.issue_id} was auto-corrected during validation")
                # Log and store corrections for pattern analysis (ENH-010)
                for correction in result.corrections:
                    self.logger.info(f"  Correction: {correction}")
                if result.corrections:
                    self.state.corrections[result.issue_id] = result.corrections
            self.merge_coordinator.queue_merge(result)
        else:
            self.logger.error(f"{result.issue_id} failed: {result.error}")
            self.queue.mark_failed(result.issue_id)

        # Update timing
        self.state.timing[result.issue_id] = {
            "total": result.duration,
        }

    def _merge_sequential(self, result: WorkerResult) -> None:
        """Merge a sequential (P0) result immediately.

        Args:
            result: Result to merge
        """
        # Handle closure for sequential issues
        if result.should_close:
            # Lazy import to avoid circular dependency
            from little_loops.issue_lifecycle import close_issue

            info = self._issue_info_by_id.get(result.issue_id)
            if info and close_issue(
                info,
                self.br_config,
                self.logger,
                result.close_reason,
                result.close_status,
            ):
                self.queue.mark_completed(result.issue_id)
            else:
                self.queue.mark_failed(result.issue_id)
            return

        self.merge_coordinator.queue_merge(result)
        # Wait for this specific merge
        self.merge_coordinator.wait_for_completion(timeout=60)

        if result.issue_id in self.merge_coordinator.merged_ids:
            self.queue.mark_completed(result.issue_id)
            self._complete_issue_lifecycle_if_needed(result.issue_id)
        else:
            self.queue.mark_failed(result.issue_id)

    def _wait_for_completion(self) -> None:
        """Wait for all workers and merges to complete."""
        self.logger.info("Waiting for workers to complete...")

        # Calculate timeout
        if self.parallel_config.orchestrator_timeout > 0:
            timeout = self.parallel_config.orchestrator_timeout
        else:
            timeout = self.parallel_config.timeout_per_issue * self.parallel_config.max_workers

        start = time.time()
        while self.worker_pool.active_count > 0:
            if time.time() - start > timeout:
                self.logger.warning(f"Timeout waiting for workers after {timeout}s")
                self.worker_pool.terminate_all_processes()
                break
            time.sleep(1.0)

        # Wait for merges
        self.logger.info("Waiting for pending merges...")
        self.merge_coordinator.wait_for_completion(timeout=120)

        # Update queue with merge results and complete lifecycle
        for issue_id in self.merge_coordinator.merged_ids:
            self.queue.mark_completed(issue_id)
            self._complete_issue_lifecycle_if_needed(issue_id)

        for issue_id in self.merge_coordinator.failed_merges:
            self.queue.mark_failed(issue_id)

    def _report_results(self, start_time: float) -> None:
        """Report processing results.

        Args:
            start_time: When processing started
        """
        total_time = time.time() - start_time

        self.logger.info("")
        self.logger.info("=" * 60)
        self.logger.info("PARALLEL ISSUE PROCESSING COMPLETE")
        self.logger.info("=" * 60)
        self.logger.info("")
        self.logger.timing(f"Total time: {format_duration(total_time)}")
        self.logger.info(f"Completed: {self.queue.completed_count}")
        self.logger.info(f"Failed: {self.queue.failed_count}")
        if self._interrupted_issues:
            self.logger.info(f"Interrupted: {len(self._interrupted_issues)}")

        if self.queue.completed_count > 0:
            total_issue_time = sum(t.get("total", 0) for t in self.state.timing.values())
            if total_issue_time > 0:
                speedup = total_issue_time / total_time
                self.logger.info(f"Estimated speedup: {speedup:.2f}x")

        if self.queue.failed_ids:
            self.logger.info("")
            self.logger.warning("Failed issues:")
            for issue_id in self.queue.failed_ids:
                self.logger.warning(f"  - {issue_id}")

        # Report interrupted issues separately (ENH-036)
        if self._interrupted_issues:
            self.logger.info("")
            self.logger.info(f"Interrupted: {len(self._interrupted_issues)} (can retry)")
            for issue_id in self._interrupted_issues:
                self.logger.info(f"  - {issue_id}")

        # Report correction statistics for quality tracking (ENH-010)
        if self.state.corrections:
            total_corrected = len(self.state.corrections)
            total_issues = self.queue.completed_count + self.queue.failed_count
            correction_rate = (total_corrected / total_issues * 100) if total_issues > 0 else 0
            self.logger.info("")
            self.logger.info(
                f"Auto-corrections: {total_corrected}/{total_issues} ({correction_rate:.1f}%)"
            )

            # Group corrections by category (ENH-010 fourth fix)
            from collections import Counter, defaultdict

            all_corrections: list[str] = []
            by_category: dict[str, int] = defaultdict(int)
            for corrections in self.state.corrections.values():
                all_corrections.extend(corrections)
                for correction in corrections:
                    # Extract category from [category] prefix if present
                    if correction.startswith("[") and "]" in correction:
                        category = correction[1 : correction.index("]")]
                        by_category[category] += 1
                    else:
                        by_category["uncategorized"] += 1

            # Log corrections by type/category
            if by_category:
                self.logger.info("Corrections by type:")
                for category, count in sorted(by_category.items(), key=lambda x: -x[1]):
                    self.logger.info(f"  - {category}: {count}")

            # Log most common individual corrections
            if all_corrections:
                common = Counter(all_corrections).most_common(3)
                self.logger.info("Most common corrections:")
                for correction, count in common:
                    # Truncate long correction descriptions
                    display = correction[:60] + "..." if len(correction) > 60 else correction
                    self.logger.info(f"  - {display}: {count}")

        # Report stash pop warnings (local changes need manual recovery)
        stash_warnings = self.merge_coordinator.stash_pop_failures
        if stash_warnings:
            self.logger.info("")
            self.logger.warning("Stash recovery warnings (local changes need manual restoration):")
            for issue_id, message in stash_warnings.items():
                self.logger.warning(f"  - {issue_id}: {message}")
            self.logger.warning("")
            self.logger.warning(
                "To recover: Run 'git stash list' to find your changes, "
                "then 'git stash pop' or 'git stash apply stash@{N}'"
            )

    def _complete_issue_lifecycle_if_needed(self, issue_id: str) -> bool:
        """Complete issue lifecycle if the issue file wasn't moved during merge.

        Args:
            issue_id: ID of the issue to complete

        Returns:
            True if lifecycle was completed (or already complete), False on error
        """
        info = self._issue_info_by_id.get(issue_id)
        if not info:
            self.logger.warning(f"No issue info found for {issue_id}")
            return False

        original_path = info.path
        completed_dir = self.br_config.get_completed_dir()
        completed_path = completed_dir / original_path.name

        # Check if already moved to completed
        if completed_path.exists():
            return True

        # Check if still in original location
        if not original_path.exists():
            return True

        # Issue file still in original location - complete lifecycle
        self.logger.info(f"Completing lifecycle for {issue_id} (merged but file not moved)")

        try:
            completed_dir.mkdir(parents=True, exist_ok=True)

            # Read original content
            content = original_path.read_text()

            # Add resolution section if not already present
            if "## Resolution" not in content:
                action = self.br_config.get_category_action(info.issue_type)
                resolution = f"""

---

## Resolution

- **Action**: {action}
- **Completed**: {datetime.now().strftime("%Y-%m-%d")}
- **Status**: Completed (parallel merge fallback)
- **Implementation**: Merged from parallel worker branch

### Changes Made
- See git history for implementation details

### Verification Results
- Work verification passed before merge

### Commits
- See `git log --oneline` for merge commit details
"""
                content += resolution

            # Use git mv if possible (before writing content to avoid "destination exists")
            result = self._git_lock.run(
                ["mv", str(original_path), str(completed_path)],
                cwd=self.repo_path,
            )

            if result.returncode != 0:
                # git mv failed (destination may exist or other error)
                self.logger.warning(f"git mv failed for {issue_id}: {result.stderr}")
                # Write content to destination (may overwrite existing)
                completed_path.write_text(content)
                # Remove source if it still exists
                if original_path.exists():
                    original_path.unlink()
            else:
                # git mv succeeded, write updated content
                completed_path.write_text(content)

            # Stage and commit
            self._git_lock.run(
                ["add", "-A"],
                cwd=self.repo_path,
            )

            action = self.br_config.get_category_action(info.issue_type)
            commit_msg = f"""{action}({info.issue_type}): complete {issue_id} lifecycle

Parallel merge fallback - issue file moved to completed.

Issue: {issue_id}
Type: {info.issue_type}
Title: {info.title}
"""
            commit_result = self._git_lock.run(
                ["commit", "-m", commit_msg],
                cwd=self.repo_path,
            )

            if commit_result.returncode != 0:
                if "nothing to commit" not in commit_result.stdout.lower():
                    self.logger.warning(f"git commit failed: {commit_result.stderr}")
            else:
                commit_hash_match = re.search(r"\[[\w-]+\s+([a-f0-9]+)\]", commit_result.stdout)
                if commit_hash_match:
                    self.logger.success(
                        f"Completed lifecycle for {issue_id}: {commit_hash_match.group(1)}"
                    )
                else:
                    self.logger.success(f"Completed lifecycle for {issue_id}")

            return True

        except Exception as e:
            self.logger.error(f"Failed to complete lifecycle for {issue_id}: {e}")
            return False

    def _cleanup(self) -> None:
        """Clean up resources."""
        self.logger.info("Cleaning up...")

        # Save final state
        self._save_state()

        # Shutdown components
        self.worker_pool.shutdown(wait=True)
        self.merge_coordinator.shutdown(wait=True, timeout=30)

        # Clean up worktrees if not interrupted
        if not self._shutdown_requested:
            self.worker_pool.cleanup_all_worktrees()
