---
id: ENH-2084
title: Add Wilson CI reporting to ll-loop run --baseline
type: ENH
priority: P3
status: done
captured_at: '2026-06-10T18:12:09Z'
completed_at: '2026-06-11T04:23:13Z'
discovered_date: '2026-06-10'
discovered_by: capture-issue
parent: EPIC-2087
confidence_score: 91
outcome_confidence: 83
score_complexity: 19
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 22
---

# ENH-2084: Add Wilson CI reporting to ll-loop run --baseline

## Summary

Extend `ll-loop run --baseline` and `ll-loop diagnose-evaluators` with Wilson 95% binomial confidence intervals, replacing bare point-estimate reporting for small sample sizes where naive estimates are unreliable.

## Motivation

Loop performance comparisons in `ll-loop run --baseline` report point estimates (k/N pass rates). For small sample sizes (n < 20), naive ±√(p(1-p)/n) intervals are inaccurate near 0 or 1 — the exact regime where loop optimization matters most. Wilson binomial confidence intervals give honest asymmetric uncertainty bounds for pass/fail outcomes.

## Current Behavior

`ll-loop run --baseline` reports only point estimates (k/N pass rates) in the baseline diff table with no confidence intervals. For small sample sizes (n < 20), estimates near 0 or 1 are misleading without uncertainty bounds. `ll-loop diagnose-evaluators` Bernoulli variance output similarly lacks CI quantification.

## Expected Behavior

- `ll-loop run --baseline` displays Wilson 95% CI bounds `[lower, upper]` alongside the point estimate in the diff table: `p_hat [lower, upper]`
- `ll-loop diagnose-evaluators` includes Wilson CI bounds in the Bernoulli variance section
- Formula implemented inline (no scipy or new runtime dependencies required)

## Proposed Solution

Add Wilson 95% CI calculation to the baseline comparison output in `ll-loop run --baseline`. Use the formula `(p + z²/2n ± z√(p(1-p)/n + z²/4n²)) / (1 + z²/n)` with z=1.96. Display as `[lower, upper]` bounds alongside the point estimate in the baseline diff table. Also surface Wilson CIs in the `ll-loop diagnose-evaluators` output for the Bernoulli variance check. Implement the formula directly to avoid adding a new dependency (no scipy.stats required).

## Implementation Steps

1. Implement Wilson 95% CI formula directly in `scripts/little_loops/` (no new dependencies)
2. Integrate Wilson CI output into `ll-loop run --baseline` diff table: `p_hat [lower, upper]`
3. Surface Wilson CIs in `ll-loop diagnose-evaluators` Bernoulli variance output
4. Add unit tests for the Wilson CI formula at boundary cases (p=0, p=1, small n)

## Acceptance Criteria

- [x] `ll-loop run --baseline` shows Wilson 95% CI bounds `[lower, upper]` alongside point estimate
- [x] `ll-loop diagnose-evaluators` includes Wilson CI in Bernoulli variance report
- [x] Formula implemented without `scipy` or other new dependencies
- [x] Unit tests cover p=0, p=1, n=1, and typical mid-range values

## Impact

- **Priority**: P3 — Useful for honest reporting at small n, but not blocking any optimization workflows
- **Effort**: Small — Pure formula implementation; no new dependencies; existing baseline diff table provides the integration hook
- **Risk**: Low — Additive output change only; no modifications to pass/fail logic or exit codes
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-10 | Priority: P3

---

## Scope Boundaries

**Note** (added by `/ll:audit-issue-conflicts`): This issue covers Wilson 95% CI bounds in `ll-loop run --baseline` diff table and `ll-loop diagnose-evaluators`. Related issue ENH-2080 adds a Bernoulli variance score column to the same baseline diff table and also reports variance in `diagnose-evaluators`. Both compute over the same p/n inputs drawn from the history DB. To avoid duplicate utility code, the Wilson CI formula and variance `p*(1-p)` computation should share a single `scripts/little_loops/stats.py` module. This issue should land before ENH-2080 (which `depends_on` ENH-2084) so the baseline diff table format is established first.


## Labels

`enhancement`, `ll-loop`, `statistics`, `reporting`

## Resolution

Implemented Wilson 95% CI (`(p + z²/2n ± z√(p(1-p)/n + z²/4n²)) / (1 + z²/n)` with z=1.96) in a new shared `scripts/little_loops/stats.py` module. Integrated into:
- `ll-loop run --baseline` diff table: harness/baseline pass-rates now display `XX%  [lo, hi]` CI bounds
- `ll-loop diagnose-evaluators`: variance line now includes `CI=[lo, hi]`
- `ll-loop calibrate-budget`: same CI alongside each evaluator's `p*(1-p)` line
- `EvaluatorVariance.to_dict()` serializes `ci_lower`/`ci_upper` for JSON consumers

No new runtime dependencies. 14 unit tests added covering p=0, p=1, n=1, midrange, custom z, and error cases.

## Session Log
- `/ll:manage-issue` - 2026-06-11T04:23:13Z - implementation complete
- `/ll:ready-issue` - 2026-06-11T04:06:40 - `0c981cab-32d8-4229-bc5d-eb371e08d0c4.jsonl`
- `/ll:format-issue` - 2026-06-10T23:33:25 - `c1ec6a7d-1589-4894-bc72-c32d1a4d4c69.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-10T23:30:28 - `59a16773-20bc-402b-b0cb-97d45d141b4c.jsonl`
