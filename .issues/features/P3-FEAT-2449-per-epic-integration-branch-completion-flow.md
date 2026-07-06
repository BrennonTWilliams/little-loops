---
id: FEAT-2449
title: per-EPIC integration branch — EPIC-completion merge + orchestrator/sprint awareness
type: FEAT
priority: P3
status: open
captured_at: '2026-07-02T22:30:00Z'
discovered_date: 2026-07-02
discovered_by: issue-size-review
labels:
- parallel
- sprint
- epics
- git
- merge
- completion
parent: EPIC-2451
relates_to:
- FEAT-2339
- EPIC-2451
- FEAT-2447
- FEAT-2448
- FEAT-2450
blocked_by:
- FEAT-2448
decision_needed: false
confidence_score: 95
outcome_confidence: 55
score_complexity: 7
score_test_coverage: 18
score_ambiguity: 6
score_change_surface: 0
---

# FEAT-2449: per-EPIC integration branch — EPIC-completion merge + orchestrator/sprint awareness

## Summary

Third of four sequenced children decomposed from FEAT-2339. This child
implements **EPIC-completion detection** (when all children of an EPIC
reach `done`, merge the `epic/<EPIC-ID>-<slug>` integration branch
into `base_branch` or open one PR), and threads epic-branch awareness
through the remaining cross-module sites: orchestrator inspection,
sprint-runner in-place warning, and the partial-failure gate that
blocks the completion-merge when any child has failed.

Depends on FEAT-2448 (worker_pool + merge_coordinator wiring +
`WorkerResult.epic_branch` field).

## Parent Issue

Decomposed from FEAT-2339: Per-EPIC integration branch strategy for
ll-parallel/ll-sprint.

## Scope

1. **EPIC-completion detection** — in the orchestrator's
   post-merge flow, call
   `compute_epic_progress(epic_id, all_issues)` from
   `scripts/little_loops/issue_progress.py:83` (walks the `parent:`
   chain transitively per commit `4887c87c`). When
   `prog.done_count == prog.total_count` and there are no failed
   children (gate per Decision Rationale #2 — "Block until all
   children are done"), merge the epic branch to `base_branch` (or
   open one PR via `gh pr create --base base_branch --head epic/<id>`,
   analogous to the existing `orchestrator._open_pr_for_branch()`
   pattern). Then delete the epic branch (explicit deletion only —
   **not** via `_is_ll_branch()` or `_cleanup_worktree()`; see
   FEAT-2339 Decision Rationale #3).
2. **`_open_pr_for_branch()` epic-child PR target** — when a
   `WorkerResult.epic_branch` is set, the per-child PR created during
   normal merge flow lands on the epic branch
   (`--base epic/<id>` instead of `--base base_branch`). This
   completes the FEAT-2448 consumer-site change at
   `orchestrator.py:1142` to a fully-functional epic-child PR
   target.
3. **Orchestrator `_inspect_worktree()` epic-awareness**
   (`scripts/little_loops/parallel/orchestrator.py`) — the
   `rev-list --count base_branch..branch_name` call at line 415
   (drifted from ~400 per FEAT-2339 anchor corrections) must compare
   against the epic branch when the inspected worktree is an EPIC
   child. Update
   `test_cleanup_orphaned_worktrees` (line 509) and
   `test_inspect_worktree_with_feature_branch` (line 1001) for
   epic-prefix handling.
4. **`cli/sprint/run.py` in-place/contention-subwave warning**
   (lines 485, 518–528) — add a parallel `effective_epic_branches`
   check (identical shape to `effective_feature_branches`) and append
   to the existing warning message rather than replacing it,
   preserving the `"feature-branch mode does not apply"` substring
   that `scripts/tests/test_cli_sprint.py:TestFeatureBranchInPlaceWarning`
   asserts on (per FEAT-2339 Decision Rationale #4).
5. **Partial-failure gate** — completion-merge is blocked until
   **ALL** children reach `done`; a failed/blocked child holds the
   epic branch open (unmerged, undeleted). Reuse the existing
   `Orchestrator.run()` precedent for group-failure gating
   (`failed_count == 0` all-or-nothing cleanup gate at
   `orchestrator.py:827-831`). Cross-reference
   `state.failed_issues` / `queue.failed_ids` against the EPIC's
   child-ID set (computed via the depth-aware helper from FEAT-2447)
   — no existing structure already scopes these dicts by EPIC.
6. **Tests** —
   - `scripts/tests/test_sprint.py:TestSprintManagerLoadOrResolve`
     (~lines 2329–2540, "FEAT-1737") — add nested-EPIC test
     (grandchild with intermediate sub-EPIC parent) to cover the
     run-construction depth-mismatch (sprint.py still does direct-only
     `info.parent == epic_id` resolution — confirms and tests the
     known gap, independent of the branch-routing flatten-to-nearest
     decision).
   - `scripts/tests/test_cli_sprint.py:TestFeatureBranchInPlaceWarning`
     — add an `epic_branches` counterpart once the in-place warning
     is made epic-aware (must not break the existing
     `"feature-branch mode does not apply"` substring assertion).
   - `scripts/tests/test_orchestrator.py` — new tests for
     `_inspect_worktree` epic-branch comparison and
     `_open_pr_for_branch()` `--base epic/<id>` epic-child PR target.
   - `scripts/tests/test_worker_pool.py` —
     `test_inspect_worktree_with_feature_branch` (line 1001) audit
     and update for `epic/*` prefix handling.
   - Partial-failure gate: test that EPIC-completion-merge is
     blocked when any child is `failed` or `blocked`, not just when
     `done_count < total_count`.

## Out of Scope (deferred to follow-on child)

- CLI flags (`--epic-branches`), TUI surface, configure skill updates
  — **FEAT-2450**.
- Docs (ARCHITECTURE, API, CONFIGURATION, CLI, SPRINT_GUIDE), 9
  templates parity, prune_merged_feature_branches docstring — **FEAT-2450**.

## Acceptance Criteria

- [ ] When all children of an EPIC reach `done` (and no children are
      failed/blocked), the orchestrator triggers a merge of
      `epic/<EPIC-ID>-<slug>` into `base_branch` (or opens one PR
      per `epic_branches.open_pr` config).
- [ ] When any child is failed/blocked, the epic branch is held
      open (no merge, no delete) — verified by partial-failure gate
      test.
- [ ] Per-child PRs (in normal merge flow, not completion merge)
      target the epic branch (`--base epic/<id>`) when
      `WorkerResult.epic_branch` is set.
- [ ] `_inspect_worktree()` correctly compares against the epic
      branch for EPIC children.
- [ ] `cli/sprint/run.py` in-place warning fires an
      epic-branches-aware variant; existing
      `"feature-branch mode does not apply"` substring test still
      passes.
- [ ] Nested-EPIC test in `TestSprintManagerLoadOrResolve` covers
      grandchild-via-sub-EPIC.
- [ ] Full `python -m pytest scripts/tests/` exits 0.

## Files Touched

**Implementation:**
- `scripts/little_loops/parallel/orchestrator.py`
  (EPIC-completion trigger, `_open_pr_for_branch()` epic-child PR
  target, `_inspect_worktree()` epic-awareness)
- `scripts/little_loops/cli/sprint/run.py` (in-place warning
  epic-awareness at lines 485, 518–528)

**Tests:**
- `scripts/tests/test_sprint.py` (nested-EPIC test)
- `scripts/tests/test_cli_sprint.py`
  (`TestFeatureBranchInPlaceWarning` epic counterpart)
- `scripts/tests/test_orchestrator.py` (epic-completion merge +
  epic-child PR target + inspect epic-awareness)
- `scripts/tests/test_worker_pool.py` (epic/* prefix audit)

**Estimated file count:** 2 implementation + 4 test = **6 files**.

## Session Log
- `/ll:issue-size-review` - 2026-07-02T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e2b9d4e-1bf7-4b43-940f-7c8cc95fcaf4.jsonl`

## Blocks

- FEAT-2450
