"""Automated issue management for little-loops.

Provides the AutoManager class for sequential issue processing with
Claude CLI integration and state persistence for resume capability.
"""

from __future__ import annotations

import signal
import subprocess
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import FrameType

from little_loops.config import BRConfig
from little_loops.dependency_graph import DependencyGraph
from little_loops.git_operations import check_git_status, verify_work_was_done
from little_loops.issue_lifecycle import (
    FailureType,
    classify_failure,
    close_issue,
    complete_issue_lifecycle,
    create_issue_from_failure,
    verify_issue_completed,
)
from little_loops.issue_parser import IssueInfo, IssueParser, find_issues
from little_loops.logger import Logger, format_duration
from little_loops.parallel.output_parsing import parse_ready_issue_output
from little_loops.state import ProcessingState, StateManager
from little_loops.subprocess_utils import (
    detect_context_handoff,
    read_continuation_prompt,
)
from little_loops.subprocess_utils import (
    run_claude_command as _run_claude_base,
)


def _compute_relative_path(abs_path: Path, base_dir: Path | None = None) -> str:
    """Compute relative path from base directory for command input.

    Used for fallback retry when ready_issue resolves to wrong file -
    allows retrying with explicit file path instead of ambiguous ID.

    Args:
        abs_path: Absolute path to the file
        base_dir: Base directory (defaults to cwd)

    Returns:
        Relative path string suitable for ready_issue command
    """
    base = base_dir or Path.cwd()
    try:
        return str(abs_path.relative_to(base))
    except ValueError:
        # Path not relative to base, use absolute
        return str(abs_path)


@contextmanager
def timed_phase(
    logger: Logger,
    phase_name: str,
) -> Generator[dict[str, float], None, None]:
    """Context manager for timing phases.

    Yields a dict that will be populated with 'elapsed' after the context exits.

    Args:
        logger: Logger for output
        phase_name: Name of the phase being timed

    Yields:
        Dict that will contain 'elapsed' key after context exits
    """
    timing_result: dict[str, float] = {}
    start = time.time()
    try:
        yield timing_result
    finally:
        elapsed = time.time() - start
        timing_result["elapsed"] = elapsed
        logger.timing(f"{phase_name} completed in {format_duration(elapsed)}")


def run_claude_command(
    command: str,
    logger: Logger,
    timeout: int = 3600,
    stream_output: bool = True,
    idle_timeout: int = 0,
) -> subprocess.CompletedProcess[str]:
    """Invoke Claude CLI command with real-time output streaming.

    Args:
        command: Command to pass to Claude CLI
        logger: Logger for output
        timeout: Timeout in seconds
        stream_output: Whether to stream output to console
        idle_timeout: Kill process if no output for this many seconds (0 to disable)

    Returns:
        CompletedProcess with stdout/stderr captured
    """
    logger.info(f"Running: claude --dangerously-skip-permissions -p {command!r}")

    def stream_callback(line: str, is_stderr: bool) -> None:
        if stream_output:
            if is_stderr:
                print(f"  {line}", file=sys.stderr)
            else:
                print(f"  {line}")

    return _run_claude_base(
        command=command,
        timeout=timeout,
        stream_callback=stream_callback if stream_output else None,
        idle_timeout=idle_timeout,
    )


def run_with_continuation(
    initial_command: str,
    logger: Logger,
    timeout: int = 3600,
    stream_output: bool = True,
    max_continuations: int = 3,
    repo_path: Path | None = None,
    idle_timeout: int = 0,
) -> subprocess.CompletedProcess[str]:
    """Run a Claude command with automatic continuation on context handoff.

    If the command signals CONTEXT_HANDOFF, reads the continuation prompt
    and spawns a fresh Claude session to continue the work.

    Args:
        initial_command: Initial command to run
        logger: Logger for output
        timeout: Timeout per session in seconds
        stream_output: Whether to stream output
        max_continuations: Maximum number of continuation attempts
        repo_path: Repository root path
        idle_timeout: Kill process if no output for this many seconds (0 to disable)

    Returns:
        Final CompletedProcess result
    """
    all_stdout: list[str] = []
    all_stderr: list[str] = []
    current_command = initial_command
    continuation_count = 0

    while continuation_count <= max_continuations:
        result = run_claude_command(
            current_command,
            logger,
            timeout=timeout,
            stream_output=stream_output,
            idle_timeout=idle_timeout,
        )

        all_stdout.append(result.stdout)
        all_stderr.append(result.stderr)

        # Check for context handoff signal
        if detect_context_handoff(result.stdout):
            logger.info("Detected CONTEXT_HANDOFF signal")

            # Read continuation prompt
            prompt_content = read_continuation_prompt(repo_path)
            if not prompt_content:
                logger.warning("Context handoff signaled but no continuation prompt found")
                break

            if continuation_count >= max_continuations:
                logger.warning(f"Reached max continuations ({max_continuations}), stopping")
                break

            continuation_count += 1
            logger.info(f"Starting continuation session #{continuation_count}")

            # Use continuation prompt as the new command
            # Escape the prompt content for CLI
            current_command = prompt_content.replace('"', '\\"')
            continue

        # No handoff signal, we're done
        break

    return subprocess.CompletedProcess(
        args=result.args,
        returncode=result.returncode,
        stdout="\n---CONTINUATION---\n".join(all_stdout),
        stderr="\n---CONTINUATION---\n".join(all_stderr),
    )


def detect_plan_creation(output: str, issue_id: str) -> Path | None:
    """Detect if manage_issue created a plan file awaiting approval.

    Checks for plan file creation in thoughts/shared/plans/ matching the issue ID.
    This happens when manage_issue creates a plan but waits for user approval.

    Args:
        output: Command stdout (unused, for future pattern matching)
        issue_id: Issue ID (e.g., "BUG-280")

    Returns:
        Path to plan file if created, None otherwise
    """
    plans_dir = Path("thoughts/shared/plans")
    if not plans_dir.exists():
        return None

    # Find plan files matching this issue ID (format: YYYY-MM-DD-ISSUE-ID-*.md)
    # Use glob pattern with issue_id
    pattern = f"*-{issue_id}-*.md"
    matching_plans = list(plans_dir.glob(pattern))

    if not matching_plans:
        return None

    # Return the most recently modified plan file
    # (in case multiple exist, take the latest)
    latest_plan = max(matching_plans, key=lambda p: p.stat().st_mtime)
    return latest_plan


@dataclass
class IssueProcessingResult:
    """Result of processing a single issue in-place."""

    success: bool
    duration: float
    issue_id: str
    was_closed: bool = False
    failure_reason: str = ""
    corrections: list[str] = field(default_factory=list)
    plan_created: bool = False
    plan_path: str = ""


def process_issue_inplace(
    info: IssueInfo,
    config: BRConfig,
    logger: Logger,
    dry_run: bool = False,
) -> IssueProcessingResult:
    """Process a single issue through the 3-phase workflow in the current working tree.

    This is the core processing logic extracted from AutoManager._process_issue(),
    suitable for use outside of AutoManager (e.g., single-issue sprint waves).

    Args:
        info: Issue information
        config: Project configuration
        logger: Logger for output
        dry_run: If True, only preview what would be done

    Returns:
        IssueProcessingResult with outcome details
    """
    issue_start_time = time.time()
    corrections: list[str] = []

    logger.header(f"Processing: {info.issue_id} - {info.title}")

    issue_timing: dict[str, float] = {}

    # Track whether we used fallback path resolution for ready_issue.
    validated_via_fallback = False

    # Phase 1: Ready/verify the issue
    logger.info(f"Phase 1: Verifying issue {info.issue_id}...")
    with timed_phase(logger, "Phase 1 (ready_issue)") as phase1_timing:
        if not dry_run:
            result = run_claude_command(
                f"/ll:ready_issue {info.issue_id}",
                logger,
                timeout=config.automation.timeout_seconds,
                stream_output=config.automation.stream_output,
                idle_timeout=config.automation.idle_timeout_seconds,
            )
            if result.returncode != 0:
                logger.warning("ready_issue command failed to execute, continuing anyway...")
            else:
                # Parse the verdict from the output
                parsed = parse_ready_issue_output(result.stdout)
                logger.info(f"ready_issue verdict: {parsed['verdict']}")

                # Validate that ready_issue analyzed the expected file
                validated_path = parsed.get("validated_file_path")
                if validated_path:
                    # Normalize paths for comparison (resolve to absolute)
                    expected_path = str(info.path.resolve())
                    # Handle both absolute and relative paths from ready_issue
                    validated_resolved = Path(validated_path).resolve()
                    if str(validated_resolved) != expected_path:
                        # Check if this is a legitimate rename (new file exists,
                        # old file doesn't) vs a mismatch error
                        old_file_exists = info.path.exists()
                        new_file_exists = validated_resolved.exists()

                        if new_file_exists and not old_file_exists:
                            # ready_issue renamed the file - update tracking
                            logger.info(
                                f"Issue file renamed: '{info.path.name}' -> "
                                f"'{validated_resolved.name}'"
                            )
                            info.path = validated_resolved
                        else:
                            # Genuine mismatch - attempt fallback with explicit path
                            logger.warning(
                                f"Path mismatch: ready_issue validated "
                                f"'{validated_path}' but expected '{info.path}'"
                            )
                            logger.info(
                                "Attempting fallback: retrying ready_issue "
                                "with explicit file path..."
                            )

                            # Compute relative path for the command
                            relative_path = _compute_relative_path(info.path)

                            # Retry with explicit path
                            retry_result = run_claude_command(
                                f"/ll:ready_issue {relative_path}",
                                logger,
                                timeout=config.automation.timeout_seconds,
                                stream_output=config.automation.stream_output,
                                idle_timeout=config.automation.idle_timeout_seconds,
                            )

                            if retry_result.returncode != 0:
                                logger.error(f"Fallback ready_issue failed for {info.issue_id}")
                                return IssueProcessingResult(
                                    success=False,
                                    duration=time.time() - issue_start_time,
                                    issue_id=info.issue_id,
                                    failure_reason="Fallback failed after path mismatch",
                                )

                            # Re-parse and validate retry output
                            retry_parsed = parse_ready_issue_output(retry_result.stdout)
                            retry_validated_path = retry_parsed.get("validated_file_path")

                            if retry_validated_path:
                                retry_resolved = Path(retry_validated_path).resolve()
                                if str(retry_resolved) != str(info.path.resolve()):
                                    logger.error(
                                        f"Fallback still mismatched: "
                                        f"got '{retry_validated_path}', "
                                        f"expected '{info.path}'"
                                    )
                                    return IssueProcessingResult(
                                        success=False,
                                        duration=time.time() - issue_start_time,
                                        issue_id=info.issue_id,
                                        failure_reason="Path mismatch persisted after fallback",
                                    )

                            # Fallback succeeded - use retry result
                            logger.info("Fallback succeeded: validated correct file")
                            parsed = retry_parsed
                            validated_via_fallback = True

                # Log and store any corrections made
                if parsed.get("was_corrected"):
                    logger.info(f"Issue {info.issue_id} was auto-corrected")
                    phase_corrections = parsed.get("corrections", [])
                    for correction in phase_corrections:
                        logger.info(f"  Correction: {correction}")
                    if phase_corrections:
                        corrections.extend(phase_corrections)

                # Log any concerns found
                if parsed["concerns"]:
                    for concern in parsed["concerns"]:
                        logger.warning(f"  Concern: {concern}")

                # Handle CLOSE verdict - issue should not be implemented
                if parsed.get("should_close"):
                    close_reason = parsed.get("close_reason", "unknown")
                    logger.info(f"Issue {info.issue_id} should be closed (reason: {close_reason})")

                    # CRITICAL: Skip file operations for invalid references
                    if close_reason == "invalid_ref":
                        logger.warning(
                            f"Skipping {info.issue_id}: invalid reference - "
                            "no matching issue file exists"
                        )
                        return IssueProcessingResult(
                            success=False,
                            duration=time.time() - issue_start_time,
                            issue_id=info.issue_id,
                            failure_reason=f"Invalid reference: {close_reason}",
                            corrections=corrections,
                        )

                    # Also require validated_file_path to match before closing
                    close_validated_path = parsed.get("validated_file_path")
                    if not close_validated_path:
                        logger.warning(
                            f"Skipping close for {info.issue_id}: "
                            "ready_issue did not return validated file path"
                        )
                        return IssueProcessingResult(
                            success=False,
                            duration=time.time() - issue_start_time,
                            issue_id=info.issue_id,
                            failure_reason="CLOSE without validated file path",
                            corrections=corrections,
                        )

                    if close_issue(
                        info,
                        config,
                        logger,
                        close_reason,
                        parsed.get("close_status"),
                    ):
                        return IssueProcessingResult(
                            success=True,
                            duration=time.time() - issue_start_time,
                            issue_id=info.issue_id,
                            was_closed=True,
                            corrections=corrections,
                        )
                    else:
                        return IssueProcessingResult(
                            success=False,
                            duration=time.time() - issue_start_time,
                            issue_id=info.issue_id,
                            failure_reason=f"CLOSE failed: {parsed.get('close_status', 'unknown')}",
                            corrections=corrections,
                        )

                # Check if issue is NOT READY (and not closeable)
                if not parsed["is_ready"]:
                    logger.error(
                        f"Issue {info.issue_id} is NOT READY for implementation "
                        f"(verdict: {parsed['verdict']})"
                    )
                    return IssueProcessingResult(
                        success=False,
                        duration=time.time() - issue_start_time,
                        issue_id=info.issue_id,
                        failure_reason=(
                            f"NOT READY: {parsed['verdict']} - {len(parsed['concerns'])} concern(s)"
                        ),
                        corrections=corrections,
                    )

                # Log if proceeding with corrected issue
                if parsed.get("was_corrected"):
                    logger.success(f"Issue {info.issue_id} corrected and ready for implementation")
        else:
            logger.info(f"Would run: /ll:ready_issue {info.issue_id}")
    issue_timing["ready"] = phase1_timing.get("elapsed", 0.0)

    # Phase 2: Implement the issue (with automatic continuation on context handoff)
    action = config.get_category_action(info.issue_type)
    logger.info(f"Phase 2: Implementing {info.issue_id}...")
    with timed_phase(logger, "Phase 2 (implement)") as phase2_timing:
        if not dry_run:
            # Build manage_issue command
            type_name = info.issue_type.rstrip("s")  # bugs -> bug

            # Use relative path if fallback was used, otherwise use issue_id
            if validated_via_fallback:
                issue_arg = _compute_relative_path(info.path)
            else:
                issue_arg = info.issue_id

            # Use run_with_continuation to handle context exhaustion
            result = run_with_continuation(
                f"/ll:manage_issue {type_name} {action} {issue_arg}",
                logger,
                timeout=config.automation.timeout_seconds,
                stream_output=config.automation.stream_output,
                max_continuations=config.automation.max_continuations,
                repo_path=config.repo_path,
                idle_timeout=config.automation.idle_timeout_seconds,
            )
        else:
            logger.info(f"Would run: /ll:manage_issue {info.issue_type} {action} {info.issue_id}")
            result = subprocess.CompletedProcess(args=[], returncode=0)
    issue_timing["implement"] = phase2_timing.get("elapsed", 0.0)

    # Handle implementation failure
    if result.returncode != 0:
        error_output = result.stderr or result.stdout or "Unknown error"
        failure_type, failure_reason_text = classify_failure(error_output, result.returncode)

        if failure_type == FailureType.TRANSIENT:
            # Transient failure - log but don't create bug issue
            logger.warning(f"Transient failure for {info.issue_id}: {failure_reason_text}")
            logger.warning("Not creating bug issue - this is a temporary error")
            logger.info("Error output (first 500 chars):")
            logger.info(error_output[:500])

            return IssueProcessingResult(
                success=False,
                duration=time.time() - issue_start_time,
                issue_id=info.issue_id,
                failure_reason=f"Transient: {failure_reason_text}",
                corrections=corrections,
            )

        # Real failure - create issue as before
        logger.error(f"Implementation failed for {info.issue_id}")

        failure_reason = ""
        if not dry_run:
            # Create new issue for the failure
            new_issue = create_issue_from_failure(
                error_output,
                info,
                config,
                logger,
            )
            failure_reason = str(new_issue) if new_issue else error_output
        else:
            logger.info("Would create new bug issue for this failure")

        return IssueProcessingResult(
            success=False,
            duration=time.time() - issue_start_time,
            issue_id=info.issue_id,
            failure_reason=failure_reason,
            corrections=corrections,
        )

    # Phase 3: Verify completion
    logger.info(f"Phase 3: Verifying {info.issue_id} completion...")
    verified = False
    with timed_phase(logger, "Phase 3 (verify)") as phase3_timing:
        if not dry_run:
            verified = verify_issue_completed(info, config, logger)

            # Fallback: Only complete lifecycle if:
            # 1. Command returned success (returncode 0)
            # 2. File wasn't moved to completed
            # 3. There's EVIDENCE of actual work being done (code changes)
            if not verified and result.returncode == 0:
                # Check if a plan was created awaiting approval
                plan_path = detect_plan_creation(result.stdout, info.issue_id)
                if plan_path is not None:
                    logger.info(
                        f"Plan created at {plan_path}, awaiting approval - "
                        "issue will remain incomplete until plan is approved and implemented"
                    )
                    return IssueProcessingResult(
                        success=False,
                        duration=time.time() - issue_start_time,
                        issue_id=info.issue_id,
                        plan_created=True,
                        plan_path=str(plan_path),
                        failure_reason="",  # Not a failure - plan awaiting approval
                        corrections=corrections,
                    )

                logger.info(
                    "Command returned success but issue not moved - "
                    "checking for evidence of work..."
                )

                # CRITICAL: Verify actual implementation work was done
                work_done = verify_work_was_done(logger)
                if work_done:
                    logger.info("Evidence of code changes found - completing lifecycle...")
                    verified = complete_issue_lifecycle(info, config, logger)
                    if verified:
                        logger.success(f"Fallback completion succeeded for {info.issue_id}")
                    else:
                        logger.warning(f"Fallback completion failed for {info.issue_id}")
                else:
                    # NO work was done - do NOT mark as completed
                    logger.error(
                        f"REFUSING to mark {info.issue_id} as completed: "
                        "no code changes detected despite returncode 0"
                    )
                    logger.error(
                        "This likely indicates the command was not executed properly. "
                        "Check command invocation and Claude CLI output."
                    )
                    verified = False
        else:
            logger.info("Would verify issue moved to completed")
            verified = True  # In dry run, assume success
    issue_timing["verify"] = phase3_timing.get("elapsed", 0.0)

    # Record timing
    total_issue_time = time.time() - issue_start_time
    issue_timing["total"] = total_issue_time
    logger.timing(f"Total processing time: {format_duration(total_issue_time)}")

    if verified:
        logger.success(f"Completed: {info.issue_id}")
    else:
        logger.warning(f"Issue {info.issue_id} was attempted but verification failed")
        logger.info("This issue will be skipped on future runs (check logs above for details)")

    return IssueProcessingResult(
        success=verified,
        duration=total_issue_time,
        issue_id=info.issue_id,
        corrections=corrections,
    )


class AutoManager:
    """Automated issue manager for sequential processing.

    Processes issues in priority order using Claude CLI commands,
    with state persistence for resume capability.
    """

    def __init__(
        self,
        config: BRConfig,
        dry_run: bool = False,
        max_issues: int = 0,
        resume: bool = False,
        category: str | None = None,
        only_ids: set[str] | None = None,
        skip_ids: set[str] | None = None,
        verbose: bool = True,
    ) -> None:
        """Initialize the auto manager.

        Args:
            config: Project configuration
            dry_run: If True, only preview what would be done
            max_issues: Maximum issues to process (0 = unlimited)
            resume: Whether to resume from previous state
            category: Optional category to filter (e.g., "bugs")
            only_ids: If provided, only process these issue IDs
            skip_ids: Issue IDs to skip (in addition to attempted issues)
            verbose: Whether to output progress messages
        """
        self.config = config
        self.dry_run = dry_run
        self.max_issues = max_issues
        self.resume = resume
        self.category = category
        self.only_ids = only_ids
        self.skip_ids = skip_ids or set()

        self.logger = Logger(verbose=verbose)
        self.state_manager = StateManager(config.get_state_file(), self.logger)
        self.parser = IssueParser(config)

        # Build dependency graph for dependency-aware sequencing (ENH-016)
        all_issues = find_issues(self.config, self.category)
        self.dep_graph = DependencyGraph.from_issues(all_issues)

        # Warn about any cycles
        if self.dep_graph.has_cycles():
            cycles = self.dep_graph.detect_cycles()
            for cycle in cycles:
                self.logger.warning(f"Dependency cycle detected: {' -> '.join(cycle)}")

        self.processed_count = 0
        self._shutdown_requested = False

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: FrameType | None) -> None:
        """Handle shutdown signals gracefully."""
        self._shutdown_requested = True
        self.logger.warning(f"Received signal {signum}, shutting down gracefully...")

    def _get_next_issue(self) -> IssueInfo | None:
        """Get next issue respecting dependencies.

        Returns the highest priority issue whose blockers have all been
        completed. If no ready issues exist but blocked issues remain,
        logs warnings about what is blocking progress.

        Returns:
            Next IssueInfo to process, or None if no ready issues
        """
        # Get completed issues from state
        completed = set(self.state_manager.state.completed_issues)

        # Combine skip_ids from state and CLI argument
        skip_ids = self.state_manager.state.attempted_issues | self.skip_ids

        # Get issues that are ready (blockers satisfied)
        ready_issues = self.dep_graph.get_ready_issues(completed)

        # Filter by skip_ids, only_ids
        candidates = [
            i
            for i in ready_issues
            if i.issue_id not in skip_ids and (self.only_ids is None or i.issue_id in self.only_ids)
        ]

        if candidates:
            return candidates[0]  # Already sorted by priority in get_ready_issues()

        # No ready candidates - check if there are blocked issues remaining
        all_in_graph = set(self.dep_graph.issues.keys())
        remaining = all_in_graph - completed - skip_ids
        if self.only_ids is not None:
            remaining = remaining & self.only_ids

        if remaining:
            self._log_blocked_issues(remaining, completed)

        return None

    def _log_blocked_issues(self, remaining: set[str], completed: set[str]) -> None:
        """Log information about blocked issues when processing stalls.

        Args:
            remaining: Set of issue IDs that haven't been processed
            completed: Set of completed issue IDs
        """
        blocked_count = 0
        for issue_id in sorted(remaining):
            blockers = self.dep_graph.get_blocking_issues(issue_id, completed)
            if blockers:
                blocked_count += 1
                self.logger.info(f"  {issue_id} blocked by: {', '.join(sorted(blockers))}")

        if blocked_count > 0:
            self.logger.warning(f"{blocked_count} issue(s) remain blocked - check dependencies")

    def run(self) -> int:
        """Run the automation loop.

        Returns:
            Exit code (0 = success)
        """
        run_start_time = time.time()
        self.logger.info("Starting automated issue management...")

        if self.dry_run:
            self.logger.info("DRY RUN MODE - No actual changes will be made")

        if not self.dry_run:
            has_changes = check_git_status(self.logger)
            if has_changes:
                self.logger.warning("Proceeding anyway...")

        # Load or initialize state
        if self.resume:
            state = self.state_manager.load()
            if state:
                self.logger.info(f"Resuming from: {state.current_issue}")
                self.processed_count = len(state.completed_issues)
        else:
            # Fresh start
            self.state_manager._state = ProcessingState(timestamp=datetime.now().isoformat())

        try:
            while not self._shutdown_requested:
                if self.max_issues > 0 and self.processed_count >= self.max_issues:
                    self.logger.info(f"Reached max issues limit: {self.max_issues}")
                    break

                info = self._get_next_issue()
                if not info:
                    self.logger.success("No more issues to process!")
                    break

                success = self._process_issue(info)
                if success:
                    self.processed_count += 1

        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            return 1

        finally:
            if not self._shutdown_requested:
                self.state_manager.cleanup()

        self._log_timing_summary(run_start_time)
        self.logger.success(f"Processed {self.processed_count} issue(s)")
        return 0

    def _log_timing_summary(self, run_start_time: float) -> None:
        """Log aggregate timing summary."""
        total_run_time = time.time() - run_start_time

        self.logger.info("")
        self.logger.header("PROCESSING SUMMARY")
        self.logger.timing(f"Total run time: {format_duration(total_run_time)}")
        self.logger.timing(f"Issues processed: {self.processed_count}")

        state = self.state_manager.state
        if state.timing:
            total_times = [t.get("total", 0) for t in state.timing.values()]
            if total_times:
                avg_time = sum(total_times) / len(total_times)
                self.logger.timing(f"Average per issue: {format_duration(avg_time)}")

        if state.failed_issues:
            self.logger.warning(f"Failed issues: {len(state.failed_issues)}")
            for issue_id, reason in state.failed_issues.items():
                self.logger.warning(f"  - {issue_id}: {reason[:50]}...")

        # Log correction statistics for quality tracking
        if state.corrections:
            total_corrected = len(state.corrections)
            total_issues = len(state.completed_issues) + len(state.failed_issues)
            correction_rate = (total_corrected / total_issues * 100) if total_issues > 0 else 0
            self.logger.info(
                f"Auto-corrections: {total_corrected}/{total_issues} ({correction_rate:.1f}%)"
            )

            # Log most common correction types
            from collections import Counter

            all_corrections: list[str] = []
            for corrections in state.corrections.values():
                all_corrections.extend(corrections)
            if all_corrections:
                common = Counter(all_corrections).most_common(3)
                self.logger.info("Most common corrections:")
                for correction, count in common:
                    # Truncate long correction descriptions
                    display = correction[:60] + "..." if len(correction) > 60 else correction
                    self.logger.info(f"  - {display}: {count}")

    def _process_issue(self, info: IssueInfo) -> bool:
        """Process a single issue through the workflow.

        Delegates to process_issue_inplace() and maps the result back
        to state manager calls.

        Args:
            info: Issue information

        Returns:
            True if processing succeeded
        """
        # Pre-processing state updates (before delegating)
        self.state_manager.mark_attempted(info.issue_id, save=False)
        self.state_manager.update_current(str(info.path), "processing")

        result = process_issue_inplace(info, self.config, self.logger, self.dry_run)

        # Map result back to state tracking
        if result.was_closed:
            self.state_manager.mark_completed(info.issue_id)
        elif result.success:
            self.state_manager.mark_completed(info.issue_id, {"total": result.duration})
        elif result.plan_created:
            # Don't mark as failed if a plan was created (awaiting approval)
            self.logger.info(
                f"{info.issue_id} has plan at {result.plan_path} - "
                "leaving in pending state for manual approval"
            )
            # Issue remains in pending state (not marked as failed)
        elif result.failure_reason:
            self.state_manager.mark_failed(info.issue_id, result.failure_reason)

        if result.corrections:
            self.state_manager.record_corrections(info.issue_id, result.corrections)

        return result.success
