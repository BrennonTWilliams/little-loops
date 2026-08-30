"""Worker pool for parallel issue processing with git worktree isolation.

Each worker operates in an isolated git worktree, allowing concurrent issue
processing without file conflicts.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from little_loops.context_window import context_window_for
from little_loops.host_runner import project_child_env, resolve_automation, resolve_host
from little_loops.parallel.git_lock import GitLock
from little_loops.parallel.types import ParallelConfig, WorkerResult, WorkerStage
from little_loops.ready_issue import run_ready_issue_with_retry
from little_loops.session_store import (
    record_orchestration_run,
    record_session_lifecycle_event,
    resolve_history_db,
)
from little_loops.subprocess_utils import (
    assemble_guillotine_prompt,
    detect_context_handoff,
    read_continuation_prompt,
    read_sentinel,
)
from little_loops.subprocess_utils import (
    run_claude_command as _run_claude_base,
)
from little_loops.work_verification import EXCLUDED_DIRECTORIES, verify_work_was_done

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.events import EventBus
    from little_loops.issue_parser import IssueInfo
    from little_loops.logger import Logger
    from little_loops.parallel.types import SprintWorkerContext
    from little_loops.test_tamper_guard import TamperSnapshot


def _run_per_worktree_proof_first_gate(
    issue: IssueInfo,
    worktree_path: Path,
    br_config: BRConfig,
    parallel_config: ParallelConfig,
    logger: Logger,
) -> bool:
    """Run proof-first-task gate for learning_tests_required issues (ENH-2219).

    Called in WorkerPool._process_issue() between VALIDATING and IMPLEMENTING.
    Returns True if implementation may proceed, False if blocked or errored.
    """
    # Short-circuits run BEFORE target resolution so disabled / skipped runs
    # incur no JIT extraction cost (BUG-2320 — mirrors the ordering in
    # cli/sprint/run.py:_run_learning_gate_preflight).
    if not br_config.learning_tests.enabled:
        return True
    if parallel_config.skip_learning_gate:
        logger.info(f"[{issue.issue_id}] Learning gate skipped (--skip-learning-gate)")
        return True

    # Resolve targets just-in-time. A populated field is used as-is; an absent
    # field (None) means "deps not yet computed" — extract from the issue text
    # rather than treating it as "no deps" (BUG-2320). Once ENH-2319 lands a
    # shared resolve_learning_targets() this inline extraction collapses into it.
    if issue.learning_tests_required is not None:
        targets = issue.learning_tests_required
    else:
        from little_loops.learning_tests.extractor import extract_learning_targets

        try:
            targets = extract_learning_targets(issue.path.read_text())
        except OSError:
            targets = []

    if not targets:
        logger.info(f"[{issue.issue_id}] Learning gate: no external dependencies detected")
        return True

    logger.info(f"[{issue.issue_id}] Running proof-first-task gate (targets: {', '.join(targets)})")
    cmd = [
        "ll-loop",
        "run",
        "proof-first-task",
        "--context",
        f"issue_file={issue.path}",
        "--context",
        f"targets_csv={','.join(targets)}",
    ]
    gate_result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=worktree_path,
        env=project_child_env(),
    )

    # Function-local import: little_loops.fsm's package __init__ pulls in the
    # executor, which imports little_loops.config — a cycle at module scope.
    from little_loops.fsm.types import FAILURE_TERMINAL_EXIT_CODE

    # ENH-2814: the gate's failure terminals (blocked, impl_failed) carry
    # `failure: true`, so `ll-loop run` exits FAILURE_TERMINAL_EXIT_CODE for
    # them. The old state-file read that distinguished blocked from done is
    # retired — the exit code alone is authoritative.
    if gate_result.returncode == FAILURE_TERMINAL_EXIT_CODE:
        logger.info(f"[{issue.issue_id}] proof-first-task gate: blocked")
        return False

    if gate_result.returncode != 0:
        logger.warning(f"[{issue.issue_id}] proof-first-task exited {gate_result.returncode}")
        return False

    logger.info(f"[{issue.issue_id}] proof-first-task gate: passed")
    return True


class WorkerPool:
    """Thread pool for processing issues in isolated git worktrees.

    Each worker:
    1. Creates a dedicated git worktree and branch
    2. Runs issue validation and implementation via Claude CLI
    3. Commits changes locally
    4. Returns results for merge coordination

    Example:
        >>> pool = WorkerPool(parallel_config, br_config, logger)
        >>> pool.start()
        >>> future = pool.submit(issue_info)
        >>> result = future.result()  # WorkerResult
        >>> pool.shutdown()
    """

    def __init__(
        self,
        parallel_config: ParallelConfig,
        br_config: BRConfig,
        logger: Logger,
        repo_path: Path | None = None,
        git_lock: GitLock | None = None,
        run_id: str | None = None,
        driver: str | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        """Initialize the worker pool.

        Args:
            parallel_config: Parallel processing configuration
            br_config: Project configuration (for category actions)
            logger: Logger for worker output
            repo_path: Path to the git repository (default: current directory)
            git_lock: Shared lock for git operations (created if not provided)
            run_id: Orchestration run this pool belongs to (ENH-2866); together
                with ``driver`` it enables the dequeue-time base-SHA stamp.
                Omitted by a caller that does not record orchestration runs, in
                which case no early row is written.
            driver: Producer identity for the stamp (``ll-parallel`` /
                ``ll-sprint``); see ``run_id``.
            event_bus: Optional EventBus (ENH-3302). When set, a
                ``parallel.epic_branch_stale`` event is emitted whenever an
                epic-branch reuse is warned/merged/conflict-degraded by
                ``_ensure_epic_branch``. Appended last, keyword-optional, so
                existing positional callers (``cli/parallel.py``,
                ``test_subprocess_mocks.py``) remain unaffected.
        """
        self.run_id = run_id
        self.driver = driver
        self._event_bus = event_bus
        self.parallel_config = parallel_config
        self.br_config = br_config
        self.logger = logger
        self.repo_path = repo_path or Path.cwd()
        self._git_lock = git_lock or GitLock(logger)
        self._executor: ThreadPoolExecutor | None = None
        self._active_workers: dict[str, Future[WorkerResult]] = {}
        # Track active subprocesses for forceful termination on shutdown
        self._active_processes: dict[str, subprocess.Popen[str]] = {}
        # Track active worktree paths to prevent cleanup while in use (BUG-142)
        self._active_worktrees: set[Path] = set()
        self._process_lock = threading.Lock()
        # Track callbacks currently executing
        self._pending_callbacks: set[str] = set()
        self._callback_lock = threading.Lock()
        # Shutdown tracking for interrupted worker detection (ENH-036)
        self._shutdown_requested = False
        self._terminated_during_shutdown: set[str] = set()
        # Track worker processing stages for progress visibility (ENH-262)
        self._worker_stages: dict[str, WorkerStage] = {}
        # Cache of EPIC integration branches already created/verified (FEAT-2447)
        self._epic_branches_created: set[str] = set()
        # Per-issue EPIC integration branch a worker forks from / merges into
        # (FEAT-2452); None when the issue is standalone or epic_branches is
        # disabled, in which case git mechanics fall back to base_branch.
        self._worker_epic_branches: dict[str, str | None] = {}

    def start(self) -> None:
        """Start the worker pool."""
        if self._executor is not None:
            return

        # Ensure worktree base directory exists
        worktree_base = self.repo_path / self.parallel_config.worktree_base
        worktree_base.mkdir(parents=True, exist_ok=True)

        self._executor = ThreadPoolExecutor(
            max_workers=self.parallel_config.max_workers,
            thread_name_prefix="issue-worker",
        )
        self.logger.info(f"Worker pool started with {self.parallel_config.max_workers} workers")

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the worker pool.

        Args:
            wait: Whether to wait for pending tasks to complete
        """
        if self._executor is None:
            return

        self.logger.info("Shutting down worker pool...")

        # First, terminate all active subprocesses to unblock worker threads
        if not wait:
            self.terminate_all_processes()

        self._executor.shutdown(wait=wait)
        self._executor = None

    def set_shutdown_requested(self, value: bool = True) -> None:
        """Set the shutdown flag.

        Called by orchestrator during shutdown to enable tracking of
        workers that are terminated due to shutdown vs. actual failures.
        """
        self._shutdown_requested = value

    def terminate_all_processes(self) -> None:
        """Forcefully terminate all active subprocesses.

        Called when we need to abort workers immediately,
        such as on timeout or shutdown.
        """
        with self._process_lock:
            for issue_id, process in list(self._active_processes.items()):
                if process.poll() is None:  # Still running
                    self.logger.warning(
                        f"Terminating subprocess for {issue_id} (PID {process.pid})"
                    )
                    # Track issues terminated during shutdown for interrupted detection (ENH-036)
                    if self._shutdown_requested:
                        self._terminated_during_shutdown.add(issue_id)
                    try:
                        # Send SIGTERM first for graceful termination
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            # Force kill if SIGTERM didn't work
                            self.logger.warning(f"Force killing {issue_id} (PID {process.pid})")
                            process.kill()
                            process.wait(timeout=2)
                    except Exception as e:
                        self.logger.error(f"Failed to terminate {issue_id}: {e}")
            self._active_processes.clear()

    def submit(
        self,
        issue: IssueInfo,
        on_complete: Callable[[WorkerResult], None] | None = None,
    ) -> Future[WorkerResult]:
        """Submit an issue for processing.

        Args:
            issue: Issue to process
            on_complete: Optional callback when processing completes

        Returns:
            Future that will contain the WorkerResult
        """
        if self._executor is None:
            raise RuntimeError("Worker pool not started")

        future = self._executor.submit(self._process_issue, issue)
        with self._process_lock:
            self._active_workers[issue.issue_id] = future

        if on_complete:
            future.add_done_callback(
                lambda f: self._handle_completion(f, on_complete, issue.issue_id)
            )

        return future

    def _handle_completion(
        self,
        future: Future[WorkerResult],
        callback: Callable[[WorkerResult], None],
        issue_id: str,
    ) -> None:
        """Handle worker completion and invoke callback."""
        with self._callback_lock:
            self._pending_callbacks.add(issue_id)
        try:
            try:
                result = future.result()
            except Exception as e:
                self.logger.error(f"Worker future failed for {issue_id}: {e}")
                result = WorkerResult(
                    issue_id=issue_id,
                    success=False,
                    branch_name="",
                    worktree_path=Path(),
                    error=f"Worker future failed: {e}",
                )
            # Set final stage based on result (ENH-262)
            if result.success:
                self.set_worker_stage(issue_id, WorkerStage.COMPLETED)
            elif result.interrupted:
                self.set_worker_stage(issue_id, WorkerStage.INTERRUPTED)
            else:
                self.set_worker_stage(issue_id, WorkerStage.FAILED)
            try:
                callback(result)
            except Exception as e:
                self.logger.error(f"Worker completion callback failed for {issue_id}: {e}")
        finally:
            with self._callback_lock:
                self._pending_callbacks.discard(issue_id)

    def _emit_worker_started(self, issue_id: str, worktree_path: Path, branch: str) -> None:
        """Emit ``parallel.worker_started`` (ENH-3346).

        Called from ``_process_issue`` immediately after worktree creation —
        not from ``submit()`` at dispatch time — because the payload needs
        ``worktree_path``/``branch``, which don't exist until then.

        Args:
            issue_id: The issue this worker is processing (also stamped as
                ``worker_id``)
            worktree_path: Path to the worker's newly created git worktree
            branch: Git branch created for this worker
        """
        if self._event_bus:
            self._event_bus.emit(
                {
                    "event": "parallel.worker_started",
                    "ts": datetime.now(UTC).isoformat(),
                    "run_id": self.run_id,
                    "worker_id": issue_id,
                    "issue_id": issue_id,
                    "worktree_path": str(worktree_path),
                    "branch": branch,
                }
            )

    def _process_issue(self, issue: IssueInfo) -> WorkerResult:
        """Process a single issue in an isolated worktree.

        Args:
            issue: Issue to process

        Returns:
            WorkerResult with processing outcome
        """
        start_time = time.time()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        if self.parallel_config.use_feature_branches:
            from little_loops.issue_parser import slugify

            branch_name = f"feature/{issue.issue_id.lower()}-{slugify(issue.title)}"
        else:
            branch_name = f"parallel/{issue.issue_id.lower()}-{timestamp}"
        worktree_path = (
            self.repo_path
            / self.parallel_config.worktree_base
            / f"worker-{issue.issue_id.lower()}-{timestamp}"
        )

        # Resolve the EPIC integration branch this worker forks from / merges
        # into (FEAT-2452). Both targets are the same string by construction
        # (FEAT-2339 Decision Rationale #1), so we take the fork point. The
        # resolver returns base_branch for standalone issues or when
        # epic_branches is disabled — normalize that no-op case to None so
        # downstream git mechanics (and WorkerResult.epic_branch) stay
        # byte-for-byte identical to today's base_branch behavior.
        fork_point, _ = self._resolve_branch_targets(issue)
        epic_branch: str | None = (
            fork_point if fork_point != self.parallel_config.base_branch else None
        )
        self._worker_epic_branches[issue.issue_id] = epic_branch

        # Set initial stage for progress tracking (ENH-262)
        self.set_worker_stage(issue.issue_id, WorkerStage.SETUP)

        # Capture baseline of main repo status before worker starts
        # Used to detect files incorrectly written to main repo
        baseline_status = self._get_main_repo_baseline()
        # Capture main HEAD SHA before worker starts to detect committed leaks
        baseline_head_sha = self._get_main_head_sha()

        # ENH-2866: the same value is this issue's dequeue-time base state.
        # Normalize the "" _get_main_head_sha() returns on failure to None so
        # NULL-means-unstamped holds all the way to the reader.
        base_sha = baseline_head_sha or None
        base_dirty = self._is_main_repo_dirty()
        # Persist the stamp *now*, not at worker completion: a consumer asking
        # "what tree did this change start from?" reads it while the issue is
        # still in flight. The terminal upsert from
        # ParallelOrchestrator._record_orchestration_result() lands the outcome
        # on the same (run_id, issue_id) row and COALESCEs the stamp through.
        self._record_dequeue_stamp(issue.issue_id, base_sha, base_dirty)

        was_corrected: bool = False
        corrections: list[str] = []

        def _stamped_result(**kwargs: Any) -> WorkerResult:
            """Build a WorkerResult carrying this worker's base-state stamp.

            Every return path inside this method uses it — a failed worker's
            base state is as worth recording as a successful one. Corrections
            are opt-out rather than opt-in for the same reason: a blocked or
            failed worker's corrections are as worth recording as a
            successful one's.
            """
            kwargs.setdefault("was_corrected", was_corrected)
            kwargs.setdefault("corrections", list(corrections))
            return WorkerResult(base_sha=base_sha, base_dirty=base_dirty, **kwargs)

        try:
            # Step 1: Create worktree with new branch. Fork from the EPIC
            # integration branch when set (FEAT-2452); otherwise keep today's
            # base_branch / HEAD behavior.
            self._setup_worktree(
                worktree_path,
                branch_name,
                base_branch=epic_branch
                or (
                    self.parallel_config.base_branch
                    if self.parallel_config.use_feature_branches
                    else None
                ),
            )
            self._emit_worker_started(issue.issue_id, worktree_path, branch_name)
            with suppress(Exception):
                record_session_lifecycle_event(
                    resolve_history_db(),
                    session_id=None,
                    event="worktree_create",
                    detail={
                        "worktree_path": str(worktree_path),
                        "branch": branch_name,
                        "issue_id": issue.issue_id,
                        "parent_sha": baseline_head_sha,
                    },
                )

            # Register worktree as active to prevent cleanup while in use (BUG-142)
            with self._process_lock:
                self._active_worktrees.add(worktree_path)

            # Update stage for progress tracking (ENH-262)
            self.set_worker_stage(issue.issue_id, WorkerStage.VALIDATING)

            # Step 2: Run ready-issue validation
            ready_cmd = self.parallel_config.get_ready_command(issue.issue_id)

            def _run_ready(command: str) -> subprocess.CompletedProcess[str]:
                # Never spawn a retry into a shutdown. Returning non-zero stops
                # run_ready_issue_with_retry; the INTERRUPTED check below then
                # reports the real outcome.
                if issue.issue_id in self._terminated_during_shutdown:
                    return subprocess.CompletedProcess(command, 1, "", "shutdown in progress")
                return self._run_claude_command(
                    command,
                    worktree_path,
                    issue_id=issue.issue_id,
                )

            # An UNKNOWN verdict means the model returned nothing verdict-shaped
            # — a non-compliant turn, not a rejection. Retry it rather than
            # failing the worker (see little_loops.ready_issue).
            ready_parsed, ready_result = run_ready_issue_with_retry(
                target=issue.issue_id,
                initial_command=ready_cmd,
                run=_run_ready,
                config=self.br_config,
                retries=self.br_config.automation.ready_issue_unknown_retries,
                log=self.logger.warning,
            )

            # Track if issue was corrected (corrections stay in worktree).
            # Hoisted here (rather than after the CLOSE/BLOCKED/NOT_READY
            # verdict checks below) so every return path below this point,
            # not just the success path, carries the real values via the
            # _stamped_result closure's opt-out defaults.
            was_corrected = ready_parsed.get("was_corrected", False)
            corrections = ready_parsed.get("corrections", [])

            # Check if worker was terminated during shutdown (ENH-036)
            if issue.issue_id in self._terminated_during_shutdown:
                self.set_worker_stage(issue.issue_id, WorkerStage.INTERRUPTED)
                return _stamped_result(
                    epic_branch=epic_branch,
                    issue_id=issue.issue_id,
                    success=False,
                    interrupted=True,
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    duration=time.time() - start_time,
                    error="Interrupted during shutdown",
                    stdout=ready_result.stdout,
                    stderr=ready_result.stderr,
                )

            if ready_result.returncode != 0:
                err_detail = ready_result.stderr or (ready_result.stdout or "")[:500]
                return _stamped_result(
                    epic_branch=epic_branch,
                    issue_id=issue.issue_id,
                    success=False,
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    duration=time.time() - start_time,
                    error=f"ready-issue failed: {err_detail}",
                    stdout=ready_result.stdout,
                    stderr=ready_result.stderr,
                )

            # Step 3: Check the verdict (already parsed, post-retry, above)

            # Handle CLOSE verdict - issue should not be implemented
            if ready_parsed.get("should_close"):
                return _stamped_result(
                    epic_branch=epic_branch,
                    issue_id=issue.issue_id,
                    success=True,  # Closure is a valid outcome
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    duration=time.time() - start_time,
                    should_close=True,
                    close_reason=ready_parsed.get("close_reason"),
                    close_status=ready_parsed.get("close_status"),
                    stdout=ready_result.stdout,
                    stderr=ready_result.stderr,
                )

            # Handle BLOCKED verdict - issue has open dependencies
            if ready_parsed.get("is_blocked"):
                return _stamped_result(
                    epic_branch=epic_branch,
                    issue_id=issue.issue_id,
                    success=False,
                    was_blocked=True,
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    duration=time.time() - start_time,
                    error="ready-issue verdict: BLOCKED - open dependency detected",
                    stdout=ready_result.stdout,
                    stderr=ready_result.stderr,
                )

            # Handle NOT_READY verdict
            if not ready_parsed["is_ready"]:
                concerns = ready_parsed.get("concerns", [])
                if concerns:
                    concern_msg = "; ".join(concerns)
                elif ready_parsed["verdict"] == "UNKNOWN":
                    # For UNKNOWN verdicts, show a snippet of output for debugging
                    raw_out = (ready_result.stdout or "")[:200].strip()
                    concern_msg = (
                        f"Could not parse verdict. Output: {raw_out}..."
                        if raw_out
                        else "No output from ready-issue"
                    )
                else:
                    concern_msg = "Issue not ready"
                return _stamped_result(
                    epic_branch=epic_branch,
                    issue_id=issue.issue_id,
                    success=False,
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    duration=time.time() - start_time,
                    error=f"ready-issue verdict: {ready_parsed['verdict']} - {concern_msg}",
                    stdout=ready_result.stdout,
                    stderr=ready_result.stderr,
                )

            # Learning test gate: per-worktree proof-first-task wrapper (ENH-2219)
            self.set_worker_stage(issue.issue_id, WorkerStage.PROVING)
            if not _run_per_worktree_proof_first_gate(
                issue, worktree_path, self.br_config, self.parallel_config, self.logger
            ):
                return _stamped_result(
                    epic_branch=epic_branch,
                    issue_id=issue.issue_id,
                    success=False,
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    duration=time.time() - start_time,
                    error="proof-first-task gate blocked",
                )

            # Update stage for progress tracking (ENH-262)
            self.set_worker_stage(issue.issue_id, WorkerStage.IMPLEMENTING)

            # Decision gate: invoke decide-issue when the issue requires a decision
            if issue.decision_needed is True:
                decide_cmd = self.parallel_config.get_decide_command(issue.issue_id)
                decide_result = self._run_claude_command(
                    decide_cmd, worktree_path, issue_id=issue.issue_id
                )
                if decide_result.returncode != 0:
                    self.logger.warning(
                        f"[{issue.issue_id}] decide-issue command failed, "
                        "continuing to implementation anyway..."
                    )

            # Step 4: Get action from BRConfig
            action = self.br_config.get_category_action(issue.issue_type)

            # Step 5: Run manage-issue implementation (with continuation support)
            # Capture the worktree's pre-implement HEAD as the tamper guard's
            # "before" reference (BUG-2954/BUG-2959) -- without this, the guard
            # falls back to the worktree's HEAD *at verification time*, which is
            # blind to any test-weakening the agent commits inside the worktree.
            tamper_baseline_sha = self._get_worktree_head_sha(worktree_path)
            manage_cmd = self.parallel_config.get_manage_command(
                issue.issue_type, action, issue.issue_id
            )
            manage_result = self._run_with_continuation(
                manage_cmd,
                worktree_path,
                issue_id=issue.issue_id,
            )

            # ENH-2958: live post-implement tamper snapshot, captured here
            # (end of Step 5) so _verify_work_was_done can bracket the
            # post-implement window byte-strictly -- Step 8b's committed-leak
            # recovery (below) lands inside this window by design. Imported
            # lazily to avoid a circular import (test_tamper_guard ->
            # config.core -> parallel.types -> parallel -> worker_pool).
            from little_loops.test_tamper_guard import (
                snapshot_test_paths,
                tamper_guard_candidate_paths,
            )

            post_implement_snapshot = snapshot_test_paths(
                tamper_guard_candidate_paths(worktree_path, config=self.br_config), worktree_path
            )

            # Update stage for progress tracking (ENH-262)
            self.set_worker_stage(issue.issue_id, WorkerStage.VERIFYING)

            # Check if worker was terminated during shutdown (ENH-036)
            if issue.issue_id in self._terminated_during_shutdown:
                self.set_worker_stage(issue.issue_id, WorkerStage.INTERRUPTED)
                return _stamped_result(
                    epic_branch=epic_branch,
                    issue_id=issue.issue_id,
                    success=False,
                    interrupted=True,
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    duration=time.time() - start_time,
                    error="Interrupted during shutdown",
                    stdout=manage_result.stdout,
                    stderr=manage_result.stderr,
                )

            # Step 6: Get list of changed files in worktree
            changed_files = self._get_changed_files(worktree_path, issue.issue_id)

            # Step 8: Detect files leaked to main repo instead of worktree (unstaged)
            leaked_files = self._detect_main_repo_leaks(issue.issue_id, baseline_status)
            if leaked_files:
                self.logger.warning(
                    f"{issue.issue_id} leaked {len(leaked_files)} file(s) to main repo: "
                    f"{leaked_files}"
                )
                # Clean up leaked files to prevent stash conflicts during merge.
                # The actual work is preserved in the worktree branch.
                self._cleanup_leaked_files(leaked_files)

            # Step 8b: Detect commits made directly to main instead of worktree branch.
            # If Claude committed to main (not the worktree), worktree will have no diff,
            # causing work verification to fail. Attempt to recover by cherry-picking
            # the leaked commits to the worktree and resetting main. (BUG-580)
            committed_leaks = self._detect_committed_leaks(baseline_head_sha)
            if committed_leaks:
                self.logger.warning(
                    f"{issue.issue_id} committed {len(committed_leaks)} commit(s) directly "
                    f"to main instead of worktree: {[sha[:8] for sha in committed_leaks]}"
                )
                if not changed_files:
                    recovered = self._recover_committed_leaks(
                        committed_leaks, worktree_path, baseline_head_sha, issue.issue_id
                    )
                    if recovered:
                        changed_files = self._get_changed_files(worktree_path, issue.issue_id)

            # Step 7: Verify actual work was done (after potential committed-leak recovery)
            # Pass full filename for better doc-only keyword matching
            issue_filename = issue.path.stem if issue.path else ""
            work_verified, verification_error = self._verify_work_was_done(
                changed_files,
                issue.issue_id,
                issue_filename,
                worktree_path,
                baseline_sha=tamper_baseline_sha,
                pre_step_snapshot=post_implement_snapshot,
            )

            if manage_result.returncode != 0:
                err_detail = manage_result.stderr or (manage_result.stdout or "")[:500]
                return _stamped_result(
                    epic_branch=epic_branch,
                    issue_id=issue.issue_id,
                    success=False,
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    changed_files=changed_files,
                    leaked_files=leaked_files,
                    duration=time.time() - start_time,
                    error=f"manage-issue failed: {err_detail}",
                    stdout=manage_result.stdout,
                    stderr=manage_result.stderr,
                )

            if not work_verified:
                return _stamped_result(
                    epic_branch=epic_branch,
                    issue_id=issue.issue_id,
                    success=False,
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    changed_files=changed_files,
                    leaked_files=leaked_files,
                    duration=time.time() - start_time,
                    error=verification_error,
                    stdout=manage_result.stdout,
                    stderr=manage_result.stderr,
                )

            # Step 9: Update branch base before merge (BUG-180)
            # Fetch origin/main and rebase to ensure branch is based on latest main
            base_updated, base_error = self._update_branch_base(worktree_path, issue.issue_id)

            # Update stage for progress tracking (ENH-262)
            self.set_worker_stage(issue.issue_id, WorkerStage.MERGING)

            if not base_updated:
                return _stamped_result(
                    epic_branch=epic_branch,
                    issue_id=issue.issue_id,
                    success=False,
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    changed_files=changed_files,
                    leaked_files=leaked_files,
                    duration=time.time() - start_time,
                    error=base_error,
                    stdout=manage_result.stdout,
                    stderr=manage_result.stderr,
                )

            return _stamped_result(
                epic_branch=epic_branch,
                issue_id=issue.issue_id,
                success=True,
                branch_name=branch_name,
                worktree_path=worktree_path,
                changed_files=changed_files,
                leaked_files=leaked_files,
                duration=time.time() - start_time,
                error=None,
                stdout=manage_result.stdout,
                stderr=manage_result.stderr,
            )

        except Exception as e:
            return _stamped_result(
                epic_branch=epic_branch,
                issue_id=issue.issue_id,
                success=False,
                branch_name=branch_name,
                worktree_path=worktree_path,
                duration=time.time() - start_time,
                error=str(e),
            )
        finally:
            # Unregister worktree as no longer active (BUG-142)
            with self._process_lock:
                self._active_worktrees.discard(worktree_path)

    def _setup_worktree(
        self, worktree_path: Path, branch_name: str, base_branch: str | None = None
    ) -> None:
        """Create a git worktree with a new branch.

        Args:
            worktree_path: Path for the new worktree
            branch_name: Name of the new branch
            base_branch: Optional commit-ish to fork the branch from; None forks from HEAD.
        """
        from little_loops.worktree_utils import setup_worktree

        setup_worktree(
            repo_path=self.repo_path,
            worktree_path=worktree_path,
            branch_name=branch_name,
            copy_files=self.parallel_config.worktree_copy_files,
            logger=self.logger,
            git_lock=self._git_lock,
            base_branch=base_branch,
        )

        # Verify model if --show-model flag is set (requires API call)
        if self.parallel_config.show_model:
            model = self._detect_worktree_model_via_api(worktree_path)
            if model:
                self.logger.info(f"  Using model: {model}")
            else:
                self.logger.warning("  Could not detect Claude CLI model")

    def _detect_worktree_model_via_api(self, worktree_path: Path) -> str | None:
        """Detect the model Claude will use by making an API call.

        Runs a minimal Claude command with JSON output and parses the modelUsage
        field to verify settings.local.json is being respected.

        Args:
            worktree_path: Path to the worktree to test

        Returns:
            Model name (e.g., "claude-sonnet-4-20250514") or None if unable to detect
        """
        try:
            invocation = resolve_host().build_blocking_json(prompt="reply with just 'ok'")
            # No-perm-skip preserved: this is a detection probe, not a real run.
            args = [a for a in invocation.args if a != "--dangerously-skip-permissions"]

            # Set environment to keep Claude in the project working directory (BUG-007)
            # This ensures the first Claude CLI invocation in the worktree has the same
            # project root behavior as subsequent invocations via run_claude_command()
            env = project_child_env(
                invocation, extra={"CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "1"}
            )

            result = subprocess.run(
                [invocation.binary, *args],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            if result.returncode == 0 and result.stdout.strip():
                data: dict[str, Any] = json.loads(result.stdout.strip())
                model_usage: dict[str, Any] = data.get("modelUsage", {})
                # Return the first (primary) model from modelUsage
                if model_usage:
                    return cast(str, next(iter(model_usage.keys())))
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            pass
        return None

    def _cleanup_worktree(self, worktree_path: Path) -> None:
        """Remove a git worktree and its associated branch.

        Args:
            worktree_path: Path to the worktree to remove
        """
        if not worktree_path.exists():
            return

        # Skip cleanup if worktree is actively in use by a running worker (BUG-142)
        with self._process_lock:
            if worktree_path in self._active_worktrees:
                self.logger.warning(
                    f"Skipping cleanup of {worktree_path.name}: worktree is in active use"
                )
                return

        # Delete ll-managed branches (parallel/* and loop YYYYMMDD-HHMMSS-* shapes)
        from little_loops.worktree_utils import _is_ll_branch

        # ll-no-project: local git plumbing, no host CLI/credentials in play (ENH-3184 AC2)
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        branch_name = branch_result.stdout.strip() if branch_result.returncode == 0 else None
        delete_branch = branch_name is not None and _is_ll_branch(branch_name)

        from little_loops.worktree_utils import cleanup_worktree

        cleanup_worktree(
            worktree_path=worktree_path,
            repo_path=self.repo_path,
            logger=self.logger,
            git_lock=self._git_lock,
            delete_branch=delete_branch,
        )
        with suppress(Exception):
            match = re.match(r"^worker-(.+)-\d{8}-\d{6}$", worktree_path.name)
            record_session_lifecycle_event(
                resolve_history_db(),
                session_id=None,
                event="worktree_delete",
                detail={
                    "worktree_path": str(worktree_path),
                    "branch": branch_name,
                    "issue_id": match.group(1).upper() if match else None,
                },
            )

    def _run_claude_command(
        self,
        command: str,
        working_dir: Path,
        issue_id: str | None = None,
        on_usage: Callable[[int, int], None] | None = None,
        resume_session: bool = False,
        disable_background_tasks: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        """Run a Claude CLI command with real-time output streaming.

        Args:
            command: The command to run (e.g., "/ll:ready-issue BUG-123")
            working_dir: Directory to run the command in
            issue_id: Optional issue ID for subprocess tracking
            on_usage: Optional usage callback for token tracking
            resume_session: If True, passes --continue to the Claude CLI
            disable_background_tasks: FEAT-3078 opt-in to hard-disable
                tool-level background tasks in the spawned child. Forwarded
                to run_claude_command() for parity with the issue_manager.py
                and FSM paths.

        Returns:
            CompletedProcess with stdout and stderr
        """
        stream_output = self.parallel_config.stream_subprocess_output

        def stream_callback(line: str, is_stderr: bool) -> None:
            if stream_output:
                if is_stderr:
                    print(f"  {line}", file=sys.stderr)
                else:
                    self.logger.info(f"  {line}")

        def on_start(process: subprocess.Popen[str]) -> None:
            if issue_id:
                with self._process_lock:
                    self._active_processes[issue_id] = process

        def on_end(process: subprocess.Popen[str]) -> None:
            if issue_id:
                with self._process_lock:
                    self._active_processes.pop(issue_id, None)

        # ENH-3097: this site has no automation_profile= kwarg of its own
        # (pre-existing asymmetry, preserved not fixed) — profile stays None.
        # resolve_automation() returns None for all-default input, preserving
        # today's automation=None on the common path (Decision Rules).
        idle_timeout = self.parallel_config.idle_timeout_per_issue
        automation = resolve_automation(
            None,
            None,
            disable_background_tasks,
            float(idle_timeout) if idle_timeout else None,
            caller="WorkerPool._run_claude_command()",
        )

        return _run_claude_base(
            command=command,
            timeout=self.parallel_config.timeout_per_issue,
            working_dir=working_dir,
            stream_callback=stream_callback if stream_output else None,
            on_process_start=on_start if issue_id else None,
            on_process_end=on_end if issue_id else None,
            automation=automation,
            on_usage=on_usage,
            resume_session=resume_session,
            timeout_kill_grace_seconds=self.parallel_config.timeout_kill_grace_seconds,
            extra_env={"LL_ISSUE_ID": issue_id} if issue_id else None,
        )

    def _check_issue_already_done(self, issue_id: str | None, working_dir: Path) -> bool:
        """Check if the issue file's status indicates work is already complete.

        Pre-continuation guard (BUG-1759): when the inner Claude session hits its
        context limit but the issue was already marked done, skip the handoff and
        return success rather than triggering an unnecessary handoff cycle.

        Args:
            issue_id: Issue identifier (e.g., "BUG-1759"), or None.
            working_dir: Working directory (worktree) to search for issue files.

        Returns:
            True if the issue's status is 'done' or 'cancelled'.
        """
        if issue_id is None:
            return False
        issues_dir = working_dir / ".issues"
        if not issues_dir.exists():
            return False
        try:
            from little_loops.frontmatter import parse_frontmatter

            # Search all category directories for the issue file
            for cat_dir in issues_dir.iterdir():
                if not cat_dir.is_dir():
                    continue
                for f in cat_dir.iterdir():
                    if not f.is_file() or not f.suffix == ".md":
                        continue
                    if f"-{issue_id}-" in f.name or f.name.endswith(f"-{issue_id}.md"):
                        fm = parse_frontmatter(f.read_text(encoding="utf-8"))
                        return fm.get("status") in ("done", "cancelled")
            return False
        except Exception:
            return False

    def _run_with_continuation(
        self,
        command: str,
        working_dir: Path,
        issue_id: str | None = None,
        max_continuations: int = 3,
        context_limit: int | None = None,
        run_dir: str | None = None,
        sprint_context: SprintWorkerContext | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a Claude command with automatic continuation on context handoff.

        Mirrors the E+J logic in issue_manager.run_with_continuation.

        Args:
            command: The command to run
            working_dir: Directory (worktree) to run the command in
            issue_id: Optional issue ID for subprocess tracking
            max_continuations: Maximum number of continuation attempts
            context_limit: Context window size in tokens

        Returns:
            Combined CompletedProcess with all session outputs
        """
        if context_limit is None:
            context_limit = context_window_for(None)
        all_stdout: list[str] = []
        all_stderr: list[str] = []
        current_command = command
        continuation_count = 0
        result: subprocess.CompletedProcess[str] = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr=""
        )
        tag = f"[{issue_id}]" if issue_id else "[worker]"

        # Track token usage per-round for sentinel/guillotine thresholds
        _last_input: list[int] = [0]
        _last_output: list[int] = [0]

        def _usage_tracker(input_tokens: int, output_tokens: int) -> None:
            _last_input[0] = input_tokens
            _last_output[0] = output_tokens

        while continuation_count <= max_continuations:
            result = self._run_claude_command(
                current_command,
                working_dir,
                issue_id=issue_id,
                on_usage=_usage_tracker,
            )

            all_stdout.append(result.stdout)
            all_stderr.append(result.stderr)

            # Standard path: Claude emitted CONTEXT_HANDOFF
            if detect_context_handoff(result.stdout):
                self.logger.info(f"{tag} Detected CONTEXT_HANDOFF signal")

                # Pre-continuation guard: if the issue is already done/cancelled,
                # the work is complete — return success without signalling handoff
                # so the outer FSM doesn't waste a handoff cycle on finished work.
                already_done = self._check_issue_already_done(issue_id, working_dir)
                if already_done:
                    self.logger.info(
                        f"{tag} Issue already done/cancelled; "
                        "skipping handoff and returning success"
                    )
                    result = subprocess.CompletedProcess(
                        args=result.args,
                        returncode=0,
                        stdout=result.stdout,
                        stderr=result.stderr,
                    )
                    break

                # Forward CONTEXT_HANDOFF signal to stdout so the outer FSM's
                # signal_detector can detect it via the existing HANDOFF_SIGNAL pattern.
                handoff_message = "CONTEXT_HANDOFF: Ready for fresh session"
                print(handoff_message)
                self.logger.info(f"{tag} Forwarded handoff signal to stdout; exiting cleanly")

                result = subprocess.CompletedProcess(
                    args=result.args,
                    returncode=0,
                    stdout=result.stdout + "\n" + handoff_message,
                    stderr=result.stderr,
                )
                break

            prompt_too_long = "prompt is too long" in (result.stderr or "").lower()

            # Option J: guillotine — fires only on the reliable "Prompt is too long" stderr
            # signal (BUG-2280). When run_dir is set (loop context), write a resume file and
            # invoke /ll:resume. Otherwise fall back to the transcript-summary blob.
            if prompt_too_long and continuation_count < max_continuations:
                # Pre-continuation guard (BUG-2281): mirror the CONTEXT_HANDOFF branch —
                # if the issue is already done/cancelled, return success without spawning.
                if self._check_issue_already_done(issue_id, working_dir):
                    self.logger.info(
                        f"{tag} Issue already done/cancelled; skipping Option J continuation"
                    )
                    result = subprocess.CompletedProcess(
                        args=result.args,
                        returncode=0,
                        stdout=result.stdout,
                        stderr=result.stderr,
                    )
                    break
                trigger_reason = "Prompt is too long"
                self.logger.warning(
                    f"{tag} Option J triggered ({trigger_reason}): spawning fresh session"
                )
                if run_dir is not None:
                    try:
                        guillotine_file = Path(run_dir) / "guillotine-prompt.md"
                        guillotine_file.parent.mkdir(parents=True, exist_ok=True)
                        task_first_line = (command.strip().splitlines() or [""])[0]
                        sprint_framing = ""
                        if sprint_context is not None:
                            sprint_framing = (
                                f"## Sprint Worker Context\n"
                                f"You are a sprint worker. Process exactly ONE issue: "
                                f"{sprint_context.issue_id}\n"
                                f"After completing this issue, exit immediately — "
                                f"do NOT process other issues.\n"
                                f"Do NOT ask for further instructions. Exit with code 0.\n"
                                f"Branch: {sprint_context.branch}\n\n"
                            )
                        guillotine_file.write_text(
                            sprint_framing + f"## Intent\n"
                            f"Resume an interrupted automation session that hit the context limit.\n"
                            f"Original task: {task_first_line}\n"
                            f"Trigger reason: {trigger_reason} "
                            f"({_last_input[0] + _last_output[0]:,} / {context_limit:,} tokens)\n"
                            f"\n"
                            f"## Next Steps\n"
                            f"1. Check `git log` to see what was committed in the previous session\n"
                            f"2. Check the issue file status — if already done/cancelled, stop\n"
                            f"3. Review `.loops/tmp/scratch/` for partial progress notes\n"
                            f"4. Continue the original task from where it left off, "
                            f"skipping already-completed work\n",
                            encoding="utf-8",
                        )
                        guillotine_cmd = f"/ll:resume {guillotine_file}"
                        self.logger.info(f"{tag} Option J resume file written: {guillotine_file}")
                    except Exception as exc:
                        self.logger.warning(
                            f"{tag} Failed to write guillotine resume file ({exc}), "
                            "falling back to summary blob"
                        )
                        guillotine_cmd = command
                else:
                    try:
                        guillotine_cmd = assemble_guillotine_prompt(
                            original_command=command,
                            captured_stdout="\n---CONTINUATION---\n".join(all_stdout),
                            token_stats={
                                "input_tokens": _last_input[0],
                                "output_tokens": _last_output[0],
                                "context_limit": context_limit,
                                "trigger_reason": trigger_reason,
                            },
                            sprint_context=sprint_context,
                        )
                    except Exception as exc:
                        self.logger.warning(
                            f"{tag} Failed to assemble guillotine prompt ({exc}), "
                            "using bare restart"
                        )
                        guillotine_cmd = command
                continuation_count += 1
                current_command = guillotine_cmd
                _last_input[0] = 0
                _last_output[0] = 0
                continue

            # Option E: read sentinel from a PREVIOUS session (must run before G writes
            # the current-session sentinel to avoid immediately consuming our own write).
            sentinel_data = read_sentinel(working_dir)
            if sentinel_data is not None and continuation_count < max_continuations:
                usage_pct = sentinel_data.get("usage_percent", 0)
                self.logger.info(
                    f"{tag} Sentinel detected ({usage_pct}% context used): "
                    "sending explicit handoff instruction"
                )
                continuation_count += 1
                explicit_handoff_instruction = (
                    f"Context limit is approaching ({usage_pct}% of the context window is used). "
                    "Please run /ll:handoff RIGHT NOW to save your progress to "
                    ".ll/ll-continue-prompt.md, then output "
                    '"CONTEXT_HANDOFF: Ready for fresh session" to signal continuation.'
                )
                _last_input[0] = 0
                _last_output[0] = 0
                result = self._run_claude_command(
                    explicit_handoff_instruction,
                    working_dir,
                    issue_id=issue_id,
                    on_usage=_usage_tracker,
                    resume_session=True,
                )
                all_stdout.append(result.stdout)
                all_stderr.append(result.stderr)

                if detect_context_handoff(result.stdout):
                    self.logger.info(
                        f"{tag} CONTEXT_HANDOFF detected after explicit handoff instruction"
                    )
                    prompt_content = read_continuation_prompt(working_dir)
                    if prompt_content and continuation_count < max_continuations:
                        continuation_count += 1
                        self.logger.info(
                            f"{tag} Starting continuation session #{continuation_count}"
                        )
                        current_command = f"{command} --resume"
                        _last_input[0] = 0
                        _last_output[0] = 0
                        continue
                break

            # No handoff signal, no prior-session sentinel, no overflow — done
            break

        return subprocess.CompletedProcess(
            args=result.args,
            returncode=result.returncode,
            stdout="\n---CONTINUATION---\n".join(all_stdout),
            stderr="\n---CONTINUATION---\n".join(all_stderr),
        )

    def _get_changed_files(self, worktree_path: Path, issue_id: str | None = None) -> list[str]:
        """Get list of files changed in the worktree.

        Args:
            worktree_path: Path to the worktree
            issue_id: Issue ID used to look up the EPIC integration branch to
                diff against (FEAT-2452); when the worker has an epic branch
                set, files are diffed against it instead of ``base_branch``.

        Returns:
            List of changed file paths relative to repo root
        """
        diff_base = self.parallel_config.base_branch
        if issue_id is not None:
            epic_branch = self._worker_epic_branches.get(issue_id)
            if epic_branch:
                diff_base = epic_branch
        # ll-no-project: local git plumbing, no host CLI/credentials in play (ENH-3184 AC2)
        result = subprocess.run(
            ["git", "diff", "--name-only", diff_base, "HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return []

        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

    def _update_branch_base(self, worktree_path: Path, issue_id: str) -> tuple[bool, str]:
        """Fetch origin/main and rebase worker branch onto it.

        This ensures the worker branch is based on the latest main before
        merge coordination, preventing conflicts when main advances during
        sprint execution (BUG-180).

        Args:
            worktree_path: Path to the worker's worktree
            issue_id: Issue ID for logging

        Returns:
            Tuple of (success, error_message)
        """
        # EPIC integration branches are local-only (created off base_branch by
        # _resolve_branch_targets), so rebase directly onto the local branch
        # without a remote fetch (FEAT-2452). Standalone issues keep today's
        # fetch-then-rebase-onto-remote behavior.
        epic_branch = self._worker_epic_branches.get(issue_id)
        if epic_branch:
            rebase_target = epic_branch
        else:
            # Fetch latest base branch from configured remote (fall back to
            # local if fetch fails)
            base = self.parallel_config.base_branch
            remote = self.parallel_config.remote_name
            # ll-no-project: local git plumbing (fetch), no host CLI/credentials in play (ENH-3184 AC2)
            fetch_result = subprocess.run(
                ["git", "fetch", remote, base],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

            rebase_target = f"{remote}/{base}" if fetch_result.returncode == 0 else base

        # Rebase current branch onto base (remote or local fallback)
        # ll-no-project: local git plumbing (rebase), no host CLI/credentials in play (ENH-3184 AC2)
        rebase_result = subprocess.run(
            ["git", "rebase", rebase_target],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if rebase_result.returncode != 0:
            # Abort the failed rebase
            # ll-no-project: local git plumbing (rebase --abort), no host CLI/credentials in play (ENH-3184 AC2)
            subprocess.run(
                ["git", "rebase", "--abort"],
                cwd=worktree_path,
                capture_output=True,
                timeout=10,
            )
            return False, f"Failed to rebase onto {rebase_target}: {rebase_result.stderr}"

        self.logger.info(f"[{issue_id}] Rebased branch onto {rebase_target}")
        return True, ""

    def _verify_work_was_done(
        self,
        changed_files: list[str],
        issue_id: str,
        issue_filename: str = "",
        worktree_path: Path | None = None,
        baseline_sha: str | None = None,
        pre_step_snapshot: TamperSnapshot | None = None,
    ) -> tuple[bool, str]:
        """Verify that actual implementation work was done.

        Uses the shared verify_work_was_done() function to check that changed
        files include meaningful work, not just issue files or other artifacts.

        Args:
            changed_files: List of files changed during processing
            issue_id: The issue ID being processed (unused, kept for compatibility)
            issue_filename: Full issue filename (unused, kept for compatibility)
            worktree_path: Worktree the tamper guard (ENH-2933/ENH-2935) runs
                against; defaults to cwd when omitted.
            baseline_sha: Worktree HEAD captured before Phase 2 began (BUG-2954/
                BUG-2959) -- the tamper guard's "before" reference. Without it,
                the guard falls back to the worktree's HEAD at verification
                time, which is blind to test-weakening the agent already
                committed inside the worktree.
            pre_step_snapshot: Live snapshot captured right after Step 5's
                implement call returns (ENH-2958) -- the tamper guard's
                post-implement "before" reference, bracketing everything from
                the end of implement through Step 8b's committed-leak
                recovery.

        Returns:
            Tuple of (success, error_message)
        """
        if not changed_files:
            return False, "No files were changed during implementation"

        # Check if code changes are required
        if not self.parallel_config.require_code_changes:
            return True, ""

        # Use shared verification function
        if verify_work_was_done(
            self.logger,
            changed_files,
            baseline_sha=baseline_sha,
            config=self.br_config,
            repo_root=worktree_path,
            pre_step_snapshot=pre_step_snapshot,
            issue_id=issue_id,
            git_lock=self._git_lock,
        ):
            return True, ""

        # Generate descriptive error with actual excluded files
        excluded_files = [
            f
            for f in changed_files
            if f and any(f.startswith(excl) for excl in EXCLUDED_DIRECTORIES)
        ]
        if excluded_files:
            files_preview = ", ".join(excluded_files[:5])
            if len(excluded_files) > 5:
                files_preview += f" (+{len(excluded_files) - 5} more)"
            return False, f"Only excluded files modified: {files_preview}"
        return False, "Only excluded files modified (e.g., .issues/, thoughts/)"

    def _has_other_issue_id(self, file_lower: str, current_issue_id_lower: str) -> bool:
        """Check if file contains a different issue ID than the current worker's.

        This prevents cross-worker contamination where worker A detects worker B's
        leaked file. When multiple workers run in parallel, their leaked files may
        both appear in the main repo. Each worker should only clean up its own leaks.

        Args:
            file_lower: Lowercase file path to check
            current_issue_id_lower: Lowercase issue ID of the current worker

        Returns:
            True if the file contains a different issue ID (belongs to another worker),
            False if the file contains the current issue ID or no recognizable issue ID
        """
        # Pattern matches common issue ID formats: BUG-123, ENH-456, FEAT-789, EPIC-001
        # Use non-capturing group (?:...) so findall returns full match, not group
        matches = re.findall(r"(?:bug|enh|feat|epic)-\d+", file_lower)

        if not matches:
            # No issue ID found - file doesn't belong to any specific worker
            return False

        # Check if any of the found issue IDs match the current worker
        for match in matches:
            if match == current_issue_id_lower:
                return False  # File belongs to current worker

        # File has issue ID(s) but none match current worker - belongs to another worker
        return True

    def _detect_main_repo_leaks(self, issue_id: str, baseline_status: set[str]) -> list[str]:
        """Detect files incorrectly written to main repo instead of worktree.

        Claude Code may write files to the main repository instead of the
        worktree due to project root detection issues (see GitHub #8771).
        This method detects such leaks by comparing main repo status before
        and after worker execution.

        Args:
            issue_id: ID of the issue being processed (for pattern matching)
            baseline_status: Set of file paths from git status before worker started

        Returns:
            List of file paths that were leaked to main repo
        """
        # Get current status of main repo
        result = self._git_lock.run(
            ["status", "--porcelain"],
            cwd=self.repo_path,
            timeout=30,
        )

        if result.returncode != 0:
            return []

        current_files: set[str] = set()
        for line in result.stdout.strip().split("\n"):
            if not line or len(line) < 3:
                continue
            # Extract file path (after status codes and space)
            file_path = line[3:].strip()
            # Handle renamed files (old -> new)
            if " -> " in file_path:
                file_path = file_path.split(" -> ")[-1]
            current_files.add(file_path)

        # Find new files that appeared during worker execution
        new_files = current_files - baseline_status

        # Filter to files likely related to this issue
        issue_id_lower = issue_id.lower()
        leaked_files: list[str] = []

        # Build source prefix list: start with common fallbacks, then add configured dirs
        source_prefixes = ["backend/", "src/", "lib/", "tests/"]
        for dir_path in [self.br_config.project.src_dir, self.br_config.project.test_dir]:
            if dir_path:
                normalized = dir_path.rstrip("/") + "/"
                if normalized not in source_prefixes:
                    source_prefixes.append(normalized)

        for file_path in new_files:
            # Skip state file (managed by orchestrator)
            if file_path.endswith(".parallel-manage-state.json"):
                continue
            # Skip .gitignore (may be modified by ll-parallel)
            if file_path == ".gitignore":
                continue

            # Check if file is related to this issue
            file_lower = file_path.lower()
            if issue_id_lower in file_lower:
                leaked_files.append(file_path)
            # Also catch source files that shouldn't be modified in main
            elif file_path.startswith(tuple(source_prefixes)):
                leaked_files.append(file_path)
            # Catch thoughts/plans files
            elif file_path.startswith("thoughts/"):
                leaked_files.append(file_path)
            # Catch issue files in any issue directory variant
            # Handles both .issues/ (with dot) and issues/ (without dot)
            # Only include files without a different issue ID - files WITH other issue IDs
            # belong to other workers running in parallel (cross-worker contamination)
            elif file_path.startswith((".issues/", "issues/")):
                if not self._has_other_issue_id(file_lower, issue_id_lower):
                    leaked_files.append(file_path)

        return leaked_files

    def _cleanup_leaked_files(self, leaked_files: list[str]) -> int:
        """Discard leaked files from main repo working directory.

        Claude Code sometimes writes files to the main repo instead of the
        worktree. These files cause stash conflicts during merge operations.
        Since the actual work is preserved in the worktree branch, we can
        safely discard these leaked changes from the main repo.

        Args:
            leaked_files: List of file paths leaked to main repo

        Returns:
            Number of files successfully cleaned up
        """
        if not leaked_files:
            return 0

        cleaned = 0

        # Get status to determine which files are tracked vs untracked
        status_result = self._git_lock.run(
            ["status", "--porcelain", "--"] + leaked_files,
            cwd=self.repo_path,
            timeout=30,
        )

        tracked_files: list[str] = []
        untracked_files: list[str] = []

        for line in status_result.stdout.splitlines():
            if not line or len(line) < 3:
                continue
            status_code = line[:2]
            file_path = line[3:].split(" -> ")[-1].strip()

            if status_code.startswith("?"):
                # Untracked file - need to delete
                untracked_files.append(file_path)
            else:
                # Tracked file - can use git checkout to discard
                tracked_files.append(file_path)

        # Discard changes to tracked files
        if tracked_files:
            checkout_result = self._git_lock.run(
                ["checkout", "--"] + tracked_files,
                cwd=self.repo_path,
                timeout=30,
            )
            if checkout_result.returncode == 0:
                cleaned += len(tracked_files)
            else:
                self.logger.warning(
                    f"Failed to discard tracked leaked files: {checkout_result.stderr}"
                )

        # Delete untracked files
        for file_path in untracked_files:
            full_path = self.repo_path / file_path
            try:
                if full_path.exists():
                    full_path.unlink()
                    cleaned += 1
            except OSError as e:
                self.logger.warning(f"Failed to delete leaked file {file_path}: {e}")

        # Fallback: directly delete files not reported by git status
        # This handles gitignored files that git status --porcelain doesn't show
        accounted_files = set(tracked_files + untracked_files)
        for file_path in leaked_files:
            if file_path not in accounted_files:
                full_path = self.repo_path / file_path
                if full_path.exists():
                    try:
                        full_path.unlink()
                        cleaned += 1
                        self.logger.info(f"Deleted gitignored leaked file: {file_path}")
                    except OSError as e:
                        self.logger.warning(
                            f"Failed to delete gitignored leaked file {file_path}: {e}"
                        )
                else:
                    self.logger.debug(f"Leaked file not found (may have been moved): {file_path}")

        if cleaned > 0:
            self.logger.info(f"Cleaned up {cleaned} leaked file(s) from main repo")

        return cleaned

    def _get_main_repo_baseline(self) -> set[str]:
        """Get baseline of modified/untracked files in main repo.

        Returns:
            Set of file paths currently showing in git status
        """
        result = self._git_lock.run(
            ["status", "--porcelain"],
            cwd=self.repo_path,
            timeout=30,
        )

        if result.returncode != 0:
            return set()

        files: set[str] = set()
        for line in result.stdout.strip().split("\n"):
            if not line or len(line) < 3:
                continue
            file_path = line[3:].strip()
            if " -> " in file_path:
                file_path = file_path.split(" -> ")[-1]
            files.add(file_path)

        return files

    def _get_main_head_sha(self) -> str:
        """Get the current HEAD SHA of the main repo.

        Returns:
            HEAD SHA string, or empty string if unavailable
        """
        result = self._git_lock.run(
            ["rev-parse", "HEAD"],
            cwd=self.repo_path,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return ""

    def _is_main_repo_dirty(self) -> bool | None:
        """Whether the main repo has *tracked* modifications right now (ENH-2866).

        ``--untracked-files=no`` is deliberate: a base-state consumer
        reconstructs the tree by checkout, so only tracked modifications make
        that reconstruction approximate — an untracked scratch file does not.

        Returns:
            True/False, or None when git could not be consulted (the stamp is
            advisory, so an unknown dirty state is recorded as unstamped rather
            than guessed as clean).
        """
        result = self._git_lock.run(
            ["status", "--porcelain", "--untracked-files=no"],
            cwd=self.repo_path,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        return bool(result.stdout.strip())

    def _record_dequeue_stamp(
        self, issue_id: str, base_sha: str | None, base_dirty: bool | None
    ) -> None:
        """Write the dequeue-time base-state row for *issue_id* (ENH-2866).

        A ``status="running"`` upsert issued before the worktree exists, so the
        stamp is readable while the issue is in flight. Skipped when this pool
        has no orchestration identity. Never propagates a failure: the stamp is
        advisory and must not take a worker down.
        """
        if not self.run_id or not self.driver:
            return
        with suppress(Exception):
            record_orchestration_run(
                resolve_history_db(),
                run_id=self.run_id,
                driver=self.driver,
                issue_id=issue_id,
                status="running",
                base_sha=base_sha,
                base_dirty=base_dirty,
            )

    def _get_worktree_head_sha(self, worktree_path: Path) -> str:
        """Get the current HEAD SHA of *worktree_path*, or "" if unavailable.

        Used as the tamper guard's pre-implement ``baseline_sha`` reference
        (BUG-2954/BUG-2959) -- distinct from ``_get_main_head_sha``, which
        tracks the main repo's HEAD for committed-leak detection. Called
        before the worktree is guaranteed to exist yet (e.g. worktree setup
        failed upstream), so a missing directory is tolerated the same as any
        other git failure -- the tamper guard falls back to its own default
        ("HEAD" at verification time) when this returns "".
        """
        try:
            result = self._git_lock.run(
                ["rev-parse", "HEAD"],
                cwd=worktree_path,
                timeout=10,
            )
        except OSError:
            return ""
        if result.returncode == 0:
            return result.stdout.strip()
        return ""

    def _detect_committed_leaks(self, baseline_head_sha: str) -> list[str]:
        """Detect commits made directly to main repo during worker execution.

        When Claude commits to the main repo instead of the worktree branch,
        the commits appear on main's history but the worktree has no changes.
        This method detects such leaked commits by comparing main's HEAD SHA
        before and after worker execution.

        Args:
            baseline_head_sha: HEAD SHA captured before worker started

        Returns:
            List of commit SHAs committed to main during worker execution,
            newest first. Empty list if no committed leaks detected.
        """
        if not baseline_head_sha:
            return []

        current_sha = self._get_main_head_sha()
        if not current_sha or current_sha == baseline_head_sha:
            return []

        # Get list of new commits on main since baseline
        result = self._git_lock.run(
            ["log", "--format=%H", f"{baseline_head_sha}..HEAD"],
            cwd=self.repo_path,
            timeout=30,
        )
        if result.returncode != 0:
            return []

        commits = [sha.strip() for sha in result.stdout.strip().split("\n") if sha.strip()]
        return commits

    def _recover_committed_leaks(
        self,
        leaked_commits: list[str],
        worktree_path: Path,
        baseline_head_sha: str,
        issue_id: str,
    ) -> bool:
        """Attempt to recover committed leaks by cherry-picking to worktree.

        When Claude commits directly to main instead of the worktree branch,
        we attempt to:
          1. Cherry-pick the leaked commits onto the worktree branch
          2. Reset main back to the baseline SHA (if safe to do so)

        This preserves the implementation work in the worktree while
        cleaning up the incorrect commits on main.

        Args:
            leaked_commits: Commit SHAs that leaked to main (newest first)
            worktree_path: Path to the worker's worktree
            baseline_head_sha: Main HEAD SHA before worker started
            issue_id: Issue ID for logging

        Returns:
            True if cherry-pick succeeded (main reset is attempted but
            not required for a True return value)
        """
        self.logger.info(
            f"[{issue_id}] Attempting recovery: cherry-picking {len(leaked_commits)} "
            f"commit(s) to worktree"
        )

        # Cherry-pick in chronological order (oldest first = reverse of log output)
        for sha in reversed(leaked_commits):
            # ll-no-project: local git plumbing (cherry-pick), no host CLI/credentials in play (ENH-3184 AC2)
            result = subprocess.run(
                ["git", "cherry-pick", sha],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                # ll-no-project: local git plumbing (cherry-pick --abort), no host CLI/credentials in play (ENH-3184 AC2)
                subprocess.run(
                    ["git", "cherry-pick", "--abort"],
                    cwd=worktree_path,
                    capture_output=True,
                    timeout=10,
                )
                self.logger.warning(
                    f"[{issue_id}] Cherry-pick of {sha[:8]} failed: {result.stderr.strip()}"
                )
                return False

        # Attempt to reset main to baseline (only if main hasn't advanced further)
        current_main_sha = self._get_main_head_sha()
        most_recent_leaked = leaked_commits[0]  # Newest first
        if current_main_sha == most_recent_leaked:
            reset_result = self._git_lock.run(
                ["reset", "--hard", baseline_head_sha],
                cwd=self.repo_path,
                timeout=30,
            )
            if reset_result.returncode == 0:
                self.logger.info(f"[{issue_id}] Reset main to baseline {baseline_head_sha[:8]}")
            else:
                self.logger.warning(
                    f"[{issue_id}] Cherry-pick succeeded but failed to reset main: "
                    f"{reset_result.stderr.strip()}"
                )
        else:
            # main has advanced past the leaked commits — attempt surgical rebase
            # to excise only the leaked commits while preserving subsequent work
            self.logger.info(
                f"[{issue_id}] Main has advanced beyond leaked commits "
                f"({current_main_sha[:8]} != {most_recent_leaked[:8]}) — "
                f"attempting surgical rebase to excise leaked commits"
            )
            rebase_result = self._git_lock.run(
                ["rebase", "--onto", baseline_head_sha, most_recent_leaked],
                cwd=self.repo_path,
                timeout=60,
            )
            if rebase_result.returncode == 0:
                self.logger.info(f"[{issue_id}] Surgically removed leaked commits via rebase")
            else:
                self._git_lock.run(
                    ["rebase", "--abort"],
                    cwd=self.repo_path,
                    timeout=10,
                )
                self.logger.warning(
                    f"[{issue_id}] Surgical rebase failed — manual cleanup required: "
                    f"{rebase_result.stderr.strip()}"
                )

        self.logger.info(
            f"[{issue_id}] Recovered {len(leaked_commits)} commit(s): "
            f"cherry-picked to worktree branch"
        )
        return True

    def _resolve_branch_targets(self, issue: IssueInfo) -> tuple[str, str]:
        """Return ``(fork_point, merge_target)`` for ``issue`` (FEAT-2447).

        Semantics:
        - ``epic_branches.enabled is False`` or ``issue.parent is None``:
          return ``(base_branch, base_branch)`` — no-op, identical to today's
          behavior so ``merge_coordinator.py`` consumer sites remain unchanged.
        - ``epic_branches.enabled is True`` and the issue has an EPIC ancestor:
          return ``(epic/<EPIC-ID>-<slug>, epic/<EPIC-ID>-<slug>)``, flattened
          to the **nearest** EPIC ancestor (cycle-guarded walk modeled on
          ``cli/issues/list_cmd.py::_find_epic_ancestor``).

        The branch is created lazily off ``base_branch`` on first call per
        ``epic_id``; subsequent calls are idempotent via
        ``self._epic_branches_created``.
        """
        base = self.parallel_config.base_branch
        if not self.parallel_config.epic_branches.enabled:
            return (base, base)
        epic_id = self._find_nearest_epic_ancestor(issue)
        if epic_id is None:
            return (base, base)
        from little_loops.worktree_utils import (
            resolve_epic_base,
            resolve_epic_branch_name,
        )

        slug = self._load_epic_slug(epic_id)
        prefix = self.parallel_config.epic_branches.prefix
        branch = resolve_epic_branch_name(epic_id, prefix, slug)
        epic_base = resolve_epic_base(
            epic_id,
            self.parallel_config.base_branch,
            self.repo_path,
            self.br_config,
        )
        self._ensure_epic_branch(branch, epic_base)
        return (branch, branch)

    def _find_nearest_epic_ancestor(self, issue: IssueInfo) -> str | None:
        """Walk ``issue.parent`` chain upward; return nearest ``EPIC-*`` ID or None.

        Delegates the walk to the shared module helper
        ``little_loops.issue_progress.find_nearest_epic_ancestor`` (FEAT-2561),
        supplying the disk-scanned ``_build_parent_map``. Behavior-preserving:
        the helper is the walk lifted verbatim from this method.
        """
        from little_loops.issue_progress import find_nearest_epic_ancestor

        return find_nearest_epic_ancestor(issue, self._build_parent_map())

    def _build_parent_map(self) -> dict[str, str | None]:
        """Build ``{issue_id: parent_id}`` by scanning ``.issues/`` markdown files.

        Used by ``_find_nearest_epic_ancestor`` for the multi-hop parent walk.
        Cached on the instance after first build.
        """
        cached = getattr(self, "_parent_map_cache", None)
        if cached is not None:
            return cached
        from little_loops.issue_parser import IssueParser

        parent_map: dict[str, str | None] = {}
        issues_base = self.repo_path / ".issues"
        if issues_base.is_dir():
            parser = IssueParser(self.br_config)
            for category_dir in issues_base.iterdir():
                if not category_dir.is_dir():
                    continue
                for issue_file in category_dir.glob("*.md"):
                    try:
                        info = parser.parse_file(issue_file)
                    except Exception:  # noqa: BLE001 — skip malformed files
                        continue
                    parent_map[info.issue_id] = info.parent
        self._parent_map_cache = parent_map
        return parent_map

    def _load_epic_slug(self, epic_id: str) -> str:
        """Return a slug for the EPIC, derived from its title or fallback to ID.

        Slug source is the EPIC's title (per FEAT-2447 implementation guidance),
        via the shared ``slugify()`` in ``little_loops.issue_parser``. If the EPIC
        title cannot be resolved (file missing or malformed), fall back to a
        slug of the EPIC ID alone (e.g. ``"epic-2451"``).
        """
        from little_loops.issue_parser import IssueParser, slugify

        issues_base = self.repo_path / ".issues"
        if issues_base.is_dir():
            parser = IssueParser(self.br_config)
            for category_dir in issues_base.iterdir():
                if not category_dir.is_dir():
                    continue
                for issue_file in category_dir.glob(f"P?-{epic_id}-*.md"):
                    try:
                        info = parser.parse_file(issue_file)
                    except Exception:  # noqa: BLE001
                        continue
                    if info.title:
                        return slugify(info.title)
        return epic_id.lower()

    def _ensure_epic_branch(self, branch: str, base: str) -> None:
        """Lazily create ``branch`` off ``base``, guarding reuse against staleness.

        Idempotent via ``self._epic_branches_created`` (in-memory cache hit ->
        return; the guard fires once per run per branch, at first touch). Thin
        wrapper over ``worktree_utils.ensure_epic_branch()`` (ENH-3302), the
        shared exists-check/staleness/merge implementation also used by the
        ``checkout_epic_branch`` FSM state — no ``run_dir`` here (``WorkerPool``
        holds only ``run_id``), so a merge conflict's diagnostic detail goes
        into the emitted event/log line instead of a persisted artifact.

        ``base`` is the EPIC fork base resolved via
        ``worktree_utils.resolve_epic_base`` (ENH-2656).
        """
        if branch in self._epic_branches_created:
            return

        from little_loops.worktree_utils import ensure_epic_branch

        status = ensure_epic_branch(
            branch,
            base,
            repo_path=self.repo_path,
            git_lock=self._git_lock,
            logger=self.logger,
            remote_name=self.parallel_config.remote_name,
            refresh_on_reuse=self.parallel_config.epic_branches.refresh_on_reuse,
        )
        self._epic_branches_created.add(branch)

        if status.action in ("warned", "merged", "merge_conflict") and self._event_bus:
            self._event_bus.emit(
                {
                    "event": "parallel.epic_branch_stale",
                    "ts": datetime.now(UTC).isoformat(),
                    "run_id": self.run_id,
                    "branch": status.branch,
                    "base": status.base,
                    "commits_behind": status.commits_behind,
                    "mode": self.parallel_config.epic_branches.refresh_on_reuse,
                    "action": status.action,
                }
            )

    @property
    def active_count(self) -> int:
        """Number of currently active workers.

        Includes both workers with running futures AND workers whose futures
        are done but callbacks haven't completed yet.
        """
        with self._process_lock:
            running_futures = sum(1 for f in self._active_workers.values() if not f.done())
        with self._callback_lock:
            pending_callback_count = len(self._pending_callbacks)
        return running_futures + pending_callback_count

    def set_worker_stage(self, issue_id: str, stage: WorkerStage) -> None:
        """Update the stage of a worker.

        Args:
            issue_id: Issue ID being processed
            stage: New stage value
        """
        with self._process_lock:
            self._worker_stages[issue_id] = stage

    def get_worker_stage(self, issue_id: str) -> WorkerStage | None:
        """Get the current stage of a worker.

        Args:
            issue_id: Issue ID being processed

        Returns:
            Current stage, or None if issue not being tracked
        """
        with self._process_lock:
            return self._worker_stages.get(issue_id)

    def get_active_stages(self) -> dict[str, WorkerStage]:
        """Get all active worker stages.

        Returns:
            Dictionary mapping issue_id to current stage for active workers
        """
        with self._process_lock:
            # Only return workers that are actually active
            active_ids = set(self._active_workers.keys())
            return {
                issue_id: stage
                for issue_id, stage in self._worker_stages.items()
                if issue_id in active_ids
            }

    def remove_worker_stage(self, issue_id: str) -> None:
        """Remove a worker from stage tracking.

        Args:
            issue_id: Issue ID to remove
        """
        with self._process_lock:
            self._worker_stages.pop(issue_id, None)

    def cleanup_all_worktrees(self) -> None:
        """Clean up all worker worktrees."""
        worktree_base = self.repo_path / self.parallel_config.worktree_base
        if not worktree_base.exists():
            return

        from little_loops.worktree_utils import _is_ll_worktree

        for worktree_dir in worktree_base.iterdir():
            if worktree_dir.is_dir() and _is_ll_worktree(worktree_dir.name):
                self._cleanup_worktree(worktree_dir)

    def prune_merged_feature_branches(
        self, base_branch: str, dry_run: bool = False
    ) -> tuple[list[str], list[str]]:
        """Delete local feature/* branches already merged into base_branch.

        Uses ``git branch --merged <base_branch>`` to detect fast-forward and
        merge-commit histories, then cross-checks remaining ``feature/`` branches
        via :func:`~.github_utils.is_pr_merged` to handle squash- and
        rebase-merged PRs.  When ``gh`` is absent the cross-check returns False
        for every branch, so only ``--merged``-detected branches are pruned.

        The ``feature/*``-only scope is intentional: ``epic/*`` integration
        branches (FEAT-2339) are deleted explicitly by the EPIC
        completion-merge step, never auto-pruned here, so restricting this
        sweep to ``feature/`` is by design, not a bug (FEAT-2339 Decision
        Rationale #3).

        Args:
            base_branch: Branch that acts as the merge target (e.g. ``"main"``).
            dry_run: If True, list candidates but do not delete anything.

        Returns:
            (pruned, skipped): names of branches that were (or would be) deleted,
            and branches where deletion failed (non-dry-run only).
        """
        from little_loops.parallel.github_utils import is_pr_merged

        current_result = self._git_lock.run(
            ["rev-parse", "--abbrev-ref", "HEAD"], cwd=self.repo_path, timeout=10
        )
        current_branch = current_result.stdout.strip() if current_result.returncode == 0 else ""

        all_result = self._git_lock.run(["branch"], cwd=self.repo_path, timeout=30)
        merged_result = self._git_lock.run(
            ["branch", "--merged", base_branch], cwd=self.repo_path, timeout=30
        )

        def _parse(output: str) -> list[str]:
            branches = []
            for line in output.splitlines():
                b = line.strip()
                if b.startswith("* "):
                    b = b[2:]
                if b and not b.startswith("("):
                    branches.append(b)
            return branches

        all_branches = _parse(all_result.stdout) if all_result.returncode == 0 else []
        merged_set = set(_parse(merged_result.stdout) if merged_result.returncode == 0 else [])

        pruned: list[str] = []
        skipped: list[str] = []

        for branch in all_branches:
            if not branch.startswith("feature/"):
                continue
            if branch in (current_branch, base_branch):
                continue

            is_merged = branch in merged_set or is_pr_merged(branch)
            if not is_merged:
                continue

            if dry_run:
                self.logger.info(f"[DRY RUN] would delete: {branch}")
                pruned.append(branch)
            else:
                del_result = self._git_lock.run(
                    ["branch", "-D", branch], cwd=self.repo_path, timeout=30
                )
                if del_result.returncode == 0:
                    self.logger.info(f"Deleted merged feature branch: {branch}")
                    pruned.append(branch)
                else:
                    self.logger.warning(
                        f"Failed to delete branch {branch}: {del_result.stderr.strip()}"
                    )
                    skipped.append(branch)

        return pruned, skipped

        self.logger.info("Cleaned up all worker worktrees")
