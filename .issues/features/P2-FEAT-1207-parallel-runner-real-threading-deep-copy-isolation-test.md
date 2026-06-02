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
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1207: TestParallelRunnerRealThreading — Deep Copy Isolation Test

## Summary

Add `test_real_threads_deep_copy_isolates_mutations` to `TestParallelRunnerRealThreading` in `scripts/tests/test_parallel_runner.py`.

## Parent Issue

Decomposed from FEAT-1205: TestParallelRunnerRealThreading — Deep Copy + Max Workers Tests

## Use Case

**Who**: Developer completing FEAT-1075 (`ParallelRunner` implementation)

**Context**: After FEAT-1202 creates `test_parallel_runner.py` with `TestParallelRunner`, this issue adds the deep copy isolation test to `TestParallelRunnerRealThreading`. FEAT-1208 adds the sibling max-workers test.

**Goal**: Add `TestParallelRunnerRealThreading` class (if not yet present) with class-level `@pytest.mark.integration`, then add `test_real_threads_deep_copy_isolates_mutations`. MUST run in default CI — NOT gated behind `@pytest.mark.slow`.

**Outcome**: `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_deep_copy_isolates_mutations -x` passes green.

## Proposed Solution

### Add to existing file: scripts/tests/test_parallel_runner.py

#### Class: TestParallelRunnerRealThreading

Apply `@pytest.mark.integration` at class level (NOT module-level `pytestmark`) — template: `scripts/tests/test_goals_parser.py:437-438`.

**`test_real_threads_deep_copy_isolates_mutations`** — 4 real workers each receive a `copy.deepcopy(parent_context)` and mutate nested structures. Assert the original `parent_context` dict passed to `runner.run(...)` is unchanged after the run (no bleed into parent).

Test shape:
1. Pass `parent_context = {"shared": {"counter": 0, "list": []}}` to `runner.run(...)`.
2. Worker body (mocked at `FSMExecutor.run` seam): mutates the received deepcopy (increment counter, append item_index to list).
3. After run completes: assert `parent_context["shared"]["counter"] == 0` and `parent_context["shared"]["list"] == []`.
4. Assert per-worker `result.all_results[i].captures` reflects only that worker's mutations.

### Implementation Notes

- Apply `@pytest.mark.integration` at **class** level — `TestParallelRunner` (FEAT-1202) is not integration-marked.
- `integration` marker runs in default CI (`scripts/pyproject.toml:113-116`). Do NOT use `@pytest.mark.slow`.
- `loop_name` can be any string like `"test_loop"` when mocking at the `FSMExecutor.run` seam.
- `ExecutionResult.captured` is nested: `dict[str, dict[str, Any]]` (keyed by state name) — see `scripts/little_loops/fsm/types.py:34`. Empty `captured={}` is valid for tests not asserting captured content.
- **Field name distinction** (easy to confuse in assertions): the mock's return is `ExecutionResult.captured` (singular, from `fsm/types.py:34`), but the runner surfaces per-worker data as `ParallelItemResult.captures` (plural, from FEAT-1075 contract at line 76 of `.issues/features/P2-FEAT-1075-parallel-runner-module.md`). Step 3 assertion is `result.all_results[i].captures` — plural, on the runner's wrapper type, not on the executor's return.

### Codebase Research Findings

**FSMExecutor.run mock seam** — `scripts/little_loops/fsm/executor.py:215` defines `def run(self) -> ExecutionResult` (no parameters). Mocking must use a closure-capturing `side_effect` that reads bound instance state. Patch target: `little_loops.fsm.executor.FSMExecutor.run` via `patch.object(FSMExecutor, "run", autospec=True)`.

**Class-level integration marker template** — `scripts/tests/test_goals_parser.py:437-438` is the **only** class-level `@pytest.mark.integration` in the codebase; all others use module-level `pytestmark`. Copy the class-level syntax exactly.

**No existing deepcopy pattern** — `test_real_threads_deep_copy_isolates_mutations` introduces `copy.deepcopy` in tests for the first time.

**`patch.object(FSMExecutor, "run", ...)` seam** — No existing test patches `FSMExecutor.run`; closest prior patterns patch `__init__` (`test_ll_loop_commands.py:2869`) or `_run_subprocess` (`test_fsm_executor.py:409`).

_Added by `/ll:refine-issue` 2026-04-20 (auto refresh) — based on codebase re-scan:_

- **Name-collision risk — `ParallelConfig` vs `ParallelStateConfig`**: An unrelated `ParallelConfig` dataclass already exists at `scripts/little_loops/parallel/types.py:283` (in the top-level `parallel/` package, serving `ll-parallel` worktree orchestration). The pending `ParallelStateConfig` (FEAT-1074) lives in `scripts/little_loops/fsm/schema.py` and serves FSM parallel states. Import the FSM one: `from little_loops.fsm.schema import ParallelStateConfig` — do NOT import from `little_loops.parallel.types`.
- **`ExecutionResult` full field list** (`scripts/little_loops/fsm/types.py:16-37`): 5 required (`final_state`, `iterations`, `terminated_by`, `duration_ms`, `captured`) + 3 optional with defaults (`error: str | None = None`, `handoff: bool = False`, `continuation_prompt: str | None = None`). The minimal stub used in the test only needs the 5 required fields.
- **Dependency state confirmed unmet as of 2026-04-20**: `parallel_runner.py`, `ParallelRunner`, `ParallelItemResult`, `ParallelResult`, `ParallelStateConfig`, and `test_parallel_runner.py` all still absent. FEAT-1074/1075/1202 remain blocking (matches Confidence Check note).

### Required Imports

```python
import copy
import threading
from unittest.mock import patch, MagicMock

import pytest

from little_loops.fsm import ParallelRunner, ParallelItemResult, ParallelResult
from little_loops.fsm.executor import FSMExecutor
from little_loops.fsm.schema import ParallelStateConfig
from little_loops.fsm.types import ExecutionResult
```

### Similar Patterns (copy from)

- `scripts/tests/test_goals_parser.py:437` — class-level `@pytest.mark.integration` in mixed file (direct template)
- `scripts/tests/test_fsm_executor.py:1847-1854` — minimal `ExecutionResult` stub: `ExecutionResult(final_state="done", iterations=5, terminated_by="terminal", duration_ms=1234, captured={})`
- `scripts/tests/test_state.py:409-435` — `ThreadPoolExecutor` + `as_completed` real-threading template

## Integration Map

### Files to Modify
- `scripts/tests/test_parallel_runner.py` — Add `TestParallelRunnerRealThreading` class (if absent) + `test_real_threads_deep_copy_isolates_mutations`

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_goals_parser.py:437-438` — class-level `@pytest.mark.integration` syntax (the only class-level example; all others use module-level `pytestmark`)
- `scripts/tests/test_fsm_executor.py:1847-1854` — `ExecutionResult` stub; 5 required fields (`final_state`, `iterations`, `terminated_by`, `duration_ms`, `captured`); `error` has a default
- `scripts/tests/test_state.py:409-435` — real `ThreadPoolExecutor` + `as_completed` real-threading pattern
- `scripts/tests/test_issue_parser.py:1026` — only `patch.object(..., autospec=True, side_effect=...)` example in the codebase; confirms the combined `autospec + side_effect` pattern is already established

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml:113-116` — `integration` and `slow` markers both registered; `--strict-markers` active (line 107); no changes needed, confirms `@pytest.mark.integration` at class level is valid without triggering unknown-mark error

### Dependent Files (under test / needed first)
- `scripts/little_loops/fsm/parallel_runner.py` — Implementation under test (FEAT-1075)
- `scripts/little_loops/fsm/schema.py` — provides `ParallelStateConfig` (FEAT-1074)
- `scripts/little_loops/fsm/__init__.py` — exports `ParallelRunner`, `ParallelItemResult`, `ParallelResult` (FEAT-1075)
- `scripts/little_loops/fsm/executor.py` — provides `FSMExecutor` (mock seam: `FSMExecutor.run`)
- `scripts/little_loops/fsm/types.py` — provides `ExecutionResult` for mock return values
- FEAT-1202 must be complete (`test_parallel_runner.py` with `TestParallelRunner`)

### Sibling Coordination
FEAT-1208 also appends to `TestParallelRunnerRealThreading`. If FEAT-1207 lands first, FEAT-1208 appends its test method to the class. If FEAT-1208 lands first, FEAT-1207 creates the class declaration and FEAT-1208 appends after. Coordinate to avoid merge conflicts.

## Dependencies

- **FEAT-1074** must be complete (`ParallelStateConfig` in `schema.py`)
- **FEAT-1075** must be complete (`ParallelRunner` implementation + `fsm/__init__.py` exports)
- **FEAT-1202** must be complete (creates `test_parallel_runner.py`)

## Implementation Steps

1. Verify prerequisites: `test_parallel_runner.py` exists with `TestParallelRunner`; `ParallelRunner`, `ParallelResult`, `ParallelItemResult` exported from `little_loops.fsm`; `ParallelStateConfig` exists in `little_loops.fsm.schema`.
2. If `TestParallelRunnerRealThreading` doesn't exist yet, append it to `test_parallel_runner.py` with `@pytest.mark.integration` at class level (template: `test_goals_parser.py:437-438`). Add missing imports from the Required Imports block.
3. Implement `test_real_threads_deep_copy_isolates_mutations`:
   - Build `parent_context = {"shared": {"counter": 0, "list": []}}`.
   - Patch `FSMExecutor.run` with a closure `side_effect` that mutates the deepcopy received by each worker and returns a stubbed `ExecutionResult`.
   - Call `runner.run(items=[...4 items...], loop_name="test_loop", config=config, parent_context=parent_context)`.
   - Assert `parent_context["shared"]["counter"] == 0` and `parent_context["shared"]["list"] == []`.
   - Assert per-worker `result.all_results[i].captures` reflects only that worker's mutations.
4. Run: `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_deep_copy_isolates_mutations -x -v` — must pass green.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. `autospec=True` side_effect arity: `patch.object(FSMExecutor, "run", autospec=True)` preserves the `(self,)` method signature. The `side_effect` closure must declare `def mock_run(executor_instance): ...` — it will receive the bound executor as its first argument. A zero-argument lambda will raise `TypeError` at test time.

## Acceptance Criteria

- `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_deep_copy_isolates_mutations -x` passes green
- Test runs in default CI (class-level `@pytest.mark.integration`, no `@pytest.mark.slow`)
- Original `parent_context` is unchanged after run (no mutation bleed from worker deepcopies)

## Labels

`fsm`, `parallel`, `tests`, `integration`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-20_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- All three blocking dependencies are unresolved: FEAT-1074 (`ParallelStateConfig` not in `schema.py`), FEAT-1075 (`parallel_runner.py` absent), FEAT-1202 (`test_parallel_runner.py` absent). Cannot begin implementation until all three land.

## Session Log
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `24e16d90-d706-4111-b42c-d75eb4381930.jsonl`
- `/ll:refine-issue` - 2026-04-21T03:55:16 - `445a2e37-ad29-42d1-a9e4-80733da8b83d.jsonl`
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `be83f398-c7a1-4e75-9895-d25d16c13942.jsonl`
- `/ll:wire-issue` - 2026-04-21T03:51:52 - `d34feae8-08b3-40e8-980d-65151a568b44.jsonl`
- `/ll:refine-issue` - 2026-04-21T03:47:34 - `bb865c69-0af1-4083-a5ce-cea71c5ad79d.jsonl`
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `d825c2a4-fabd-41df-8994-3e6d74767fc9.jsonl`
