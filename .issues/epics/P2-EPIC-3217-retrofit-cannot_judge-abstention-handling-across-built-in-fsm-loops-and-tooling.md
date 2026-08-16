---
id: EPIC-3217
type: EPIC
title: Retrofit cannot_judge abstention handling across built-in FSM loops and tooling
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:26:39Z'
---

# EPIC-3217: Retrofit cannot_judge abstention handling across built-in FSM loops and tooling

## Summary

ENH-3185 added a 5-value LLM-judge verdict grammar (`yes`/`no`/`blocked`/`partial`/`cannot_judge`) with an SSOT at `scripts/little_loops/fsm/verdicts.py`, bounded abstention routing in `FSMExecutor`, a v41 history schema with `harness_eval_abstention_rate()`, and an `ll-harness` ABSTAIN exit code 3. The mechanism landed; adoption did not.

An audit of the built-in loops found **34 LLM-judged gates across 23 loops in `scripts/little_loops/loops/`, and not one declares `on_cannot_judge`**. Every gate therefore runs on the AC6 undeclared-abstention fallback: hold up to `_ABSTENTION_HOLD_CAP = 2` consecutive re-entries, then escalate to `on_error` (never `on_no`, never `route.default`). That fallback is safe by construction, but the *destination* it escalates to was written for infrastructure errors, not for "the judge could not observe this" — and for a third of the gates it is materially worse than the pre-ENH-3185 behavior.

Audit breakdown:

- **13 gates declare neither `on_cannot_judge` nor `on_error`.** `_abstention_fallback()` (`executor.py:2669`) returns `None`, so the run terminates via "No valid transition" after two holds. This set includes all three `harness-*` templates, which are the documented copy-paste examples in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — so the shape propagates into every user-authored harness.
- **10 "funnel" gates** send `on_yes`/`on_no`/`on_partial` to a single shared target (the LLM produces an artifact rather than judging), leaving abstention as the only diverging verdict. Three diverge into a hard failure: `goal-cluster::dedup_and_batch`, `loop-composer::decompose_goal`, and `loop-router::classify_goal` all fall to `finalize_failed`.
- **1 gate re-creates the fabricated-pass failure mode ENH-3185 exists to remove**: `sprint-build-and-validate::audit_conflicts` has `on_error: commit`, so an abstained conflict audit commits.
- **Both telemetry surfaces are unconsumed**: `harness_eval_abstention_rate()` has zero callers outside its own definition and tests, and `ll-harness` exit 3 collapses to `error` in the FSM `exit_code` evaluator (0→yes, 1→no, 2+→error, `evaluators.py:250-255`), making an abstained harness run indistinguishable from a crash to a parent loop.
- **Neither static-check surface knows the verdict exists**: `fsm/validation/` has no rule for the missing-both-routes condition, and `fsm-loop-schema.json` declares `on_partial` and `on_blocked` on `stateConfig` (`additionalProperties: false`) but not `on_cannot_judge`.

This EPIC coordinates the retrofit. It deliberately separates the mechanical route repairs (which remove latent run-killers and can land immediately) from the per-gate semantic work (which requires deciding what abstention *means* at each gate) and the tooling work (which prevents the gap from recurring).

## Scope

In scope: declaring abstention routes across the built-in loops in `scripts/little_loops/loops/`, a validator rule and JSON-schema property for `on_cannot_judge`, and wiring the two existing abstention telemetry surfaces into consumers.

Out of scope: changing the abstention grammar, the hold cap, or the routing precedence established by ENH-3185; and admitting `cannot_judge` into the binary consumers (blind comparator, contract evaluator), which `verdicts.py` documents as a deliberate exclusion (AC8).

## Sequencing

1. Funnel-gate repairs (mechanical, one line per gate, removes three run-killers).
2. Validator rule + JSON-schema property (prevents regression before the semantic work lands).
3. Per-gate semantics for the 13 no-route gates, including the harness templates.
4. Telemetry consumers.

The `audit_conflicts` fix is independent of the sequence and should land first on severity.


## Motivation

ENH-3185's stated purpose was to stop LLM-judged gates from coercing unobservable checks into a fabricated binary pass/fail. The grammar, the routing, the persistence, and the exit code all landed. What did not land is any *use* of them: no built-in loop declares an abstention route, and neither telemetry surface has a consumer. Until the retrofit happens, the enhancement's benefit is theoretical, and its safe-by-construction fallback is in some places worse than the behavior it replaced — a run that dies on "No valid transition", or an audit that commits.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/*.yaml` — 23 loops, 34 judged gates (see per-issue tables for the exact list)
- `scripts/little_loops/fsm/validation/` — new structural rule (ENH-3222)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — `stateConfig.properties.on_cannot_judge` (BUG-3221)
- `scripts/little_loops/fsm/evaluators.py` — `exit_code` mapping, if ENH-3224 takes that route
- `scripts/little_loops/history_reader.py` / a CLI reporting surface — ENH-3223 consumer

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `_abstention_declared` / `_abstention_fallback` / `_route_abstention_hold` define the semantics every loop change is written against; not expected to change
- `scripts/little_loops/fsm/verdicts.py` — SSOT for the grammar; not expected to change
- Consuming projects' own loop YAMLs — unaffected by the built-in loop edits, but affected by a validator rule that warns on their gates

### Tests
- `scripts/tests/test_fsm_schema.py` — existing schema/dataclass lockstep conventions (ENH-2896, ENH-2934, ENH-2997) are the pattern for BUG-3221
- FSM validation tests for the new rule
- `ll-loop validate` over all built-in loops must stay clean after the retrofit

### Documentation
- `docs/generalized-fsm-loop.md` — already documents `on_cannot_judge`; may need the funnel/expensive-gate guidance
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — the harness templates' inline comments are the de facto pattern documentation
- `docs/reference/API.md` — if `harness_eval_abstention_rate()` gains a CLI surface

## Impact

- **Priority**: P2 — one child is P1 (a fail-open path to `commit`); the rest are latent run-terminations and unrealized value in a just-shipped feature.
- **Effort**: Medium — the funnel repairs and the schema property are near-mechanical; the per-gate semantics for 13 gates and the telemetry consumers carry the real work.
- **Risk**: Low-Medium — loop YAML route additions are individually small and reversible, but they change control flow in loops that this repo's own automation runs, and every local-editable project on this machine picks up working-tree changes immediately.
- **Breaking Change**: No — all changes are additive routes, a new schema property, a warning-severity rule, and new reporting.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.executor` / `little_loops.fsm.validation`
  sections — abstention-fallback mechanics and the MR rule set this EPIC's
  children extend
- `.claude/CLAUDE.md` `## Loop Authoring` — meta-loop rules enforced by
  `ll-loop validate`, and the harness-template guide affected by 3 of the 13
  no-route gates

## Status

**Open** | Created: 2026-08-16 | Priority: P2

## Goal

Every LLM-judged gate in the built-in loops routes abstention deliberately, static checks prevent the shape from recurring, and the abstention data already being recorded reaches a consumer.

## Children
- **BUG-3218** — sprint-build-and-validate commits when the conflict audit abstains (open)
- **BUG-3219** — Judged gates with neither on_cannot_judge nor on_error terminate the run on abstention (open)
- **BUG-3220** — Funnel judged gates route abstention into finalize_failed in composer and router loops (open)
- **BUG-3221** — fsm-loop-schema.json stateConfig omits on_cannot_judge under additionalProperties false (open)
- **ENH-3222** — Validator rule for judged gates with no abstention route and no error route (open)
- **ENH-3223** — harness_eval_abstention_rate has no consumers - surface abstention as a criterion-quality signal (open)
- **ENH-3224** — ll-harness ABSTAIN exit code 3 is indistinguishable from an error to a parent FSM (open)



## Success Metrics

- Zero judged gates in `scripts/little_loops/loops/` declare neither `on_cannot_judge` nor `on_error` (currently 13).
- No judged gate routes abstention to a state its other verdicts do not reach, unless that divergence is stated deliberately (currently 4 diverge accidentally, 6 more coincide only by accident of `on_error`).
- No path exists from an abstained gate to `commit` (currently 1).
- `ll-loop validate` flags the missing-both-routes condition (currently no rule).
- `harness_eval_abstention_rate()` has at least one non-test consumer (currently zero).

## Session Log
- `/ll:capture-issue` - 2026-08-16T23:29:36 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`
