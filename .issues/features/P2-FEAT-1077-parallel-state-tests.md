---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1072
confidence_score: 90
outcome_confidence: 93
---

# FEAT-1077: Parallel State Tests

## Summary

Write all tests for the `parallel:` state type: executor dispatch, schema validation, validation rules, `ParallelRunner` unit tests, fixture YAML, fuzz coverage extension, and display badge test.

## Parent Issue

Decomposed from FEAT-1072: Add `parallel:` State Type to FSM for Concurrent Sub-Loop Fan-Out

## Use Case

**Who**: Developer completing the `parallel:` state type implementation (FEAT-1074/1075/1076)

**Context**: After `ParallelRunner`, schema, and executor dispatch are implemented, test coverage must be in place before the feature can merge.

**Goal**: Write comprehensive tests covering `ParallelRunner` behavior, FSM schema round-trips, validation rule enforcement, fixture loading, fuzz coverage, and display badges for `parallel:` states.

**Outcome**: All new tests pass, the regression suite stays green, and the `parallel:` feature is fully covered by the test suite.

## Current Behavior

No tests exist for the `parallel:` state type. `ParallelRunner`, `ParallelStateConfig`, and the executor dispatch path (`_execute_parallel_state()`) have no test coverage. Schema validation and mutual exclusion rules for `parallel:` states are unchecked.

## Expected Behavior

A full test suite covers the `parallel:` state type:
- `scripts/tests/fsm/test_parallel_runner.py` unit-tests `ParallelRunner` (thread mode, worktree mode, fail_fast, edge cases)
- `test_fsm_executor.py` covers parallel dispatch and route correctness
- `test_fsm_schema.py` covers `ParallelStateConfig` round-trips
- `test_fsm_validation.py` covers mutual exclusion and invalid field values
- `parallel-loop.yaml` fixture round-trips cleanly
- Fuzz strategy includes `parallel` key
- Display badge test added for `parallel:` state

## Motivation

This feature would:
- Ensure correctness of the `parallel:` state type implementation (FEAT-1074/1075/1076) before merging
- Prevent regressions as the FSM evolves — parallel state is complex (threading, worktree isolation, fail modes)
- Required for FEAT-1072 to be complete: tests are the final gating deliverable

## Proposed Solution

### New test file: scripts/tests/test_parallel_runner.py

Create `scripts/tests/test_parallel_runner.py` (flat directory — all FSM tests live directly under `scripts/tests/`, no `fsm/` subdirectory exists). Unit tests for `ParallelRunner` with mock `FSMExecutor` workers:

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

**test_fsm_schema.py** (not `test_fsm_validation.py`) — Add mutual exclusion cases as a new class `TestParallelMutualExclusion`, following the existing `test_loop_and_action_mutual_exclusion` pattern at `test_fsm_schema.py:1722`:

- `parallel` + `action` → validation error
- `parallel` + `loop` → validation error
- `parallel` + `next` → validation error
- `max_workers: 0` → validation error
- `isolation: "invalid"` → validation error
- `fail_mode: "invalid"` → validation error

**test_fsm_validation.py** — `test_fsm_validation.py:18` only has `TestExtraRoutesReachability`; mutual exclusion tests don't belong here. Add one test that a `parallel:` state with routing does NOT trigger the no-transition guard (the guard at `validation.py:271` gains `and not has_parallel` as part of FEAT-1074).

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

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_executor.py` — Add `TestParallelExecution` class (new class, not extending `TestSubLoopExecution`) modeled after `TestSubLoopExecution:3472`
- `scripts/tests/test_fsm_schema.py` — Add `TestParallelStateConfig` and `TestParallelMutualExclusion` classes
- `scripts/tests/test_fsm_validation.py` — Add one test that `parallel:` state doesn't trigger no-transition guard
- `scripts/tests/test_fsm_schema_fuzz.py` — Add `parallel` to `malformed_state_config` strategy at line 134 (after line 174, before the `unexpected_*` block)
- `scripts/tests/test_ll_loop_display.py` — Add parallel badge test to `TestStateBadges:2225` (requires `_PARALLEL_BADGE` from FEAT-1078)

### Files to Create
- `scripts/tests/test_parallel_runner.py` — New unit tests for `ParallelRunner` (flat in `scripts/tests/`, no subdirectory)
- `scripts/tests/fixtures/fsm/parallel-loop.yaml` — New fixture

### Existing Parallel Coverage
- `scripts/tests/test_parallel_types.py` — Already covers parallel type definitions; `test_parallel_runner.py` must not duplicate this

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/parallel_runner.py` — Implementation under test (FEAT-1075; does not exist yet)
- `scripts/little_loops/fsm/executor.py:383` — `_execute_parallel_state()` under test (FEAT-1076; dispatch inserts after `executor.py:402`)
- `scripts/little_loops/fsm/schema.py:180` — `ParallelStateConfig`, `StateConfig` under test (FEAT-1074; `parallel` field added after `schema.py:233`)
- `scripts/little_loops/fsm/validation.py:271` — No-transition guard; gains `and not has_parallel` (FEAT-1074); one validation test covers this
- `scripts/little_loops/cli/loop/layout.py` — Must export `_PARALLEL_BADGE` constant (FEAT-1078) before badge test compiles

### Similar Patterns
- `scripts/tests/test_fsm_executor.py:3472` — `TestSubLoopExecution` — Model `TestParallelExecution` after this class; use write-YAML-to-`tmp_path / ".loops"` pattern, `FSMExecutor(parent_fsm, loops_dir=loops_dir)`, assert `result.final_state` and `executor.captured`
- `scripts/tests/test_fsm_schema.py:1722` — `test_loop_and_action_mutual_exclusion` — Template for `TestParallelMutualExclusion`; constructs `FSMLoop` inline, calls `validate_fsm()`, asserts on error message strings
- `scripts/tests/test_ll_loop_display.py:2255` — `test_get_state_badge_sub_loop` — Template for parallel badge test; constructs `StateConfig(parallel=...)` inline, asserts `_get_state_badge(state) == _PARALLEL_BADGE`
- `scripts/tests/test_fsm_schema_fuzz.py:174` — End of `route` block in `malformed_state_config`; add `parallel` block after this line, before `unexpected_*` block at line 175
- `scripts/tests/test_fsm_schema.py:1673` — `TestSubLoopStateConfig` — Round-trip pattern for `TestParallelStateConfig`; tests `to_dict()` includes/excludes fields, `from_dict()` applies defaults

### Tests
- N/A — This issue IS the test implementation

### Regression Surfaces

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema.py:636` (`TestFSMValidation`) — `len(error_list) == 0` assertions on minimal valid FSMs; `ParallelStateConfig` added to `StateConfig` must not emit validation errors for non-parallel loops
- `scripts/tests/test_ll_loop_display.py:2260–2263` — sub-loop badge precedence assertions (`loop > action_type`); the position where FEAT-1078 inserts the `parallel:` check in `_get_state_badge()` must not break these existing priority tests
- `scripts/tests/test_ll_loop_display.py:2328–2334` — `loop > route` badge priority assertions; same concern as above

### Documentation
- N/A

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml:106` — `--strict-markers` is active; any `@pytest.mark.*` decoration on new test methods must be pre-registered in `[tool.pytest.ini_options].markers` (currently declared: `integration`, `slow`). Do not introduce new markers.
- `scripts/pyproject.toml:133` — `fail_under = 80` coverage gate; new implementation files (`parallel_runner.py`, executor dispatch path, schema `parallel` field, layout badge) count against coverage. New tests must exercise those paths to keep the gate green.

## Implementation Steps

1. Create `scripts/tests/test_parallel_runner.py` (flat in `scripts/tests/`, not a subdirectory) with `ParallelRunner` unit tests; mock `FSMExecutor` workers; assert on `ParallelResult` fields; worker success = `terminated_by == "terminal" and final_state == "done"`
2. Add new `TestParallelExecution` class to `test_fsm_executor.py` (after `TestSubLoopExecution:3472`); write child YAML to `tmp_path / ".loops"`, run `FSMExecutor`, assert routes and `captured[state_name]["results"]`
3. Add `TestParallelStateConfig` and `TestParallelMutualExclusion` classes to `test_fsm_schema.py` (following `TestSubLoopStateConfig:1673` and `test_loop_and_action_mutual_exclusion:1722` patterns)
4. Add one `parallel:` no-transition-guard test to `test_fsm_validation.py` (verifies `parallel:` states are not falsely flagged)
5. Create `scripts/tests/fixtures/fsm/parallel-loop.yaml` and add an explicit test method to `test_fsm_schema.py:TestLoadAndValidate` that references `fsm_fixtures / "parallel-loop.yaml"` by name — no auto-discovery occurs for files in `fixtures/fsm/`; the fixture must be explicitly named in a test method
6. Add `parallel` malformed key to `malformed_state_config` strategy in `test_fsm_schema_fuzz.py` after line 174 (before `unexpected_*` block)
7. Add parallel badge test to `test_ll_loop_display.py:TestStateBadges` — requires FEAT-1078 to export `_PARALLEL_BADGE`; implement this step last
8. Run full test suite: `python -m pytest scripts/tests/test_parallel_runner.py scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_validation.py scripts/tests/test_ll_loop_display.py -x`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Verify `test_fsm_schema.py:TestLoadAndValidate` has an explicit test method for `parallel-loop.yaml` (no glob discovery — the fixture file must be named directly in a test method, e.g., `fsm_fixtures / "parallel-loop.yaml"`)
10. Use only pre-declared pytest markers (`integration`, `slow`); `pyproject.toml:106` `--strict-markers` causes collection failure for any undeclared marker
11. Before merging, run `python -m pytest scripts/tests/ --cov --cov-fail-under=80` to confirm the `fail_under = 80` gate passes with new implementation files in scope

## Files to Create/Modify

- `scripts/tests/test_parallel_runner.py` — New unit tests for `ParallelRunner` (flat in `scripts/tests/`)
- `scripts/tests/test_fsm_executor.py` — Add new `TestParallelExecution` class
- `scripts/tests/test_fsm_schema.py` — Add `TestParallelStateConfig` and `TestParallelMutualExclusion` classes
- `scripts/tests/test_fsm_validation.py` — Add one `parallel:` no-transition-guard test
- `scripts/tests/fixtures/fsm/parallel-loop.yaml` — New fixture
- `scripts/tests/test_fsm_schema_fuzz.py` — Add `parallel` to `malformed_state_config` strategy at line 174
- `scripts/tests/test_ll_loop_display.py` — Add parallel badge test to `TestStateBadges` (last step; requires FEAT-1078)

## Implementation Notes

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **ParallelRunner.run() signature**: `run(items: list[str], loop_name: str, config: ParallelStateConfig, parent_context: dict | None = None) -> ParallelResult`
- **Worker success condition**: `child_result.terminated_by == "terminal" and child_result.final_state == "done"` (mirrors `_execute_sub_loop()` at `executor.py:354–361`)
- **Captures storage**: `self.captured[self.current_state] = {"results": result.all_captures}` (confirmed from executor dispatch design)
- **Routing**: `_route()` at `executor.py:713–762` already handles `"yes"/"partial"/"no"` at lines 747–753 — `_execute_parallel_state()` calls `self._route(state, result.verdict, ctx)` directly
- **`test_fsm_validation.py` scope**: File currently has only 67 lines with one class (`TestExtraRoutesReachability`). Mutual exclusion tests go in `test_fsm_schema.py` (where `test_loop_and_action_mutual_exclusion:1722` lives). The single validation test added here is for the no-transition guard at `validation.py:271`.
- **`_PARALLEL_BADGE` gate**: Badge test imports `_PARALLEL_BADGE` from `little_loops.cli.loop.layout` — this constant does not exist until FEAT-1078. Implement badge test last and guard with a skip if not yet available.
- **`test_parallel_types.py`**: Already exists at `scripts/tests/test_parallel_types.py`; review its contents before writing `test_parallel_runner.py` to avoid duplicating `ParallelResult` field assertions. Confirmed: it covers `little_loops.parallel.types` (the ll-parallel orchestrator layer), NOT `little_loops.fsm` types — no duplication risk with `ParallelStateConfig` or FSM `ParallelResult`.
- **`fsm_fixtures` fixture**: Defined at `test_fsm_schema.py:34` as `Path(__file__).parent / "fixtures" / "fsm"`. The parallel-loop.yaml test method in `TestLoadAndValidate:1397` must accept `fsm_fixtures: Path` as a parameter and follow the `test_load_valid_yaml()` pattern at line 1400 (e.g., `fixture_path = fsm_fixtures / "parallel-loop.yaml"`).
- **Fuzz block code pattern**: The `parallel` block to insert in `malformed_state_config` after line 173 (end of `route` block), before line 175 (`# Add unexpected fields`):
  ```python
  # Add parallel config
  if draw(st.booleans()):
      state["parallel"] = draw(
          st.one_of(
              st.fixed_dictionaries({
                  "items": st.text(min_size=1, max_size=100),
                  "loop": st.text(min_size=1, max_size=50),
              }),
              st.integers(),
              st.text(),
              st.none(),
          )
      )
  ```
- **Implementation status of dependencies**: As of this refinement pass, `parallel_runner.py`, `ParallelStateConfig` in schema.py, `_execute_parallel_state()` in executor.py, and `_PARALLEL_BADGE` in layout.py all do NOT yet exist. FEAT-1074, FEAT-1075, FEAT-1076, and FEAT-1078 must complete first — tests in this issue will fail to import until those implementations land.

## Dependencies

- FEAT-1074, FEAT-1075, FEAT-1076 must be complete (tests exercise those implementations)

## Acceptance Criteria

- All new tests pass: `python -m pytest scripts/tests/test_parallel_runner.py scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_validation.py scripts/tests/test_ll_loop_display.py -x`
- `test_fsm_schema.py:TestFSMValidation` — no regressions in existing error-count assertions
- `test_fsm_fragments.py` + `test_builtin_loops.py` — all 33 built-in loops still pass validation
- `parallel-loop.yaml` fixture round-trips without validation errors
- Fuzz test includes `parallel` key in malformed strategy

## API/Interface

N/A - No public API changes (test files only)

## Impact

- **Priority**: P2 - Required gate for FEAT-1072 (parent) completion; unblocks merging the parallel state feature
- **Effort**: Medium - Multiple test files across executor, schema, validation, fuzz, and display; patterns are well-established in the existing test suite
- **Risk**: Low - Test-only changes; no production code modified
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `tests`

---

## Session Log
- `/ll:confidence-check` - 2026-04-12T23:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9da6eb97-069e-44c5-91dc-b06213bbdb44.jsonl`
- `/ll:refine-issue` - 2026-04-12T22:32:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1a0289e-787a-444b-9e0f-8948f014d350.jsonl`
- `/ll:wire-issue` - 2026-04-12T22:26:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/40ba99b1-af2b-4221-bf0c-5829fac63188.jsonl`
- `/ll:refine-issue` - 2026-04-12T22:21:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c0de4a6f-059b-48e7-a248-7017de5869a3.jsonl`
- `/ll:format-issue` - 2026-04-12T22:13:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0a3bd623-b6f1-4633-9128-0ace3241e1e4.jsonl`
- `/ll:issue-size-review` - 2026-04-12T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8e4e49c-4e79-4270-9839-915fa38b03f2.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2
