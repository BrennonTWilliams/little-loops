---
discovered_date: 2026-04-11
discovered_by: capture-issue
---

# ENH-1033: `refine-to-ready-issue`: skip retry refine when only outcome confidence fails

## Summary

When `check_scores` fails in `refine-to-ready-issue`, the FSM unconditionally retries `/ll:refine-issue` regardless of which metric failed. `/ll:refine-issue` improves technical readiness (codebase research, implementation wiring). When only outcome confidence is below threshold — a measure of business value certainty — the retry is unlikely to close the gap and wastes roughly 11 minutes per attempt.

## Current Behavior

`check_scores` at `scripts/little_loops/loops/refine-to-ready-issue.yaml:110` evaluates both `confidence` (readiness) and `outcome` in a single boolean. Any failure routes to `check_refine_limit → refine_issue`. There is no distinction between:
- Readiness failed (technical gaps — `/ll:refine-issue` can fix this)
- Outcome confidence failed (business value uncertainty — `/ll:refine-issue` cannot reliably fix this)

Observed in practice: FEAT-095 scored 93/100 readiness (above threshold) but 64/100 outcome (below 75 threshold). The FSM retried `/ll:refine-issue`, which ran for ~11 minutes and is unlikely to raise outcome confidence by 11 points since the uncertainty is inherent to the feature's business case, not missing technical detail.

## Expected Behavior

When readiness passes but only outcome confidence fails, the FSM should route directly to `breakdown_issue` (or `failed` with a diagnostic) rather than retrying refinement. Optionally, it could invoke a different skill targeted at outcome uncertainty (e.g., prompting for use-case clarification or scope reduction).

## Motivation

Outcome confidence measures whether the feature's benefit is well-understood and realistically achievable. Low outcome confidence signals a problem with the feature's definition, not the implementation plan. Re-researching the codebase won't resolve "we're not sure this feature will have the expected impact." The retry wastes time and token budget without addressing the actual gap.

## Proposed Solution

Split `check_scores` into two sequential checks:
1. **`check_readiness`** — if readiness < threshold, route to retry path (refine is appropriate)
2. **`check_outcome`** — if outcome < threshold (after readiness passes), route directly to `breakdown_issue` (scope reduction is the right intervention, not more refinement)

Alternatively, add a separate `check_scores_by_metric` state that exits with distinct codes for "readiness failed", "outcome failed", or "both failed", and route accordingly.

## Implementation Steps

1. In `scripts/little_loops/loops/refine-to-ready-issue.yaml:110–135` — split `check_scores` into two states:
   - `check_readiness`: evaluates `confidence >= readiness_threshold`; on_yes → `check_outcome`; on_no → `check_refine_limit`
   - `check_outcome`: evaluates `outcome >= outcome_threshold`; on_yes → `done`; on_no → `breakdown_issue`
2. Update `check_scores_from_file` (line 162) similarly if it remains as an error fallback
3. Update `recursive-refine.yaml` references — `run_refine.on_success: check_passed` still applies; verify `check_passed` logic is unaffected
4. Add test case to `scripts/tests/test_builtin_loops.py` covering the outcome-only-fails path
5. Update loop description/comments in `refine-to-ready-issue.yaml:1–10`

## Scope Boundaries

- **In scope**: Routing logic change in `refine-to-ready-issue.yaml`; corresponding test coverage
- **Out of scope**: Changing the thresholds themselves; adding new skills to address outcome uncertainty

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:110–159` — split `check_scores` into `check_readiness` + `check_outcome`

## Impact

- **Priority**: P3 — Saves ~11 min per issue with inherently low outcome confidence
- **Effort**: Low — routing change + 1-2 new states
- **Risk**: Low — change is additive; existing paths unaffected when both metrics fail or when readiness fails
- **Breaking Change**: No

## Blocked By

- BUG-1032 — fix direct breakdown path first; ENH-1031 routes to `breakdown_issue` which needs correct wiring

## Labels

`enhancement`, `loops`, `fsm`, `refine-to-ready-issue`, `performance`

## Status

**Open** | Created: 2026-04-11 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/05d0324c-611c-469d-8af1-b4e42644c47d.jsonl`
