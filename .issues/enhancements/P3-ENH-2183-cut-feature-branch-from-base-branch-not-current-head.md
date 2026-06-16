---
id: ENH-2183
title: Cut feature branch from parallel.base_branch, not the current HEAD
type: ENH
status: done
priority: P3
parent: EPIC-2171
captured_at: '2026-06-15T00:00:00Z'
completed_at: '2026-06-16T17:06:08Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels:
- parallel
- feature-branches
- worktrees
- base-branch
- correctness
blocked_by:
- BUG-2172
relates_to:
- ENH-2181
confidence_score: 100
outcome_confidence: 84
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 22
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

## Motivation

`base_branch` is referenced by three consumers — fork point, PR target (BUG-2172),
and prune merge-check (ENH-2181) — but only the latter two actually honor it.
Users who launch `ll-parallel` from a release branch, hotfix branch, or stacked
branch (all common workflows) silently get a worktree forked from the wrong
commit. The fallout is PR diffs polluted with upstream commits and prune decisions
that misidentify merged branches. This enhancement closes the last gap so
`base_branch` governs all three consumers consistently, completing the contract
established by BUG-2172 and ENH-2181.

## Current Behavior

- `parallel/worker_pool.py:248` — computes `feature/<id>-<slug>`.
- `parallel/worker_pool.py:268` — calls `self._setup_worktree(worktree_path, branch_name)` (no `base_branch` arg).
- `parallel/worker_pool.py:538` — `_setup_worktree()` definition; calls `setup_worktree()` at line 547 with no `base_branch` argument.
- `worktree_utils.py:49-53` — `git_lock.run(["worktree", "add", "-b", branch_name, str(worktree_path)])` (no commit-ish) → new branch forks from HEAD of `repo_path`.
- `parallel/types.py:378` — `base_branch: str = "main"` is the config default; serialized in `to_dict()` at line 458, deserialized in `from_dict()` at line 503.
- **CLI auto-detection nuance**: `cli/parallel.py:198-205` and `cli/sprint/run.py:504-511` both run `git rev-parse --abbrev-ref HEAD` at startup and set `base_branch` to whichever branch is currently checked out. This means right now, `base_branch` IS the current HEAD — so `worktree add` without a commit-ish forks from the same place `base_branch` points. The mismatch becomes real when BUG-2172 makes `base_branch` configurable from JSON (so a user can declare `base_branch: "main"` in config while sitting on `release`); after that fix, branch creation remains the one consumer that doesn't honor it.
- Net: all three uses of `base_branch` only agree when the user happens to have `base_branch` checked out at launch. Otherwise the fork point silently differs from the declared base.

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

## Implementation Steps

1. Add `base_branch: str | None = None` parameter to `setup_worktree()` signature in `worktree_utils.py:21`
2. Before worktree creation, validate when `base_branch` is not `None`: use `git_lock.run(["rev-parse", "--verify", base_branch], cwd=repo_path, timeout=10)` (follows GitLock.run convention — no leading `"git"`, returns CompletedProcess); on `returncode != 0`, raise `RuntimeError(f"Branch '{base_branch}' does not resolve: {result.stderr}")` (matches existing error format in `worktree_utils.py:55` and `merge_coordinator.py`)
3. Append `base_branch` to the `git worktree add` args when provided: `["worktree", "add", "-b", branch_name, str(worktree_path), base_branch]`; when `None`, emit the current four-arg form unchanged
4. Update `_setup_worktree()` at `worker_pool.py:538`: add `base_branch: str | None = None` to its signature and forward it to `setup_worktree(..., base_branch=base_branch)`
5. At the call site `worker_pool.py:268` in `_process_issue()`: pass `base_branch=self.parallel_config.base_branch` when `self.parallel_config.use_feature_branches` is true; pass `None` (or omit) for `parallel/*` worktrees
6. Add tests following patterns in `test_subprocess_mocks.py:TestWorktreeManagement` (patches `subprocess.run` and captures commands) and `test_worker_pool.py:TestWorkerPoolWorktreeManagement` (patches `worker_pool._git_lock.run`): fork-point from `base_branch` when HEAD ≠ base; unresolvable-base raises RuntimeError; `parallel/*` path passes `None` and is unaffected

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
- `scripts/little_loops/worktree_utils.py` — `setup_worktree()` (signature line 21, `git worktree add` call lines 49–53): add optional `base_branch: str | None = None` parameter; add `rev-parse --verify` validation before line 49; append commit-ish to the git args when provided
- `scripts/little_loops/parallel/worker_pool.py` — two touch points:
  - `_setup_worktree()` (definition line 538, `setup_worktree()` call line 547): add `base_branch: str | None = None` to signature and forward to `setup_worktree()`
  - `_process_issue()` (call site line 268): pass `base_branch=self.parallel_config.base_branch` in feature-branch mode, `None` otherwise

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — secondary caller of `setup_worktree()` (for loop worktrees); does not pass `base_branch` and is unaffected by the `None` default
- `scripts/little_loops/parallel/orchestrator.py` — reads `self.parallel_config.base_branch` (lines 399, 1085) for rev-list and PR `--base`; unaffected by this change but benefits from the fork-point fix
- `scripts/little_loops/parallel/merge_coordinator.py` — reads `self.config.base_branch` (lines 624, 875) for checkout/rebase; same as above

### Dependencies
- **BUG-2172** — promotes `base_branch` to `config-schema.json` and makes it independently configurable from the current HEAD. This ENH makes branch creation honor that config value. Sequence after (or alongside) BUG-2172; the fix is invisible until BUG-2172 decouples `base_branch` from the CLI's `rev-parse --abbrev-ref HEAD` auto-detection.
- **ENH-2181** — its prune merge-check becomes correct only once the fork point matches `base_branch`.

### Similar Patterns
- `scripts/little_loops/parallel/git_lock.py` — `GitLock.run()`: the lock wrapper used for all git calls in `setup_worktree()`; args omit the leading `"git"` (the lock prepends it); returns `CompletedProcess`; caller checks `.returncode`. Use this for the `rev-parse --verify` validation.
- `scripts/little_loops/worktree_utils.py:54-55` — existing `RuntimeError` pattern: `raise RuntimeError(f"Failed to create worktree: {result.stderr}")`. Mirror for the unresolvable-base error: `raise RuntimeError(f"Branch '{base_branch}' does not resolve: {result.stderr}")`.
- `scripts/little_loops/parallel/types.py:458/503` — `base_branch` serialization round-trip in `to_dict()`/`from_dict()`; no changes needed here but confirms the field is stable.

### Tests
- `scripts/tests/test_subprocess_mocks.py` — `TestWorktreeManagement.test_setup_worktree_creates_branch` (around line 559): patches `subprocess.run` and captures command args; extend to assert commit-ish present in `worktree add` args when `base_branch` is set
- `scripts/tests/test_worker_pool.py` — `TestWorkerPoolWorktreeManagement` (around line 597): patches `worker_pool._git_lock.run` via `patch.object`; add cases for fork-point threading and unresolvable-base error

### Documentation
- N/A

### Configuration
- N/A — `base_branch` schema is owned by BUG-2172; this ENH adds no new config keys.

## Impact

- **Priority**: P3 — correctness: without it, `base_branch` is honored
  inconsistently and the PR/prune halves of the workflow can be wrong whenever
  the user isn't sitting on the base branch.
- **Effort**: Small — one optional parameter + a validation check + tests.
- **Risk**: Low — additive; `None` default preserves current behavior.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Resolution

Implemented `base_branch` as an optional commit-ish parameter threaded through `setup_worktree()` and `_setup_worktree()`. In feature-branch mode, `_process_issue()` now passes `self.parallel_config.base_branch`; the `parallel/*` path passes `None`, preserving existing behavior. Added `rev-parse --verify` validation before worktree creation to fail fast on unresolvable bases.

## Session Log
- `/ll:manage-issue` - 2026-06-16T17:06:08Z - implementation
- `/ll:ready-issue` - 2026-06-16T17:01:34 - `b8ab6481-33a0-41c6-8ce4-68f4c099a943.jsonl`
- `/ll:confidence-check` - 2026-06-16T17:30:00Z - `ba03ef2c-f3e9-4b3d-bad3-545f9435e93b.jsonl`
- `/ll:refine-issue` - 2026-06-16T16:53:50 - `5bc9b09b-e1ee-42a7-b42e-915950c44a27.jsonl`
- `/ll:confidence-check` - 2026-06-16T00:00:00Z - `61a1f3f6-4acc-425c-ab1a-103513caa7f2.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-15T20:51:38 - `fc9e22f8-f75a-4ab7-a570-0b05a961077c.jsonl`
- `/ll:format-issue` - 2026-06-15T20:18:15 - `243f0ddc-3093-4f69-bc1f-a6a8bcf7d3fd.jsonl`
- `/ll:capture-issue` - 2026-06-15 - added to EPIC-2171 (base_branch fork-point inconsistency identified during EPIC review)
