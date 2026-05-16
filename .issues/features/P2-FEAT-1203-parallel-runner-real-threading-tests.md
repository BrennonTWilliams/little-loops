---
discovered_date: "2026-04-20"
discovered_by: issue-size-review

size: Very Large
confidence_score: 78
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
parent: FEAT-1199
status: done
completed_at: 2026-05-10T00:00:00Z
---

# FEAT-1203: TestParallelRunnerRealThreading — Real-Threading Concurrency Tests

## Summary

Add `TestParallelRunnerRealThreading` to `scripts/tests/test_parallel_runner.py` — 4 integration-marked tests using real `ThreadPoolExecutor` (no mocks) to verify actual concurrency behavior.

## Parent Issue

Decomposed from FEAT-1199: Parallel Runner Unit Tests (test_parallel_runner.py)

## Use Case

**Who**: Developer completing FEAT-1075 (`ParallelRunner` implementation)

**Context**: After FEAT-1202 creates the file with `TestParallelRunner`, this issue adds `TestParallelRunnerRealThreading` to the same file. These tests run in default CI and verify thread scheduling actually works.

**Goal**: Add `TestParallelRunnerRealThreading` class to `scripts/tests/test_parallel_runner.py` with 4 real-threading tests. MUST run in default CI — NOT gated behind `@pytest.mark.slow`. Apply `@pytest.mark.integration` at class level.

**Outcome**: `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading -x` passes green in < 30s total.

## Proposed Solution

### Add to existing file: scripts/tests/test_parallel_runner.py

#### Class: TestParallelRunnerRealThreading

Apply `@pytest.mark.integration` at class level. Use real `ThreadPoolExecutor` (no mocks on executor layer). All 4 tests use `time.sleep` deliberately to exercise actual thread scheduling.

Test cases:

- **`test_real_threads_deep_copy_isolates_mutations`** — 4 real workers each mutate nested structures in their context. Assert each worker's mutations land only in its own `ParallelItemResult.captures` and the parent dict is unchanged. (Complements the mocked version in FEAT-1202 with real thread scheduling.)

- **`test_real_threads_max_workers_enforced`** — 20 items, `max_workers=2`. Each worker records start timestamp into a `threading.Lock`-protected list. After run, assert at most 2 timestamps overlap at any point. Adapt pattern from `scripts/tests/test_git_lock.py:421-460` — use timestamp pairs `(start, end)` per worker and count concurrent overlaps in post-hoc analysis.

- **`test_real_threads_fail_fast_cancels_pending`** — 10 items, `fail_mode: fail_fast`, item 2 fails. Track how many worker bodies actually started (shared counter). Assert counter < 10.

- **`test_real_threads_timeout_one_while_others_complete`** — 4 workers, `timeout_seconds=1`, worker 2 sleeps 5s. Assert worker 2 is timed-out, workers 0/1/3 complete normally, overall verdict is `"partial"`.

Target: all 4 tests complete in < 30s total (individual timeouts: `timeout_seconds=1` for the timeout test; `time.sleep` calls should use minimal values like 0.1–0.5s for coordination).

### Implementation Notes

- Apply `@pytest.mark.integration` at **class** level (NOT module level `pytestmark`) — `TestParallelRunner` (FEAT-1202) is not integration-marked.
- `integration` marker runs in default CI (`scripts/pyproject.toml:113-116`). Do NOT use `@pytest.mark.slow`.
- Max-workers overlap detection: use `(start_time, end_time)` pairs per worker recorded under a `threading.Lock`. Post-hoc: for each pair of workers, check if their intervals overlap; assert max overlap count ≤ `max_workers`.
- `fail_fast` counter: use a `threading.Lock`-protected integer incremented at the top of each worker body before any business logic.

## Integration Map

### Files to Modify
- `scripts/tests/test_parallel_runner.py` — Add class; file created by FEAT-1202

### Dependent Files (under test / needed first)
- `scripts/little_loops/fsm/parallel_runner.py` — Implementation under test (FEAT-1075)
- FEAT-1202 must be complete (file must exist with `TestParallelRunner`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/schema.py` — provides `ParallelStateConfig` constructed in every test; must exist and export `ParallelStateConfig` (FEAT-1074)
- `scripts/little_loops/fsm/__init__.py` — must export `ParallelRunner`, `ParallelItemResult`, `ParallelResult`, `ParallelItemError` before the test file can be collected (FEAT-1075 step 8)

### Similar Patterns (copy from)
- `scripts/tests/test_state.py:409-435` — `TestStateConcurrency.test_concurrent_save_no_corruption` — `ThreadPoolExecutor` + `as_completed` real-threading
- `scripts/tests/test_git_lock.py:395-419` — `threading.Lock`-protected list of enter/exit pairs
- `scripts/tests/test_git_lock.py:421-460` — max-workers overlap detection with `threading.Event` pinning
- `scripts/tests/test_git_lock.py:462-479` — 20 threads, counter assertion (deadlock-free many-thread sanity)
- `scripts/tests/test_concurrency.py:333-355` — `threading.Barrier(N)` for simultaneous-start races
- `scripts/tests/test_worker_pool.py:1-110` — closest sibling (orchestrator-layer `WorkerPool`); use fixture-chain shape as template but keep imports targeted at FSM `ParallelRunner`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-04-20):_

**Verified references (no corrections needed):**
- All 6 file:line patterns referenced in "Similar Patterns" are accurate as-written.
- `scripts/pyproject.toml:113-116` confirmed — `integration` marker registered, runs in default CI; `slow` marker excluded by default.

**ParallelRunner API surface (from FEAT-1075 spec, needed to write these tests):**
- Instantiation: `ParallelRunner()` — no constructor arguments.
- Entry point: `run(items: list[str], loop_name: str, config: ParallelStateConfig, parent_context: dict | None = None, on_worker_complete: Callable[[ParallelItemResult], None] | None = None, starting_item_index: int = 0) -> ParallelResult`.
- `on_worker_complete` fires from the main thread (not worker threads); callback exceptions are caught and swallowed.

**`ParallelItemResult` shape (FEAT-1075):** `item: str`, `item_index: int`, `verdict: "yes" | "no" | "partial"`, `terminated_by: "terminal" | "error" | "timeout" | "signal" | "max_iterations" | "handoff" | "cancelled"`, `captures: dict`, `error: ParallelItemError | None`. Tests should assert on these exact field names and string values.

**`ParallelResult.verdict` values:** `"yes"` (all workers `verdict == "yes"`), `"no"` (all failed), `"partial"` (mixed). The `test_real_threads_timeout_one_while_others_complete` assertion target `"partial"` in the existing spec is correct.

**`fail_mode` enum (FEAT-1074):** `"collect"` (default) | `"fail_fast"`. Use `"fail_fast"` literal string for the fail-fast test (the issue already says `fail_mode: fail_fast`; confirmed correct).

**Class-level marker precedent:** `scripts/tests/test_goals_parser.py:437` applies `@pytest.mark.integration` at class level in an otherwise-unmarked file — direct template for mixing `TestParallelRunner` (unmarked) and `TestParallelRunnerRealThreading` (marked) in one file. All other integration test files use module-level `pytestmark` instead.

**Timeout test nuance:** FEAT-1075 specifies the runner uses `concurrent.futures.TimeoutError` (NOT built-in `TimeoutError`) when enforcing `timeout_seconds` via `future.result(timeout=...)`. Timed-out workers get `ParallelItemResult(verdict="no", terminated_by="timeout", error=ParallelItemError(kind="timeout", ...))`. For `test_real_threads_timeout_one_while_others_complete`, assert `terminated_by == "timeout"` on worker 2 and confirm `error.kind == "timeout"`.

**`all_results` ordering guarantee:** FEAT-1075 pre-allocates `all_results` by slot (NOT by `as_completed()` order). `all_results[i]` always corresponds to `items[i]` — safe for index-based assertions in `test_real_threads_timeout_one_while_others_complete`.

_Second refinement pass — 2026-04-20:_

**Pattern-reference corrections (override prior entries in "Similar Patterns"):**
- `scripts/tests/test_git_lock.py:395-419` — prior label (`threading.Lock`-protected list of enter/exit pairs) is inaccurate. Actual content: `test_concurrent_operations_serialize` using a `threading.Lock`-protected `execution_order: list[int]` where adjacent pairs `[i, i+1]` must share the same id (serialization, not enter/exit strings). Still useful as a lock-protected shared-list pattern — but for the max-workers overlap test, record `(start_time, end_time)` tuples directly per the Implementation Notes, do NOT attempt to copy enter/exit strings from this range.
- `scripts/tests/test_git_lock.py:421-460` — prior label ("max-workers overlap detection with `threading.Event` pinning") is inaccurate. Actual content: `test_second_thread_waits_for_first` — a 2-thread FIFO-ordering check using `threading.Event` pairs (`first_started`, `first_can_finish`, `second_started`). There is **no existing max-workers overlap detection test in the repo**; `test_real_threads_max_workers_enforced` is greenfield on that axis. Follow the Implementation Notes recipe (record `(start, end)` pairs under a `threading.Lock`, post-hoc count overlapping intervals) rather than copying from test_git_lock.py.
- Other 4 pattern references (`test_state.py:409-435`, `test_git_lock.py:462-479`, `test_concurrency.py:333-355`, `test_goals_parser.py:437`) — verified accurate as-written.

**Deep-copy test target correction (affects `test_real_threads_deep_copy_isolates_mutations`):**
The prior Proposed Solution says workers "mutate nested structures in their context" and assert mutations "land only in its own `ParallelItemResult.captures`". This mixes two directions. FEAT-1075 (lines 138-150) specifies the deep-copy contract is **parent → worker**: each worker receives a `copy.deepcopy(parent_context)` so worker-side mutations cannot bleed into the shared parent. The correct test shape:
1. Pass a `parent_context` dict containing nested mutable structures (e.g., `{"shared": {"counter": 0, "list": []}}`).
2. Each of 4 real worker threads mutates its *received* `parent_context` (via whatever seam FEAT-1075 exposes — typically passed into the mocked `FSMExecutor.run()`).
3. Assert the original `parent_context` passed to `runner.run(...)` is unchanged after the run (no bleed into parent).
4. `captures` is populated from `child FSMExecutor.captured at exit` (FEAT-1075 line 76) — it is an *output* of each worker, not the shared-state under test for deep-copy isolation. Asserting per-worker `captures[i]` contains only that worker's mutation is a secondary check, not the primary isolation invariant.

**`max_workers` source assumption:**
FEAT-1075 `ThreadPoolExecutor(max_workers=N, ...)` does not explicitly cite `N = config.max_workers`, but the acceptance-criteria phrasing "`max_workers: 2`" implies it is a `ParallelStateConfig` field owned by FEAT-1074. These tests assume `ParallelStateConfig(max_workers=2, ...)` wires through to the executor. If FEAT-1074 names the field differently (e.g., `concurrency`, `workers`), adjust constructor calls in all 4 tests accordingly.

**`loop_name` sentinel for tests:**
FEAT-1075 (lines 373, 406) directs unit tests to mock `FSMExecutor.run()` directly — bypassing loop-definition file resolution. For these real-threading tests:
- If mocking at the `FSMExecutor.run` seam (recommended), `loop_name` can be any string like `"test_loop"`.
- If exercising the real loop-path resolution, tests must materialize a minimal `.loops/<loop_name>.fsm.yaml` under `tmp_path` and wire `loops_dir` through config/env. The spec does not require the real path; stick with the mocked seam.

**FEAT-1075 self-contradiction warning:**
FEAT-1075 contains two conflicting API shapes for `ParallelResult` — the older `## API/Interface` block (`succeeded: list[str]`, `failed: list[str]`, `all_captures: list[dict]`) and the newer `## Proposed Solution` block (`all_results: list[ParallelItemResult]` with `succeeded`/`failed` as `@property`). FEAT-1075's Acceptance Criteria confirm the newer shape is authoritative. These tests must target `all_results`, `succeeded` (property), and `failed` (property). Any assertion phrased against `all_captures` should be translated to `[r.captures for r in result.all_results]`.

## Dependencies

- **FEAT-1074** must be complete (defines `ParallelStateConfig` in `scripts/little_loops/fsm/schema.py` — needed by every test)
- **FEAT-1075** must be complete (`ParallelRunner` implementation and `fsm/__init__.py` exports for all 4 symbols)
- **FEAT-1202** must be complete (creates `test_parallel_runner.py`)

## Acceptance Criteria

- `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading -x` passes green
- All 4 tests run in default CI (class-level `@pytest.mark.integration`, no `@pytest.mark.slow`)
- `test_real_threads_max_workers_enforced` asserts ≤ 2 concurrent workers at any point
- `test_real_threads_fail_fast_cancels_pending` asserts fewer than 10 workers started
- `test_real_threads_timeout_one_while_others_complete` asserts worker 2 timed-out, others complete, verdict `"partial"`

## Labels

`fsm`, `parallel`, `tests`, `integration`

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-04-20_

**Readiness Score**: 78/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- **All three critical dependencies remain unresolved** — FEAT-1074 (`ParallelStateConfig` in `schema.py`), FEAT-1075 (`ParallelRunner` implementation + `fsm/__init__.py` exports), and FEAT-1202 (creates `test_parallel_runner.py`) are all still active issues. None appear in `.issues/completed/`. Neither `parallel_runner.py` nor `test_parallel_runner.py` exists in the codebase.
- Do not begin this issue until all three predecessors are complete. The test file cannot be collected by pytest without the production module in place.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-20
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-1205: TestParallelRunnerRealThreading — Deep Copy + Max Workers Tests
- FEAT-1206: TestParallelRunnerRealThreading — Fail Fast + Timeout Tests

## Session Log
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2ed5d9eb-8026-4655-8ff3-63958b109e67.jsonl`
- `/ll:refine-issue` - 2026-04-21T03:19:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d3d655e9-2b80-4758-b8d2-61a85ff1693e.jsonl`
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/628aabf4-d66c-4fb0-b275-6946311dcfc7.jsonl`
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6f87ed8a-22e1-4fb3-8418-fd0b638c6558.jsonl`
- `/ll:wire-issue` - 2026-04-21T03:14:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38e7a9d0-9262-4670-8ac7-28934af36866.jsonl`
- `/ll:refine-issue` - 2026-04-21T03:10:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7cfd1ec1-906d-4e09-af52-188f7454ffcb.jsonl`
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee39c2da-53b6-4990-b649-6f5e43993562.jsonl`
