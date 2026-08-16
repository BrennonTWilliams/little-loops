---
id: ENH-3224
type: ENH
title: ll-harness ABSTAIN exit code 3 is indistinguishable from an error to a parent
  FSM
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:29:27Z'
parent: EPIC-3217
---

# ENH-3224: ll-harness ABSTAIN exit code 3 is indistinguishable from an error to a parent FSM

## Summary

ENH-3185 gave `ll-harness` a distinct ABSTAIN exit code 3, so an inconclusive run is separable from a pass (0) and a failure (1). A parent FSM cannot see that distinction: the `exit_code` evaluator maps `0 → yes`, `1 → no`, and `2+ → error` (`scripts/little_loops/fsm/evaluators.py:250-255`), so exit 3 collapses into `error` — the same verdict a crash, a missing binary, or a timeout produces.

## Current Behavior

A loop shelling out to `ll-harness` (via the `shell_exit` fragment in `loops/lib/common.yaml`, or any `evaluate.type: exit_code` state) routes an all-abstained harness run to `on_error`. The loop cannot tell "the harness ran fine and could not judge" from "the harness died".

No built-in loop currently invokes `ll-harness`, so this is latent rather than actively breaking a shipped loop. It becomes real as soon as a harness run is composed into a loop — which is the composition ENH-3185's exit code was added to enable.

## Expected Behavior

A parent FSM can route an abstained sub-invocation distinctly from an errored one, so that the abstention semantics established inside the FSM (hold, or a declared `on_cannot_judge` route) survive a process boundary.

## Motivation

Abstention is only useful if it propagates. Inside one FSM the grammar is now precise; the moment it crosses into a subprocess it is flattened back into the binary-plus-error shape the enhancement set out to replace. The same flattening will apply to any future tool that adopts the ABSTAIN exit code.

## Proposed Solution

Options, in rough order of blast radius — the implementer should pick one rather than treating this as a list of requirements:

1. **Map exit 3 to `cannot_judge` in the `exit_code` evaluator.** Most direct, and makes `on_cannot_judge` work uniformly for shell gates and judge gates. Risk: exit 3 is not reserved — an arbitrary command returning 3 would now emit an abstention verdict. Would need to be opt-in per state rather than a global remap.
2. **A dedicated `harness_exit` fragment / evaluator** that knows the `ll-harness` exit-code contract specifically. Narrower and safer; costs a new evaluator type.
3. **Allow numeric verdict keys in `route:`** so a state can write `route: {3: <state>}`. Most general, largest schema surface.

Whichever is chosen, document the mapping next to the ABSTAIN exit code so the two stay in sync.

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

Enables abstention-aware loop composition over `ll-harness`. No current built-in loop changes behavior.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.executor` section — the
  `exit_code` evaluator's verdict mapping this issue targets

## Status

**Open** | Created: 2026-08-16 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-08-16T23:29:37 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`
