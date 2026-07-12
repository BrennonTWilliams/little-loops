---
id: ENH-2615
type: enhancement
priority: P3
status: open
captured_at: '2026-07-12T17:56:40Z'
discovered_date: 2026-07-12
discovered_by: capture-issue
relates_to: [BUG-2614, ENH-2601, EPIC-2575]
---

# ENH-2615: Mid-run decomposed children bypass the epic-branch worktree

## Summary

`auto-refine-and-implement.yaml` resolves an EPIC's child issue set once, in
`resolve_set` (lines 90-139), and captures it as `issue_set` for the rest of
the run. If `/ll:refine-issue` (or the loop's own refine sub-pass) decomposes
one of those children into a new follow-up issue mid-run, the new issue has
no mechanism attaching it to the epic-branch worktree that `delegate`
(lines 224-247) set up for the original `issue_set` — its work lands wherever
the ambient checkout/working tree happens to be (typically `base_branch`)
instead of on `epic/<EPIC-ID>-<slug>`.

Confirmed on `EPIC-2575`: ENH-2612 ("code_query config block") was
decomposed from ENH-2577 (a declared EPIC-2575 child) during a run, but its
implementation commit (`4c4dcc79`) landed directly on `main`, not on the
epic branch — even though ENH-2577 was actively part of the resolved
`issue_set` on that run.

## Current Behavior

A child decomposed mid-run has `parent:` set to the original child (e.g.
`parent: ENH-2577`) but is otherwise treated as an untracked, unscoped issue
by the epic-branch machinery — its `relates_to`/scope membership isn't
re-derived from its `parent` chain, so `delegate`/worktree routing has no
way to know it belongs to the in-progress epic run.

## Expected Behavior

When a child of an in-progress epic-scoped run is decomposed into a new
issue, that new issue's own implementation work should also land on the
epic branch — either by re-resolving `issue_set` to include newly-discovered
descendants before each `delegate` iteration, or by having decomposition
itself detect an active epic-branch context and route the new issue's work
into the same worktree.

## Motivation

This is the same class of gap as [[BUG-2614]] (epic-branch work not making
it back to base) but on the other end: pre-declared children get *into* the
branch correctly; children created by decomposition after the run starts do
not. Because decomposition is a normal, expected part of `/ll:refine-issue`
(splitting an underspecified issue into a scoped-down original plus
follow-ups), this isn't a rare edge case — it's likely to recur on every
epic run where a child needs decomposition, silently fragmenting the
"everything for this epic lands on one branch" guarantee the feature exists
to provide.

## Proposed Solution

1. In `auto-refine-and-implement.yaml`, re-check for new children with
   `parent:` pointing into the resolved `issue_set` (transitively) before
   each `delegate` dispatch, and fold them into the active worktree/branch
   scope rather than only resolving once in `resolve_set`.
2. Alternatively (simpler, less invasive): have the decomposition step
   itself check whether the issue being decomposed is currently being
   worked inside an epic-branch worktree (e.g. via `context.run_dir` /
   captured epic branch name) and, if so, ensure the new issue's file and
   subsequent implementation commits are made against that same worktree.
3. Add regression coverage: an epic-scoped FSM run where one child is
   decomposed mid-run should result in the decomposed follow-up's commits
   also landing on the epic branch, not `base_branch`.

## Impact

- **Priority**: P3 — real but narrower than BUG-2614; only affects runs
  where mid-run decomposition happens, and the symptom (work on `main`
  instead of the epic branch) is recoverable by hand.
- **Effort**: Medium — depends on how `resolve_set`/`delegate` currently
  track scope membership; may share plumbing with whatever fixes BUG-2614.
- **Risk**: Low — additive scope-tracking, no change to existing
  single-pass runs where no decomposition occurs.

## Session Log
- `/ll:capture-issue` - 2026-07-12T17:56:40Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/655a2464-a4d4-4557-b538-8038528dc56f.jsonl`

---

## Status

- [ ] Not started
