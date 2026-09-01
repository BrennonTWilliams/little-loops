---
id: BUG-3375
type: BUG
title: autodev cascades Errno 2 into clean terminal exit and silently abandons queue
  when worktree vanishes
priority: P2
status: open
discovered_by: claude-code-review
discovered_date: '2026-09-01'
relates_to:
- BUG-3373
- ENH-3374
confidence_score: 90
outcome_confidence: 64
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 10
---

# BUG-3375: autodev cascades Errno 2 into clean terminal exit and silently abandons queue when worktree vanishes

## Summary

When the shared worktree a sub-loop is running in disappears mid-run, the
FSM has no notion of "my working directory is gone": every subsequent shell
action fails with `[Errno 2] No such file or directory` at `Popen`
(`cwd=worktree`), each failure is routed through the loop's ordinary
`on_error` edges, and the loop walks — erroring state by erroring state —
to a *clean* terminal exit. In the BUG-3373 incident, `refine-to-ready-issue`
and then `autodev` cascaded ~12 such errors in under a second, autodev
exited via its normal terminal state, the remaining queued issue (ENH-1722)
was never dequeued, and the run's only verdict was a generic
`incomplete-abandoned` — nothing surfaced "the worktree vanished" as the
cause.

## Current Behavior

From `.loops/.history/2026-09-01T031623-sprint-refine-and-implement/events.jsonl`
(`03:57:14.937`–`03:57:15.369`): `check_decision_mid_refine`,
`check_wire_done`, `normalize_structure`, `check_verify_verdict`, … then
autodev's `skip_inflight`, `dequeue_next`, `finalize_done` each raise
`action_error` `[Errno 2] No such file or directory: PosixPath('...')`,
each routes onward via `on_error`, and both loops reach `loop_complete`
normally. The operator-facing result is an `incomplete-abandoned` verdict
indistinguishable from an ordinary partial drain; the abandoned issue is
reported only as a count.

## Expected Behavior

A vanished working directory is an unrecoverable infrastructure failure,
not a per-state error to be routed around. When an action fails because the
executor's `working_dir` no longer exists, the executor should:

1. detect it (a `FileNotFoundError` from `Popen` whose `cwd` no longer
   exists, confirmed by an explicit `working_dir` existence check),
2. abort the loop immediately with a distinct infrastructure-failure
   terminal (analogous to the existing infra-retry classification), rather
   than dispatching further states that can only fail the same way, and
3. surface the cause explicitly in events and the finalize verdict (e.g.
   `verdict=infra-worktree-vanished`, naming the missing path), so the
   operator sees "worktree deleted mid-run", not a generic abandonment.

## Motivation

The silent-clean-exit behavior is what turned the BUG-3373 deletion into an
invisible batch truncation: one issue killed mid-refine, one abandoned
untouched, and a verdict that reads like a routine timeout. Whatever the
upstream deleter turns out to be (BUG-3373) and however cleanup is hardened
(ENH-3374), the executor should fail loudly and immediately when the ground
disappears from under it — both for operators and so future incidents are
diagnosable from the verdict instead of a full events.jsonl replay.

## Proposed Solution

In `scripts/little_loops/fsm/executor.py`:

1. **Primary detector — pre-dispatch existence check in `run()`'s main
   loop.** Immediately before each state dispatch (next to the existing
   `_check_host_guard` call, `executor.py:744`), if `self.working_dir` is
   set and `Path(self.working_dir).exists()` is `False`, short-circuit to
   `self._finish("workdir_vanished", error=...)`. This is one `stat` per
   state and covers **every** action type. It must be the primary detector
   because the Popen-site approach alone cannot work: `DefaultActionRunner`'s
   prompt-mode branch (`runners.py:232-272`) wraps `run_claude_command` in a
   bare `except Exception` and returns `ActionResult(exit_code=1,
   stderr="Action failed: ...")`, so a vanished cwd under a `/ll:*` prompt
   state never raises out to the executor — it silently routes via
   `on_failure`/`on_error`. Prompt states are the majority in the affected
   loops, so instrumenting only `_run_subprocess`/the shell branch would
   leave the cascade intact.
1b. *(Optional, secondary)* At the two raising launch sites
   (`FSMExecutor._run_subprocess`, `executor.py:2559`; shell branch,
   `runners.py:298`), catch `FileNotFoundError` where
   `exc.filename == str(working_dir)` and set the same pending flag so the
   abort fires before the current state's `on_error` route rather than at
   the next dispatch. Skip this if it grows the change surface; the
   pre-dispatch check alone satisfies the "at most one further dispatch"
   test criterion in step 4.
2. On that classification, stop routing via the state's `on_error` edge:
   terminate the loop with a distinct failure terminal, emitting a new
   event (e.g. `workdir_vanished`) carrying the missing path and current
   state. Follow the established event-registration procedure
   (CONTRIBUTING.md § "Event Schema Maintenance": EVENT-SCHEMA.md →
   `SCHEMA_DEFINITIONS` in `generate_schemas.py` → regenerate → commit
   `.json` → `DESVariant` in `observability/schema.py`; update the
   `test_generate_schemas.py` count literals and
   `test_des_schema.py`/`test_des_audit.py` expectations).
3. Let parent sub-loops observe the child's distinct terminal
   (`terminated_by`/verdict plumbing already read by
   `auto-refine-and-implement`'s `delegate_failed` state) so the sprint
   verdict names the real cause. **No special parent propagation.** In the
   incident the parent (`sprint-refine-and-implement`) ran from the project
   root, whose cwd was intact; only the sub-loops' cwd vanished. The
   existing catch-all else-branch in `_execute_sub_loop`
   (`executor.py:1191-1196`) routing unknown `terminated_by` values to
   `on_no` is the correct behaviour for that case. When a parent *shares*
   the vanished dir, its own pre-dispatch check (step 1) aborts it at the
   next dispatch. Add `workdir_vanished` to that else-branch's comment list.
4. Tests in `scripts/tests/test_fsm_executor.py`: delete the executor's
   working dir mid-run (after the first state) and assert the loop
   terminates with the new failure terminal after at most one further
   dispatch attempt, with the new event emitted — instead of walking its
   remaining states.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- **Correction**: `_run_subprocess_direct` (named in step 1 above) does not exist anywhere in the repository — confirmed by a repo-wide, unfiltered grep with zero hits outside this issue file. The two actual subprocess-launch sites needing the fix are `FSMExecutor._run_subprocess` (`executor.py:2543`, Popen at `2559-2566`) for `mcp_tool` actions, and `DefaultActionRunner.run()`'s shell branch (`runners.py:117`, Popen at `298-306`) for ordinary shell actions — both need equivalent FileNotFoundError/vanished-cwd handling. See Integration Map and Program Design below for the full call path and the existing abort-pattern this should follow.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/logs.py::_derive_loop_outcome()` (lines 1968-1987) — add an explicit branch mapping `workdir_vanished` to `"error"` (decided: an infrastructure loss is not a loop-logic failure and must not inflate the `"failed"` bucket in fleet rollups; `"error"` is the existing bucket for non-loop-logic termination and needs no new consumer wiring); without it, the run falls through to the `final_state` keyword-substring fallback and is misclassified as `"converged"` in `ll-loop history`/`ll-logs loop-fleet` rollups
- Add a Popen-raises-`FileNotFoundError` test to `scripts/tests/test_fsm_runners.py::TestDefaultActionRunnerShellPath` for the `runners.py` shell-branch site (no such test exists there today)
- Bump the four `== 58` count literals in `scripts/tests/test_generate_schemas.py` (lines 21, 114, 121, 250) to `59`
- Add a `workdir_vanished` row to `docs/guides/LOOPS_GUIDE.md`'s `terminated_by` exit-reasons table (lines 907-921)
- Regenerate `docs/reference/schemas/workdir_vanished.json` via `ll-generate-schemas`. `docs/observability/des-audit.md` is **hand-maintained** despite its "DO NOT EDIT - generated" header (verified 2026-09-01: `ll-verify-des-audit` / `cli/verify_des_audit.py` is audit-only with no write flag, and no other writer exists in the repo) — add the `workdir_vanished` row by hand and bump "Total variants: 83" to 84

## Integration Map

### Codebase Research Findings

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_run_subprocess` (Popen at `2559-2566`) and `_run_action_or_route` (`3344-3372`) need FileNotFoundError/vanished-cwd detection and a new abort path, analogous to `_check_host_guard`/`_check_cost_ceiling` (`3527-3601`, `3603-3683`) and the `run()` main-loop checks at lines `744-834`
  > ⚠ Superseded — Proposed Solution step 1's `_run_subprocess_direct` does not exist in the repo; the actual site is `_run_subprocess` above (see § Codebase Research Findings under Proposed Solution)
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()` shell branch (Popen at `298-306`) may get the optional secondary detection; note its prompt-mode branch (`232-272`) converts **any** launch failure into `ActionResult(exit_code=1)` and never raises, which is why the pre-dispatch check in `run()` is the required primary detector rather than Popen-site catching
- `scripts/little_loops/fsm/types.py` — `ExecutionResult.terminated_by` docstring (lines 35-41) enumerates existing abort kinds; add the new value there
- `scripts/little_loops/generate_schemas.py` — `SCHEMA_DEFINITIONS`; register the new event following the `"stall_detected"` entry (lines 383-395) as the pattern
- `scripts/little_loops/observability/schema.py` — new `DESVariant` subclass following `StallDetectedVariant`/`HostPressureAbortVariant` (lines 207-211, 406-410), registered in the `DES_VARIANTS` tuple

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/logs.py` — `_derive_loop_outcome()` (lines 1968-1987) is a closed if/elif chain (`max_steps`/`max_iterations_reached` → `"max-steps"`, `cycle_detected` → `"stalled"`, `interrupted`/`handoff`/`timeout`/`user_stopped` → `"interrupted"`, `system_signal` → `"signal"`) with no branch for the new value; without one, `workdir_vanished` falls through to the `final_state` keyword-substring fallback and is silently misclassified as `"converged"` in `ll-loop history`/`ll-logs loop-fleet` rollups unless the landing state's name happens to contain `fail`/`error`/`abort` [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `delegate_failed` state (lines 342-379) already reads `${captured.delegate.terminated_by}` in a `case` statement; its `*` branch currently folds all non-`terminal` `terminated_by` values into `recheck_set` — a new abort kind falls into this existing catch-all unless the case list is deliberately extended
- `scripts/little_loops/fsm/executor.py::_execute_sub_loop` (lines 914-1196) — captures `child_result.terminated_by`/`failure_terminal` for any parent loop observing a sub-loop's outcome (lines 1147-1196)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (lines 1036-1041) — `case "${captured.confidence_check.failure_terminal?}:${captured.confidence_check.terminated_by?}" in True:*|*:error|*:timeout|*:max_steps)` — the `True:*` arm already catches any `failure_terminal=True` terminal, so a `workdir_vanished` classification is caught automatically here with no code change; this is a second sub-loop-delegation consumer beyond `auto-refine-and-implement.yaml`'s `delegate_failed`, and is one of the loops the BUG-3373/BUG-3375 incident itself ran (`sprint-refine-and-implement` → `refine-to-ready-issue`) [Agent 1/2 finding]
- `scripts/little_loops/fsm/persistence.py::map_final_status()` (lines 132-168) — canonical `(terminated_by, failure_terminal)` → persisted `LoopState.status` mapper; its default fallback already returns `"failed"` for any unrecognized `terminated_by`, so `workdir_vanished` is auto-covered with no code change [Agent 1/2 finding]
- `scripts/little_loops/cli/loop/_helpers.py` — `EXIT_CODES` dict (lines 69-82) and `_is_success()` (1917-1920); since the new terminal sets `failure_terminal=True`, the exit-code path is auto-covered via `FAILURE_TERMINAL_EXIT_CODE` (checked before `EXIT_CODES` is consulted) — no change needed [Agent 2 finding]
- `scripts/little_loops/cli/loop/info.py`, `scripts/little_loops/cli/loop/audit.py`, `scripts/little_loops/cli/loop/testing.py` — all pass `terminated_by` through verbatim (f-string/dict field); display correctly for any new string value with no change needed [Agent 1/2 finding]
- `scripts/little_loops/testing.py` — imports `ExecutionResult, FSMExecutor`; wraps `FSMExecutor` in a `PersistentExecutor`-style class whose `.run()`/`.resume()` return `ExecutionResult` [Agent 1 finding]
- `scripts/little_loops/extension.py` — imports `FSMExecutor, RouteContext, RouteDecision`; type-annotates executor fields [Agent 1 finding]
- `scripts/little_loops/cli/loop/lifecycle.py` — indirect consumer via `persistence.py`'s `map_final_status` (instantiates `PersistentExecutor`, line 728) [Agent 1 finding]
- `scripts/little_loops/history_reader.py::_WASTED_RUN_PREDICATE` (lines 1011-1017) — SQL `IN (...)` list with an `OR lr.failure_terminal = 1` arm auto-covers the new terminal for `waste_attribution()` token-waste rollups, no change needed [Agent 2 finding]
- `scripts/little_loops/parallel/worker_pool.py`, `scripts/little_loops/learning_tests/gate.py`, `scripts/little_loops/cli/queue.py` — branch on the `FAILURE_TERMINAL_EXIT_CODE` (`=2`) of a `ll-loop run <subloop>` subprocess, not on the `terminated_by` string — a workdir-vanished sub-loop surfaces as `"blocked"`/`"terminal failure"`, the same bucket as any other `failure: true` terminal; no change needed but these are affected consumers [Agent 2 finding]

### Conventions in Force
- Every distinct infra-abort kind in this codebase follows a `_pending_*` flag set deep in the call stack, checked in `run()`'s main loop, short-circuiting to `self._finish(<new terminated_by>, error=...)` — evidence: `_check_host_guard`/`HOST_PRESSURE_ABORT_EVENT` (`executor.py:3527-3601`, `744-748`), `_check_cost_ceiling`/cost-ceiling event (`3603-3683`, `825-834`), the stall detector/`STALL_DETECTED_EVENT` (`774-784`)
- Every new FSM-emitted event needs a module-level `*_EVENT` constant (`executor.py:90-130`), a `DESVariant` subclass in `observability/schema.py` registered in `DES_VARIANTS`, and a `SCHEMA_DEFINITIONS` entry in `generate_schemas.py` — evidence: `StallDetectedVariant` (`schema.py:207-211`) + `"stall_detected"` (`generate_schemas.py:383-395`)
- The retryable-infra-blip convention (`FailureType.INFRA_RETRY`/`classify_failure`, `issue_lifecycle.py:141-156`) is a separate, incompatible pattern — it operates on a completed `ActionResult`'s text/exit-code and retries in place; it does not apply to a Popen launch failure, which never produces an `ActionResult`

### Tests
- `scripts/tests/test_fsm_executor.py` — existing `_run_subprocess` patch-target tests (lines 717-839, 5349-5396) are the location for the new "delete working dir mid-run" test this issue's own Proposed Solution names
- `scripts/tests/test_generate_schemas.py`, `scripts/tests/test_des_schema.py`, `scripts/tests/test_des_audit.py` — count-literal/expectation updates required by the event-registration procedure (CONTRIBUTING.md § Event Schema Maintenance)
- `scripts/tests/test_builtin_loops.py` — structural/lint coverage over the built-in loop YAMLs (autodev, auto-refine-and-implement) that would exercise the new terminal wiring

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_runners.py` — `TestDefaultActionRunnerShellPath` (lines 226-460) covers the shell-branch Popen call this issue targets (`runners.py:298-306`) but no existing test makes `Popen` raise — every test there patches `Popen` with `return_value=mock_process`. Add a `patch("subprocess.Popen", side_effect=FileNotFoundError(2, "No such file or directory", "..."))` test here, paired with a `working_dir` pointed at a deleted `tmp_path` subdirectory, following the same shape as `test_fsm_executor.py`'s `test_current_process_cleared_after_successful_run`/`_after_timeout` (lines 5348-5400). This is a second implementation-site test file this issue's Proposed Solution step 4 didn't separately call out [Agent 3 finding]
- `scripts/tests/test_generate_schemas.py` — the hardcoded `assert len(SCHEMA_DEFINITIONS) == 58` / `len(files) == 58` / `len(list(output_dir.glob("*.json"))) == 58` (×2) at lines 21, 114, 121, 250 all need bumping to `59`; `scripts/tests/test_des_schema.py` is set-relational (`>=`/set-difference) and self-adjusts with no literal to bump; `scripts/tests/test_des_audit.py` exercises `main_verify_des_audit()` generically and requires no manual update, only that the new `_emit("workdir_vanished", ...)` call site gets a matching registered `DESVariant` [Agent 2/3 finding]
- `scripts/tests/test_cli_loop_lifecycle.py` — mocks `PersistentExecutor`/`map_final_status` routing via `mock_result.terminated_by = "..."`/`failure_terminal = ...` (e.g. lines 669-870); consider adding a `workdir_vanished` case to confirm it maps to `"failed"` status through the existing fallback [Agent 1 finding]
- `scripts/tests/test_host_guard.py::TestExecutorPressureGate.test_abort_on_pressure` (lines 360-374) and `scripts/tests/test_cost_ceiling_enforcement.py::TestCostCeilingBreachAborts.test_breach_aborts_with_terminated_by` — closest existing `_pending_*`-abort-convention test shapes (assert `result.terminated_by == "<value>"` plus an event name present in captured events); useful as the E2E-level pattern to follow, though neither mocks `Popen` directly since neither originates from a Popen call [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` § "`terminated_by` exit reasons" (lines 907-921) — add a `workdir_vanished` row to the existing Markdown table alongside `host_pressure_abort`/`host_budget_exceeded` [Agent 2 finding]
- `docs/reference/API.md` § `ExecutionResult` (lines 6162, 6172) — closed pipe-union type comment for `terminated_by`; add `workdir_vanished` there (note: this union is already stale relative to `LOOPS_GUIDE.md`, missing `host_pressure_abort`/`host_budget_exceeded`/`cost_ceiling_exceeded`/`user_stopped`/`system_signal` — pre-existing drift, not introduced by this fix) [Agent 2 finding]
- `docs/observability/des-audit.md` — header claims it is generated (`<!-- DO NOT EDIT - generated by ll-verify-des-audit -->`, currently "Total variants: 83") but it is hand-maintained: `ll-verify-des-audit` / `scripts/little_loops/cli/verify_des_audit.py` is audit-only with no write flag and no other writer exists (verified 2026-09-01). Add the `workdir_vanished` row and bump the count to 84 by hand [Agent 2 finding, resolved]
- `docs/reference/schemas/workdir_vanished.json` — new generated JSON-Schema artifact via `ll-generate-schemas`, joining the existing 58-file set referenced by `test_generate_schemas.py` [Agent 2 finding]

## Program Design

### Codebase Research Findings

### Types
- No new data type/shape is introduced. `ExecutionResult.terminated_by: str` (`scripts/little_loops/fsm/types.py`, docstring lines 35-41) already enumerates the extension point for distinct abort kinds (`"cycle_detected"`, `"stall_detected"`, `"host_pressure_abort"`, `"host_budget_exceeded"`); the fix adds one more literal to that same string space (e.g. `"workdir_vanished"`).

### Signatures
- `FSMExecutor._run_subprocess(cmd: list[str], timeout: int) -> ActionResult` (`executor.py:2543`) — Popen call at `2559-2566`, `cwd=self.working_dir`, currently unguarded (full signature also takes `on_output_line`, `idle_timeout`, omitted here for brevity)
- `DefaultActionRunner.run(action: str, timeout: int, is_slash_command: bool, working_dir: Path | None = None) -> ActionResult` (`runners.py:117`) — shell-branch Popen call at `298-306`, `cwd=working_dir`, currently unguarded (full signature has additional kwargs, omitted here for brevity)
- `FSMExecutor._run_action_or_route(state: StateConfig, ctx: InterpolationContext) -> tuple[ActionResult | None, str | None]` (`executor.py:3344`) — the generic `except Exception as exc:` handler (line 3361) that currently intercepts both failure sites identically

### Call Path
`_execute_state` → `_run_action_or_route` → `_run_action` (`executor.py:2180`) → { `_run_subprocess` (mcp_tool actions) | `self.action_runner.run()` → `DefaultActionRunner.run()` shell branch (ordinary shell actions) } → `subprocess.Popen(cwd=...)` raises `FileNotFoundError` → caught generically by `_run_action_or_route` → routes via `state.on_error` → cascades until a `terminal: true` state → `run()` calls `_finish("terminal", ...)`. Established distinct-abort precedent to follow: `_check_host_guard`/`_check_cost_ceiling`/the stall detector each set a `_pending_*` flag checked in `run()`'s main loop (lines 744-834), short-circuiting straight to `self._finish(<new_terminated_by>, error=...)` before further states dispatch — the fix should add an equivalent `_pending_workdir_vanished`-style flag.

### Decision Rules
- **Primary trigger (pre-dispatch)**: at the top of each `run()` main-loop iteration, `self.working_dir is not None and not Path(self.working_dir).exists()` → `_finish("workdir_vanished", ...)`. Action-type-agnostic; this is what catches prompt-mode states, whose launch failures are swallowed into `ActionResult(exit_code=1)` by `runners.py:232-272` and never raise.
- **Secondary trigger (optional, Popen sites)**: a `FileNotFoundError` at `executor.py:2559` or `runners.py:298` is a vanished-cwd failure iff `exc.filename == str(working_dir)`. Verified 2026-09-01: CPython sets `.filename` to the cwd when the child's `chdir` fails (both `shell=True` and `shell=False`) and to the executable name when the command is missing — so `filename` discriminates precisely, whereas a post-hoc `exists()` check is racy and errno alone is ambiguous. Escape hatch: if `working_dir` is `None` or `exc.filename` names something other than the cwd, the failure is NOT reclassified — it falls through to the existing generic `action_error`/`on_error` path unchanged.
- **Outcome bucket**: `_derive_loop_outcome()` maps `workdir_vanished` → `"error"`, not `"failed"` (see Wiring Phase). `FailureType.INFRA_RETRY`/`classify_failure` (`issue_lifecycle.py:141-159`) is a different, incompatible convention — it operates on a completed `ActionResult`'s stderr/exit-code text and retries in place, and cannot apply here since a Popen launch failure never produces an `ActionResult`.

## Impact

Without this, any mid-run loss of a worktree (BUG-3373's actor, manual
deletion, disk issues) converts into a plausible-looking partial-drain
verdict; queued issues are abandoned with no signal. Affects all sub-loop
based automation (`autodev`, `auto-refine-and-implement`,
`sprint-refine-and-implement`, `refine-to-ready-issue`).

## Related Key Documentation

- `docs/reference/EVENT-SCHEMA.md`
- `CONTRIBUTING.md` § Event Schema Maintenance
- `docs/reference/DEFERRAL_CODES.md`

## Status

**Open** | Created: 2026-09-01 | Priority: P2

## Steps to Reproduce

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

Observed as part of the same incident BUG-3373 documents (`ll-loop run sprint-refine-and-implement EPIC-1463`, 2026-09-01). All timestamps from `.loops/.history/2026-09-01T031623-sprint-refine-and-implement/events.jsonl` (UTC):

1. `03:54:58`–`03:57:14` — the shared epic worktree is deleted mid-run (see BUG-3373 for the deleter); a `/ll:refine-issue FEAT-2122 --auto` subprocess is using it as cwd at the time.
2. `03:57:14.937`–`03:57:15.369` — with the cwd now vanished, `refine-to-ready-issue` states (`check_decision_mid_refine`, `check_wire_done`, `normalize_structure`, `check_verify_verdict`, …) each raise `[Errno 2] No such file or directory` at their `Popen(cwd=...)` call, each is caught generically and routed via `on_error`; then the parent `autodev` loop's `skip_inflight`, `dequeue_next`, `finalize_done` states do the same in sequence — roughly 12 such errors in well under a second.
3. `03:57:15.369` — `autodev` reaches `loop_complete`, a normal `terminal: true` state with no `failure: true` marking tied to the vanished-cwd cause.
4. `03:57:15.371` — `sub_loop_worktree_detached` fires (a no-op teardown against the already-deleted path); the run finalizes as `incomplete-abandoned`, with the queued issue (ENH-1722) never dequeued and no signal in the verdict naming "worktree vanished" as the cause.

Reproducing without a real incident requires deleting (or renaming) an `FSMExecutor.working_dir` mid-run — e.g. in a test, spin up an executor against a temp directory, remove that directory after the first state dispatches, and assert on the resulting cascade (see this issue's Proposed Solution step 4 for the corresponding test approach).

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- **File**: `scripts/little_loops/fsm/executor.py` (also `scripts/little_loops/fsm/runners.py`)
- **Anchor**: `_run_action_or_route()` (`executor.py:3344-3372`) — the generic exception-to-`on_error` funnel
- **Cause**: Two subprocess-launch sites call `subprocess.Popen(..., cwd=<working dir>)` with no guard around the call itself: `FSMExecutor._run_subprocess` (`executor.py:2543`, Popen at `2559-2566`, used for `mcp_tool` actions) and `DefaultActionRunner.run()`'s shell branch (`runners.py:298-306`, used for ordinary shell actions). When the cwd (a shared worktree) has vanished, Popen raises `FileNotFoundError` uncaught at either site. It propagates up through `_run_action` (`executor.py:2180`) and is caught by `_run_action_or_route`'s bare `except Exception as exc:` (`executor.py:3361`) — the same generic handler used for every other action exception, with no `FileNotFoundError`/`OSError`-specific branch anywhere between either Popen call and this handler. If the failing state declares `on_error`, the handler emits a generic `action_error` event and routes to `on_error` with no distinction for a vanished-cwd cause. Because the cwd stays vanished, every subsequently-reached `on_error`-linked state fails the same way and re-routes the same way, cascading state-by-state until the FSM lands on some `terminal: true` state; `_finish()` (`executor.py:3835-3930`) reports `terminated_by="terminal"` with `failure_terminal` determined solely by whether that landing state happens to be declared `failure: true` in the loop YAML — nothing about the original Popen failure is preserved. Contrast: `DefaultActionRunner.run()`'s prompt-mode branch (`runners.py:232-272`) already converts a launch failure into a normal `ActionResult(exit_code=1, ...)` instead of raising — the shell branch has no equivalent conversion.


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-01_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 64/100 → LOW

### Outcome Risk Factors
- Broad enumeration across ~15+ touchpoints (executor.py, runners.py, types.py, generate_schemas.py, schema.py, logs.py, plus doc/test wiring) with no single verification grep or automated completeness test tying the full fanout together — Criterion D scored 10/25 (sites enumerated, no verification command) rather than 25/25
- Several dependent-file consumers were reasoned through individually as "no code change needed" (map_final_status default fallback, EXIT_CODES via FAILURE_TERMINAL_EXIT_CODE, etc.) rather than exercised by a test asserting that reasoning holds — mitigate by adding the `workdir_vanished` case to `test_cli_loop_lifecycle.py` already suggested in the Wiring Phase notes to close this gap for at least one consumer

## Session Log
- `/ll:confidence-check` - 2026-09-01T21:40:51 - `4b16ef85-c362-493d-849c-c846475b72fa.jsonl`
- Manual review 2026-09-01: pre-dispatch existence check made the primary detector (prompt-mode branch swallows launch failures, so Popen-site catching alone misses most states); `exc.filename == cwd` discriminator documented; sub-loop propagation rule stated (none needed); `des-audit.md` confirmed hand-maintained; `_derive_loop_outcome` bucket decided as `"error"`.
- `/ll:format-issue` - 2026-09-01T21:22:14 - `1d545f12-483a-4164-8eb9-869bb2218b10.jsonl`
- `/ll:confidence-check` - 2026-09-01T21:18:13 - `af7d0948-35ab-4cf4-ba66-d9d4fed80c50.jsonl`
- `/ll:wire-issue` - 2026-09-01T21:11:04 - `27ab64ec-faa5-4f8f-b9db-d62e91a3f572.jsonl`
- `/ll:refine-issue` - 2026-09-01T20:49:16 - `87c7efdc-d115-415c-a741-428b9e0191a6.jsonl`
