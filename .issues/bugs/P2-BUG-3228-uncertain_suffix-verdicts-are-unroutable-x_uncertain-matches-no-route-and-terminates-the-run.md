---
id: BUG-3228
type: BUG
title: 'uncertain_suffix verdicts are unroutable: X_uncertain matches no route and
  terminates the run'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T01:19:18Z'
parent: EPIC-3217
---

# BUG-3228: uncertain_suffix verdicts are unroutable: X_uncertain matches no route and terminates the run

## Summary

`uncertain_suffix: true` makes a loop unroutable. `evaluate_llm_structured()` appends `_uncertain` to *whatever* verdict the judge returned when `confidence < min_confidence` (`fsm/evaluators.py:1295-1296`), but `FSMExecutor._route()` (`fsm/executor.py:2699-2752`) has no suffix handling for any verdict — so `yes_uncertain` matches no shorthand, no `extra_routes` key, and no route-table entry, returns `None`, and the run terminates via `_finish("error", "No valid transition")`.

The setting is therefore unusable as shipped: a loop that enables it dies on the first below-threshold `yes`, unless the author has declared `on_yes_uncertain`, `on_no_uncertain`, `on_partial_uncertain`, `on_blocked_uncertain` and `on_cannot_judge_uncertain` by hand. No loop under `scripts/little_loops/loops/` sets `uncertain_suffix` (grep-confirmed), which is why this has never surfaced in a run.

## Current Behavior

Against a state declaring `on_yes`/`on_no`/`on_error` (verified by direct call):

```
yes                    -> _route='done'
yes_uncertain          -> _route=None        # run dies: "No valid transition"
no_uncertain           -> _route=None
partial_uncertain      -> _route=None
cannot_judge           -> _route=None        # holds, then _abstention_fallback
cannot_judge_uncertain -> _route=None        # holds, then _abstention_fallback
```

With `on_cannot_judge` declared, `cannot_judge` resolves but `cannot_judge_uncertain` still returns `None` — `_abstention_declared()` (`executor.py:2655-2664`) matches the literal verdict string, as its own docstring states.

`uncertain_suffix` is declared in `fsm-loop-schema.json:765` and `EvaluateConfig` (`fsm/schema.py:103`, default `false`), so a loop author reading the schema can enable a setting that breaks their loop.

## Expected Behavior

`X_uncertain` falls back to `on_X` (or `route.routes["X"]`) when the state declares no explicit `on_X_uncertain` / `route.routes["X_uncertain"]`. An explicit suffixed route always wins, so an author who wants distinct handling for a low-confidence verdict still gets it.

This preserves ENH-3185 AC12's position that the two signals are semantically distinct — `cannot_judge` is "I could not evaluate it", `_uncertain` is "I am unsure" — while making the combination routable by default instead of fatal.

For the abstention verdicts specifically, the fallback must compose with the existing hold machinery: `cannot_judge_uncertain` at a state declaring `on_cannot_judge` should count as *declared* (route immediately, no hold), matching the base verdict's behavior.

## Motivation

Resolves decision (a) of EPIC-3217. The retrofit children (BUG-3218, BUG-3219, BUG-3220) declare `on_cannot_judge` only; without this fix, each of those gates still has an unroutable `cannot_judge_uncertain` path, and ENH-3222's validator rule would certify the narrow form as complete.

The alternatives were considered and rejected at the EPIC: declaring both keys at ~22 gate sites hardens one branch of an already-fatal configuration and doubles routing boilerplate forever; an abstention-only prefix-match fixes 1 of 5 suffixed verdicts and encodes an asymmetry that is hard to explain later.

## Proposed Solution

Add the suffix fallback to `_route()` and the matching declaration check in `_abstention_declared()`, after the explicit-route lookups and before returning `None`. Strip a trailing `_uncertain` (the literal suffix, per the `history_reader.py:3089` precedent — not an arbitrary trailing token) and retry the same resolution order with the base verdict.

Note this changes shipped ENH-3185 routing semantics, so it needs its own tests rather than riding along with a loop-YAML retrofit. `test_fsm_executor.py::TestAbstentionRouting` (from line 1882) already covers the undeclared/declared abstention matrix and is the natural home; `test_cannot_judge_uncertain_undeclared_also_holds_then_falls_to_on_error` (line 2041) asserts today's behavior for the undeclared case and should keep passing — the fallback changes the *declared* case, not the undeclared one.

## Impact

Makes `uncertain_suffix` usable for the first time and closes the `cannot_judge_uncertain` gap across every gate the EPIC-3217 retrofit touches, without adding routing boilerplate to any of them.

## Status

**Open** | Created: 2026-08-17 | Priority: P2
