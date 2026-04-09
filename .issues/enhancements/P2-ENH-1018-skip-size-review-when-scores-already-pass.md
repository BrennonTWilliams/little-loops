---
discovered_date: 2026-04-09
discovered_by: capture-issue
---

# ENH-1018: Skip size-review when scores already pass thresholds in recursive-refine

## Summary

In `recursive-refine.yaml`, when the `refine-to-ready-issue` sub-loop fails or errors, the flow goes to `detect_children` → `size_review_snap` → `run_size_review` without ever checking whether the issue's confidence/outcome scores already meet project thresholds. This causes `/ll:issue-size-review` to run unnecessarily on issues that are already ready (e.g., scoring 100 readiness, 91 outcome).

## Context

**Direct mode**: User description: "add a score check before size_review_snap so it bails out early when thresholds are already met"

Running `recursive-refine` on another project showed `/ll:issue-size-review` firing on an issue that scored 100 confidence and 91 outcome — well above the configured thresholds (90 readiness, 75 outcome by default). The sub-loop had failed for unrelated reasons, but the issue's scores were already passing.

## Motivation

The `size_review_snap` → `run_size_review` path is reached whenever the sub-loop fails/errors and no children were detected. But failure in the sub-loop doesn't mean the issue's scores are insufficient — it could fail for other reasons (max iterations, action errors). Running size-review on an already-ready issue wastes a full LLM cycle and can decompose issues that don't need it.

## Current Behavior

The flow from `run_refine` is:

```
run_refine
  on_success → check_passed → (if pass) dequeue_next
                           → (if fail) detect_children → (if children) enqueue_children
                                                       → (no children) size_review_snap → run_size_review
  on_failure → detect_children → (no children) size_review_snap → run_size_review  ← bypasses check_passed
  on_error   → detect_children → (no children) size_review_snap → run_size_review  ← bypasses check_passed
```

When the sub-loop fails/errors, `check_passed` is never reached, so scores are never evaluated before `size_review_snap`.

## Proposed Solution

Add a new state (e.g., `recheck_scores`) between `size_review_snap` and `run_size_review` (or as a gate before `size_review_snap`) that:

1. Reads the issue's current `confidence` and `outcome` scores via `ll-issues show --json`
2. Compares against the project's `readiness_threshold` and `outcome_threshold` (from `ll-config.json` with context defaults as fallback)
3. If both thresholds are met → record the issue as passed and go to `dequeue_next`
4. If not met → proceed to `run_size_review`

This reuses the same scoring logic already in `check_passed` (lines 104-136).

## Implementation Steps

1. Add a `recheck_scores` state in `recursive-refine.yaml` between `size_review_snap` and `run_size_review`
2. Port the score-check Python logic from `check_passed` into `recheck_scores`
3. Wire: `recheck_scores` on_yes → `dequeue_next`, on_no → `run_size_review`
4. Update `size_review_snap`'s `next` from `run_size_review` to `recheck_scores`

## API/Interface

No public API changes. Internal FSM state additions only.

## Files

- `scripts/little_loops/loops/recursive-refine.yaml` — add `recheck_scores` state, update transitions

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `captured`

---

## Status

**Open** | Created: 2026-04-09 | Priority: P2
