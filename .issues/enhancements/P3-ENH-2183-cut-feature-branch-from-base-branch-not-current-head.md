---
id: ENH-2183
title: Cut feature branch from parallel.base_branch, not the current HEAD
type: ENH
status: open
priority: P3
parent: EPIC-2171
captured_at: '2026-06-15T00:00:00Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels: [parallel, feature-branches, worktrees, base-branch, correctness]
relates_to: [BUG-2172, ENH-2181]
---

# ENH-2183: Cut feature branch from parallel.base_branch, not the current HEAD

## Summary

The feature branch is created with `git worktree add -b <branch> <path>` and
**no commit-ish**, so it forks from whatever the main repo currently has checked
out — not from `parallel.base_branch`. Meanwhile BUG-2172 makes `base_branch` the
PR target and ENH-2181 makes it the prune merge-check. So `base_branch` governs
two downstream consumers while the branch's actual fork point is unmanaged. If
the user isn't sitting on `base_branch` when they launch (e.g. on a release or
stacked branch), the PR base and the true merge-base disagree — producing noisy
PR diffs and incorrect prune results.

## Current Behavior

- `parallel/worker_pool.py:248` — computes `feature/<id>-<slug>`.
- `worktree_utils.py:49-50` — `git worktree add -b <branch> <path>` (no
  commit-ish) → the new branch forks from the current HEAD of `repo_path`.
- `parallel/types.py:376` — `base_branch` defaults to `"main"` and is consumed
  by the PR target (BUG-2172) and merged-check (ENH-2181), but **not** by branch
  creation.
- Net: all three uses of `base_branch` only agree when the user happens to have
  `base_branch` checked out at launch. Otherwise the fork point silently differs
  from the declared base.

## Steps to Reproduce

1. Set `parallel.use_feature_branches: true` and `parallel.base_branch: main`.
2. `git checkout some-release-branch` in the main repo.
3. Run `ll-parallel` against an issue.
4. Inspect the feature branch: it forks from `some-release-branch`, not `main`.
   A PR opened against `main` (BUG-2172) shows every commit unique to the release
   branch, and ENH-2181's `git branch --merged main` check misjudges merged-ness.

## Expected Behavior

- The feature branch is cut from `parallel.base_branch` regardless of what the
  main repo currently has checked out, so the fork point, the PR target, and the
  prune merge-check all reference the same base.
- If `base_branch` does not exist locally, the run fails fast (or fetches it)
  with a clear message rather than silently forking from HEAD.

## Proposed Solution

1. Thread `base_branch` into `setup_worktree()` as an optional `base_branch`
   parameter (commit-ish for the new branch).
2. Emit `git worktree add -b <branch> <path> <base_branch>` when provided;
   preserve current behavior (fork from HEAD) when `None` so non-feature-branch
   `parallel/*` worktrees are unaffected unless we choose to honor it there too.
3. Validate `base_branch` resolves (`git rev-parse --verify <base_branch>`)
   before worktree creation; on failure, fail the run with a clear message (or
   fetch `origin/<base_branch>` first — decide during impl, coordinate with
   BUG-2172's push/remote handling).
4. Pass `self.parallel_config.base_branch` from `worker_pool` in feature-branch
   mode.

## API/Interface

- `setup_worktree(..., base_branch: str | None = None)` — new optional commit-ish;
  `None` preserves the current fork-from-HEAD behavior.

## Acceptance Criteria

1. In feature-branch mode, the branch is cut from `parallel.base_branch`
   irrespective of the main repo's currently checked-out branch.
2. The PR target (BUG-2172) and the prune merge-check (ENH-2181) reference the
   same base the branch was cut from.
3. A missing/unresolvable `base_branch` fails fast with a clear message (or is
   fetched first) — it does not silently fork from HEAD.
4. Non-feature-branch `parallel/*` worktrees are unchanged unless explicitly
   opted in.
5. Tests cover: branch forked from `base_branch` when HEAD is on a different
   branch; unresolvable `base_branch` errors clearly; `parallel/*` path
   unaffected.

## Scope Boundaries

- **In scope**: where the feature branch's fork point comes from, and validating
  it resolves.
- **Out of scope**: adding `base_branch` to the schema (owned by BUG-2172);
  the `--base-branch` CLI override (a natural ENH-2173 addition); remote fetch
  policy beyond the minimal validation above.

## Integration Map

### Files to Modify
- `scripts/little_loops/worktree_utils.py` — `setup_worktree()` (~line 21/49):
  add optional `base_branch` commit-ish to `git worktree add`
- `scripts/little_loops/parallel/worker_pool.py` — `_setup_worktree()` call
  (~line 547): pass `self.parallel_config.base_branch` in feature-branch mode

### Dependencies
- **BUG-2172** — promotes `base_branch` to `config-schema.json`; this issue makes
  branch creation honor it. Sequence after (or alongside) BUG-2172.
- **ENH-2181** — its prune merge-check becomes correct only once the fork point
  matches `base_branch`.

### Similar Patterns
- `parallel/types.py:454/497` — existing `base_branch` serialization round-trip
  to mirror if any new plumbing is needed.

### Tests
- `scripts/tests/test_worktree_utils.py` / `test_worker_pool.py` — fork-point
  assertions under a non-base HEAD; unresolvable-base error path.

## Impact

- **Priority**: P3 — correctness: without it, `base_branch` is honored
  inconsistently and the PR/prune halves of the workflow can be wrong whenever
  the user isn't sitting on the base branch.
- **Effort**: Small — one optional parameter + a validation check + tests.
- **Risk**: Low — additive; `None` default preserves current behavior.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-06-15 - added to EPIC-2171 (base_branch fork-point inconsistency identified during EPIC review)
