---
id: BUG-2007
title: "rn-remediate: four design defects in score-routing and convergence logic"
priority: P2
type: bug
status: open
captured_at: "2026-06-07T20:43:39Z"
discovered_date: "2026-06-07"
discovered_by: capture-issue
affects: scripts/little_loops/loops/rn-remediate.yaml
---

# BUG-2007: rn-remediate: four design defects in score-routing and convergence logic

## Summary

`rn-remediate.yaml` has four design defects that affect routing correctness and convergence detection. Three are logical errors; one is a dead code path introduced by redundant gating.

## Current Behavior

`rn-remediate.yaml` exhibits four independent routing and convergence defects:
1. `wire` unconditionally chains to `refine` on success, running a full rewrite pass even when wiring alone resolved the condition
2. `diagnose` uses hardcoded literals (`15` for ambiguity/complexity/change_surface, `50` for the low-confidence floor) that do not adjust when callers override `readiness_threshold` or `outcome_threshold`
3. `check_convergence` compares against `pre_scores_$ID.json` written once at session start and never refreshed — delta accumulates across the full session instead of measuring the most recent pass
4. The `check_outcome → diagnose → route_d_implement` path is unreachable; `check_readiness` already failed the both-threshold gate, so `route_d_implement` can never fire from this branch

## Expected Behavior

- `wire` routes to `re_assess` on success; only falls back to `refine` if re-assessment shows ambiguity/artifacts still present
- `diagnose` thresholds reference named context parameters (not hardcoded literals) so callers can tune routing to match their score targets
- `check_convergence` overwrites `pre_scores_$ID.json` with current post-scores at the end of each pass, measuring pass-over-pass delta
- The dead `check_outcome → diagnose` path is replaced with a direct route to an appropriate remediation state

## Root Cause

**File**: `scripts/little_loops/loops/rn-remediate.yaml`

Four independent defects:

### Defect 1 — `wire` unconditionally chains to `refine` (line 258)

The `wire` state routes `on_success: refine` regardless of outcome. If wiring alone resolves the ambiguity/missing-artifacts condition, a full `--full-rewrite` refine pass still runs before re-assessment. This wastes a remediation-budget slot and may overwrite valid wiring changes.

### Defect 2 — `diagnose` uses hardcoded magic thresholds (lines 176–183)

Routing decisions in `diagnose` use literals `15` for `ambiguity`, `complexity`, and `change_surface`, and `50` for the low-confidence REFINE floor. These are not derived from `context.readiness_threshold`, `context.outcome_threshold`, or any loop parameter. When callers override thresholds (e.g. `readiness_threshold: 70`), the `diagnose` routing does not adjust — the readiness gate and the routing gate disagree.

### Defect 3 — `check_convergence` compares against stale initial `pre_scores` (lines 316–344)

`pre_scores_$ID.json` is written once during `verify_scores_persisted` at session start and never updated between remediation passes. After multiple passes, `TOTAL_DELTA` accumulates across the entire session rather than measuring the last pass. A stalled issue that improved early and plateaued will never emit `CONVERGED_STALLED` because its cumulative delta exceeds the ≤2 threshold. The fix is to overwrite `pre_scores_$ID.json` with the current `post_scores_$ID.json` at the end of each `check_convergence` run, so the delta is always pass-over-pass.

### Defect 4 — Dead path: `check_outcome → diagnose → route_d_implement` can never fire (lines 95–196)

`check_readiness` (line 95) succeeds only when both `confidence ≥ readiness_threshold` AND `outcome ≥ outcome_threshold`. When it fails, `check_outcome` (line 108) tests `outcome ≥ outcome_threshold` alone. If that passes, execution enters `diagnose`, whose first rule is "if both scores ≥ threshold → emit IMPLEMENT". But `check_readiness` already verified that both-threshold condition is false, so `route_d_implement` can never fire from this path. The issue is that `check_outcome` routing to `diagnose` instead of a lower-confidence remediation state (e.g. `refine` directly) is misleading and adds dead states to the routing chain.

## Steps to Reproduce

These are static code defects visible by inspection:

1. Open `scripts/little_loops/loops/rn-remediate.yaml`
2. Locate the `wire` state — `on_success: refine` is hardcoded (line 258); routing skips re-assessment regardless of outcome
3. Locate the `diagnose` state (lines 176–183) — routing uses literals `15` and `50` not derived from context parameters
4. Locate the `check_convergence` state (lines 316–344) — `pre_scores_$ID.json` is written once and never refreshed; run two remediation passes and observe cumulative vs. pass-over-pass delta discrepancy
5. Trace: `check_readiness` (line 95) fails both-threshold test → `check_outcome` (line 108) passes outcome-only test → `diagnose` first rule checks both thresholds again → `route_d_implement` can never fire from this branch

## Acceptance Criteria

- [ ] `wire` routes to `re_assess` on success (not unconditionally to `refine`); only routes to `refine` if re-assessment shows ambiguity/artifacts remain
- [ ] `diagnose` thresholds for `ambiguity`, `complexity`, `change_surface`, and the low-confidence floor are derived from loop context parameters (or explicit named context keys), not hardcoded literals
- [ ] `check_convergence` overwrites `pre_scores_$ID.json` with the current post-scores at the end of each pass so delta is always pass-over-pass
- [ ] The dead `check_outcome → diagnose` path is replaced with a direct route to the appropriate remediation state (e.g. `refine` or `diagnose` with a guard that skips `route_d_implement`)
- [ ] `ll-loop validate rn-remediate` passes with no new errors after the fix

## Implementation Notes

- Defect 3 fix: at the end of `check_convergence`, add `cp "${RUN_DIR}/post_scores_${ID}.json" "${RUN_DIR}/pre_scores_${ID}.json"` before the emitted token
- Defect 2 fix: add context keys `diagnose_ambiguity_threshold`, `diagnose_complexity_threshold`, `diagnose_change_surface_threshold`, `diagnose_confidence_floor` with defaults matching current literals, then reference them in `diagnose`
- Defect 1 fix: `wire` → `re_assess` on success; add a routing state after `re_assess` that checks if ambiguity/artifacts are still flagged before deciding whether to call `refine`
- Defect 4 fix: remove `check_outcome` or reroute its `on_yes` branch to skip `diagnose` and go directly to a suitable lower-confidence remediation state

## Impact

- **Priority**: P2 — routing correctness directly affects convergence detection reliability; stalled issues may never emit `CONVERGED_STALLED`, and the dead path misleads FSM readers
- **Effort**: Medium — four independent targeted fixes in YAML and shell (`cp` call, context key references, routing reroute, dead state removal)
- **Risk**: Low — all changes scoped to `rn-remediate.yaml`; no public API changes; fixes align routing with documented intent
- **Breaking Change**: No

## Labels

`bug`, `loops`, `rn-remediate`, `routing`

## Session Log
- `/ll:format-issue` - 2026-06-07T20:48:57 - `8e6e4e26-f150-4e10-860a-db222eaca46f.jsonl`
- `/ll:capture-issue` - 2026-06-07T20:43:39Z - captured from conversation review of rn-remediate.yaml
