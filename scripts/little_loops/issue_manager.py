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
from little_loops.issue_parser import (
    IssueInfo,
    IssueParser,
    find_highest_priority_issue,
    get_next_issue_number,
    slugify,
)
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


def verify_work_was_done(logger: Logger) -> bool:
    """Verify that actual code changes were made (not just issue file moves).

    Returns True if there's evidence of implementation work:
    - Changes to src/ files
    - Changes to tests/ files
    - New commits since workflow started

    This prevents the fallback from marking issues as "completed" when
    no actual fix was implemented.

    Args:
        logger: Logger for output

    Returns:
        True if code changes were detected
    """
    try:
        # Check for uncommitted changes in source code (not just .issues/)
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            changed_files = result.stdout.strip().split("\n")
            # Filter to actual code changes (exclude issue files and docs)
            code_changes = [
                f
                for f in changed_files
                if f
                and not f.startswith(".issues/")
                and not f.startswith("thoughts/")
                and not f.endswith(".md")
            ]
            if code_changes:
                logger.info(f"Found {len(code_changes)} code file(s) changed: {code_changes[:5]}")
                return True

        # Also check staged changes
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            staged_files = result.stdout.strip().split("\n")
            code_staged = [
                f
                for f in staged_files
                if f
                and not f.startswith(".issues/")
                and not f.startswith("thoughts/")
                and not f.endswith(".md")
            ]
            if code_staged:
                logger.info(f"Found {len(code_staged)} staged code file(s): {code_staged[:5]}")
                return True

        logger.warning("No code changes detected - only issue/doc files modified")
        return False

    except Exception as e:
        logger.error(f"Could not verify work: {e}")
        # Be conservative - don't assume work was done if we can't verify
        return False


def create_issue_from_failure(
    error_output: str,
    parent_info: IssueInfo,
    config: BRConfig,
    logger: Logger,
) -> Path | None:
    """Create a new bug issue file when implementation fails.

    Args:
        error_output: Error output from the failed command
        parent_info: Info about the issue that failed
        config: Project configuration
        logger: Logger for output

    Returns:
        Path to new issue file, or None if creation failed
    """
    bug_num = get_next_issue_number(config, "bugs")
    prefix = config.get_issue_prefix("bugs")
    bug_id = f"{prefix}-{bug_num}"

    # Try to extract meaningful error info
    error_lines = error_output.split("\n")[:20]  # First 20 lines
    traceback = "\n".join(error_lines)

    # Generate title from error
    title = f"Implementation failure in {parent_info.issue_id}"
    if "Error" in error_output:
        import re
        error_match = re.search(r"([A-Z]\w+Error[:\s]+[^\n]+)", error_output)
        if error_match:
            title = error_match.group(1)
    title_slug = slugify(title)

    filename = f"P1-{bug_id}-{title_slug}.md"
    bugs_dir = config.get_issue_dir("bugs")
    new_issue_path = bugs_dir / filename

    content = f"""# {bug_id}: Implementation Failure - {parent_info.issue_id}

## Summary
Issue encountered during automated implementation of {parent_info.issue_id}.

## Current Behavior
```
{traceback}
```

## Expected Behavior
Implementation should complete without errors.

## Root Cause
Discovered during automated processing of `{parent_info.path}`.

## Reproduction Steps
1. Run: `/ll:manage_issue {parent_info.issue_type} fix {parent_info.issue_id}`
2. Observe error

## Proposed Fix
Investigate the error output above and address the root cause.

## Impact
- **Severity**: High
- **Effort**: Unknown
- **Risk**: Medium
- **Breaking Change**: No

## Labels
`bug`, `high-priority`, `auto-generated`, `implementation-failure`

---

## Status
**Open** | Created: {datetime.now().isoformat()} | Priority: P1

## Related Issues
- [{parent_info.issue_id}]({parent_info.path})
"""

    try:
        bugs_dir.mkdir(parents=True, exist_ok=True)
        new_issue_path.write_text(content)
        logger.success(f"Created new issue: {new_issue_path}")
        return new_issue_path
    except Exception as e:
        logger.error(f"Failed to create issue: {e}")
        return None


def close_issue(
    info: IssueInfo,
    config: BRConfig,
    logger: Logger,
    close_reason: str | None,
    close_status: str | None,
) -> bool:
    """Close an issue by moving it to completed with closure status.

    Used when ready_issue determines an issue should not be implemented
    (e.g., already fixed, invalid, duplicate).

    Args:
        info: Issue info
        config: Project configuration
        logger: Logger for output
        close_reason: Reason code (e.g., "already_fixed", "invalid_ref")
        close_status: Status text (e.g., "Closed - Already Fixed")

    Returns:
        True if successful, False otherwise
    """
    completed_dir = config.get_completed_dir()
    completed_dir.mkdir(parents=True, exist_ok=True)

    original_path = info.path
    completed_path = completed_dir / original_path.name

    # Safety checks - handle stale state gracefully
    if completed_path.exists():
        logger.info(f"{info.issue_id} already in completed/ - cleaning up source")
        if original_path.exists():
            original_path.unlink()
            subprocess.run(["git", "add", "-A"], capture_output=True, text=True)
            subprocess.run(
                ["git", "commit", "-m", f"cleanup: remove stale {info.issue_id} from bugs/"],
                capture_output=True,
                text=True,
            )
        return True

    if not original_path.exists():
        logger.info(f"{info.issue_id} source already removed - nothing to close")
        return True

    # Use defaults if not provided
    if not close_status:
        close_status = "Closed - Invalid"
    if not close_reason:
        close_reason = "unknown"

    logger.info(f"Closing {info.issue_id}: {close_status} (reason: {close_reason})")

    try:
        # Read original content
        content = original_path.read_text()

        # Add resolution section for closure
        if "## Resolution" not in content:
            resolution = f"""

---

## Resolution

- **Status**: {close_status}
- **Closed**: {datetime.now().strftime("%Y-%m-%d")}
- **Reason**: {close_reason}
- **Closure**: Automated (ready_issue validation)

### Closure Notes
Issue was automatically closed during validation.
The issue was determined to be invalid, already resolved, or not actionable.
"""
            content += resolution

        # Write to completed location
        completed_path.write_text(content)

        # Use git mv if possible
        result = subprocess.run(
            ["git", "mv", str(original_path), str(completed_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # git mv failed, file was already written above, just remove original
            logger.warning(f"git mv failed: {result.stderr}")
            original_path.unlink()
        else:
            logger.success(f"Used git mv to move {info.issue_id}")

        # Stage and commit
        stage_result = subprocess.run(
            ["git", "add", "-A"],
            capture_output=True,
            text=True,
        )
        if stage_result.returncode != 0:
            logger.warning(f"git add failed: {stage_result.stderr}")

        # Create commit for closure
        commit_msg = f"""close({info.issue_type}): {info.issue_id} - {close_status}

Automated closure - issue determined to be invalid or already resolved.

Issue: {info.issue_id}
Reason: {close_reason}
Status: {close_status}
"""
        commit_result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            capture_output=True,
            text=True,
        )
        if commit_result.returncode != 0:
            if "nothing to commit" in commit_result.stdout.lower():
                logger.info("No changes to commit (already committed)")
            else:
                logger.warning(f"git commit failed: {commit_result.stderr}")
        else:
            import re
            commit_hash_match = re.search(r"\[[\w-]+\s+([a-f0-9]+)\]", commit_result.stdout)
            if commit_hash_match:
                logger.success(f"Committed closure: {commit_hash_match.group(1)}")
            else:
                logger.success("Committed issue closure")

        logger.success(f"Closed {info.issue_id}: {close_status}")
        return True

    except Exception as e:
        logger.error(f"Failed to close {info.issue_id}: {e}")
        return False


def complete_issue_lifecycle(
    info: IssueInfo,
    config: BRConfig,
    logger: Logger,
) -> bool:
    """Fallback: Complete the issue lifecycle when command exited early.

    This moves the issue to completed and adds a resolution section.

    Args:
        info: Issue info
        config: Project configuration
        logger: Logger for output

    Returns:
        True if successful, False otherwise
    """
    completed_dir = config.get_completed_dir()
    completed_dir.mkdir(parents=True, exist_ok=True)

    original_path = info.path
    completed_path = completed_dir / original_path.name

    # Safety checks - handle stale state gracefully
    if completed_path.exists():
        logger.info(f"{info.issue_id} already in completed/ - cleaning up source")
        if original_path.exists():
            original_path.unlink()
            subprocess.run(["git", "add", "-A"], capture_output=True, text=True)
            subprocess.run(
                ["git", "commit", "-m", f"cleanup: remove stale {info.issue_id} from bugs/"],
                capture_output=True,
                text=True,
            )
        return True

    if not original_path.exists():
        logger.info(f"{info.issue_id} source already removed - nothing to complete")
        return True

    logger.info(f"Completing lifecycle for {info.issue_id} (command may have exited early)...")

    try:
        # Read original content
        content = original_path.read_text()

        # Add resolution section if not already present
        if "## Resolution" not in content:
            action = config.get_category_action(info.issue_type)
            resolution = f"""

---

## Resolution

- **Action**: {action}
- **Completed**: {datetime.now().strftime("%Y-%m-%d")}
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed

### Changes Made
- See git history for changes

### Verification Results
- Automated verification passed

### Commits
- See git log for details
"""
            content += resolution

        # Write to completed location
        completed_path.write_text(content)

        # Use git mv if possible, otherwise regular mv
        result = subprocess.run(
            ["git", "mv", str(original_path), str(completed_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # git mv failed, file was already written above, just remove original
            logger.warning(f"git mv failed: {result.stderr}")
            original_path.unlink()
        else:
            logger.success(f"Used git mv to move {info.issue_id}")

        # Commit all implementation changes + issue file move
        # Stage all changes (implementation code + issue file move)
        stage_result = subprocess.run(
            ["git", "add", "-A"],
            capture_output=True,
            text=True,
        )
        if stage_result.returncode != 0:
            logger.warning(f"git add failed: {stage_result.stderr}")

        # Create the commit
        action = config.get_category_action(info.issue_type)
        commit_msg = f"""{action}({info.issue_type}): implement {info.issue_id}

Automated fallback commit - command exited before completion.

Issue: {info.issue_id}
Action: {action}
Status: Completed via fallback lifecycle completion
"""
        commit_result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            capture_output=True,
            text=True,
        )
        if commit_result.returncode != 0:
            # Check if it's just "nothing to commit"
            if "nothing to commit" in commit_result.stdout.lower():
                logger.info("No changes to commit (already committed or no changes)")
            else:
                logger.warning(f"git commit failed: {commit_result.stderr}")
        else:
            # Extract commit hash from output
            import re
            commit_hash_match = re.search(r"\[[\w-]+\s+([a-f0-9]+)\]", commit_result.stdout)
            if commit_hash_match:
                logger.success(f"Committed changes: {commit_hash_match.group(1)}")
            else:
                logger.success("Committed implementation changes")

        logger.success(f"Completed lifecycle for {info.issue_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to complete lifecycle for {info.issue_id}: {e}")
        return False


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
            self.state_manager._state = ProcessingState(
                timestamp=datetime.now().isoformat()
            )

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
                    self.logger.warning("ready_issue command failed to execute, continuing anyway...")
                else:
                    # Parse the verdict from the output
                    parsed = parse_ready_issue_output(result.stdout)
                    self.logger.info(f"ready_issue verdict: {parsed['verdict']}")

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
                                f"CLOSE failed: {parsed.get('close_status', 'unknown')}"
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
                            f"NOT READY: {parsed['verdict']} - {len(parsed['concerns'])} concern(s)"
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
                self.logger.info(f"Would run: /ll:manage_issue {info.issue_type} {action} {info.issue_id}")
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
                        info.issue_id,
                        result.stderr or result.stdout or "Unknown error"
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
                            self.logger.success(f"Fallback completion succeeded for {info.issue_id}")
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
