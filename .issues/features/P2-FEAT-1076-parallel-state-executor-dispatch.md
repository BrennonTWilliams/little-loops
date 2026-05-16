---
discovered_date: "2026-04-12"
discovered_by: issue-size-review

confidence_score: 80
outcome_confidence: 83
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 18
size: Very Large
parent: FEAT-1072
status: deferred
---

# FEAT-1076: Parallel State Executor Dispatch

## Blockers & Folded Criteria

**v1 SHIP-BLOCKERS — MUST land in this PR, not as follow-ups:**

These were deferred issues that have been folded into this issue's acceptance criteria (2026-04-20). Shipping `_execute_parallel_state()` without them is a regression vs. sequential loops — this is the "correctness-complete" bar for v1. See also the Ship Companions section for the companion issues (FEAT-1174, FEAT-1184) that must land in the same release.

- **ENH-1164 — simulation-mode guard**: when `self.action_runner` is a `SimulationActionRunner`, `_execute_parallel_state()` runs items **sequentially** through the simulation runner rather than invoking `ParallelRunner`. No real threads, no worktrees, no subprocesses. Emitted shape identical: `self.captured[state_name] = {"results": [...]}` so `on_yes`/`on_partial`/`on_no` routing is unchanged. Raising `NotImplementedError` is explicitly rejected — `ll-loop simulate` must work on loops containing `parallel:` states.
- **ENH-1165 Option B — Ctrl-C-driven pool shutdown**: `_execute_parallel_state()` wraps `runner.run()` in `try/finally`. On `KeyboardInterrupt` (or any signal-driven exception), it calls `executor.shutdown(wait=False, cancel_futures=True)` on the underlying `ThreadPoolExecutor` before re-raising. Pending (not-yet-started) workers are cancelled immediately.

**Option B does NOT stop in-flight workers mid-state** — they complete their current state before the pool shuts down. For a worker running a 20-minute state, Ctrl-C can take ~20 minutes to actually stop. This is a regression vs. sequential-loop Ctrl-C behavior (which kills via SIGTERM immediately through the subprocess signal handler). Full per-worker cancellation via a shared `threading.Event` checked between state transitions — Option A — remains deferred post-v1 (`.issues/enhancements/P2-ENH-1165-...`). Document the Ctrl-C latency prominently in `docs/generalized-fsm-loop.md` when FEAT-1084 lands.

**Implementer checklist — do NOT merge without each of these present:**

1. [ ] `isinstance(self.action_runner, SimulationActionRunner)` branch at top of `_execute_parallel_state()` with sequential fallback
2. [ ] Sequential fallback produces `self.captured[state_name] = {"results": [...]}` with identical shape to real parallel execution (same `ParallelItemResult`-as-dict entries)
3. [ ] `try/finally` around `runner.run()` with `executor.shutdown(wait=False, cancel_futures=True)` in the exception path
4. [ ] A test in FEAT-1077 asserts that `ll-loop simulate` on a loop containing `parallel:` does not spawn real threads (check via `threading.active_count()` before/after) and does not invoke real sub-loop commands
5. [ ] A test in FEAT-1077 asserts `KeyboardInterrupt` during a parallel run cancels pending futures (count of worker bodies that started < total items)

## Summary

Add `_execute_parallel_state()` to `executor.py` and wire the dispatch at `_execute_state()`. Decide and document the scope lock architecture for parallel states.

## Current Behavior

`executor.py` has no `_execute_parallel_state()` method and `_execute_state()` has no dispatch for `parallel:` state types. A state YAML containing a `parallel:` key silently falls through to the `if state.next:` block, with no concurrent fan-out triggered.

## Expected Behavior

When a state contains `parallel: ...`, `_execute_state()` dispatches to `_execute_parallel_state()`, which fans out sub-loop execution concurrently via `ParallelRunner`, stores per-worker captures in `self.captured[self.current_state]`, and returns a verdict (`done`/`partial`/`failed`) for routing via `_route_parallel()`.

## Use Case

**Who**: An automation engineer building an FSM loop that needs to process multiple items concurrently (e.g., running the same sub-loop against a list of open issues in parallel).

**Context**: The engineer has a list of items in captured context and wants to fan out a named sub-loop across all items concurrently rather than sequentially, with configurable `max_workers`, `fail_mode`, and `context_passthrough`.

**Goal**: Define a `parallel:` state in YAML that triggers concurrent fan-out execution and aggregates worker results under `${captured.<state_name>.results}`.

**Outcome**: All items are processed concurrently; the FSM routes on `on_yes` / `on_partial` / `on_no` based on collective verdict.

## Motivation

This feature:
- **Completes FEAT-1072**: This dispatch wiring is the final integration point connecting the schema (FEAT-1074) and `ParallelRunner` (FEAT-1075) into the live executor.
- **Enables concurrent fan-out**: Reduces wall-clock time from O(n) sequential to O(n/workers) concurrent for multi-item sub-loop patterns.
- **Establishes scope lock architecture**: Documents that `isolation: worktree` handles real conflict risk, keeping `FSMExecutor` clean of lock concerns.

## Parent Issue

Decomposed from FEAT-1072: Add `parallel:` State Type to FSM for Concurrent Sub-Loop Fan-Out

## Proposed Solution

### executor.py changes

**Add `_execute_parallel_state()`** alongside `_execute_sub_loop()` at line 318:

```python
def _execute_parallel_state(self, state: StateConfig) -> str:
    """Fan out sub-loop execution over a list of items concurrently."""
    assert state.parallel is not None
    items = self._interpolate(state.parallel.items).splitlines()
    runner = ParallelRunner()
    result = runner.run(
        items=items,
        loop_name=state.parallel.loop,
        config=state.parallel,
        parent_context=self.captured if state.parallel.context_passthrough else None,
    )
    # Serialize each ParallelItemResult as a dict for downstream interpolation.
    # Order is by item_index (original items order), NOT completion order — the runner
    # guarantees this by writing into pre-allocated slots (see FEAT-1075 "Ordering guarantee").
    self.captured[self.current_state] = {
        "results": [
            {
                "item": r.item,
                "item_index": r.item_index,
                "verdict": r.verdict,
                "terminated_by": r.terminated_by,
                "captures": r.captures,
                "error": r.error,
            }
            for r in result.all_results
        ]
    }
    return result.verdict
```

`ParallelRunner` owns the deep-copy boundary when `context_passthrough` is enabled; the caller may pass `self.captured` by reference here.

**Insert dispatch** at `executor.py:396–402` immediately after the `if state.loop is not None:` block (line 403) and before the `if state.next:` block. Follow the same `try/except (FileNotFoundError, ValueError)` guard pattern:

```python
if state.parallel is not None:
    try:
        verdict = self._execute_parallel_state(state)
        return self._route_parallel(state, verdict)
    except (FileNotFoundError, ValueError) as e:
        ...
```

**Scope lock design decision** — pick one and document in implementation:
- Option A (recommended): Leave scope lock management at the CLI level (`run.py:148`). Worktree isolation handles the real conflict risk. Document that `isolation: worktree` makes per-worker locking unnecessary.
- Option B: Thread `lock_manager` into `FSMExecutor` as an optional constructor arg

**Captured context**: parallel state stores results as `self.captured[self.current_state] = {"results": [<ParallelItemResult-as-dict>, ...]}` — accessible downstream as `${captured.<state_name>.results}`. Each entry has fields `item`, `item_index`, `verdict`, `terminated_by`, `captures`, `error`. Downstream states read `.verdict` to distinguish successes from failures and `.captures` for per-worker output.

**Route method** — add `_route_parallel(state, verdict)` that maps `verdict` → `on_yes` / `on_partial` / `on_no` route keys.

## Implementation Steps

1. Add `_execute_parallel_state(state)` to `FSMExecutor` in `executor.py` alongside `_execute_sub_loop()`
2. Add `_route_parallel(state, verdict)` to map verdict → `on_yes` / `on_partial` / `on_no` route keys
3. Insert `if state.parallel is not None:` dispatch block in `_execute_state()` after the `if state.loop is not None:` block, following the same `try/except (FileNotFoundError, ValueError)` guard pattern
4. Adopt Option A for scope lock (leave at CLI level) and add a comment in `_execute_parallel_state()` documenting why executor-level locking is unnecessary
5. Verify existing `loop:` sequential dispatch is unaffected (run existing FSM tests)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Verify `persistence.py:418` — confirm `captured` dict mutation flows into `PersistentExecutor._save_state()` automatically; no changes to `persistence.py` expected, but run `test_fsm_persistence.py` after implementation
7. Verify interceptor behavior — check where the `_interceptors` loop runs inside `_execute_state()` relative to the `if state.loop:` early-return; if interceptors are skipped for sub-loop states (expected), parallel dispatch is consistent — document this behavior in `_execute_parallel_state()` comments
8. Add comment in `_execute_parallel_state()` noting that `SimulationActionRunner` is bypassed when `ParallelRunner` is invoked (see `cli/loop/testing.py:185`) — simulation mode does not support parallel states
9. Confirm `fsm/__init__.py` — lazy import of `ParallelRunner` inside method body means no `__init__.py` update is required; verify after FEAT-1075 is merged
10. Coordinate `validation.py` updates with FEAT-1074 implementer — two rules required when `StateConfig.parallel` lands: (a) add `has_parallel` flag to the "no transition" guard in `_validate_state_transitions()` at lines 266–277; (b) add `parallel`/`action` and `parallel`/`loop` mutual exclusion to `_validate_state_action()` at lines 217–226. If FEAT-1074 doesn't include these, add them here.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — Add `_execute_parallel_state()`, `_route_parallel()`, insert dispatch at `_execute_state()` after `if state.loop is not None:` block

_Wiring pass 2 added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation.py` — Two rules must be added alongside FEAT-1074 landing: (1) `has_parallel = state.parallel is not None` flag in the "no transition" guard at `_validate_state_transitions()` lines 266–277 so states with only `parallel:` and no routing are caught; (2) `parallel`/`action` and `parallel`/`loop` mutual exclusion in `_validate_state_action()` at lines 217–226, mirroring the existing `loop`/`action` check. Coordinate with FEAT-1074 implementer — these changes are blocked on `StateConfig.parallel` existing.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — Uses `FSMExecutor` transparently; no changes expected but verify scope lock architecture holds
- `scripts/little_loops/fsm/schema.py` — Must expose `StateConfig.parallel` (FEAT-1074 prerequisite)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/persistence.py:343` — `PersistentExecutor` wraps `FSMExecutor` directly; `self.captured[self.current_state] = {"results": ...}` mutation from `_execute_parallel_state()` flows into `_save_state()` at line 418 automatically — verify no changes to `persistence.py` are needed
- `scripts/little_loops/extension.py:188–254` — `wire_extensions()` attaches interceptors to `FSMExecutor._interceptors`; the interceptor loop in `_execute_state()` does not fire for early-return dispatch paths (same behavior as `state.loop` — interceptors are skipped for both sub-loop and parallel dispatch); document this in `_execute_parallel_state()` comments
- `scripts/little_loops/cli/loop/testing.py:185` — `run_simulated_loop()` constructs `FSMExecutor` directly with `SimulationActionRunner`; parallel states will invoke `ParallelRunner`, bypassing the simulation runner — known gap, document in code comments
- `scripts/little_loops/cli/loop/_helpers.py:56–66` — signal handler reaches `FSMExecutor._current_process` to kill subprocesses; `ParallelRunner` worker threads are not reachable via this mechanism — out of scope for this issue, document as a known limitation
- `scripts/little_loops/fsm/__init__.py:86–94` — re-exports `FSMExecutor` and related symbols as the public `fsm` API; `ParallelRunner` is lazy-imported inside `_execute_parallel_state()` to avoid circular imports, so no `__init__.py` update is needed — verify

### Similar Patterns
- `_execute_sub_loop()` in `executor.py` — Parallel dispatch follows same structure; use as implementation template
- `if state.loop is not None:` block — Dispatch pattern to mirror for `if state.parallel is not None:`

### Tests
- New tests in `scripts/tests/test_fsm_executor.py` — add class `TestParallelExecution` following the `TestSubLoopExecution` pattern at line 3473; write child YAML to `tmp_path / ".loops"`, pass `loops_dir=loops_dir` to `FSMExecutor` (no `fsm/` subdirectory exists)
- Existing: `scripts/tests/test_fsm_executor.py` — Verify no regressions in `loop:` dispatch

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_persistence.py` — verify `PersistentExecutor._save_state()` correctly serializes `captured[state_name] = {"results": [...]}` produced by `_execute_parallel_state()` (parallel results must round-trip through persistence without loss)
- `scripts/tests/test_ll_loop_execution.py:95` — `TestEndToEndExecution` exercises `_execute_state()` through `PersistentExecutor.run()`; run as a regression gate after implementing the dispatch insertion
- **`TestParallelExecution` must cover** (mirrors `TestSubLoopExecution` method set at `test_fsm_executor.py:3475–3792`): all-workers-succeed → `on_yes`; mixed results → `on_partial`; all-workers-fail → `on_no`; missing child loop with `on_error` set; missing child loop without `on_error`; `context_passthrough=True` stores results in `self.captured[state_name]`; `max_workers` limiting; `fail_mode: collect` vs `fail_mode: fail_fast`

_Wiring pass 2 added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_commands.py:2845` — imports `FSMExecutor` directly; run as regression gate after dispatch insertion to catch any import-path breakage
- `scripts/tests/test_extension.py` — interceptor wiring tests; verify `before_route`/`after_route` hooks are not accidentally fired for the parallel early-return path (interceptors skip parallel states the same way they skip `loop:` states)
- `scripts/tests/test_interceptor_extension.py` — extension interceptor tests; parallel dispatch skips `_interceptors` loop same as sub-loop; run as regression gate
- `scripts/tests/test_fsm_executor.py::TestRateLimitCircuitIntegration:test_sub_loop_inherits_parent_circuit` (line 5305–5324) — verifies that the `circuit` breaker is propagated from parent executor to child sub-loop workers; `ParallelRunner` (FEAT-1075) must similarly propagate `circuit` to worker child executors — verify this is covered in the `TestParallelExecution` matrix or add a dedicated `test_parallel_state_inherits_parent_circuit` test

### Documentation
- N/A — internal implementation; no public-facing docs changes

_Wiring pass added by `/ll:wire-issue`:_
- `skills/create-loop/loop-types.md:978–1014` — documents `loop:` sub-loop state type; no `parallel:` entry exists; users cannot discover the new state type from this skill (FEAT-1078 scope)
- `skills/create-loop/reference.md:686–713` — documents `loop` field mutual exclusions; `parallel` field and `on_yes`/`on_partial`/`on_no` routing semantics are absent (FEAT-1078 scope)

_Wiring pass 2 added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md:236–312` — schema definition block lists all state fields; `loop:` is absent and `parallel:` will also be absent; `docs/generalized-fsm-loop.md:1397–1414` — execution engine flow section describes only action-based dispatch, not sub-loop or parallel early-return paths (FEAT-1078 scope)
- `docs/guides/LOOPS_GUIDE.md:1865–1914` — "Composable Sub-Loops" section documents only `loop:` fan-out; `parallel:` concurrent fan-out analog is absent; natural extension point for documenting the new state type (FEAT-1078 scope)

### Display Files (Out of Scope — Known Gaps)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/layout.py:118–133` — `_get_state_badge()` checks `state.loop is not None` but has no branch for `state.parallel`; parallel states render with no badge in the TUI diagram — track as a separate display issue
- `scripts/little_loops/cli/loop/info.py:548–576` — `_print_state_overview_table()` Type column falls through to `—` for states with no `action`, `action_type`, `next`, or `loop`; parallel states show no type — track as a separate display issue

### Configuration
- N/A (executor changes require no config key additions)

_Wiring pass 2 added by `/ll:wire-issue`:_
- `config-schema.json:751–774` — `loops.glyphs` object uses `additionalProperties: false`; the six allowed glyph keys do not include `parallel`; when display code gains a `parallel` state badge branch (deferred display issue), a `parallel` key entry must be added here or schema validation will reject user attempts to configure it

## Dependencies

- FEAT-1074 (schema) and FEAT-1075 (ParallelRunner) must be complete

## Known Limitations / Follow-ups

- **Unresolved-context-variable pre-scan does not cover `state.parallel.items`** — `cli/loop/run.py:107-115` pre-scans `state.action` for unresolved `{{ }}` context variables but not `state.parallel.items`. An `items:` field referencing `{{ captured.X.Y }}` that fails to resolve at runtime will split on an empty string or on literal-brace text and fan out zero (or garbage) workers with no early warning. Tracked as **ENH-1173** (`.issues/enhancements/P3-ENH-1173-extend-unresolved-context-variable-pre-scan-to-cover-parallel-items.md`).

- **Interceptors are skipped on the parallel dispatch early-return path** — `FSMExecutor._interceptors` (registered by `extension.py:wire_extensions()`) do not fire around `_execute_parallel_state()`. This is intentional and mirrors the existing `_execute_sub_loop` early-return behavior, but it is a silent behavior change for extension authors who wire interceptors expecting them to fire for every state. Document in `_execute_parallel_state()` docstring AND surface in FEAT-1086 (architecture/contributing docs) so third-party extensions are built with this in mind.

- **Ctrl-C latency** (Option B only): running workers finish their current state before the pool shuts down. For a worker running a long state, Ctrl-C can take minutes to actually stop. Full per-worker cancellation (Option A) is deferred to post-v1.

- **Signal-handler unreachability of worker threads** — `cli/loop/_helpers.py:56-66` signal handler reaches `FSMExecutor._current_process` to kill the active subprocess; `ParallelRunner` worker threads each have their own `FSMExecutor` instance unknown to the parent signal handler. Partially mitigated by Option B pool shutdown above, but a worker's currently-running subprocess survives until it completes or hits its own timeout. Document this in `docs/generalized-fsm-loop.md`. Full fix tracked in deferred **ENH-1165** Option A.

## Scope Note

**This issue folds ENH-1164 and ENH-1165 (Option B).** Both are tracked as separate active issues (`.issues/enhancements/P2-ENH-1164-…`, `.issues/enhancements/P2-ENH-1165-…`) for traceability and to own their tests; their *behavioral* acceptance criteria land here. The acceptance criteria below are split into three explicit code paths — **(a) Simulation**, **(b) Real execution**, **(c) Cancellation** — because folding ENH-1164/1165 introduces two additional code paths that each have their own test matrix. Do not review this issue as a single-path dispatch.

**This issue also relies on the cleanup ownership contract defined in FEAT-1184**: the dispatcher loop in `_execute_parallel_state()` (here) owns all branch ref-modifying git operations under `GitLock`; worker threads from `ParallelRunner` (FEAT-1075) MUST NOT issue `git branch -D`, `git merge`, or any other ref-modifying git command. Re-read FEAT-1184 before implementing to avoid re-introducing the worker-thread branch-op race condition.

## Acceptance Criteria

### (a) Simulation path (folded from ENH-1164)

- When `self.action_runner` is a `SimulationActionRunner`, `_execute_parallel_state()` runs items **sequentially** through the simulation runner — no real threads, no worktrees, no subprocess execution.
- The resulting `self.captured[state_name] = {"results": [...]}` shape is identical to real execution so downstream `on_yes`/`on_partial`/`on_no` routing is unchanged.
- Raising `NotImplementedError` is explicitly rejected; see ENH-1164 §29-33 for rationale.
- **Test**: `ll-loop simulate` on a loop containing `parallel:` does NOT spawn real threads (verified via `threading.active_count()` before/after) and does NOT invoke real sub-loop commands (verified via `SimulationActionRunner` call count or equivalent).

### (b) Real-execution path

- `parallel:` key in a state YAML triggers concurrent sub-loop fan-out via `_execute_parallel_state()`.
- `on_yes` routes when all workers reached terminal `yes`; `on_partial` when mixed; `on_no` when all failed.
- Worker captures accessible as `${captured.<state_name>.results[i]}`.
- `context_passthrough: true` passes parent captured dict to each worker (deep-copied by the runner per FEAT-1075).
- `max_workers` limits concurrency; excess items queue and execute as workers finish.
- `fail_mode: collect` continues all workers even if some fail.
- `fail_mode: fail_fast` cancels remaining on first failure.
- Existing loops using `loop:` (sequential sub-loop delegation) are unaffected.
- Scope lock behavior is documented in code comments.
- **Cleanup ownership (FEAT-1184 contract)**: the dispatcher loop (this issue) owns all branch ref-modifying git operations under `GitLock`; worker threads perform zero ref-modifying git ops. A test asserts this by instrumenting `subprocess.run` / the git helper with `threading.get_ident()` and failing if any ref-modifying op fires off the main thread.

### (c) Cancellation path (folded from ENH-1165 Option B)

- `_execute_parallel_state()` wraps the `runner.run()` call in `try/finally`; on `KeyboardInterrupt` (or any signal-driven exception) it calls `executor.shutdown(wait=False, cancel_futures=True)` on the underlying `ThreadPoolExecutor` before re-raising.
- Pending (not-yet-started) workers are cancelled; running workers finish their current state before exiting. **Ctrl-C latency** (running worker's current-state duration) is a documented v1 limitation (see ENH-1186).
- Full per-worker `threading.Event` cancellation (Option A) is deferred; it remains the open scope of ENH-1165 post-v1.
- **Test**: `KeyboardInterrupt` raised during a parallel run cancels pending futures (count of worker bodies that started `<` total items).

## Tests (owned by this issue)

Moved from FEAT-1077 (2026-04-20). The dispatcher's three explicit code paths — simulation, real-execution, cancellation — each have their own test matrix. Each maps to a path in the split Acceptance Criteria above.

**`scripts/tests/test_fsm_executor.py::TestParallelExecution`** (new class, mirrors `TestSubLoopExecution:3472` pattern; write child YAML to `tmp_path / ".loops"`, pass `loops_dir=loops_dir` to `FSMExecutor`):

- **Simulation path (AC block a, folded ENH-1164):**
  - `test_parallel_state_simulation_runs_sequentially` — `SimulationActionRunner` in use; assert `threading.active_count()` unchanged; assert sequential item order in the capture trace
  - `test_parallel_state_simulation_captures_shape_matches_real` — identical `{"results": [...]}` shape to the real-execution path
  - `test_parallel_state_simulation_does_not_raise_notimplementederror` — regression gate against the rejected `NotImplementedError` approach
- **Real-execution path (AC block b):**
  - `test_parallel_state_dispatches` — state with `parallel:` config calls `_execute_parallel_state()`
  - `test_parallel_state_captures_merged` — captures stored at `self.captured[state_name]["results"]`
  - `test_parallel_state_routes_on_yes`, `_on_partial`, `_on_no` — route correctness for each verdict
  - `test_parallel_state_branch_ops_never_on_worker_thread` — cleanup-ownership contract (FEAT-1184): wrap the git helper / `subprocess.run` with a shim that records `threading.get_ident()`; assert any git ref-modification fires on the main thread only
- **Cancellation path (AC block c, folded ENH-1165 Option B):**
  - `test_parallel_state_keyboardinterrupt_cancels_pending_futures` — raise `KeyboardInterrupt` mid-run; assert worker-bodies-started counter < total items
  - `test_parallel_state_keyboardinterrupt_propagates` — assert the exception re-raises after `executor.shutdown(...)` is called

Integration/end-to-end loop tests (`test_parallel_state_end_to_end` with `on_yes`/`on_partial`/`on_no` variants) remain with FEAT-1077.

## Implementation Notes

- **`_execute_state()` dispatch insertion point**: `executor.py:396–402`. Insert `if state.parallel is not None:` immediately after the `if state.loop is not None:` block (line 402, before the blank comment line `# Handle unconditional transition`) and before `if state.next:` at line 405.
- **Scope locking architecture**: `LockManager` is instantiated in `cli/loop/run.py:145` and scope lock acquisition happens at `run.py:148` — before `FSMExecutor` is ever constructed (via `PersistentExecutor` at `run.py:217`). `FSMExecutor` has zero awareness of `LockManager`. Option A (leave at CLI) is simplest and sufficient.
- `cli/loop/run.py` — No changes expected; uses `FSMExecutor` via `PersistentExecutor` transparently.
- **Implementation Step 2 (`_route_parallel()`) is eliminated**: Use `self._route(state, result.verdict, ctx)` directly inside `_execute_parallel_state()`. `_route()` at `executor.py:713` already maps `"yes"` → `on_yes`, `"partial"` → `on_partial`, `"no"` → `on_no` via shorthand routing at lines 747–753. No separate routing method is needed.
- **`interpolate()` import**: The standalone `interpolate` function is already imported at the top of `executor.py`. No new import needed inside `_execute_parallel_state()` — only the lazy `from little_loops.fsm.parallel_runner import ParallelRunner` line inside the method body.
- **Effective implementation steps** (supersedes Step 2 in Implementation Steps above):
  1. Add `_execute_parallel_state(self, state: StateConfig, ctx: InterpolationContext) -> str | None` alongside `_execute_sub_loop()` at line 318
  2. Insert `if state.parallel is not None:` dispatch block in `_execute_state()` after line 402, before `if state.next:` at line 405 — pass `ctx` to `_execute_parallel_state(state, ctx)`
  3. Verify `persistence.py:418` — no changes expected
  4. Document known limitations in `_execute_parallel_state()` comments (interceptors skipped, simulation bypassed, signal handler gap)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Verdict values**: Issue body says `done/partial/failed` but FEAT-1075 spec defines `ParallelResult.verdict: str` with values `"yes"` / `"partial"` / `"no"`. Implementation must use FEAT-1075's values. The `_route_parallel()` method maps `"yes"` → `on_yes`, `"partial"` → `on_partial`, `"no"` → `on_no`.
- **`_route_parallel()` simplification**: The existing `_route()` method at `executor.py:713` already handles `on_yes`/`on_partial`/`on_no` for these exact verdict strings. Consider calling `self._route(state, verdict, ctx)` directly instead of adding a separate `_route_parallel()`. If a dedicated method is added for clarity, it can simply delegate to `_route()` or inline the same three-case check.
- **`_execute_parallel_state()` signature**: `_execute_sub_loop()` at `executor.py:318` takes `(self, state: StateConfig, ctx: InterpolationContext) -> str | None`. Mirror this signature for `_execute_parallel_state()` so routing can call `interpolate()` with `ctx`.
- **Lazy import pattern**: `_execute_sub_loop()` imports `resolve_loop_path` and `load_and_validate` inside the method body to avoid circular imports. Apply the same pattern for `ParallelRunner` — import lazily from `little_loops.fsm.concurrency` (where `LockManager` lives; `ParallelRunner` will be added there by FEAT-1075).
- **Test location confirmed**: `scripts/tests/` (flat, no `fsm/` subdirectory). Model tests after `TestSubLoopExecution` at `scripts/tests/test_fsm_executor.py:3473`. FEAT-1077 may target the same file with a `TestParallelExecution` class.
- **Prerequisite status**: Both FEAT-1074 (schema — `StateConfig.parallel` field absent from `schema.py`) and FEAT-1075 (`ParallelRunner` class absent from codebase) are confirmed **Open**. Do not begin implementation until both are merged.
- **`self._interpolate()` does not exist — use `interpolate(string, ctx)` instead**: The `Proposed Solution` code block calls `self._interpolate(state.parallel.items)`, but `FSMExecutor` has no such method. The executor uses a standalone `interpolate()` function (imported at the top of `executor.py`) called as `interpolate(string, ctx)`. The correct items line is `items = interpolate(state.parallel.items, ctx).splitlines()`. This also means `_execute_parallel_state()` **must accept `ctx: InterpolationContext`** as a second parameter — exactly mirroring `_execute_sub_loop(self, state: StateConfig, ctx: InterpolationContext) -> str | None`.
- **Routing decision resolved — drop `_route_parallel()`, call `_route()` directly**: `_route()` at `executor.py:713` already handles `"yes"` → `on_yes`, `"partial"` → `on_partial`, `"no"` → `on_no` via shorthand routing (lines 747–753). `ParallelResult.verdict` is already one of these three strings. Call `return self._route(state, result.verdict, ctx)` at the end of `_execute_parallel_state()`. This makes Implementation Step 2 ("Add `_route_parallel()`") unnecessary — skip it.
- **Corrected `_execute_parallel_state()` code** (supersedes Proposed Solution code block):
  ```python
  def _execute_parallel_state(self, state: StateConfig, ctx: InterpolationContext) -> str | None:
      """Fan out sub-loop execution over a list of items concurrently.
      
      Note: interceptors (_interceptors loop) are skipped for this early-return path,
      consistent with _execute_sub_loop() behavior.
      Note: SimulationActionRunner is bypassed — simulation mode does not support parallel states.
      Note: isolation: worktree handles real conflict risk; FSMExecutor needs no scope lock awareness.
      """
      from little_loops.fsm.parallel_runner import ParallelRunner
      assert state.parallel is not None
      items = interpolate(state.parallel.items, ctx).splitlines()
      runner = ParallelRunner()
      result = runner.run(
          items=items,
          loop_name=state.parallel.loop,
          config=state.parallel,
          parent_context=self.captured if state.parallel.context_passthrough else None,
      )
      self.captured[self.current_state] = {"results": result.all_captures}
      return self._route(state, result.verdict, ctx)
  ```
- **Corrected dispatch block** in `_execute_state()` (insertion point: after line 402, before `if state.next:` at line 405):
  ```python
  if state.parallel is not None:
      try:
          return self._execute_parallel_state(state, ctx)
      except (FileNotFoundError, ValueError) as e:
          if state.on_error:
              return interpolate(state.on_error, ctx)
          raise
  ```

_Re-refined 2026-04-20 (/ll:refine-issue pass 3) — codebase line numbers re-verified against HEAD:_

- **Stale line numbers across the issue body** (verified 2026-04-20; all references to pre-FEAT-1074 revisions of executor.py/persistence.py are off). Use these current numbers when implementing:
  - `_execute_sub_loop()` — defined at `executor.py:366` (issue says 318)
  - `_execute_state()` dispatch — `if state.loop is not None:` block spans **lines 445–451**; blank line at 452; `# Handle unconditional transition` comment at 453; `if state.next:` at **line 454** (issue says "after 402, before 405"). **Correct insertion point: after line 451, before line 453** (the blank line 452 sits between).
  - `_route()` — defined at `executor.py:786` (issue says 713)
  - `_route()` shorthand routing block — **lines 820–829** (issue says 747–753). Handles `"yes"` → `on_yes`, `"no"` → `on_no`, `"error"` → `on_error`, `"partial"` → `on_partial`, `"blocked"` → `on_blocked`. Note: the `state.route:` table branch at lines 809–817 runs first; if a full route table is present, shorthand is never reached.
  - `persistence.py:_save_state()` — defined at **line 436** (issue says 418). It builds `LoopState` with `captured=self._executor.captured` at line 448. `LoopState.to_dict()` at lines 114–138 serializes `captured` verbatim as `data["captured"] = self.captured` at line 120. JSON round-trip of `{"results": [...]}` with JSON-primitive entries is fully supported; `from_dict()` at line 171 restores via `data.get("captured", {})` without coercion. **No persistence.py changes required**, verified.
  - `_build_context()` — `executor.py:892–908`. `_execute_state()` builds `ctx = self._build_context()` at **line 442** before any dispatch. Read this to confirm what `ctx` carries at parallel-dispatch time.

- **`_execute_sub_loop()` does NOT call `self._route()`** — confirmed at `executor.py:419–430`. It uses direct `interpolate(state.on_yes, ctx)` / `interpolate(state.on_no, ctx)` / `interpolate(state.on_error, ctx)` calls because the verdict is structurally derived from `child_result.terminated_by` + `child_result.final_state` (strings like `"terminal"` / `"error"` / `"max_iterations"`), not from a `"yes"`/`"no"`/`"partial"` evaluator verdict. **Parallel dispatch is different**: `ParallelResult.verdict` is already `"yes"` / `"partial"` / `"no"` (per FEAT-1075), so calling `self._route(state, result.verdict, ctx)` is correct and idiomatic here even though sub-loop does not. The prior refinement note recommending `_route()` remains correct — this finding explains why the two dispatchers legitimately diverge in routing style.

- **`SimulationActionRunner` class location** — defined at `scripts/little_loops/fsm/runners.py:174`, not `cli/loop/testing.py:185`. The cli path is where it's *constructed* at simulate-time (which is what the wiring section correctly documents); the class itself lives in `fsm/runners.py`. Use `from little_loops.fsm.runners import SimulationActionRunner` for the `isinstance()` guard at the top of `_execute_parallel_state()`.

- **`InterpolationContext` fields** (`fsm/interpolation.py:37`): dataclass with `context`, `captured`, `prev`, `result`, `state_name`, `iteration`, `loop_name`, `started_at`, `elapsed_ms`. This is what `ctx` carries into `_execute_parallel_state(state, ctx)`.

- **`FSMExecutor.__init__` signature** (`executor.py:120–205`) — takes `fsm`, `event_callback=None`, `action_runner=None`, `signal_detector=None`, `handoff_handler=None`, `loops_dir=None`, `circuit=None`. `self.action_runner` is set at line 143 via `action_runner or DefaultActionRunner()`. When workers construct child executors for parallel fan-out, the `ParallelRunner` (FEAT-1075) is responsible for propagating `action_runner`, `loops_dir`, `circuit`; `_execute_parallel_state()` itself just passes `state.parallel` config and does not construct executors directly.

- **`self.current_state` is safe to read** at parallel-dispatch time — set in constructor at `executor.py:150` (`self.current_state = fsm.initial`), updated at lines 344–345 at end of each iteration (`self.current_state = resolved_next`), and in maintain-mode at line 271. By the time `_execute_state()` runs, `self.current_state` is the name of the state being executed. `self.captured[self.current_state] = {"results": [...]}` is safe.

- **Dispatch-block prerequisite files — current HEAD status** (verified 2026-04-20):
  - `StateConfig.parallel` field — **absent** from `schema.py:179–255`. `StateConfig` has `loop: str | None = None` at line 251 but no `parallel` field. FEAT-1074 has not landed; do not start implementation before it merges.
  - `ParallelRunner` class — **absent** from the codebase (no `class ParallelRunner` anywhere in `scripts/`). Module `fsm/parallel_runner.py` does not exist. `fsm/concurrency.py` exists and hosts `LockManager` / `ScopeLock` but not `ParallelRunner`. FEAT-1075 has not landed.

- **Test patterns needing to be invented (no precedent in repo)** — call out in test-writing plan so implementer doesn't waste time searching for an existing shim:
  - **`threading.active_count()` assertion pattern** for "simulation path spawns no real threads": zero uses in `scripts/tests/`. Closest analogue is `MockActionRunner().calls == []` from `test_fsm_executor.py:3876–3896` (`test_sub_loop_without_action_runs_child`). Model the simulation test on that pattern AND add a `threading.active_count()` before/after delta check.
  - **`threading.get_ident()` shim for "branch ops never on worker thread"** (FEAT-1184 contract): zero uses of `threading.get_ident`, `thread_ident`, or any worker-thread-id recording pattern in `scripts/tests/`. This is a new test-infra pattern — write a `subprocess.run` wrapper (patched via `patch("little_loops.fsm.executor.subprocess.run", ...)`, mirroring the existing patch-path convention at `test_fsm_executor.py:1790` and `test_ll_loop_state.py:382–388`) that records `threading.get_ident()` on each call. Main-thread id is captured at test start; assert any git ref-modifying invocation's recorded ident equals the main-thread id.
  - **`KeyboardInterrupt` mid-executor patterns** exist elsewhere (`test_orchestrator.py:990` uses `patch.object(orchestrator, "_setup_signal_handlers", side_effect=KeyboardInterrupt)`; `test_sprint.py:716` uses `monkeypatch.setattr` to replace a collaborator with a raising function). Use the `patch.object(..., side_effect=KeyboardInterrupt)` shape for the cancellation test — point it at `ParallelRunner.run` (the lazy-imported target) so the interrupt fires inside `runner.run()` and the surrounding `try/finally` in `_execute_parallel_state()` is exercised.

- **`_execute_sub_loop()` lazy-import exact lines** (for the `_execute_parallel_state()` docstring template): `from little_loops.cli.loop._helpers import resolve_loop_path` and `from little_loops.fsm.validation import load_and_validate` at `executor.py:376–377`. The parallel equivalent is `from little_loops.fsm.parallel_runner import ParallelRunner` (FEAT-1075's module path) plus `from little_loops.fsm.runners import SimulationActionRunner` for the isinstance guard.

- **`_route()` call shape** — live example at `executor.py:535`: `next_state = self._route(state, verdict, ctx)`. This is the only production call site; all other verdict→state routing in the codebase flows through `_route()` at this line. `_execute_parallel_state()` becomes the second production call site.

_Re-verified 2026-04-20 (/ll:refine-issue pass 4) — drift found vs. pass 3; correct these when implementing:_

- **`TestSubLoopExecution` moved**: now at `scripts/tests/test_fsm_executor.py:3634` (pass 3 said `:3473`). Class spans lines **3634–3956** (ends just before `class TestRouteContext` at 3957). Model `TestParallelExecution` after this class at its current location.
- **`validation.py` — function name correction**: the "no transition" guard described above lives in `_validate_state_routing()`, **not** `_validate_state_transitions()`. The lines are 266–278 (pass 3 said 266–277; off by one on the end). `has_loop` flag is set at line 269. Coordinate the `has_parallel` addition with this correct function name.
- **`config-schema.json` glyphs key range**: `"glyphs"` object spans lines **760–772** (pass 3 said 751–774, which was actually the outer `loops` object range). The outer `loops` object opens at 751 and closes at 774; `additionalProperties: false` on the inner `glyphs` object is at line 771. When the deferred `parallel` badge key is added, insert it inside the 760–772 block.
- **`skills/create-loop/loop-types.md` section shift**: "Sub-Loop Composition" section now starts at line **985** (pass 3 said 978) and runs to line **1019** (pass 3 said 1014). Lines 978–982 are still inside the prior example's YAML fence. FEAT-1078 should target 985–1019.
- **Re-verified clean (no drift)**: executor.py line refs (`_execute_sub_loop` at 366, `if state.loop` block 445–454, `_route` at 786, shorthand 820–829, `_build_context` 892–908 called at 442), persistence.py line refs (`_save_state` at 436, `captured=...` at 448, `LoopState.to_dict` 114–138), cli/loop file ranges (`layout.py:118–133`, `info.py:548–576`, `_helpers.py:56–66`), `validation.py` mutual exclusion at 217–226, docs refs (`docs/generalized-fsm-loop.md:236–312` and `:1397–1414`, `LOOPS_GUIDE.md:1865–1914`, `skills/create-loop/reference.md:686–713`), `test_sub_loop_inherits_parent_circuit` at 5305–5324, `SimulationActionRunner` at `fsm/runners.py:174`.
- **Prerequisite status re-confirmed**: `StateConfig.parallel` still absent from `schema.py`; `scripts/little_loops/fsm/parallel_runner.py` does not exist; no `class ParallelRunner` anywhere in the codebase. FEAT-1074 and FEAT-1075 remain unmerged — do not start implementation yet.

## Impact

- **Priority**: P2 — Core dispatch wiring for FEAT-1072; blocked by FEAT-1074 and FEAT-1075 completing first
- **Effort**: Small — Adds 2 new methods and 1 dispatch block; mirrors the existing `_execute_sub_loop()` pattern exactly
- **Risk**: Low — New code path only; existing `loop:` dispatch block is untouched; scope lock stays at CLI level
- **Breaking Change**: No

## Ship Companions (must land together)

The following issues were originally filed as P3 "known limitations" of this dispatch but are now **P2 blockers that must ship in the same release as FEAT-1076**. Shipping `_execute_parallel_state()` without them would leave users with a broken dry-run mode and uncancellable worker threads — both regressions vs. the sequential loop behavior they replace.

- **ENH-1164** (folded into this issue's acceptance criteria 2026-04-20) — Simulation guard at the top of `_execute_parallel_state()`. Without this, `ll-loop simulate` on any loop with a `parallel:` state runs real concurrent sub-loops against live issue files.
- **ENH-1165 Option B** (folded into this issue's acceptance criteria 2026-04-20) — Wrap `runner.run()` in `try/finally` and call `executor.shutdown(wait=False, cancel_futures=True)` on `KeyboardInterrupt`. Option A (full per-worker cancellation via `threading.Event`) remains deferred as a follow-up.
- **FEAT-1174** (promoted P3 → P2 on 2026-04-20) — Per-worker checkpointing and resume. v1 parallel must not regress sequential-loop checkpoint guarantees (SIGKILL mid-fan-out currently re-runs all workers).
- **FEAT-1184** (new P2, split from ENH-1175 on 2026-04-20) — Worker side-effect cleanup contract: failed worktree-mode branches deleted; thread-mode write warning documented; always-one-entry-per-item result guarantee.

Together these define "v1 parallel ship" as a correctness-complete unit. The two folded ENHs are ~20 lines combined inside `_execute_parallel_state()`; FEAT-1174 and FEAT-1184 are their own issues.

### Follow-up issues (not blockers)

Tracked for post-v1; do not gate this issue on them:
- **ENH-1165 Option A** — Full per-worker cancellation via shared `threading.Event` checked between worker state transitions (tracked in `.issues/enhancements/P2-ENH-1165-...`; Option A scope remains post-v1)
- **ENH-1175** — Worker retry policy (`retry_on_failure`, `retry_backoff_seconds`) — cleanup half split out to FEAT-1184; retry remains P3
- **ENH-1176** — Parallel state resource limits (max items, cumulative timeout, worktree warnings)
- **ENH-1177** — Worker-tagged observability (per-worker event tags in logs)
- **ENH-1178** — Thread-mode isolation safety detection (validation heuristic for unsafe sub-loops)

## Labels

`fsm`, `parallel`, `executor`

---

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-04-20 (supersedes 2026-04-12 entry)_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 83/100 → HIGH CONFIDENCE

### Concerns
- **Blocking dependencies not satisfied**: FEAT-1074 (`StateConfig.parallel`) and FEAT-1075 (`ParallelRunner`) are both confirmed absent from codebase (re-verified 2026-04-20). Do not start implementation until both merge.
- **FEAT-1184 must be read before implementing**: The cleanup ownership contract (worker threads must not issue ref-modifying git ops) governs the FEAT-1184 acceptance criterion test. Re-read that issue before writing the `threading.get_ident()` shim.
- **Novel test infrastructure**: The `threading.get_ident()` shim (branch-ops-on-main-thread test) and `KeyboardInterrupt` mid-executor pattern are both new to this test suite — no existing pattern to copy. Budget extra time for writing these test helpers.

## Session Log
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/12e33204-56d1-4038-8776-e8d9f2442372.jsonl`
- `/ll:refine-issue` - 2026-04-21T02:01:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1dc90cc-dac3-4e0d-a30f-b9e27f7e7775.jsonl`
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6cfaa5a5-e8e0-47d0-9b89-97fd288b03e9.jsonl`
- `/ll:wire-issue` - 2026-04-21T01:55:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/58b40d30-15bb-4829-b285-cf0821b85a5d.jsonl`
- `/ll:refine-issue` - 2026-04-21T01:48:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c9b58d3-a24a-4a89-ae5d-ef6671209818.jsonl`
- `/ll:refine-issue` - 2026-04-12T22:06:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d78494ba-e368-4d92-ac07-474ca60ddbb1.jsonl`
- `/ll:wire-issue` - 2026-04-12T22:00:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bbab3ea7-aba1-4f99-878c-4df082545c74.jsonl`
- `/ll:refine-issue` - 2026-04-12T21:53:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b6227012-241e-4253-adf1-d540b03b8c94.jsonl`
- `/ll:format-issue` - 2026-04-12T21:50:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e24121c8-614a-47dc-b39d-f7ef139d0a8c.jsonl`
- `/ll:issue-size-review` - 2026-04-12T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8e4e49c-4e79-4270-9839-915fa38b03f2.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d6467f5-0702-4f04-ae61-18783596ccff.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2
