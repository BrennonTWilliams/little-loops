---
id: ENH-3483
type: ENH
title: Handler-routed cap terminations (on_max_steps / on_max_iterations) should be
  resumable
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T01:44:24Z'
reconcile_attempted: true
verify_verdict: VALID
---

# ENH-3483: Handler-routed cap terminations (on_max_steps / on_max_iterations) should be resumable

## Summary

When a loop hits `max_steps` / `max_iterations` and has declared an `on_max_steps` / `on_max_iterations` handler, the run already persists `status: interrupted` (resumable) with `terminated_by="max_steps"` / `"max_iterations_reached"` — the BUG-158/BUG-2204 special-cases in the terminal check (`fsm/executor.py:822-832`) and the no-route fallback (`:984-987`) guarantee that. The status mapping is **not** the problem.

The problem is what `ll-loop resume` restarts from. `PersistentExecutor.resume()` (`fsm/persistence.py:1361`) restores `current_state` verbatim from `LoopState.current_state`, which for a handler-routed cap is the state the handler chain ended on — typically its `terminal: true` endpoint (e.g. `done` in the `test_fsm_persistence.py:1486` fixture). The resumed executor is a fresh instance, so `_summary_state_executed` / `_iteration_summary_executed` are `False`; the terminal check at `fsm/executor.py:801` therefore falls through to `_finish("terminal")` (`:835`) and the run "completes" instantly without doing any of the original work. Raising the cap and resuming is a no-op for exactly the loops that took the trouble to declare a salvage path (`general-task.yaml`'s `on_max_steps: summarize_partial`, `canvas-sketch-generator.yaml`), while bare loops resume correctly.

Fix: record `pre_cap_state` — the state that was current immediately before the cap check overwrote `current_state` with the handler — persist it on `LoopState`, and have `resume()` restore `current_state` from it when set. No `map_final_status()` change, no new `terminated_by` value, no vocabulary ripple. (An earlier draft proposed Option A/B around a `terminated_by="terminal"` path; that path is unreachable in current code — see Codebase Research Findings — and both options were dropped.)

Verify against: `fsm/executor.py:646-680` / `:689-708` (cap routing), `:800-835` and `:980-988` (terminal / no-route special-cases), `fsm/persistence.py:1361-1418` (`resume()` restoration), `fsm/persistence.py:144-181` (`map_final_status`, unchanged).

## Current Behavior

Two termination paths exist for cap terminations. Both persist a resumable status, but only one resumes usefully:

- **Unhandled cap** (no `on_max_steps` / `on_max_iterations` declared): the cap check calls `self._finish("max_steps")` / `self._finish("max_iterations_reached")` directly (`fsm/executor.py:685`, `:708`). `map_final_status()` maps both to `"interrupted"` (`RESUMABLE_STATUSES`, `fsm/persistence.py:54-59`). `current_state` at finish is the state that was about to execute, so `resume()` restarts it once the cap is raised.
- **Handler-routed cap** (`on_max_steps` / `on_max_iterations` declared): the cap check overwrites `current_state` with the handler state and sets `_summary_state_executed` / `_iteration_summary_executed` (`:646-680`, `:689-708`). The handler chain runs; when it reaches a terminal (or returns no route) the special-cases at `:822-832` / `:984-987` return `_finish("max_steps")` / `_finish("max_iterations_reached")`, so the persisted status is also `"interrupted"`. But `current_state` at finish is the handler-chain endpoint, and neither the pre-cap state nor the two flags are persisted. `resume()` restarts on the endpoint with both flags `False`; if the endpoint is `terminal: true` (the normal case), `run()` returns `_finish("terminal")` immediately and the run is marked `completed`.

`ll-loop resume` (`cli/loop/lifecycle.py:559`, `cmd_resume`) performs no cap check of its own: resuming an `interrupted` cap run without raising the cap re-hits the cap on the first loop pass (bare path: finishes `max_steps` again; handler path: re-fires the handler). That parity is preserved by this issue.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- **The `terminated_by="terminal"` path assumed by the original Option A/B is unreachable in current code.** `scripts/tests/test_fsm_executor.py:11078-11091` (`TestMaxStepsSummaryHook::test_terminated_by_max_steps_after_summary`) and `test_summary_state_runs_on_cap` (`:11050-11060`) assert `result.terminated_by == "max_steps"` for a handler-routed cap termination, with an `on_max_steps` handler that chains `next="done"` into a `terminal: true` state.
- **Mechanism, already landed as ENH-1631/BUG-2204** (comment at `fsm/executor.py:819-821`): the terminal-state check (`fsm/executor.py:800-835`) special-cases `_summary_state_executed`/`_iteration_summary_executed` — when either flag is set and `current_state` is not the still-pending handler state itself, it returns `_finish("max_steps")`/`_finish("max_iterations_reached")` (`:828`, `:832`) instead of `_finish("terminal")` (`:835`, reached only when BOTH flags are `False`). The `next_state is None` fallback (`:980-988`) applies the identical special-case. The step-cap re-check at the top of `run()`'s loop (`:645-646`) also routes to `_finish("max_steps")` (`:685`) once the flag is set. A handler-routed cap termination is therefore structurally incapable of reaching `_finish("terminal")` once the handler has been entered.
- **Consequence**: `map_final_status()` (`fsm/persistence.py:152-158`) already maps the handler-routed path to `"interrupted"`. No status-mapping change is needed.
- **The verified gap is entirely in `resume()`'s state restoration.** `ExecutionResult.final_state`/`LoopState.current_state` at finish is the handler-chain endpoint, never the pre-cap state. `_summary_state_executed`/`_iteration_summary_executed` are not persisted on `LoopState` and not restored by `resume()` (no hits in `fsm/persistence.py`). A resumed run therefore starts on the endpoint with both flags `False`; a terminal endpoint returns `_finish("terminal")` on the first pass.

_Added by review — 2026-09-16:_

- **Restoring the two flags on resume is harmful, not required.** If `_summary_state_executed` were restored `True` and the user had raised the cap, the resumed run's first legitimate terminal state would hit `fsm/executor.py:822` and return `_finish("max_steps")` instead of `"terminal"`; the no-route fallback at `:984` does the same. The flags are correct at `False` once `current_state` is restored from `pre_cap_state`: with the cap raised the loop simply continues; without it, the handler re-fires exactly as on a fresh cap hit. The earlier "restore or neutralize the flags" step has been removed.
- **BUG-158 flush edge case** (`fsm/executor.py:660-671`): when `_just_routed` is set and the previous state was a sub-loop, `_flush_pending_shell_state()` executes the pending state's action *before* entering the handler. `pre_cap_state` must be captured before that flush. On resume the flushed state's action runs a second time — accepted, because its routing was never evaluated and re-running is the only way to obtain it.
- **`on_max_iterations` path**: the iteration cap is checked at the top of the loop after the maintain route (`:808-818`), so `pre_cap_state` is the maintain restart target (`on_maintain` or `initial`). `_iteration_count` is already persisted and restored (`fsm/persistence.py:1211`, `:1391`), so raising `max_iterations` before resuming takes effect.
- **`cmd_resume` reloads the loop YAML**, so a raised `max_steps` / `max_iterations` is seen by the resumed executor's cap checks (`self.fsm.max_steps`).

## Expected Behavior

A run that reached `max_steps` / `max_iterations` and ran its declared `on_max_steps` / `on_max_iterations` handler persists `status: interrupted` (already true today) **and** a `pre_cap_state` naming the state that was about to execute when the cap fired. `ll-loop resume` restarts execution from `pre_cap_state`, never from the handler-chain endpoint, and never re-enters the handler as the current state.

Concretely, after `resume()` restores from `pre_cap_state`:

- **Cap raised**: the loop continues the original work. When it later reaches a genuine terminal it ends `terminated_by="terminal"` / `status: completed` (or `failed`), because the summary flags are `False` on the resumed executor.
- **Cap not raised**: the first loop pass re-hits the cap and the handler re-fires from `pre_cap_state`, ending `max_steps` / `max_iterations_reached` / `interrupted` again — identical to a fresh cap hit and to the bare-loop path's "immediately finishes `max_steps` again". No warning or refusal is added; this matches existing `cmd_resume` behavior for unhandled caps.
- **Signal / user stop during the handler chain**: the run persists `interrupted` / `user_stopped` with `pre_cap_state` set. Resume prefers `pre_cap_state` whenever it is set, abandoning the unfinished handler chain — the handler is a salvage path, not the work, and the cap will re-fire it if still applicable.
- **Normal finish of a resumed run**: `pre_cap_state` is `None` on the fresh executor's `ExecutionResult`, so the final `LoopState` clears it.

## Motivation

- Loops that declare a salvage path for cap terminations lose usable resumability entirely, while bare loops with no handler keep it — an inversion that penalizes the more careful configuration.
- Business value: a user hitting a step/iteration cap on a loop with a configured handler currently has no path to continue with a larger budget; `ll-loop resume` reports the run as `completed` after doing nothing.
- Technical debt: closes the gap ENH-3473 Decision 2 explicitly deferred to this issue (`.issues/enhancements/P2-ENH-3473-best-effort-checkpoint-on-no-acceptance-termination.md`).

## Proposed Solution

Three changes, no decision needed:

1. Capture `pre_cap_state` in the cap-routing block (`fsm/executor.py:646-680` and `:689-708`) — the value of `current_state` immediately before it is overwritten with `fsm.on_max_steps` / `fsm.on_max_iterations`, captured **before** the BUG-158 flush (`:660-671`). Capture only on the first cap hit (the flags gate re-entry, so this is naturally once per run). Keep it as an executor instance attribute alongside `_summary_state_executed` (`:407`) and read it inside `_finish()` (`:4308`) onto `ExecutionResult`, following the `_iteration_count` pattern — `_finish()`'s signature does not change.
2. Persist `pre_cap_state` on `LoopState` (`fsm/persistence.py:310`; `to_dict()` omits it when `None`, `from_dict()` defaults to `None`), threaded from `result.pre_cap_state` at both `LoopState(...)` construction sites (`run()` and `archive_run_only()`).
3. In `PersistentExecutor.resume()` (`fsm/persistence.py:1361`), restore `current_state` from `state.pre_cap_state` when it is not `None`, else from `state.current_state` as today (`:1377`). Do **not** restore or set `_summary_state_executed` / `_iteration_summary_executed` — they must remain `False` (see review finding above). Emit `from_state` in the `loop_resume` event as the state actually being resumed into.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- **Option A/B's premise does not reproduce** (see Current Behavior finding above): `map_final_status()` already returns `"interrupted"` for a handler-routed cap termination today. No new `terminated_by` value or `cap_handled` keyword is needed, and both options are dropped.
- **Narrowed scope**: `pre_cap_state` capture and its use in `resume()`'s `current_state` restoration are the verified-necessary changes.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — new `self._pre_cap_state: str | None` instance attribute (near `:407`); set it in the cap-routing block (`:646-680`, `:689-708`) before the BUG-158 flush and before overwriting `current_state`; read it in `_finish()` (`:4308`) onto `ExecutionResult`.
- `scripts/little_loops/fsm/types.py` — `ExecutionResult` gains `pre_cap_state: str | None = None`; `to_dict()` emits it only when set (existing conditional-emission pattern).
- `scripts/little_loops/fsm/persistence.py` — `LoopState` (`:322`) gains `pre_cap_state: str | None = None` with `to_dict()`/`from_dict()` support; both `LoopState(...)` construction sites (`run()` ~`:1307`, `archive_run_only()` `:1249`) thread `result.pre_cap_state`; `resume()` (`:1361`, restore at `:1377`) prefers `state.pre_cap_state`. `map_final_status()` (`:144`) is unchanged.
- `scripts/little_loops/cli/loop/lifecycle.py` — `_build_status_dict()` (`:161`) and `_status_single()` (`:213`) surface `pre_cap_state` as "resumes at: <state>" when set, so `ll-loop status` does not present the stale handler-endpoint `current_state` as the resume target.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py:568-575` — reads `RESUMABLE_STATUSES`; no change.
- `scripts/little_loops/mcp_server/tasks.py:214-227` — `resumable` flag from `RESUMABLE_STATUSES`; no change. `handle_tasks_get()` (`:170-177`) reconstructs an `ExecutionResult(...)` from disk without `pre_cap_state`; it is omitted via conditional emission — no change forced.
- `scripts/little_loops/fsm/executor.py:822,830,984,986` — the existing flag reads; unchanged, but they are why the flags must stay `False` on resume.
- `scripts/little_loops/fsm/executor.py:1308-1349` — `_execute_sub_loop()` reads `child_result.terminated_by`; unaffected (no vocabulary change).
- `scripts/little_loops/cli/loop/runner.py:472,515,588` — `run_foreground()` calls `executor.resume()` and maps `terminated_by` to `EXIT_CODES`; unaffected.
- `scripts/little_loops/cli/loop/lifecycle.py:468,777` — `_stop_instance()`, `_print_last_state()` print `state.current_state`; optional to extend, not required.

### Similar Patterns
- The unhandled-cap path (`fsm/executor.py:685`, `:708`) is the precedent: `current_state` at finish is the next state to execute, so resume works. This fix records that same "next state to execute" for the handler-routed path.
- `_iteration_count` is the precedent for an executor attribute persisted on `LoopState` and restored in `resume()` (`fsm/persistence.py:1211`, `:1391`).

### Tests
- `scripts/tests/test_fsm_executor.py` — new `FSMExecutor`/`ExecutionResult`-level tests using `_make_fsm()` (`:11037`) / `_make_maintain_fsm()` (`:11461`): `test_finish_records_pre_cap_state` (on_max_steps), `test_finish_records_pre_cap_state_on_max_iterations` (maintain-mode, expects `on_maintain`/`initial`), `test_pre_cap_state_none_on_unhandled_cap`, `test_pre_cap_state_none_on_terminal`, and a BUG-158 flush variant asserting `pre_cap_state` is the flushed state.
- `scripts/tests/test_fsm_persistence.py::TestPersistentExecutor::test_final_status_interrupted_with_on_max_steps_summary` (`:1486-1515`) — extend with `assert state.pre_cap_state == "check"`.
- `scripts/tests/test_fsm_persistence.py::TestPersistentExecutor::test_run_writes_checkpoint_on_max_steps_with_handler_chaining_to_terminal` (`:1947-1982`) — extend with a `pre_cap_state` assertion. Its docstring already flags the Decision 2 premise as wrong and names this issue as the follow-on.
- New `TestPreCapStatePersistence` in `test_fsm_persistence.py`, modeled on `TestContextPersistence` (`:3985-4167`) / `TestRateLimitRetriesPersistence` (`:3770-3983`): round-trip, omitted-when-None, missing-key-defaults-to-None, `_save_state` inclusion, `archive_run_only()` threading, and resume restoration.
- A `test_resume_restores_persisted_state_not_initial`-style test (pattern at `:4599-4656`) asserting resume restarts from `pre_cap_state`, not the raw `current_state`, and that the `loop_resume` event's `from_state` is `pre_cap_state`.
- Two-executor, file-based cap→resume tests modeled on `test_signal_interrupted_loop_can_be_resumed` (`:3532-3607`):
  - **cap raised**: run to cap with an `on_max_steps` handler chaining to a terminal; second `PersistentExecutor` with a larger `max_steps` resumes; assert the pre-cap state's action runs again, the handler does **not** re-execute, and the run ends `terminated_by="terminal"` / `status: completed` (proves the flags stay `False`).
  - **cap not raised**: same setup, same `max_steps`; assert the handler re-fires once and the run ends `max_steps` / `interrupted` again.
  - **`on_max_iterations` variant** with a maintain-mode loop and raised `max_iterations`.
- `scripts/tests/test_cli_loop_lifecycle.py::TestCmdResume` (`:675-2823`) mocks `PersistentExecutor` at the class boundary, so CLI-level coverage of a real cap-then-resume is out of scope here; the file-based persistence tests above are the integration coverage. Add a `_status_single` test asserting the "resumes at" line when `pre_cap_state` is set.
- `scripts/tests/test_feat_3145_mcp_tasks.py:103,141-160` — `ExecutionResult.to_dict()` field-set test; additive-safe, re-run to confirm.

### Documentation
- `docs/reference/API.md` § `LoopState` and § `ExecutionResult` field-enumeration blocks — add `pre_cap_state`, matching the `continuation_prompt`/`accumulated_ms` style; update the `PersistentExecutor.resume()` contract to say it restarts from `pre_cap_state` when set.
- `docs/reference/json-output-contracts.md` § `ll-loop status --json` — **decision: `pre_cap_state` is CLI-visible** (it is a `LoopState.to_dict()` key and `status --json` emits `to_dict()`); add a row: conditionally emitted, string, "state the next `ll-loop resume` restarts from after a handler-routed cap".
- `docs/guides/LOOPS_GUIDE.md` § "Stop, Resume, and Exit Reasons" table — note `max_steps` / `max_iterations_reached` rows are resumable via `ll-loop resume` after raising the cap; § "What survives `ll-loop stop`/`ll-loop resume`" — qualify "restores the loop to the exact state where it stopped" with the handler-routed exception (restarts from the pre-cap state, handler chain is not replayed).
- `skills/debug-loop-run/SKILL.md` — where `current_state` is described as "last active state", add that for a handler-routed cap `pre_cap_state` is the resume target.
- `.issues/enhancements/P2-ENH-3473-*.md` — **Decision 2's paragraph (`### Decision 2: qualifying set`, "Handler-routed caps do not qualify...") still asserts the stale premise** (handler-routed caps "end as terminal" and get no `best_effort.json`), and remains uncorrected in place. A separate `### Deviations` entry was appended later under `## Program Design` acknowledging the premise doesn't hold and deferring the "if it chooses a new `terminated_by` value" question to this issue (ENH-3483) — but that entry supplements Decision 2 rather than fixing it, so the two sections now say contradictory things. Since this issue settles that question (no new `terminated_by` value — see Proposed Solution), correct Decision 2's paragraph in place and resolve the Deviations entry's conditional accordingly. The in-code comment at `fsm/persistence.py:68-73` (`_NO_ACCEPTANCE_TERMINATIONS`) carries the identical stale "end as terminal... excluded by construction" claim and should be corrected in the same pass. `docs/reference/loops.md` is already correct and needs no change.
- `skills/create-loop/loop-types.md:1075-1083` — the `on_max_steps: summarize_partial` pattern; add one line that such runs are resumable after raising the cap.

### Configuration
- N/A — no config schema changes.

## Program Design

### Types

- `_pre_cap_state: str | None` — new `FSMExecutor` instance attribute (alongside `_summary_state_executed` / `_iteration_summary_executed`, `fsm/executor.py:407`, `:412`), `None` until a handler-routed cap fires.
- `pre_cap_state: str | None = None` — new field on `ExecutionResult` (`fsm/types.py`) and on `LoopState` (`fsm/persistence.py:322`), omitted from `to_dict()` when `None`.

### Signatures

- `FSMExecutor._finish(self, terminated_by: str, error: str | None = None) -> ExecutionResult` (`fsm/executor.py:4308`) — unchanged signature; reads `self._pre_cap_state`.
- `PersistentExecutor.resume(self) -> ExecutionResult | None` (`fsm/persistence.py:1361`) — unchanged signature; restores `current_state` from `state.pre_cap_state or state.current_state`.
- `map_final_status(terminated_by: str, *, failure_terminal: bool = False) -> str` (`fsm/persistence.py:144`) — unchanged.

### Call Path

`FSMExecutor.run()` cap-check block (`fsm/executor.py:646-680`, `:689-708`) sets `self._pre_cap_state = self.current_state` before the BUG-158 flush and before overwriting `current_state` -> handler chain ends via `:828`/`:832`/`:984`/`:986` -> `_finish()` (`:4308`) copies `_pre_cap_state` onto `ExecutionResult.pre_cap_state` -> `PersistentExecutor.run()` / `archive_run_only()` persist it on `LoopState.pre_cap_state` -> `PersistentExecutor.resume()` (`fsm/persistence.py:1361`) restores `current_state` from it when set, leaves the summary flags `False`, and calls `run(clear_previous=False)`.

## Implementation Steps

1. Add `_pre_cap_state` to `FSMExecutor.__init__`; set it in both cap-routing blocks before the flush/overwrite; copy it onto `ExecutionResult` in `_finish()`. Add the `ExecutionResult` field and conditional `to_dict()` emission in `fsm/types.py`.
2. Add `pre_cap_state` to `LoopState` (`to_dict()` / `from_dict()`); thread `result.pre_cap_state` at both `LoopState(...)` construction sites (`run()`, `archive_run_only()`).
3. Update `PersistentExecutor.resume()` to restore `current_state` from `state.pre_cap_state` when set; use the same value for the `loop_resume` event's `from_state`. Leave `_summary_state_executed` / `_iteration_summary_executed` untouched (`False`).
4. Surface `pre_cap_state` in `ll-loop status` (`_build_status_dict()`, `_status_single()`) as "resumes at".
5. Add the tests listed under Tests, including the cap-raised run that must end `terminal` / `completed`, the cap-not-raised run that re-fires the handler, and the `on_max_iterations` variant.
6. Update the docs listed under Documentation, including the ENH-3473 Decision 2 correction.
7. Run `python -m pytest scripts/tests/` and confirm the unhandled-cap resume path is unaffected.

## Impact

- **Priority**: P3 - Correctness gap in resume semantics, not a crash or data-loss bug; affects only loops that both hit a cap and declare a handler.
- **Effort**: Small - One new optional field threaded through `ExecutionResult` / `LoopState`, one capture site in the executor, one branch in `resume()`, a status line, tests, and docs. No `terminated_by` vocabulary change.
- **Risk**: Low-Medium - `resume()` is on the core resume path for every loop; the change is gated on `pre_cap_state is not None`, which is only set on handler-routed caps, so all other resumes take the existing branch. The cap-raised integration test guards against the flag-restoration mistake.
- **Breaking Change**: No - `pre_cap_state` is additive and omitted when `None`; persisted status values are unchanged. The only observable change is that resuming a handler-routed cap run now continues the work instead of completing instantly.

## Related Key Documentation

| Document | Category | Relevance |
|----------|----------|-----------|
| docs/ARCHITECTURE.md | architecture | FSM executor termination, persistence, and resume flow |
| docs/reference/API.md | architecture | `LoopState`, `ExecutionResult`, `PersistentExecutor.resume()` contracts |

## Status

**Open** | Created: 2026-09-16 | Priority: P3

## Success Metrics

- The two-executor cap-raised test passes: after `on_max_steps` fires and the run persists `interrupted`, a resume with a larger `max_steps` re-runs the pre-cap state's action, never re-runs the handler, and ends `terminated_by="terminal"` / `status: completed`.
- The cap-not-raised test passes: resume re-fires the handler once and ends `max_steps` / `interrupted`, matching a fresh cap hit.
- `ll-loop status` on a handler-routed cap run shows the `pre_cap_state` as the resume target.
- Full suite green; every existing unhandled-cap resume test unchanged and passing.

## Scope Boundaries

- **In scope**: capturing `pre_cap_state` for handler-routed cap terminations (both `on_max_steps` and `on_max_iterations`); persisting it on `LoopState`; making `resume()` restart from it; surfacing it in `ll-loop status`; correcting the ENH-3473 Decision 2 prose.
- **Out of scope**: modifying `map_final_status()` or the `terminated_by` vocabulary (already correct; the former Option A/B is dropped); restoring `_summary_state_executed` / `_iteration_summary_executed` on resume (explicitly must not happen); adding a cap-not-raised warning or refusal to `cmd_resume` (parity with the existing unhandled-cap behavior is kept); automatically raising `max_steps` / `max_iterations` on resume; ENH-3473's `best_effort.json` behavior beyond the doc correction; CLI-layer integration tests through `cmd_resume` (mocked at the class boundary today).

## Backwards Compatibility

- `pre_cap_state` is a new optional key on `state.json` / `ll-loop status --json` / `ExecutionResult.to_dict()`, emitted only when set. Old state files without it load with `None` and resume exactly as before.
- Runs persisted before this change by a handler-routed cap have no `pre_cap_state` and keep today's (broken) resume behavior; no migration.
- No change to `RESUMABLE_STATUSES`, `map_final_status()`, exit codes, or `ll-logs` outcome buckets.

## API/Interface

```python
# fsm/types.py
@dataclass
class ExecutionResult:
    ...
    pre_cap_state: str | None = None  # state to resume into after a handler-routed cap

# fsm/persistence.py
@dataclass
class LoopState:
    ...
    pre_cap_state: str | None = None  # omitted from to_dict() when None

# PersistentExecutor.resume(): restoration
self._executor.current_state = state.pre_cap_state or state.current_state
# _summary_state_executed / _iteration_summary_executed intentionally left False
```


## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of
what was wrong and fixed, not an outstanding action item).

- Core technical claims verified accurate against current code: the cap-routing
  blocks (`fsm/executor.py:646-680`, `:689-708`), the terminal-check special-cases
  (`:800-835`, `:980-988`), `_finish()` (`:4308`), and `PersistentExecutor.resume()`
  (`fsm/persistence.py:1361`) all match the issue's description exactly, including
  the subtle "current_state != handler state" fall-through at `:827`/`:831`. No
  `pre_cap_state` concept exists anywhere in the codebase today, confirming this is
  genuinely unimplemented. `test_run_writes_checkpoint_on_max_steps_with_handler_chaining_to_terminal`'s
  own docstring independently corroborates the "ends as max_steps, not terminal"
  finding and already names ENH-3483 as the follow-on.
- Fixed: two Tests-section citations attributed
  `test_final_status_interrupted_with_on_max_steps_summary` and
  `test_run_writes_checkpoint_on_max_steps_with_handler_chaining_to_terminal` to
  class `TestAcceptanceCriteria`; both actually live in `TestPersistentExecutor`.
- Fixed: `cli/loop/lifecycle.py:733` for `cmd_resume` was stale — the function is
  now at `:559` (content/behavior claim still holds: no cap check on resume).
- Fixed: minor ~12-line drift on `fsm/persistence.py` citations — `LoopState`
  `:310` → `:322`, `map_final_status()` `:132`/`:132-169` → `:144`/`:144-181`,
  the `run()`/`archive_run_only()` `LoopState(...)` construction sites `:1303`/
  `:1241-1249` → `:1307`/`:1249`.
- Fixed: the Documentation section's characterization of ENH-3473 Decision 2 was
  imprecise — ENH-3473 already has a `### Deviations` entry (dated 2026-09-16)
  acknowledging the "ends as terminal" premise doesn't hold, but Decision 2's own
  paragraph remains uncorrected and now contradicts that entry. Reworded to name
  both sections and added the matching stale comment at
  `fsm/persistence.py:68-73` (`_NO_ACCEPTANCE_TERMINATIONS`) as needing the same
  correction.
- All other spot-checked citations (test line ranges, `runner.py:472/515/588`,
  `mcp_server/tasks.py:214-227`, `_make_fsm`/`_make_maintain_fsm` at
  `:11037`/`:11461`, `TestContextPersistence`/`TestRateLimitRetriesPersistence`/
  `test_signal_interrupted_loop_can_be_resumed`/
  `test_resume_restores_persisted_state_not_initial`) matched exactly.
- Evidence-quote check (`ll-verify-evidence --json`): clean, 0 findings.
- Decisions log: no active required rules to check against (`ll-issues decisions
  list --type rule --enforcement required --active-only` returned none).
- No `## Blocked By`/`## Blocks` sections present — dependency-reference check
  skipped. Not a match to any completed issue — regression detection skipped.

## Session Log
- `/ll:verify-issues` - 2026-09-16T02:49:53 - `9f9fa6f8-45a5-41d0-954a-49cd44bc619d.jsonl`
- `/ll:wire-issue` - 2026-09-16T02:36:16 - `6b434db3-d48c-4bb4-adf2-19646e1e0d80.jsonl`
- `/ll:reconcile-issue` - 2026-09-16T02:12:37 - `7a435e29-efad-4c49-9f3c-8d2f500cf069.jsonl`
- `/ll:refine-issue` - 2026-09-16T02:07:09 - `7a435e29-efad-4c49-9f3c-8d2f500cf069.jsonl`
- `/ll:format-issue` - 2026-09-16T01:54:03 - `40e731d3-d53c-4de7-b4f5-5d02be86a0f0.jsonl`
- `/ll:capture-issue` - 2026-09-16T01:44:32 - `7e7f4c6d-9565-4770-b859-052872972b63.jsonl`
