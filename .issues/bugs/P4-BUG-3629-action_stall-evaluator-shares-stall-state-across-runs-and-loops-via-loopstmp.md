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

## Steps to Reproduce

1. Author a loop with a state using `evaluate: {type: action_stall, max_repeat: 1}` and the default `track: ["action"]`, with a constant action string.
2. Run it until the evaluator returns `no` (stalled); `.loops/tmp/ll-action-stall-<key>.count` now holds `>= max_repeat`.
3. Start a second run (same or a different loop with the same `track`) from the same working directory.
4. Observe: the first check on the new run returns `no` immediately (inherited snapshot and count) instead of the first-call `yes` with `stall_count` 0.

## Expected Behavior

Stall state is scoped per run instance and per state. A fresh run's first check always returns `yes` with `stall_count` 0.

## Motivation

`action_stall` is a documented non-LLM stall evaluator (used to satisfy MR-1 pairing for harness loops). Cross-run and cross-loop state leakage produces false stall verdicts that terminate healthy loops early, or hide real stalls when concurrent loops reset each other's counters. Fixing it keeps the evaluator trustworthy and aligns it with the per-run `run_dir` convention already used by `score_stall` / `open_question_stall`.

## Proposed Solution

Mirror the BUG-3627 approach:

- Derive `state_dir` from `context.context["run_dir"]` (the function already receives `context`), keying files `<state_name>-<md5(track)[:12]>`; fall back to the current `.loops/tmp` path only when no run context exists (`cli/loop/testing.py::cmd_test` passes a bare `InterpolationContext()`).
- Keep `details` keys (`stall_count`, `max_repeat`, `hash_changed`, `tracked_keys`) unchanged.
- Correct the docstring ("different states/loops maintain independent stall counters").
- Coordinate with BUG-3627 so both evaluators share one state-dir/key helper rather than duplicating it.

## Program Design

### Types

- `state_dir: Path | None` — per-run directory for snapshot/count files; `None` keeps the legacy `.loops/tmp` location
- `state_name: str` — state identifier used as the file-key prefix

### Signatures

- `evaluate_action_stall(track: list[str] | None = None, max_repeat: int = 2, context: InterpolationContext | None = None, state_dir: Path | None = None, state_name: str = "") -> EvaluationResult` — state files keyed `<state_name>-<md5(sorted track)[:12]>`; `details` keys unchanged

### Call Path

`evaluate` (`elif eval_type == "action_stall"` branch) -> `evaluate_action_stall(..., state_dir=<context.context["run_dir"]>)` -> `EvaluationResult` verdict `yes` / `no` -> state routing

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_action_stall()` (state path, docstring) and the `evaluate()` `action_stall` branch (~:2044) that derives `state_dir` from `context.context["run_dir"]`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/testing.py` — `cmd_test` passes a bare `InterpolationContext()` (must hit the `.loops/tmp` fallback)
- `scripts/little_loops/fsm/schema.py` — `track` / `max_repeat` evaluator fields (unchanged)

### Similar Patterns
- `evaluate_diff_stall()` (BUG-3627), `evaluate_score_stall`, `evaluate_open_question_stall` — `run_dir`-scoped state; share one state-dir/key helper with BUG-3627

### Tests
- `scripts/tests/test_fsm_evaluators.py` — action_stall test class (~:2118); its `clean_state_files` fixture relies on cwd `.loops/tmp`, add run_dir cases

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — `action_stall` section (~:465), document per-run scoping

### Configuration
- N/A

## Implementation Steps

1. Land or reuse the shared state-dir/key helper from BUG-3627, then add `state_dir` / `state_name` params to `evaluate_action_stall` and key files `<state_name>-<md5(track)[:12]>`.
2. Derive `state_dir` from `context.context["run_dir"]` in the `evaluate()` `action_stall` branch, falling back to `.loops/tmp` when absent; fix the docstring.
3. Update existing action_stall tests and add cases for sequential runs, same-`track` states in one run, shared parent/child `run_dir`, and missing `run_dir`.
4. Run `python -m pytest scripts/tests/test_fsm_evaluators.py` and `ll-loop validate` on a sample loop.

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
- `/ll:format-issue` - 2026-09-27T04:32:29 - `79da1788-ca93-44d9-aace-4d2e47c2197b.jsonl`
- `/ll:capture-issue` - 2026-09-27T04:30:00 - `1a55a3cf-a3d0-4f25-8b08-d58a3a50c7bc.jsonl`
