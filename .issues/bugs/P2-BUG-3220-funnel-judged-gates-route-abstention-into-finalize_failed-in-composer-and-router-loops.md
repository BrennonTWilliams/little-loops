---
id: BUG-3220
type: BUG
title: Funnel judged gates route abstention into finalize_failed in composer and router
  loops
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:28:07Z'
parent: EPIC-3217
---

# BUG-3220: Funnel judged gates route abstention into finalize_failed in composer and router loops

## Summary

Ten LLM-judged gates in the built-in loops are *funnels*: `on_yes`, `on_no`, and `on_partial` all point at the same next state, because the LLM call produces an artifact (a plan, a classification, a score sheet) rather than judging a condition. The verdict is structurally irrelevant — every branch proceeds.

Since ENH-3185, abstention is the one verdict that does not follow the funnel. It escalates to `on_error` instead. For three of these gates, `on_error` is `finalize_failed`, so a state that structurally cannot fail today becomes a run-killer the first time a judge returns `cannot_judge`.

## Current Behavior

Funnel gates whose abstention path diverges from the funnel (`scripts/little_loops/loops/`):

| loop :: state | funnel target | abstention target |
|---|---|---|
| `goal-cluster` :: `dedup_and_batch` | `parse_batch_plan` | `finalize_failed` |
| `loop-composer` :: `decompose_goal` | `parse_plan` | `finalize_failed` |
| `loop-router` :: `classify_goal` | `route_branch_project` | `finalize_failed` |
| `goal-cluster` :: `propagate_context` | `save_hints` | `execute_cluster` |

The remaining six funnel gates — `goal-cluster::synthesize_cluster_result`, `loop-composer::review_chain`, `loop-router::score_project_loops`, `loop-router::score_builtin_loops`, `loop-router::review`, `migrate-sdk-version::classify_outcome` — happen to have an `on_error` that equals the funnel target, so they behave correctly today by coincidence rather than by declaration, and only after paying two holds first.

## Expected Behavior

A funnel gate funnels every verdict, abstention included. The downstream parse/consume state is already the component that handles a malformed or empty artifact; abstention should reach it the same way a `no` does, so the existing artifact-validation path gets to run instead of the loop failing upstream of it.

Where the parse state genuinely cannot tolerate an unproduced artifact, that is worth stating explicitly rather than inheriting a failure route written for infrastructure errors.

## Motivation

These four gates convert a working loop into a failing one on a verdict that carries no information about the artifact. The six coincidentally-correct gates additionally waste two re-runs of an LLM call per abstention. Both are cheap to fix and the fix is mechanical: one line per gate.

## Proposed Solution

Declare `on_cannot_judge: <funnel target>` on all ten gates. A declared route fires immediately with no hold (ENH-3185 precedence), which removes both the spurious failures and the wasted retries.

Doing this on the six coincidentally-correct gates as well is deliberate: it converts an accident of the error route into a stated intent, so a later change to `on_error` cannot silently reintroduce the divergence.

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

Removes three spurious run failures, one spurious re-execution branch, and up to two wasted LLM calls per abstention on six further gates. No behavior change on the non-abstention paths.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.executor` section — abstention-hold
  and escalation-to-`on_error` mechanics that route funnel gates into `finalize_failed`
- `docs/ARCHITECTURE.md` `## Extension Architecture & Event Flow` — FSM executor
  state-transition and event-emission model

## Status

**Open** | Created: 2026-08-16 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-16T23:29:37 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`
