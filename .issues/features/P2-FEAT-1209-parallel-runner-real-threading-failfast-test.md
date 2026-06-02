---
discovered_date: "2026-04-20"
discovered_by: issue-size-review

size: Small
confidence_score: 90
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
parent: FEAT-1206
status: deferred
---

# FEAT-1209: TestParallelRunnerRealThreading — Fail Fast Cancellation Test

## Summary

Add `test_real_threads_fail_fast_cancels_pending` to `TestParallelRunnerRealThreading` in `scripts/tests/test_parallel_runner.py`.

## Parent Issue

Decomposed from FEAT-1206: TestParallelRunnerRealThreading — Fail Fast + Timeout Tests

## Use Case

**Who**: Developer completing FEAT-1075 (`ParallelRunner` implementation)

**Context**: After FEAT-1205 adds the `TestParallelRunnerRealThreading` class (or this issue creates it), this adds the fail_fast cancellation test to verify that once one worker fails, pending workers are cancelled and fewer than all workers start.

**Goal**: Add 1 real-threading test to `TestParallelRunnerRealThreading` in `scripts/tests/test_parallel_runner.py`. Class-level `@pytest.mark.integration` must be present (added by FEAT-1205 or this issue if FEAT-1205 runs first). MUST run in default CI — NOT gated behind `@pytest.mark.slow`.

**Outcome**: `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_fail_fast_cancels_pending -x` passes green.

## Proposed Solution

### Add to existing file: scripts/tests/test_parallel_runner.py

Test goes inside `TestParallelRunnerRealThreading` (class-level `@pytest.mark.integration`). Uses real `ThreadPoolExecutor` (no mocks on executor layer).

**`test_real_threads_fail_fast_cancels_pending`** — 10 items, `fail_mode: "fail_fast"`, item 2 fails. Track how many worker bodies actually started (shared counter under `threading.Lock`). Assert counter < 10.

Implementation recipe:
```python
lock = threading.Lock()
started_count = [0]  # list-wrapping matches codebase convention (test_git_lock.py:462-479)

def worker_body(item, context):
    with lock:
        started_count[0] += 1
    if item == items[2]:
        raise RuntimeError("forced failure")
    time.sleep(0.1)
```

Assert: `started_count[0] < 10` after run completes.

### Implementation Notes

- Apply `@pytest.mark.integration` at **class** level (NOT module-level `pytestmark`). If FEAT-1205 already created the class with the marker, just add the method.
- `integration` marker runs in default CI (`scripts/pyproject.toml:113-116`). Do NOT use `@pytest.mark.slow`.
- Use mutable list `counter = [0]` rather than `nonlocal` — matches `test_git_lock.py:462-479` convention.
- Test should complete in < 5s total.

## Integration Map

### Files to Modify
- `scripts/tests/test_parallel_runner.py` — Add 1 test to `TestParallelRunnerRealThreading`

### Dependent Files (under test / needed first)
- `scripts/little_loops/fsm/parallel_runner.py` — Implementation under test (FEAT-1075). **Does not yet exist as of 2026-04-20.**
- `scripts/little_loops/fsm/schema.py` — must gain `ParallelStateConfig` with `fail_mode` field (FEAT-1074). **No parallel-related symbols present yet as of 2026-04-20** (`fail_mode`, `ParallelState*` grep returns 0 matches).
- `scripts/little_loops/fsm/__init__.py` — must export `ParallelRunner`, `ParallelItemResult`, `ParallelResult` (FEAT-1075). **Currently exports no parallel symbols.**
- `scripts/tests/test_parallel_runner.py` — created by FEAT-1202. **Does not yet exist.**
- FEAT-1205 should be complete (creates `TestParallelRunnerRealThreading` class with class-level `@pytest.mark.integration` marker)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-04-20:_

- Sibling module `scripts/little_loops/fsm/runners.py` already exists (distinct from the new `parallel_runner.py`); confirm the naming convention with FEAT-1075 owner before assuming a new file vs. extension.
- FSM package currently contains 14 modules (`executor`, `runners`, `persistence`, `schema`, `validation`, `interpolation`, `signal_detector`, `handoff_handler`, `concurrency`, `evaluators`, `types`, `fragments`, `rate_limit_circuit`, `__init__`). None reference `ParallelRunner`.
- `@pytest.mark.integration` is registered in `scripts/pyproject.toml:113-116` (default-CI marker, not `slow`) — confirmed.
- Only one existing class-level `integration` marker usage in repo: `scripts/tests/test_goals_parser.py:437` — the template for placement.

### Similar Patterns (copy from)
- `scripts/tests/test_git_lock.py:462-479` (`test_no_deadlock_with_many_threads`) — canonical `counter = [0]` + `counter_lock = threading.Lock()` shared-counter pattern. Use this for the `started_count` bookkeeping. (Note: this test asserts equality `counter[0] == 20`; for this issue use an inequality — see next bullet.)
- `scripts/tests/test_hooks_integration.py:1041-1047` — real `ThreadPoolExecutor` with inequality count assertion (`assert denied_count >= 4, f"..."`). Use this pattern for `assert started_count[0] < 10, f"..."`.
- `scripts/tests/test_goals_parser.py:437` — the only existing class-level `@pytest.mark.integration` example in the repo (`@pytest.mark.integration` above `class TestIntegration:`). Follow this exact placement.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml:113-116` — `integration` marker is registered under `[tool.pytest.ini_options] markers`; no modification needed. `--strict-markers` (line 107) means any unregistered marker aborts collection.
- `scripts/pyproject.toml:134` — `fail_under = 80` coverage gate applies to `little_loops/`. FEAT-1209 fills the `fail_fast` branch of `parallel_runner.py`; without this test, that branch will be uncovered and CI coverage will fail once FEAT-1075 ships.
- `scripts/tests/conftest.py` — no `ParallelRunner`, `ParallelStateConfig`, or parallel fixtures defined. Test must construct all objects inline (no fixture injection available).

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_parallel_runner.py` — target file (new test method). If `TestParallelRunnerRealThreading` does not yet exist when this issue is picked up (FEAT-1205 not yet landed), create the class with `@pytest.mark.integration` before adding the method — follow `scripts/tests/test_goals_parser.py:437` placement.

## Dependencies

- **FEAT-1074** must be complete (`ParallelStateConfig` in `schema.py`)
- **FEAT-1075** must be complete (`ParallelRunner` implementation + `fsm/__init__.py` exports)
- **FEAT-1202** must be complete (creates `test_parallel_runner.py`)
- **FEAT-1205** should be complete (creates `TestParallelRunnerRealThreading` class with marker)
- **FEAT-1210** (`P2-FEAT-1210-parallel-runner-real-threading-timeout-test.md`) adds a second method to the same `TestParallelRunnerRealThreading` class; land order matters to avoid merge conflicts. FEAT-1210's description notes it depends on FEAT-1209 or FEAT-1205 creating the class first.

## Acceptance Criteria

- `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_fail_fast_cancels_pending -x` passes green
- Test runs in default CI (class-level `@pytest.mark.integration`, no `@pytest.mark.slow`)
- Asserts fewer than 10 workers started (verifying fail_fast cancels pending)

## Labels

`fsm`, `parallel`, `tests`, `integration`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-20_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 100/100 → HIGH CONFIDENCE

### Concerns
- FEAT-1074 still in `.issues/features/` — `ParallelStateConfig` + `fail_mode` not yet in `schema.py`; test cannot exercise `fail_mode` without it.
- FEAT-1075 still in `.issues/features/` — `ParallelRunner` does not exist in `scripts/little_loops/fsm/`; acceptance criterion ("passes green") cannot be met without it.
- FEAT-1202 still in `.issues/features/` — `scripts/tests/test_parallel_runner.py` does not exist on disk, despite FEAT-1205 being in `completed/`. FEAT-1205 appears to have been closed as a tracking action rather than an implementation action; the test class it was supposed to create is absent.
- The test can be authored now (TDD) but will not pass green until FEAT-1074, FEAT-1075, and FEAT-1202 are implemented.

## Session Log
- `/ll:refine-issue` - 2026-04-21T04:39:31 - `ede8d582-24be-426f-8a38-144ee1d87f89.jsonl`
- `/ll:confidence-check` - 2026-04-20T23:41:00 - `7375438a-9732-4d6b-85bc-98eeec9b0490.jsonl`
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `bff28984-0248-4c2d-a245-daa9001c7e4e.jsonl`
- `/ll:wire-issue` - 2026-04-21T04:35:50 - `bff28984-0248-4c2d-a245-daa9001c7e4e.jsonl`
- `/ll:refine-issue` - 2026-04-21T04:30:39 - `d89e7586-7b6d-4f89-9afa-b0711038479e.jsonl`
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `f84bc5fa-3fa1-4822-8f5a-25670ac913a0.jsonl`
