---
discovered_date: 2026-04-11
discovered_by: capture-issue
---

# BUG-1032: `refine-to-ready-issue`: no direct path from score-failure to breakdown

## Summary

In `refine-to-ready-issue.yaml`, when `check_scores` fails and the per-run retry budget is exhausted (`check_refine_limit` → `on_no: failed`), the sub-loop exits at `failed` with no route to `breakdown_issue`. The `breakdown_issue` state is only reachable from `check_lifetime_limit` (the lifetime cap path). Breakdown is silently delegated to the parent `recursive-refine` loop via its indirect `detect_children → size_review_snap → recheck_scores → run_size_review` chain — meaning the sub-loop never initiates decomposition when scores persistently fail.

## Current Behavior

`check_refine_limit` at `scripts/little_loops/loops/refine-to-ready-issue.yaml:143` routes:
- `on_yes: refine_issue` (retry when under budget)
- `on_no: failed` (exit sub-loop when budget exhausted)

`breakdown_issue` at `refine-to-ready-issue.yaml:191` is only reachable from `check_lifetime_limit:71` (`on_no: breakdown_issue`). There is no edge from `check_refine_limit` → `breakdown_issue`.

When `recursive-refine` invokes the sub-loop via `run_refine` (`recursive-refine.yaml:88`), it routes `on_failure: detect_children`. If no children were auto-created by the sub-loop, `detect_children` exits 1 → `size_review_snap` → `recheck_scores` → `run_size_review`. This indirect path works only when the parent is `recursive-refine`; running `refine-to-ready-issue` standalone never triggers breakdown regardless of scores.

## Expected Behavior

When the per-run retry budget is exhausted and scores still fail, `refine-to-ready-issue` should directly invoke `breakdown_issue` (i.e., route `check_refine_limit on_no: breakdown_issue` instead of `failed`). This makes the sub-loop self-contained and ensures breakdown happens regardless of which parent loop called it.

## Root Cause

`refine-to-ready-issue.yaml:159` — `check_refine_limit.on_no` is wired to `failed` instead of `breakdown_issue`.

## Steps to Reproduce

1. Run `ll-loop run refine-to-ready-issue "ISSUE_ID"` on an issue that scores below `outcome_threshold`
2. Allow two refine attempts to complete
3. Observe: sub-loop exits `failed`; no `breakdown_issue` is ever called; no child issues are created

## Impact

- **Priority**: P3 — Logic gap causes unexpected behavior; breakdown only works as a side-effect of the parent loop
- **Effort**: Trivial — single routing change
- **Risk**: Low — `breakdown_issue` already exists and is proven via the lifetime-cap path
- **Breaking Change**: No

## Proposed Solution

Change `check_refine_limit.on_no` from `failed` to `breakdown_issue` in `scripts/little_loops/loops/refine-to-ready-issue.yaml:159`.

## Implementation Steps

1. Edit `scripts/little_loops/loops/refine-to-ready-issue.yaml:159` — change `on_no: failed` to `on_no: breakdown_issue`
2. Update the comment block on `check_refine_limit` (lines 151–154) to reflect that budget exhaustion now triggers decomposition
3. Verify `recursive-refine`'s `run_refine` state still handles both paths:
   - `on_success`: sub-loop reached `done` (confidence pass or breakdown → done)
   - `on_failure`: sub-loop reached `failed` (error condition, not expected on budget exhaustion)
4. Run `scripts/tests/test_builtin_loops.py` to confirm no regressions

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:159` — `on_no: failed` → `on_no: breakdown_issue`

## Labels

`bug`, `loops`, `fsm`, `refine-to-ready-issue`, `recursive-refine`

## Status

**Open** | Created: 2026-04-11 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/05d0324c-611c-469d-8af1-b4e42644c47d.jsonl`
