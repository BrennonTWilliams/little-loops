"""Shared worktree setup and cleanup utilities.

Used by ll-parallel, ll-sprint, and ll-loop to create and remove isolated git
worktrees with consistent file-copy behavior.
"""

from __future__ import annotations

import os
import re
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
    logger: Logger,
    git_lock: GitLock,
    base_branch: str | None = None,
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
        base_branch: Optional commit-ish to fork the new branch from. When None,
            the branch forks from the current HEAD of repo_path (existing behavior).
            When provided, validated before use; fails fast if unresolvable.

    Raises:
        RuntimeError: If git worktree creation fails or base_branch does not resolve.
    """
    if worktree_path.exists():
        cleanup_worktree(worktree_path, repo_path, logger, git_lock, delete_branch=True)

    if base_branch is not None:
        verify_result = git_lock.run(
            ["rev-parse", "--verify", base_branch],
            cwd=repo_path,
            timeout=10,
        )
        if verify_result.returncode != 0:
            raise RuntimeError(f"Branch '{base_branch}' does not resolve: {verify_result.stderr}")

    worktree_args = ["worktree", "add", "-b", branch_name, str(worktree_path)]
    if base_branch is not None:
        worktree_args.append(base_branch)

    result = git_lock.run(
        worktree_args,
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
    logger: Logger,
    git_lock: GitLock,
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

    git_lock.run(["worktree", "unlock", str(worktree_path)], cwd=repo_path, timeout=10)
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


def _is_ll_worktree(name: str) -> bool:
    """Return True if the directory name matches an ll-managed worktree naming pattern.

    Matches both ll-parallel worker dirs (``worker-<issue>-<timestamp>``) and
    ll-loop worktree dirs (``<YYYYMMDD>-<HHMMSS>-<safe-name>``).
    """
    return name.startswith("worker-") or re.match(r"^\d{8}-\d{6}-", name) is not None


def _is_ll_branch(branch_name: str) -> bool:
    """Return True if branch_name is an ll-managed branch safe to auto-delete.

    Accepts ``parallel/*`` (ll-parallel) and ``YYYYMMDD-HHMMSS-<safe-name>`` (ll-loop).
    Rejects ``main``, ``master``, ``HEAD``, detached state, and any other name.
    """
    if not branch_name or branch_name in ("HEAD", "main", "master"):
        return False
    return branch_name.startswith("parallel/") or re.match(r"^\d{8}-\d{6}-", branch_name) is not None
