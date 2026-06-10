---
id: ENH-2080
title: Add retry-budget calibration guide tied to evaluator health
type: ENH
priority: P3
status: open
captured_at: "2026-06-10T18:12:09Z"
discovered_date: "2026-06-10"
discovered_by: capture-issue
parent: EPIC-2087
---

# ENH-2080: Add retry-budget calibration guide tied to evaluator health

## Motivation

Loop `max_iterations` values are currently set by convention. Additional iterations amplify a sound strategy but produce near-zero returns when the underlying evaluator is unhealthy. Spending retry budget against a toothless evaluator wastes tokens without changing outcomes, which is directly indicated by the existing Bernoulli variance check in CLAUDE.md.

## Proposed Solution

Add a `ll-loop calibrate-budget <loop>` subcommand that:
1. Runs the loop's evaluator in isolation across a sample of past run states
2. Reports the Bernoulli variance `p*(1-p)`
3. If variance is below 0.05, emits a warning that increasing `max_iterations` is unlikely to help and recommends fixing the evaluator first

Document the threshold in the Loop Authoring section of CLAUDE.md with a concrete example linking evaluator health to retry budget ROI. Surface the variance score in `ll-loop run --baseline` output.

## Implementation Steps

1. Add `calibrate-budget` subcommand to `ll-loop` CLI
2. Implement evaluator isolation runner against sampled past run states from history DB
3. Compute and report Bernoulli variance per evaluator state
4. Emit actionable warning when variance < 0.05
5. Surface variance score in `ll-loop run --baseline` diff table
6. Document threshold and ROI linkage in `CLAUDE.md` Loop Authoring section with example

## Acceptance Criteria

- [ ] `ll-loop calibrate-budget <loop>` runs and reports per-evaluator Bernoulli variance
- [ ] Variance < 0.05 triggers a warning recommending evaluator repair before increasing iterations
- [ ] `ll-loop run --baseline` output includes variance score
- [ ] CLAUDE.md Loop Authoring section documents the threshold with a worked example

## Status

open
