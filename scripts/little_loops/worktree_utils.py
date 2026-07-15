"""Shared worktree setup and cleanup utilities.

Used by ll-parallel, ll-sprint, and ll-loop to create and remove isolated git
worktrees with consistent file-copy behavior.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.logger import Logger
    from little_loops.parallel.git_lock import GitLock


def detect_default_branch(repo_path: Path, git_lock: GitLock | None = None) -> str:
    """Resolve the repository's default/integration branch (BUG-2323).

    Resolution order:
    1. ``origin/HEAD`` symbolic ref — the remote's real default branch
       (strips the ``origin/`` prefix).
    2. The current branch via ``git rev-parse --abbrev-ref HEAD``, only when
       it is a real branch name (not the literal ``HEAD`` from a detached HEAD).
    3. ``"main"`` as a last resort.

    Args:
        repo_path: Path to the repository to inspect.
        git_lock: Optional thread-safe git lock. Pass the orchestrator's lock
            when calling mid-run (serializes with concurrent checkout/pull);
            leave as None at CLI startup, before the orchestrator exists.

    Returns:
        The detected branch name. Never returns the literal ``"HEAD"``.
    """

    def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
        if git_lock is not None:
            return git_lock.run(args, cwd=repo_path, timeout=10)
        return subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

    result = _git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"])
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().removeprefix("origin/")

    result = _git(["rev-parse", "--abbrev-ref", "HEAD"])
    current = result.stdout.strip() if result.returncode == 0 else ""
    if current and current != "HEAD":
        return current

    return "main"


def setup_worktree(
    repo_path: Path,
    worktree_path: Path,
    branch_name: str,
    copy_files: list[str],
    logger: Logger,
    git_lock: GitLock,
    base_branch: str | None = None,
    checkout_existing: bool = False,
) -> None:
    """Create a git worktree and copy essential files.

    Copies the .claude/ directory (for project root detection by Claude Code)
    and any additional files listed in copy_files. Writes a session marker so
    orphan-cleanup routines can identify this process's worktrees.

    Args:
        repo_path: Path to the main repository.
        worktree_path: Destination path for the new worktree.
        branch_name: Name of the branch. By default this is a *new* branch
            created via ``git worktree add -b``. When ``checkout_existing`` is
            True, it names an *already-existing* branch checked out in place
            instead (no new branch is created, and no branch is deleted when
            this worktree is later torn down for it).
        copy_files: File paths (relative to repo_path) to copy into the worktree.
        logger: Logger instance.
        git_lock: Thread-safe git lock for serializing repo operations.
        base_branch: Optional commit-ish to fork the new branch from. When None,
            the branch forks from the current HEAD of repo_path (existing behavior).
            When provided, validated before use; fails fast if unresolvable.
            Mutually exclusive with ``checkout_existing``.
        checkout_existing: When True, check out ``branch_name`` (which must
            already exist) instead of creating a new branch.

    Raises:
        ValueError: If both ``base_branch`` and ``checkout_existing`` are given.
        RuntimeError: If git worktree creation fails or base_branch does not resolve.
    """
    if checkout_existing and base_branch is not None:
        raise ValueError("base_branch and checkout_existing are mutually exclusive")

    if worktree_path.exists():
        cleanup_worktree(
            worktree_path, repo_path, logger, git_lock, delete_branch=not checkout_existing
        )

    if base_branch is not None:
        verify_result = git_lock.run(
            ["rev-parse", "--verify", base_branch],
            cwd=repo_path,
            timeout=10,
        )
        if verify_result.returncode != 0:
            raise RuntimeError(f"Branch '{base_branch}' does not resolve: {verify_result.stderr}")

    if checkout_existing:
        worktree_args = ["worktree", "add", str(worktree_path), branch_name]
    else:
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
            git_lock.run(
                ["config", config_key, value_result.stdout.strip()],
                cwd=worktree_path,
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
        branch_result = git_lock.run(
            ["rev-parse", "--abbrev-ref", "HEAD"],
            cwd=worktree_path,
            timeout=10,
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
    return (
        branch_name.startswith("parallel/") or re.match(r"^\d{8}-\d{6}-", branch_name) is not None
    )


def format_verify_detail(
    stdout: str | None,
    stderr: str | None,
    *,
    max_lines: int = 40,
    max_chars: int = 2000,
) -> str:
    """Capture the diagnostic *tail* of a failed verify command (ENH-2641).

    The epic-merge verify gate previously recorded a first-500-char prefix of
    ``stderr or stdout``. pytest-benchmark / xdist emit ``PytestBenchmarkWarning``
    banners to **stderr**, while pytest's ``=== short test summary info ===`` /
    ``FAILED …`` lines go to **stdout** at the tail. The old capture preferred a
    non-empty stderr and clipped its head, so the surviving artifact held only
    warnings and dropped the real failure summary (BUG-2640).

    Combine both streams in ``stderr + stdout`` order (matching the
    ``merge_coordinator.py`` idiom) so stdout — carrying the failure summary —
    lands at the tail, then keep the last ``max_lines`` lines bounded to
    ``max_chars`` (mirrors the ``splitlines()[-N:]`` scrollback cap in
    ``cli/loop/_helpers.py``).
    """
    combined = "\n".join(s for s in (stderr or "", stdout or "") if s.strip())
    tail = "\n".join(combined.splitlines()[-max_lines:]).strip()
    if len(tail) > max_chars:
        tail = tail[-max_chars:].strip()
    return tail


def verify_epic_branch_before_merge(
    epic_id: str,
    epic_branch: str,
    *,
    verify_before_merge: bool,
    repo_path: Path,
    worktree_base: str | Path,
    test_cmd: str | None,
    lint_cmd: str | None,
    logger: Logger,
    git_lock: GitLock,
    src_dir: str | None = None,
) -> tuple[bool, str | None, int | None]:
    """Run test_cmd/lint_cmd against an EPIC branch tip before merge/PR (ENH-2603, BUG-2614).

    Stateless free-function extraction of ``ParallelOrchestrator``'s
    ``_verify_epic_branch_before_merge`` (FEAT-2449/ENH-2603) so both
    ``WorkerPool``-based runs and the FSM ``auto-refine-and-implement`` loop
    can share one implementation instead of the loop's prior inline
    reimplementation. Checks out ``epic_branch`` in a scratch worktree under
    ``worktree_base``, runs ``test_cmd`` and (if set) ``lint_cmd`` against it,
    and always tears the worktree down regardless of outcome.

    Args:
        epic_id: The EPIC issue ID, used for logging and the scratch worktree name.
        epic_branch: Name of the EPIC integration branch to verify.
        verify_before_merge: When False, returns ``(True, None)`` immediately
            without doing any work (the gate is disabled).
        repo_path: Path to the main repository.
        worktree_base: Directory (relative to repo_path) to create the scratch
            worktree in.
        test_cmd: Shell command to run as the test gate, or None to skip.
        lint_cmd: Shell command to run as the lint gate, or None to skip.
        logger: Logger instance.
        git_lock: Thread-safe git lock for serializing repo operations.
        src_dir: When truthy, the source directory (relative to the branch
            worktree, e.g. ``"scripts"``) whose absolute path is prepended to
            ``PYTHONPATH`` for the test/lint subprocess. This defeats
            editable-install ``.pth`` shadowing (BUG-2629): the editable
            ``_editable_impl_*.pth`` hardcodes the *main* checkout's source dir
            and is loaded at interpreter startup regardless of ``cwd``, so
            ``import little_loops.<branch_only_module>`` would otherwise resolve
            to the main tree and fail collection. ``.pth`` entries land on
            ``sys.path`` *after* ``PYTHONPATH``, so the prepend wins. When falsy
            (default), no injection occurs — preserving prior behavior for
            non-editable / non-Python setups.

    Returns:
        ``(ok, message, returncode)``. ``(True, None, None)`` if the gate
        passed (or was disabled). ``(False, message, returncode)`` if worktree
        setup or a configured command failed, where ``message`` describes the
        failure for the caller to surface and ``returncode`` is the failing
        process exit code (``None`` for a worktree-setup failure, which never
        ran a command). ENH-2631: the exit code lets callers distinguish a
        pytest collection/usage error (exit 2, a harness/env problem — BUG-2629)
        from a real test failure (exit 1) without re-running the suite.
    """
    if not verify_before_merge:
        return True, None, None

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    worktree_path = repo_path / worktree_base / f"verify-{epic_id.lower()}-{timestamp}"

    try:
        setup_worktree(
            repo_path=repo_path,
            worktree_path=worktree_path,
            branch_name=epic_branch,
            copy_files=[],
            logger=logger,
            git_lock=git_lock,
            checkout_existing=True,
        )
    except RuntimeError as e:
        message = f"verify-gate worktree setup failed: {e}"
        logger.warning(f"EPIC {epic_id}: {message}")
        return False, message, None

    env: dict[str, str] | None = None
    if src_dir:
        # Prepend the worktree's source dir to PYTHONPATH so branch-only modules
        # resolve here, not via the editable-install .pth pointing at the main
        # checkout (BUG-2629). .pth entries land on sys.path after PYTHONPATH.
        env = os.environ.copy()
        worktree_src = str(worktree_path / src_dir)
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(p for p in (worktree_src, existing) if p)

    try:
        for label, cmd in (("test", test_cmd), ("lint", lint_cmd)):
            if not cmd:
                continue
            logger.info(f"EPIC {epic_id}: running {label}_cmd against {epic_branch}")
            result = subprocess.run(
                shlex.split(cmd),
                capture_output=True,
                text=True,
                cwd=worktree_path,
                env=env,
            )
            if result.returncode != 0:
                detail = format_verify_detail(result.stdout, result.stderr)
                message = f"{label}_cmd failed (exit {result.returncode}): {detail}"
                logger.warning(f"EPIC {epic_id}: {message}")
                return False, message, result.returncode
        return True, None, None
    finally:
        cleanup_worktree(worktree_path, repo_path, logger, git_lock, delete_branch=False)


def merge_epic_branch_to_base(
    epic_id: str,
    epic_branch: str,
    *,
    base_branch: str,
    repo_path: Path,
    logger: Logger,
    git_lock: GitLock,
    run_dir: Path | None = None,
) -> bool:
    """Merge ``epic_branch`` into ``base_branch`` then delete it (FEAT-2449, BUG-2614).

    Stateless free-function extraction of ``ParallelOrchestrator``'s
    ``_merge_epic_branch_to_base``. Assumes ``repo_path``'s working tree is
    already checked out on (or fast-forwardable to) ``base_branch`` — no
    checkout is performed here, mirroring the orchestrator precedent where
    the main repo stays on ``base_branch`` throughout a run.

    Args:
        epic_id: The EPIC issue ID, used in the merge commit message and logs.
        epic_branch: Name of the EPIC integration branch to merge and delete.
        base_branch: Branch to merge into.
        repo_path: Path to the repository, checked out on ``base_branch``.
        logger: Logger instance.
        git_lock: Thread-safe git lock for serializing repo operations.
        run_dir: When non-``None``, the per-run directory to persist a
            merge-failure diagnostic into (ENH-2643). On failure — *before*
            ``git merge --abort`` discards the conflict state — three flat-text
            artifacts are written, mirroring the verify gate's
            ``verify-detail.txt`` / ``verify-returncode.txt`` pair:
            ``merge-returncode.txt`` (the failing ``git merge`` exit code),
            ``merge-detail.txt`` (the bounded ``stderr + stdout`` tail via
            ``format_verify_detail``), and ``merge-conflicts.txt`` (the
            conflicted-path list from ``git diff --name-only --diff-filter=U``).
            When ``None`` (the parallel-orchestrator caller, which has no
            per-run ``run_dir``), nothing is persisted — behavior is otherwise
            unchanged.

    Returns:
        True if the merge succeeded (and the branch was deleted), False on
        merge failure or an unexpected error (never raises).
    """
    try:
        result = git_lock.run(
            [
                "merge",
                "--no-ff",
                epic_branch,
                "-m",
                f"Merge EPIC integration branch {epic_id} into {base_branch}",
            ],
            cwd=repo_path,
            timeout=60,
        )
        if result.returncode == 0:
            logger.success(f"EPIC {epic_id} integration branch merged into {base_branch}")
            git_lock.run(["branch", "-D", epic_branch], cwd=repo_path, timeout=10)
            return True
        else:
            logger.warning(f"EPIC {epic_id} integration branch merge failed: {result.stderr}")
            if run_dir is not None:
                # ENH-2643: persist the failure detail before `merge --abort`
                # discards the conflict state, mirroring the verify gate's
                # verify-detail.txt / verify-returncode.txt artifacts.
                conflicts = git_lock.run(
                    ["diff", "--name-only", "--diff-filter=U"],
                    cwd=repo_path,
                    timeout=10,
                )
                detail = format_verify_detail(result.stdout, result.stderr)
                (run_dir / "merge-returncode.txt").write_text(str(result.returncode))
                (run_dir / "merge-detail.txt").write_text(detail)
                (run_dir / "merge-conflicts.txt").write_text(conflicts.stdout or "")
            git_lock.run(["merge", "--abort"], cwd=repo_path, timeout=10)
            return False
    except Exception as e:  # noqa: BLE001 — never let completion crash the caller
        logger.warning(f"EPIC {epic_id} integration branch merge error: {e}")
        return False


def open_pr_for_epic_branch(
    epic_id: str,
    epic_branch: str,
    *,
    base_branch: str,
    repo_path: Path,
    logger: Logger,
) -> None:
    """Open one PR for a completed EPIC integration branch via gh (FEAT-2449, BUG-2614).

    Stateless free-function extraction of ``ParallelOrchestrator``'s
    ``_open_pr_for_epic_branch``. The branch is NOT deleted — the PR needs
    it. ``--head`` is the epic branch, ``--base`` is ``base_branch``.

    Args:
        epic_id: The EPIC issue ID, used in the PR title/body and logs.
        epic_branch: Name of the EPIC integration branch to open a PR for.
        base_branch: PR base branch.
        repo_path: Path to the repository.
        logger: Logger instance.
    """
    try:
        auth_result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if auth_result.returncode != 0:
            logger.warning(f"EPIC {epic_id}: gh not authenticated, skipping integration PR")
            return
        pr_result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                f"EPIC {epic_id} integration",
                "--body",
                f"Integration branch for {epic_id} (all children complete)",
                "--base",
                base_branch,
                "--head",
                epic_branch,
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if pr_result.returncode == 0:
            logger.info(f"EPIC {epic_id}: integration PR created: {pr_result.stdout.strip()}")
        else:
            logger.warning(f"EPIC {epic_id}: gh pr create failed: {pr_result.stderr.strip()}")
    except FileNotFoundError:
        logger.warning(f"EPIC {epic_id}: gh CLI not found, skipping integration PR")
    except subprocess.TimeoutExpired:
        logger.warning(f"EPIC {epic_id}: gh pr create timed out")
