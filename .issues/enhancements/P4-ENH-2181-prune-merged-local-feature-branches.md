---
id: ENH-2181
title: Prune merged local feature branches (feature-branch lifecycle/cleanup)
type: ENH
status: open
priority: P4
parent: EPIC-2171
captured_at: '2026-06-15T00:00:00Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels: [parallel, feature-branches, cleanup, worktrees, lifecycle, dx]
relates_to: [BUG-2172, ENH-2175]
---

# ENH-2181: Prune merged local feature branches (feature-branch lifecycle/cleanup)

## Summary

Feature branches created in `use_feature_branches` mode are retained forever in
the main repo — worktree cleanup deletes only `parallel/*` branches, and nothing
ever removes a `feature/<id>-<slug>` branch after its PR merges. Provide an
opt-in prune that deletes local feature branches already merged into the base
branch, and document the retention behavior so the accumulation is intentional,
not a surprise.

## Motivation

The feature-branch path deliberately *retains* its branch (skip auto-merge,
survive worktree cleanup) so the user can push / open a PR. But there is no
back-end of that lifecycle:

- `worker_pool.py:631` deletes a worktree's branch only when it starts with
  `parallel/`; `feature/*` branches are explicitly kept.
- `/ll:cleanup-worktrees` removes orphaned worktrees but does not touch retained
  feature branches.
- Nothing — not the orchestrator, not any CLI — ever deletes a `feature/*` branch
  after its PR is merged.

Over many runs the main repo accumulates dozens of stale `feature/<id>-<slug>`
refs whose work is long since merged. For a workflow meant to be the default
development loop, the missing cleanup half makes the local branch list unusable.

## Current Behavior

- `parallel/worker_pool.py:630-631` — `delete_branch = branch_name is not None and
  branch_name.startswith("parallel/")`; `feature/*` survives by design.
- `/ll:cleanup-worktrees` — prunes worktrees, not branches.
- No `git branch --merged` style prune anywhere in the parallel code.

## Expected Behavior

- An explicit, opt-in command/flag prunes local `feature/<id>-<slug>` branches
  that are already merged into the configured base branch (`parallel.base_branch`,
  per BUG-2172). It must **never** delete an unmerged branch.
- A dry-run mode lists what would be deleted without deleting.
- The retention behavior (feature branches survive runs and are not auto-deleted)
  is documented at the toggle surfaces and in the workflow guide, so users
  understand why the branches accumulate and how to prune them.
- Branches with work not yet merged (no PR, or open PR) are left untouched.

## Proposed Solution

1. Add an opt-in prune surface — preferred as a subcommand/flag on the existing
   cleanup path, e.g. `ll-parallel --prune-merged-branches` or extend
   `/ll:cleanup-worktrees` with a `--branches` mode.
2. Determine merged-ness safely with `git branch --merged <base_branch>` filtered
   to the `feature/` prefix; optionally cross-check PR state via `gh pr view
   <branch> --json state` when `gh` is available (a merged PR is a stronger
   signal than local merge for squash/rebase merges, which `--merged` misses).
3. Always support `--dry-run` (list only) and require the merged check to pass
   before any deletion. Never delete the current branch or `base_branch`.
4. Document the lifecycle: feature branches are retained by design; this is how
   you reclaim them. Coordinate with ENH-2174 (toggle description) and ENH-2177
   (workflow guide).

## API/Interface

- New prune surface (exact spelling decided during impl): a `ll-parallel`
  flag or a `/ll:cleanup-worktrees` mode, plus `--dry-run`.

## Acceptance Criteria

1. The prune deletes local `feature/<id>-<slug>` branches that are merged into
   `parallel.base_branch` and leaves unmerged branches untouched.
2. A dry-run lists candidates without deleting.
3. Squash/rebase-merged branches are handled correctly — either via a `gh`
   PR-state cross-check or a documented limitation that `--merged` only catches
   fast-forward/merge-commit merges.
4. The current branch and the base branch are never deleted.
5. The retention + prune lifecycle is documented at a toggle surface and in the
   feature-branch workflow guide.
6. Tests cover: merged feature branch pruned; unmerged feature branch retained;
   `parallel/*` branches unaffected; dry-run deletes nothing.

## Scope Boundaries

- **In scope**: pruning *local* merged feature branches; documenting retention.
- **Out of scope**: deleting *remote* branches (GitHub's "delete branch on merge"
  setting owns that); changing the retention default (branches still survive the
  run); auto-pruning during a run (prune is a separate, explicit, opt-in action).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/parallel.py` **or** the `cleanup-worktrees` surface
  (`skills/cleanup-worktrees/` + its CLI/handler) — add the prune mode + `--dry-run`
- `scripts/little_loops/parallel/worker_pool.py` — reuse branch-prefix knowledge
  (`feature/`, ~line 245/631) for safe candidate selection
- `docs/guides/SPRINT_GUIDE.md` — document the feature-branch lifecycle (coordinate
  with ENH-2177)

### Similar Patterns
- `worker_pool.py:631` — the existing `startswith("parallel/")` branch-delete
  decision; mirror the prefix gate for `feature/`
- `/ll:cleanup-worktrees` — existing worktree-pruning flow to extend

### Dependencies
- **BUG-2172** — establishes `parallel.base_branch` in config (the merge target
  this prune checks against) and the push/PR flow that makes branches PR-backed.
- **ENH-2175** — `pr_url:`/`branch:` frontmatter could make PR-state cross-checks
  more precise (optional).

### Tests
- `scripts/tests/test_worker_pool.py` / cleanup tests — merged vs unmerged
  feature-branch handling, `parallel/*` untouched, dry-run is a no-op

### Documentation
- `docs/guides/SPRINT_GUIDE.md` — feature-branch lifecycle/cleanup section
- ENH-2174 toggle description — note that feature branches are retained and how to prune

## Impact

- **Priority**: P4 — housekeeping/polish; no functional gap in producing branches,
  but the missing cleanup half degrades the workflow over time.
- **Effort**: Small–Medium — a guarded prune + `gh` cross-check + tests + docs.
- **Risk**: Low–Medium — branch deletion is destructive; the merged-only gate and
  dry-run are the key safeguards.
- **Breaking Change**: No (opt-in; retention default unchanged).

## Status

**Open** | Created: 2026-06-15 | Priority: P4

## Session Log
- `/ll:capture-issue` - 2026-06-15 - added to EPIC-2171 (feature-branch lifecycle/cleanup gap identified during EPIC review)
