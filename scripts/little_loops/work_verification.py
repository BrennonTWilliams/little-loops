"""Work verification utilities for little-loops.

Contains shared functions for verifying that actual implementation work
was done, used by both issue_manager (ll-auto) and worker_pool (ll-parallel).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.config.core import BRConfig
    from little_loops.logger import Logger
    from little_loops.parallel.git_lock import GitLock
    from little_loops.test_tamper_guard import TamperPolicy, TamperSnapshot


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


def _sample(paths: list[str], limit: int = 5) -> str:
    """Render *paths* truncated to *limit*, saying so when anything is elided.

    BUG-3055: these diagnostics used to pair a full ``len()`` with a bare
    ``[:5]`` slice, so a 9-file change printed as a 5-item list with no
    indication the rest existed — actively misleading when the log is the
    only forensic record of a failed automated run.
    """
    if len(paths) <= limit:
        return f"{paths}"
    return f"{paths[:limit]} (first {limit} of {len(paths)})"


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
    pre_step_snapshot: TamperSnapshot | None = None,
) -> bool:
    """Run the tamper guard (ENH-2933) against the current on-disk state.

    Runs the guard twice and ANDs the verdicts, covering two distinct windows:

    1. *Implement window* (unconditional, unchanged). Because this window
       spans the whole implement phase -- including legitimate TDD-mode test
       writes -- there is no live pre-step snapshot for it, so "before" is
       reconstructed from git history via ``snapshot_test_paths_at_ref``,
       using *baseline_sha* (or ``HEAD`` when unset) as the reference point.
       Findings are narrowed via ``filter_weakening_findings`` (BUG-2954) to
       edits that actually weaken the test suite, not merely change its
       bytes.
    2. *Post-implement window* (ENH-2958, only when *pre_step_snapshot* is
       given). A live snapshot captured at the end of the implement phase --
       mirroring the FSM adapter's (ENH-2934) snapshot-on-entry bracket --
       compared byte-strictly (no weakening filter) against the current
       on-disk state. This catches a mutation occurring strictly after
       implement returned (e.g. a worker's committed-leak recovery), which
       the implement-window heuristic could miss if it happens to preserve
       assertion/test counts.

    Returns True when both windows pass (nothing found, or an "allow"/
    "revert" policy resolved the findings); False when either window's
    "fail" policy trips on an unresolved finding -- the caller should treat
    that as verification failure regardless of other evidence of work.
    """
    from functools import partial

    from little_loops.test_tamper_guard import (
        filter_weakening_findings,
        run_tamper_guard,
        snapshot_test_paths_at_ref,
        tamper_guard_candidate_paths,
        tamper_guard_changed_files,
    )

    policy = _effective_tamper_guard_policy(config)

    ref = baseline_sha or "HEAD"
    candidate_paths = tamper_guard_candidate_paths(repo_root, config=config)
    changed = tamper_guard_changed_files(repo_root)

    # Implement window: git-reconstructed "before", weakening-filtered.
    before = snapshot_test_paths_at_ref(repo_root, ref, candidate_paths)
    finding_filter = partial(filter_weakening_findings, repo_root=repo_root, ref=ref)
    report = run_tamper_guard(before, changed, config, policy, repo_root, finding_filter)
    if not report.passed:
        logger.error(
            f"Tamper guard ({report.policy}) failed: "
            f"{[f.path for f in report.findings]} not resolved"
        )
    elif report.findings:
        logger.warning(
            f"Tamper guard ({report.policy}) found and handled: {[f.path for f in report.findings]}"
        )
    passed = report.passed

    # Post-implement window (ENH-2958): live snapshot, byte-strict, no filter.
    if pre_step_snapshot is not None:
        post_report = run_tamper_guard(pre_step_snapshot, changed, config, policy, repo_root)
        if not post_report.passed:
            logger.error(
                f"Post-implement tamper guard ({post_report.policy}) failed: "
                f"{[f.path for f in post_report.findings]} not resolved"
            )
        elif post_report.findings:
            logger.warning(
                f"Post-implement tamper guard ({post_report.policy}) found and handled: "
                f"{[f.path for f in post_report.findings]}"
            )
        passed = passed and post_report.passed

    return passed


def _prepatch_git(
    repo_root: Path, args: list[str], ok_codes: tuple[int, ...] = (0,)
) -> str | None:
    """Run a git command, returning stdout only when its exit code is in *ok_codes*.

    Mirrors ``fsm/executor.py``'s ``_prepatch_git`` (ENH-2997): ``git diff
    --no-index`` exits 1 (not 0) when it finds a difference, the expected
    outcome for every untracked-file fragment ``_prepatch_step_diff`` produces.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode not in ok_codes:
        return None
    return proc.stdout


def _prepatch_step_diff(repo_root: Path, base_ref: str) -> str:
    """Cumulative patch diff for the pre-patch check core's ``step_diff``.

    Mirrors ``fsm/executor.py``'s ``_prepatch_step_diff`` (ENH-2997): the whole
    patch under evaluation, ``git diff <base_ref>`` unioned with a
    ``--no-index`` fragment per untracked non-ignored path so newly added,
    not-yet-committed files are visible to the core's diff parser.
    """
    fragments: list[str] = []
    tracked = _prepatch_git(repo_root, ["diff", base_ref])
    if tracked:
        fragments.append(tracked)
    untracked = _prepatch_git(repo_root, ["ls-files", "--others", "--exclude-standard"])
    for path in (untracked or "").splitlines():
        if not path:
            continue
        fragment = _prepatch_git(
            repo_root, ["diff", "--no-index", "--", "/dev/null", path], ok_codes=(0, 1)
        )
        if fragment:
            fragments.append(fragment)
    return "\n".join(fragments)


def _prepatch_existing_forks(worktree_base: Path) -> set[Path]:
    """Snapshot the ``prepatch-*`` forks already present under *worktree_base*."""
    try:
        return {p for p in worktree_base.iterdir() if p.name.startswith("prepatch-")}
    except OSError:
        return set()


def _prepatch_teardown(
    repo_root: Path,
    worktree_base: Path,
    forks_before: set[Path],
    evidence: Any,
    logger: Logger,
    git_lock: GitLock,
) -> None:
    """Clean up the fork(s) the core leaves behind, following ENH-2997's teardown contract.

    ``run_prepatch_check()`` does not clean up its own fork on the success
    path, and an exception path leaves no ``PrePatchEvidence`` bound at all --
    so any new ``prepatch-*`` directory under *worktree_base* is fair game.
    """
    from little_loops.worktree_utils import cleanup_worktree

    targets: list[Path] = []
    if evidence is not None and getattr(evidence, "worktree_path", None) is not None:
        targets.append(Path(evidence.worktree_path))
    targets.extend(sorted(_prepatch_existing_forks(worktree_base) - forks_before - set(targets)))
    for target in targets:
        try:
            cleanup_worktree(target, repo_root, logger, git_lock, delete_branch=True)
        except Exception:
            pass


def _run_non_fsm_prepatch_check(
    logger: Logger,
    repo_root: Path,
    config: BRConfig,
    issue_id: str,
    git_lock: GitLock | None = None,
) -> bool:
    """Run the pre-patch check (ENH-3142) against the current diff for *issue_id*.

    Mirrors ``fsm/executor.py``'s ``_check_prepatch_check()`` (ENH-2997): resolves
    ``(base_sha, base_dirty)`` from ``.ll/history.db`` via ``read_base_sha``/
    ``read_base_dirty``, forks a pre-patch worktree, runs the candidate tests,
    persists the resulting ``PrePatchEvidence`` to ``.ll/history.db`` via
    ``record_prepatch_evidence()`` (the surface ``cli/harness.py`` reads), and
    tears the fork down in a ``finally`` -- on both the success and exception
    paths.

    ``config.prepatch_check.enabled`` (default ``False``) is this check's only
    off-switch, matching the tamper guard's ``config is not None`` gate shape;
    the adapter adds no second one. When disabled, this returns True without
    touching git or the database.

    Unlike the tamper guard, there is no per-caller fail/warn/allow policy for
    the non-FSM path (``PrePatchCheckConfig`` has no ``policy`` field) -- a
    ``flagged`` verdict fails verification outright, the same way an unresolved
    tamper-guard finding does under the default "fail" policy.

    Returns True when the check is disabled, skipped (red run guard is the
    caller's responsibility -- this is only reached after
    ``_detect_meaningful_changes`` and the tamper guard already passed), or
    clean; False when the check ran and flagged the diff.
    """
    if not config.prepatch_check.enabled:
        return True

    from little_loops.history_reader import read_base_dirty, read_base_sha
    from little_loops.parallel.git_lock import GitLock
    from little_loops.prepatch_check import resolve_base_ref, run_prepatch_check
    from little_loops.session_store import record_prepatch_evidence, resolve_history_db

    history_db = resolve_history_db()
    base_sha = read_base_sha(issue_id, db=history_db)
    base_dirty = read_base_dirty(issue_id, db=history_db)
    base_branch = config.parallel.base_branch or "main"
    base_ref, _base_source = resolve_base_ref(repo_root, base_sha, base_branch)
    step_diff = _prepatch_step_diff(repo_root, base_ref)

    worktree_base = config.get_worktree_base()
    # Threaded when the caller already owns one (worker_pool.py's
    # self._git_lock); constructed locally otherwise (issue_manager.py has
    # no GitLock anywhere in the file) -- mirrors fsm/executor.py's local
    # construction, the one in-repo precedent for the "state which" choice
    # ENH-2998's Design Notes call out.
    wt_git_lock = git_lock or GitLock(logger)

    forks_before = _prepatch_existing_forks(worktree_base)
    evidence = None
    try:
        evidence = run_prepatch_check(
            step_diff=step_diff,
            repo_root=repo_root,
            worktree_base=worktree_base,
            base_sha=base_sha,
            base_dirty=base_dirty,
            base_branch=base_branch,
            logger=logger,
            git_lock=wt_git_lock,
            config=config,
        )
    finally:
        _prepatch_teardown(repo_root, worktree_base, forks_before, evidence, logger, wt_git_lock)

    try:
        record_prepatch_evidence(
            history_db,
            issue_id=issue_id,
            evidence=evidence.to_dict(),
        )
    except Exception:
        pass

    if evidence.verdict == "flagged":
        logger.error(
            f"Pre-patch check flagged {len(evidence.outcomes)} candidate test(s) "
            f"against {evidence.base_ref}"
        )
        return False
    return True


def verify_work_was_done(
    logger: Logger,
    changed_files: list[str] | None = None,
    baseline_sha: str | None = None,
    config: BRConfig | None = None,
    repo_root: Path | None = None,
    pre_step_snapshot: TamperSnapshot | None = None,
    issue_id: str | None = None,
    git_lock: GitLock | None = None,
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
        pre_step_snapshot: Optional live ``snapshot_test_paths(...)`` captured
            by the caller at the end of the implement phase (ENH-2958). When
            given, the tamper guard runs a second, byte-strict comparison
            against this snapshot -- covering the post-implement window --
            in addition to (not instead of) the git-reconstructed
            implement-window comparison. ``None`` (the default) preserves
            today's behavior unchanged: one git-reconstructed guard run.
        issue_id: Optional issue ID (ENH-2998) used to resolve the pre-patch
            check's (ENH-3142/ENH-2997) base SHA/dirty flag from
            ``.ll/history.db`` and to persist its evidence bundle there. The
            check only runs when both ``config`` and ``issue_id`` are given
            and ``config.prepatch_check.enabled`` is true (default false) --
            its only off-switch. ``None`` preserves prior behavior unchanged.
        git_lock: Optional caller-owned ``GitLock`` (ENH-2998) the pre-patch
            check's worktree fork uses; when omitted, one is constructed
            locally. Unused when the pre-patch check does not run.

    Returns:
        True if meaningful file changes were detected and neither the tamper
        guard nor the pre-patch check failed them.
    """
    work_done = _detect_meaningful_changes(logger, changed_files, baseline_sha)
    if not work_done:
        return False
    if config is None:
        return True
    resolved_repo_root = repo_root or config.project_root
    if not _run_non_fsm_tamper_guard(
        logger, resolved_repo_root, config, baseline_sha, pre_step_snapshot
    ):
        return False
    if issue_id and not _run_non_fsm_prepatch_check(
        logger, resolved_repo_root, config, issue_id, git_lock
    ):
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
                f"Found {len(meaningful_changes)} file(s) changed: {_sample(meaningful_changes)}"
            )
            return True
        # Log which excluded files were modified for diagnostic purposes
        excluded_files = [f for f in changed_files if f]
        logger.warning(
            f"No meaningful changes detected - only excluded files modified: "
            f"{_sample(excluded_files, 10)}"
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
                    f"Found {len(meaningful_changes)} file(s) changed: {_sample(meaningful_changes)}"
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
                    f"Found {len(meaningful_staged)} staged file(s): {_sample(meaningful_staged)}"
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
                                f"baseline: {_sample(meaningful_committed)}"
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
                f"{_sample(all_excluded_files, 10)}"
            )
        else:
            logger.warning("No meaningful changes detected - no files modified")
        return False

    except Exception as e:
        logger.error(f"Could not verify work: {e}")
        # Be conservative - don't assume work was done if we can't verify
        return False
