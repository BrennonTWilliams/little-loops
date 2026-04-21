> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
discovered_date: "2026-04-20"
discovered_by: issue-size-review
parent_issue: FEAT-1199
size: Very Large
confidence_score: 80
outcome_confidence: 86
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1202: TestParallelRunner — Core Mocked Unit Tests

## Summary

Create `TestParallelRunner` in `scripts/tests/test_parallel_runner.py` — the fast mocked-FSMExecutor suite covering all core `ParallelRunner` behaviors without real thread overhead.

## Parent Issue

Decomposed from FEAT-1199: Parallel Runner Unit Tests (test_parallel_runner.py)

## Use Case

**Who**: Developer completing FEAT-1075 (`ParallelRunner` implementation)

**Context**: Once `ParallelRunner` exists, this test class provides fast, mocked unit coverage for all core behaviors. It runs without real thread scheduling and forms the baseline suite.

**Goal**: Create `scripts/tests/test_parallel_runner.py` (flat in `scripts/tests/`, no subdirectory) with the `TestParallelRunner` class and its 8 test cases. Subsequent issues (FEAT-1203, FEAT-1204) will add more classes to the same file.

**Outcome**: `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunner -x` passes green.

## Proposed Solution

### New file: scripts/tests/test_parallel_runner.py

Create the file with module-level docstring explaining the mocking departure from `TestSubLoopExecution`:

> `TestParallelRunner` mocks `FSMExecutor.run()` directly to keep the fast suite fast. This is a deliberate departure from `TestSubLoopExecution` (which uses real FSMExecutor instances) — mock one level higher here.

#### Class: TestParallelRunner (mocked FSMExecutor)

Use `unittest.mock.patch` on `FSMExecutor.run` to prevent real executor fan-out.

Test cases:

- **Thread mode**: mock sub-loop runs, verify captures collected, verdict derived correctly
- **Thread mode `fail_fast`**: verify remaining futures cancelled on first failure
- **Worktree mode**: mock worktree setup/teardown, verify merge-back called
- **`context_passthrough: true`**: verify parent context passed to each worker
- **`test_parallel_runner_context_passthrough_is_deep_copy_per_worker`** — pass a `parent_context` with nested mutable structures (`{"items": ["a", "b"], "meta": {"count": 0}}`). Spawn N (≥4) workers each mutating their nested structures. Assert: (a) each worker's mutations visible only in its own `ParallelItemResult.captures`, (b) sibling workers see no mutations from each other in their initial context, (c) parent's original dict is byte-for-byte unchanged (including nested containers — check identity with `is not`).
- **`test_parallel_runner_preserves_item_order_under_async_completion`** — 4 items with durations `[3.0, 1.0, 2.0, 0.5]` (inverted). Assert `result.all_results[i].item == items[i]` and `item_index == i` for all `i`; assert completion timestamps are out of order.
- **`timeout_seconds`**: worker exceeding timeout records `ParallelItemResult(verdict="no", terminated_by="timeout", error="...")` aggregated under `fail_mode`; `timeout_seconds=None` means no timeout enforced
- **Edge — 0 items**: → immediate `ParallelResult(all_results=[], verdict="yes")` (assert `.succeeded == [] and .failed == []`)
- **Edge — 1 item fails of 1**: → `result.all_results[0].verdict == "no"`; `result.verdict == "no"`; `result.failed[0].error` is non-empty string

### Implementation Notes

- **Worker success condition**: `child_result.terminated_by == "terminal" and child_result.final_state == "done"` (mirrors `_execute_sub_loop()` at `scripts/little_loops/fsm/executor.py:417-418`)
- **Captures storage**: `self.captured[self.current_state] = {"results": [<ParallelItemResult-as-dict>, ...]}` (parallel to sub-loop pattern at `executor.py:414`)
- **Mocking departure**: `TestSubLoopExecution` at `scripts/tests/test_fsm_executor.py:3634-3957` uses real FSMExecutor instances with child YAML written to `tmp_path / ".loops"`. `TestParallelRunner` mocks `FSMExecutor.run()` directly — deliberate departure, document in module docstring.
- Do NOT apply `pytestmark = pytest.mark.integration` at module level — subsequent FEAT-1203/1204 classes need class-level markers only.

## Integration Map

### Files to Create / Modify
- `scripts/tests/test_parallel_runner.py` — New file (flat in `scripts/tests/`); FEAT-1203 and FEAT-1204 will add classes to this same file

### Dependent Files (under test / needed first)
- `scripts/little_loops/fsm/parallel_runner.py` — Implementation under test (FEAT-1075; must exist first)
- `scripts/little_loops/fsm/schema.py:229-255` — `ParallelStateConfig` (added by FEAT-1074)
- `scripts/little_loops/fsm/types.py:15-54` — `ExecutionResult` (child result consumed by `ParallelRunner`)
- `scripts/little_loops/fsm/executor.py:366-430` — `_execute_sub_loop()`; success condition at 417-418
- `scripts/little_loops/fsm/__init__.py:143-195` — Must export `ParallelRunner` and `ParallelResult` (FEAT-1075 step 8)

### Import Paths

```python
from little_loops.fsm import ParallelRunner, ParallelResult       # via __init__.py AFTER FEAT-1075 step 8
from little_loops.fsm.parallel_runner import ParallelItemResult, ParallelItemError  # direct
from little_loops.fsm.schema import ParallelStateConfig           # direct
```

`ParallelStateConfig` minimum constructor: `ParallelStateConfig(items="ctx_key", loop="child")` — all other fields have defaults.

### Similar Patterns (copy from)
- `scripts/tests/test_fsm_executor.py:3634-3957` — `TestSubLoopExecution` — sub-loop test structure (but uses real FSMExecutor; this suite mocks higher)
- `scripts/tests/test_fsm_executor.py:30-92` — `MockActionRunner` dataclass — action-layer mocking convention (NOT reused here)
- `scripts/tests/conftest.py:225-305` — `temp_project` / `valid_loop_file` fixtures
- `scripts/tests/conftest.py:55-61` — `temp_project_dir` (generator) fixture
- `scripts/tests/test_parallel_types.py` — existing parallel-component type tests; shows conventions for testing parallel module dataclasses and results

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis 2026-04-20:_

**Blocker status (confirmed):** Neither `scripts/little_loops/fsm/parallel_runner.py` nor `ParallelStateConfig` in `scripts/little_loops/fsm/schema.py` exists yet. FEAT-1074 and FEAT-1075 must land first — listed under Dependencies is already accurate.

**Line-reference corrections (vs. issue body):**
- `types.py:15-54` → `ExecutionResult` dataclass runs lines 16-54 (`@dataclass` at 15). `ActionResult` begins at line 58. Functionally correct.
- `executor.py:366-430`, `executor.py:417-418`, `executor.py:414`, `__init__.py:143-195` — all **exact matches**, no change needed.
- `schema.py:229-255` — this range is currently the `StateConfig` field block (`action`...`extra_routes`). `ParallelStateConfig` will be inserted in that vicinity by FEAT-1074; treat the reference as an **insertion zone**, not existing code.
- `conftest.py:225-305` → `temp_project` is at line 226, `valid_loop_file` at 235, `loops_dir` at 271. Range is correct.
- `conftest.py:55-61` → `temp_project_dir` generator at line 56. Exact.

**Captures-shape clarification (important):** `executor.py:414` currently stores `self.captured[self.current_state] = child_executor.captured` — the entire child captured dict placed under the parent state name. The parallel runner's planned shape `{"results": [<ParallelItemResult-as-dict>, ...]}` is **parallel in position, not in shape**. Tests should assert on the `{"results": [...]}` wrapper explicitly; do not assume the sub-loop's dict-of-dicts shape.

**Mock target path (critical for `patch`):** Patch the name as imported into the module under test:
- `patch("little_loops.fsm.parallel_runner.FSMExecutor")` (not `little_loops.fsm.executor.FSMExecutor`)
- For the fake clock: `patch("little_loops.fsm.parallel_runner.time.time", side_effect=[...])`

Precedent: `scripts/tests/test_orchestrator.py:139-156` patches `little_loops.parallel.orchestrator.WorkerPool` etc. in a `with (patch(...), patch(...), ...)` block; `scripts/tests/test_fsm_executor.py:2004-2037` patches `little_loops.fsm.executor.time.time` with a `side_effect` closure for fake-clock timeout tests.

**Additional reusable patterns:**
- `scripts/tests/test_orchestrator.py:139-156` — multi-patch fixture block; model for constructing a `ParallelRunner` whose internal executor is mocked.
- `scripts/tests/test_worker_pool.py:401-416` — `patch.object(instance, "_method")` when patching a method after instance construction.
- `scripts/tests/test_fsm_executor.py:2004-2037` — fake-clock closure for `timeout_seconds` test (pattern: `time_values = [start, start, start + N]` with call-count indirection).
- `scripts/tests/test_subprocess_mocks.py:121-127` — shorter `mock_time.side_effect = [0, 0, 100]` form for simple timeout.
- `scripts/tests/test_concurrency.py:333-355` — `threading.Barrier` for simultaneous-start races (relevant to FEAT-1203; NOT needed here since this suite is mocked).

**TestSubLoopExecution structure (concrete):** `scripts/tests/test_fsm_executor.py:3634+` uses **no `setup_method` and no class-level fixtures** — each test takes `tmp_path: Path` directly, writes inline YAML strings, constructs a live `FSMExecutor`, asserts on returned `ExecutionResult`. Mirror this flat style for `TestParallelRunner` (minus the live executor — mock `FSMExecutor.run` instead).

**MockActionRunner placement:** `scripts/tests/test_fsm_executor.py:30-92` — module-level dataclass, NOT in conftest. The issue correctly notes this is not reused here (parallel runner mocks at the `FSMExecutor.run` layer, above the action layer).

**Assertion conventions for `ExecutionResult`:** `test_fsm_executor.py:97-121` (`result.final_state`, `result.iterations`, `result.terminated_by`, `mock_runner.calls`) and `test_fsm_executor.py:592-668` (`result.captured["key"]["output"]`, `...["exit_code"]`, `...["stderr"]`). For this suite, the inner child `ExecutionResult` produced by the mocked `FSMExecutor.run` should be constructed with matching field names: `ExecutionResult(final_state="done", terminated_by="terminal", captured={...}, iterations=1, duration_ms=..., error=None, handoff=False, continuation_prompt=None)`.

**Exports required for `from little_loops.fsm import ParallelRunner, ParallelResult`:** Current `__init__.py:143-195` `__all__` does **not** include any parallel types. FEAT-1075 step 8 must add them — without that, the import used by this test file will fail. If FEAT-1075 ships without the export step, either patch the import to `from little_loops.fsm.parallel_runner import ...` (direct) or file a follow-up.

#### Contract Updates Since Initial Refinement

_Added 2026-04-21 — reflects FEAT-1075 design changes captured after the previous refinement pass. These supersede any conflicting guidance above; test bodies must use the current contract._

- **`error` field is a `ParallelItemError` dataclass, not a string** (FEAT-1075:20, 59, 77). The edge-case assertion "1 item fails of 1 → `result.failed[0].error` is non-empty string" is **out of date**. Replace with: `isinstance(result.failed[0].error, ParallelItemError) and result.failed[0].error.kind in {"verdict_failure", "exception"}`. `ParallelItemError` fields: `kind`, `message`, `exc_type`. Import from `little_loops.fsm.parallel_runner` (direct, already in import block above).

- **`concurrent.futures.TimeoutError`, NOT builtin `TimeoutError`** (FEAT-1075:426, 457). The `timeout_seconds` test's mocked worker must raise `concurrent.futures.TimeoutError` (or the mocked `future.result(timeout=...)` must raise it). The runner catches that specific class and classifies as `ParallelItemError(kind="timeout", exc_type="TimeoutError", ...)`. Do NOT use the builtin; they are distinct classes and a misuse will silently bypass the runner's handler and surface as an `exception`-kind error instead.

- **`fail_fast` cancelled-slot sentinel shape** (FEAT-1075:116, 352). The `Thread mode fail_fast` test must assert not just that remaining futures were cancelled but that cancelled slots are materialized as `ParallelItemResult(verdict="no", terminated_by="cancelled", error=ParallelItemError(kind="cancelled", ...), ...)` with `len(result.all_results) == len(items)` preserved. Position-preserving slots are the contract, not just cancellation.

- **Scope question — 3 additional test cases defined by FEAT-1075 acceptance criteria:** FEAT-1075:380-382 names three tests that are mocking-friendly (no real threading needed) and therefore land most naturally in this suite:
  - `test_parallel_runner_invokes_on_worker_complete_per_worker` — callback invoked once per worker from the runner's main thread (capture `threading.current_thread()` in callback).
  - `test_parallel_runner_on_worker_complete_exception_is_swallowed` — callback raises; fan-out still completes; WARN log produced.
  - `test_parallel_runner_starting_item_index_offsets_absolute_index` — call with `items=["c", "d"]`, `starting_item_index=3`; assert `all_results[0].item_index == 3`, `all_results[1].item_index == 4`.
  
  If kept here, the case count goes from 8 → 11. Alternative: park in FEAT-1203 (real threading) or a separate follow-up. Flag for human decision during implementation — the surfaces (`on_worker_complete`, `starting_item_index`) are in the `ParallelRunner.run()` signature per FEAT-1075:99-100, so they will exist when FEAT-1075 ships.

- **Per-kind `ParallelItemError` classification tests** (FEAT-1075:379) — one test per `kind` value (`timeout`, `exception`, `verdict_failure`, `cancelled`) asserting both `kind` and `exc_type` are set correctly. These can be folded into the existing 8 test cases above (each already exercises one kind) or added as a single parameterized test; no new separate test class needed.

- **`ParallelItemError` is serialized as a plain dict when persisted into captures** (FEAT-1075:359): `{"kind": ..., "message": ..., "exc_type": ...}`. That serialization happens at the FEAT-1076 dispatch boundary, NOT inside `ParallelRunner`. Inside this mocked suite `error` is the live dataclass instance — do not assert dict form here.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md:26` — states "~50 test modules"; adding `test_parallel_runner.py` increments this count [Agent 2 finding]
- `docs/development/TESTING.md:117` — states "50+ modules" in directory-tree diagram; same count drift [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml:133` — `fail_under = 80` coverage threshold applies to `little_loops.fsm.parallel_runner` once the source file exists (FEAT-1075). The 8 test cases in `TestParallelRunner` must provide ≥80% line coverage of `parallel_runner.py` or the full suite run will fail [Agent 2 finding]

## Dependencies

- **FEAT-1075** must be complete (`ParallelRunner` implementation)
- **FEAT-1074** must be complete (`ParallelStateConfig` schema)

## Acceptance Criteria

- `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunner -x` passes green
- All 8 core test cases pass (including both edge cases)
- `test_parallel_runner_context_passthrough_is_deep_copy_per_worker` asserts independent deep copies
- `test_parallel_runner_preserves_item_order_under_async_completion` asserts order preservation with out-of-order completion timestamps
- No `pytestmark` at module level (class-level markers only for integration tests added later)

## Labels

`fsm`, `parallel`, `tests`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. After `test_parallel_runner.py` is created and passing, update `docs/development/TESTING.md:26` and `:117` to reflect the incremented test module count
2. Confirm that the 8 test cases provide ≥80% line coverage of `scripts/little_loops/fsm/parallel_runner.py` — run `python -m pytest scripts/tests/test_parallel_runner.py --cov=little_loops.fsm.parallel_runner --cov-report=term-missing` to verify before declaring done

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-04-21 (originally 2026-04-20)_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1074 not landed**: `ParallelStateConfig` is absent from `scripts/little_loops/fsm/schema.py` — imports in the new test file will fail at pytest collection time until this lands.
- **FEAT-1075 not landed**: `scripts/little_loops/fsm/parallel_runner.py` does not exist — `ParallelRunner`, `ParallelResult`, `ParallelItemResult`, `ParallelItemError` are unavailable; the test class cannot be written or verified.
- **Scope question (minor)**: 3 extra test cases from FEAT-1075 acceptance criteria (`on_worker_complete` callback, exception-swallowed callback, `starting_item_index` offset) have no placement decision — flag for resolution at implementation start.

## Session Log
- `/ll:refine-issue` - 2026-04-21T03:02:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/07623ac5-5513-4145-aea8-be71852f8e8c.jsonl`
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/adf19c3d-af16-4568-99a4-72ac7ad42433.jsonl`
- `/ll:wire-issue` - 2026-04-21T02:58:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86381121-9ca4-4fa8-8a67-27c9fa03a53f.jsonl`
- `/ll:refine-issue` - 2026-04-21T02:54:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b3b8d4aa-c1fc-49e8-825b-5fcfad583404.jsonl`
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee39c2da-53b6-4990-b649-6f5e43993562.jsonl`
