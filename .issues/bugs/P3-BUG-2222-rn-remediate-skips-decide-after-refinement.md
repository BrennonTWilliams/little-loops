---
id: BUG-2222
status: done
priority: P3
type: BUG
captured_at: '2026-06-18T20:17:08Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
labels:
- loop
- routing
- bug
---

# P3-BUG-2222: rn-remediate subloop skips /ll:decide-issue after refinement sets decision_needed

## Summary

The `rn-remediate` subloop's `mark_refined` state hardcodes `next: re_assess`, so when `/ll:refine-issue` deposits `decision_needed: true` (by adding multiple solution options), the loop runs a redundant `/ll:confidence-check` instead of routing to `/ll:decide-issue`. The `check_convergence` state does eventually detect the flag but routes to `MANUAL_REVIEW_NEEDED` (block for human) rather than `decide` (handle automatically). The same gap exists on the `mark_wired` path.

## Current Behavior

When `/ll:refine-issue --full-rewrite` adds `decision_needed: true` to an issue (e.g., because it deposited 4 solution options A/B/C/D that need a decision), the subloop follows this chain:

```
refine → mark_refined ──next: re_assess──→ /ll:confidence-check → check_convergence → NEEDS_MANUAL_REVIEW
```

This:
1. Wastes a `/ll:confidence-check` call that adds latency and token cost
2. Blocks the issue for human review instead of running `/ll:decide-issue` automatically
3. The `check_decision_needed` gate at `rn-remediate.yaml:193-198` already ran before refinement (when the flag didn't exist yet), so there's no post-refinement path to `decide`

The `mark_wired` state has the same hardcoded `next: re_assess` and is subject to the same gap.

## Expected Behavior

After `refine` (or `wire`) completes and `mark_refined` (or `mark_wired`) records the pass, the subloop should check `decision_needed` before proceeding:

```
refine → mark_refined → check_decision_needed_post → if yes → decide → re_assess
                                                   → if no  → re_assess
```

The `check_convergence → NEEDS_MANUAL_REVIEW` path should only fire when `decide` has already run but `decision_needed` persists (true impassable decision), not as the first encounter of the flag.

## Motivation

This routing gap causes every issue that receives multiple solution options during refinement to be blocked for manual review, breaking the automation chain. The remediate subloop is designed to handle `/ll:decide-issue` autonomously (the `decide` state exists at `rn-remediate.yaml:331-348`), but is never routed to it after refinement. Users must manually unblock these issues, defeating the purpose of the automation loop.

## Steps to Reproduce

1. Run `rn-implement` against an issue that has moderate readiness/outcome scores (below gates)
2. Let the remediate subloop run `/ll:refine-issue` which adds multiple solution options → sets `decision_needed: true`
3. Observe the subloop routes to `re_assess` (another confidence check) instead of `decide`
4. Observe `check_convergence` outputs `NEEDS_MANUAL_REVIEW` — issue is blocked for human

## Root Cause

- **File**: `scripts/little_loops/loops/rn-remediate.yaml`
- **Anchor**: states `mark_refined` (line 375) and `mark_wired` (line 383)
- **Cause**: Both states hardcode `next: re_assess` with no intermediate `decision_needed` gate. The `check_decision_needed` state at line 193 only runs once, before refinement, when the flag hasn't been set yet. The `check_convergence` state at line 493-501 does detect `decision_needed` but routes to `NEEDS_MANUAL_REVIEW` (human intervention) rather than `decide` (automated resolution).

## Proposed Solution

Replace the hardcoded `next: re_assess` on `mark_refined` and `mark_wired` with an intermediate `check_decision_needed_post` state that routes to `decide` if the flag is set:

1. Add a new state `check_decision_needed_post` (identical logic to `check_decision_needed` at line 193)
2. Change `mark_refined.next` from `re_assess` to `check_decision_needed_post`
3. Change `mark_wired.next` from `re_assess` to `check_decision_needed_post`
4. `check_decision_needed_post.on_yes → decide`, `on_no → re_assess`
5. Optionally update `check_convergence`'s `NEEDS_MANUAL_REVIEW` path to route to `decide` instead when remediation budget remains

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` — add post-refinement gate and reroute mark_refined/mark_wired

### Dependent Files
- `scripts/little_loops/loops/rn-implement.yaml` — parent loop may need no changes if the subloop outcome token stays compatible
- `scripts/little_loops/loops/recursive-refine.yaml` — has its own `check_decision_needed` state (line 538) that may have the same gap
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — has its own `check_decision_needed` (line 201), check for same pattern

### Tests
- `scripts/tests/test_builtin_loops.py` — likely location for loop routing tests

### Documentation
- Loop architecture docs if they describe the remediate flow

## Implementation Steps

1. Add `check_decision_needed_post` state in `rn-remediate.yaml` (copy `check_decision_needed` routing at line 193)
2. Change `mark_refined.next` from `re_assess` to `check_decision_needed_post`
3. Change `mark_wired.next` from `re_assess` to `check_decision_needed_post`
4. Run `ll-loop validate rn-remediate` to confirm no YAML errors
5. Verify with a test run of `rn-implement` against a decision-needed issue

## Impact

- **Priority**: P3 — Automation efficiency gap, not a crash or data loss; user-facing only when running `rn-implement`
- **Effort**: Small — 1 new state + 2 routing changes in 1 file
- **Risk**: Low — new state reuses existing `check_decision_needed` logic; `decide` state already exists and is tested
- **Breaking Change**: No — subloop outcome tokens unchanged; parent routing unaffected

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`loop`, `routing`, `bug`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-06-18T20:17:08Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ae0d3d67-5037-4ded-ba55-237674f0b14b.jsonl`

## Status

**Open** | Created: 2026-06-18 | Priority: P3
