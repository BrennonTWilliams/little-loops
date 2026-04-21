---
discovered_date: "2026-04-20"
discovered_by: issue-size-review
parent_issue: FEAT-1199
size: Very Large
confidence_score: 88
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1204: TestParallelRunnerSingletonSafety + items_hash Resume-Warning Test

## Summary

Add `TestParallelRunnerSingletonSafety` (4 tests) and `test_items_hash_mismatch_warning_is_prominent` to `scripts/tests/test_parallel_runner.py` — verifying thread-safety contracts for shared state and resume-hash warning behavior.

## Parent Issue

Decomposed from FEAT-1199: Parallel Runner Unit Tests (test_parallel_runner.py)

## Use Case

**Who**: Developer completing FEAT-1075/FEAT-1174 (`ParallelRunner` + items_hash resume warning)

**Context**: After FEAT-1203 adds real-threading tests, this issue completes the test file with singleton-safety tests and the resume-warning test. These validate behavioral contracts: that `_save_state()` is only called from the main thread, that JSONL writes are atomic per line, that `BRConfig` is not lazily initialized from workers, and that items_hash mismatches surface at WARNING level.

**Goal**: Add `TestParallelRunnerSingletonSafety` class and `test_items_hash_mismatch_warning_is_prominent` to `scripts/tests/test_parallel_runner.py`.

**Outcome**: `python -m pytest scripts/tests/test_parallel_runner.py -x` passes green for the entire file.

## Proposed Solution

### Add to existing file: scripts/tests/test_parallel_runner.py

#### Class: TestParallelRunnerSingletonSafety

Apply `@pytest.mark.integration` at class level. Real `ThreadPoolExecutor`, ≥4 workers, light real workloads.

Test cases:

- **`test_parent_checkpoint_file_not_written_from_worker_threads`** — instrument `PersistentExecutor._save_state()` at `scripts/little_loops/fsm/persistence.py:436-461` with a `threading.get_ident()` check via a wrapper decorator. Record the main thread TID in setUp/fixture before fan-out. Assert every `_save_state()` call came from the main thread's TID. This validates a behavioral contract — no threading primitive currently guards `_save_state()`.

- **`test_worker_session_jsonl_writes_are_one_line_atomic`** — 4 workers each write 50 events into their session JSONL files; after run, `json.loads()` each line; assert every line parses cleanly. Note: if each worker has its own session JSONL path (per FEAT-1075 worker-scoped paths), concurrent writes to one file aren't the scenario — validate that each worker's file parses cleanly line-by-line. Reference: `scripts/tests/test_rate_limit_circuit.py:134-177` (atomic write) and `scripts/tests/test_events.py:170-182` (JSONL line-per-event parsing).

- **`test_config_snapshot_is_read_only_from_worker_threads`** — patch the `BRConfig` **constructor** (`patch("little_loops.config.BRConfig")` or equivalent, since `BRConfig.__init__(project_root: Path)` at `scripts/little_loops/config/core.py:77-93` has no `load()` classmethod, no caching, no module-level singleton) and record `threading.get_ident()` per call. Assert all constructor-call TIDs equal the main thread's TID. Do NOT patch a non-existent `BRConfig.load()`.

- **`test_module_level_caches_not_lazily_written_from_workers`** — for each module-level cache the runner depends on, record cache size before `runner.run()` (with a pre-warmed cache). Assert cache size is identical after `runner.run()`. This verifies workers don't lazily populate shared module-level state.

#### Resume-warning test (folded from FEAT-1174)

Add as a standalone test function (or within `TestParallelRunnerSingletonSafety`):

- **`test_items_hash_mismatch_warning_is_prominent`** — suspend a parallel state mid-run, mutate the `items` source on disk, resume. Assert:
  1. Mismatch log line appears at `WARNING` level (not `DEBUG`), checked via `caplog.at_level(logging.WARNING, logger="little_loops.fsm.persistence")`
  2. Log message contains both pre-suspend and post-resume hash values
  3. Log message names the resume action (`"full re-run of parallel state <state>"`)
  4. Warning appears in the summary printed by `ll-loop resume` at exit (captured via `capsys`)

Note: `items_hash` has **zero** codebase presence — this test validates behavior introduced by FEAT-1075/FEAT-1174, not existing behavior. `PersistentExecutor.resume()` at `scripts/little_loops/fsm/persistence.py:504-558` currently emits no WARNING-level logs.

### Implementation Notes

- `threading.get_ident()` is new to this suite — no existing test uses it. Record the main thread's TID in the test setUp/fixture before fan-out; each thread's `get_ident()` is stable for its lifetime.
- For caplog: use **Form 2** (`caplog.at_level(logging.WARNING, logger="little_loops.fsm.persistence")` + `caplog.records` predicate) — gives level-specific scoping and structured record access. Reference: `scripts/tests/test_issue_parser.py:674-699`.
- For the `ll-loop resume` summary assertion: use pytest's `capsys` fixture in addition to `caplog` to capture stdout/stderr.
- **Two logging systems in play — pick the right fixture for each assertion:**
  - `persistence.py:43` uses **stdlib logging** (`logger = logging.getLogger(__name__)` with no `basicConfig` / handlers registered anywhere in `scripts/little_loops/`). This is where the `items_hash` WARNING record originates. → assert via `caplog.records` with `logger="little_loops.fsm.persistence"`.
  - `lifecycle.py:19,282` uses the **custom `Logger` class** from `little_loops/logger.py:17-113`. `Logger.success()`/`warning()`/`info()` call `print(..., flush=True)` to **stdout** (only `.error()` goes to stderr at `logger.py:99`). It is NOT loguru and NOT stdlib logging. → assert the resume-summary echo via `capsys.readouterr().out` (stdout, not stderr).
  - Consequence for FEAT-1174 re-echo: for the WARNING to appear in `ll-loop resume` stdout, `lifecycle.py` (or a callback from `persistence.py.resume()`) must explicitly call the CLI `Logger.warning(...)` — stdlib `logger.warning(...)` alone will go to the stdlib "last resort" stderr handler and will NOT land in `capsys.readouterr().out`. If FEAT-1174 hasn't wired this echo, the `capsys` assertion will fail — flag as a FEAT-1174 gap rather than relaxing the test.
- `terminated_by` values from `scripts/little_loops/fsm/types.py:15-54`: `"terminal"`, `"max_iterations"`, `"timeout"`, `"signal"`, `"error"`, `"handoff"`. Do not conflate child executor timeout (`max_total_seconds` exhausted) with `ParallelRunner`-level per-worker `timeout_seconds` cancellation.

_Wiring pass added by `/ll:wire-issue`:_
- **`@pytest.mark.integration` placement**: All 9 existing usages are module-level (`pytestmark = pytest.mark.integration`) or single-function level. Applying at class level (as specified here) is a new pattern for the suite — it works identically with pytest, but note the divergence from convention seen in `test_worker_pool.py:34` and `test_orchestrator.py:40`.
- **`capsys` + `caplog` in same test**: No existing test combines both fixtures. `test_items_hash_mismatch_warning_is_prominent` would be the first. Do not set `propagate=False` on the caplog logger or it will suppress the stdlib log record before caplog can capture it.
- **Teardown risk**: If `patch.object(PersistentExecutor, "_save_state")` is applied at **class scope** (not test scope), the patch may not restore the original if a test raises before teardown, leaking into `test_fsm_persistence.py`'s executor tests. Use test-scoped `patch.object` (inside each test function or via a test-scoped `autouse=False` fixture) to prevent decorator leaks.

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified 2026-04-21:_

- All line numbers cited in this issue verified against current HEAD:
  - `persistence.py:436-461` `_save_state()` ✓
  - `persistence.py:504-558` `resume()` ✓ (emits only `loop_resume` event via `append_event` at line 555, no WARNING logs today — items_hash check must be added by FEAT-1174)
  - `config/core.py:77-93` `BRConfig.__init__(project_root: Path)` ✓ — constructor does `self._load_config()` + `self._parse_config()`, no classmethod load, no module cache
  - `lifecycle.py:282-285` `logger.success("Resumed and completed: ...")` ✓
  - `logger.py` `Logger` class spans lines 17-112 (issue says 17-113 — off-by-one, no impact); `.info`/`.success`/`.warning` at 76-94 `print(..., flush=True)` → stdout; `.error` at line 99 → stderr
- Target files do NOT exist yet: `scripts/little_loops/fsm/parallel_runner.py` (FEAT-1075), `scripts/tests/test_parallel_runner.py` (created by FEAT-1202). This issue cannot run until both land.
- `items_hash` has zero codebase presence (`grep items_hash scripts/little_loops/ -r` returns no matches) — confirms test validates FEAT-1174-introduced behavior, not existing behavior.
- Existing stdlib-logging `caplog` patterns in the test suite (all use Form 2): `test_sprint.py:282-334`, `test_frontmatter.py:95-147`, `test_dependency_graph.py:82-106`, `test_issue_parser.py:674-699`. No prior test asserts on the custom `Logger` class via `capsys` — this test adds that pattern.

_Re-verified 2026-04-21 (second refine pass — additional findings):_

- **Dependency status check**: FEAT-1075, FEAT-1174, FEAT-1202 all still under `.issues/features/` (not complete). FEAT-1203 is complete (in `.issues/completed/`). This issue is the last of the test-decomposition chain and remains blocked on three parent issues.
- **FEAT-1174 title clarification**: The parent issue on disk is `P2-FEAT-1174-per-worker-checkpointing-for-parallel-states.md` — a broader per-worker checkpointing scope that includes the `items_hash` resume-warning behavior. When citing FEAT-1174 as a dependency, expect the full per-worker-checkpointing feature, not just the items_hash hook.
- **Existing `Logger.warning()` precedent at `lifecycle.py:271`**: `logger.warning(f"Nothing to resume for: {loop_name}")` already wires the custom `Logger.warning()` → stdout path. Confirms the integration point the FEAT-1174 items_hash echo will also need to use. Implementers can reference this line as a concrete precedent for how the echo should look and where it will land in `capsys.readouterr().out`.
- **`test_module_level_caches_not_lazily_written_from_workers` — target caches unclear**: Grepping the likely dependency chain (`FSMExecutor`, `PersistentExecutor`, `EventBus`, `BRConfig`) turns up no `@lru_cache`, `@functools.cache`, or lazy dict/set module-level caches. The only module-level mutable state found is `cli/output.py:31 _USE_COLOR` (set once at import, not thread-mutated) and read-only `_DEFAULT_*` constants in `fsm/executor.py:52-70`. **Implication**: until FEAT-1075 introduces the runner, there is no concrete cache for this test to pre-warm and assert against. Implementer should either (a) re-scope the test to assert against whatever caches FEAT-1075 actually introduces, or (b) drop the test if the runner introduces no new lazy module-level state. Flag during FEAT-1075 review rather than writing a no-op assertion.
- **`threading.get_ident()` has zero precedent in `scripts/` tests** — confirmed via Grep. This test file introduces the pattern. Recommended fixture (no existing pattern to copy):
  ```python
  @pytest.fixture
  def main_tid():
      """Record main-thread TID before any fan-out; stable for fixture lifetime."""
      return threading.get_ident()
  ```
  Call sites then compare recorded TIDs against `main_tid` after `runner.run()` returns.
- **Closest existing threading pattern** for instrumenting `_save_state()` with a TID-recording wrapper: `test_orchestrator.py:2425-2468` (`test_concurrent_state_checkpoint`) uses raw `threading.Thread` to exercise `_save_state()` concurrently — but records no TIDs. Use its Thread construction pattern; add TID recording via `patch.object(PersistentExecutor, "_save_state", wraps=...)` with a side_effect that appends `threading.get_ident()` to a list before delegating.

## Integration Map

### Files to Modify
- `scripts/tests/test_parallel_runner.py` — Add class and test function; file created by FEAT-1202, extended by FEAT-1203

### Dependent Files (under test / needed first)
- `scripts/little_loops/fsm/parallel_runner.py` — Implementation under test (FEAT-1075); does NOT exist yet
- `scripts/little_loops/fsm/persistence.py:23-43` — stdlib `logging` import + `logger = logging.getLogger(__name__)`; scope for `caplog.at_level(..., logger="little_loops.fsm.persistence")`
- `scripts/little_loops/fsm/persistence.py:436-461` — `PersistentExecutor._save_state()`; singleton-safety instrumentation target
- `scripts/little_loops/fsm/persistence.py:504-558` — `PersistentExecutor.resume()`; items_hash check integration point (new behavior via FEAT-1075/FEAT-1174)
- `scripts/little_loops/cli/loop/lifecycle.py:19` — `from little_loops.logger import Logger` (custom print-based class, NOT stdlib logging)
- `scripts/little_loops/cli/loop/lifecycle.py:282-285` — `logger.success(...)` exit summary; WARNING must surface here via `Logger.warning()` → stdout
- `scripts/little_loops/logger.py:86-94` — `Logger.success`/`Logger.warning` → `print(..., flush=True)` to stdout; drives `capsys.readouterr().out` assertion
- `scripts/little_loops/config/core.py:77-93` — `BRConfig.__init__(project_root: Path)`; patch constructor (not `load()`) for singleton tests
- FEAT-1202 and FEAT-1203 must be complete (create `test_parallel_runner.py`, add `TestParallelRunnerRealThreading`)

### Similar Patterns (copy from)
- `scripts/tests/test_issue_parser.py:674-699` — caplog Form 2 (`logging.WARNING` + `caplog.records` predicate) — preferred for resume-warning test
- `scripts/tests/test_sprint.py:282-334` — caplog Form 1 (context manager + substring)
- `scripts/tests/test_rate_limit_circuit.py:134-177` — concurrent writer/reader JSON validity assertion
- `scripts/tests/test_events.py:170-182` — JSONL line-per-event parsing assertion
- `scripts/tests/test_fsm_persistence.py` — Tests `PersistentExecutor` directly; run together with `test_parallel_runner.py` to confirm no fixture teardown/mock leak conflicts

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_state.py:328-408` — `test_resume_continues_running_loop` — the ONLY existing test asserting `lifecycle.py:282-285` stdout via real `Logger` + `capsys.readouterr().out`; primary pattern reference for the `capsys` assertion in `test_items_hash_mismatch_warning_is_prominent`
- `scripts/tests/test_cli_loop_lifecycle.py:1054,1088` — `TestCmdResumeCircuitWiring` — patches `"little_loops.config.BRConfig"` at the correct module import path; reference for `test_config_snapshot_is_read_only_from_worker_threads`
- `scripts/tests/test_orchestrator.py:2425-2468` — `test_concurrent_state_checkpoint` — concurrent `_save_state()` via raw `threading.Thread`; closest existing threading pattern to the TID-recording tests
- `scripts/tests/test_logger.py:145-175,290-310` — `capsys`-based `Logger.success()` / `Logger.warning()` assertions for the custom print-based `Logger` class; reference for the resume-warning test's stdout assertion
- `scripts/tests/conftest.py` — shared fixtures (`temp_project_dir`, `temp_project`, `loops_dir`); check before writing new fixtures to avoid duplication

### Tests to Run After Completion
```bash
# Verify no regressions from FEAT-1075/FEAT-1076 landing:
pytest scripts/tests/test_fsm_executor.py::TestSubLoopExecution scripts/tests/test_fsm_persistence.py scripts/tests/test_parallel_runner.py
```

## Dependencies

- **FEAT-1075** must be complete (`ParallelRunner` implementation)
- **FEAT-1174** must be complete (`items_hash` resume-warning feature)
- **FEAT-1202** must be complete (creates `test_parallel_runner.py`)
- **FEAT-1203** must be complete (adds `TestParallelRunnerRealThreading`)

## Acceptance Criteria

- `python -m pytest scripts/tests/test_parallel_runner.py -x` passes green for the entire file
- `TestParallelRunnerSingletonSafety` all 4 tests pass
- `test_parent_checkpoint_file_not_written_from_worker_threads` asserts every `_save_state()` call from main thread TID
- `test_config_snapshot_is_read_only_from_worker_threads` patches constructor (not `load()`), asserts main-thread TID only
- `test_items_hash_mismatch_warning_is_prominent` asserts WARNING level, both hash values, resume action name, and summary echo in stdout

## Labels

`fsm`, `parallel`, `tests`, `integration`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-21_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- **3/4 critical dependencies unresolved**: FEAT-1075 (`parallel_runner.py`), FEAT-1174 (`items_hash` WARNING + stdout echo), and FEAT-1202 (`test_parallel_runner.py` creation) all remain open. Tests can be authored now but are not executable until all three land.
- **FEAT-1174 stdout echo gap**: `test_items_hash_mismatch_warning_is_prominent` assertion 4 (`capsys.readouterr().out`) requires FEAT-1174 to explicitly call `Logger.warning()` → stdout; stdlib `logger.warning()` alone will not land there. Flag back to FEAT-1174 if omitted — do not weaken the assertion.
- **Class-level `@pytest.mark.integration`**: Minor divergence from suite convention (9 existing files use module-level `pytestmark`). Functionally equivalent; may draw a review comment requesting alignment.

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-21
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- FEAT-1211: TestParallelRunnerSingletonSafety (4 thread-safety tests)
- FEAT-1212: test_items_hash_mismatch_warning_is_prominent (resume-warning test)

## Session Log
- `/ll:refine-issue` - 2026-04-21T05:15:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b81df27a-b04e-4518-8864-70ad291ebb13.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f6986cb5-4dbc-4c04-b517-f2ff10b4476f.jsonl`
- `/ll:wire-issue` - 2026-04-21T05:11:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/28a5b938-df29-4cdd-8a8d-ba0a49c5f19f.jsonl`
- `/ll:refine-issue` - 2026-04-21T05:04:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/edb9716a-29af-42f1-8488-311d53642d0e.jsonl`
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee39c2da-53b6-4990-b649-6f5e43993562.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0dfd96a3-66df-4e02-b30b-139bf75f812f.jsonl`
