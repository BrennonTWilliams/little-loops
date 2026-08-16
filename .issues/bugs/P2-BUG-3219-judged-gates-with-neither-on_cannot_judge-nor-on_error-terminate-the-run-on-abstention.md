---
id: BUG-3219
type: BUG
title: Judged gates with neither on_cannot_judge nor on_error terminate the run on
  abstention
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:27:46Z'
parent: EPIC-3217
---

# BUG-3219: Judged gates with neither on_cannot_judge nor on_error terminate the run on abstention

## Summary

Thirteen LLM-judged gates in the built-in loops declare neither `on_cannot_judge` nor `on_error`. When such a gate abstains, `FSMExecutor` holds the state twice and then calls `_abstention_fallback()`, which returns `None` because there is no error route to resolve — and `_route()` returning `None` terminates the run via `_finish("error", "No valid transition")`.

ENH-3185 accepted this outcome as "loud rather than silent", and as a default that is correct. But three of the thirteen are the `harness-*` templates that `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` tells users to copy, so the shape propagates into every user-authored harness.

## Current Behavior

Gates with neither route (`scripts/little_loops/loops/`):

| loop | state |
|---|---|
| `harness-single-shot.yaml` | `check_semantic` |
| `harness-multi-item.yaml` | `check_semantic`, `check_skill` |
| `harness-plan-research-implement-report.yaml` | `check_semantic` |
| `rn-build.yaml` | `check_substrate` |
| `rn-plan.yaml` | `check_substrate` |
| `integrate-sdk.yaml` | `enumerate_from_code`, `enumerate_from_docs` |
| `adopt-third-party-api.yaml` | `enumerate` |
| `assumption-firewall.yaml` | `extract_assumptions` |
| `dataset-curation.yaml` | `validate_schema` |
| `incremental-refactor.yaml` | `check_complete` |
| `loop-specialist-eval.yaml` | `check_skill` |

A run reaching any of these and abstaining dies after three attempts with "No valid transition".

There is a cost dimension as well. `_route_abstention_hold()` re-enters the *state*, not just the evaluator, so the state's action re-runs on each hold. For `check_skill` — an agentic user-simulation gate documented at 30–300s — an undeclared abstention buys two full re-simulations before the run terminates anyway.

## Expected Behavior

Each of these gates routes abstention somewhere deliberate. The right destination is per-gate and is not uniformly "retry the work":

- `check_semantic` in the harness templates: abstention means the judge could not see the evidence. The productive route is a state that *produces* the missing evidence (re-run with artifact capture, widen the diff scope), not `execute`, which redoes work the judge already could not observe.
- `rn-build` / `rn-plan` `check_substrate`: "does the substrate exist" is deterministically probe-able. Abstention should run a probe rather than guess `design_artifacts`.
- `loop-specialist-eval` / `harness-multi-item` `check_skill`: declare an explicit route so the expensive hold is skipped entirely.
- The extraction-shaped gates (`enumerate*`, `extract_assumptions`, `validate_schema`, `check_complete`) may legitimately funnel abstention to the same target as their other verdicts — see the sibling funnel-gate issue for that pattern.

## Motivation

The templates are the propagation vector. Fixing the three `harness-*` files stops the defect from being copied forward; fixing the remaining ten removes latent run-terminations from loops that are shipped as working.

## Proposed Solution

Work gate by gate rather than applying one blanket route. For each, decide what unobservability means at that point in the loop, declare `on_cannot_judge` accordingly, and where the answer is genuinely "we cannot proceed", route to a failure-shaped terminal so the run reports `failed` rather than dying on an unroutable verdict.

Update the harness templates' inline comments to show the `on_cannot_judge` line alongside the existing `on_partial` self-hold, since those comments are the de facto documentation for the pattern.

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

Removes 13 latent run-terminations and stops the no-route shape from propagating into user harnesses via the documented templates.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.executor` / `little_loops.fsm.validation`
  sections — `_abstention_fallback()` semantics and the MR rule set
- `.claude/CLAUDE.md` `## Loop Authoring` — meta-loop shape rules referenced by
  `ll-loop validate`, and the harness-template guide these gates propagate into

## Status

**Open** | Created: 2026-08-16 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-16T23:29:36 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`
