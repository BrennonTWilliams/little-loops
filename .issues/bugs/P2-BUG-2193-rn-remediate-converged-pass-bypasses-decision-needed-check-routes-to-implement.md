---
id: BUG-2193
title: 'rn-remediate: CONVERGED_PASS bypasses decision_needed check and routes to
  implement'
type: BUG
priority: P2
status: done
captured_at: '2026-06-15T00:00:00Z'
completed_at: '2026-06-15T19:18:43Z'
discovered_date: '2026-06-15'
discovered_by: audit-loop-run
relates_to:
- BUG-1985
labels:
- rn-implement
- rn-remediate
- loop-defect
- routing
confidence_score: 96
outcome_confidence: 89
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 23
score_change_surface: 23
decision_needed: false
---

# BUG-2193: rn-remediate CONVERGED_PASS bypasses decision_needed check

## Summary

When `rn-remediate`'s `refine` pass both raises scores above the readiness/outcome thresholds AND sets `decision_needed: true`, `check_convergence` emits `CONVERGED_PASS` without inspecting the flag. The issue is then routed to `implement` (`ll-auto --only <ID>`), which always fails because Claude detects `decision_needed: true` and stops to ask for `/ll:decide-issue` instead of implementing. `ll-auto` exits 1, and `rn-remediate` reaches its `failed` terminal.

Observed in run `2026-06-15T175757` on FEAT-2083:
- `/ll:refine-issue` raised readiness 76→86, outcome 78→83 (both above thresholds), and set `decision_needed: true` (Option A vs Option B for deferred-queue persistence)
- `check_convergence`: POST_CONFIDENCE (86) ≥ 85 AND POST_OUTCOME (83) ≥ 75 → emitted `CONVERGED_PASS` without reading `decision_needed`
- `gate_implement` also ignores `decision_needed`, emitted `IMPLEMENT`
- `ll-auto --only FEAT-2083` stopped and asked for `/ll:decide-issue FEAT-2083`; no code changes; exit 1
- `rn-remediate` reached `failed` terminal

## Relation to BUG-1985

BUG-1985 (done) fixed the stall path: `TOTAL_DELTA ≤ 0 AND decision_needed = true → NEEDS_MANUAL_REVIEW`. This is the **pass path** equivalent: `TOTAL_DELTA > 0, thresholds met AND decision_needed = true` still routes to `CONVERGED_PASS`. The fix for BUG-1985 left this branch unguarded.

## Root Cause

- **File**: `loops/rn-remediate.yaml`
- **Anchor**: `check_convergence` state action
- **Cause**: The `CONVERGED_PASS` branch checks only numeric score thresholds (readiness ≥ 85, outcome ≥ 75) and never inspects `decision_needed` in the post-scores JSON. BUG-1985 added a `decision_needed` guard only on the stall/no-improvement path (`TOTAL_DELTA ≤ 0`), leaving the pass path (`TOTAL_DELTA > 0, thresholds met`) unguarded. `gate_implement` has the same omission, providing no secondary defense.

## Current Behavior

In `check_convergence` (`loops/rn-remediate.yaml`):

```bash
if [ "$POST_CONFIDENCE" -ge "$READINESS_THRESHOLD" ] && [ "$POST_OUTCOME" -ge "$OUTCOME_THRESHOLD" ]; then
  echo "CONVERGED_PASS"    # <-- decision_needed never inspected here
```

## Expected Behavior

When `check_convergence` detects thresholds met AND `decision_needed: true` in the post-scores JSON, the issue is blocked by a human-required decision — not ready to implement. Emit `NEEDS_MANUAL_REVIEW` instead of `CONVERGED_PASS`.

## Steps to Reproduce

1. Run `ll-loop run rn-implement FEAT-2083` (or any issue where `/ll:refine-issue` sets `decision_needed: true` while also improving scores above the gate)
2. Observe `check_convergence` emitting `CONVERGED_PASS`
3. Observe `ll-auto --only <ID>` stopping with "Run `/ll:decide-issue <ID>` to pick an approach" and exit code 1

## Proposed Solution

In `check_convergence` action (`loops/rn-remediate.yaml`), guard the `CONVERGED_PASS` branch:

```bash
# BEFORE:
if [ "$POST_CONFIDENCE" -ge "$READINESS_THRESHOLD" ] && [ "$POST_OUTCOME" -ge "$OUTCOME_THRESHOLD" ]; then
  echo "CONVERGED_PASS"

# AFTER:
if [ "$POST_CONFIDENCE" -ge "$READINESS_THRESHOLD" ] && [ "$POST_OUTCOME" -ge "$OUTCOME_THRESHOLD" ]; then
  POST_DECISION=$(jq -r '.decision_needed // "false"' "$POST" 2>/dev/null)
  if [ "$POST_DECISION" = "true" ]; then
    echo "NEEDS_MANUAL_REVIEW"
  else
    echo "CONVERGED_PASS"
  fi
```

**Defense-in-depth** (optional): `gate_implement` can also check `decision_needed` from the live issue file, so any path that bypasses `check_convergence` is still guarded.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Exact fix location: `check_convergence` at lines 524–525 in `scripts/little_loops/loops/rn-remediate.yaml` — the first `if` block that currently emits bare `echo "CONVERGED_PASS"`
- `$POST` variable is already in scope at the fix point (set to `$RUN_DIR/post_scores_$ID.json` at line ~471 of the same action block); no additional setup needed
- The stall-branch guard at lines 526–533 uses the identical expression `jq -r '.decision_needed // "false"' "$POST" 2>/dev/null` — mirror it exactly
- `route_conv_manual_review` (line ~561) and `emit_needs_manual_review` (line ~634) are already fully wired; no new routing states are needed — the fix only changes what `check_convergence` emits
- Defense-in-depth for `gate_implement` (line ~318): `ll-issues check-flag "$${ID}" decision_needed` is already used by the `check_decision_needed` state (lines 193–198) — same pattern applies; route a new `NEEDS_DECISION` verdict to `emit_needs_manual_review`

## Files to Modify

- `loops/rn-remediate.yaml` — `check_convergence` state action: add `decision_needed` guard inside the `CONVERGED_PASS` branch (primary fix)
- `loops/rn-remediate.yaml` — `gate_implement` state action: optionally add live-file `decision_needed` check as defense-in-depth

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` — `check_convergence` state (lines ~524–536): add `POST_DECISION` guard inside the first `if` branch (primary fix)
- `scripts/little_loops/loops/rn-remediate.yaml` — `gate_implement` state (line ~307): optionally add `decision_needed` check as defense-in-depth

### Routing States (No Modification Needed — Already Wired)
- `scripts/little_loops/loops/rn-remediate.yaml` — `route_conv_manual_review` (line ~561): already routes `NEEDS_MANUAL_REVIEW` token → `emit_needs_manual_review`
- `scripts/little_loops/loops/rn-remediate.yaml` — `emit_needs_manual_review` (line ~634): already writes `MANUAL_REVIEW_NEEDED` to outcome file and routes to `failed` terminal

### Tests
- `scripts/tests/test_rn_remediate.py` — `TestOutcomeTokenChannel.test_check_convergence_detects_decision_needed` (lines 978–984): existing stall-path regression test; extend or mirror for the pass-path guard
- `scripts/tests/test_rn_remediate.py` — `TestDiagnoseAmbiguityWireDiscrimination._run` (lines 1040–1070): bash subprocess test helper pattern to follow for a behavioral pass-path test

### Similar Patterns (Reference)
- `scripts/little_loops/loops/rn-remediate.yaml` — `check_convergence` stall branch (lines 526–533): exact `jq` expression to mirror (`POST_DECISION=$(jq -r '.decision_needed // "false"' "$POST" 2>/dev/null)`)
- `scripts/little_loops/loops/rn-remediate.yaml` — `check_decision_needed` state (lines 193–198): `ll-issues check-flag` shell-exit fragment variant (reference for `gate_implement` defense-in-depth)

## Implementation Steps

1. **Primary fix** — In `scripts/little_loops/loops/rn-remediate.yaml`, `check_convergence` state (lines ~524–525): replace the bare `echo "CONVERGED_PASS"` with the `POST_DECISION` guard, mirroring the stall branch at lines 526–533:
   ```bash
   POST_DECISION=$(jq -r '.decision_needed // "false"' "$POST" 2>/dev/null)
   if [ "$POST_DECISION" = "true" ]; then
     echo "NEEDS_MANUAL_REVIEW"
   else
     echo "CONVERGED_PASS"
   fi
   ```
   `$POST` is already set to `$RUN_DIR/post_scores_$ID.json` earlier in the same action block — it is in scope at this point with no additional setup.

2. **Optional defense-in-depth** — In `gate_implement` state (line ~318), add before the complexity-band block:
   ```bash
   if ll-issues check-flag "$${ID}" decision_needed 2>/dev/null; then
     echo "NEEDS_DECISION"
     exit 0
   fi
   ```
   Add a `NEEDS_DECISION` routing path through `gate_implement`'s routing table to `emit_needs_manual_review`. This guards any future bypass of `check_convergence`.

3. **Add pass-path regression test** — In `scripts/tests/test_rn_remediate.py`, add a test in `TestOutcomeTokenChannel` following the `test_check_convergence_detects_decision_needed` pattern (lines 978–984) that asserts the pass-path guard is present in the `check_convergence` action. Optionally add a behavioral subprocess test (following `_run` at lines 1040–1070) that injects a temp POST JSON with `decision_needed: true` and scores above thresholds and asserts output is `NEEDS_MANUAL_REVIEW`.

4. **BUG-1985 regression** — Run `python -m pytest scripts/tests/test_rn_remediate.py -v` to verify the stall-path guard and existing routing are unaffected.

## Acceptance Criteria

- [ ] `check_convergence` emits `NEEDS_MANUAL_REVIEW` when thresholds are met but `decision_needed: true`
- [ ] `rn-remediate` routes `NEEDS_MANUAL_REVIEW` to the existing manual-review handler (not `implement`)
- [ ] A test or `ll-loop simulate` run with a fixture issue that has `decision_needed: true` and scores above thresholds confirms the new routing
- [ ] BUG-1985 regression: `CONVERGED_STALLED + decision_needed` still routes to `NEEDS_MANUAL_REVIEW` (not broken by this change)

## Impact

- **Priority**: P2 — Causes automated `rn-remediate` runs to fail at the terminal when issues need manual decisions, forcing manual operator intervention in what should be a cleanly-handled case. The stall path (BUG-1985) is guarded; this symmetry gap was unknown until observed in production.
- **Effort**: Small — Single guard clause in `check_convergence` plus an optional defense-in-depth guard in `gate_implement`; no new states or routing tables needed.
- **Risk**: Low — Change is additive: the new `decision_needed` check gates an existing branch rather than replacing logic. Non-decision issues (the common case) follow the identical code path. BUG-1985 stall routing is unaffected.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-15 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-06-15T19:14:45 - `0fbea843-ba09-4b11-bdab-deaf05918c21.jsonl`
- `/ll:refine-issue` - 2026-06-15T19:09:12 - `f9981eaf-3dbc-4974-a5e6-36a59852650d.jsonl`
- `/ll:format-issue` - 2026-06-15T18:59:45 - `8f899d92-1ce7-4186-817c-89a797e247d3.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `f2f3df1b-ff88-42ca-bb50-1fcba18c0c5c.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `59bb93b6-bcfd-4cc4-b54e-e42012807e6e.jsonl`
