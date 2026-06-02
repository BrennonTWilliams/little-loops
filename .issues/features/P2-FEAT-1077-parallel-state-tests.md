---
discovered_date: "2026-04-12"
discovered_by: issue-size-review

confidence_score: 80
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
size: Very Large
parent: FEAT-1072
status: done
completed_at: 2026-05-10T00:00:00Z
---

# FEAT-1077: Parallel State Tests

## Rescope (2026-04-20)

This issue was originally "write all tests for parallel" but that created a circular dependency: FEAT-1076 cannot merge without passing tests for its folded-in ENH-1164 (simulation) and ENH-1165 (cancellation) criteria, yet those tests were owned here, which blocked on FEAT-1075. To break the cycle, **unit tests now live with the code they test** and this issue owns only the integration suite.

**Unit-test ownership moved to core FEATs:**

| Test scope | New owner | Notes |
|---|---|---|
| Schema round-trip (`TestParallelStateConfig`), mutual exclusion (`TestParallelMutualExclusion`), validation no-transition guard, fuzz `parallel` key | **FEAT-1074** | Block FEAT-1074 on these tests passing |
| `ParallelRunner` unit tests (thread mode, worktree, fail modes, deep-copy contract, ordering guarantee, timeout, edges 0/1 item) | **FEAT-1075** | Includes the mocked-executor fast suite |
| Dispatcher tests: simulation path (folded ENH-1164), real-execution path, cancellation path (folded ENH-1165 Option B) | **FEAT-1076** | All three code paths from FEAT-1076's split acceptance criteria |

**This issue retains ownership of:**

1. **End-to-end integration tests** — real `FSMExecutor.run()` + real `ParallelRunner` + toy sub-loops, across the three routing variants (`on_yes`/`on_partial`/`on_no`).
2. **`TestParallelRunnerRealThreading`** — 4 real-thread tests that exercise OS-level scheduling (deep-copy under real threads, max_workers enforcement, fail_fast cancellation under real futures, timeout-one-while-others-complete). MUST run in default CI (not gated behind `slow`).
3. **`TestParallelRunnerSingletonSafety`** — 4 tests asserting workers do not write to parent checkpoint, mutate module-level caches, reload config, or corrupt session JSONL. **Scaffolding owned here**; ENH-1185 contributes the audit step that enumerates which singletons need coverage and may add test methods into this class.
4. **`items_hash` resume-warning test** (`test_items_hash_mismatch_warning_is_prominent`) — folded from FEAT-1174 tightening.
5. **Display badge test** — `TestStateBadges` extension (depends on FEAT-1078 / FEAT-1081).
6. **Fixture YAML** — `scripts/tests/fixtures/fsm/parallel-loop.yaml`.

The sections below retain the original detailed inventory of tests; treat them as *where each test now lives*, not as a to-do list owned exclusively by this issue.

## Summary

Write the **integration-level** tests for the `parallel:` state type: end-to-end FSM execution with real fan-out, real-threading concurrency safety nets, singleton-safety scaffolding, resume-warning test, fixture YAML, and display badge test. Unit-level tests are owned by FEAT-1074/1075/1076 per the Rescope section above.

## Parent Issue

Decomposed from FEAT-1072: Add `parallel:` State Type to FSM for Concurrent Sub-Loop Fan-Out

## Use Case

**Who**: Developer completing the `parallel:` state type implementation (FEAT-1074/1075/1076)

**Context**: After `ParallelRunner`, schema, and executor dispatch are implemented, test coverage must be in place before the feature can merge.

**Goal**: Write comprehensive tests covering `ParallelRunner` behavior, FSM schema round-trips, validation rule enforcement, fixture loading, fuzz coverage, and display badges for `parallel:` states.

**Outcome**: All new tests pass, the regression suite stays green, and the `parallel:` feature is fully covered by the test suite.

## Current Behavior

No tests exist for the `parallel:` state type. `ParallelRunner`, `ParallelStateConfig`, and the executor dispatch path (`_execute_parallel_state()`) have no test coverage. Schema validation and mutual exclusion rules for `parallel:` states are unchecked.

## Expected Behavior

A full test suite covers the `parallel:` state type:
- `scripts/tests/fsm/test_parallel_runner.py` unit-tests `ParallelRunner` (thread mode, worktree mode, fail_fast, edge cases)
- `test_fsm_executor.py` covers parallel dispatch and route correctness
- `test_fsm_schema.py` covers `ParallelStateConfig` round-trips
- `test_fsm_validation.py` covers mutual exclusion and invalid field values
- `parallel-loop.yaml` fixture round-trips cleanly
- Fuzz strategy includes `parallel` key
- Display badge test added for `parallel:` state

## Motivation

This feature would:
- Ensure correctness of the `parallel:` state type implementation (FEAT-1074/1075/1076) before merging
- Prevent regressions as the FSM evolves — parallel state is complex (threading, worktree isolation, fail modes)
- Required for FEAT-1072 to be complete: tests are the final gating deliverable

## Proposed Solution

### New test file: scripts/tests/test_parallel_runner.py

Create `scripts/tests/test_parallel_runner.py` (flat directory — all FSM tests live directly under `scripts/tests/`, no `fsm/` subdirectory exists). Unit tests for `ParallelRunner` with mock `FSMExecutor` workers:

- Thread mode: mock sub-loop runs, verify captures collected, verdict derived correctly
- Thread mode `fail_fast`: verify remaining futures cancelled on first failure
- Worktree mode: mock worktree setup/teardown, verify merge-back called
- `context_passthrough: true`: verify parent context passed to each worker
- `test_parallel_runner_context_passthrough_is_deep_copy_per_worker` — thread-safety invariant from FEAT-1075 (deep-copy contract): pass a `parent_context` that includes nested mutable structures (a dict-of-lists, e.g., `{"items": ["a", "b"], "meta": {"count": 0}}`). Spawn N (≥4) workers where each worker mutates its nested structures (e.g., appends to `items`, increments `meta["count"]`). After the run, assert: (a) every worker's mutations are visible only inside that worker's own `ParallelItemResult.captures` entry, (b) sibling workers see no mutations from each other in their initial context, (c) the parent's original `self.captured` dict is byte-for-byte unchanged (including nested containers — check `parent_context["items"] is not worker_context["items"]` identity). This catches regressions to shallow-copy or pass-by-reference.
- `test_parallel_runner_preserves_item_order_under_async_completion` — ordering guarantee from FEAT-1075: submit 4 items with durations `[3.0, 1.0, 2.0, 0.5]` seconds (deliberately inverted so completion order ≠ submission order). Assert `result.all_results[i].item == items[i]` for all `i`; assert `result.all_results[i].item_index == i`; assert completion timestamps are out of order (sanity check that the scheduling was actually async). Catches regressions that would append from `as_completed()` instead of writing into pre-allocated slots.
- `timeout_seconds`: worker exceeding timeout records `ParallelItemResult(verdict="no", terminated_by="timeout", error="...")` and is aggregated under `fail_mode` (`collect` → lands in `result.failed`; `fail_fast` → cancels remaining futures); `timeout_seconds=None` means no timeout enforced
- Edge: 0 items → immediate `ParallelResult(all_results=[], verdict="yes")` (also assert `.succeeded == [] and .failed == []`)
- Edge: 1 item fails of 1 → `result.all_results[0].verdict == "no"`; `result.verdict == "no"`; `result.failed[0].error` is a non-empty string

### End-to-end integration test

One end-to-end test must exercise a real parallel loop YAML through `FSMExecutor.run()` **without mocking `ParallelRunner` or `FSMExecutor`**:

- Add `test_parallel_state_end_to_end` to `scripts/tests/test_ll_loop_execution.py` (this file already exercises full `PersistentExecutor.run()` paths per the wiring notes on FEAT-1076)
- Fixture: a loop YAML with a `parallel:` state pointing at ≥2 toy sub-loops (smallest possible — e.g., two trivial one-state sub-loops that immediately reach `done`)
- Assert: fan-out actually executes N sub-loops (verify via captures), verdict aggregation produces the expected `"yes"`/`"partial"`/`"no"` value, and the outer loop routes correctly on each of `on_yes` / `on_partial` / `on_no` — parameterize or run three variants to cover all three routes
- Use `isolation: "thread"` (the new default) and `timeout_seconds: None` for speed; worktree-mode integration coverage stays in the unit tests

### Real-threading concurrency tests (not mocked)

Most `test_parallel_runner.py` tests mock `FSMExecutor` for speed and determinism. That leaves real `ThreadPoolExecutor` behavior unexercised — the exact surface where race conditions hide. Add a dedicated `TestParallelRunnerRealThreading` class in `test_parallel_runner.py` that runs real threads against minimal real workloads:

- **`test_real_threads_deep_copy_isolates_mutations`** — 4 real workers, each mutates nested structures in its context. Use real `ThreadPoolExecutor` (no mocks). Assert each worker's mutations land only in its own `ParallelItemResult.captures` and the parent dict is unchanged. This is the canonical regression test for the deep-copy contract.
- **`test_real_threads_max_workers_enforced`** — 20 items, `max_workers=2`. Each worker records its start timestamp into a shared `threading.Lock`-protected list. After the run, assert at most 2 timestamps overlap at any point (no more than `max_workers` concurrent). Catches regressions that would silently let `ThreadPoolExecutor` exceed its pool.
- **`test_real_threads_fail_fast_cancels_pending`** — 10 items, `fail_mode: fail_fast`, item 2 fails. Track how many worker bodies actually started (shared counter incremented at the top of each worker). Assert the counter is strictly less than 10 — pending futures were cancelled before starting. Uses real futures + cancellation, not mocked.
- **`test_real_threads_timeout_one_while_others_complete`** — 4 workers, `timeout_seconds=1`, worker 2 sleeps 5 seconds. Assert worker 2 is recorded as timed-out, workers 0/1/3 complete normally, overall verdict is `"partial"`. Catches interaction bugs between timeout and aggregation.

These tests MUST use `time.sleep` deliberately in worker bodies (not `time.monotonic` polling) so that actual thread scheduling is exercised. They may be slightly slower than the mocked suite (target < 5s total); tag with `@pytest.mark.integration` if they push overall test time up noticeably (note: `integration` is already registered per `pyproject.toml:106`, so no new marker needed).

**CI discipline — REQUIRED**: `TestParallelRunnerRealThreading` MUST run in the **default** `python -m pytest scripts/tests/` invocation used by CI. It MUST NOT be gated behind `@pytest.mark.slow` (or any marker that is excluded by default), and it MUST NOT be behind an opt-in env var. Tagging with `@pytest.mark.integration` is permitted (that marker is collected by default), but the class must NOT be skipped unless the whole suite is running under `-m "not integration"`. Rationale: OS-scheduling races only surface under real threads; if this class doesn't run on every PR, thread bugs escape review and ship silently.

### Singleton thread-safety tests (new — class `TestParallelRunnerSingletonSafety` in `test_parallel_runner.py`)

These cover the thread-safety contract added to FEAT-1075. All four use real `ThreadPoolExecutor` (no mocks) with ≥4 workers and light real workloads:

- **`test_parent_checkpoint_file_not_written_from_worker_threads`** — instrument `PersistentExecutor._save_state()` with a `threading.get_ident()` check; spawn 4 workers and assert every call came from the main thread's TID. Regression gate for "parent checkpoint stays main-thread-only."
- **`test_worker_session_jsonl_writes_are_one_line_atomic`** — 4 workers each write 50 events into session JSONL files; after the run, `json.loads()` each line and assert every line parses cleanly (no interleaved or truncated records). Proves single-line atomic-append discipline.
- **`test_config_snapshot_is_read_only_from_worker_threads`** — mock `BRConfig.load()` to record thread IDs that call it; spawn 4 workers and assert load-call TID is only the main thread's. Workers must read from their snapshot, not reload.
- **`test_module_level_caches_not_lazily_written_from_workers`** — for each module-level cache the runner depends on (fragment cache, validator cache), assert that the cache's size is identical before and after `runner.run()` was called from workers with a pre-warmed cache; any cache growth from a worker thread fails the test.

### `items_hash` resume warning test (new — folded from FEAT-1174 tightening)

- **`test_items_hash_mismatch_warning_is_prominent`** — suspend a parallel state mid-run, mutate the `items` source on disk, resume. Assert the mismatch log line appears at `WARNING` level (not `DEBUG`), contains both the pre-suspend and post-resume hash values, names the resume action (`"full re-run of parallel state <state>"`), and appears in the summary printed by `ll-loop resume` at exit. Regression gate for "silent re-run" footgun.

### Existing test files to extend

**test_fsm_executor.py** — Add parallel state dispatch tests to `TestSubLoopExecution` class at line 3634:

- `test_parallel_state_dispatches()` — state with `parallel:` config calls `_execute_parallel_state()`
- `test_parallel_state_captures_merged()` — captures stored at `self.captured[state_name]["results"]`
- `test_parallel_state_routes_on_yes()`, `_on_partial()`, `_on_no()` — route correctness

**test_fsm_schema.py** — Add `TestParallelStateConfig` class:

- Round-trip `to_dict()` / `from_dict()` with all fields
- `from_dict()` with only required fields (defaults applied)
- `StateConfig` with `parallel:` serializes `parallel` key; without, key absent

**test_fsm_schema.py** (not `test_fsm_validation.py`) — Add mutual exclusion cases as a new class `TestParallelMutualExclusion`, following the existing `test_loop_and_action_mutual_exclusion` pattern at `test_fsm_schema.py:1866`:

- `parallel` + `action` → validation error
- `parallel` + `loop` → validation error
- `parallel` + `next` → validation error
- `max_workers: 0` → validation error
- `isolation: "invalid"` → validation error
- `fail_mode: "invalid"` → validation error

**test_fsm_validation.py** — `test_fsm_validation.py:18` has `TestExtraRoutesReachability`; line 69 has `TestRateLimitFieldValidation`. Mutual exclusion tests don't belong here. Add one test that a `parallel:` state with routing does NOT trigger the no-transition guard (the guard at `validation.py:271` gains `and not has_parallel` as part of FEAT-1074).

### New fixture: scripts/tests/fixtures/fsm/parallel-loop.yaml

Minimal `parallel:` state for `TestLoadAndValidate`-style round-trip tests:

```yaml
states:
  fan_out:
    parallel:
      items: "${captured.queue.output}"
      loop: refine-to-ready-issue
      max_workers: 2
      isolation: thread
      fail_mode: collect
      context_passthrough: false
    route:
      on_yes: done
      on_partial: done
      on_no: done
  done:
    next: ~
```

### Fuzz and display tests

**test_fsm_schema_fuzz.py:135** — Add `parallel` key to `malformed_state_config` hypothesis strategy so `StateConfig.from_dict()` fuzz coverage includes malformed `parallel:` inputs. Insert after the `route` block (ends at `:174`), before the `# Add unexpected fields` block at `:175`.

**test_ll_loop_display.py:TestStateBadges** (line 2353) — Add test for `parallel:` state badge modeled after `test_get_state_badge_sub_loop` at line 2383.

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_executor.py` — Add `TestParallelExecution` class (new class, not extending `TestSubLoopExecution`) modeled after `TestSubLoopExecution:3634`
- `scripts/tests/test_fsm_schema.py` — Add `TestParallelStateConfig` and `TestParallelMutualExclusion` classes
- `scripts/tests/test_fsm_validation.py` — Add one test that `parallel:` state doesn't trigger no-transition guard
- `scripts/tests/test_fsm_schema_fuzz.py` — Add `parallel` to `malformed_state_config` strategy at line 135 (after line 174, before `# Add unexpected fields` at line 175)
- `scripts/tests/test_ll_loop_display.py` — Add parallel badge test to `TestStateBadges:2353` (requires `_PARALLEL_BADGE` from FEAT-1078)
- `scripts/tests/test_ll_loop_execution.py` — Add `test_parallel_state_end_to_end` inside `TestEndToEndExecution` class (append at end of class; class ends at line 560, `TestLLMFlags` begins at 562); write `parallel:` loop YAML inline to `tmp_path / ".loops"`, run `main_loop()` with `monkeypatch.chdir(tmp_path)`, assert `on_yes`/`on_partial`/`on_no` routes; uses real `FSMExecutor.run()` without mocking `ParallelRunner` [wiring pass added by `/ll:wire-issue`]

### Files to Create
- `scripts/tests/test_parallel_runner.py` — New unit tests for `ParallelRunner` (flat in `scripts/tests/`, no subdirectory)
- `scripts/tests/fixtures/fsm/parallel-loop.yaml` — New fixture

### Existing Parallel Coverage
- `scripts/tests/test_parallel_types.py` — Already covers parallel type definitions; `test_parallel_runner.py` must not duplicate this

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/parallel_runner.py` — Implementation under test (FEAT-1075; does not exist yet)
- `scripts/little_loops/fsm/executor.py` — `_execute_parallel_state()` under test (FEAT-1076; proposed insertion near existing `_execute_sub_loop` at `executor.py:366` / `_execute_state` at `executor.py:432`). Pre-refinement anchors `:383` / `:402` have drifted due to rate-limit circuit additions.
- `scripts/little_loops/fsm/schema.py:180` — `ParallelStateConfig`, `StateConfig` under test (FEAT-1074; `parallel` field added after the existing `StateConfig` field block around `schema.py:233`)
- `scripts/little_loops/fsm/validation.py:271` — No-transition guard; gains `and not has_parallel` (FEAT-1074); one validation test covers this
- `scripts/little_loops/cli/loop/layout.py:109` — `_SUB_LOOP_BADGE` defined here; must add `_PARALLEL_BADGE` constant (FEAT-1078) before badge test compiles. **Verified 2026-04-20**: despite FEAT-1078 being in `.issues/completed/`, `_PARALLEL_BADGE` does not yet exist in `layout.py` — the badge test step remains gated and cannot compile until this constant is added.

### Similar Patterns
- `scripts/tests/test_fsm_executor.py:3634` — `TestSubLoopExecution` — Model `TestParallelExecution` after this class; use write-YAML-to-`tmp_path / ".loops"` pattern, `FSMExecutor(parent_fsm, loops_dir=loops_dir)`, assert `result.final_state` and `executor.captured`
- `scripts/tests/test_fsm_schema.py:1866` — `test_loop_and_action_mutual_exclusion` — Template for `TestParallelMutualExclusion`; constructs `FSMLoop` inline, calls `validate_fsm()`, asserts on error message strings
- `scripts/tests/test_ll_loop_display.py:2383` — `test_get_state_badge_sub_loop` — Template for parallel badge test; constructs `StateConfig(parallel=...)` inline, asserts `_get_state_badge(state) == _PARALLEL_BADGE`
- `scripts/tests/test_fsm_schema_fuzz.py:174` — End of `route` block in `malformed_state_config` (strategy defined at `:135`); add `parallel` block after this line, before `# Add unexpected fields` block at line 175
- `scripts/tests/test_fsm_schema.py:1817` — `TestSubLoopStateConfig` — Round-trip pattern for `TestParallelStateConfig`; tests `to_dict()` includes/excludes fields, `from_dict()` applies defaults
- `scripts/little_loops/fsm/executor.py:417–423` — Worker success condition pattern in `_execute_sub_loop`: `child_result.terminated_by == "terminal" and child_result.final_state == "done"` — same test the parallel runner per-worker success check must mirror

### Tests
- N/A — This issue IS the test implementation

### Regression Surfaces

_Wiring pass added by `/ll:wire-issue` (line refs refreshed 2026-04-20):_
- `scripts/tests/test_fsm_schema.py:780` (`TestFSMValidation`) — `len(error_list) == 0` assertions on minimal valid FSMs; `ParallelStateConfig` added to `StateConfig` must not emit validation errors for non-parallel loops
- `scripts/tests/test_ll_loop_display.py:2388–2391` (`test_sub_loop_badge_takes_precedence_over_action_type`) — sub-loop badge precedence assertions (`loop > action_type`); the position where FEAT-1078 inserts the `parallel:` check in `_get_state_badge()` must not break this existing priority test
- `scripts/tests/test_ll_loop_display.py:2455–2461` (`test_route_badge_lower_priority_than_sub_loop`) — `loop > route` badge priority assertions; same concern as above

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md:115` — hardcodes `"FSM YAML fixtures (8 files)"`; will become stale when `parallel-loop.yaml` is added (current count is 9, new count will be 10); not enforced by `ll-verify-docs` (doc_counts.py only tracks commands/agents/skills). Update the count after the fixture is created.

### Configuration

_Wiring pass added by `/ll:wire-issue` (line refs refreshed 2026-04-20):_
- `scripts/pyproject.toml:107` — `--strict-markers` is active (verified at line 107, not 106); any `@pytest.mark.*` decoration on new test methods must be pre-registered in `[tool.pytest.ini_options].markers` at `:113` (currently declared: `integration`, `slow`). Do not introduce new markers.
- `scripts/pyproject.toml:134` — `fail_under = 80` coverage gate; new implementation files (`parallel_runner.py`, executor dispatch path, schema `parallel` field, layout badge) count against coverage. New tests must exercise those paths to keep the gate green.

## Implementation Steps

1. Create `scripts/tests/test_parallel_runner.py` (flat in `scripts/tests/`, not a subdirectory) with `ParallelRunner` unit tests; mock `FSMExecutor` workers; assert on `ParallelResult` fields; worker success = `terminated_by == "terminal" and final_state == "done"`
2. Add new `TestParallelExecution` class to `test_fsm_executor.py` (after `TestSubLoopExecution:3472`); write child YAML to `tmp_path / ".loops"`, run `FSMExecutor`, assert routes and `captured[state_name]["results"]`
3. Add `TestParallelStateConfig` and `TestParallelMutualExclusion` classes to `test_fsm_schema.py` (following `TestSubLoopStateConfig:1673` and `test_loop_and_action_mutual_exclusion:1722` patterns)
4. Add one `parallel:` no-transition-guard test to `test_fsm_validation.py` (verifies `parallel:` states are not falsely flagged)
5. Create `scripts/tests/fixtures/fsm/parallel-loop.yaml` and add an explicit test method to `test_fsm_schema.py:TestLoadAndValidate` that references `fsm_fixtures / "parallel-loop.yaml"` by name — no auto-discovery occurs for files in `fixtures/fsm/`; the fixture must be explicitly named in a test method
6. Add `parallel` malformed key to `malformed_state_config` strategy in `test_fsm_schema_fuzz.py` after line 174 (before `unexpected_*` block)
7. Add parallel badge test to `test_ll_loop_display.py:TestStateBadges` — requires FEAT-1078 to export `_PARALLEL_BADGE`; implement this step last
8. Add `test_parallel_state_end_to_end` to `TestEndToEndExecution` class in `test_ll_loop_execution.py` (append at end of class; class ends at line 560, `TestLLMFlags` begins at 562); write a `parallel:` loop YAML inline to `tmp_path / ".loops"`, run via `main_loop()` with `monkeypatch.chdir(tmp_path)`, cover all three routes (`on_yes`/`on_partial`/`on_no`); uses real `FSMExecutor.run()` without mocking `ParallelRunner` [added by `/ll:wire-issue`]
9. Run full test suite: `python -m pytest scripts/tests/test_parallel_runner.py scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_validation.py scripts/tests/test_ll_loop_display.py scripts/tests/test_ll_loop_execution.py -x`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Verify `test_fsm_schema.py:TestLoadAndValidate` has an explicit test method for `parallel-loop.yaml` (no glob discovery — the fixture file must be named directly in a test method, e.g., `fsm_fixtures / "parallel-loop.yaml"`)
10. Use only pre-declared pytest markers (`integration`, `slow`); `pyproject.toml:106` `--strict-markers` causes collection failure for any undeclared marker
11. Before merging, run `python -m pytest scripts/tests/ --cov --cov-fail-under=80` to confirm the `fail_under = 80` gate passes with new implementation files in scope

## Files to Create/Modify

- `scripts/tests/test_parallel_runner.py` — New unit tests for `ParallelRunner` (flat in `scripts/tests/`)
- `scripts/tests/test_fsm_executor.py` — Add new `TestParallelExecution` class
- `scripts/tests/test_fsm_schema.py` — Add `TestParallelStateConfig` and `TestParallelMutualExclusion` classes
- `scripts/tests/test_fsm_validation.py` — Add one `parallel:` no-transition-guard test
- `scripts/tests/fixtures/fsm/parallel-loop.yaml` — New fixture
- `scripts/tests/test_fsm_schema_fuzz.py` — Add `parallel` to `malformed_state_config` strategy at line 174
- `scripts/tests/test_ll_loop_display.py` — Add parallel badge test to `TestStateBadges` (last step; requires FEAT-1078)
- `scripts/tests/test_ll_loop_execution.py` — Add `test_parallel_state_end_to_end` integration test (three route variants: on_yes/on_partial/on_no); runs real `FSMExecutor.run()` with a parallel state and ≥2 toy sub-loops, `isolation: "thread"`

## Implementation Notes

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **ParallelRunner.run() signature**: `run(items: list[str], loop_name: str, config: ParallelStateConfig, parent_context: dict | None = None) -> ParallelResult`
- **Worker success condition**: `child_result.terminated_by == "terminal" and child_result.final_state == "done"` (mirrors `_execute_sub_loop()` at `executor.py:417–423`)
- **Captures storage**: `self.captured[self.current_state] = {"results": [<ParallelItemResult-as-dict>, ...]}` — each entry has `item`, `item_index`, `verdict`, `terminated_by`, `captures`, `error` (see FEAT-1076 dispatch code)
- **Routing**: `_route()` at `executor.py:786–836` already handles `"yes"/"partial"/"no"` at lines 820–830 — `_execute_parallel_state()` calls `self._route(state, result.verdict, ctx)` directly
- **`test_fsm_validation.py` scope**: File is now 266 lines with two classes (`TestExtraRoutesReachability:18`, `TestRateLimitFieldValidation:69`). Mutual exclusion tests still go in `test_fsm_schema.py` (where `test_loop_and_action_mutual_exclusion:1866` lives). The single validation test added here is for the no-transition guard at `validation.py:271`.
- **`_PARALLEL_BADGE` gate**: Badge test imports `_PARALLEL_BADGE` from `little_loops.cli.loop.layout` — this constant does not exist until FEAT-1078. `_SUB_LOOP_BADGE` is defined at `layout.py:109` for reference. Implement badge test last and guard with a skip if not yet available.
- **`test_parallel_types.py`**: Already exists at `scripts/tests/test_parallel_types.py`; review its contents before writing `test_parallel_runner.py` to avoid duplicating `ParallelResult` field assertions. Confirmed: it covers `little_loops.parallel.types` (the ll-parallel orchestrator layer), NOT `little_loops.fsm` types — no duplication risk with `ParallelStateConfig` or FSM `ParallelResult`.
- **`fsm_fixtures` fixture**: Defined at `test_fsm_schema.py:33` as `Path(__file__).parent / "fixtures" / "fsm"`. The parallel-loop.yaml test method in `TestLoadAndValidate:1541` must accept `fsm_fixtures: Path` as a parameter and follow the `test_load_valid_yaml()` pattern (e.g., `fixture_path = fsm_fixtures / "parallel-loop.yaml"`).
- **Fuzz block code pattern**: The `parallel` block to insert in `malformed_state_config` (strategy at `test_fsm_schema_fuzz.py:135`) after the `route` block ending at `:174`, before line 175 (`# Add unexpected fields`):
  ```python
  # Add parallel config
  if draw(st.booleans()):
      state["parallel"] = draw(
          st.one_of(
              st.fixed_dictionaries({
                  "items": st.text(min_size=1, max_size=100),
                  "loop": st.text(min_size=1, max_size=50),
              }),
              st.integers(),
              st.text(),
              st.none(),
          )
      )
  ```
- **Implementation status of dependencies**: As of this refinement pass, `parallel_runner.py`, `ParallelStateConfig` in schema.py, `_execute_parallel_state()` in executor.py, and `_PARALLEL_BADGE` in layout.py all do NOT yet exist. FEAT-1074, FEAT-1075, FEAT-1076, and FEAT-1078 must complete first — tests in this issue will fail to import until those implementations land.

## Dependencies

- FEAT-1074, FEAT-1075, FEAT-1076 must be complete (tests exercise those implementations)

## Acceptance Criteria

- All new tests pass: `python -m pytest scripts/tests/test_parallel_runner.py scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_validation.py scripts/tests/test_ll_loop_display.py scripts/tests/test_ll_loop_execution.py -x`
- At least one end-to-end test exercises a real parallel loop YAML through `FSMExecutor.run()` (not mocked) with ≥2 toy sub-loops, verifying fan-out, verdict aggregation, and correct routing on each of `on_yes`, `on_partial`, `on_no`
- `test_parallel_runner_context_passthrough_is_deep_copy_per_worker` exists and asserts that each worker receives an independent deep copy: workers may mutate nested containers freely without affecting sibling workers or the parent's `self.captured`
- `test_fsm_schema.py:TestFSMValidation` — no regressions in existing error-count assertions
- `test_fsm_fragments.py` + `test_builtin_loops.py` — all 33 built-in loops still pass validation
- `parallel-loop.yaml` fixture round-trips without validation errors
- Fuzz test includes `parallel` key in malformed strategy
- `TestParallelRunnerRealThreading` class runs in default CI (no `@pytest.mark.slow` gating); all four tests pass on every PR
- `TestParallelRunnerSingletonSafety` class (four tests) asserts no config, checkpoint, session JSONL, or module-cache writes originate from worker threads
- `test_items_hash_mismatch_warning_is_prominent` asserts the mismatch warning is WARN-level (not DEBUG), contains both hashes, and is echoed in the resume-summary output

## API/Interface

N/A - No public API changes (test files only)

## Impact

- **Priority**: P2 - Required gate for FEAT-1072 (parent) completion; unblocks merging the parallel state feature
- **Effort**: Medium - Multiple test files across executor, schema, validation, fuzz, and display; patterns are well-established in the existing test suite
- **Risk**: Low - Test-only changes; no production code modified
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `tests`

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-20_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 85/100 → HIGH CONFIDENCE

### Concerns
- **Blocking dependency gap**: FEAT-1074, FEAT-1075, and FEAT-1076 are all still open (features/ not completed/). `ParallelRunner`, `ParallelStateConfig`, `StateConfig.parallel`, and `_execute_parallel_state()` don't exist — any attempt to run the new tests will produce `ImportError` or `AttributeError`. Implementation order must be 1074 → 1075 → 1076 → 1077.
- **FEAT-1078 anomaly (verified 2026-04-20)**: although FEAT-1078 is filed under `.issues/completed/`, `_PARALLEL_BADGE` is **not** present in `scripts/little_loops/cli/loop/layout.py` — only `_SUB_LOOP_BADGE` (line 109) exists. The earlier confidence-check claim that the badge test was unblocked is incorrect. The badge test step must either (a) wait for `_PARALLEL_BADGE` to actually land, (b) add the constant as part of this issue, or (c) be deferred to a follow-up. Treat the badge step as still gated.

---

## Session Log
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `ffa52965-8df7-4476-a2af-96e098002a6a.jsonl`
- `/ll:refine-issue` - 2026-04-21T02:22:01 - `44c14e5a-4278-4377-8d15-bde5c92f7b4b.jsonl`
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `cd52fa57-9703-45ce-81ef-323e54add01d.jsonl`
- `/ll:wire-issue` - 2026-04-21T02:16:50 - `68123ceb-d691-4c92-a1ba-bff0b179367e.jsonl`
- `/ll:refine-issue` - 2026-04-21T02:11:22 - `8b558b47-c898-4962-9944-ec3045e3607e.jsonl`
- `/ll:confidence-check` - 2026-04-12T23:00:00 - `9da6eb97-069e-44c5-91dc-b06213bbdb44.jsonl`
- `/ll:refine-issue` - 2026-04-12T22:32:19 - `c1a0289e-787a-444b-9e0f-8948f014d350.jsonl`
- `/ll:wire-issue` - 2026-04-12T22:26:52 - `40ba99b1-af2b-4221-bf0c-5829fac63188.jsonl`
- `/ll:refine-issue` - 2026-04-12T22:21:01 - `c0de4a6f-059b-48e7-a248-7017de5869a3.jsonl`
- `/ll:format-issue` - 2026-04-12T22:13:02 - `0a3bd623-b6f1-4633-9128-0ace3241e1e4.jsonl`
- `/ll:issue-size-review` - 2026-04-12T21:00:00 - `c8e4e49c-4e79-4270-9839-915fa38b03f2.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-20
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-1199: Parallel Runner Unit Tests (test_parallel_runner.py)
- FEAT-1200: Parallel State Schema, Validation, and Fuzz Tests
- FEAT-1201: Parallel State Executor, Integration, and Display Tests

---

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-21T02:27:44 - `eb2a4d4b-681c-4336-8ebc-dacfae9712d8.jsonl`
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `eb2a4d4b-681c-4336-8ebc-dacfae9712d8.jsonl`
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `ffa52965-8df7-4476-a2af-96e098002a6a.jsonl`
- `/ll:refine-issue` - 2026-04-21T02:22:01 - `44c14e5a-4278-4377-8d15-bde5c92f7b4b.jsonl`
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `cd52fa57-9703-45ce-81ef-323e54add01d.jsonl`
- `/ll:wire-issue` - 2026-04-21T02:16:50 - `68123ceb-d691-4c92-a1ba-bff0b179367e.jsonl`
- `/ll:refine-issue` - 2026-04-21T02:11:22 - `8b558b47-c898-4962-9944-ec3045e3607e.jsonl`
- `/ll:confidence-check` - 2026-04-12T23:00:00 - `9da6eb97-069e-44c5-91dc-b06213bbdb44.jsonl`
- `/ll:refine-issue` - 2026-04-12T22:32:19 - `c1a0289e-787a-444b-9e0f-8948f014d350.jsonl`
- `/ll:wire-issue` - 2026-04-12T22:26:52 - `40ba99b1-af2b-4221-bf0c-5829fac63188.jsonl`
- `/ll:refine-issue` - 2026-04-12T22:21:01 - `c0de4a6f-059b-48e7-a248-7017de5869a3.jsonl`
- `/ll:format-issue` - 2026-04-12T22:13:02 - `0a3bd623-b6f1-4623-9128-0ace3241e1e4.jsonl`
- `/ll:issue-size-review` - 2026-04-12T21:00:00 - `c8e4e49c-4e79-4270-9839-915fa38b03f2.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2
