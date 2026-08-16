---
id: BUG-3218
type: BUG
title: sprint-build-and-validate commits when the conflict audit abstains
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:27:23Z'
parent: EPIC-3217
---

# BUG-3218: sprint-build-and-validate commits when the conflict audit abstains

## Summary

`sprint-build-and-validate.yaml`'s `audit_conflicts` gate is an `llm_structured` judge with `on_error: commit`. Since ENH-3185, a judge that cannot evaluate the conflict audit from the evidence available returns `cannot_judge`; with no `on_cannot_judge` declared, `FSMExecutor` holds the state twice and then escalates to the `on_error` fallback — which is `commit`. An audit that could not be performed therefore produces a commit, exactly as if it had returned `yes`.

This is the fabricated-pass failure mode ENH-3185 was written to remove, relocated from the judge's verdict into the loop's route table.

## Current Behavior

`scripts/little_loops/loops/sprint-build-and-validate.yaml`, state `audit_conflicts`:

- `on_yes: commit`
- `on_no: audit_conflicts_retry`
- `on_partial: audit_conflicts_retry`
- `on_error: commit`

An abstention takes the `on_error` branch (`executor.py:2669` `_abstention_fallback`) after `_ABSTENTION_HOLD_CAP = 2` holds, landing on `commit`. Note the two holds re-enter the state and re-run its action, so the audit is attempted three times before the loop gives up and commits anyway.

## Expected Behavior

An abstained conflict audit must not reach `commit`. Abstention here means "the audit could not be performed", which is a reason to retry with better evidence or to stop — never a reason to proceed as though no conflicts exist.

The `on_error: commit` route should also be re-examined on its own merits: it was presumably written to keep an infrastructure failure from stalling a sprint, but it has the same fail-open shape for genuine errors.

## Motivation

This gate guards a commit. A silent fail-open on an unobservable audit is the highest-severity instance of the abstention gap found in the built-in loops, and it is the only one where the wrong route writes to the repository.

## Proposed Solution

Declare `on_cannot_judge: audit_conflicts_retry` so an abstention routes immediately (a declared route fires with no hold, per the ENH-3185 precedence) into the existing retry path, which already exists for `no`/`partial`.

If the retry path can itself abstain indefinitely, pair it with the state's `max_retries` / `on_retry_exhausted` machinery so exhaustion terminates in a failure-shaped state rather than in `commit`.

Separately, evaluate whether `on_error: commit` should become a failure-shaped terminal.

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

Removes a fail-open path to `commit` on an unobservable conflict audit.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.executor` / `little_loops.fsm.validation`
  sections — abstention-fallback routing and MR-4's `on_yes`-without-route rule
- `docs/ARCHITECTURE.md` `## Extension Architecture & Event Flow` — FSM executor
  role and event emission for state transitions

## Status

**Open** | Created: 2026-08-16 | Priority: P1


## Session Log
- `/ll:capture-issue` - 2026-08-16T23:29:36 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`
