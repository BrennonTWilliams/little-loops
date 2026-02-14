"""Issue lifecycle management for little-loops.

Provides functions for closing, completing, and verifying issue completion,
as well as creating new issues from implementation failures.

Also provides failure classification to distinguish transient errors
(API quota, network issues, timeouts) from real implementation failures.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from enum import Enum
from pathlib import Path

from little_loops.config import BRConfig
from little_loops.issue_parser import IssueInfo, get_next_issue_number, slugify
from little_loops.logger import Logger

# =============================================================================
# Failure Classification
# =============================================================================


class FailureType(Enum):
    """Classification of command failure types.

    Used to distinguish between transient errors that should not
    create bug issues and real implementation failures that should.
    """

    TRANSIENT = "transient"  # Temporary error, don't create issue
    REAL = "real"  # Actual bug/error, create issue


def classify_failure(error_output: str, returncode: int) -> tuple[FailureType, str]:
    """Classify a command failure as transient or real.

    Examines error output for patterns indicating transient failures
    (API quota, network errors, timeouts) vs real implementation failures.

    Args:
        error_output: stderr or stdout from failed command
        returncode: Process exit code (available for future use)

    Returns:
        Tuple of (failure_type, reason) where reason explains the classification
    """
    error_lower = error_output.lower()

    # API quota/rate limit patterns
    quota_patterns = [
        "out of extra usage",
        "rate limit",
        "quota exceeded",
        "too many requests",
        "api limit",
        "usage limit",
        "429",  # HTTP Too Many Requests
        "resource exhausted",
        "resourceexhausted",  # No space variant (gRPC style)
    ]
    if any(pattern in error_lower for pattern in quota_patterns):
        return (FailureType.TRANSIENT, "API quota or rate limit exceeded")

    # Network/connectivity patterns
    # Note: Use word boundaries where needed to avoid false positives
    # (e.g., "enotfound" shouldn't match "ModuleNotFoundError")
    network_patterns = [
        "connection refused",
        "connection timeout",
        "network error",
        "dns resolution",
        "connection reset",
        "service unavailable",
        "502 bad gateway",
        "503 service unavailable",
        "504 gateway timeout",
    ]
    if any(pattern in error_lower for pattern in network_patterns):
        return (FailureType.TRANSIENT, "Network or connectivity error")

    # Check for Node.js-style error codes with word boundary awareness
    # These are typically at word boundaries (e.g., "Error: ECONNREFUSED")
    if re.search(r"\beconnrefused\b", error_lower):
        return (FailureType.TRANSIENT, "Network or connectivity error")
    if re.search(r"\benotfound\b", error_lower):
        return (FailureType.TRANSIENT, "Network or connectivity error")
    if re.search(r"\betimedout\b", error_lower):
        return (FailureType.TRANSIENT, "Network or connectivity error")

    # Timeout patterns
    timeout_patterns = [
        "timeout",
        "timed out",
        "deadline exceeded",
        "operation timed out",
    ]
    if any(pattern in error_lower for pattern in timeout_patterns):
        return (FailureType.TRANSIENT, "Command timeout")

    # Resource/system transient patterns
    resource_patterns = [
        "disk full",
        "no space left",
        "resource temporarily unavailable",
        "too many open files",
        "memory allocation failed",
        "out of memory",
    ]
    if any(pattern in error_lower for pattern in resource_patterns):
        return (FailureType.TRANSIENT, "System resource error")

    # Default: treat as real failure
    return (FailureType.REAL, "Implementation error")


# =============================================================================
# Content Manipulation Helpers
# =============================================================================


def _build_closure_resolution(
    close_status: str,
    close_reason: str,
    fix_commit: str | None = None,
    files_changed: list[str] | None = None,
) -> str:
    """Build resolution section for closed issues.

    Args:
        close_status: Status text (e.g., "Closed - Already Fixed")
        close_reason: Reason code (e.g., "already_fixed", "invalid_ref")
        fix_commit: SHA of the commit that fixed the issue (for regression tracking)
        files_changed: List of files modified by the fix (for regression tracking)

    Returns:
        Resolution section markdown string
    """
    # Build fix commit line
    fix_commit_line = f"- **Fix Commit**: {fix_commit}\n" if fix_commit else ""

    # Build files changed section
    if files_changed:
        files_list = "\n".join(f"  - `{f}`" for f in files_changed)
        files_section = f"""
### Files Changed
{files_list}
"""
    else:
        files_section = ""

    return f"""

---

## Resolution

- **Status**: {close_status}
- **Closed**: {datetime.now().strftime("%Y-%m-%d")}
- **Reason**: {close_reason}
- **Closure**: Automated (ready-issue validation)
{fix_commit_line}
### Closure Notes
Issue was automatically closed during validation.
The issue was determined to be invalid, already resolved, or not actionable.
{files_section}"""


def _build_completion_resolution(
    action: str,
    fix_commit: str | None = None,
    files_changed: list[str] | None = None,
) -> str:
    """Build resolution section for completed issues.

    Args:
        action: Action verb (e.g., "fix", "implement")
        fix_commit: SHA of the commit that fixed the issue (for regression tracking)
        files_changed: List of files modified by the fix (for regression tracking)

    Returns:
        Resolution section markdown string
    """
    # Build fix commit line
    fix_commit_line = f"- **Fix Commit**: {fix_commit}" if fix_commit else ""

    # Build files changed section
    if files_changed:
        files_list = "\n".join(f"  - `{f}`" for f in files_changed)
        files_section = f"""
### Files Changed
{files_list}"""
    else:
        files_section = """
### Files Changed
- See git history for details"""

    return f"""

---

## Resolution

- **Action**: {action}
- **Completed**: {datetime.now().strftime("%Y-%m-%d")}
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed
{fix_commit_line}
{files_section}

### Verification Results
- Automated verification passed

### Commits
- See git log for details
"""


def _prepare_issue_content(original_path: Path, resolution: str) -> str:
    """Read issue file and append resolution section if needed.

    Args:
        original_path: Path to the original issue file
        resolution: Resolution section to append

    Returns:
        Updated file content with resolution section
    """
    content = original_path.read_text()
    if "## Resolution" not in content:
        content += resolution
    return content


# =============================================================================
# Git Operations Helpers
# =============================================================================


def _is_git_tracked(file_path: Path) -> bool:
    """Check if a file is under git version control.

    Args:
        file_path: Path to the file to check

    Returns:
        True if file is tracked by git, False otherwise
    """
    result = subprocess.run(
        ["git", "ls-files", str(file_path)],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def _cleanup_stale_source(original_path: Path, issue_id: str, logger: Logger) -> None:
    """Remove orphaned source file and commit cleanup.

    Args:
        original_path: Path to the stale source file
        issue_id: Issue identifier for commit message
        logger: Logger for output
    """
    original_path.unlink()
    subprocess.run(["git", "add", "-A"], capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", f"cleanup: remove stale {issue_id} from bugs/"],
        capture_output=True,
        text=True,
    )


def _move_issue_to_completed(
    original_path: Path,
    completed_path: Path,
    content: str,
    logger: Logger,
) -> bool:
    """Move issue file to completed dir, preferring git mv for history.

    Checks if source is under git version control before attempting git mv.
    If source is tracked, uses git mv for history preservation.
    If source is not tracked, uses manual copy + delete directly.

    Args:
        original_path: Source path of issue file
        completed_path: Destination path in completed directory
        content: Updated file content to write
        logger: Logger for output

    Returns:
        True if move succeeded
    """
    # Handle pre-existing destination (e.g., from parallel worker or worktree leak)
    if completed_path.exists():
        logger.info(f"Destination already exists: {completed_path.name}, updating content")
        completed_path.write_text(content)
        if original_path.exists():
            original_path.unlink()
        return True

    # Check if source is under git version control before attempting git mv
    source_tracked = _is_git_tracked(original_path)

    if source_tracked:
        # Source is tracked, use git mv for history preservation
        result = subprocess.run(
            ["git", "mv", str(original_path), str(completed_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # git mv failed, fall back to manual copy + delete
            logger.warning(f"git mv failed: {result.stderr}")
            completed_path.write_text(content)
            if original_path.exists():
                original_path.unlink()
        else:
            logger.success(f"Used git mv to move {original_path.stem}")
            # Write updated content to the moved file
            completed_path.write_text(content)
    else:
        # Source is not tracked, use manual copy + delete directly
        logger.info(f"Source not tracked by git, using manual copy: {original_path.name}")
        completed_path.write_text(content)
        if original_path.exists():
            original_path.unlink()

    return True


def _commit_issue_completion(
    info: IssueInfo,
    commit_prefix: str,
    commit_body: str,
    logger: Logger,
) -> bool:
    """Stage all changes and create completion commit.

    Args:
        info: Issue information
        commit_prefix: Prefix for commit message (e.g., "close" or action verb)
        commit_body: Body text for commit message
        logger: Logger for output

    Returns:
        True if commit succeeded or nothing to commit
    """
    # Stage all changes
    stage_result = subprocess.run(
        ["git", "add", "-A"],
        capture_output=True,
        text=True,
    )
    if stage_result.returncode != 0:
        logger.warning(f"git add failed: {stage_result.stderr}")

    # Create commit
    commit_msg = f"{commit_prefix}({info.issue_type}): {commit_body}"
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
        commit_hash_match = re.search(r"\[[\w-]+\s+([a-f0-9]+)\]", commit_result.stdout)
        if commit_hash_match:
            logger.success(f"Committed: {commit_hash_match.group(1)}")
        else:
            logger.success("Committed changes")

    return True


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
    bug_id = f"{prefix}-{bug_num:03d}"

    # Try to extract meaningful error info
    error_lines = error_output.split("\n")[:20]  # First 20 lines
    traceback = "\n".join(error_lines)

    # Generate title from error
    title = f"Implementation failure in {parent_info.issue_id}"
    if "Error" in error_output:
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

## Steps to Reproduce
1. Run: `/ll:manage-issue {parent_info.issue_type} fix {parent_info.issue_id}`
2. Observe error

## Proposed Solution
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
    fix_commit: str | None = None,
    files_changed: list[str] | None = None,
) -> bool:
    """Close an issue by moving it to completed with closure status.

    Used when ready-issue determines an issue should not be implemented
    (e.g., already fixed, invalid, duplicate).

    Args:
        info: Issue info
        config: Project configuration
        logger: Logger for output
        close_reason: Reason code (e.g., "already_fixed", "invalid_ref")
        close_status: Status text (e.g., "Closed - Already Fixed")
        fix_commit: SHA of the commit that fixed the issue (for regression tracking)
        files_changed: List of files modified by the fix (for regression tracking)

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
            _cleanup_stale_source(original_path, info.issue_id, logger)
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
        # Prepare content with resolution section
        resolution = _build_closure_resolution(
            close_status, close_reason, fix_commit, files_changed
        )
        content = _prepare_issue_content(original_path, resolution)

        # Move to completed directory
        _move_issue_to_completed(original_path, completed_path, content, logger)

        # Commit the closure
        commit_body = f"""{info.issue_id} - {close_status}

Automated closure - issue determined to be invalid or already resolved.

Issue: {info.issue_id}
Reason: {close_reason}
Status: {close_status}"""
        _commit_issue_completion(info, "close", commit_body, logger)

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
            _cleanup_stale_source(original_path, info.issue_id, logger)
        return True

    if not original_path.exists():
        logger.info(f"{info.issue_id} source already removed - nothing to complete")
        return True

    logger.info(f"Completing lifecycle for {info.issue_id} (command may have exited early)...")

    try:
        # Prepare content with resolution section
        action = config.get_category_action(info.issue_type)
        resolution = _build_completion_resolution(action)
        content = _prepare_issue_content(original_path, resolution)

        # Move to completed directory
        _move_issue_to_completed(original_path, completed_path, content, logger)

        # Commit the completion
        commit_body = f"""implement {info.issue_id}

Automated fallback commit - command exited before completion.

Issue: {info.issue_id}
Action: {action}
Status: Completed via fallback lifecycle completion"""
        _commit_issue_completion(info, action, commit_body, logger)

        logger.success(f"Completed lifecycle for {info.issue_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to complete lifecycle for {info.issue_id}: {e}")
        return False
