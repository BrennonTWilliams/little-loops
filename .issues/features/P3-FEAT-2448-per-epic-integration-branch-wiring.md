---
id: FEAT-2448
title: per-EPIC integration branch — worker_pool + merge_coordinator wiring
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
- worktree
- merge
parent: EPIC-2451
relates_to:
- FEAT-2339
- EPIC-2451
- EPIC-2447
- EPIC-2449
- FEAT-2450
blocked_by:
- EPIC-2447
decision_needed: false
confidence_score: 95
outcome_confidence: 60
score_complexity: 7
score_test_coverage: 18
score_ambiguity: 6
score_change_surface: 0
---

# FEAT-2448: per-EPIC integration branch — worker_pool + merge_coordinator wiring

## Summary

Second of four sequenced children decomposed from FEAT-2339. This child
**wires the resolver into worker_pool and merge_coordinator** so that
when epic mode is active, an EPIC child's branch forks from and merges
into the shared `epic/<EPIC-ID>-<slug>` branch instead of
`base_branch`. Carries the cross-module state threading
(`WorkerPool` → `MergeCoordinator`) flagged as the load-bearing risk
in FEAT-2339's Confidence Check Notes.

Depends on FEAT-2447 (config + `_resolve_branch_targets` resolver).

## Parent Issue

Decomposed from FEAT-2339: Per-EPIC integration branch strategy for
ll-parallel/ll-sprint.

## Scope

1. **Branch-naming + worktree setup**
   (`scripts/little_loops/parallel/worker_pool.py:334-360`) — when
   epic mode active and `issue.parent` resolves to an EPIC, name the
   worker's branch per today's `feature/<id>-<slug>` /
   `parallel/<id>-<timestamp>` convention (decision: epic mode
   changes only the fork point and merge target, **not** the child's
   branch name — see FEAT-2339 Decision Rationale #3). Pass the
   resolver's fork point as `base_branch` to
   `_setup_worktree(base_branch=...)` instead of
   `self.parallel_config.base_branch`.
2. **`WorkerResult.epic_branch` field** — add
   `epic_branch: str | None = None` to `WorkerResult` in
   `scripts/little_loops/parallel/types.py` with matching
   `to_dict()` / `from_dict()` rows, mirroring how `was_blocked`
   (ENH-036) and `interrupted` were added. Populate **once** in
   `WorkerPool._process_issue()` at the same site as `branch_name` /
   `worktree_path`, immediately above the
   `_setup_worktree(base_branch=...)` call. The fork point and merge
   target are the same string per Decision Rationale #1 (flatten to
   nearest), so the same `_resolve_branch_targets()` return value
   threads through both.
3. **Three downstream consumer sites** — replace
   `base = self.config.base_branch` with
   `base = result.epic_branch or self.config.base_branch` at:
   - `scripts/little_loops/parallel/merge_coordinator.py:624`
     (checkout in `_process_single_merge()`)
   - `scripts/little_loops/parallel/merge_coordinator.py:875`
     (fetch + rebase in same method)
   - `scripts/little_loops/parallel/orchestrator.py:1142` — note:
     `_open_pr_for_branch()` itself stays untouched here; only the
     `--base <value>` read site switches to the epic branch (the full
     PR target decision is FEAT-2449's "child PR lands on epic
     branch" step).
4. **`_get_changed_files()` epic-mode variant**
   (`scripts/little_loops/parallel/worker_pool.py`) — when an issue
   has `epic_branch` set, diff against the epic branch
   (`git diff --name-only <epic_branch> HEAD`) for accurate
   changed-file detection when children share the epic branch.
5. **`_update_branch_base()` epic-mode variant**
   (`scripts/little_loops/parallel/worker_pool.py:_update_branch_base`) —
   when epic mode active, rebase against the epic branch instead of
   `<remote>/<base_branch>`. Three existing tests at
   `scripts/tests/test_worker_pool.py:1714–1791` set
   `worker_pool.parallel_config.base_branch = "main"` before calling
   `_update_branch_base()`; add epic-mode counterparts.
6. **Tests** —
   - `scripts/tests/test_worker_pool.py:test_process_issue_uses_feature_branch_name_when_enabled`
     (lines 2191–2236) — add explicit `issue.parent = None` when this
     area is touched (per FEAT-2339 second-pass Tests finding: a
     MagicMock without `parent` would have a truthy auto-attribute once
     epic-mode branch-naming checks `issue.parent`).
   - `scripts/tests/test_worker_pool.py` — new epic-mode variants of
     `_update_branch_base` tests asserting rebase target is the epic
     branch when `epic_branches.enabled=True` and `issue.parent` is
     set.
   - `scripts/tests/test_merge_coordinator.py` — new
     `test_*_epic_branch_*` tests verifying that `MergeCoordinator`
     routes the merge target to the epic branch (not `base_branch`)
     when the issue has a parent EPIC and
     `epic_branches.enabled=True`. Modeled on the existing
     `test_*_untracked_files_error` / `test_*_local_changes_error`
     patterns.
   - `scripts/tests/test_orchestrator.py:test_on_worker_complete_feature_branch_open_pr`
     (lines 2008–2052) — add an assertion on the actual `--base`
     value so a silent regression in `_open_pr_for_branch()`'s
     `--base` target switching would be caught.
   - `scripts/tests/test_subprocess_mocks.py:test_setup_worktree_with_base_branch_appends_commit_ish`
     (~line 615) plus the two assertions at ~838 and ~892 — add
     epic-branch-substitution counterparts covering the new path.

## Out of Scope (deferred to follow-on children)

- EPIC-completion → epic-branch merge logic — **FEAT-2449**.
- Orchestrator `_inspect_worktree()` rev-list comparison against
  epic branch — **FEAT-2449**.
- `cli/sprint/run.py` in-place warning epic-awareness — **FEAT-2449**.
- CLI flags (`--epic-branches`), TUI surface, configure skill updates
  — **FEAT-2450**.
- Docs, 9 templates parity, prune_merged_feature_branches docstring
  — **FEAT-2450**.

## Acceptance Criteria

- [ ] When `epic_branches.enabled=True` and an issue has an EPIC
      parent, the worker's branch forks from
      `epic/<EPIC-ID>-<slug>` (verified in
      `_setup_worktree(base_branch=...)` capture in
      `test_subprocess_mocks.py`).
- [ ] `WorkerResult.epic_branch` is populated for EPIC children and
      None for standalone issues.
- [ ] `_process_single_merge()` checks out and rebases against
      `result.epic_branch or self.config.base_branch` at
      `merge_coordinator.py:624` and `:875`.
- [ ] `_open_pr_for_branch()` reads `--base` from
      `result.epic_branch or self.config.base_branch` at
      `orchestrator.py:1142`.
- [ ] `_get_changed_files()` diffs against `epic_branch` when set.
- [ ] `_update_branch_base()` rebases against the epic branch when
      epic mode active.
- [ ] With `epic_branches.enabled=False` (default), behavior is
      byte-for-byte identical to today (regression-tested via the
      updated `_update_branch_base` and `_process_issue` tests).
- [ ] Full `python -m pytest scripts/tests/` exits 0.

## Files Touched

**Implementation:**
- `scripts/little_loops/parallel/worker_pool.py` (branch naming,
  worktree setup, `_get_changed_files`, `_update_branch_base`,
  `_process_issue`)
- `scripts/little_loops/parallel/merge_coordinator.py` (two consumer
  sites at :624 and :875)
- `scripts/little_loops/parallel/orchestrator.py` (one consumer site
  at :1142 — read only; full PR-target logic is FEAT-2449)
- `scripts/little_loops/parallel/types.py` (`WorkerResult.epic_branch`
  field + `to_dict`/`from_dict`)

**Tests:**
- `scripts/tests/test_worker_pool.py`
- `scripts/tests/test_merge_coordinator.py`
- `scripts/tests/test_orchestrator.py`
- `scripts/tests/test_subprocess_mocks.py`

**Estimated file count:** 4 implementation + 4 test = **8 files**.

## Cross-Module State Threading

This child carries the cross-module state threading risk flagged in
FEAT-2339's Confidence Check Notes. The chosen shape (`WorkerResult.epic_branch`
field, populated once at the same site as `branch_name`) keeps
"what the worker forked from" and "where the merge should land" as the
same string by construction — no synchronization point where merge
target can disagree with fork point.

## Session Log
- `/ll:issue-size-review` - 2026-07-02T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e2b9d4e-1bf7-4b43-940f-7c8cc95fcaf4.jsonl`

## Blocks

- EPIC-2449
