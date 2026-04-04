"""Shared worktree setup and cleanup utilities.

Used by ll-parallel, ll-sprint, and ll-loop to create and remove isolated git
worktrees with consistent file-copy behavior.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.logger import Logger
    from little_loops.parallel.git_lock import GitLock


def setup_worktree(
    repo_path: Path,
    worktree_path: Path,
    branch_name: str,
    copy_files: list[str],
    logger: "Logger",
    git_lock: "GitLock",
) -> None:
    """Create a git worktree on a new branch and copy essential files.

    Copies the .claude/ directory (for project root detection by Claude Code)
    and any additional files listed in copy_files. Writes a session marker so
    orphan-cleanup routines can identify this process's worktrees.

    Args:
        repo_path: Path to the main repository.
        worktree_path: Destination path for the new worktree.
        branch_name: Name of the new branch to create.
        copy_files: File paths (relative to repo_path) to copy into the worktree.
        logger: Logger instance.
        git_lock: Thread-safe git lock for serializing repo operations.

    Raises:
        RuntimeError: If git worktree creation fails.
    """
    if worktree_path.exists():
        cleanup_worktree(worktree_path, repo_path, logger, git_lock, delete_branch=True)

    result = git_lock.run(
        ["worktree", "add", "-b", branch_name, str(worktree_path)],
        cwd=repo_path,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create worktree: {result.stderr}")

    # Copy git identity so commits inside the worktree have the right author
    for config_key in ["user.email", "user.name"]:
        value_result = git_lock.run(["config", config_key], cwd=repo_path)
        if value_result.returncode == 0 and value_result.stdout.strip():
            subprocess.run(
                ["git", "config", config_key, value_result.stdout.strip()],
                cwd=worktree_path,
                capture_output=True,
            )

    # Copy .claude/ to establish project root for Claude Code (BUG-007)
    claude_dir = repo_path / ".claude"
    if claude_dir.exists() and claude_dir.is_dir():
        dest_claude_dir = worktree_path / ".claude"
        if dest_claude_dir.exists():
            shutil.rmtree(dest_claude_dir)
        shutil.copytree(claude_dir, dest_claude_dir)
        logger.info("Copied .claude/ directory to worktree")

    # Copy additional configured files
    for file_path in copy_files:
        if file_path.startswith(".claude/"):
            continue  # already covered by the copytree above
        src = repo_path / file_path
        if src.exists():
            if src.is_dir():
                logger.warning(
                    f"Skipping '{file_path}' in copy_files: "
                    "is a directory (use symlinks or copytree for directories)"
                )
                continue
            dest = worktree_path / file_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            logger.info(f"Copied {file_path} to worktree")
        else:
            logger.debug(f"Skipped {file_path} (not found in main repo)")

    logger.info(f"Created worktree at {worktree_path} on branch {branch_name}")

    # Write session marker for orphan cleanup (BUG-579)
    if worktree_path.exists():
        marker_path = worktree_path / f".ll-session-{os.getpid()}"
        marker_path.write_text(str(os.getpid()))


def cleanup_worktree(
    worktree_path: Path,
    repo_path: Path,
    logger: "Logger",
    git_lock: "GitLock",
    delete_branch: bool = True,
) -> None:
    """Remove a git worktree and optionally its associated branch.

    Args:
        worktree_path: Path to the worktree to remove.
        repo_path: Path to the main repository.
        logger: Logger instance.
        git_lock: Thread-safe git lock for serializing repo operations.
        delete_branch: If True, detect and delete the worktree's branch after removal.
    """
    if not worktree_path.exists():
        return

    branch_name: str | None = None
    if delete_branch:
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        branch_name = branch_result.stdout.strip() if branch_result.returncode == 0 else None

    git_lock.run(
        ["worktree", "remove", "--force", str(worktree_path)],
        cwd=repo_path,
        timeout=30,
    )

    if worktree_path.exists():
        shutil.rmtree(worktree_path, ignore_errors=True)

    if delete_branch and branch_name:
        git_lock.run(["branch", "-D", branch_name], cwd=repo_path, timeout=10)
        logger.info(f"Deleted branch {branch_name}")
