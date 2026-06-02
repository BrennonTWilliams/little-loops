---
discovered_date: "2026-04-20"
discovered_by: issue-size-review

size: Very Large
confidence_score: 80
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
parent: FEAT-1203
status: done
completed_at: 2026-05-10T00:00:00Z
---

# FEAT-1206: TestParallelRunnerRealThreading — Fail Fast + Timeout Tests

## Summary

Add 2 tests to `TestParallelRunnerRealThreading` in `scripts/tests/test_parallel_runner.py`:
`test_real_threads_fail_fast_cancels_pending` and `test_real_threads_timeout_one_while_others_complete`.

## Parent Issue

Decomposed from FEAT-1203: TestParallelRunnerRealThreading — Real-Threading Concurrency Tests

## Use Case

**Who**: Developer completing FEAT-1075 (`ParallelRunner` implementation)

**Context**: After FEAT-1205 adds the isolation/concurrency tests to `TestParallelRunnerRealThreading`, this issue adds the failure/termination mode tests to the same class.

**Goal**: Add 2 real-threading tests to `TestParallelRunnerRealThreading` class in `scripts/tests/test_parallel_runner.py`. Class-level `@pytest.mark.integration` must be present (added by FEAT-1205 or this issue if FEAT-1205 runs first). MUST run in default CI — NOT gated behind `@pytest.mark.slow`.

**Outcome**: `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_fail_fast_cancels_pending scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_timeout_one_while_others_complete -x` passes green.

## Proposed Solution

### Add to existing file: scripts/tests/test_parallel_runner.py

Both tests go inside `TestParallelRunnerRealThreading` (class-level `@pytest.mark.integration`). Use real `ThreadPoolExecutor` (no mocks on executor layer).

**`test_real_threads_fail_fast_cancels_pending`** — 10 items, `fail_mode: "fail_fast"`, item 2 fails. Track how many worker bodies actually started (shared counter under `threading.Lock`). Assert counter < 10.

Implementation recipe:
```python
lock = threading.Lock()
started_count = 0

def worker_body(item, context):
    nonlocal started_count
    with lock:
        started_count += 1
    if item == items[2]:
        raise RuntimeError("forced failure")
    time.sleep(0.1)
```

Assert: `started_count < 10` after run completes.

**`test_real_threads_timeout_one_while_others_complete`** — 4 workers, `timeout_seconds=1`, worker 2 (index 2) sleeps 5s. Assert:
- `result.all_results[2].terminated_by == "timeout"`
- `result.all_results[2].error.kind == "timeout"`
- `result.all_results[0].verdict == "yes"` and `result.all_results[1].verdict == "yes"` and `result.all_results[3].verdict == "yes"` (workers 0/1/3 complete normally)
- `result.verdict == "partial"` (mixed: 3 success + 1 timeout)

Note: FEAT-1075 uses `concurrent.futures.TimeoutError` (NOT built-in `TimeoutError`) when enforcing `timeout_seconds` via `future.result(timeout=...)`. Timed-out workers get `ParallelItemResult(verdict="no", terminated_by="timeout", error=ParallelItemError(kind="timeout", ...))`. The overall verdict is `"partial"` (mixed success/failure).

Individual timeouts: worker 2 uses `time.sleep(5)` inside worker body; `timeout_seconds=1` in `ParallelStateConfig` causes the runner to treat it as timed-out. Other workers use `time.sleep(0.1)` or no sleep to complete quickly.

### Implementation Notes

- Apply `@pytest.mark.integration` at **class** level (NOT module-level `pytestmark`). If FEAT-1205 already created the class with the marker, just add methods.
- `integration` marker runs in default CI (`scripts/pyproject.toml:113-116`). Do NOT use `@pytest.mark.slow`.
- Both tests should complete in < 15s total (timeout test: worker 2 hits `timeout_seconds=1` ceiling, not the full 5s sleep).
- `ParallelResult.verdict` values: `"yes"` (all workers `verdict == "yes"`), `"no"` (all failed), `"partial"` (mixed).
- `all_results` ordering guarantee: FEAT-1075 pre-allocates by slot — `all_results[i]` always corresponds to `items[i]`. Safe for index-based assertions.
- `ParallelResult` shape: `all_results: list[ParallelItemResult]`, `succeeded` (property), `failed` (property). Do NOT assert against `all_captures` (old API shape) — translate to `[r.captures for r in result.all_results]` if needed.
- **API-shape resolution note**: FEAT-1075's own issue document contains two conflicting shapes for `ParallelResult.succeeded`/`failed` — an older `list[str]` field shape and a newer `@property` returning `list[ParallelItemResult]`. FEAT-1203's research resolved the `@property` form as authoritative. FEAT-1206's tests assert per-item via `result.all_results[i].verdict`, so they do not depend on `.succeeded`/`.failed` shape — but if you add adjacent assertions, use the property form.

## Integration Map

### Files to Modify
- `scripts/tests/test_parallel_runner.py` — Add 2 tests to `TestParallelRunnerRealThreading`

### Dependent Files (under test / needed first)
- `scripts/little_loops/fsm/parallel_runner.py` — Implementation under test (FEAT-1075)
- `scripts/little_loops/fsm/schema.py` — provides `ParallelStateConfig` (FEAT-1074)
- `scripts/little_loops/fsm/__init__.py` — exports `ParallelRunner`, `ParallelItemResult`, `ParallelResult`, `ParallelItemError` (FEAT-1075)
- FEAT-1202 must be complete (creates `test_parallel_runner.py`)
- FEAT-1205 should be complete (creates `TestParallelRunnerRealThreading` class with marker)

### Similar Patterns (copy from)
- `scripts/tests/test_git_lock.py:462-479` — 20 threads, counter assertion (deadlock-free many-thread sanity) — template for the fail-fast counter pattern
- `scripts/tests/test_concurrency.py:333-355` — `threading.Barrier(N)` for simultaneous-start races — useful for coordinating the timeout test setup
- `scripts/tests/test_goals_parser.py:437-438` — class-level `@pytest.mark.integration` in mixed file (the only class-level marker in the suite; all other integration files use module-level `pytestmark`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Additional patterns (supplementary to the copy-from list above):**
- `scripts/tests/test_state.py:426-436` — `ThreadPoolExecutor(max_workers=5) as executor` + `as_completed(futures)` drain pattern. Useful as a reference shape for anyone sanity-checking how the runner's internal executor should be exercised, though FEAT-1206 does NOT construct a `ThreadPoolExecutor` directly — it drives the runner, which owns the executor.
- `scripts/tests/test_worker_pool.py:461-462` — `future.result(timeout=5)` blocking pattern. Matches the runner-internal timeout path (FEAT-1075 catches `concurrent.futures.TimeoutError` from `future.result(timeout=...)` and translates it into `terminated_by="timeout"`).
- `scripts/tests/test_git_lock.py:395-419` — lock-protected timing-pair list. Alternative to the counter pattern if you later want to assert ordering; not needed for FEAT-1206's two tests.

**Counter idiom choice (fail-fast test):** The recipe in the Proposed Solution uses `nonlocal started_count`. The established idiom at `test_git_lock.py:462-479` instead uses a mutable `counter = [0]` list captured by closure. Either works; the list-wrapping form matches the existing codebase convention and avoids the `nonlocal` keyword in the inner function.

_Second refinement pass (2026-04-20) — additional structural anchors:_

- `scripts/tests/test_hooks_integration.py:1041` — real `ThreadPoolExecutor(max_workers=5)` with "not all N succeeded" count assertion (`denied_count >= 4`). Closest existing structural template for the fail-fast test's "fewer than 10 workers started" count-assertion shape. Uses real subprocess work (no mocks on executor layer) and asserts an inequality on a shared counter — same shape FEAT-1206 needs.
- **Novelty flag (list-indexed per-item outcome assertions)**: A full-suite scan found **no existing test** that asserts `terminated_by == "timeout"` on a list-indexed per-item result (e.g., `result.all_results[i].terminated_by`). The precedents cited above (`test_fsm_executor.py:2033-2037`, `test_fsm_persistence.py:868`) all operate on a single scalar result. Similarly, `verdict == "partial"` is asserted only on a scalar in `test_fsm_evaluators.py:627` — never on a list-indexed shape. FEAT-1206's timeout test is the first to assert these strings on `ParallelResult.all_results[i]`. Not a blocker, just be prepared to get the field-path right on the first try rather than copy-adapting.
- **Dependency status re-verified 2026-04-20**: FEAT-1074, FEAT-1075, FEAT-1202 still unimplemented. `fsm/parallel_runner.py` absent; `schema.py` contains no `ParallelStateConfig`/`fail_mode`/`timeout_seconds`/`max_workers`; `tests/test_parallel_runner.py` absent. The only parallel-adjacent test file present is `tests/test_parallel_types.py`, which covers the unrelated worktree-orchestrator types in `little_loops/parallel/types.py` (not the FSM parallel runner). No change to the hard-block chain described in the Dependencies section.

_Wiring pass added by `/ll:wire-issue`:_

**`terminated_by == "timeout"` assertion syntax** (for the timeout test):
- `scripts/tests/test_fsm_executor.py:2033-2037` — asserts `result.terminated_by == "timeout"` on `ExecutionResult`; the parallel analogue is `result.all_results[2].terminated_by == "timeout"` on `ParallelItemResult`. Structurally identical string assertion, different dataclass.
- `scripts/tests/test_fsm_persistence.py:868` — `assert result.terminated_by == "timeout"` on `PersistentExecutor` result; same string value, different layer.

**`verdict == "partial"` assertion syntax** (for the timeout test's overall result):
- `scripts/tests/test_fsm_evaluators.py:620-627` — `assert result.verdict == "partial"` on `EvaluationResult`; the parallel analogue is `assert result.verdict == "partial"` on `ParallelResult`. String value is shared across both FSM evaluator and parallel runner domains.

**Coverage gate risk**: `scripts/pyproject.toml:133` sets `fail_under = 80`. FEAT-1202's 8 mocked unit tests cover the happy path and basic error branches of `parallel_runner.py`. FEAT-1206's 2 real-threading tests fill the `fail_fast` cancellation path and the `concurrent.futures.TimeoutError` → `terminated_by="timeout"` translation path — branches that mocks cannot exercise. If coverage falls below 80 after FEAT-1202 lands but before FEAT-1206, CI will fail at the coverage gate. Run with `--no-cov` locally if iterating on FEAT-1202 independently.

## Dependencies

- **FEAT-1074** must be complete (`ParallelStateConfig` in `schema.py`)
- **FEAT-1075** must be complete (`ParallelRunner` implementation + `fsm/__init__.py` exports)
- **FEAT-1202** must be complete (creates `test_parallel_runner.py`)
- **FEAT-1205** should be complete (creates `TestParallelRunnerRealThreading` class with marker)

### Current Dependency Status (verified 2026-04-20)

| Dependency | Artifact | Status |
|---|---|---|
| FEAT-1074 | `ParallelStateConfig` in `scripts/little_loops/fsm/schema.py` | NOT IMPLEMENTED (schema.py has `EvaluateConfig`, `RouteConfig`, `StateConfig`, `LLMConfig`, `LoopConfigOverrides`, `FSMLoop`; no `ParallelStateConfig`) |
| FEAT-1075 | `scripts/little_loops/fsm/parallel_runner.py` + exports in `fsm/__init__.py` | NOT IMPLEMENTED (file does not exist; grep for `ParallelRunner` returns zero matches) |
| FEAT-1202 | `scripts/tests/test_parallel_runner.py` | NOT IMPLEMENTED (file does not exist) |
| FEAT-1205 | `TestParallelRunnerRealThreading` class with class-level `@pytest.mark.integration` | NOT IMPLEMENTED (FEAT-1205 appears in `.issues/completed/` but resolved as "Decomposed" — planning milestone, not code) |

**Implication**: FEAT-1206 is hard-blocked on the full chain. Any attempt to collect these tests today would fail at import time (`little_loops.fsm.parallel_runner` unresolvable). If FEAT-1205 has not landed by the time FEAT-1206 is picked up, FEAT-1206 must create the `TestParallelRunnerRealThreading` class itself with the class-level marker.

## Acceptance Criteria

- `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_fail_fast_cancels_pending -x` passes green
- `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_timeout_one_while_others_complete -x` passes green
- Both tests run in default CI (class-level `@pytest.mark.integration`, no `@pytest.mark.slow`)
- `test_real_threads_fail_fast_cancels_pending` asserts fewer than 10 workers started
- `test_real_threads_timeout_one_while_others_complete` asserts worker 2 timed-out, workers 0/1/3 complete, verdict `"partial"`

## Labels

`fsm`, `parallel`, `tests`, `integration`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-20_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- **All four dependencies unresolved**: FEAT-1074 (`ParallelStateConfig`), FEAT-1075 (`ParallelRunner`), and FEAT-1202 (creates `test_parallel_runner.py`) are active issues with no implementation in the codebase. Tests cannot be collected by pytest without the production module in place.
- **FEAT-1205 is planning-only**: It was resolved as "Decomposed" — `TestParallelRunnerRealThreading` class does not exist. If FEAT-1205 hasn't landed as code by the time FEAT-1206 is picked up, FEAT-1206 must create the class with the class-level marker itself (the issue already accounts for this in the Implementation Notes).

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-20
- **Reason**: Issue too large for single session

### Decomposed Into
- FEAT-1209: TestParallelRunnerRealThreading — Fail Fast Cancellation Test
- FEAT-1210: TestParallelRunnerRealThreading — Timeout Per-Item Test

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-21T04:29:03 - `f84bc5fa-3fa1-4822-8f5a-25670ac913a0.jsonl`
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `f84bc5fa-3fa1-4822-8f5a-25670ac913a0.jsonl`
- `/ll:confidence-check` - 2026-04-21T05:00:00 - `69b939e3-2896-4279-b3ea-8328e8e1c023.jsonl`
- `/ll:refine-issue` - 2026-04-21T04:23:46 - `66364a66-e97f-4af0-a258-69e7737504ed.jsonl`
- `/ll:wire-issue` - 2026-04-21T04:19:21 - `56c2a151-a828-48a2-859f-a74fb4ffad74.jsonl`
- `/ll:refine-issue` - 2026-04-21T04:14:42 - `d0419d06-3d45-4aed-8539-389c50e1cd76.jsonl`
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `2ed5d9eb-8026-4655-8ff3-63958b109e67.jsonl`
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `ffa52965-8df7-4476-a2af-96e098002a6a.jsonl`
