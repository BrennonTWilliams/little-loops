"""Main orchestrator for parallel issue processing.

Coordinates the priority queue, worker pool, and merge coordinator to process
multiple issues concurrently.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from little_loops.events import EventBus
from little_loops.frontmatter import parse_frontmatter, update_frontmatter
from little_loops.issue_parser import IssueInfo
from little_loops.logger import Logger, format_duration
from little_loops.parallel.git_lock import GitLock
from little_loops.parallel.merge_coordinator import MergeCoordinator
from little_loops.parallel.overlap_detector import OverlapDetector
from little_loops.parallel.priority_queue import IssuePriorityQueue
from little_loops.parallel.types import (
    OrchestratorState,
    ParallelConfig,
    PendingWorktreeInfo,
    WorkerResult,
)
from little_loops.parallel.worker_pool import WorkerPool
from little_loops.session_log import append_session_log_entry
from little_loops.session_store import record_orchestration_run, resolve_history_db
from little_loops.worktree_utils import (
    _is_ll_branch,
    _is_ll_worktree,
    merge_epic_branch_to_base,
    open_pr_for_epic_branch,
    verify_epic_branch_before_merge,
)

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def _worktree_branch_name(worktree_path: Path) -> str | None:
    """Return the current branch of a worktree via git rev-parse.

    Uses bare subprocess.run (not _git_lock) — the lock must not block on a
    partially torn-down worktree.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


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
        wave_label: str | None = None,
        event_bus: EventBus | None = None,
        run_id: str | None = None,
        driver: str = "ll-parallel",
    ) -> None:
        """Initialize the orchestrator.

        Args:
            parallel_config: Parallel processing configuration
            br_config: Project configuration
            repo_path: Path to the git repository (default: current directory)
            verbose: Whether to output progress messages
            wave_label: Optional label for wave-based execution (e.g., "Wave 1")
            event_bus: Optional EventBus for emitting worker completion events
            run_id: Opaque ID shared by every issue in this top-level invocation
            driver: Producer identity (``ll-parallel`` or ``ll-sprint``)
        """
        self.parallel_config = parallel_config
        self.br_config = br_config
        self.repo_path = repo_path or Path.cwd()
        from little_loops.cli.output import use_color_enabled

        self.logger = Logger(verbose=verbose, use_color=use_color_enabled())
        self.wave_label = wave_label
        self._event_bus = event_bus
        self.run_id = run_id or uuid4().hex
        self.driver = driver
        self._execution_duration: float = 0.0

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
        self._state_lock = threading.Lock()
        self._shutdown_requested = False
        self._original_sigint: Any = None
        self._original_sigterm: Any = None

        # Track issue info for lifecycle completion after merge
        self._issue_info_by_id: dict[str, IssueInfo] = {}
        # Track interrupted issues separately from failures (ENH-036)
        self._interrupted_issues: list[str] = []
        # Accumulate per-issue failure reasons for state file (BUG-1383)
        self._worker_errors: dict[str, str] = {}
        # Track feature-branch state when use_feature_branches=True (ENH-665, BUG-2172)
        self._pr_ready_branches: dict[str, dict] = {}  # issue_id -> {branch_name, pushed, pr_url}
        # Track EPIC integration branches already merged/PR'd on completion so the
        # completion trigger is idempotent across worker callbacks (FEAT-2449).
        self._merged_epic_branches: set[str] = set()
        # Verify-gate failure messages, keyed by EPIC ID (ENH-2603).
        self._epic_branch_verify_failures: dict[str, str] = {}

        # Overlap detection (ENH-143)
        self.overlap_detector: OverlapDetector | None = (
            OverlapDetector(config=br_config.dependency_mapping)
            if parallel_config.overlap_detection
            else None
        )
        # Track deferred issues for re-check after active issues complete
        self._deferred_issues: list[IssueInfo] = []
        # Track last status report time for progress visibility (ENH-262)
        self._last_status_time: float = 0.0
        self._last_status_line: str = ""
        # Track last state save time to throttle disk writes (ENH-485)
        self._last_save_time: float = 0.0

    @property
    def execution_duration(self) -> float:
        """Return the total execution duration in seconds."""
        return self._execution_duration

    @property
    def epic_branch_verify_failures(self) -> dict[str, str]:
        """Mapping of EPIC IDs to verify-gate failure messages (ENH-2603).

        Populated when ``epic_branches.verify_before_merge`` is True and the
        test_cmd/lint_cmd gate fails against an EPIC branch tip, blocking its
        merge/PR-open.
        """
        with self._state_lock:
            return dict(self._epic_branch_verify_failures)

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

    def _cleanup_orphaned_worktrees(self, dry_run: bool = False) -> None:
        """Clean up worktrees from previous interrupted runs.

        Scans the worktree base directory and removes any worktrees that are
        not from the current session. This handles cases where a previous run
        was interrupted (Ctrl+C) and worktrees were not cleaned up.

        Args:
            dry_run: If True, log what would be removed but make no changes.
        """
        worktree_base = self.repo_path / self.parallel_config.worktree_base
        if not worktree_base.exists():
            return

        # Get list of worktree directories, skipping those owned by live processes (BUG-579)
        orphaned = []
        for item in worktree_base.iterdir():
            if item.is_dir() and _is_ll_worktree(item.name):
                # Check for a .ll-session-<pid> marker left by an active orchestrator
                owned_by_live = False
                for marker in item.glob(".ll-session-*"):
                    try:
                        pid = int(marker.name.split("-")[-1])
                        os.kill(pid, 0)  # Signal 0: check if process exists
                        owned_by_live = True
                        break
                    except (ProcessLookupError, ValueError):
                        pass
                    except PermissionError:
                        owned_by_live = True  # Process exists, no permission to signal
                        break
                if owned_by_live:
                    self.logger.info(f"Skipping {item.name}: owned by running process")
                    continue
                orphaned.append(item)

        if orphaned:
            self.logger.info(f"Cleaning up {len(orphaned)} orphaned worktree(s) from previous run")

            for worktree_path in orphaned:
                try:
                    # Resolve branch name BEFORE removing the worktree (BUG-2324)
                    branch_name = _worktree_branch_name(worktree_path)

                    if dry_run:
                        self.logger.info(
                            f"[dry-run] Would remove worktree {worktree_path.name}"
                            + (
                                f" and branch {branch_name}"
                                if branch_name and _is_ll_branch(branch_name)
                                else ""
                            )
                        )
                        continue

                    self._git_lock.run(
                        ["worktree", "unlock", str(worktree_path)],
                        cwd=self.repo_path,
                        timeout=10,
                    )
                    # Try git worktree remove first
                    self._git_lock.run(
                        ["worktree", "remove", "--force", str(worktree_path)],
                        cwd=self.repo_path,
                        timeout=30,
                    )

                    # If git worktree remove failed, force delete the directory
                    if worktree_path.exists():
                        shutil.rmtree(worktree_path, ignore_errors=True)

                    # Delete branch only for ll-managed shapes (BUG-2324: safe guard replaces
                    # the old parallel/-only guard to also cover loop worktree branches)
                    if branch_name and _is_ll_branch(branch_name):
                        self._git_lock.run(
                            ["branch", "-D", branch_name],
                            cwd=self.repo_path,
                            timeout=10,
                        )
                except Exception as e:
                    self.logger.warning(f"Failed to clean up {worktree_path.name}: {e}")

            if not dry_run:
                # Also prune git worktree references
                self._git_lock.run(
                    ["worktree", "prune"],
                    cwd=self.repo_path,
                    timeout=30,
                )

        self._prune_ghost_worktree_refs()

    def _prune_ghost_worktree_refs(self) -> None:
        """Prune git worktree metadata entries whose on-disk path no longer exists.

        Handles the SIGKILL race where a worker directory was deleted before
        git worktree prune ran, leaving .git/worktrees/<name>/ intact.  The
        next git worktree add for the same path would then fail with "already exists".
        """
        try:
            result = self._git_lock.run(
                ["worktree", "list", "--porcelain"],
                cwd=self.repo_path,
                timeout=30,
            )
        except Exception as e:
            self.logger.warning(f"Failed to list worktrees for ghost ref scan: {e}")
            return

        ghost_names: list[str] = []
        current: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if not line:
                if current:
                    path_str = current.get("worktree", "")
                    name = Path(path_str).name
                    if _is_ll_worktree(name) and path_str and not Path(path_str).exists():
                        ghost_names.append(name)
                    current = {}
                continue
            key, _, value = line.partition(" ")
            current[key] = value
        if current:
            path_str = current.get("worktree", "")
            name = Path(path_str).name
            if _is_ll_worktree(name) and path_str and not Path(path_str).exists():
                ghost_names.append(name)

        if not ghost_names:
            return

        for name in ghost_names:
            self.logger.info(f"Pruned ghost ref: {name}")

        try:
            self._git_lock.run(
                ["worktree", "prune"],
                cwd=self.repo_path,
                timeout=30,
            )
        except Exception as e:
            self.logger.warning(f"Failed to prune ghost worktree refs: {e}")

    def _inspect_worktree(self, worktree_path: Path) -> PendingWorktreeInfo | None:
        """Inspect a worktree to determine its status.

        Args:
            worktree_path: Path to the worktree directory

        Returns:
            PendingWorktreeInfo if inspection succeeded, None if failed
        """
        try:
            # Read actual branch name from worktree via rev-parse
            branch_name = _worktree_branch_name(worktree_path)

            # Extract issue ID (e.g., bug-045 -> BUG-045)
            # Pattern: worker-<issue-id>-<timestamp>
            match = re.match(r"worker-([a-z]+-\d+)-\d{8}-\d{6}", worktree_path.name)
            issue_id = match.group(1).upper() if match else worktree_path.name

            # EPIC-aware comparison base (FEAT-2562): an EPIC child's commits
            # diverge from the EPIC integration branch, not base_branch — compare
            # against that instead when the worktree belongs to an EPIC child.
            base = self.parallel_config.base_branch
            if self.parallel_config.epic_branches.enabled:
                issue_info = self._issue_info_by_id.get(issue_id)
                if issue_info is not None:
                    from little_loops.issue_parser import find_issues
                    from little_loops.issue_progress import (
                        build_parent_map,
                        find_nearest_epic_ancestor,
                    )

                    all_issues = find_issues(
                        self.br_config,
                        status_filter={
                            "open",
                            "in_progress",
                            "blocked",
                            "done",
                            "cancelled",
                            "deferred",
                        },
                    )
                    parent_map = build_parent_map(all_issues)
                    epic_id = find_nearest_epic_ancestor(issue_info, parent_map)
                    if epic_id is not None:
                        from little_loops.worktree_utils import resolve_epic_branch_name

                        slug = self.worker_pool._load_epic_slug(epic_id)
                        prefix = self.parallel_config.epic_branches.prefix
                        base = resolve_epic_branch_name(epic_id, prefix, slug)

            # Check commits ahead of base (epic branch for EPIC children, base_branch otherwise)
            result = self._git_lock.run(
                ["rev-list", "--count", f"{base}..{branch_name}"],
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
            item for item in worktree_base.iterdir() if item.is_dir() and _is_ll_worktree(item.name)
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
                if info.branch_name is None:
                    self.logger.warning(
                        f"  Skipping merge for {info.issue_id}: branch name unknown (rev-parse failed)"
                    )
                    continue

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
        if self.parallel_config.clean_start:
            self.state.started_at = datetime.now().isoformat()
            return
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

    def _save_state(self, force: bool = False) -> None:
        """Save current state to file using an atomic write.

        Writes are throttled to at most once every 5 seconds to reduce filesystem I/O
        during high-frequency loop ticks (e.g., merge-waiting phase). Pass force=True
        to bypass the throttle, e.g., on shutdown.
        """
        now = time.time()
        if not force and now - self._last_save_time < 5.0:
            return
        self._last_save_time = now
        with self._state_lock:
            self.state.last_checkpoint = datetime.now().isoformat()
            self.state.completed_issues = self.queue.completed_ids
            self.state.failed_issues = {
                issue_id: self._worker_errors.get(issue_id, "Failed")
                for issue_id in self.queue.failed_ids
            }
            self.state.in_progress_issues = self.queue.in_progress_ids

            state_file = self.repo_path / self.parallel_config.state_file
            data = json.dumps(self.state.to_dict(), indent=2)
            tmp_fd, tmp_path = tempfile.mkstemp(dir=state_file.parent, suffix=".tmp")
            try:
                with os.fdopen(tmp_fd, "w") as f:
                    f.write(data)
                os.replace(tmp_path, state_file)
            except Exception:
                os.unlink(tmp_path)
                raise

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

    def _maybe_report_status(self) -> None:
        """Report status if enough time has elapsed since last report.

        Reports every 5 seconds during active processing for progress visibility (ENH-262).
        Suppresses duplicate lines when nothing has changed.
        """
        now = time.time()
        # Report every 5 seconds
        if now - self._last_status_time < 5.0:
            return

        self._last_status_time = now

        # Build status line
        parts = []

        # Add wave label if present
        if self.wave_label:
            parts.append(f"{self.wave_label}")

        # Get queue counts
        in_progress = len(self.queue.in_progress_ids)
        completed = self.queue.completed_count
        failed = self.queue.failed_count
        pending_merge = self.merge_coordinator.pending_count

        parts.append(f"Active: {in_progress}")
        parts.append(f"Done: {completed}")
        if failed > 0:
            parts.append(f"Failed: {failed}")
        if pending_merge > 0:
            parts.append(f"Merging: {pending_merge}")

        # Build status line
        status = " | ".join(parts)

        # Get active worker stages
        active_stages = self.worker_pool.get_active_stages()

        # Add worker details if any are active
        if active_stages:
            # Group by stage
            by_stage: dict[str, list[str]] = {}
            for issue_id, worker_stage in active_stages.items():
                stage_name = worker_stage.value.title()
                by_stage.setdefault(stage_name, []).append(issue_id)

            stage_parts = []
            for stage_name in ["Validating", "Implementing", "Verifying", "Merging"]:
                if stage_name in by_stage:
                    issue_ids = ", ".join(by_stage[stage_name])
                    stage_parts.append(f"{stage_name}: [{issue_ids}]")

            if stage_parts:
                status += " | " + " | ".join(stage_parts)

        # Skip if nothing changed since last report
        if status == self._last_status_line:
            return
        self._last_status_line = status

        # Log with gray color to distinguish from normal logs
        self.logger.debug(status)

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

            # Report status periodically for progress visibility (ENH-262)
            self._maybe_report_status()

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
            type_prefixes=self.parallel_config.type_prefixes,
            label_filter=self.parallel_config.label_filter,
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
        # Check for overlaps if enabled (ENH-143)
        if self.overlap_detector:
            overlap = self.overlap_detector.check_overlap(issue)
            if overlap:
                if self.parallel_config.serialize_overlapping:
                    self.logger.warning(
                        f"Deferring {issue.issue_id} - overlaps with {overlap.overlapping_issues}"
                    )
                    # Track for re-check when active issues complete
                    self._deferred_issues.append(issue)
                    return
                else:
                    self.logger.warning(
                        f"Warning: {issue.issue_id} may conflict with {overlap.overlapping_issues}"
                    )

            # Register as active before dispatch
            self.overlap_detector.register_issue(issue)

        self.logger.info(f"Dispatching {issue.issue_id} to worker pool")
        self.worker_pool.submit(issue, self._on_worker_complete)

    def _record_orchestration_result(
        self,
        result: WorkerResult,
        *,
        status: str,
        failure_reason: str | None = None,
    ) -> None:
        """Persist one worker outcome without affecting orchestration behavior."""
        branch_state = self._pr_ready_branches.get(result.issue_id, {})
        with suppress(Exception):
            record_orchestration_run(
                resolve_history_db(),
                run_id=self.run_id,
                driver=self.driver,
                issue_id=result.issue_id,
                status=status,
                failure_reason=failure_reason,
                duration_s=result.duration,
                wave=self.wave_label,
                pr_url=branch_state.get("pr_url"),
                branch=result.branch_name or None,
            )

    def _on_worker_complete(self, result: WorkerResult) -> None:
        """Callback when a worker completes.

        Args:
            result: Result from the worker
        """
        # Unregister from overlap tracking (ENH-143)
        if self.overlap_detector:
            self.overlap_detector.unregister_issue(result.issue_id)
            # Re-queue deferred issues that were waiting on this one
            self._requeue_deferred_issues()

        # Handle interrupted workers (not counted as failed) - ENH-036
        if result.interrupted:
            self.logger.info(f"{result.issue_id} was interrupted during shutdown (can retry)")
            self._record_orchestration_result(
                result,
                status="interrupted",
                failure_reason=result.error or "Worker interrupted",
            )
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
                # TODO(ENH-1686): parallel-path close events not yet live-written
                if close_issue(
                    info,
                    self.br_config,
                    self.logger,
                    result.close_reason,
                    result.close_status,
                    interceptors=None,
                ):
                    self.queue.mark_completed(result.issue_id)
                else:
                    self._worker_errors[result.issue_id] = (
                        f"Close failed: {result.close_reason or 'close error'}"
                    )
                    self.queue.mark_failed(result.issue_id)
            else:
                self.logger.warning(f"No issue info found for {result.issue_id}")
                self._worker_errors[result.issue_id] = "Close failed: no issue info"
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
                    with self._state_lock:
                        self.state.corrections[result.issue_id] = result.corrections
            if self.parallel_config.use_feature_branches:
                # Feature branch mode: skip auto-merge, branch stays alive (ENH-665, BUG-2172)
                # Hold issue at in_progress until PR is merged; ll-sync reconcile promotes to done (ENH-2182)
                self.logger.info(f"{result.issue_id}: feature branch ready — {result.branch_name}")
                self.queue.mark_completed(result.issue_id)
                self._complete_issue_lifecycle_if_needed(
                    result.issue_id, terminal_status="in_progress"
                )
                branch_state: dict[str, Any] = {
                    "branch_name": result.branch_name,
                    "pushed": False,
                    "pr_url": None,
                }
                if self.parallel_config.push_feature_branches:
                    push_result = subprocess.run(
                        [
                            "git",
                            "push",
                            "--force-with-lease",
                            self.parallel_config.remote_name,
                            result.branch_name,
                        ],
                        cwd=self.repo_path,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if push_result.returncode == 0:
                        branch_state["pushed"] = True
                        self.logger.info(
                            f"{result.issue_id}: pushed {result.branch_name}"
                            f" to {self.parallel_config.remote_name}"
                        )
                        if self.parallel_config.open_pr_for_feature_branches:
                            # Carry the per-EPIC integration branch through the
                            # existing branch_state carrier (FEAT-2453); None for
                            # non-EPIC issues so the PR --base falls back to base.
                            branch_state["epic_branch"] = result.epic_branch
                            self._open_pr_for_branch(
                                result.issue_id, result.branch_name, branch_state
                            )
                    else:
                        self.logger.warning(
                            f"{result.issue_id}: git push failed: {push_result.stderr.strip()}"
                        )
                # Write branch name (and optional PR URL) back to issue frontmatter (ENH-2175)
                info = self._issue_info_by_id.get(result.issue_id)
                if info and info.path.exists():
                    try:
                        content = info.path.read_text()
                        fm = parse_frontmatter(content)
                        updates: dict[str, Any] = {"branch": result.branch_name}
                        if branch_state.get("pr_url") and not fm.get("pr_url"):
                            updates["pr_url"] = branch_state["pr_url"]
                        content = update_frontmatter(content, updates)
                        info.path.write_text(content)
                        # BUG-2424: stage only the issue file, never `git add -A`
                        # against the main repo (would sweep unrelated dirty state).
                        commit_result = self._stage_and_commit_issue_scoped(
                            result.issue_id,
                            info.path,
                            f"{result.issue_id}: record feature branch in frontmatter",
                        )
                        if (
                            commit_result is not None
                            and commit_result.returncode != 0
                            and "nothing to commit" not in commit_result.stdout.lower()
                        ):
                            self.logger.warning(
                                f"{result.issue_id}: branch frontmatter commit failed:"
                                f" {commit_result.stderr}"
                            )
                    except Exception as exc:
                        self.logger.warning(
                            f"{result.issue_id}: failed to record branch in frontmatter: {exc}"
                        )
                with self._state_lock:
                    self._pr_ready_branches[result.issue_id] = branch_state
            else:
                self.merge_coordinator.queue_merge(result)
                # Wait for merge to complete before returning from callback.
                # This prevents dispatch of next worker while merge is in progress,
                # avoiding race conditions between worktree creation and merge ops.
                # (BUG-140: Race condition between worktree creation and merge)
                self.merge_coordinator.wait_for_completion(timeout=120)
                if result.issue_id in self.merge_coordinator.merged_ids:
                    self.queue.mark_completed(result.issue_id)
                    self._complete_issue_lifecycle_if_needed(result.issue_id)
                else:
                    self._worker_errors[result.issue_id] = (
                        f"Merge failed: {result.error or 'merge error'}"
                    )
                    self.queue.mark_failed(result.issue_id)
        else:
            self.logger.error(f"{result.issue_id} failed: {result.error}")
            self._worker_errors[result.issue_id] = result.error or "Failed"
            self.queue.mark_failed(result.issue_id)

        # EPIC-completion merge (FEAT-2449): once every child of this issue's
        # nearest EPIC ancestor reaches `done` (and none is failed/blocked),
        # merge/PR the shared `epic/<id>-<slug>` integration branch to base.
        # Runs on both the success and failure branches: a failed child holds
        # the epic branch open via the partial-failure gate inside the helper.
        if self.parallel_config.epic_branches.enabled and result.epic_branch:
            self._maybe_complete_epic(result.issue_id, result.epic_branch)

        # Update timing
        with self._state_lock:
            self.state.timing[result.issue_id] = {
                "total": result.duration,
            }

        # Record the authoritative result after merge/PR and timing state are final.
        recorded_error = self._worker_errors.get(result.issue_id)
        if result.was_blocked:
            orchestration_status = "skipped"
            orchestration_reason = result.error or recorded_error
        elif (result.success or result.should_close) and recorded_error is None:
            orchestration_status = "completed"
            orchestration_reason = None
        else:
            orchestration_status = "failed"
            orchestration_reason = recorded_error or result.error or "Worker failed"
        self._record_orchestration_result(
            result,
            status=orchestration_status,
            failure_reason=orchestration_reason,
        )

        # Clean up stage tracking after callback completes (ENH-262)
        # Delay briefly so status reporter can show completion
        self.worker_pool.remove_worker_stage(result.issue_id)

        # Emit worker completion event for extensions (ENH-921)
        if self._event_bus:
            self._event_bus.emit(
                {
                    "event": "parallel.worker_completed",
                    "ts": datetime.now(UTC).isoformat(),
                    "issue_id": result.issue_id,
                    "worker_name": result.worktree_path.name,
                    "status": "success" if result.success else "failure",
                    "duration_seconds": result.duration,
                }
            )

    def _requeue_deferred_issues(self) -> None:
        """Re-queue deferred issues that no longer have overlaps (ENH-143)."""
        if not self._deferred_issues:
            return

        # Check each deferred issue for remaining overlaps
        still_deferred = []
        for issue in self._deferred_issues:
            if self.overlap_detector:
                overlap = self.overlap_detector.check_overlap(issue)
                if overlap:
                    # Still has overlaps, keep deferred
                    still_deferred.append(issue)
                else:
                    # No more overlaps, add back to queue
                    self.logger.info(f"Re-queuing {issue.issue_id} - no longer overlapping")
                    self.queue.add(issue)

        self._deferred_issues = still_deferred

    def _open_pr_for_branch(
        self,
        issue_id: str,
        branch_name: str,
        branch_state: dict[str, Any],
    ) -> None:
        """Open a draft PR for a pushed feature branch using the gh CLI.

        Mutates branch_state in place to record pr_url on success.
        Degrades gracefully if gh is missing or unauthenticated.
        """
        try:
            auth_result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if auth_result.returncode != 0:
                self.logger.warning(f"{issue_id}: gh not authenticated, skipping PR creation")
                return
            issue_info = self._issue_info_by_id.get(issue_id)
            pr_title = issue_info.title if issue_info else issue_id
            pr_result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--title",
                    pr_title,
                    "--body",
                    f"Closes {issue_id}",
                    "--base",
                    branch_state.get("epic_branch") or self.parallel_config.base_branch,
                    "--draft",
                    "--head",
                    branch_name,
                ],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if pr_result.returncode == 0:
                branch_state["pr_url"] = pr_result.stdout.strip()
                self.logger.info(f"{issue_id}: PR opened: {branch_state['pr_url']}")
            else:
                self.logger.warning(f"{issue_id}: gh pr create failed: {pr_result.stderr.strip()}")
        except FileNotFoundError:
            self.logger.warning(f"{issue_id}: gh CLI not found, skipping PR creation")
        except subprocess.TimeoutExpired:
            self.logger.warning(f"{issue_id}: gh pr create timed out")

    def _maybe_complete_epic(self, issue_id: str, epic_branch: str) -> None:
        """Merge/PR an EPIC integration branch once all its children are done (FEAT-2449).

        Called from ``_on_worker_complete`` after each worker finishes. Resolves
        the completed issue's nearest EPIC ancestor via the shared FEAT-2561
        helpers, then consults ``compute_epic_progress`` (transitive child walk)
        against the current on-disk statuses:

        - **All children terminally ``done``** (``by_status["done"]`` alone;
          cancelled children do NOT count) with no ``blocked``/``cancelled``
          child and no child in this run's failure set → merge
          ``epic/<id>-<slug>`` into ``base_branch`` (or open one PR when
          ``epic_branches.open_pr``), then delete the branch on merge.
        - **Any child failed/blocked** → the epic branch is held open (no merge,
          no delete): the partial-failure gate scopes ``queue.failed_ids`` /
          ``state.failed_issues`` to this EPIC's child-ID set.

        Idempotent per branch via ``self._merged_epic_branches``.
        """
        cfg = self.parallel_config.epic_branches
        # Config-branch gate (closes the FEAT-2448 dead-read gap): with neither
        # a direct merge nor a PR requested there is nothing to trigger.
        if not cfg.merge_to_base_on_complete and not cfg.open_pr:
            return

        issue_info = self._issue_info_by_id.get(issue_id)
        if issue_info is None:
            return

        from little_loops.issue_parser import find_issues
        from little_loops.issue_progress import (
            build_parent_map,
            compute_epic_progress,
            find_nearest_epic_ancestor,
        )

        all_issues = find_issues(
            self.br_config,
            status_filter={
                "open",
                "in_progress",
                "blocked",
                "done",
                "cancelled",
                "deferred",
            },
        )
        parent_map = build_parent_map(all_issues)
        epic_id = find_nearest_epic_ancestor(issue_info, parent_map)
        if epic_id is None:
            return

        prog = compute_epic_progress(epic_id, all_issues)
        if prog is None:
            return

        total = len(prog.children)
        # Use by_status["done"] ALONE — a cancelled child must NOT trigger a
        # merge into base (diverges from the list_cmd badge which sums
        # done+cancelled; see issue Codebase Research Findings).
        done_count = prog.by_status.get("done", 0)
        blocked_count = prog.by_status.get("blocked", 0)
        cancelled_count = prog.by_status.get("cancelled", 0)
        all_done = total > 0 and done_count == total and blocked_count == 0 and cancelled_count == 0
        if not all_done:
            return

        # Partial-failure gate: even if disk status momentarily reads all-done,
        # a child that failed/blocked in THIS run holds the branch open. Scope
        # the flat run-level failure sets to this EPIC's child IDs (FEAT-2561).
        epic_child_ids = {c.issue_id for c in prog.children}
        failed_here = epic_child_ids & (set(self.queue.failed_ids) | set(self.state.failed_issues))
        if failed_here:
            self.logger.info(
                f"EPIC {epic_id} integration branch held open — "
                f"{len(failed_here)} child(ren) unresolved: {sorted(failed_here)}"
            )
            return

        # Verify gate (ENH-2603): run test_cmd/lint_cmd against the branch tip
        # before merge/PR-open. Deliberately runs BEFORE the idempotency-set
        # add below so a failure leaves the branch retryable on the next
        # completion event instead of being silenced for the rest of the run.
        if not self._verify_epic_branch_before_merge(epic_id, epic_branch):
            return

        # Idempotency: merge/PR each epic branch at most once.
        if epic_branch in self._merged_epic_branches:
            return
        self._merged_epic_branches.add(epic_branch)

        if cfg.open_pr:
            self._open_pr_for_epic_branch(epic_id, epic_branch)
        else:
            self._merge_epic_branch_to_base(epic_id, epic_branch)

    def _verify_epic_branch_before_merge(self, epic_id: str, epic_branch: str) -> bool:
        """Run test_cmd/lint_cmd against the EPIC branch tip before merge/PR (ENH-2603).

        Thin wrapper around the stateless
        ``worktree_utils.verify_epic_branch_before_merge`` (BUG-2614) that
        adapts this instance's config/state: reads
        ``epic_branches.verify_before_merge`` and ``project.test_cmd``/
        ``lint_cmd`` from config, and records a failure message into
        ``self._epic_branch_verify_failures`` for ``_report_results()`` to
        surface.
        """
        cfg = self.parallel_config.epic_branches
        project = self.br_config.project
        ok, message, _returncode = verify_epic_branch_before_merge(
            epic_id,
            epic_branch,
            verify_before_merge=cfg.verify_before_merge,
            repo_path=self.repo_path,
            worktree_base=self.parallel_config.worktree_base,
            test_cmd=project.test_cmd,
            lint_cmd=project.lint_cmd,
            logger=self.logger,
            git_lock=self._git_lock,
            src_dir=project.src_dir,
        )
        if not ok and message is not None:
            with self._state_lock:
                self._epic_branch_verify_failures[epic_id] = message
        return ok

    def _merge_epic_branch_to_base(self, epic_id: str, epic_branch: str) -> None:
        """Merge ``epic_branch`` into ``base_branch`` then delete it (FEAT-2449).

        Thin wrapper around the stateless
        ``worktree_utils.merge_epic_branch_to_base`` (BUG-2614). The main repo
        stays checked out on ``base_branch`` throughout a parallel run, so no
        checkout is needed (mirrors the pending-merge precedent).
        """
        merge_epic_branch_to_base(
            epic_id,
            epic_branch,
            base_branch=self.parallel_config.base_branch,
            repo_path=self.repo_path,
            logger=self.logger,
            git_lock=self._git_lock,
        )

    def _open_pr_for_epic_branch(self, epic_id: str, epic_branch: str) -> None:
        """Open one PR for a completed EPIC integration branch via gh (FEAT-2449).

        Thin wrapper around the stateless
        ``worktree_utils.open_pr_for_epic_branch`` (BUG-2614).
        """
        open_pr_for_epic_branch(
            epic_id,
            epic_branch,
            base_branch=self.parallel_config.base_branch,
            repo_path=self.repo_path,
            logger=self.logger,
        )

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
            # TODO(ENH-1686): parallel-path close events not yet live-written
            if info and close_issue(
                info,
                self.br_config,
                self.logger,
                result.close_reason,
                result.close_status,
                interceptors=None,
            ):
                self.queue.mark_completed(result.issue_id)
            else:
                self._worker_errors[result.issue_id] = (
                    f"Close failed: {result.close_reason or 'close error'}"
                )
                self.queue.mark_failed(result.issue_id)
            return

        self.merge_coordinator.queue_merge(result)
        # Wait for this specific merge
        self.merge_coordinator.wait_for_completion(timeout=60)

        if result.issue_id in self.merge_coordinator.merged_ids:
            self.queue.mark_completed(result.issue_id)
            self._complete_issue_lifecycle_if_needed(result.issue_id)
        else:
            self._worker_errors[result.issue_id] = f"Merge failed: {result.error or 'merge error'}"
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

        for issue_id, reason in self.merge_coordinator.failed_merges.items():
            self._worker_errors[issue_id] = reason or "Merge failed"
            self.queue.mark_failed(issue_id)

    def _report_results(self, start_time: float) -> None:
        """Report processing results.

        Args:
            start_time: When processing started
        """
        total_time = time.time() - start_time
        self._execution_duration = total_time

        self.logger.info("")
        self.logger.info("=" * 60)
        if self.wave_label:
            self.logger.info(f"{self.wave_label.upper()} PROCESSING COMPLETE")
        else:
            self.logger.info("PARALLEL ISSUE PROCESSING COMPLETE")
        self.logger.info("=" * 60)
        self.logger.info("")
        self.logger.timing(f"Total time: {format_duration(total_time)}")
        self.logger.info(f"Completed: {self.queue.completed_count}")
        self.logger.info(f"Failed: {self.queue.failed_count}")
        if self._interrupted_issues:
            self.logger.info(f"Interrupted: {len(self._interrupted_issues)}")

        with self._state_lock:
            timing_snapshot = dict(self.state.timing)
            corrections_snapshot = dict(self.state.corrections)

        if self.queue.completed_count > 0:
            total_issue_time = sum(t.get("total", 0) for t in timing_snapshot.values())
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

        # Report feature branches with actual per-branch state (ENH-665, BUG-2172)
        if self._pr_ready_branches:
            self.logger.info("")
            self.logger.info(f"Feature branches: {len(self._pr_ready_branches)} branch(es)")
            for issue_id, state in self._pr_ready_branches.items():
                branch = state["branch_name"]
                if state.get("pr_url"):
                    self.logger.info(
                        f"  - {issue_id}: {branch} — pushed + PR opened: {state['pr_url']}"
                    )
                elif state.get("pushed"):
                    self.logger.info(f"  - {issue_id}: {branch} — pushed (PR skipped)")
                else:
                    self.logger.info(f"  - {issue_id}: {branch} — local-only branch retained")

        # Report correction statistics for quality tracking (ENH-010)
        if corrections_snapshot:
            total_corrected = len(corrections_snapshot)
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
            for corrections in corrections_snapshot.values():
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

        # Report EPIC-branch verify-gate failures (blocked merge/PR-open, ENH-2603)
        verify_failures = self.epic_branch_verify_failures
        if verify_failures:
            self.logger.info("")
            self.logger.warning("EPIC branch verify-gate failures (merge/PR-open blocked):")
            for epic_id, message in verify_failures.items():
                self.logger.warning(f"  - {epic_id}: {message}")

    def _stage_and_commit_issue_scoped(
        self, issue_id: str, issue_path: Path, commit_msg: str
    ) -> subprocess.CompletedProcess[str] | None:
        """Stage and commit ONLY the issue file in the main repo (BUG-2424).

        Both parallel completion commits — ``_on_worker_complete``'s feature-branch
        frontmatter fallback and ``_complete_issue_lifecycle_if_needed`` — are
        frontmatter-only follow-ups: the worker's code diff is already merged and
        committed beforehand. Staging with ``git add -A`` here would sweep any
        pre-existing dirty or untracked file in the main working tree into the
        commit, corrupting its provenance (poisoned ``git blame``/``bisect``,
        premature commit of unrelated WIP).

        Mirror ``hooks/post_tool_use.py:_maybe_auto_commit`` instead: stage the
        single issue file, then skip the commit (warn only) if any *other* path is
        dirty or staged in the main repo. The skip is self-protecting under
        concurrent workers sharing one ``GitLock`` — a later completer re-runs this
        check and also declines to sweep the still-staged file.

        Returns the commit ``CompletedProcess`` on success, or ``None`` when the
        commit was skipped because unrelated dirty state was present.
        """
        filename = issue_path.name
        self._git_lock.run(["add", "--", str(issue_path)], cwd=self.repo_path)
        status = self._git_lock.run(["status", "--porcelain"], cwd=self.repo_path)
        other = [ln for ln in status.stdout.splitlines() if filename not in ln]
        if other:
            self.logger.warning(
                f"{issue_id}: skipping scoped completion commit — main repo has "
                f"unrelated dirty paths an unscoped stage would sweep in: "
                f"{[ln.strip() for ln in other]}"
            )
            return None
        return self._git_lock.run(["commit", "-m", commit_msg], cwd=self.repo_path)

    def _complete_issue_lifecycle_if_needed(
        self, issue_id: str, terminal_status: str = "done"
    ) -> bool:
        """Complete issue lifecycle by writing status to frontmatter.

        Args:
            issue_id: ID of the issue to complete
            terminal_status: Status to write — ``"done"`` for auto-merge,
                ``"in_progress"`` for feature-branch hold (ENH-2182)

        Returns:
            True if lifecycle was completed (or already complete), False on error
        """
        # TODO(ENH-1686): parallel-path close events not yet live-written
        info = self._issue_info_by_id.get(issue_id)
        if not info:
            self.logger.warning(f"No issue info found for {issue_id}")
            return False

        original_path = info.path

        if not original_path.exists():
            return True

        self.logger.info(f"Completing lifecycle for {issue_id} (frontmatter status update)")

        try:
            content = original_path.read_text()

            # Add resolution section if not already present
            if "## Resolution" not in content:
                action = self.br_config.get_category_action(info.issue_type)
                if terminal_status == "in_progress":
                    status_label = "Branch ready, awaiting PR merge"
                    impl_note = "Feature branch created; PR pending review and merge"
                else:
                    status_label = "Completed (parallel merge fallback)"
                    impl_note = "Merged from parallel worker branch"
                resolution = f"""

---

## Resolution

- **Action**: {action}
- **Completed**: {datetime.now(UTC).strftime("%Y-%m-%d")}
- **Status**: {status_label}
- **Implementation**: {impl_note}

### Changes Made
- See git history for implementation details

### Verification Results
- Work verification passed before merge

### Commits
- See `git log --oneline` for merge commit details
"""
                content += resolution

            fm_updates: dict[str, Any] = {"status": terminal_status}
            if terminal_status == "done":
                fm_updates["completed_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            content = update_frontmatter(content, fm_updates)
            original_path.write_text(content)
            append_session_log_entry(original_path, "ll-parallel")

            action = self.br_config.get_category_action(info.issue_type)
            if terminal_status == "in_progress":
                lifecycle_note = "Feature branch ready — status: in_progress (awaiting PR merge)"
            else:
                lifecycle_note = "Parallel merge fallback — status: done written to frontmatter"
            commit_msg = f"""{action}({info.issue_type}): complete {issue_id} lifecycle

{lifecycle_note}

Issue: {issue_id}
Type: {info.issue_type}
Title: {info.title}
"""
            # BUG-2424: stage only the issue file, never `git add -A` against the
            # main repo (would sweep unrelated dirty/untracked state into the commit).
            commit_result = self._stage_and_commit_issue_scoped(issue_id, original_path, commit_msg)

            if commit_result is None:
                # Skipped: unrelated dirty state in the main repo. The frontmatter
                # status was still written to the file; the helper already warned.
                return True

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

        # Save final state (force=True bypasses throttle to ensure shutdown state is persisted)
        self._save_state(force=True)

        # Shutdown components
        self.worker_pool.shutdown(wait=True)
        self.merge_coordinator.shutdown(wait=True, timeout=30)

        # Flush transports regardless of interrupt state so events are not lost.
        if self._event_bus is not None:
            self._event_bus.close_transports()

        # Clean up worktrees if not interrupted
        if not self._shutdown_requested:
            self.worker_pool.cleanup_all_worktrees()
