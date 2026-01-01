"""Automated issue management for brentech-toolkit.

Provides the AutoManager class for sequential issue processing with
Claude CLI integration and state persistence for resume capability.
"""

from __future__ import annotations

import selectors
import signal
import subprocess
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from types import FrameType

from brentech_toolkit.config import BRConfig
from brentech_toolkit.issue_parser import IssueInfo, IssueParser, find_highest_priority_issue
from brentech_toolkit.logger import Logger, format_duration
from brentech_toolkit.state import ProcessingState, StateManager


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
    cmd_args = ["claude", "--dangerously-skip-permissions", "-p", command]
    logger.info(f"Running: claude --dangerously-skip-permissions -p {command!r}")

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    process = subprocess.Popen(
        cmd_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    sel = selectors.DefaultSelector()
    if process.stdout:
        sel.register(process.stdout, selectors.EVENT_READ)
    if process.stderr:
        sel.register(process.stderr, selectors.EVENT_READ)

    start_time = time.time()
    while sel.get_map():
        if timeout and (time.time() - start_time) > timeout:
            process.kill()
            raise subprocess.TimeoutExpired(cmd_args, timeout)

        ready = sel.select(timeout=1.0)
        for key, _ in ready:
            line = key.fileobj.readline()  # type: ignore[union-attr]
            if not line:
                sel.unregister(key.fileobj)
                continue

            line = line.rstrip("\n")
            if key.fileobj is process.stdout:
                stdout_lines.append(line)
                if stream_output:
                    print(f"  {line}")
            else:
                stderr_lines.append(line)
                if stream_output:
                    print(f"  {line}", file=sys.stderr)

    process.wait()

    return subprocess.CompletedProcess(
        cmd_args,
        process.returncode or 0,
        stdout="\n".join(stdout_lines),
        stderr="\n".join(stderr_lines),
    )


def verify_issue_completed(info: IssueInfo, config: BRConfig, logger: Logger) -> bool:
    """Verify that an issue was moved to completed directory.

    Args:
        info: Issue info
        config: Project configuration
        logger: Logger for output

    Returns:
        True if issue is in completed directory
    """
    completed_path = config.get_completed_dir() / info.path.name
    original_path = info.path

    if completed_path.exists() and not original_path.exists():
        logger.success(f"Verified: {info.issue_id} properly moved to completed")
        return True

    if completed_path.exists() and original_path.exists():
        logger.warning(f"Warning: {info.issue_id} exists in BOTH locations")

    if not original_path.exists():
        logger.warning(f"Warning: {info.issue_id} was deleted but not moved to completed")
        return True

    logger.warning(f"Warning: {info.issue_id} was NOT moved to completed")
    return False


def check_git_status(logger: Logger) -> bool:
    """Check for uncommitted changes.

    Args:
        logger: Logger for output

    Returns:
        True if there are uncommitted changes
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--quiet"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning("Uncommitted changes detected in working directory")
            return True

        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning("Uncommitted staged changes detected")
            return True

        return False
    except Exception as e:
        logger.warning(f"Could not check git status: {e}")
        return True


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
    ) -> None:
        """Initialize the auto manager.

        Args:
            config: Project configuration
            dry_run: If True, only preview what would be done
            max_issues: Maximum issues to process (0 = unlimited)
            resume: Whether to resume from previous state
            category: Optional category to filter (e.g., "bugs")
        """
        self.config = config
        self.dry_run = dry_run
        self.max_issues = max_issues
        self.resume = resume
        self.category = category

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
            self.state_manager._state = ProcessingState(
                timestamp=datetime.now().isoformat()
            )

        try:
            while not self._shutdown_requested:
                if self.max_issues > 0 and self.processed_count >= self.max_issues:
                    self.logger.info(f"Reached max issues limit: {self.max_issues}")
                    break

                skip_ids = self.state_manager.state.attempted_issues
                info = find_highest_priority_issue(
                    self.config, self.category, skip_ids
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

        # Mark as attempted
        self.state_manager.mark_attempted(info.issue_id)
        self.state_manager.update_current(str(info.path), "processing")

        issue_timing: dict[str, float] = {}

        # Phase 1: Ready/verify the issue
        self.logger.info(f"Phase 1: Verifying issue {info.issue_id}...")
        with timed_phase(self.logger, "Phase 1 (ready_issue)") as phase1_timing:
            if not self.dry_run:
                result = run_claude_command(
                    f"/br:ready_issue {info.issue_id}",
                    self.logger,
                    timeout=self.config.automation.timeout_seconds,
                    stream_output=self.config.automation.stream_output,
                )
                if result.returncode != 0:
                    self.logger.warning("ready_issue failed, continuing anyway...")
            else:
                self.logger.info(f"Would run: /br:ready_issue {info.issue_id}")
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
                    f"/br:manage_issue {type_name} {action} {info.issue_id}",
                    self.logger,
                    timeout=self.config.automation.timeout_seconds,
                    stream_output=self.config.automation.stream_output,
                )
            else:
                self.logger.info(f"Would run: /br:manage_issue {info.issue_type} {action} {info.issue_id}")
                result = subprocess.CompletedProcess(args=[], returncode=0)
        issue_timing["implement"] = phase2_timing.get("elapsed", 0.0)

        # Handle failure
        if result.returncode != 0:
            self.logger.error(f"Implementation failed for {info.issue_id}")
            self.state_manager.mark_failed(
                info.issue_id,
                result.stderr or result.stdout or "Unknown error"
            )
            return False

        # Phase 3: Verify completion
        self.logger.info(f"Phase 3: Verifying {info.issue_id} completion...")
        verified = False
        with timed_phase(self.logger, "Phase 3 (verify)") as phase3_timing:
            if not self.dry_run:
                verified = verify_issue_completed(info, self.config, self.logger)
            else:
                verified = True
        issue_timing["verify"] = phase3_timing.get("elapsed", 0.0)

        # Record timing
        total_issue_time = time.time() - issue_start_time
        issue_timing["total"] = total_issue_time
        self.logger.timing(f"Total processing time: {format_duration(total_issue_time)}")

        if verified:
            self.state_manager.mark_completed(info.issue_id, issue_timing)
            self.logger.success(f"Completed: {info.issue_id}")
        else:
            self.logger.warning(f"Issue {info.issue_id} was attempted but verification failed")

        return verified
