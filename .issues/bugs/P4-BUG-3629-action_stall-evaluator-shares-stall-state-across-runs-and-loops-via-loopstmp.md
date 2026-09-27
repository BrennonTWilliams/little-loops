---
id: BUG-3629
type: BUG
title: action_stall evaluator shares stall state across runs and loops via .loops/tmp
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T04:29:54Z'
---

# BUG-3629: action_stall evaluator shares stall state across runs and loops via .loops/tmp

## Summary

`evaluate_action_stall` (`little_loops.fsm.evaluators`, `evaluators.py` ~:837) persists its snapshot hash and stall counter in `.loops/tmp/ll-action-stall-<md5(sorted track keys)[:12]>.{txt,count}`, resolved from `Path.cwd()`. The key derives only from the tracked key names, and nothing resets it at run start, so state leaks across runs and across loops. Follow-up split out of BUG-3627 (`diff_stall` has the same defect and was scoped separately).

## Current Behavior

- Every loop using the default `track: ["action"]` shares `ll-action-stall-<key>.*`, so concurrent runs of different loops clobber each other's counters.
- A new run inherits the previous run's snapshot and count. If the prior run ended stalled and the new run's first tracked value hashes identically, the first check increments past `max_repeat` and returns `no` immediately instead of the first-call `yes`.
- The docstring claims "different states/loops maintain independent stall counters"; that holds only when their tracked key names differ, not their runs or states.
- No built-in loop under `scripts/little_loops/loops/` currently uses `action_stall` (grep finds none), so exposure is limited to user-authored loops. Hence P4.

## Expected Behavior

Stall state is scoped per run instance and per state. A fresh run's first check always returns `yes` with `stall_count` 0.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Mirror the BUG-3627 approach:

- Derive `state_dir` from `context.context["run_dir"]` (the function already receives `context`), keying files `<state_name>-<md5(track)[:12]>`; fall back to the current `.loops/tmp` path only when no run context exists (`cli/loop/testing.py::cmd_test` passes a bare `InterpolationContext()`).
- Keep `details` keys (`stall_count`, `max_repeat`, `hash_changed`, `tracked_keys`) unchanged.
- Correct the docstring ("different states/loops maintain independent stall counters").
- Coordinate with BUG-3627 so both evaluators share one state-dir/key helper rather than duplicating it.

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

- **Priority**: P4 — no built-in loop uses it; false stall verdicts only in user loops.
- **Effort**: Small.
- **Risk**: Low.

## Acceptance Criteria

- Two sequential runs do not share stall state; a fresh run's first check returns `yes`.
- Two states with the same `track` in one run, and a parent/child sharing `run_dir`, do not share stall state.
- Missing `run_dir` falls back to `.loops/tmp` without raising.
- Existing `action_stall` evaluator tests updated; new tests cover each case.

## Related

- BUG-3627 — same defect in `diff_stall`; source of this split.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P4


## Session Log
- `/ll:capture-issue` - 2026-09-27T04:30:00 - `1a55a3cf-a3d0-4f25-8b08-d58a3a50c7bc.jsonl`
