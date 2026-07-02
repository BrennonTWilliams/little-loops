---
id: ENH-2440
priority: P3
type: ENH
status: done
discovered_date: 2026-07-01
discovered_by: manual
completed_at: 2026-07-02T04:09:18Z
---

# ENH-2440: vega-viz — prevent panel-level params regression and raise step budget

## Summary

Harden the `vega-viz` loop (`scripts/little_loops/loops/vega-viz.yaml`) against a
recurring Vega-Lite compile regression and a step-budget preemption that together
caused a budget-bounded no-pass. Adds preventive selection-scope guidance to the
`generate` prompt, a targeted `Duplicate signal name` recovery instruction to the
`repair` prompt, and raises `max_steps` from 20 to 30.

## Motivation

Run `vega-viz-20260702T025053Z` terminated via the designed `max_steps_summary`
terminal state without reaching `EVAL_PASS` (best score 24/40, 5 BLOCKING items
remaining). Diagnosis in
`.loops/diagnostics/vega-viz-20260702T025053Z.md` identified two layers:

- **Proximate cause**: the `max_steps: 20` ceiling preempted a *completed* iter-3
  `repair` before it could re-validate/score. The natural `repair → validate`
  transition was emitted, then intercepted 101 µs later by the step cap
  (events.jsonl:273–275). The repaired spec was never validated, captured, scored,
  or recorded.
- **Systemic cause**: the `generate` state repeatedly re-introduced a panel-level
  interval-selection `params` block in multi-layer specs, which Vega-Lite projects
  once per layer into the same scope, producing `Error: Duplicate signal name:
  "brush_x"` and a failed compile. The pattern recurred in 2 of 3 attempted
  iterations (iter-1, iter-3). The model demonstrably knows the fix when shown the
  compile error (events.jsonl:260) but reverts to the wrong scope under generation
  pressure — so a larger budget alone would only buy more iterations of the same
  regression.

## Changes Made

All edits in `scripts/little_loops/loops/vega-viz.yaml`:

1. **`max_steps: 20 → 30`** (loop metadata) with an explanatory comment referencing
   the diagnostics file and the ~1.5-repair-cycles-per-iteration cost pattern. This
   addresses the proximate cause (step-cap preemption of a completed repair).

2. **Preventive `SELECTION SCOPE` rule added to the `generate` prompt.** Instructs
   the generator, in any spec with a `layer` array, never to place an interval/point
   selection that projects an encoding channel (`select.encodings: ["x"]`/`["y"]`)
   in the top-level/panel-level `params` block; attach each selection to the single
   layer that owns it and reference it cross-layer by name. Documents the safe
   exception (panel-level params that do not project an encoding channel, e.g. bound
   input widgets). This attacks the systemic cause at the authoring step, where
   nothing previously reminded the model of the rule.

3. **Targeted `Duplicate signal name` recovery added to the `repair` prompt.**
   When that specific error appears, instructs re-scoping the offending param into
   its owning layer (not merely renaming the signal).

## Rationale for Approach

Of the three ranked remediations in the diagnosis, the lowest-risk pair was chosen:
the `max_steps` bump plus prompt hardening. The proposed deterministic `validate`
guard (Rank 1) was deferred because its sketched predicate depends on `jq` (not part
of this loop's npx-vega toolchain) and its "any panel-level params in a multi-layer
spec" test is too broad and would false-positive on legitimate cross-layer
selections. Repair-from-best (Rank 3) was also deferred. Both remain available as
follow-ups if the regression persists.

## Scope Boundaries

- **In scope**: prompt-text and `max_steps` edits to `vega-viz.yaml`.
- **Out of scope**: the deterministic validate-time anti-pattern guard (deferred Rank 1).
- **Out of scope**: repair-from-best-known-spec fallback (deferred Rank 3).
- **Out of scope**: engine-level concerns flagged in the diagnosis — the
  `status: "interrupted"` label for budget-bounded termination, and stale
  `prev_result.output` on resume. These live in the FSM engine, not this loop YAML.

## Verification

- YAML parses cleanly (PyYAML); `max_steps == 30`, `on_max_steps == max_steps_summary`.
- All 13 states present; routing unchanged (`generate → validate`,
  `validate → capture/repair/repair`, `repair → validate`).
- Both prompt inserts confirmed present in their target state action blocks.
- `ll-loop validate vega-viz` not run in-session: the CLI requires Python 3.11+ and
  the available sandbox has 3.10. Because the edits are prompt-text plus one scalar
  (no new states, routes, shell blocks, or `${...}` interpolation), they cannot trip
  the structural or MR gates; the parse + structure check covers the only real risk.
  Recommend running `ll-loop validate vega-viz` once in a 3.11 environment as a final
  confirmation, and a full re-run (`ll-loop run vega-viz "<desc>" --max-steps 30`) to
  confirm the regression no longer recurs.

## Status

Completed.

## References

- Diagnosis: `.loops/diagnostics/vega-viz-20260702T025053Z.md`
- Failing run: `vega-viz-20260701T215053` (budget-bounded-no-pass, best 24/40)
