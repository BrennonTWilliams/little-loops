---
discovered_commit: 6eeea47c42aed769128f7b357e385f64ae05a863
discovered_branch: main
discovered_date: 2026-04-26
discovered_by: session-review
confidence_score: 100
outcome_confidence: 100
---

# BUG-1296: autodev `run_decide` bypasses score gate when reached from score-failing paths

## Summary

In `autodev.yaml`, `run_decide` has `next: implement_current` unconditionally. `run_decide` is reachable from both score-passing paths (`decide_current`) and score-failing paths (`triage_outcome_failure`, `check_decision_before_size_review`). On score-failing paths, `implement_current` runs even though the issue never met the readiness/outcome thresholds.

## Location

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `run_decide` state (`next: implement_current`, `on_error: implement_current`)
- **Introduced by**: fix `f7dd85a1` — that fix added the `triage_outcome_failure → run_decide` route without accounting for the unconditional `run_decide → implement_current` transition. The pre-existing `check_decision_before_size_review → run_decide` path had the same latent bug.

## Current Behavior

With readiness=85 and `readiness_threshold=90`:

1. `check_passed` → FAIL (85 < 90) → `triage_outcome_failure`
2. `triage_outcome_failure` detects `decision_needed=true` → `run_decide`
3. `run_decide` → `implement_current` — implementation runs despite the issue never passing the score gate

Identical path via `check_decision_before_size_review`:
- `recheck_scores` FAIL → `check_decision_before_size_review` [decision_needed=true] → `run_decide` → `implement_current`

## Expected Behavior

After `run_decide` resolves the decision, scores are re-validated before implementation. If scores still do not meet thresholds, the issue is dequeued rather than implemented.

## Root Cause

`run_decide` is a shared state reachable from both score-passing and score-failing contexts. Its unconditional `next: implement_current` is correct only for the score-passing case (`decide_current` path). Routes added to handle unresolved decisions mid-triage did not introduce a score re-check after decide.

| Reached from | Scores status | `next: implement_current` was correct? |
|---|---|---|
| `decide_current` | Passed `check_passed` ✓ | Yes |
| `triage_outcome_failure` | Failed `check_passed` ✗ | **No** |
| `check_decision_before_size_review` | Failed `recheck_scores` ✗ | **No** |

## Evidence

Debug trace `loop-viz-autodev-debug.txt` from a real run in another project:
- `confidence_check` wrote readiness=85, outcome=93 then was killed by `^C`
- On the next iteration, `check_passed` would evaluate 85 < 90 → fail → `triage_outcome_failure`
- With `decision_needed=true` set (introduced by `refine_issue`), `triage_outcome_failure` routes to `run_decide` → `implement_current`

## Proposed Solution

Add a `recheck_after_decide` state that mirrors `check_passed`. Change `run_decide.next` and `run_decide.on_error` to route through it:

```yaml
recheck_after_decide:
  fragment: shell_exit
  on_yes: implement_current   # scores pass after decide
  on_no: dequeue_next         # scores still fail — skip, don't re-trigger decide
  on_error: dequeue_next
```

## Implementation Steps

1. Add `recheck_after_decide` state to `autodev.yaml` after `run_decide` — mirrors `check_passed` score evaluation; `on_yes: implement_current`, `on_no: dequeue_next`, `on_error: dequeue_next`
2. Change `run_decide.next` from `implement_current` to `recheck_after_decide`
3. Change `run_decide.on_error` from `implement_current` to `recheck_after_decide`

## Impact

- **Priority**: P2 — Causes implementation of issues that have not met confidence thresholds; silent and hard to detect without log inspection
- **Effort**: Small — 1 new state + 2 transition changes in one YAML file
- **Risk**: Low — For the score-passing path (`decide_current`), `recheck_after_decide` simply re-confirms what was already true; behavior is unchanged

## Resolution

**Fixed** | Resolved: 2026-04-26

Added `recheck_after_decide` state to `scripts/little_loops/loops/autodev.yaml` (after `run_decide`). Changed `run_decide.next` and `run_decide.on_error` from `implement_current` to `recheck_after_decide`. The new state mirrors `check_passed` score evaluation and routes to `implement_current` on pass or `dequeue_next` on failure/error.

## Session Log

- session-review - 2026-04-26T22:00:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b59879f8-0f62-4897-ad7b-972b175ceecb.jsonl`

## Status

**Completed** | Created: 2026-04-26 | Priority: P2
