---
status: done
completed_at: 2026-04-21T00:00:00Z
---
> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
discovered_date: "2026-04-21"
discovered_by: issue-size-review
parent_issue: FEAT-1204
size: Very Large
confidence_score: 80
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1211: TestParallelRunnerSingletonSafety (4 thread-safety tests)

## Summary

Add `TestParallelRunnerSingletonSafety` (4 tests) to `scripts/tests/test_parallel_runner.py`, verifying thread-safety contracts for shared state: `_save_state()` main-thread-only, atomic JSONL writes, config constructor isolation, and module-level cache immutability.

## Parent Issue

Decomposed from FEAT-1204: TestParallelRunnerSingletonSafety + items_hash Resume-Warning Test

## Use Case

**Who**: Developer completing FEAT-1075/FEAT-1174 (`ParallelRunner` + items_hash resume warning)

**Context**: After FEAT-1203 adds real-threading tests, this issue adds the singleton-safety test class to `test_parallel_runner.py`. These validate behavioral contracts: that `_save_state()` is only called from the main thread, that JSONL writes are atomic per line, that `BRConfig` is not lazily initialized from workers, and that module-level caches are not written by workers.

**Goal**: Add `TestParallelRunnerSingletonSafety` class to `scripts/tests/test_parallel_runner.py`.

**Outcome**: `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerSingletonSafety -x` passes green.

## Proposed Solution

### Add to existing file: scripts/tests/test_parallel_runner.py

#### Class: TestParallelRunnerSingletonSafety

Apply `@pytest.mark.integration` at class level. Real `ThreadPoolExecutor`, ≥4 workers, light real workloads.

Test cases:

- **`test_parent_checkpoint_file_not_written_from_worker_threads`** — instrument `PersistentExecutor._save_state()` at `scripts/little_loops/fsm/persistence.py:436-461` with a `threading.get_ident()` check via a wrapper decorator. Record the main thread TID in setUp/fixture before fan-out. Assert every `_save_state()` call came from the main thread's TID. This validates a behavioral contract — no threading primitive currently guards `_save_state()`.

- **`test_worker_session_jsonl_writes_are_one_line_atomic`** — 4 workers each write 50 events into their session JSONL files; after run, `json.loads()` each line; assert every line parses cleanly. Note: if each worker has its own session JSONL path (per FEAT-1075 worker-scoped paths), concurrent writes to one file aren't the scenario — validate that each worker's file parses cleanly line-by-line. Reference: `scripts/tests/test_rate_limit_circuit.py:134-177` (atomic write) and `scripts/tests/test_events.py:170-182` (JSONL line-per-event parsing).

- **`test_config_snapshot_is_read_only_from_worker_threads`** — patch the `BRConfig` **constructor** (`patch("little_loops.config.BRConfig")` or equivalent, since `BRConfig.__init__(project_root: Path)` at `scripts/little_loops/config/core.py:77-85` has no `load()` classmethod, no caching, no module-level singleton) and record `threading.get_ident()` per call. Assert all constructor-call TIDs equal the main thread's TID. Do NOT patch a non-existent `BRConfig.load()`.

- **`test_module_level_caches_not_lazily_written_from_workers`** — for each module-level cache the runner depends on, record cache size before `runner.run()` (with a pre-warmed cache). Assert cache size is identical after `runner.run()`. If FEAT-1075 introduces no new lazy module-level state, drop this test rather than writing a no-op assertion.

### Implementation Notes

- `threading.get_ident()` is new to this suite — no existing test uses it. Record the main thread's TID in the test setUp/fixture before fan-out; each thread's `get_ident()` is stable for its lifetime.
- **Teardown risk**: If `patch.object(PersistentExecutor, "_save_state")` is applied at **class scope** (not test scope), the patch may not restore the original if a test raises before teardown, leaking into `test_fsm_persistence.py`'s executor tests. Use test-scoped `patch.object` (inside each test function or via a test-scoped `autouse=False` fixture) to prevent decorator leaks.
- **`@pytest.mark.integration` placement**: Applying at class level is a new pattern for the suite — it works identically with pytest, but note the divergence from convention seen in `test_worker_pool.py:34` and `test_orchestrator.py:40`.
- Recommended `main_tid` fixture (no existing pattern to copy):
  ```python
  @pytest.fixture
  def main_tid():
      """Record main-thread TID before any fan-out; stable for fixture lifetime."""
      return threading.get_ident()
  ```
- Closest existing threading pattern: `test_orchestrator.py:2425-2468` (`test_concurrent_state_checkpoint`) uses raw `threading.Thread` to exercise `_save_state()` concurrently. Use its Thread construction pattern; add TID recording via `patch.object(PersistentExecutor, "_save_state", wraps=...)` with a side_effect that appends `threading.get_ident()` to a list before delegating.
- **`test_module_level_caches` target caches unclear**: No `@lru_cache`, `@functools.cache`, or lazy dict/set module-level caches found in the likely dependency chain. Implement against whatever caches FEAT-1075 actually introduces, or drop if none exist.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis 2026-04-21:_

- **Module-level caches: DEFINITIVELY zero.** Full-tree grep across `scripts/little_loops/` for `@lru_cache`, `@functools.cache`, `@cache`, `_cache = {`, `_cache = [`, `_singleton`, `_instance = None` returned **no matches** anywhere. All 14 files in `scripts/little_loops/fsm/` (including `persistence.py`, `executor.py`, `runners.py`, `schema.py`, `validation.py`, `concurrency.py`) are cache-free. **Recommendation: drop `test_module_level_caches_not_lazily_written_from_workers` unless FEAT-1075 actively introduces a cache.** Class becomes 3 tests.
- **`PersistentExecutor._save_state()` patching is safe.** Method signature `def _save_state(self) -> None` at `scripts/little_loops/fsm/persistence.py:436`. Only two call sites: `persistence.py:418` inside `_on_event()` (fires on `state_enter`/`loop_complete`), and the definition itself. The method only **reads** instance state and delegates to `self.persistence.save_state(state)` — no mutation of `self`, so `patch.object(PersistentExecutor, "_save_state", wraps=original)` cleanly intercepts without corrupting internal state.
- **`BRConfig` confirmed constructor-only.** `scripts/little_loops/config/core.py:77-104` — `__init__(self, project_root: Path)` resolves path (line 83), calls `_load_config()` (opens JSON, returns `{}` if absent), then `_parse_config()`. No `load()` classmethod, no module-level singleton, no cache. Every `BRConfig(path)` call is fresh. Patch target is `"little_loops.config.BRConfig"` (see `test_cli_loop_lifecycle.py:1054,1088` for the working import-path form).
- **`@pytest.mark.integration` at class level has precedent.** One existing use: `scripts/tests/test_goals_parser.py:437` (`class TestIntegration`). All other uses in the suite are module-level (`pytestmark = pytest.mark.integration` in `test_worker_pool.py:34`, `test_orchestrator.py:40`, `test_git_lock.py:16`, and 5 others). Class-level application is valid but rare — match `test_goals_parser.py:437` form.
- **`patch.object(..., wraps=...)` has precedent.** Established in `scripts/tests/test_ll_loop_display.py:1798-1802` (repeated at lines 1857, 2018, 2089, 2178, 2259) and `scripts/tests/test_workflow_sequence_analyzer.py:1474-1482`. The established form records `mock.call_count` only; combining `wraps=` with a `side_effect` that appends `threading.get_ident()` to a list before delegating **would be new** — no existing test captures thread metadata via this technique.
- **`threading.get_ident()` and pre-fan-out TID fixtures have no precedent.** No test in `scripts/tests/` uses `threading.get_ident()`, `threading.current_thread()`, or a fixture capturing `threading.main_thread()` before fan-out. FEAT-1211 introduces these patterns from scratch — the `main_tid` fixture sketch in Implementation Notes is the new canonical form.
- **Closest concurrency model: `test_orchestrator.py:2425-2472`** (`test_concurrent_state_checkpoint`). Pattern: 5 callback threads + 1 save thread via raw `threading.Thread`, shared `errors=[]` list, assert `len(errors) == 0` and `save_count[0] == N` after join. Use this as the template for TID-recording tests (substitute appending `threading.get_ident()` for the error-collection step).
- **JSONL atomic-line assertion pattern**: `scripts/tests/test_events.py:179-182` — `lines = log_file.read_text().strip().split("\n"); for line: json.loads(line)`. Use this form per worker's session JSONL file.

## Integration Map

### Files to Modify
- `scripts/tests/test_parallel_runner.py` — Add `TestParallelRunnerSingletonSafety` class; file created by FEAT-1202, extended by FEAT-1203

### Dependent Files (under test / needed first)
- `scripts/little_loops/fsm/parallel_runner.py` — Implementation under test (FEAT-1075); does NOT exist yet
- `scripts/little_loops/fsm/persistence.py:436-461` — `PersistentExecutor._save_state()`; singleton-safety instrumentation target
- `scripts/little_loops/config/core.py:77-85` — `BRConfig.__init__(project_root: Path)`; patch constructor (not `load()`)
- FEAT-1202 and FEAT-1203 must be complete

### Similar Patterns (copy from)
- `scripts/tests/test_rate_limit_circuit.py:134-177` — concurrent writer/reader JSON validity assertion
- `scripts/tests/test_events.py:170-182` — JSONL line-per-event parsing assertion
- `scripts/tests/test_cli_loop_lifecycle.py:1054,1088` — `TestCmdResumeCircuitWiring` — patches `"little_loops.config.BRConfig"` at correct module import path
- `scripts/tests/test_orchestrator.py:2425-2468` — `test_concurrent_state_checkpoint` — concurrent `_save_state()` via raw `threading.Thread`
- `scripts/tests/conftest.py` — shared fixtures (`temp_project_dir`, `temp_project`, `loops_dir`)

### Tests to Run After Completion
```bash
pytest scripts/tests/test_fsm_persistence.py scripts/tests/test_parallel_runner.py::TestParallelRunnerSingletonSafety
```

### Tests (At-Risk)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_persistence.py:1852-1884` — `test_save_state_includes_rate_limit_retries` calls `executor._save_state()` directly; a leaked class-scope `patch.object(PersistentExecutor, "_save_state", ...)` from `TestParallelRunnerSingletonSafety` would silently intercept it — must use test-scoped patches only [Agent 3]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml:107,114` — `--strict-markers` is active; `integration` mark already registered at line 114 — no `pyproject.toml` changes required for `@pytest.mark.integration` at class level to work [Agent 2]

### Additional Pattern References

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_concurrency.py:340-355` — `threading.Barrier(2)` synchronized-start pattern: both threads call `barrier.wait()` before operating — useful for `test_parent_checkpoint_file_not_written_from_worker_threads` fan-out [Agent 3]
- `scripts/tests/test_state.py:415-436` — `ThreadPoolExecutor` with `concurrent.futures.as_completed` pattern; `max_workers=5`, collects `f.result()` — alternative to raw `threading.Thread` for the JSONL atomicity test [Agent 3]

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints must be verified during implementation:_

1. Use test-scoped `patch.object(PersistentExecutor, "_save_state", wraps=original)` inside each test function (not at class scope) — prevents mock leak into `test_fsm_persistence.py:1852-1884`
2. No `pyproject.toml` change needed — `integration` mark already registered at `scripts/pyproject.toml:114`
3. After writing tests, run full persistence suite to confirm no leak: `pytest scripts/tests/test_fsm_persistence.py scripts/tests/test_parallel_runner.py::TestParallelRunnerSingletonSafety`

## Dependencies

- **FEAT-1075** must be complete (`ParallelRunner` implementation)
- **FEAT-1202** must be complete (creates `test_parallel_runner.py`)
- **FEAT-1203** must be complete (adds `TestParallelRunnerRealThreading`)

## Acceptance Criteria

- `TestParallelRunnerSingletonSafety` all 4 tests pass (or 3 if `test_module_level_caches` dropped per guidance)
- `test_parent_checkpoint_file_not_written_from_worker_threads` asserts every `_save_state()` call from main thread TID
- `test_config_snapshot_is_read_only_from_worker_threads` patches constructor (not `load()`), asserts main-thread TID only
- No mock/fixture leak into `test_fsm_persistence.py` tests

## Labels

`fsm`, `parallel`, `tests`, `integration`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-21_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1075 not completed**: `scripts/little_loops/fsm/parallel_runner.py` does not exist yet. Tests in this class exercise the parallel runner directly — they cannot pass until the implementation is written.
- **FEAT-1202 not completed**: `scripts/tests/test_parallel_runner.py` does not exist yet. This issue adds a class to that file; the file must be created by FEAT-1202 first.
- **FEAT-1203 inconsistency**: FEAT-1203 is marked completed in `.issues/completed/`, but its dependency FEAT-1202 is unresolved and the target file doesn't exist — possible premature completion marking worth investigating before scheduling this issue.

## Session Log
- `/ll:refine-issue` - 2026-04-21T05:32:50 - `de43bbd3-c5b0-4b17-a8f0-697bc6f0cd56.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `2cedf469-785d-4536-a515-2b08375c03a8.jsonl`
- `/ll:wire-issue` - 2026-04-21T05:29:12 - `c90b360a-a58f-4344-920a-d57458c97bdd.jsonl`
- `/ll:refine-issue` - 2026-04-21T05:24:03 - `3c00710c-8d98-488e-9704-7ede190bec4f.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `0dfd96a3-66df-4e02-b30b-139bf75f812f.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `1968b1de-1999-4bd4-9f8b-f1ac52011ad8.jsonl`
