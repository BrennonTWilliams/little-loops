---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1072
---

# FEAT-1077: Parallel State Tests

## Summary

Write all tests for the `parallel:` state type: executor dispatch, schema validation, validation rules, `ParallelRunner` unit tests, fixture YAML, fuzz coverage extension, and display badge test.

## Parent Issue

Decomposed from FEAT-1072: Add `parallel:` State Type to FSM for Concurrent Sub-Loop Fan-Out

## Proposed Solution

### New test file: scripts/tests/fsm/test_parallel_runner.py

Create `scripts/tests/fsm/` directory first (does not exist). Unit tests for `ParallelRunner` with mock `FSMExecutor` workers:

- Thread mode: mock sub-loop runs, verify captures collected, verdict derived correctly
- Thread mode `fail_fast`: verify remaining futures cancelled on first failure
- Worktree mode: mock worktree setup/teardown, verify merge-back called
- `context_passthrough: true`: verify parent context passed to each worker
- Edge: 0 items → immediate `ParallelResult(succeeded=[], failed=[], all_captures=[], verdict="yes")`
- Edge: 1 item fails of 1 → `verdict="no"`

### Existing test files to extend

**test_fsm_executor.py** — Add parallel state dispatch tests to `TestSubLoopExecution` class at line 3472:

- `test_parallel_state_dispatches()` — state with `parallel:` config calls `_execute_parallel_state()`
- `test_parallel_state_captures_merged()` — captures stored at `self.captured[state_name]["results"]`
- `test_parallel_state_routes_on_yes()`, `_on_partial()`, `_on_no()` — route correctness

**test_fsm_schema.py** — Add `TestParallelStateConfig` class:

- Round-trip `to_dict()` / `from_dict()` with all fields
- `from_dict()` with only required fields (defaults applied)
- `StateConfig` with `parallel:` serializes `parallel` key; without, key absent

**test_fsm_validation.py** — Add mutual exclusion cases:

- `parallel` + `action` → validation error
- `parallel` + `loop` → validation error
- `parallel` + `next` → validation error
- `max_workers: 0` → validation error
- `isolation: "invalid"` → validation error
- `fail_mode: "invalid"` → validation error

### New fixture: scripts/tests/fixtures/fsm/parallel-loop.yaml

Minimal `parallel:` state for `TestLoadAndValidate`-style round-trip tests:

```yaml
states:
  fan_out:
    parallel:
      items: "${captured.queue.output}"
      loop: refine-to-ready-issue
      max_workers: 2
      isolation: thread
      fail_mode: collect
      context_passthrough: false
    route:
      on_yes: done
      on_partial: done
      on_no: done
  done:
    next: ~
```

### Fuzz and display tests

**test_fsm_schema_fuzz.py:134** — Add `parallel` key to `malformed_state_config` hypothesis strategy so `StateConfig.from_dict()` fuzz coverage includes malformed `parallel:` inputs.

**test_ll_loop_display.py:TestStateBadges** — Add test for `parallel:` state badge modeled after `test_get_state_badge_sub_loop` at line 2255.

## Files to Create/Modify

- `scripts/tests/fsm/` — Create directory
- `scripts/tests/fsm/test_parallel_runner.py` — New unit tests for `ParallelRunner`
- `scripts/tests/test_fsm_executor.py` — Add parallel dispatch tests to `TestSubLoopExecution`
- `scripts/tests/test_fsm_schema.py` — Add `TestParallelStateConfig`
- `scripts/tests/test_fsm_validation.py` — Add mutual exclusion tests
- `scripts/tests/fixtures/fsm/parallel-loop.yaml` — New fixture
- `scripts/tests/test_fsm_schema_fuzz.py` — Add `parallel` to fuzz strategy at line 134
- `scripts/tests/test_ll_loop_display.py` — Add parallel badge test to `TestStateBadges`

## Dependencies

- FEAT-1074, FEAT-1075, FEAT-1076 must be complete (tests exercise those implementations)

## Acceptance Criteria

- All new tests pass: `python -m pytest scripts/tests/fsm/ scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_validation.py scripts/tests/test_ll_loop_display.py -x`
- `test_fsm_schema.py:TestFSMValidation` — no regressions in existing error-count assertions
- `test_fsm_fragments.py` + `test_builtin_loops.py` — all 33 built-in loops still pass validation
- `parallel-loop.yaml` fixture round-trips without validation errors
- Fuzz test includes `parallel` key in malformed strategy

## Labels

`fsm`, `parallel`, `tests`

---

## Session Log
- `/ll:issue-size-review` - 2026-04-12T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8e4e49c-4e79-4270-9839-915fa38b03f2.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2
