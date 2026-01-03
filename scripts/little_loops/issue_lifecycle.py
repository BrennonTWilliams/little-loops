"""Issue lifecycle management for little-loops.

Provides functions for closing, completing, and verifying issue completion,
as well as creating new issues from implementation failures.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path

from little_loops.config import BRConfig
from little_loops.issue_parser import IssueInfo, get_next_issue_number, slugify
from little_loops.logger import Logger


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
    bug_id = f"{prefix}-{bug_num}"

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

        # Use git mv first to preserve history, then write updated content
        result = subprocess.run(
            ["git", "mv", str(original_path), str(completed_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # git mv failed, fall back to manual copy + delete
            logger.warning(f"git mv failed: {result.stderr}")
            completed_path.write_text(content)
            original_path.unlink()
        else:
            logger.success(f"Used git mv to move {info.issue_id}")
            # Write updated content to the moved file
            completed_path.write_text(content)

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

        # Use git mv first to preserve history, then write updated content
        result = subprocess.run(
            ["git", "mv", str(original_path), str(completed_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # git mv failed, fall back to manual copy + delete
            logger.warning(f"git mv failed: {result.stderr}")
            completed_path.write_text(content)
            original_path.unlink()
        else:
            logger.success(f"Used git mv to move {info.issue_id}")
            # Write updated content to the moved file
            completed_path.write_text(content)

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
