---
id: ENH-2116
title: 'rn-remediate diagnose: WIRE(ambiguity) heuristic fires on decision-driven ambiguity when integration map already exists'
priority: P3
type: ENH
status: open
captured_at: '2026-06-13T00:00:00Z'
discovered_date: '2026-06-13'
discovered_by: audit-loop-run
affects: scripts/little_loops/loops/rn-remediate.yaml
labels:
  - rn-remediate
  - loop-defect
  - diagnose
relates_to:
  - BUG-2007
---

# ENH-2116: rn-remediate diagnose — WIRE(ambiguity) heuristic fires on decision-driven ambiguity

## Summary

The `diagnose` state routes to WIRE whenever `score_ambiguity >= diagnose_ambiguity_threshold` (default 15), regardless of whether the ambiguity comes from a missing integration map or from conditional design choices. When `score_change_surface > 0` (the integration map is already documented), wire-issue adds more touchpoints but cannot resolve conditional-decision ambiguity, wasting a remediation slot without improving `outcome_confidence`.

## Current Behavior

**Run**: `rn-implement-20260613T124334`, input BUG-2011  
**Diagnosis scores**: `confidence=100, outcome=56, ambiguity=18, change_surface=0, decision_needed=false`

The `diagnose` action matched `WIRE(ambiguity)` because `18 >= 15`. `/ll:wire-issue` ran and added Wiring Pass 3 (~14 new touchpoints). After re-assess, `outcome_confidence` was still 56 (delta=0). The residual ambiguity in BUG-2011 came from a conditional implementation branch ("if we add `iteration_count` to `state_enter` payload — step 29") — a design decision, not a wiring gap.

Note: in the BUG-2011 case `change_surface=0`, so the current heuristic actually matched an edge case where wiring was appropriate (no integration map existed). However, the fix below adds a discriminating condition to handle the more common case where wiring already exists but decision-driven ambiguity remains.

## Root Cause

**File**: `scripts/little_loops/loops/rn-remediate.yaml` — `diagnose` state action

```bash
elif [ "$AMBIGUITY" -ge "${context.diagnose_ambiguity_threshold}" ]; then
  echo "WIRE"
```

This single branch routes all ambiguity above the threshold to WIRE. When `score_change_surface > 0` (integration map exists), the ambiguity is not coming from missing wiring — it comes from unresolved conditional decisions or unclear implementation steps. WIRE cannot fix that; REFINE or DECIDE is more appropriate.

## Expected Behavior

Only route to WIRE via the ambiguity branch when `score_change_surface == 0` (integration map is genuinely absent). When change_surface > 0 and ambiguity >= threshold, fall through to REFINE so that a full-rewrite pass can resolve the conditional logic that's blocking a high ambiguity score.

## Proposed Solution

In the `diagnose` state action, split the WIRE(ambiguity) branch:

```bash
# Before (single branch):
elif [ "$AMBIGUITY" -ge "${context.diagnose_ambiguity_threshold}" ]; then
  echo "WIRE"

# After (discriminating):
elif [ "$AMBIGUITY" -ge "${context.diagnose_ambiguity_threshold}" ] \
    && [ "$CHANGE_SURFACE" -eq 0 ]; then
  # Ambiguity is high AND no integration map exists → wiring can fill the gap
  echo "WIRE"
elif [ "$AMBIGUITY" -ge "${context.diagnose_ambiguity_threshold}" ]; then
  # Ambiguity is high BUT wiring already exists → residual ambiguity is decision-driven
  echo "REFINE"
```

## Acceptance Criteria

- [ ] `diagnose` action in `rn-remediate.yaml` only outputs WIRE from the ambiguity branch when `CHANGE_SURFACE == 0`
- [ ] When `AMBIGUITY >= diagnose_ambiguity_threshold` AND `CHANGE_SURFACE > 0`, `diagnose` outputs REFINE
- [ ] A test in `scripts/tests/test_rn_remediate.py` asserts this routing: `ambiguity=18, change_surface=5 → REFINE`; `ambiguity=18, change_surface=0 → WIRE`
- [ ] `ll-loop validate rn-remediate` passes with no new warnings

## Scope Boundaries

- Scope limited to the `WIRE(ambiguity)` branch in the `diagnose` state of `rn-remediate.yaml`
- Out of scope: changes to `diagnose_ambiguity_threshold` value
- Out of scope: changes to other diagnostic routing branches (CONFIDENCE, OUTCOME, DECIDE)
- Out of scope: changes to ambiguity scoring logic or other loops using similar scoring

## Impact

- **Priority**: P3 — Wasted remediation slots cause no meaningful outcome improvement; loop still converges via other paths
- **Effort**: Small — Two-line change to `diagnose` shell action in `rn-remediate.yaml` plus one test assertion
- **Risk**: Low — Refines routing condition without removing any existing route; WIRE path preserved for `change_surface=0`
- **Breaking Change**: No

## Session Log
- `/ll:format-issue` - 2026-06-13T18:32:25 - `bd2eb6a7-568d-4a00-8298-d0d06d2d9a27.jsonl`
- `/ll:audit-loop-run` - 2026-06-13T00:00:00Z - discovered during audit of rn-implement-20260613T124334
