---
id: FEAT-2562
title: per-EPIC integration branch — _inspect_worktree() epic-branch comparison
type: FEAT
priority: P3
status: open
captured_at: '2026-07-09T00:00:00Z'
discovered_date: 2026-07-09
discovered_by: confidence-check-decomposition
labels:
- parallel
- epics
- git
- worktree
parent: EPIC-2451
relates_to:
- EPIC-2451
- FEAT-2447
- FEAT-2448
- FEAT-2449
- FEAT-2561
blocked_by:
- FEAT-2561
unblocks:
- FEAT-2450
decision_needed: false
---

# FEAT-2562: per-EPIC integration branch — _inspect_worktree() epic-branch comparison

## Summary

Unit B extracted from FEAT-2449 (decomposed via `/ll:confidence-check` on
2026-07-09). Makes the orchestrator's `_inspect_worktree()` commit-count
comparison **epic-aware**: when the inspected worktree is an EPIC child, the
`rev-list --count` must compare against the EPIC integration branch, not
`base_branch` — otherwise an EPIC child's commits are miscounted (they diverge
from `epic/<id>`, not from `main`).

This is a single-method logic change plus a test audit; it is independent of
FEAT-2449's completion/merge lifecycle and of FEAT-2563's sprint warning. It
depends only on the shared EPIC-ancestor helper (FEAT-2561) to map the inspected
worktree's issue-ID to its EPIC.

## Parent Issue

Decomposed from FEAT-2449 on 2026-07-09 (was Scope item #3). EPIC-2451 is the
parent EPIC and remains the coordination container.

## Scope

1. **`_inspect_worktree()` epic-branch comparison base**
   (`scripts/little_loops/parallel/orchestrator.py`) — the issue-ID is parsed
   from the worktree directory name at `orchestrator.py:410`
   (`re.match(r"worker-([a-z]+-\d+)-\d{8}-\d{6}", worktree_path.name)`). The
   `rev-list --count` call at `orchestrator.py:415` currently reads
   `{self.parallel_config.base_branch}..{branch_name}`. Change the comparison
   base to `{epic_branch or base_branch}..{branch_name}` when the worktree's
   issue is an EPIC child:
   - Resolve the issue's EPIC via the FEAT-2561 shared helper
     (`find_nearest_epic_ancestor(issue, build_parent_map(all_issues))`), using
     the orchestrator's `self._issue_info_by_id` (`orchestrator.py:128, 773`) as
     the issue source.
   - Only substitute the base when `epic_branches.enabled` and an EPIC ancestor
     exists; otherwise byte-for-byte identical to today (no-op for non-EPIC runs).

   > **Helper dependency**: if this child somehow lands before FEAT-2561, it may
   > call `self.worker_pool._find_nearest_epic_ancestor(issue)` as a fallback —
   > but the intended path is the shared module helper. FEAT-2561 is the declared
   > blocker to avoid the private-method reach.

2. **Tests** —
   - `scripts/tests/test_orchestrator.py::TestInspectWorktree`
     (`:909-1082`, 6 tests that mock `git rev-list --count` and assert on its
     args) — audit each for compatibility with the
     `{epic_branch or base_branch}..{branch_name}` shape. Specifically
     `test_returns_actual_branch_for_feature_branch_mode` (~`:998-1024`) plus the
     5 others at `:912, 941, 974, 995, 1054`. Non-EPIC fixtures must keep
     asserting `main..<branch>`; add at least one EPIC-child fixture asserting
     `epic/<id>..<branch>`.
   - `scripts/tests/test_orchestrator.py::TestOrphanedWorktreeCleanup`
     (`:319-516`), specifically `test_deletes_branch_via_rev_parse` (`:485`) —
     add an `epic/*` audit verifying an `epic/<EPIC-ID>-<slug>` branch is **NOT**
     deleted by `_cleanup_orphaned_worktrees` (FEAT-2339 Decision Rationale #3 /
     ARCHITECTURE-094 — epic branches are explicitly-deleted only, never via the
     `parallel/*` cleanup gate).

   > **Anchor correction (carried from FEAT-2449 wiring pass)**: the stale
   > reference to `test_inspect_worktree_with_feature_branch` at
   > `test_worker_pool.py:1001` is wrong — the real target is
   > `test_returns_actual_branch_for_feature_branch_mode` at
   > `test_orchestrator.py:~998`; `test_worker_pool.py:1001` is unrelated
   > worktree-setup code.

## Out of Scope

- EPIC-completion detection, completion-merge/PR, partial-failure gate,
  config-branch wiring — **FEAT-2449**.
- `cli/sprint/run.py` in-place warning — **FEAT-2563**.
- Any change to `_is_ll_branch()` / `cleanup_worktree()` in `worktree_utils.py`
  (must NOT match `epic/*` — FEAT-2339 Decision Rationale #3) or to
  `MergeCoordinator._cleanup_worktree()` (`parallel/` prefix hardcode is correct
  by accident) — boundary-preserved.

## Acceptance Criteria

- [ ] `_inspect_worktree()` compares against the epic branch for EPIC children
      (`epic/<id>..<branch>`) and against `base_branch` otherwise.
- [ ] With `epic_branches.enabled=False` (default), behavior is byte-for-byte
      identical — non-EPIC `TestInspectWorktree` fixtures still assert
      `main..<branch>`.
- [ ] At least one new EPIC-child fixture in `TestInspectWorktree` asserts the
      `epic/<id>..<branch>` comparison base.
- [ ] `TestOrphanedWorktreeCleanup` gains an `epic/*` NOT-deleted audit.
- [ ] Full `python -m pytest scripts/tests/` exits 0.

## Files Touched

**Implementation (1 file):**
- `scripts/little_loops/parallel/orchestrator.py` (`_inspect_worktree` comparison
  base at `:415`, EPIC resolution via FEAT-2561 helper)

**Tests (1 file):**
- `scripts/tests/test_orchestrator.py` (`TestInspectWorktree` audit + EPIC
  fixture; `TestOrphanedWorktreeCleanup` epic/* audit)

**Estimated file count:** 1 implementation + 1 test = **2 files**.

## Integration Map

- **Files to Modify**: `parallel/orchestrator.py`
- **Depends On**: FEAT-2561 (`find_nearest_epic_ancestor` / `build_parent_map`)
- **Similar Patterns**: the `rev-list --count` comparison-base idiom already used
  for feature-branch mode elsewhere in `_inspect_worktree`; mirror its
  enabled-guard shape.
- **Tests**: `TestInspectWorktree` (`:909-1082`), `TestOrphanedWorktreeCleanup`
  (`:319-516`)
- **Boundary (do NOT modify)**: `worktree_utils.py` `_is_ll_branch()` /
  `cleanup_worktree()`; `merge_coordinator.py` `_cleanup_worktree()`.

## Blocks

- FEAT-2450 (CLI/TUI/docs polish waits on all functional epic-branch work)

## Session Log
- `/ll:confidence-check` - 2026-07-09T00:00:00 - `b4b437e8-ceeb-4657-a600-ad4fd9cabd3d.jsonl` (decomposition of FEAT-2449)
