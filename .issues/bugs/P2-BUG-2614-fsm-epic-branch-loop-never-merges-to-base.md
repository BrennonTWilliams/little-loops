---
id: BUG-2614
type: BUG
priority: P2
status: open
captured_at: '2026-07-12T17:56:40Z'
discovered_date: 2026-07-12
discovered_by: capture-issue
relates_to: [ENH-2601, EPIC-2575]
---

# BUG-2614: FSM epic-branch loop never merges the epic branch back to base

## Summary

`auto-refine-and-implement.yaml` (and its callers `sprint-refine-and-implement.yaml`
/ `autodev.yaml`) create and commit to the `epic/<EPIC-ID>-<slug>` integration
branch when `parallel.epic_branches.enabled` is `true`, but no state in that
loop ever merges the branch back to `base_branch`. The merge-back logic
(`_merge_epic_branch_to_base`, `scripts/little_loops/parallel/orchestrator.py:1388`)
exists and is fully wired for the `ll-parallel` worker-pool path
(`_maybe_complete_epic` → `_on_worker_complete`,
`scripts/little_loops/parallel/orchestrator.py:1129,1227`), but the FSM loop
path never calls it. `finalize` in `auto-refine-and-implement.yaml`
(lines 348-531) only reads from the branch (`git ls-tree` / `git grep`
against ledgers/snapshots) — it has no merge step.

Confirmed empirically on `EPIC-2575`: FEAT-2576 was implemented and marked
`done` entirely inside
`epic/epic-2575-code-knowledge-graph-adapter-query-protocol-providers-skill-integration`
(commit `53512663`), but the branch was never merged and is now several
commits behind `main` with no automatic path back.

## Current Behavior

With `parallel.epic_branches.merge_to_base_on_complete: true`:
- `ll-parallel` runs: epic branch merges to base once all children are `done`.
- `auto-refine-and-implement` / `autodev` FSM runs: epic branch is created,
  committed to, and left open indefinitely. The config flag is silently
  unhonored on this path.

## Expected Behavior

When an epic-scoped `auto-refine-and-implement` run finishes (all resolved
children `done`, per whatever gate `finalize` already uses to decide the run
is complete) and `parallel.epic_branches.merge_to_base_on_complete` is
`true`, the loop should invoke the same merge-back (and, if
`verify_before_merge` is set, the same verify gate) that `ll-parallel`
already uses, rather than leaving the branch to merge manually or never.

## Root Cause

- **File**: `scripts/little_loops/loops/auto-refine-and-implement.yaml`
- **Anchor**: `finalize` state (lines 348-531)
- **Cause**: ENH-2601 (which added epic-branch awareness to this loop) scoped
  only "checkout epic branch before delegating" + "add a post-implement
  verify state" — merge-back to base was never part of its Expected
  Behavior and no follow-up issue was filed for it. `_merge_epic_branch_to_base`
  in `scripts/little_loops/parallel/orchestrator.py:1388` is reachable only
  from `WorkerPool`'s completion callback, not from the FSM executor, so
  there is no code path connecting FSM-loop completion to the existing
  merge logic.

## Motivation

Epic branches created by `ll-parallel` self-heal (merge automatically once
children finish); epic branches created by the FSM loop path do not, and
nothing surfaces that difference to the user. The branch silently
accumulates completed work that never reaches `main`, and by the time
someone notices (as happened with EPIC-2575), the branch has drifted stale
against unrelated `main` commits, turning a simple fast-forward-able merge
into a manual reconciliation. This defeats the stated purpose of
`merge_to_base_on_complete: true` for an entire class of runs.

## Proposed Solution

Add a merge-back step to the FSM epic-branch path, reusing the existing
orchestrator logic rather than reimplementing it:

1. Extract (or directly call) `_merge_epic_branch_to_base` /
   `_verify_epic_branch_before_merge` from
   `scripts/little_loops/parallel/orchestrator.py` so both `WorkerPool` and
   the FSM `finalize` state can invoke the same merge/verify code.
2. In `auto-refine-and-implement.yaml`'s `finalize` state (or a new state
   immediately before it), when scope resolved to an EPIC and
   `parallel.epic_branches.merge_to_base_on_complete` is `true`, call that
   shared merge function once all resolved children are `done`.
3. On merge failure (or verify failure, if `verify_before_merge` is set),
   surface it the same way `orchestrator.py` does today (flag needing manual
   attention) rather than silently leaving the branch unmerged with no
   signal.
4. Add regression coverage: an FSM-driven epic run with
   `merge_to_base_on_complete: true` should end with the epic branch's
   commits present on `base_branch`.

## Impact

- **Priority**: P2 — the config flag is silently non-functional for an
  entire, real execution path (any epic worked via the FSM loop rather than
  `ll-parallel`), and the failure mode is "completed work quietly never
  reaches base" rather than a loud error.
- **Effort**: Medium — the merge/verify logic already exists and is proven;
  this is primarily plumbing a call from the FSM `finalize` state plus
  extracting the orchestrator functions into a shared location.
- **Risk**: Low-medium — touches the epic-completion path for both
  `ll-parallel` and FSM loops if the extraction isn't careful to preserve
  existing `ll-parallel` behavior exactly.

## Session Log
- `/ll:capture-issue` - 2026-07-12T17:56:40Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/655a2464-a4d4-4557-b538-8038528dc56f.jsonl`

---

## Status

- [ ] Not started
