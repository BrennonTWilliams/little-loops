---
status: done
completed_at: 2026-04-21T00:00:00Z
---
> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
discovered_date: "2026-04-20"
discovered_by: issue-size-review
parent_issue: FEAT-1205
size: Very Large
confidence_score: 80
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1208: TestParallelRunnerRealThreading — Max Workers Enforcement Test

## Summary

Add `test_real_threads_max_workers_enforced` to `TestParallelRunnerRealThreading` in `scripts/tests/test_parallel_runner.py`.

## Parent Issue

Decomposed from FEAT-1205: TestParallelRunnerRealThreading — Deep Copy + Max Workers Tests

## Use Case

**Who**: Developer completing FEAT-1075 (`ParallelRunner` implementation)

**Context**: After FEAT-1202 creates `test_parallel_runner.py` with `TestParallelRunner`, this issue adds the max-workers concurrency enforcement test to `TestParallelRunnerRealThreading`. FEAT-1207 adds the sibling deep-copy test.

**Goal**: Add `test_real_threads_max_workers_enforced` to `TestParallelRunnerRealThreading` (creating the class if absent). MUST run in default CI — NOT gated behind `@pytest.mark.slow`.

**Outcome**: `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_max_workers_enforced -x` passes green.

## Proposed Solution

### Add to existing file: scripts/tests/test_parallel_runner.py

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

- Apply `@pytest.mark.integration` at **class** level if creating the class — template: `scripts/tests/test_goals_parser.py:437-438`.
- `integration` marker runs in default CI (`scripts/pyproject.toml:113-116`). Do NOT use `@pytest.mark.slow`.
- `loop_name` can be any string like `"test_loop"` when mocking at the `FSMExecutor.run` seam.
- Uses `time.sleep(0.05)` deliberately to exercise actual thread scheduling and create a measurable overlap window.

### Codebase Research Findings

**No existing overlap-count pattern** — The codebase has no prior sweep-line / interval-overlap test. This issue introduces this pattern for the first time.

**FSMExecutor.run mock seam** — `scripts/little_loops/fsm/executor.py:215` defines `def run(self) -> ExecutionResult`. Mocking must use a closure-capturing `side_effect`. Patch target: `patch.object(FSMExecutor, "run", autospec=True)`. No existing test patches `FSMExecutor.run`; closest prior pattern patches `_run_subprocess` (`test_fsm_executor.py:409`).

**side_effect closure template** — `scripts/tests/test_worker_pool.py:1824-1832` shows a `patch.object(..., side_effect=fn)` where `fn` captures a list-boxed mutable (`call_count = [0]`) to record invocations across threads. This is the closest pattern for what FEAT-1208 needs (closure capturing shared state under a mock seam).

**Lock-protected shared list (serialization)** — `scripts/tests/test_git_lock.py:395-419` uses `threading.Lock`-protected shared list append (note: that test tracks serialization order, not interval pairs — adapt the pattern for `(start, end)` tuples).

**Lock-protected counter at matching scale** — `scripts/tests/test_git_lock.py:462-479` runs 20 raw `threading.Thread`s with a `counter_lock`-protected list-boxed counter and `t.join(timeout=10)`. Scale-matched template for the 20-item run.

**Real-threading template** — `scripts/tests/test_state.py:412-436` (`TestStateConcurrency.test_concurrent_save_no_corruption`): `ThreadPoolExecutor(max_workers=N)` + `as_completed`.

**`ExecutionResult` minimal stub** — `scripts/little_loops/fsm/types.py:16` defines `@dataclass ExecutionResult` with 5 required positional fields: `final_state: str`, `iterations: int`, `terminated_by: str`, `duration_ms: int`, `captured: dict[str, dict[str, Any]]` (optional: `error`, `handoff`, `continuation_prompt`). Minimal stub (from `test_fsm_executor.py:1847-1854`):
```python
ExecutionResult(
    final_state="done",
    iterations=1,
    terminated_by="terminal",
    duration_ms=100,
    captured={},
)
```

**Class-level `@pytest.mark.integration` uniqueness** — `test_goals_parser.py:437-438` is the **only** class-level (non-module-wide) usage in the codebase. Every other integration test file uses module-level `pytestmark = pytest.mark.integration`. Since `test_parallel_runner.py` will be a mixed-file (unit tests + real-threading class), class-level scoping on `TestParallelRunnerRealThreading` is the correct pattern — module-level would incorrectly mark the mocked `TestParallelRunner` tests too.

**`integration` marker in CI** — `scripts/pyproject.toml:113-116` declares the `integration` marker. The `addopts` block (lines 108-112) does **not** include `-m "not integration"`, so integration tests run by default. Use `integration`, not `slow`.

**Forward-reference status (2026-04-20)** — All four prerequisites are currently unbuilt: `scripts/tests/test_parallel_runner.py` (needs FEAT-1202), `scripts/little_loops/fsm/parallel_runner.py` (needs FEAT-1075), `ParallelRunner` exports in `fsm/__init__.py` (needs FEAT-1075), `ParallelStateConfig` in `schema.py` (needs FEAT-1074). This issue is **blocked** until those land.

### Required Imports

```python
import threading
import time
from unittest.mock import patch

import pytest

from little_loops.fsm import ParallelRunner, ParallelItemResult, ParallelResult
from little_loops.fsm.executor import FSMExecutor
from little_loops.fsm.schema import ParallelStateConfig
from little_loops.fsm.types import ExecutionResult
```

### Similar Patterns (copy from)

- `scripts/tests/test_state.py:409-435` — `ThreadPoolExecutor` + `as_completed` real-threading
- `scripts/tests/test_git_lock.py:395-419` — `threading.Lock`-protected shared list pattern (adapt for interval tuples)
- `scripts/tests/test_git_lock.py:462-479` — 20-thread lock-protected counter (scale-matched template)
- `scripts/tests/test_worker_pool.py:1824-1832` — `patch.object(..., side_effect=fn)` with closure capturing list-boxed mutable (directly applicable to `FSMExecutor.run` mock)
- `scripts/tests/test_goals_parser.py:437` — class-level `@pytest.mark.integration` in mixed file (direct template)
- `scripts/tests/test_fsm_executor.py:1847-1854` — minimal `ExecutionResult` stub construction

## Integration Map

### Files to Modify
- `scripts/tests/test_parallel_runner.py` — Add `test_real_threads_max_workers_enforced` to `TestParallelRunnerRealThreading` (or create class if absent)

### Dependent Files (under test / needed first)
- `scripts/little_loops/fsm/parallel_runner.py` — Implementation under test (FEAT-1075)
- `scripts/little_loops/fsm/schema.py` — provides `ParallelStateConfig` (FEAT-1074)
- `scripts/little_loops/fsm/__init__.py` — exports `ParallelRunner`, `ParallelItemResult`, `ParallelResult` (FEAT-1075)
- `scripts/little_loops/fsm/executor.py` — provides `FSMExecutor` (mock seam: `FSMExecutor.run`)
- `scripts/little_loops/fsm/types.py` — provides `ExecutionResult` for mock return values
- FEAT-1202 must be complete (`test_parallel_runner.py` with `TestParallelRunner`)

### Sibling Coordination
FEAT-1207 also appends to `TestParallelRunnerRealThreading`. If FEAT-1207 lands first, it creates the class; this issue appends `test_real_threads_max_workers_enforced` after the existing method. If this issue lands first, create the class here and FEAT-1207 appends its method after. Coordinate to avoid merge conflicts.

## Dependencies

- **FEAT-1074** must be complete (`ParallelStateConfig` in `schema.py`)
- **FEAT-1075** must be complete (`ParallelRunner` implementation + `fsm/__init__.py` exports)
- **FEAT-1202** must be complete (creates `test_parallel_runner.py`)

## Implementation Steps

1. Verify prerequisites: `test_parallel_runner.py` exists with `TestParallelRunner`; `ParallelRunner`, `ParallelResult`, `ParallelItemResult` exported from `little_loops.fsm`; `ParallelStateConfig` exists in `little_loops.fsm.schema`.
2. If `TestParallelRunnerRealThreading` doesn't exist yet, create it with `@pytest.mark.integration` at class level (template: `test_goals_parser.py:437-438`). Add missing imports from the Required Imports block.
3. Implement `test_real_threads_max_workers_enforced`:
   - Set up `lock = threading.Lock()` and `intervals: list[tuple[float, float]] = []`.
   - Patch `FSMExecutor.run` with a `side_effect` that records `(t_start, t_end)` after `time.sleep(0.05)`, appending under lock.
   - Config: 20 items, `max_workers=2`.
   - After `runner.run(...)`, compute max concurrent overlap via sweep over all interval endpoints; assert ≤ 2.
4. Run: `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_max_workers_enforced -x -v` — must pass green.

## Acceptance Criteria

- `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_max_workers_enforced -x` passes green
- Test runs in default CI (class-level `@pytest.mark.integration`, no `@pytest.mark.slow`)
- Asserts max concurrent workers ≤ 2 at any point during the 20-item run

## Labels

`fsm`, `parallel`, `tests`, `integration`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-20_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 100/100 → HIGH CONFIDENCE

### Concerns
- **Blocked by 3 unresolved critical dependencies**: FEAT-1074 (`ParallelStateConfig`), FEAT-1075 (`parallel_runner.py` + exports), and FEAT-1202 (`test_parallel_runner.py`) are all still active — none present in `completed/`. The test cannot be written and executed until all three land.

## Session Log
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8e558d48-a582-4752-a117-daef3f975c61.jsonl`
- `/ll:refine-issue` - 2026-04-21T04:08:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/98e4c323-2256-4b73-9e43-83bbb6fd2ed6.jsonl`
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8997c035-370a-4045-9e4b-18d1f35e90f9.jsonl`
- `/ll:wire-issue` - 2026-04-21T04:05:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3ac3273c-3a62-4f9f-88eb-b82f56245cd4.jsonl`
- `/ll:refine-issue` - 2026-04-21T04:01:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/671d2c60-d9cc-47d0-ad7a-e85d89e87f68.jsonl`
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d825c2a4-fabd-41df-8994-3e6d74767fc9.jsonl`
