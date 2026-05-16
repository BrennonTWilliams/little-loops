---
discovered_date: "2026-04-20"
discovered_by: issue-size-review

size: Very Large
confidence_score: 80
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
parent: FEAT-1077
status: done
completed_at: 2026-05-10T00:00:00Z
---

# FEAT-1201: Parallel State Executor, Integration, and Display Tests

## Summary

Add `TestParallelExecution` to `test_fsm_executor.py`, add `test_parallel_state_end_to_end` to `test_ll_loop_execution.py`, and add the parallel badge test to `test_ll_loop_display.py`. These are the highest-dependency tests — all require FEAT-1074/1075/1076, and the badge test additionally requires FEAT-1078.

## Parent Issue

Decomposed from FEAT-1077: Parallel State Tests

## Use Case

**Who**: Developer closing out the parallel state feature after FEAT-1074/1075/1076 are complete

**Context**: These are the final validation tests that prove the fully-integrated parallel state feature works end-to-end.

**Goal**: Extend three existing test files to cover executor dispatch, integration routing, and display badge for `parallel:` states.

**Outcome**: `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_ll_loop_execution.py scripts/tests/test_ll_loop_display.py -x` passes green.

## Proposed Solution

### test_fsm_executor.py — Add TestParallelExecution class

Model after `TestSubLoopExecution` (spans lines 3634–3956). Insert the new `TestParallelExecution` class between `TestSubLoopExecution` (ends at line 3956) and `TestRouteContext` (begins at line 3957):

- `test_parallel_state_dispatches()` — state with `parallel:` config calls `_execute_parallel_state()`
- `test_parallel_state_captures_merged()` — captures stored at `self.captured[state_name]["results"]`
- `test_parallel_state_routes_on_yes()`, `_on_partial()`, `_on_no()` — route correctness

Pattern: write child YAML to `tmp_path / ".loops"`, run `FSMExecutor(parent_fsm, loops_dir=loops_dir)`, assert `result.final_state` and `executor.captured`.

### test_ll_loop_execution.py — Add test_parallel_state_end_to_end

Append at the end of `TestEndToEndExecution` class (class ends at line 560; `TestLLMFlags` begins at 562):

- Fixture: a loop YAML with a `parallel:` state pointing at ≥2 toy sub-loops (smallest possible — two trivial one-state sub-loops that immediately reach `done`)
- Write `parallel:` loop YAML inline to `tmp_path / ".loops"`, run `main_loop()` with `monkeypatch.chdir(tmp_path)`
- Assert fan-out actually executes N sub-loops (verify via captures), verdict aggregation produces the expected value, and the outer loop routes correctly on each of `on_yes` / `on_partial` / `on_no` — write three separate named methods (`test_parallel_state_end_to_end_on_yes`, `_on_partial`, `_on_no`) per the codebase convention at `test_fsm_executor.py:1023–1130`; do NOT use `@pytest.mark.parametrize`
- Use `isolation: "thread"` and `timeout_seconds: None` for speed
- MUST use real `FSMExecutor.run()` without mocking `ParallelRunner` — this is the canonical end-to-end gate

### test_ll_loop_display.py — Add parallel badge test (gated on FEAT-1078)

Add to `TestStateBadges:2353`, modeled after `test_get_state_badge_sub_loop:2383`:

- Construct `StateConfig(parallel=...)` inline
- Assert `_get_state_badge(state) == _PARALLEL_BADGE`
- `_PARALLEL_BADGE` is imported from `little_loops.cli.loop.layout` — this constant does NOT exist until FEAT-1078 lands (re-verified 2026-04-21: `_SUB_LOOP_BADGE` exists at `layout.py:109` but `_PARALLEL_BADGE` is absent; FEAT-1078 is filed in `.issues/completed/` but its deliverable is not in the code, so treat the completion as stale)
- Implement this test last. **Preferred path**: add `_PARALLEL_BADGE` to `layout.py` and wire it into `_get_state_badge()` as part of this issue, then also add the corresponding assertion to `test_badge_constants_match_spec:2356`. Avoid `pytest.importorskip` / `@pytest.mark.skipif` — no such precedent exists in `scripts/tests/` (inline `pytest.skip(...)` is the only conditional-skip idiom in the tree, and is not idiomatic for missing-symbol gating)

### Regression Surfaces

- `scripts/tests/test_ll_loop_display.py:2388–2391` (`test_sub_loop_badge_takes_precedence_over_action_type`) — sub-loop badge precedence assertions; the position where FEAT-1078 inserts the `parallel:` check in `_get_state_badge()` must not break this existing priority test
- `scripts/tests/test_ll_loop_display.py:2455–2461` (`test_route_badge_lower_priority_than_sub_loop`) — `loop > route` badge priority assertions; same concern
- `scripts/tests/test_ll_loop_display.py:2356–2362` (`test_badge_constants_match_spec`) — asserts on `_ACTION_TYPE_BADGES`, `_SUB_LOOP_BADGE`, and `_ROUTE_BADGE` but not `_PARALLEL_BADGE`; must add `_PARALLEL_BADGE` assertion here when the constant is introduced (by FEAT-1078 or this issue) [wiring pass]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Verify `scripts/little_loops/fsm/__init__.py` exports `ParallelStateConfig` and `ParallelRunner` before writing test imports (FEAT-1074/1075 deliverables — verify, do not add here)
5. Update `test_badge_constants_match_spec` at `test_ll_loop_display.py:2356` — add `_PARALLEL_BADGE` assertion alongside existing `_SUB_LOOP_BADGE`/`_ROUTE_BADGE` checks when `_PARALLEL_BADGE` is added to `layout.py`

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_executor.py` — Add `TestParallelExecution` class (between `TestSubLoopExecution` which ends at line 3956 and `TestRouteContext` at line 3957)
- `scripts/tests/test_ll_loop_execution.py` — Add `test_parallel_state_end_to_end` inside `TestEndToEndExecution` (append at end; class ends at line 560)
- `scripts/tests/test_ll_loop_display.py` — Add parallel badge test to `TestStateBadges:2353`

### Dependent Files (all must exist before implementation)
- `scripts/little_loops/fsm/parallel_runner.py` — FEAT-1075
- `scripts/little_loops/fsm/executor.py` — `_execute_parallel_state()` — FEAT-1076 (proposed insertion near `_execute_sub_loop` at `executor.py:366` / `_execute_state` at `executor.py:432`)
- `scripts/little_loops/fsm/schema.py:180` — `ParallelStateConfig`, `StateConfig.parallel` — FEAT-1074
- `scripts/little_loops/cli/loop/layout.py:109` — `_PARALLEL_BADGE` constant — FEAT-1078 (must add before badge test compiles)
- `scripts/little_loops/fsm/__init__.py` — must export `ParallelStateConfig` in schema import block (lines 120–127) and `__all__` (lines 143–195) when FEAT-1074 lands; `ParallelRunner`/`ParallelResult` similarly when FEAT-1075 lands; verify before writing test imports [wiring pass]

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current tree on 2026-04-21:_

- **Dependency status (all confirmed MISSING as of 2026-04-21)** — `parallel_runner.py` does not exist; `ParallelStateConfig` is absent from `schema.py` (`StateConfig` at line 180 has `loop` at line 251 but no `parallel` field); `_execute_parallel_state()` is not present in `executor.py`; `_PARALLEL_BADGE` is not defined in `layout.py` (only `_SUB_LOOP_BADGE = "↳⟳"` at line 109).
- **No existing sub-loop E2E test in `test_ll_loop_execution.py`** — no tests in that file currently exercise sub-loops through `main_loop()`. The new `test_parallel_state_end_to_end` will be the first hierarchical end-to-end test in that module; no precedent exists there to copy, so model after `TestSubLoopExecution` in `test_fsm_executor.py` plus the existing E2E subprocess-mock pattern below.
- **Subprocess mock fixture** — `_make_mock_popen_factory(returncode=..., stdout=..., stderr=...)` at `test_ll_loop_execution.py:26` is the canonical mock factory. The established E2E pattern in `TestEndToEndExecution` (lines 95–560) is:
  ```python
  monkeypatch.chdir(tmp_path)
  with patch("little_loops.fsm.executor.subprocess.Popen") as mock_popen:
      mock_popen.side_effect = _make_mock_popen_factory(returncode=0, stdout="yes\n")
      with patch.object(sys, "argv", ["ll-loop", "run", "<loop-name>"]):
          from little_loops.cli import main_loop
          result = main_loop()
  ```
  For the parallel E2E, the toy sub-loops should be designed to terminate on their initial state (e.g. `initial: done` with `states: {done: {terminal: true}}`) so that `subprocess.Popen` is never invoked — avoiding the need to coordinate mock call counts across parallel workers.
- **TestSubLoopExecution patterns to copy** (from `test_fsm_executor.py:3634–3956`):
  - Write child YAML inline to `tmp_path / ".loops"`, build parent via `FSMLoop` + `StateConfig` dataclasses
  - Construct `FSMExecutor(parent_fsm, loops_dir=loops_dir)` with the `loops_dir` kwarg
  - Assert on `result.final_state` and `result.terminated_by`
  - For route variants, pair a success child with a failure child (the `on_no` branch is forced via a child YAML with `max_iterations: 1` and a non-terminating action — see `test_sub_loop_failure_routes_to_on_failure:3658`)
- **Badge test symbol import** — `test_ll_loop_display.py` already imports `_SUB_LOOP_BADGE` from `little_loops.cli.loop.layout` (lines 15–21). The parallel badge test should add `_PARALLEL_BADGE` to the same import block; mirror `test_get_state_badge_sub_loop:2383–2386` literally:
  ```python
  def test_get_state_badge_parallel(self) -> None:
      state = StateConfig(parallel=...)  # shape per FEAT-1074 ParallelStateConfig
      assert _get_state_badge(state) == _PARALLEL_BADGE
  ```
- **Coverage implication** — `scripts/pyproject.toml:134` enforces `fail_under = 80`. The new implementation files (`parallel_runner.py`, parallel branch in `_execute_state`, `ParallelStateConfig`) land via FEAT-1074/1075/1076. If their own sibling tests (FEAT-1202–1215, 1219) don't already exercise every branch, the tests added here are the safety net — particularly the real-E2E test, which is the only test that runs `ParallelRunner` un-mocked through `main_loop()`.

_Second `/ll:refine-issue` pass on 2026-04-21 (post-wiring) — additional findings:_

- **FEAT-1078 dependency state is inconsistent.** `.issues/completed/P2-FEAT-1078-parallel-state-wiring-display-docs.md` exists (parent/umbrella ticket moved to completed), but `_PARALLEL_BADGE` is still absent from `scripts/little_loops/cli/loop/layout.py` and the `parallel` keyword does not appear anywhere in that file. Treat FEAT-1078's completed marker as stale for this issue's purposes: the badge-test section of this issue MUST either (a) add `_PARALLEL_BADGE = "⇉"` (or chosen glyph) to `layout.py:109` alongside `_SUB_LOOP_BADGE` and wire it into `_get_state_badge()`, OR (b) guard the test. Prefer (a) — see pattern note below on why skipif is not precedented.
- **Ternary route tests: use three separate named methods, NOT `@pytest.mark.parametrize`.** The codebase convention in `test_fsm_executor.py` is one method per route variant with a focused docstring (e.g. `test_on_partial_routes_correctly`, `test_on_partial_shorthand_routes_to_fix_state`, `test_on_partial_missing_falls_through_to_error` at `test_fsm_executor.py:1023–1130`). `@pytest.mark.parametrize` is reserved for uniform input→output mappings (e.g. exit-code→verdict at `test_fsm_executor.py:49`). For the parallel E2E, write three methods: `test_parallel_state_end_to_end_on_yes`, `test_parallel_state_end_to_end_on_partial`, `test_parallel_state_end_to_end_on_no`. Strike the "parameterize or run three variants" ambiguity in the Proposed Solution.
- **No `pytest.mark.skipif` / `pytest.importorskip` precedent exists in `scripts/tests/`.** The only conditional-skip pattern is inline `pytest.skip(...)` inside a test body (e.g. `test_merge_coordinator.py:2560,2572,2689,2701`). Therefore the issue's "guard with a skip (`pytest.importorskip` or `@pytest.mark.skipif`)" option is off-pattern. Concrete plan: **add `_PARALLEL_BADGE` to `layout.py` as part of this issue** if FEAT-1078's decomposed work hasn't landed the constant by implementation time, and update the `test_badge_constants_match_spec` assertion at `test_ll_loop_display.py:2356` accordingly. Avoid introducing a new skip idiom.
- **Terminal-state shortcut confirmed at `scripts/little_loops/fsm/executor.py:257`.** The run loop checks `state_config.terminal` before any action dispatch, so a child YAML of the form `"name: child\ninitial: done\nstates:\n  done:\n    terminal: true"` (as used at `test_fsm_executor.py:3642`) never invokes `subprocess.Popen`. Use this exact shape for the toy sub-loops in the parallel E2E test — avoids needing a `Popen` mock for the canonical success path.
- **End-to-end test anchor points verified on 2026-04-21:** `TestEndToEndExecution` spans `test_ll_loop_execution.py:95–560`, `_make_mock_popen_factory` is at line 26, `TestLLMFlags` begins at 562 — all consistent with earlier refinement findings. Append the new test(s) at the end of `TestEndToEndExecution` (immediately before line 562).
- **`isolation: "thread"` is a `ParallelStateConfig` field (FEAT-1074 deliverable), NOT the FSM loop-YAML `isolation:` key used in `parallel/tasks/*.yaml` fixtures** (e.g. `scripts/little_loops/parallel/tasks/test-suite.yaml:18–21`). No existing `scripts/tests/fixtures/fsm/` YAML uses an `isolation:` key. Verify the ParallelStateConfig schema accepts `isolation: "thread"` (per FEAT-1074) before writing the E2E fixture; if FEAT-1074 instead names the field `worker_isolation` or similar, adjust accordingly.
- **Capture data-structure shape: existing sub-loop captures use `executor.captured[state_name]` containing sub-loop result fields (`test_fsm_executor.py:3788`).** Parallel captures will live at `executor.captured[state_name]["results"]` per FEAT-1076's design — verify the exact key naming against FEAT-1076's landed implementation before finalizing assertions; do not assume `"results"` is correct if FEAT-1076 renames it.

### Similar Patterns
- `scripts/tests/test_fsm_executor.py:3634` — `TestSubLoopExecution` — model `TestParallelExecution` after this
- `scripts/tests/test_ll_loop_display.py:2383` — `test_get_state_badge_sub_loop` — badge test template

### Configuration
- `scripts/pyproject.toml:107` — `--strict-markers` active; only `integration`, `slow` markers are pre-declared
- `scripts/pyproject.toml:134` — `fail_under = 80` coverage gate; new implementation files count against coverage — new tests must exercise those paths

## Dependencies

- **FEAT-1074** must be complete (schema, validation)
- **FEAT-1075** must be complete (ParallelRunner)
- **FEAT-1076** must be complete (`_execute_parallel_state()`)
- **FEAT-1078** must be complete (or `_PARALLEL_BADGE` added here) for the display badge test

## Acceptance Criteria

- `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_ll_loop_execution.py scripts/tests/test_ll_loop_display.py -x` passes green
- At least one end-to-end test exercises a real parallel loop YAML through `FSMExecutor.run()` (not mocked) with ≥2 toy sub-loops, verifying fan-out, verdict aggregation, and correct routing on `on_yes`, `on_partial`, `on_no`
- `TestParallelExecution` covers dispatch, captures, and all three routes
- Display badge test passes (once `_PARALLEL_BADGE` is available)
- No regressions in badge precedence tests at lines 2388–2391 and 2455–2461
- Full suite passes: `python -m pytest scripts/tests/ --cov --cov-fail-under=80`

## Labels

`fsm`, `parallel`, `tests`

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-21_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 79/100 → MODERATE

### Concerns
- All four core dependencies (FEAT-1074, FEAT-1075, FEAT-1076, FEAT-1078) remain in `.issues/features/` — none are complete. Tests cannot pass green until these land; importing non-existent symbols will fail at collection time.
- Sequencing: this issue is a tail-end deliverable. Do not pick up until at minimum FEAT-1074–1076 are in `completed/`.
- FEAT-1078 skip-vs-add-constant decision for the badge test must be resolved at implementation time.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-21
- **Reason**: Issue too large for single session

### Decomposed Into
- FEAT-1223: Parallel Executor Unit Tests (TestParallelExecution)
- FEAT-1224: Parallel State End-to-End Integration Tests
- FEAT-1225: Parallel Display Badge Test and Constant

## Session Log
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/258256f7-974b-4688-b813-9928466b24ec.jsonl`
- `/ll:refine-issue` - 2026-04-21T09:06:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/392f0d9f-b4a4-4a07-8a5b-2201bc07ec27.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b69582af-c09a-4784-9b2b-61edf9981586.jsonl`
- `/ll:wire-issue` - 2026-04-21T09:01:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/796449d9-ea7c-47ad-b328-f4efe87fa8c5.jsonl`
- `/ll:refine-issue` - 2026-04-21T08:54:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/052df3f9-70bb-4140-baf3-98360b03621c.jsonl`
- `/ll:refine-issue` - 2026-04-21T08:54:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/052df3f9-70bb-4140-baf3-98360b03621c.jsonl`
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eb2a4d4b-681c-4336-8ebc-dacfae9712d8.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f38dfa91-1ac7-4e37-bd21-313943eaeb99.jsonl`
