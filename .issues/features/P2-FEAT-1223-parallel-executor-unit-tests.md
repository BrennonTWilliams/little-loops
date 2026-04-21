---
discovered_date: "2026-04-21"
discovered_by: issue-size-review
parent_issue: FEAT-1201
size: Medium
---

# FEAT-1223: Parallel Executor Unit Tests (TestParallelExecution)

## Summary

Add `TestParallelExecution` class to `scripts/tests/test_fsm_executor.py` covering executor dispatch, result capture, and three-way routing for `parallel:` states.

## Parent Issue

Decomposed from FEAT-1201: Parallel State Executor, Integration, and Display Tests

## Use Case

**Who**: Developer closing out the parallel state feature after FEAT-1074/1075/1076 are complete

**Context**: Unit tests for `FSMExecutor`'s handling of `parallel:` states — verifying dispatch calls `_execute_parallel_state()`, captures are stored correctly, and all three route variants (`on_yes`, `on_partial`, `on_no`) resolve to the expected final states.

**Goal**: Add `TestParallelExecution` class between `TestSubLoopExecution` (ends at line 3956) and `TestRouteContext` (begins at line 3957) in `test_fsm_executor.py`.

**Outcome**: `python -m pytest scripts/tests/test_fsm_executor.py -x -k TestParallelExecution` passes green.

## Proposed Solution

Model after `TestSubLoopExecution` (spans lines 3634–3956).

Insert `TestParallelExecution` class between `TestSubLoopExecution` (ends at line 3956) and `TestRouteContext` (begins at line 3957):

- `test_parallel_state_dispatches()` — state with `parallel:` config calls `_execute_parallel_state()`
- `test_parallel_state_captures_merged()` — captures stored at `self.captured[state_name]["results"]`
- `test_parallel_state_routes_on_yes()` — route correctness for `on_yes` verdict
- `test_parallel_state_routes_on_partial()` — route correctness for `on_partial` verdict
- `test_parallel_state_routes_on_no()` — route correctness for `on_no` verdict

Pattern: write child YAML to `tmp_path / ".loops"`, run `FSMExecutor(parent_fsm, loops_dir=loops_dir)`, assert `result.final_state` and `executor.captured`.

For route variants, pair a success child with a failure child (the `on_no` branch is forced via a child YAML with `max_iterations: 1` and a non-terminating action — see `test_sub_loop_failure_routes_to_on_failure:3658`).

### Pre-implementation Checks

- Verify `scripts/little_loops/fsm/__init__.py` exports `ParallelStateConfig` and `ParallelRunner` (FEAT-1074/1075 deliverables)
- Verify exact capture key naming from FEAT-1076's landed implementation (may not be `"results"`)
- Verify `ParallelStateConfig` field names match FEAT-1074's schema

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_executor.py` — Add `TestParallelExecution` class (between `TestSubLoopExecution` ending at line 3956 and `TestRouteContext` at line 3957)

### Dependent Files (all must exist before implementation)
- `scripts/little_loops/fsm/parallel_runner.py` — FEAT-1075
- `scripts/little_loops/fsm/executor.py` — `_execute_parallel_state()` — FEAT-1076
- `scripts/little_loops/fsm/schema.py` — `ParallelStateConfig`, `StateConfig.parallel` — FEAT-1074
- `scripts/little_loops/fsm/__init__.py` — must export `ParallelStateConfig` and `ParallelRunner`

### Similar Patterns
- `scripts/tests/test_fsm_executor.py:3634` — `TestSubLoopExecution` — model after this

## Dependencies

- **FEAT-1074** must be complete (schema, validation)
- **FEAT-1075** must be complete (ParallelRunner)
- **FEAT-1076** must be complete (`_execute_parallel_state()`)

## Acceptance Criteria

- `python -m pytest scripts/tests/test_fsm_executor.py -x -k TestParallelExecution` passes green
- `TestParallelExecution` covers dispatch, captures, and all three route variants (`on_yes`, `on_partial`, `on_no`)
- No regressions in existing `TestSubLoopExecution` tests

## Labels

`fsm`, `parallel`, `tests`

## Session Log
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/258256f7-974b-4688-b813-9928466b24ec.jsonl`
