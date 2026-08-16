---
id: ENH-3222
type: ENH
title: Validator rule for judged gates with no abstention route and no error route
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:28:45Z'
parent: EPIC-3217
---

# ENH-3222: Validator rule for judged gates with no abstention route and no error route

## Summary

`ll-loop validate` has no rule covering the condition that terminates a run on abstention: an LLM-judged gate declaring neither `on_cannot_judge` nor `on_error`. The condition is entirely statically detectable, and it currently holds for 13 gates across the built-in loops.

## Current Behavior

`scripts/little_loops/fsm/validation/` contains no reference to `cannot_judge` or abstention. The MR-1..MR-14 rule set predates ENH-3185.

A loop author writing a `check_semantic` gate with `on_yes`/`on_no` and no error route gets a clean validate, and the abstention run-termination surfaces only at runtime, after `_ABSTENTION_HOLD_CAP = 2` holds have re-run the state's action twice.

## Expected Behavior

`ll-loop validate` emits a diagnostic for any state whose evaluator can produce the full verdict grammar (`evaluate.type: llm_structured`, and states resolving to it via the `llm_gate` fragment) when the state declares neither a `cannot_judge` route — `on_cannot_judge` or a `cannot_judge` key in `route:` — nor an error route (`on_error` or `route.error`).

The message should name the runtime consequence ("abstention terminates the run via 'No valid transition' after N holds") rather than just the missing key, matching the explanatory style of the existing MR-8 evidence-contract warning.

## Motivation

The sibling issues in this EPIC fix the 13 known instances. Without a rule, the next judged gate someone writes reintroduces the shape — and the failure only appears in production runs, at the cost of two re-executions of the gate's action.

## Proposed Solution

Add the rule to `scripts/little_loops/fsm/validation/`. Two decisions for the implementer:

**Severity.** WARNING is the safer default: ERROR would fail `ll-loop validate` on 13 shipped loops until the sibling issues land, and would break any consuming project's existing loops on upgrade. If ERROR is wanted eventually, sequence it after the retrofit.

**Detection scope.** Resolving `llm_gate`-fragment states requires fragment expansion; confirm whether the validation pass runs pre- or post-expansion and detect accordingly, since two of the affected gates (`learning-tests-audit`, `migrate-sdk-version`) reach `llm_structured` only through the fragment. Note that `fsm/validation`'s MR-8 lint operates on FSM YAML `evaluate.prompt` text only — this rule operates on routing keys, so it is a structural rule rather than an evaluator-prompt rule and belongs with the structural rules accordingly.

Per project policy, enforce via the local pytest suite; no hosted CI.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

Prevents recurrence of the 13-gate defect class. Adds one warning per affected loop until the retrofit lands.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.validation` section — existing
  MR-4/MR-8/MR-14 rule patterns to model the new rule after

## Status

**Open** | Created: 2026-08-16 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-08-16T23:29:37 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`
