---
id: ENH-2643
title: Persist a merge-failure diagnostic artifact when `merge_epic_branch_to_base` aborts
type: ENH
status: open
priority: P3
discovered_date: '2026-07-15'
discovered_by: capture-issue
captured_at: '2026-07-15T02:26:46Z'
decision_needed: false
labels:
- epic-merge
- observability
- loops
---

# ENH-2643: Persist a merge-failure diagnostic artifact when `merge_epic_branch_to_base` aborts

## Summary

When the auto-refine/sprint loop's merge step fails, it records only
`epic_merge_verdict=merge_failed` — no durable detail of *why*. The verify step,
by contrast, writes `verify-detail.txt` (the failing command's output tail). A
merge failure is currently invisible in the run_dir: the operator must
re-reproduce `git merge` by hand to learn the cause.

## Motivation

Observed during `ll-loop run sprint-refine-and-implement --context sprint_name=EPIC-2370`
(2026-07-14): the run reported `merge_failed` with no artifact. The actual cause
— a content conflict in `.ll/decisions.yaml` (see BUG-2642) — was only found by
manually re-running `git merge --no-commit --no-ff`. A decisions-log id collision
silently blocked an EPIC merge-back with zero diagnostic in the run_dir.

## Current Behavior

`merge_epic_branch_to_base` (`scripts/little_loops/worktree_utils.py`) logs
`result.stderr` to the `Logger`, then `git merge --abort`s and returns False.
It persists nothing to the run_dir. The loop only writes `epic-merge-verdict.txt`
(`merge_failed`). There is no `merge-detail.txt` / conflicted-file list /
returncode artifact.

## Expected Behavior

On merge failure, write a diagnostic artifact under `${context.run_dir}/`
mirroring the verify gate's `verify-detail.txt`, e.g.:

- `merge-detail.txt` — the tail of `git merge` stderr/stdout.
- The list of conflicted paths (`git diff --name-only --diff-filter=U`) captured
  before `git merge --abort`.
- `merge-returncode.txt` — the failing returncode.

so `merge_failed` is self-diagnosing without re-running git.

## Implementation Sketch

- In `merge_epic_branch_to_base`, before `git merge --abort`, capture the
  conflicted-file list and combine with `result.stderr`/`stdout`. Reuse the
  `format_verify_detail` tail idiom (`worktree_utils.py`, ENH-2641) so the same
  bounded stdout+stderr-tail formatting applies.
- Thread a `run_dir: Path | None` (or a detail-callback) into the function so it
  can write the artifact; the loop's merge state passes `${context.run_dir}`.
- Loop `merge_epic_branch` state: write `merge-detail.txt` /
  `merge-returncode.txt` alongside `epic-merge-verdict.txt`.

## Scope Boundaries

**In scope**: capturing and persisting the merge-failure detail.
**Out of scope**: fixing the recurring decisions-log conflict itself (that is
BUG-2642); changing merge strategy or conflict-resolution behavior.

## Impact

- **Priority**: P3 — observability only; does not change merge outcomes, but
  turns a silent stall into a self-diagnosing one and saves manual re-reproduction.
- **Effort**: Small — mirror the existing verify-detail artifact plumbing.
- **Risk**: Low — additive diagnostic writes; no behavior change to the merge itself.

## Related

- BUG-2642 — the recurring decisions-log conflict this would have diagnosed.
- ENH-2641 / `format_verify_detail` — the verify-detail tail idiom to reuse.

## Status

**Open** | Created: 2026-07-15 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-07-15T02:26:46Z - session: sprint-refine-and-implement EPIC-2370 review
