---
discovered_date: "2026-04-20"
discovered_by: issue-size-review

size: Very Large
confidence_score: 80
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
parent: FEAT-1203
status: done
completed_at: 2026-05-10T00:00:00Z
---

# FEAT-1205: TestParallelRunnerRealThreading — Deep Copy + Max Workers Tests

## Summary

Add 2 tests to `TestParallelRunnerRealThreading` in `scripts/tests/test_parallel_runner.py`:
`test_real_threads_deep_copy_isolates_mutations` and `test_real_threads_max_workers_enforced`.

## Parent Issue

Decomposed from FEAT-1203: TestParallelRunnerRealThreading — Real-Threading Concurrency Tests

## Use Case

**Who**: Developer completing FEAT-1075 (`ParallelRunner` implementation)

**Context**: After FEAT-1202 creates `test_parallel_runner.py` with `TestParallelRunner`, and FEAT-1203 is decomposed, this issue adds the isolation/concurrency tests to `TestParallelRunnerRealThreading`.

**Goal**: Add `TestParallelRunnerRealThreading` class (if not yet present) with 2 real-threading tests. Class must use `@pytest.mark.integration` at class level. MUST run in default CI — NOT gated behind `@pytest.mark.slow`.

**Outcome**: `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_deep_copy_isolates_mutations scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_max_workers_enforced -x` passes green.

## Proposed Solution

### Add to existing file: scripts/tests/test_parallel_runner.py

#### Class: TestParallelRunnerRealThreading

Apply `@pytest.mark.integration` at class level. Use real `ThreadPoolExecutor` (no mocks on executor layer). Both tests use `time.sleep` deliberately to exercise actual thread scheduling.

**`test_real_threads_deep_copy_isolates_mutations`** — 4 real workers each receive a `copy.deepcopy(parent_context)` and mutate nested structures. Assert the original `parent_context` dict passed to `runner.run(...)` is unchanged after the run (no bleed into parent). Secondary check: each worker's `ParallelItemResult.captures` contains only that worker's mutations.

Test shape:
1. Pass `parent_context = {"shared": {"counter": 0, "list": []}}` to `runner.run(...)`.
2. Worker body (mocked at `FSMExecutor.run` seam): mutates the received deepcopy (increment counter, append item_index to list).
3. After run completes: assert `parent_context["shared"]["counter"] == 0` and `parent_context["shared"]["list"] == []`.

**`test_real_threads_max_workers_enforced`** — 20 items, `max_workers=2`. Record `(start_time, end_time)` pairs per worker under a `threading.Lock`. After run, post-hoc: for each pair of workers, check if their intervals overlap; assert max concurrent overlap count ≤ 2.

Implementation recipe:
```python
lock = threading.Lock()
intervals: list[tuple[float, float]] = []

def worker_body(context):
    t_start = time.monotonic()
    time.sleep(0.05)  # brief sleep to ensure overlap window
    t_end = time.monotonic()
    with lock:
        intervals.append((t_start, t_end))
```

Post-hoc overlap check: for each timestamp point (all starts/ends), count how many intervals are active → assert max ≤ 2.

### Implementation Notes

- Apply `@pytest.mark.integration` at **class** level (NOT module-level `pytestmark`) — `TestParallelRunner` (FEAT-1202) is not integration-marked.
- `integration` marker runs in default CI (`scripts/pyproject.toml:113-116`). Do NOT use `@pytest.mark.slow`.
- `loop_name` can be any string like `"test_loop"` when mocking at the `FSMExecutor.run` seam.
- Both tests target FEAT-1075's API: `runner.run(items, loop_name, config, parent_context=...) -> ParallelResult`.
- `ParallelResult.all_results` is pre-allocated by slot; `all_results[i]` corresponds to `items[i]`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis 2026-04-20:_

**FSMExecutor.run mock seam** — `scripts/little_loops/fsm/executor.py:215` defines `def run(self) -> ExecutionResult` (no parameters; all state is set at `__init__`). Mocking must use a closure-capturing `side_effect` that reads `self.captured` / `self.fsm` from the bound instance. Patch target: `little_loops.fsm.parallel_runner.FSMExecutor` (wherever FEAT-1075 imports it) or `little_loops.fsm.executor.FSMExecutor.run` directly via `patch.object(FSMExecutor, "run", autospec=True)`. Return values must be `ExecutionResult` instances (from `little_loops.fsm.types`, re-exported from `fsm/__init__.py`).

**Class-level integration marker template** — `scripts/tests/test_goals_parser.py:437-438` is the **only** class-level (non-module-wide) `@pytest.mark.integration` in the codebase; all others (e.g., `test_worker_pool.py:34`, `test_git_lock.py:16`) use module-level `pytestmark = pytest.mark.integration`. Copy the class-level syntax exactly.

**Existing real-threading test template** — `scripts/tests/test_state.py:412-436` (`TestStateConcurrency.test_concurrent_save_no_corruption`) is the direct template: `from concurrent.futures import ThreadPoolExecutor, as_completed`; `with ThreadPoolExecutor(max_workers=N) as executor:`; `futures = [executor.submit(fn, i) for i in range(N)]`; `[f.result() for f in as_completed(futures)]`.

**No existing overlap-count pattern** — the codebase has no prior sweep-line / interval-overlap test. `test_max_workers_enforced` introduces this pattern. The closest related pattern is `test_concurrency.py:333-355` (exactly-one-winner via `threading.Barrier`), which is structurally different.

**FSMExecutor imports in tests** — use `from little_loops.fsm.executor import FSMExecutor` (see `test_fsm_executor.py`, `test_ll_loop_commands.py:2845` — note: line 2870 is `original_init = FSMExecutor.__init__`, a common `patch.object` wrapper capture pattern; the actual import is at 2845 inside the function body).

_Re-verification pass 2026-04-21:_

- **`ExecutionResult.captured` is nested, not flat** — `scripts/little_loops/fsm/types.py:34` declares `captured: dict[str, dict[str, Any]]` (dict of dicts, keyed by state name). Mock `side_effect` stubs returning a non-empty `captured` must use the nested form, e.g. `captured={"some_state": {"key": "value"}}`. Empty `captured={}` is still valid for tests that don't assert on captured content. This is separate from the `parent_context` dict the test asserts is unmutated — `parent_context` is whatever the caller passes to `runner.run(...)`, not `ExecutionResult.captured`.
- **`test_git_lock.py:395-419` uses raw `threading.Thread`**, not `ThreadPoolExecutor` — adapt with care. The lock-protected-list append pattern transfers directly, but thread management must switch to `ThreadPoolExecutor` + `as_completed` (template: `test_state.py:412-436`).
- **`@pytest.mark.integration` runs in default CI by absence** — `scripts/pyproject.toml:113-116` only registers the marker; there is no `-m "not integration"` exclusion in `addopts`, so integration tests run by default. Confirmed: `integration` is not gated in CI.
- **No new deepcopy / sweep-line / `FSMExecutor.run` patch patterns** have appeared in the codebase since the last refinement pass. This issue is still the first to introduce all three.

### Required Imports

```python
import copy
import threading
import time
from concurrent.futures import ThreadPoolExecutor  # if needed for helper asserts
from unittest.mock import patch, MagicMock

import pytest

from little_loops.fsm import ParallelRunner, ParallelItemResult, ParallelResult  # via FEAT-1075 exports
from little_loops.fsm.executor import FSMExecutor
from little_loops.fsm.schema import ParallelStateConfig  # via FEAT-1074
from little_loops.fsm.types import ExecutionResult  # for mock return values
```

## Integration Map

### Files to Modify
- `scripts/tests/test_parallel_runner.py` — Add 2 tests (+ class declaration if not yet present)

### Dependent Files (under test / needed first)
- `scripts/little_loops/fsm/parallel_runner.py` — Implementation under test (FEAT-1075)
- `scripts/little_loops/fsm/schema.py` — provides `ParallelStateConfig` (FEAT-1074)
- `scripts/little_loops/fsm/__init__.py` — exports `ParallelRunner`, `ParallelItemResult`, `ParallelResult`, `ParallelItemError` (FEAT-1075)
- `scripts/little_loops/fsm/executor.py` — provides `FSMExecutor` (imported as mock target: `from little_loops.fsm.executor import FSMExecutor`); `run()` is the seam patched in both tests
- `scripts/little_loops/fsm/types.py` — provides `ExecutionResult` (`from little_loops.fsm.types import ExecutionResult`); used for mock return values in `side_effect` closures
- FEAT-1202 must be complete (file must exist with `TestParallelRunner`)

_Wiring pass added by `/ll:wire-issue`:_
- **Sibling coordination**: FEAT-1204 and FEAT-1206 also append test classes to `test_parallel_runner.py`. If any sibling lands before FEAT-1205, ensure `TestParallelRunnerRealThreading` is appended after the last existing class in the file to avoid merge conflicts.

### Similar Patterns (copy from)
- `scripts/tests/test_state.py:409-435` — `TestStateConcurrency.test_concurrent_save_no_corruption` — `ThreadPoolExecutor` + `as_completed` real-threading
- `scripts/tests/test_git_lock.py:395-419` — `threading.Lock`-protected shared list pattern (note: serialization test, not enter/exit pairs — adapt for interval recording)
- `scripts/tests/test_goals_parser.py:437` — class-level `@pytest.mark.integration` in mixed file (direct template)
- `scripts/tests/test_fsm_executor.py:1847-1854` — minimal `ExecutionResult` stub construction: `ExecutionResult(final_state="done", iterations=5, terminated_by="terminal", duration_ms=1234, captured={})` — use this shape for mock `side_effect` return values
- `scripts/tests/test_fsm_executor.py:409` — `FSMExecutor._run_subprocess` patch via `patch("little_loops.fsm.executor.FSMExecutor._run_subprocess")` — closest existing seam; `test_real_threads_*` patches `.run` instead (no prior template in codebase)

_Wiring pass added by `/ll:wire-issue`:_
- **`copy.deepcopy` in tests** — No existing test uses `copy.deepcopy`; `test_real_threads_deep_copy_isolates_mutations` introduces this pattern for the first time.
- **Sweep-line overlap count** — No existing test uses interval recording + endpoint sweep to assert concurrency bounds; `test_real_threads_max_workers_enforced` introduces this pattern for the first time.
- **`patch.object(FSMExecutor, "run", ...)` seam** — No existing test patches `FSMExecutor.run`; closest prior patterns patch `__init__` (`test_ll_loop_commands.py:2869`) or `_run_subprocess` (`test_fsm_executor.py:409`).

## Dependencies

- **FEAT-1074** must be complete (`ParallelStateConfig` in `schema.py`)
- **FEAT-1075** must be complete (`ParallelRunner` implementation + `fsm/__init__.py` exports)
- **FEAT-1202** must be complete (creates `test_parallel_runner.py`)

### Current Dependency Status (verified 2026-04-20)

- **FEAT-1074** — NOT IMPLEMENTED. `scripts/little_loops/fsm/schema.py` defines `EvaluateConfig`, `RouteConfig`, `StateConfig`, `LLMConfig`, `LoopConfigOverrides`, `FSMLoop`. No `ParallelStateConfig` exists yet.
- **FEAT-1075** — NOT IMPLEMENTED. `scripts/little_loops/fsm/parallel_runner.py` does not exist. No `ParallelRunner`, `ParallelResult`, `ParallelItemResult`, or `ParallelItemError` symbol exists anywhere in `scripts/`. (Note: `scripts/little_loops/parallel/` is the orchestrator-layer parallelism package — separate module, not reusable here.)
- **FEAT-1202** — NOT IMPLEMENTED. `scripts/tests/test_parallel_runner.py` does not exist.

This issue cannot be started until all three dependencies land.

## Implementation Steps

1. Verify prerequisites: `scripts/tests/test_parallel_runner.py` exists with `TestParallelRunner` (FEAT-1202); `ParallelRunner`, `ParallelResult`, `ParallelItemResult` are exported from `little_loops.fsm` (FEAT-1075); `ParallelStateConfig` exists in `little_loops.fsm.schema` (FEAT-1074).
2. Append the `TestParallelRunnerRealThreading` class to `scripts/tests/test_parallel_runner.py`, decorated at class level with `@pytest.mark.integration` (template: `scripts/tests/test_goals_parser.py:437-438`). Add any missing imports from the "Required Imports" block above.
3. Implement `test_real_threads_deep_copy_isolates_mutations`:
   - Build `parent_context = {"shared": {"counter": 0, "list": []}}`.
   - Patch `FSMExecutor.run` with a closure `side_effect` that reads the bound instance's captured-context, mutates it (increment counter, append `item_index`), and returns a stubbed `ExecutionResult`.
   - Construct `ParallelStateConfig(items=[...], loop="test_loop", max_workers=4, ...)` (fill required fields).
   - Call `runner.run(items=[...4 items...], loop_name="test_loop", config=config, parent_context=parent_context)`.
   - Assert `parent_context["shared"]["counter"] == 0` and `parent_context["shared"]["list"] == []`.
   - Assert per-worker `result.all_results[i].captures` reflects only that worker's mutations.
4. Implement `test_real_threads_max_workers_enforced`:
   - Build `intervals: list[tuple[float, float]] = []` and `lock = threading.Lock()`.
   - `side_effect` records `(t_start, t_end)` after a `time.sleep(0.05)` window; append under lock.
   - Config: 20 items, `max_workers=2`.
   - After run, compute max concurrent overlap via sweep over all endpoints; assert ≤ 2.
5. Run targeted tests: `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading -x -v` — both tests must pass green.
6. Run the full suite with default CI markers to confirm neither test is slow-gated: `python -m pytest scripts/tests/test_parallel_runner.py -v`.

## Acceptance Criteria

- `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_deep_copy_isolates_mutations -x` passes green
- `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_max_workers_enforced -x` passes green
- Both tests run in default CI (class-level `@pytest.mark.integration`, no `@pytest.mark.slow`)
- `test_real_threads_max_workers_enforced` asserts ≤ 2 concurrent workers at any point
- `test_real_threads_deep_copy_isolates_mutations` asserts original `parent_context` is unchanged after run

## Labels

`fsm`, `parallel`, `tests`, `integration`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-20_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- All three critical dependencies remain unresolved active issues: FEAT-1074 (`ParallelStateConfig` in `schema.py`), FEAT-1075 (`ParallelRunner` implementation + exports), and FEAT-1202 (`test_parallel_runner.py` creation). The tests cannot be run — or even imported — until all three land.
- Minor: Exact `ParallelStateConfig` required fields and the `FSMExecutor.run` patch path within `ParallelRunner` are unknown until FEAT-1074 and FEAT-1075 are implemented; these will need to be confirmed before writing the tests.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-20
- **Reason**: Issue too large for single session

### Decomposed Into
- FEAT-1207: TestParallelRunnerRealThreading — Deep Copy Isolation Test
- FEAT-1208: TestParallelRunnerRealThreading — Max Workers Enforcement Test

## Session Log
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `d825c2a4-fabd-41df-8994-3e6d74767fc9.jsonl`
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `3d5312e8-2850-416b-b80a-2620333d3eb1.jsonl`
- `/ll:refine-issue` - 2026-04-21T03:41:06 - `5e4e5054-9031-473c-a890-91507c70a6f4.jsonl`
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `e9f4ed37-45ee-4710-be1c-b32805d610df.jsonl`
- `/ll:wire-issue` - 2026-04-21T03:36:27 - `e9f4ed37-45ee-4710-be1c-b32805d610df.jsonl`
- `/ll:refine-issue` - 2026-04-21T03:31:16 - `80d75a46-4607-4b8d-8528-43c8fafd182c.jsonl`
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `2ed5d9eb-8026-4655-8ff3-63958b109e67.jsonl`
