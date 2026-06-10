---
id: ENH-2084
title: Add Wilson CI reporting to ll-loop run --baseline
type: ENH
priority: P3
status: open
captured_at: "2026-06-10T18:12:09Z"
discovered_date: "2026-06-10"
discovered_by: capture-issue
parent: EPIC-2087
---

# ENH-2084: Add Wilson CI reporting to ll-loop run --baseline

## Motivation

Loop performance comparisons in `ll-loop run --baseline` report point estimates (k/N pass rates). For small sample sizes (n < 20), naive ±√(p(1-p)/n) intervals are inaccurate near 0 or 1 — the exact regime where loop optimization matters most. Wilson binomial confidence intervals give honest asymmetric uncertainty bounds for pass/fail outcomes.

## Proposed Solution

Add Wilson 95% CI calculation to the baseline comparison output in `ll-loop run --baseline`. Use the formula `(p + z²/2n ± z√(p(1-p)/n + z²/4n²)) / (1 + z²/n)` with z=1.96. Display as `[lower, upper]` bounds alongside the point estimate in the baseline diff table. Also surface Wilson CIs in the `ll-loop diagnose-evaluators` output for the Bernoulli variance check. Implement the formula directly to avoid adding a new dependency (no scipy.stats required).

## Implementation Steps

1. Implement Wilson 95% CI formula directly in `scripts/little_loops/` (no new dependencies)
2. Integrate Wilson CI output into `ll-loop run --baseline` diff table: `p_hat [lower, upper]`
3. Surface Wilson CIs in `ll-loop diagnose-evaluators` Bernoulli variance output
4. Add unit tests for the Wilson CI formula at boundary cases (p=0, p=1, small n)

## Acceptance Criteria

- [ ] `ll-loop run --baseline` shows Wilson 95% CI bounds `[lower, upper]` alongside point estimate
- [ ] `ll-loop diagnose-evaluators` includes Wilson CI in Bernoulli variance report
- [ ] Formula implemented without `scipy` or other new dependencies
- [ ] Unit tests cover p=0, p=1, n=1, and typical mid-range values

## Status

open
