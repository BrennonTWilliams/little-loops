---
id: BUG-1975
title: 'rn-decompose: run_size_review has no on_partial route, so a partial LLM verdict
  terminates the sub-loop with error'
type: BUG
priority: P3
status: done
captured_at: '2026-06-06T00:00:00Z'
completed_at: '2026-06-06T04:42:09Z'
discovered_date: '2026-06-06'
discovered_by: audit-loop-run
relates_to:
- BUG-567
- BUG-1974
- ENH-1977
labels:
- rn-implement
- rn-decompose
- loop-defect
- routing
confidence_score: 100
outcome_confidence: 90
score_complexity: 25
score_test_coverage: 15
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1975: rn-decompose run_size_review missing on_partial route

> **Coordination (2026-06-06):** Folded into **ENH-1977** as a prerequisite sub-task. ENH-1977's Fix 1
> requires `run_size_review` to emit a `SIZE_REVIEW_FAILED` token on its partial/error paths, but a
> `partial` verdict currently falls through to `_finish("error")` *before any token-write state runs* —
> so Fix 1 is not implementable without this bug's `on_partial` route. ENH-1977 adopts this issue's
> routing decision (`on_partial → detect_children`, "proceed with caveat"), **not** a blanket
> `SIZE_REVIEW_FAILED`: the observed `partial` was a hygiene caveat (staged unrelated changes, BUG-1976),
> not a review failure. Implement as part of ENH-1977 rather than standalone to avoid double-editing
> `run_size_review`.

## Summary

In `rn-decompose`, the `run_size_review` state runs `/ll:issue-size-review` as a `slash_command`
action whose verdict is graded by the default LLM judge. That judge can return `partial` (as it did
for FEAT-1713 during run `2026-06-06T015949`, correctly flagging that the size review had staged
unrelated working-tree changes). The state declares `on_success`, `on_error`, and
`on_rate_limit_exhausted` but **no `on_partial`** — so a `partial` verdict has no routing target and
the sub-loop terminates with `terminated_by: error`.

`on_partial` is a first-class transition at runtime (BUG-567, done), but `rn-decompose` never uses
it. The parent recovers via `run_decomposition.on_error → skip_issue`, so there is no user-visible
crash, but the evaluator's useful finding (here: a staged-changes problem, see BUG-1976) is silently
discarded and the issue is skipped instead of decomposed.

## Current Behavior

`loops/rn-decompose.yaml`, `run_size_review` state:

```yaml
  run_size_review:
    fragment: with_rate_limit_handling
    action: "/ll:issue-size-review ${context.issue_id} --auto"
    action_type: slash_command
    on_success: detect_children
    on_error: failed
    on_rate_limit_exhausted: rate_limit_diagnostic
```

When the default LLM evaluator returns `partial`, `_route()` finds no matching transition and the
loop finishes via `_finish("error")` → `terminated_by: error`.

## Expected Behavior

A `partial` verdict from `run_size_review` should route deterministically — most reasonably to
`detect_children` (treat partial as "review completed, proceed") so the loop still makes progress and
the evaluator's caveat is logged rather than discarded. At minimum, `partial` must not error-terminate
the sub-loop.

## Steps to Reproduce

From run `2026-06-06T015949` (rn-implement processing FEAT-1713):

```
state: run_size_review
action: /ll:issue-size-review FEAT-1713 --auto
evaluator: default LLM judge
verdict: partial (confidence 0.82)  # caught staged unrelated working-tree changes
route: no on_partial target → _finish("error")
loop_complete: { terminated_by: "error" }
parent: run_decomposition.on_error → skip_issue
```

FEAT-1713 was skipped rather than decomposed, and the evaluator's staged-changes finding was lost.

## Root Cause

- **File**: `loops/rn-decompose.yaml`
- **Anchor**: in state `run_size_review`
- **Cause**: The state omits an `on_partial` transition. The default LLM judge on a `slash_command`
  action can emit `partial`, but with no routing target the executor falls through to
  `_finish("error")`. Runtime support for `on_partial` exists (BUG-567); the loop definition simply
  does not exercise it.

## Proposed Solution

Add an `on_partial` route to `run_size_review`:

```yaml
  run_size_review:
    fragment: with_rate_limit_handling
    action: "/ll:issue-size-review ${context.issue_id} --auto"
    action_type: slash_command
    on_success: detect_children
+   on_partial: detect_children   # partial = review ran with a caveat; proceed and log it
    on_error: failed
    on_rate_limit_exhausted: rate_limit_diagnostic
```

Note MR-4 (`ll-loop validate`): an LLM-judged state with `on_yes` but no `on_partial`/`on_no` is
flagged as a silent dead-end. Adding `on_partial` here aligns the state with that rule.

## Implementation Steps

1. Add `on_partial: detect_children` to `run_size_review` in `loops/rn-decompose.yaml`.
2. Audit sibling LLM-judged slash_command states in `rn-decompose`, `rn-remediate`, and
   `rn-implement` for the same missing-`on_partial` gap.
3. Run `ll-loop validate loops/rn-decompose.yaml` and confirm MR-4 passes.
4. Re-run a decomposition iteration that produces a `partial` verdict and confirm the loop routes to
   `detect_children` instead of `terminated_by: error`.

## Impact

- **Priority**: P3 — recoverable via parent's `on_error → skip_issue`, but loses evaluator findings
  and skips issues that should be decomposed.
- **Effort**: Small — single-line YAML addition.
- **Risk**: Low — adds a route for a verdict that currently errors; no existing path changes.
- **Breaking Change**: No
- **Severity**: MEDIUM — rare (1/5 sub-loop runs observed) but discards evaluator intelligence and
  changes the issue's outcome (skip vs decompose).
- **Blast radius**: Any `rn-decompose` run where the size-review LLM judge returns `partial`.

## Status

**Open** | Created: 2026-06-06 | Priority: P3

## Resolution

**Fixed**: Added `on_partial: detect_children` and `on_no: failed` to `run_size_review` in `loops/rn-decompose.yaml`.

- `on_partial → detect_children`: partial verdict (e.g. hygiene caveat from staged changes) now proceeds to child detection rather than error-terminating the sub-loop.
- `on_no → failed`: inconclusive judge verdict terminates with error explicitly instead of dead-ending.
- Removed `partial_route_ok: true` top-level suppressor — no longer needed since all LLM-judged states in rn-decompose now have full routing tables.
- MR-4 (`ll-loop validate`) now passes cleanly with no warnings.

**Sibling audit**: rn-remediate (5 slash_command states) and rn-implement have `partial_route_ok: true` suppressing the same gap — tracked separately.

**Test**: Added `test_run_size_review_routes_partial_to_detect_children` in `test_rn_decompose.py`; updated routing-key tuples in structural tests to include `on_partial`.

## Session Log
- `/ll:ready-issue` - 2026-06-06T04:38:44 - `cd60e399-996e-41ba-b8f7-cdae1ec0ace5.jsonl`
- `/ll:capture-issue` - 2026-06-06 - from rn-implement-audit-2026-06-06.md (run 2026-06-06T015949, F3)
- `/ll:confidence-check` - 2026-06-05 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1adb4edf-fbef-44fc-a122-565b3721e970.jsonl`
