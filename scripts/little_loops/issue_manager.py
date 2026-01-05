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
from datetime import datetime
from pathlib import Path
from types import FrameType

from little_loops.config import BRConfig
from little_loops.git_operations import check_git_status, verify_work_was_done
from little_loops.issue_lifecycle import (
    close_issue,
    complete_issue_lifecycle,
    create_issue_from_failure,
    verify_issue_completed,
)
from little_loops.issue_parser import IssueInfo, IssueParser, find_highest_priority_issue
from little_loops.logger import Logger, format_duration
from little_loops.parallel.output_parsing import parse_ready_issue_output
from little_loops.state import ProcessingState, StateManager
from little_loops.subprocess_utils import run_claude_command as _run_claude_base


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
) -> subprocess.CompletedProcess[str]:
    """Invoke Claude CLI command with real-time output streaming.

    Args:
        command: Command to pass to Claude CLI
        logger: Logger for output
        timeout: Timeout in seconds
        stream_output: Whether to stream output to console

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
        """
        self.config = config
        self.dry_run = dry_run
        self.max_issues = max_issues
        self.resume = resume
        self.category = category
        self.only_ids = only_ids
        self.skip_ids = skip_ids or set()

        self.logger = Logger(verbose=True)
        self.state_manager = StateManager(config.get_state_file(), self.logger)
        self.parser = IssueParser(config)

        self.processed_count = 0
        self._shutdown_requested = False

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: FrameType | None) -> None:
        """Handle shutdown signals gracefully."""
        self._shutdown_requested = True
        self.logger.warning(f"Received signal {signum}, shutting down gracefully...")

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

                # Combine skip_ids from state and CLI argument
                skip_ids = self.state_manager.state.attempted_issues | self.skip_ids
                info = find_highest_priority_issue(
                    self.config, self.category, skip_ids, self.only_ids
                )
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

    def _process_issue(self, info: IssueInfo) -> bool:
        """Process a single issue through the workflow.

        Args:
            info: Issue information

        Returns:
            True if processing succeeded
        """
        issue_start_time = time.time()

        self.logger.header(f"Processing: {info.issue_id} - {info.title}")

        # Mark as attempted and update current (single save)
        self.state_manager.mark_attempted(info.issue_id, save=False)
        self.state_manager.update_current(str(info.path), "processing")

        issue_timing: dict[str, float] = {}

        # Phase 1: Ready/verify the issue
        self.logger.info(f"Phase 1: Verifying issue {info.issue_id}...")
        with timed_phase(self.logger, "Phase 1 (ready_issue)") as phase1_timing:
            if not self.dry_run:
                result = run_claude_command(
                    f"/ll:ready_issue {info.issue_id}",
                    self.logger,
                    timeout=self.config.automation.timeout_seconds,
                    stream_output=self.config.automation.stream_output,
                )
                if result.returncode != 0:
                    self.logger.warning(
                        "ready_issue command failed to execute, continuing anyway..."
                    )
                else:
                    # Parse the verdict from the output
                    parsed = parse_ready_issue_output(result.stdout)
                    self.logger.info(f"ready_issue verdict: {parsed['verdict']}")

                    # Validate that ready_issue analyzed the expected file
                    validated_path = parsed.get("validated_file_path")
                    if validated_path:
                        # Normalize paths for comparison (resolve to absolute)
                        expected_path = str(info.path.resolve())
                        # Handle both absolute and relative paths from ready_issue
                        validated_resolved = str(Path(validated_path).resolve())
                        if validated_resolved != expected_path:
                            self.logger.error(
                                f"Path mismatch detected: ready_issue validated "
                                f"'{validated_path}' but expected '{info.path}'"
                            )
                            self.state_manager.mark_failed(
                                info.issue_id,
                                f"Path mismatch: validated {validated_path}, expected {info.path}",
                            )
                            return False

                    # Log any corrections made
                    if parsed.get("was_corrected"):
                        self.logger.info(f"Issue {info.issue_id} was auto-corrected")
                        corrections = parsed.get("corrections", [])
                        for correction in corrections:
                            self.logger.info(f"  Correction: {correction}")

                    # Log any concerns found
                    if parsed["concerns"]:
                        for concern in parsed["concerns"]:
                            self.logger.warning(f"  Concern: {concern}")

                    # Handle CLOSE verdict - issue should not be implemented
                    if parsed.get("should_close"):
                        self.logger.info(
                            f"Issue {info.issue_id} should be closed "
                            f"(reason: {parsed.get('close_reason', 'unknown')})"
                        )
                        if close_issue(
                            info,
                            self.config,
                            self.logger,
                            parsed.get("close_reason"),
                            parsed.get("close_status"),
                        ):
                            self.state_manager.mark_completed(info.issue_id)
                            return True
                        else:
                            self.state_manager.mark_failed(
                                info.issue_id,
                                f"CLOSE failed: {parsed.get('close_status', 'unknown')}",
                            )
                            return False

                    # Check if issue is NOT READY (and not closeable)
                    if not parsed["is_ready"]:
                        self.logger.error(
                            f"Issue {info.issue_id} is NOT READY for implementation "
                            f"(verdict: {parsed['verdict']})"
                        )
                        # Record in failed_issues with reason
                        self.state_manager.mark_failed(
                            info.issue_id,
                            f"NOT READY: {parsed['verdict']} - {len(parsed['concerns'])} concern(s)",
                        )
                        return False

                    # Log if proceeding with corrected issue
                    if parsed.get("was_corrected"):
                        self.logger.success(
                            f"Issue {info.issue_id} corrected and ready for implementation"
                        )
            else:
                self.logger.info(f"Would run: /ll:ready_issue {info.issue_id}")
        issue_timing["ready"] = phase1_timing.get("elapsed", 0.0)

        # Phase 2: Implement the issue
        action = self.config.get_category_action(info.issue_type)
        self.logger.info(f"Phase 2: Implementing {info.issue_id}...")
        with timed_phase(self.logger, "Phase 2 (implement)") as phase2_timing:
            if not self.dry_run:
                # Build manage_issue command
                # Use category name that matches the directory (bugs -> bug, features -> feature)
                type_name = info.issue_type.rstrip("s")  # bugs -> bug
                result = run_claude_command(
                    f"/ll:manage_issue {type_name} {action} {info.issue_id}",
                    self.logger,
                    timeout=self.config.automation.timeout_seconds,
                    stream_output=self.config.automation.stream_output,
                )
            else:
                self.logger.info(
                    f"Would run: /ll:manage_issue {info.issue_type} {action} {info.issue_id}"
                )
                result = subprocess.CompletedProcess(args=[], returncode=0)
        issue_timing["implement"] = phase2_timing.get("elapsed", 0.0)

        # Handle implementation failure
        if result.returncode != 0:
            self.logger.error(f"Implementation failed for {info.issue_id}")

            if not self.dry_run:
                # Create new issue for the failure
                new_issue = create_issue_from_failure(
                    result.stderr or result.stdout or "Unknown error",
                    info,
                    self.config,
                    self.logger,
                )
                if new_issue:
                    self.state_manager.mark_failed(info.issue_id, str(new_issue))
                else:
                    self.state_manager.mark_failed(
                        info.issue_id, result.stderr or result.stdout or "Unknown error"
                    )
            else:
                self.logger.info("Would create new bug issue for this failure")

            return False

        # Phase 3: Verify completion
        self.logger.info(f"Phase 3: Verifying {info.issue_id} completion...")
        verified = False
        with timed_phase(self.logger, "Phase 3 (verify)") as phase3_timing:
            if not self.dry_run:
                verified = verify_issue_completed(info, self.config, self.logger)

                # Fallback: Only complete lifecycle if:
                # 1. Command returned success (returncode 0)
                # 2. File wasn't moved to completed
                # 3. There's EVIDENCE of actual work being done (code changes)
                if not verified and result.returncode == 0:
                    self.logger.info(
                        "Command returned success but issue not moved - checking for evidence of work..."
                    )

                    # CRITICAL: Verify actual implementation work was done
                    work_done = verify_work_was_done(self.logger)
                    if work_done:
                        self.logger.info("Evidence of code changes found - completing lifecycle...")
                        verified = complete_issue_lifecycle(info, self.config, self.logger)
                        if verified:
                            self.logger.success(
                                f"Fallback completion succeeded for {info.issue_id}"
                            )
                        else:
                            self.logger.warning(f"Fallback completion failed for {info.issue_id}")
                    else:
                        # NO work was done - do NOT mark as completed
                        self.logger.error(
                            f"REFUSING to mark {info.issue_id} as completed: "
                            "no code changes detected despite returncode 0"
                        )
                        self.logger.error(
                            "This likely indicates the command was not executed properly. "
                            "Check command invocation and Claude CLI output."
                        )
                        verified = False
            else:
                self.logger.info("Would verify issue moved to completed")
                verified = True  # In dry run, assume success
        issue_timing["verify"] = phase3_timing.get("elapsed", 0.0)

        # Record timing
        total_issue_time = time.time() - issue_start_time
        issue_timing["total"] = total_issue_time
        self.logger.timing(f"Total processing time: {format_duration(total_issue_time)}")

        # Update state - only mark as completed if verification succeeded
        if verified:
            self.state_manager.mark_completed(info.issue_id, issue_timing)
            self.logger.success(f"Completed: {info.issue_id}")
        else:
            self.logger.warning(f"Issue {info.issue_id} was attempted but verification failed")
            self.logger.info(
                "This issue will be skipped on future runs (check logs above for details)"
            )

        return verified
