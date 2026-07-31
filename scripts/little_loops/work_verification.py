"""Work verification utilities for little-loops.

Contains shared functions for verifying that actual implementation work
was done, used by both issue_manager (ll-auto) and worker_pool (ll-parallel).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config.core import BRConfig
    from little_loops.logger import Logger
    from little_loops.test_tamper_guard import TamperPolicy


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


def _effective_tamper_guard_policy(config: BRConfig) -> TamperPolicy:
    """Resolve config.tamper_guard.policy, falling back to the built-in default
    for an unrecognized value (schema validation is expected to catch this
    earlier; this is just a safe runtime fallback)."""
    from little_loops.test_tamper_guard import DEFAULT_TAMPER_POLICY

    policy = config.tamper_guard.policy
    if policy == "revert":
        return "revert"
    if policy == "fail":
        return "fail"
    if policy == "allow":
        return "allow"
    return DEFAULT_TAMPER_POLICY


def _run_non_fsm_tamper_guard(
    logger: Logger,
    repo_root: Path,
    config: BRConfig,
    baseline_sha: str | None,
) -> bool:
    """Run the tamper guard (ENH-2933) against the current on-disk state.

    Unlike the FSM adapter (ENH-2934), this path never captured a live
    pre-step snapshot -- verification runs once, after the whole run already
    happened -- so "before" is reconstructed from git history via
    ``snapshot_test_paths_at_ref`` instead, using *baseline_sha* (or ``HEAD``
    when unset) as the reference point.

    Returns True when the guard passes (nothing found, or an "allow"/"revert"
    policy resolved the findings); False only when a "fail" policy trips on
    an unresolved finding -- the caller should treat that as verification
    failure regardless of other evidence of work.
    """
    from little_loops.test_tamper_guard import (
        run_tamper_guard,
        snapshot_test_paths_at_ref,
        tamper_guard_candidate_paths,
        tamper_guard_changed_files,
    )

    policy = _effective_tamper_guard_policy(config)

    candidate_paths = tamper_guard_candidate_paths(repo_root, config=config)
    before = snapshot_test_paths_at_ref(repo_root, baseline_sha or "HEAD", candidate_paths)
    changed = tamper_guard_changed_files(repo_root)

    report = run_tamper_guard(before, changed, config, policy, repo_root)
    if not report.passed:
        logger.error(
            f"Tamper guard ({report.policy}) failed: "
            f"{[f.path for f in report.findings]} not resolved"
        )
    elif report.findings:
        logger.warning(
            f"Tamper guard ({report.policy}) found and handled: "
            f"{[f.path for f in report.findings]}"
        )
    return report.passed


def verify_work_was_done(
    logger: Logger,
    changed_files: list[str] | None = None,
    baseline_sha: str | None = None,
    config: BRConfig | None = None,
    repo_root: Path | None = None,
) -> bool:
    """Verify that actual work was done (not just issue file moves).

    Returns True if there's evidence of implementation work - changes to files
    outside of excluded directories like .issues/, thoughts/, etc.

    This prevents marking issues as "completed" when no actual fix was implemented.

    Args:
        logger: Logger for output
        changed_files: Optional list of changed files. If not provided,
            will detect via git diff commands.
        baseline_sha: Optional git SHA captured before Phase 2 began. When provided
            and the working tree is clean, checks for commits made since this SHA
            (covers the case where the agent commits mid-phase and exits cleanly).
        config: Optional BRConfig used to resolve the tamper guard's
            (ENH-2933/ENH-2935) default policy and test-file patterns. The
            guard only runs when a config is supplied -- both `ll-auto`
            (issue_manager.py) and `ll-parallel`/`ll-sprint` (worker_pool.py)
            always have one in scope and pass it through; a caller with no
            config in scope (e.g. a bare unit test) gets the pre-ENH-2935
            behavior unchanged.
        repo_root: Optional repo root the tamper guard runs against; defaults
            to config.project_root when config is given.

    Returns:
        True if meaningful file changes were detected and the tamper guard
        did not fail them.
    """
    work_done = _detect_meaningful_changes(logger, changed_files, baseline_sha)
    if not work_done:
        return False
    if config is None:
        return True
    resolved_repo_root = repo_root or config.project_root
    if not _run_non_fsm_tamper_guard(logger, resolved_repo_root, config, baseline_sha):
        return False
    return True


def _detect_meaningful_changes(
    logger: Logger,
    changed_files: list[str] | None,
    baseline_sha: str | None,
) -> bool:
    """Original changed-files detection, unchanged by the ENH-2935 tamper guard hook."""
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
            f"No meaningful changes detected - only excluded files modified: {excluded_files[:10]}"
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

        # Check commits made since baseline (covers mid-phase commits in ll-auto)
        if baseline_sha:
            try:
                current_head = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                )
                if current_head.returncode == 0 and current_head.stdout.strip() != baseline_sha:
                    result = subprocess.run(
                        ["git", "diff", "--name-only", f"{baseline_sha}..HEAD"],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        committed = result.stdout.strip().split("\n")
                        meaningful_committed = filter_excluded_files(committed)
                        if meaningful_committed:
                            logger.info(
                                f"Found {len(meaningful_committed)} file(s) committed since "
                                f"baseline: {meaningful_committed[:5]}"
                            )
                            return True
                        all_excluded_files.extend(
                            [f for f in committed if f and f not in all_excluded_files]
                        )
            except Exception as e:
                logger.error(f"Could not check committed changes: {e}")

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
