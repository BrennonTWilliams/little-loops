"""Issue lifecycle management for little-loops.

Provides functions for closing, completing, and verifying issue completion,
as well as creating new issues from implementation failures.

Also provides failure classification to distinguish transient errors
(API quota, network issues, timeouts) from real implementation failures.
"""

from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from little_loops.config import BRConfig
from little_loops.events import EventBus
from little_loops.file_utils import atomic_write
from little_loops.frontmatter import parse_frontmatter, update_frontmatter
from little_loops.issue_parser import IssueInfo, IssueParser, get_next_issue_number, slugify
from little_loops.logger import Logger
from little_loops.session_log import append_session_log_entry


def _iso_now() -> str:
    """Return current time as ISO 8601 string."""
    return datetime.now(UTC).isoformat()


def _completed_at_now() -> str:
    """Return current UTC time as ISO 8601 with ``Z`` suffix for ``completed_at``."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# =============================================================================
# Failure Classification
# =============================================================================


class FailureType(Enum):
    """Classification of command failure types.

    Used to distinguish between transient errors that should not
    create bug issues and real implementation failures that should.
    """

    TRANSIENT = "transient"  # Temporary error, don't create issue
    NON_RECOVERABLE = "non_recoverable"  # Auth/credential failure — retry won't help, not a code bug
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

    # Auth/credential failure patterns — non-recoverable (retry cannot fix an expired/invalid token)
    # Placed before server_error_patterns because "api error" in that list could also match auth text.
    auth_patterns = [
        "401",
        "403",
        "unauthorized",
        "forbidden",
        "authentication",
        "invalid api key",
        "invalid_api_key",
        "expired token",
    ]
    if any(pattern in error_lower for pattern in auth_patterns):
        return (FailureType.NON_RECOVERABLE, "Auth/credentials failure")

    # API server error patterns (distinct from rate-limits; trigger short-burst retry in executor)
    server_error_patterns = [
        "the server had an error",
        "internal server error",
        "overloaded_error",
        "overloaded",
        "529",  # Anthropic overload HTTP code
        "api error",  # generic "API Error: ..." prefix from Claude Code
    ]
    if any(pattern in error_lower for pattern in server_error_patterns):
        return (FailureType.TRANSIENT, "API server error")

    # Context window exhaustion patterns — Claude CLI exits non-zero with this on stderr
    context_patterns = [
        "prompt is too long",
        "context length exceeded",
        "context window",
        "maximum context",
    ]
    if any(pattern in error_lower for pattern in context_patterns):
        return (FailureType.TRANSIENT, "Context window exhausted")

    # CLI session continuation errors — --continue/--resume without a live session.
    # Treated as transient so a failed Option E call does not produce phantom issues.
    session_id_patterns = [
        "requires a valid session id",
        "requires a valid session title",
    ]
    if any(pattern in error_lower for pattern in session_id_patterns):
        return (FailureType.TRANSIENT, "CLI session continuation error")

    # Shell sandbox environment errors — the ll CLI never executed (exit 127 indicators)
    sandbox_patterns = [
        "command not found",
        "read-only variable",
    ]
    if any(pattern in error_lower for pattern in sandbox_patterns):
        return (FailureType.TRANSIENT, "Shell sandbox environment error")

    # Process killed by OS (SIGKILL/OOM kill) — exit 137 text signal
    if re.search(r"\bkilled\b", error_lower):
        return (FailureType.TRANSIENT, "Process killed (OOM/SIGKILL)")

    # User-cancelled tool calls — not a defect
    if "<tool_use_error>" in error_output:
        return (FailureType.TRANSIENT, "User-cancelled tool call")

    # Ad-hoc Python snippet tracebacks — not from an ll CLI
    if 'file "<string>"' in error_lower or 'file "<stdin>"' in error_lower:
        return (FailureType.TRANSIENT, "Ad-hoc Python snippet error, not an ll CLI failure")

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
    try:
        result = subprocess.run(
            ["git", "ls-files", str(file_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False
    return bool(result.stdout.strip())


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
    try:
        stage_result = subprocess.run(
            ["git", "add", "-A"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if stage_result.returncode != 0:
            logger.warning(f"git add failed: {stage_result.stderr}")
    except subprocess.TimeoutExpired:
        logger.warning("git add timed out")

    # Create commit
    commit_msg = f"{commit_prefix}({info.issue_type}): {commit_body}"
    try:
        commit_result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        logger.warning("git commit timed out")
        return True

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
    """Verify that an issue was marked as completed via frontmatter.

    Reads the issue file's ``status:`` frontmatter; ``done`` (or ``cancelled``)
    means the close path ran successfully. Files no longer move on completion,
    so this is a pure frontmatter check.

    Args:
        info: Issue info
        config: Project configuration (unused; kept for signature stability)
        logger: Logger for output

    Returns:
        True if issue's frontmatter shows it is done/cancelled
    """
    path = info.path
    if not path.exists():
        # Source removed without lifecycle update — treat as completed for back-compat
        # with any external scripts that delete files manually.
        logger.warning(f"Warning: {info.issue_id} source not found at {path}")
        return True

    try:
        fm = parse_frontmatter(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Warning: failed to read {info.issue_id} frontmatter: {e}")
        return False

    status = fm.get("status", "open")
    if status in ("done", "cancelled"):
        logger.success(f"Verified: {info.issue_id} status={status}")
        return True

    logger.warning(f"Warning: {info.issue_id} status={status} (expected done/cancelled)")
    return False


def create_issue_from_failure(
    error_output: str,
    parent_info: IssueInfo,
    config: BRConfig,
    logger: Logger,
    event_bus: EventBus | None = None,
) -> Path | None:
    """Create a new bug issue file when implementation fails.

    Args:
        error_output: Error output from the failed command
        parent_info: Info about the issue that failed
        config: Project configuration
        logger: Logger for output
        event_bus: Optional EventBus for event emission

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

    captured_at_val = _completed_at_now()
    content = f"""---
id: {bug_id}
type: BUG
priority: P1
status: open
captured_at: {captured_at_val}
discovered_by: auto-generated
---

# {bug_id}: Implementation Failure - {parent_info.issue_id}

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
**Open** | Created: {_iso_now()} | Priority: P1

## Related Issues
- [{parent_info.issue_id}]({parent_info.path})
"""

    try:
        bugs_dir.mkdir(parents=True, exist_ok=True)
        new_issue_path.write_text(content)
        logger.success(f"Created new issue: {new_issue_path}")
        if event_bus is not None:
            event_bus.emit(
                {
                    "event": "issue.failure_captured",
                    "ts": _iso_now(),
                    "issue_id": bug_id,
                    "file_path": str(new_issue_path),
                    "parent_issue_id": parent_info.issue_id,
                    "captured_at": captured_at_val,
                }
            )
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
    event_bus: EventBus | None = None,
    interceptors: list[Any] | None = None,
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
        event_bus: Optional EventBus for event emission
        interceptors: Optional list of interceptor objects; each may implement
            ``before_issue_close(info) -> bool | None``.  Returning ``False``
            vetoes the close; ``None`` or any truthy value allows it to proceed.

    Returns:
        True if successful, False otherwise
    """
    original_path = info.path

    if not original_path.exists():
        logger.info(f"{info.issue_id} source already removed - nothing to close")
        return True

    # Use defaults if not provided
    if not close_status:
        close_status = "Closed - Invalid"
    if not close_reason:
        close_reason = "unknown"

    logger.info(f"Closing {info.issue_id}: {close_status} (reason: {close_reason})")

    # before_issue_close interceptors — veto check before any file I/O
    if interceptors:
        for interceptor in interceptors:
            if hasattr(interceptor, "before_issue_close"):
                result = interceptor.before_issue_close(info)
                if result is False:
                    return False

    try:
        captured_at = parse_frontmatter(original_path.read_text(encoding="utf-8")).get(
            "captured_at"
        )
        # Prepare content with resolution section, then write status + completed_at
        resolution = _build_closure_resolution(
            close_status, close_reason, fix_commit, files_changed
        )
        content = _prepare_issue_content(original_path, resolution)
        content = update_frontmatter(
            content,
            {"status": "done", "completed_at": _completed_at_now()},
        )
        original_path.write_text(content, encoding="utf-8")

        # Commit the closure
        commit_body = f"""{info.issue_id} - {close_status}

Automated closure - issue determined to be invalid or already resolved.

Issue: {info.issue_id}
Reason: {close_reason}
Status: {close_status}"""
        _commit_issue_completion(info, "close", commit_body, logger)

        logger.success(f"Closed {info.issue_id}: {close_status}")
        if event_bus is not None:
            event_bus.emit(
                {
                    "event": "issue.closed",
                    "ts": _iso_now(),
                    "issue_id": info.issue_id,
                    "file_path": str(original_path),
                    "close_reason": close_reason,
                    "captured_at": captured_at,
                }
            )
        return True

    except Exception as e:
        logger.error(f"Failed to close {info.issue_id}: {e}")
        return False


def complete_issue_lifecycle(
    info: IssueInfo,
    config: BRConfig,
    logger: Logger,
    event_bus: EventBus | None = None,
) -> bool:
    """Fallback: Complete the issue lifecycle when command exited early.

    This moves the issue to completed and adds a resolution section.

    Args:
        info: Issue info
        config: Project configuration
        logger: Logger for output
        event_bus: Optional EventBus for event emission

    Returns:
        True if successful, False otherwise
    """
    original_path = info.path

    if not original_path.exists():
        logger.info(f"{info.issue_id} source already removed - nothing to complete")
        return True

    logger.info(f"Completing lifecycle for {info.issue_id} (command may have exited early)...")

    try:
        captured_at = parse_frontmatter(original_path.read_text(encoding="utf-8")).get(
            "captured_at"
        )
        # Prepare content with resolution section, then write status + completed_at
        action = config.get_category_action(info.issue_type)
        resolution = _build_completion_resolution(action)
        content = _prepare_issue_content(original_path, resolution)
        content = update_frontmatter(
            content,
            {"status": "done", "completed_at": _completed_at_now()},
        )
        original_path.write_text(content, encoding="utf-8")
        append_session_log_entry(original_path, "ll-auto")

        # Commit the completion
        commit_body = f"""implement {info.issue_id}

Automated fallback commit - command exited before completion.

Issue: {info.issue_id}
Action: {action}
Status: Completed via fallback lifecycle completion"""
        _commit_issue_completion(info, action, commit_body, logger)

        logger.success(f"Completed lifecycle for {info.issue_id}")
        if event_bus is not None:
            event_bus.emit(
                {
                    "event": "issue.completed",
                    "ts": _iso_now(),
                    "issue_id": info.issue_id,
                    "file_path": str(original_path),
                    "captured_at": captured_at,
                }
            )
        return True

    except Exception as e:
        logger.error(f"Failed to complete lifecycle for {info.issue_id}: {e}")
        return False


# =============================================================================
# Issue Deferral
# =============================================================================


def _build_deferred_section(reason: str) -> str:
    """Build the ## Deferred section content."""
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""

## Deferred

- **Date**: {now}
- **Reason**: {reason}
"""


def _build_undeferred_section(reason: str) -> str:
    """Build the ## Undeferred section content."""
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""

## Undeferred

- **Date**: {now}
- **Reason**: {reason}
"""


def defer_issue(
    info: IssueInfo,
    config: BRConfig,
    logger: Logger,
    reason: str | None = None,
    event_bus: EventBus | None = None,
) -> bool:
    """Defer an issue by writing ``status: deferred`` to its frontmatter.

    The file remains in its type directory; only the ``status:`` field changes.

    Args:
        info: Issue info
        config: Project configuration (unused; kept for signature stability)
        logger: Logger for output
        reason: Reason for deferring
        event_bus: Optional EventBus for event emission

    Returns:
        True if successful, False otherwise
    """
    original_path = info.path

    if not original_path.exists():
        logger.info(f"{info.issue_id} source not found - nothing to defer")
        return True

    if not reason:
        reason = "Intentionally set aside for later consideration"

    logger.info(f"Deferring {info.issue_id}: {reason}")

    try:
        deferred_section = _build_deferred_section(reason)
        raw_content = original_path.read_text(encoding="utf-8")
        captured_at = parse_frontmatter(raw_content).get("captured_at")
        content = raw_content + deferred_section
        content = update_frontmatter(content, {"status": "deferred"})
        original_path.write_text(content, encoding="utf-8")

        commit_body = f"""{info.issue_id} - Deferred

Reason: {reason}"""
        _commit_issue_completion(info, "defer", commit_body, logger)

        logger.success(f"Deferred {info.issue_id}")
        if event_bus is not None:
            event_bus.emit(
                {
                    "event": "issue.deferred",
                    "ts": _iso_now(),
                    "issue_id": info.issue_id,
                    "file_path": str(original_path),
                    "reason": reason,
                    "captured_at": captured_at,
                }
            )
        return True

    except Exception as e:
        logger.error(f"Failed to defer {info.issue_id}: {e}")
        return False


# =============================================================================
# Issue Skip (Deprioritize)
# =============================================================================


def _build_skip_section(reason: str | None) -> str:
    """Build the ## Skip Log section content."""
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    reason_text = reason or "No reason provided"
    return f"""

## Skip Log

- **Date**: {now}
- **Reason**: {reason_text}
"""


def skip_issue(
    original_path: Path,
    new_path: Path,
    reason: str | None = None,
    event_bus: EventBus | None = None,
) -> None:
    """Deprioritize an issue by renaming its priority prefix.

    Appends a ``## Skip Log`` entry with ISO timestamp and optional reason,
    then renames the file in-place (same directory, new priority prefix).
    Prefers ``git mv`` for tracked files to preserve history; falls back to
    an atomic ``Path.rename`` for untracked files.

    Args:
        original_path: Current path to the issue file
        new_path: Target path (same directory, new priority prefix)
        reason: Optional reason text for the Skip Log entry
        event_bus: Optional EventBus for emitting ``issue.skipped``

    Raises:
        FileNotFoundError: If original_path does not exist
        FileExistsError: If new_path already exists
    """
    if not original_path.exists():
        raise FileNotFoundError(f"Issue file not found: {original_path}")
    if new_path.exists():
        raise FileExistsError(f"Target already exists: {new_path}")

    raw_content = original_path.read_text(encoding="utf-8")
    captured_at = parse_frontmatter(raw_content).get("captured_at")
    content = raw_content + _build_skip_section(reason)

    if _is_git_tracked(original_path):
        try:
            result = subprocess.run(
                ["git", "mv", str(original_path), str(new_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            result = None  # type: ignore[assignment]

        if result is None or result.returncode != 0:
            # git mv failed — fall back to write + rename
            atomic_write(original_path, content, encoding="utf-8")
            original_path.rename(new_path)
        else:
            atomic_write(new_path, content, encoding="utf-8")
    else:
        # Not tracked — write updated content then rename atomically
        atomic_write(original_path, content, encoding="utf-8")
        original_path.rename(new_path)

    if event_bus is not None:
        m = re.match(r"P\d+-([A-Z]+-\d+)-", new_path.name)
        issue_id = m.group(1) if m else str(new_path.stem)
        event_bus.emit(
            {
                "event": "issue.skipped",
                "ts": _iso_now(),
                "issue_id": issue_id,
                "file_path": str(new_path),
                "reason": reason,
                "captured_at": captured_at,
            }
        )


def undefer_issue(
    config: BRConfig,
    deferred_issue_path: Path,
    logger: Logger,
    reason: str | None = None,
    event_bus: EventBus | None = None,
) -> Path | None:
    """Undefer an issue by writing ``status: open`` to its frontmatter.

    The file remains where it is (in its type directory); only the ``status:``
    field is updated.

    Args:
        config: Project configuration
        deferred_issue_path: Path to deferred issue (still in its type dir)
        logger: Logger for output
        reason: Reason for undeferring

    Returns:
        Path to undeferred issue, or None if failed
    """
    if not deferred_issue_path.exists():
        logger.error(f"Deferred issue not found: {deferred_issue_path}")
        return None

    if not reason:
        reason = "Ready to resume active work"

    logger.info(f"Undeferring {deferred_issue_path.name}")

    try:
        info = IssueParser(config).parse_file(deferred_issue_path)

        content = deferred_issue_path.read_text(encoding="utf-8")
        captured_at = parse_frontmatter(content).get("captured_at")
        content += _build_undeferred_section(reason)
        content = update_frontmatter(content, {"status": "open"})
        deferred_issue_path.write_text(content, encoding="utf-8")

        commit_body = f"""{info.issue_id} - Undeferred

Reason: {reason}"""
        _commit_issue_completion(info, "undefer", commit_body, logger)

        logger.success(f"Undeferred: {deferred_issue_path.name}")
        if event_bus is not None:
            event_bus.emit(
                {
                    "event": "issue.started",
                    "ts": _iso_now(),
                    "issue_id": info.issue_id,
                    "file_path": str(deferred_issue_path),
                    "reason": reason,
                    "captured_at": captured_at,
                }
            )
        return deferred_issue_path

    except Exception as e:
        logger.error(f"Failed to undefer issue: {e}")
        return None
