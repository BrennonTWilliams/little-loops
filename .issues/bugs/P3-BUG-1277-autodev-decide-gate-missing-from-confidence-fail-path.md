---
id: BUG-1277
type: BUG
priority: P3
status: open
discovered_date: 2026-04-24
discovered_by: capture-issue
captured_at: "2026-04-24T21:18:45Z"
related: []
decision_needed: false
---

# BUG-1277: autodev `decide_current` Gate Missing from Confidence-Fail Path

## Summary

The `decide_current` / `run_decide` states in `autodev.yaml` are only reachable when `check_passed` succeeds (both confidence scores meet thresholds). When an unresolved decision causes low outcome confidence, the issue fails `check_passed` and routes to `run_size_review` (decomposition) instead of `run_decide`, producing incorrect breakdown behavior.

## Current Behavior

Flow when outcome confidence is below threshold:

```
check_passed (fail) → detect_children → size_review_snap
  → check_broke_down → recheck_scores (fail) → run_size_review → breakdown
```

`decide_current` is never consulted. An issue whose low outcome confidence is caused by an unresolved design decision gets decomposed instead of having its decision resolved.

Observed in: ENH-1115 ran autodev, confidence check noted "Persistence decision unresolved", `outcome_confidence: 53` < `outcome_threshold: 75` → loop broke down the issue rather than calling `/ll:decide-issue`.

## Expected Behavior

When `check_passed` fails (or `recheck_scores` fails) and `decision_needed: true` is set on the issue, the loop should route to `run_decide` before attempting `run_size_review`. A decision is more likely to resolve low outcome confidence than decomposition is.

Proposed gate: insert a `check_decision_before_size_review` state between `recheck_scores` (on_no) and `run_size_review` — if `decision_needed: true`, route to `run_decide`; else proceed to `run_size_review`.

## Root Cause

`decide_current` is only wired as a successor of three states, all on the scores-PASS path:
- `autodev.yaml:161` — `check_passed` on_yes
- `autodev.yaml:357` — `recheck_scores` on_yes
- `autodev.yaml:473` — `recheck_after_size_review` on_yes

There is no decision check on the `recheck_scores → run_size_review` edge (line 358), which is the path taken when outcome confidence is low.

## Acceptance Criteria

- When `decision_needed: true` and scores fail, autodev routes to `run_decide` instead of `run_size_review`
- When `decision_needed: false` (or absent), existing behavior is unchanged
- Test: add an autodev loop integration test covering this path
- Existing autodev tests continue to pass

## Scope Boundaries

- **In scope**: `autodev.yaml` state graph; adding decision gate on failure path
- **Out of scope**: `refine-to-ready-issue` sub-loop behavior; `decide_current` logic itself; other loops that don't have an equivalent decision gate

## Implementation Steps

1. Add a `check_decision_before_size_review` state to `autodev.yaml` between `recheck_scores` and `run_size_review` — shell action reads `ll-issues show --json` and exits 0 if `decision_needed == 'true'`, else exits 1
2. Wire `recheck_scores` on_no → `check_decision_before_size_review`
3. Wire `check_decision_before_size_review` on_yes → `run_decide`, on_no → `run_size_review`
4. Ensure `run_decide` next/on_error still flows to `implement_current` (or a score re-check after decision)

## Impact

- **Priority**: P3 — causes incorrect decomposition of decidable issues in autodev
- **Risk**: Low — additive state; existing issues with `decision_needed: false` follow unchanged path

## Labels

`bug`, `loops`, `autodev`, `fsm`, `decision-gate`

## Status

**Open** | Created: 2026-04-24 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-24T21:18:45Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82f88b14-6ac1-4d64-a028-6d67f78c0498.jsonl`
