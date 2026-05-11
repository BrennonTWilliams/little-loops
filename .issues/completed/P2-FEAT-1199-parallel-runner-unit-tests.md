---
discovered_date: "2026-04-20"
discovered_by: issue-size-review

size: Very Large
confidence_score: 80
outcome_confidence: 86
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
parent: FEAT-1077
---

# FEAT-1199: Parallel Runner Unit Tests (test_parallel_runner.py)

## Summary

Create `scripts/tests/test_parallel_runner.py` with all unit tests for `ParallelRunner`: mocked-executor fast suite, real-threading concurrency tests, singleton safety tests, and the `items_hash` resume-warning test.

## Parent Issue

Decomposed from FEAT-1077: Parallel State Tests

## Use Case

**Who**: Developer completing FEAT-1075 (`ParallelRunner` implementation)

**Context**: Once `ParallelRunner` exists, this new test file provides full unit coverage for it.

**Goal**: Create `scripts/tests/test_parallel_runner.py` (flat in `scripts/tests/`, no subdirectory) with four test classes covering all `ParallelRunner` behavior.

**Outcome**: `python -m pytest scripts/tests/test_parallel_runner.py -x` passes green.

## Proposed Solution

### New file: scripts/tests/test_parallel_runner.py

#### Core unit tests (TestParallelRunner — mocked FSMExecutor)

- Thread mode: mock sub-loop runs, verify captures collected, verdict derived correctly
- Thread mode `fail_fast`: verify remaining futures cancelled on first failure
- Worktree mode: mock worktree setup/teardown, verify merge-back called
- `context_passthrough: true`: verify parent context passed to each worker
- `test_parallel_runner_context_passthrough_is_deep_copy_per_worker` — pass a `parent_context` with nested mutable structures (`{"items": ["a", "b"], "meta": {"count": 0}}`). Spawn N (≥4) workers each mutating their nested structures. Assert: (a) each worker's mutations visible only in its own `ParallelItemResult.captures`, (b) sibling workers see no mutations from each other in their initial context, (c) parent's original dict is byte-for-byte unchanged (including nested containers — check identity with `is not`).
- `test_parallel_runner_preserves_item_order_under_async_completion` — 4 items with durations `[3.0, 1.0, 2.0, 0.5]` (inverted). Assert `result.all_results[i].item == items[i]` and `item_index == i` for all `i`; assert completion timestamps are out of order.
- `timeout_seconds`: worker exceeding timeout records `ParallelItemResult(verdict="no", terminated_by="timeout", error="...")` aggregated under `fail_mode`; `timeout_seconds=None` means no timeout enforced
- Edge: 0 items → immediate `ParallelResult(all_results=[], verdict="yes")` (assert `.succeeded == [] and .failed == []`)
- Edge: 1 item fails of 1 → `result.all_results[0].verdict == "no"`; `result.verdict == "no"`; `result.failed[0].error` is non-empty string

#### Real-threading concurrency tests (TestParallelRunnerRealThreading)

Use real `ThreadPoolExecutor` (no mocks). MUST run in default CI — NOT gated behind `@pytest.mark.slow`. Tagging with `@pytest.mark.integration` is permitted (that marker runs by default).

- `test_real_threads_deep_copy_isolates_mutations` — 4 real workers each mutate nested structures in their context. Assert each worker's mutations land only in its own `ParallelItemResult.captures` and the parent dict is unchanged.
- `test_real_threads_max_workers_enforced` — 20 items, `max_workers=2`. Each worker records start timestamp into a `threading.Lock`-protected list. After run, assert at most 2 timestamps overlap at any point.
- `test_real_threads_fail_fast_cancels_pending` — 10 items, `fail_mode: fail_fast`, item 2 fails. Track how many worker bodies actually started (shared counter). Assert counter < 10.
- `test_real_threads_timeout_one_while_others_complete` — 4 workers, `timeout_seconds=1`, worker 2 sleeps 5s. Assert worker 2 is timed-out, workers 0/1/3 complete normally, overall verdict is `"partial"`.

All four tests use `time.sleep` deliberately in worker bodies to exercise actual thread scheduling (target < 5s total).

#### Singleton safety tests (TestParallelRunnerSingletonSafety)

Real `ThreadPoolExecutor`, ≥4 workers, light real workloads:

- `test_parent_checkpoint_file_not_written_from_worker_threads` — instrument `PersistentExecutor._save_state()` with `threading.get_ident()` check; assert every call came from the main thread's TID.
- `test_worker_session_jsonl_writes_are_one_line_atomic` — 4 workers each write 50 events into session JSONL files; after run, `json.loads()` each line; assert every line parses cleanly.
- `test_config_snapshot_is_read_only_from_worker_threads` — mock `BRConfig.load()` to record thread IDs; assert load-call TID is only the main thread's.
- `test_module_level_caches_not_lazily_written_from_workers` — for each module-level cache the runner depends on, assert cache size is identical before and after `runner.run()` with a pre-warmed cache.

#### Resume-warning test (folded from FEAT-1174)

- `test_items_hash_mismatch_warning_is_prominent` — suspend a parallel state mid-run, mutate the `items` source on disk, resume. Assert: mismatch log line appears at `WARNING` level (not `DEBUG`), contains both pre-suspend and post-resume hash values, names the resume action (`"full re-run of parallel state <state>"`), and appears in the summary printed by `ll-loop resume` at exit.

### Implementation Notes

- **Worker success condition**: `child_result.terminated_by == "terminal" and child_result.final_state == "done"` (mirrors `_execute_sub_loop()` at `scripts/little_loops/fsm/executor.py:417-418`; full method spans 366-430)
- **Captures storage**: `self.captured[self.current_state] = {"results": [<ParallelItemResult-as-dict>, ...]}` (parallel to sub-loop pattern at `executor.py:414`: `self.captured[self.current_state] = child_executor.captured`)
- **No duplication**: `scripts/tests/test_parallel_types.py` covers `little_loops.parallel.types` (the ll-parallel orchestrator layer — `QueuedIssue`, `WorkerResult`, `MergeRequest`, `OrchestratorState`, `ParallelConfig`), NOT FSM types — no risk of duplication with `ParallelStateConfig` or FSM `ParallelResult`
- **Markers**: Only pre-declared markers (`integration`, `slow`) are valid — `--strict-markers` at `scripts/pyproject.toml:107`, markers registered at `scripts/pyproject.toml:113-116`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Mocking approach (departure from `TestSubLoopExecution` pattern)

- `TestSubLoopExecution` (`scripts/tests/test_fsm_executor.py:3634-3957`) uses **real** `FSMExecutor` instances with child YAML written to `tmp_path / ".loops"`, NOT mocks. Pattern: `(loops_dir / "child.yaml").write_text(...)`, then `FSMExecutor(parent_fsm, loops_dir=loops_dir).run()`.
- `TestParallelRunner` (mocked suite) must **mock `FSMExecutor.run()` directly** to keep the fast suite fast — deliberate departure, document in module docstring.
- Existing `MockActionRunner` dataclass at `scripts/tests/test_fsm_executor.py:30-92` is the codebase convention for mocking at the action layer, NOT the executor layer. Not reused here since we mock one level higher.

#### BRConfig has no `load()` classmethod

- `BRConfig.__init__(project_root: Path)` at `scripts/little_loops/config/core.py:77-93` — constructor reads `.ll/ll-config.json` directly, no caching, no `load()` classmethod, no module-level singleton.
- `test_config_snapshot_is_read_only_from_worker_threads` must patch the **constructor** (`patch("little_loops.config.BRConfig")` or equivalent) and record `threading.get_ident()` per call, NOT patch a non-existent `BRConfig.load()`.

#### `items_hash` resume behavior is entirely new

- Grep across `scripts/` finds **zero** matches for `items_hash`. The feature does not exist yet.
- `PersistentExecutor.resume()` (`scripts/little_loops/fsm/persistence.py:504-558`) and `cmd_resume()` exit summary (`scripts/little_loops/cli/loop/lifecycle.py:282-285`) currently emit no WARNING-level logs — `test_items_hash_mismatch_warning_is_prominent` is validating behavior introduced by FEAT-1075/FEAT-1174, not existing behavior.
- The "summary printed by `ll-loop resume` at exit" referenced in this issue maps to `logger.success(f"Resumed and completed: ...")` at `lifecycle.py:282-285`.

#### `_save_state()` thread contract is new

- `PersistentExecutor._save_state()` at `scripts/little_loops/fsm/persistence.py:436-461`, invoked via `_handle_event` at `persistence.py:417-418` (registered as `event_callback` at `persistence.py:374-381`).
- No threading primitive currently guards `_save_state()` — the singleton-safety test is validating a **behavioral contract**, not an existing enforcement. Test must instrument the method (e.g., wrap with a TID-recording decorator) because the runtime code will not assert this itself.

#### `threading.get_ident()` pattern is new to this suite

- Grep confirms **no existing test** uses `threading.get_ident()`. The singleton-safety tests introduce this pattern fresh. Reference from stdlib: each thread's `get_ident()` is stable for its lifetime; record the main thread's TID in the test `setUp`/fixture before fan-out.

#### Real-threading test patterns to copy

- **ThreadPoolExecutor + as_completed**: `scripts/tests/test_state.py:409-435` (`TestStateConcurrency.test_concurrent_save_no_corruption`) — 5 threads, submit via `as_completed`, aggregate results.
- **Thread ordering / serialization**: `scripts/tests/test_git_lock.py:395-419` — `threading.Lock`-protected list of enter/exit pairs, assert adjacent entries match to prove non-overlap.
- **Max-workers overlap detection**: adapt `test_git_lock.py:421-460` (`test_second_thread_waits_for_first`) — uses `threading.Event` to pin first thread mid-critical-section, asserts second thread is blocked; for `test_real_threads_max_workers_enforced`, use timestamp pairs `(start, end)` per worker and count concurrent overlaps in post-hoc analysis.
- **Barrier-based simultaneous start**: `scripts/tests/test_concurrency.py:333-355` — `threading.Barrier(N)` ensures workers all hit the critical section together; useful for race detection.
- **Deadlock-free many-thread sanity**: `scripts/tests/test_git_lock.py:462-479` — 20 threads, counter assertion.

#### JSONL atomicity precedent

- Closest existing pattern: `scripts/tests/test_rate_limit_circuit.py:134-177` (`test_atomic_write_crash_safety`) — concurrent writer + reader, reader asserts every observable state parses as JSON.
- Line-per-event validation: `scripts/tests/test_events.py:170-182` (`test_file_sink`) — `log_file.read_text().strip().split("\n")`, then `json.loads(lines[i])` each.
- **No existing** test writes from N concurrent threads into one JSONL — `test_worker_session_jsonl_writes_are_one_line_atomic` is net-new. Implementation hint: if each worker has its own session JSONL path (per FEAT-1075 worker-scoped paths), concurrent write to one file isn't the scenario — validate that each worker's file parses cleanly line-by-line.

#### Caplog forms to use for the resume-warning test

Prefer **Form 2** (`caplog.at_level(logging.WARNING, logger="<specific logger>")` + `caplog.records` predicate) — gives level-specific scoping and structured record access:

```python
# Pattern from scripts/tests/test_issue_parser.py:674-699
import logging
with caplog.at_level(logging.WARNING, logger="little_loops.fsm.persistence"):
    executor.resume()
# assertions can inspect record.levelname, record.message, record.name
assert any(
    record.levelname == "WARNING"
    and "items_hash mismatch" in record.message
    and pre_hash in record.message
    and post_hash in record.message
    for record in caplog.records
)
```

For the "summary printed by `ll-loop resume` at exit" assertion, capture stdout/stderr via pytest's `capsys` fixture in addition to `caplog`.

#### Integration-marked fixture chain precedent

- `scripts/tests/test_worker_pool.py:1-110` is the closest existing sibling to what this suite will look like: an `@pytest.mark.integration`-marked test module (module-level `pytestmark = pytest.mark.integration` at line 34) with a nested fixture chain (`temp_repo_with_config` → `default_parallel_config` → `br_config` → `worker_pool`, lines 43-106) and a `MagicMock`-based logger fixture. Note: this file tests the **orchestrator-layer** `WorkerPool` (`little_loops.parallel.worker_pool`), not the FSM `ParallelRunner`. Use its fixture-chain shape as a template for `TestParallelRunnerRealThreading` and `TestParallelRunnerSingletonSafety`, but keep imports/assertions targeted at `little_loops.fsm.parallel_runner.ParallelRunner` — no direct reuse of its fixtures.
- `test_worker_pool.py:34` confirms the convention: apply `@pytest.mark.integration` at the **module level** via `pytestmark` when every class in the file is integration-grade. If `TestParallelRunner` (mocked fast suite) and `TestParallelRunnerRealThreading`/`TestParallelRunnerSingletonSafety` coexist in one file, use **class-level** `@pytest.mark.integration` on the latter two only — do NOT apply `pytestmark` at module level.

#### Re-verification (2026-04-20, second refine pass)

- `scripts/little_loops/fsm/executor.py:417-418` — worker success condition (`terminated_by == "terminal" and final_state == "done"`) still present, line numbers unchanged.
- `scripts/little_loops/fsm/persistence.py:436-461` — `_save_state()` signature/body unchanged.
- `scripts/little_loops/config/core.py:77-93` — `BRConfig.__init__(project_root: Path)` still has no `load()` classmethod; patch the constructor.
- `scripts/little_loops/fsm/parallel_runner.py` — still absent. Grep across `scripts/` returns **zero** matches for `ParallelRunner`, `ParallelStateConfig`, `ParallelItemResult`, `ParallelResult` — FEAT-1074/FEAT-1075 have not landed. Readiness note at lines 246-247 (Confidence Check) remains accurate: imports in the new test file will fail at collection until FEAT-1075 ships.

#### `ExecutionResult.terminated_by` enumeration

From `scripts/little_loops/fsm/types.py:15-54`, `terminated_by` values: `"terminal"`, `"max_iterations"`, `"timeout"`, `"signal"`, `"error"`, `"handoff"`. For the timeout test, verify the parent aggregates the child's `terminated_by="timeout"` into `ParallelItemResult(terminated_by="timeout")` — do not conflate child executor timeout (`max_total_seconds` exhausted) with `ParallelRunner`-level per-worker `timeout_seconds` cancellation; they may produce different `error.kind` values.

## Integration Map

### Files to Create
- `scripts/tests/test_parallel_runner.py` — New file (flat in `scripts/tests/`, no subdirectory)

### Existing Parallel Coverage
- `scripts/tests/test_parallel_types.py` — Covers orchestrator-layer types (`QueuedIssue`, `WorkerResult`, `MergeRequest`, `OrchestratorState`, `ParallelConfig`). Zero overlap with FSM `ParallelResult`/`ParallelItemResult`/`ParallelStateConfig` — safe to proceed.

### Dependent Files (under test / needed first)
- `scripts/little_loops/fsm/parallel_runner.py` — Implementation under test (FEAT-1075; must exist first)
- `scripts/little_loops/fsm/schema.py:229-255` — `StateConfig`; `ParallelStateConfig` added by FEAT-1074
- `scripts/little_loops/fsm/types.py:15-54` — `ExecutionResult` (child result consumed by `ParallelRunner`)
- `scripts/little_loops/fsm/executor.py:366-430` — `_execute_sub_loop()`; success condition at 417-418, captures at 414
- `scripts/little_loops/fsm/persistence.py:436-461` — `PersistentExecutor._save_state()`; singleton-safety target
- `scripts/little_loops/fsm/persistence.py:504-558` — `PersistentExecutor.resume()`; items_hash check integration point
- `scripts/little_loops/cli/loop/lifecycle.py:282-285` — `ll-loop resume` exit summary (new WARNING must surface here)
- `scripts/little_loops/config/core.py:77-93` — `BRConfig.__init__`; patch constructor (not `load()`) for singleton tests
- `scripts/little_loops/fsm/__init__.py:143-195` — Must export `ParallelRunner` and `ParallelResult` (FEAT-1075 wiring step 8) before test file imports work; `ParallelItemResult`/`ParallelItemError`/`ParallelStateConfig` are NOT in `__init__.py` — import them directly

### Import Paths (required for test file)

_Wiring pass added by `/ll:wire-issue`:_

```python
from little_loops.fsm import ParallelRunner, ParallelResult       # via __init__.py AFTER FEAT-1075 step 8
from little_loops.fsm.parallel_runner import ParallelItemResult, ParallelItemError  # direct (not in __init__)
from little_loops.fsm.schema import ParallelStateConfig           # direct (not in __init__)
from little_loops.fsm import FSMExecutor, PersistentExecutor      # already exported
from little_loops.config.core import BRConfig                     # direct; patch constructor, no load() classmethod
```

`ParallelStateConfig` minimum constructor: `ParallelStateConfig(items="ctx_key", loop="child")` — all other fields have defaults (`max_workers=4`, `isolation="thread"`, `fail_mode="collect"`, etc.).

### Similar Patterns (copy into test file)
- `scripts/tests/test_fsm_executor.py:3634-3957` — `TestSubLoopExecution` — sub-loop test structure (but uses real FSMExecutor, not mocks — departure documented above)
- `scripts/tests/test_fsm_executor.py:30-92` — `MockActionRunner` dataclass — action-layer mocking convention (NOT reused; this suite mocks higher)
- `scripts/tests/test_state.py:409-485` — `TestStateConcurrency` — `ThreadPoolExecutor` + `as_completed` real-threading
- `scripts/tests/test_git_lock.py:395-479` — `TestThreadSafety` — `threading.Lock` ordering, `threading.Event` pinning, deadlock-free many-thread patterns
- `scripts/tests/test_concurrency.py:333-355` — `threading.Barrier` for simultaneous-start races
- `scripts/tests/test_rate_limit_circuit.py:134-177` — concurrent writer/reader JSON validity assertion
- `scripts/tests/test_events.py:170-182` — JSONL line-per-event parsing assertion
- `scripts/tests/test_sprint.py:282-334` — caplog Form 1 (context manager + substring)
- `scripts/tests/test_issue_parser.py:674-699` — caplog Form 2 (`logging.WARNING` constant + `caplog.records` predicate) — preferred for resume-warning test
- `scripts/tests/conftest.py:225-305` — `temp_project` / `valid_loop_file` fixtures
- `scripts/tests/conftest.py:55-61` — `temp_project_dir` (generator) fixture

### Test Fixtures
- `scripts/tests/fixtures/fsm/` — existing FSM fixture YAMLs (reference patterns); no parallel-specific fixture needed for unit tests (mocked), integration-level `parallel-loop.yaml` is FEAT-1077 scope
- Use pytest built-in `tmp_path` + `caplog` + `capsys` — no new conftest fixtures required for this suite

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_fsm_executor.py:3634-3957` — `TestSubLoopExecution` tests exercise `executor.py:417-418` success condition (the same lines FEAT-1199's worker tests reference). When FEAT-1075/FEAT-1076 land and modify the executor dispatch, these tests may break — **review and update** if the `terminated_by == "terminal" and final_state == "done"` contract at lines 417-418 changes.
- `scripts/tests/test_fsm_persistence.py` — Tests `PersistentExecutor` directly. The `TestParallelRunnerSingletonSafety` suite instruments `_save_state()` with TID-recording wrappers; review this file to ensure no fixture teardown or mock leak conflicts with the new singleton-safety tests. No overlap expected but should be run together (`pytest scripts/tests/test_fsm_persistence.py scripts/tests/test_parallel_runner.py`) to confirm isolation.

### Configuration
- `scripts/pyproject.toml:101-116` — pytest config: `--strict-markers` enabled, `integration` and `slow` markers registered. Use `@pytest.mark.integration` on `TestParallelRunnerRealThreading` and `TestParallelRunnerSingletonSafety` (runs in default CI); do NOT use `@pytest.mark.slow`.

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Verify `scripts/little_loops/fsm/__init__.py` exports `ParallelRunner` and `ParallelResult` (FEAT-1075 step 8) before writing import statements at the top of `test_parallel_runner.py`
2. Import `ParallelItemResult`/`ParallelItemError` directly from `little_loops.fsm.parallel_runner` (NOT `__init__.py`) and `ParallelStateConfig` directly from `little_loops.fsm.schema`
3. After `test_parallel_runner.py` passes, run `pytest scripts/tests/test_fsm_executor.py::TestSubLoopExecution scripts/tests/test_fsm_persistence.py` to verify no regressions from FEAT-1075/FEAT-1076 landing

## Dependencies

- **FEAT-1075** must be complete (`ParallelRunner` implementation)

## Acceptance Criteria

- `python -m pytest scripts/tests/test_parallel_runner.py -x` passes green
- `TestParallelRunnerRealThreading` runs in default CI (no `@pytest.mark.slow` gating)
- `test_parallel_runner_context_passthrough_is_deep_copy_per_worker` asserts independent deep copies per worker
- `TestParallelRunnerSingletonSafety` all 4 tests pass
- `test_items_hash_mismatch_warning_is_prominent` asserts WARNING level, both hashes, resume action name, and summary echo

## Labels

`fsm`, `parallel`, `tests`

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-20_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns
- **Blocking dependency unimplemented**: `parallel_runner.py` (FEAT-1075) and `ParallelStateConfig` (FEAT-1074) do not exist. All imports in the proposed test file would fail at collection time. The acceptance criterion ("passes green") is structurally unachievable until FEAT-1075 is complete.
- **items_hash test targets unbuilt behavior**: `test_items_hash_mismatch_warning_is_prominent` tests a WARNING log and summary echo for a feature with zero codebase presence. The exact implementation interface won't be known until FEAT-1075 ships — the test may need adjustment against the real API.

## Session Log
- `/ll:refine-issue` - 2026-04-21T02:45:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9944c1f0-21a3-4e5b-be98-4546be686b97.jsonl`
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3ffbc4c4-bcb2-4b28-8dfc-80043a1db329.jsonl`
- `/ll:confidence-check` - 2026-04-21T03:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/28c13f99-a607-4a13-a093-5ab45fd793d5.jsonl`
- `/ll:wire-issue` - 2026-04-21T02:39:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/989a22a0-5990-4db6-99ab-5f00fc036441.jsonl`
- `/ll:refine-issue` - 2026-04-21T02:34:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a9ba45a4-e650-4b5a-ae29-132e450b4a40.jsonl`
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eb2a4d4b-681c-4336-8ebc-dacfae9712d8.jsonl`
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee39c2da-53b6-4990-b649-6f5e43993562.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-20
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-1202: TestParallelRunner — Core mocked unit tests
- FEAT-1203: TestParallelRunnerRealThreading — Real-threading concurrency tests
- FEAT-1204: TestParallelRunnerSingletonSafety + items_hash resume-warning test
