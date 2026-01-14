"""Work verification utilities for little-loops.

Contains shared functions for verifying that actual implementation work
was done, used by both issue_manager (ll-auto) and worker_pool (ll-parallel).
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.logger import Logger


# Directories that are excluded when verifying work was done.
# Changes to files in these directories don't count as "real work".
EXCLUDED_DIRECTORIES = (
    ".issues/",
    "issues/",  # Support non-dotted variant (issues.base_dir = "issues")
    ".speckit/",
    "thoughts/",
    ".worktrees/",
    ".auto-manage",
)


def filter_excluded_files(files: list[str]) -> list[str]:
    """Filter out files in excluded directories.

    Args:
        files: List of file paths to filter

    Returns:
        List of files not in excluded directories
    """
    return [
        f
        for f in files
        if f and not any(f.startswith(excluded) for excluded in EXCLUDED_DIRECTORIES)
    ]


def verify_work_was_done(logger: Logger, changed_files: list[str] | None = None) -> bool:
    """Verify that actual work was done (not just issue file moves).

    Returns True if there's evidence of implementation work - changes to files
    outside of excluded directories like .issues/, thoughts/, etc.

    This prevents marking issues as "completed" when no actual fix was implemented.

    Args:
        logger: Logger for output
        changed_files: Optional list of changed files. If not provided,
            will detect via git diff commands.

    Returns:
        True if meaningful file changes were detected
    """
    # If changed_files provided, use them directly (ll-parallel case)
    if changed_files is not None:
        meaningful_changes = filter_excluded_files(changed_files)
        if meaningful_changes:
            logger.info(
                f"Found {len(meaningful_changes)} file(s) changed: {meaningful_changes[:5]}"
            )
            return True
        # Log which excluded files were modified for diagnostic purposes
        excluded_files = [f for f in changed_files if f]
        logger.warning(
            f"No meaningful changes detected - only excluded files modified: "
            f"{excluded_files[:10]}"
        )
        return False

    # Otherwise detect via git (ll-auto case)
    all_excluded_files: list[str] = []
    try:
        # Check for uncommitted changes
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            files = result.stdout.strip().split("\n")
            meaningful_changes = filter_excluded_files(files)
            if meaningful_changes:
                logger.info(
                    f"Found {len(meaningful_changes)} file(s) changed: {meaningful_changes[:5]}"
                )
                return True
            # Collect excluded files for diagnostic logging
            all_excluded_files.extend([f for f in files if f])

        # Also check staged changes
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            staged = result.stdout.strip().split("\n")
            meaningful_staged = filter_excluded_files(staged)
            if meaningful_staged:
                logger.info(
                    f"Found {len(meaningful_staged)} staged file(s): {meaningful_staged[:5]}"
                )
                return True
            # Collect excluded files for diagnostic logging
            all_excluded_files.extend([f for f in staged if f and f not in all_excluded_files])

        # Log which excluded files were modified for diagnostic purposes
        if all_excluded_files:
            logger.warning(
                f"No meaningful changes detected - only excluded files modified: "
                f"{all_excluded_files[:10]}"
            )
        else:
            logger.warning("No meaningful changes detected - no files modified")
        return False

    except Exception as e:
        logger.error(f"Could not verify work: {e}")
        # Be conservative - don't assume work was done if we can't verify
        return False
