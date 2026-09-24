---
id: BUG-3553
title: refine-to-ready-issue decision/spike re-score cycles are bounded only by the circuit breaker
type: BUG
priority: P2
status: open
discovered_date: '2026-09-24'
labels:
- loops
- refine-to-ready-issue
---

# refine-to-ready-issue decision/spike re-score cycles are bounded only by the circuit breaker

## Summary

`check_decision_needed → resolve_decision_pre_breakdown → confidence_check →
check_readiness → check_outcome → check_decision_needed` repeats while
`decision_needed` stays set. Post-BUG-3278 `oracles/resolve-decision` reaches
`done` with the flag *legitimately* still set when a residual lower-tier group
survives (a defined human-review exit), so nothing in the loop breaks the cycle
— only `circuit.recurrent_window: 6`, after ~6 confidence-check oracle runs and
~6 resolve-decision sub-loops. The trip routes to `diagnose → classify_terminal`,
where no capture has a nonzero exit, so the run is ledgered `quality` instead of
`decision_unresolved` and the issue is not deferred for human review.

`run_spike` has the same shape: its one-shot guard is `spike_attempted`, written
by the `/ll:spike` skill. A spike that errors or never stamps the field re-fires
until the circuit trips.

## Current Behavior

Residual decision → up to ~30 steps of expensive re-scoring → `failed` with
class `quality`.

## Expected Behavior

One pre-breakdown resolve attempt per run (matching autodev's write-once
`autodev-decide-ran` marker); a second `decision_needed` reading routes to
`record_decision_unresolved` (defer + `decision_unresolved` class). The spike
gate is one-shot per run via an in-loop marker, independent of the skill.

## Steps to Reproduce

1. Run the loop on an issue with two decision tiers where `/ll:decide-issue --auto`
   resolves only the top tier and outcome stays below threshold.
2. Observe the loop re-enter `resolve_decision_pre_breakdown` until the
   recurrent-window circuit fires.

## Proposed Solution

- New `check_decide_attempts` counter (`refine-to-ready-decide-attempts`, target 2)
  between `check_decision_needed.on_yes` and `resolve_decision_pre_breakdown`;
  `on_no: record_decision_unresolved`.
- `check_spike_needed` additionally requires the run-dir marker
  `refine-to-ready-spike-ran` to be absent and writes it on the yes branch.
- `resolve_issue` resets both.

## Program Design

Loop YAML only (`scripts/little_loops/loops/refine-to-ready-issue.yaml`); no
Python changes. Mirrors the `check_reconcile_limit` counter shape.

## Impact

- **Priority**: P2 — wastes oracle/sub-loop runs and misclassifies the terminal.
- **Effort**: Small.
- **Risk**: Low — the circuit breaker stays as a backstop.

## Acceptance Criteria

- `check_decision_needed.on_yes` routes to `check_decide_attempts`; its second entry routes to `record_decision_unresolved`.
- `check_spike_needed` is one-shot per run without relying on `spike_attempted`.
- Tests cover the new routing; `ll-loop validate refine-to-ready-issue` is clean.

## Related

- BUG-3065, BUG-3278, ENH-3250, BUG-3551, BUG-3552

## Status

Open
