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
---

# ENH-3483: Handler-routed cap terminations (on_max_steps / on_max_iterations) should be resumable

## Summary

When a loop hits `max_steps` or `max_iterations` **without** a handler, the executor calls `_finish("max_steps")` / `_finish("max_iterations_reached")`, `map_final_status()` maps that to `interrupted`, which is in `RESUMABLE_STATUSES`, so `ll-loop resume` can pick the run back up (after the user raises the cap). When the loop **does** declare `on_max_steps` / `on_max_iterations`, the cap check in `fsm/executor.py:685-708` routes to the summary state instead, the summary state reaches a terminal, and the run ends with `terminated_by="terminal"` → `completed` / `failed` → **not resumable**.

That is an inversion: the loops that took the trouble to declare a salvage path are the ones that lose the ability to resume, while bare loops keep it. A user who configured `on_max_steps: summarize_partial` in `general-task.yaml` and then wants to continue the run with a larger budget has no path — the on-disk state says the run completed.

Proposed direction (decision needed, see options): keep the summary state, but record that the run reached the cap so the persisted status is resumable.

Option A — new `terminated_by` value (e.g. `max_steps_handled`) emitted when a run ends on a terminal reached *via* the `on_max_steps` / `on_max_iterations` route (`_summary_state_executed` / `_iteration_summary_executed` is set at finish time); `map_final_status()` maps it to `interrupted`. Ripples through the closed `terminated_by` vocabulary: `map_final_status()` (`fsm/persistence.py:132`), `_derive_loop_outcome()` (`cli/logs.py:2062`), `EXIT_CODES` (`cli/loop/runner.py:39`), `_WASTED_RUN_PREDICATE` (`history_reader/usage.py:310`), the child-result match in `_execute_sub_loop()` (`fsm/executor.py:1349`), `_FLAG_OUTCOMES` (`cli/logs.py:1188`), and the `test_parity_with_flag_loops` parity list (`scripts/tests/test_ll_logs.py:6688`) — the same ripple ENH-3473 Decision 1 declined for its artifact-only change. `mcp_server/tasks.py` itself only consults `RESUMABLE_STATUSES` (lines 214, 227), not the `terminated_by` string vocabulary directly, so it needs no code change either way — just benefits from the corrected `resumable` value.

Option B — keep `terminated_by="terminal"` but add a `cap_handled: bool` field on `ExecutionResult` (populated from the summary-executed flags) and have `map_final_status()` take it as a keyword, returning `interrupted` when set. Narrower: only `map_final_status()` and its four callers change, no vocabulary change, `ll-logs` outcome buckets untouched. Resume then restores `iteration` from state as today, so `max_steps` must be raised before resuming — same as the bare-loop path.

Either way, resume after a handler-routed cap must **not** re-run the summary state as the current state: `resume()` restores `current_state` from `LoopState`, which would be the terminal summary state. The resumed run needs to restart from the state that was current *before* the cap fired — record it (e.g. `pre_cap_state`) when the cap routes to the handler.

Relationship to ENH-3473: that issue writes `best_effort.json` only on unhandled caps and explicitly excludes handler-routed caps from both the checkpoint and (by inheritance) resumability under its Decision 1. This issue is the follow-on that Decision 1 deferred. If Option A is chosen, ENH-3473's `_NO_ACCEPTANCE_TERMINATIONS` should gain the new value.

Verify against: `fsm/executor.py:685-708` (cap routing), `fsm/persistence.py:132-169` (`map_final_status`), `fsm/persistence.py:54-59` (`RESUMABLE_STATUSES`), `PersistentExecutor.resume()` state restoration.


## Current Behavior

Two termination paths exist for cap terminations, and only one survives a resume:

- **Unhandled cap** (no `on_max_steps` / `on_max_iterations` declared): the cap check calls `self._finish("max_steps")` / `self._finish("max_iterations_reached")` directly (`fsm/executor.py:685`, `:708`). `map_final_status()` (`fsm/persistence.py:132-169`) maps both to `"interrupted"`, which is in `RESUMABLE_STATUSES` (`fsm/persistence.py:54-59`), so `ll-loop resume` picks the run back up once the cap is raised.
- **Handler-routed cap** (`on_max_steps` / `on_max_iterations` declared): the same cap check instead overwrites `current_state` with the handler state (`fsm/executor.py:646-680` for steps, `:689-708` for iterations) and sets `_summary_state_executed` / `_iteration_summary_executed`. When that handler reaches a `terminal: true` state, `_finish("terminal")` runs instead (`fsm/executor.py:835`), `map_final_status()` maps `"terminal"` to `"completed"`/`"failed"`, and `PersistentExecutor.resume()` (`fsm/persistence.py:1299`) refuses to resume because that status is not in `RESUMABLE_STATUSES`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- **Current code does not reproduce the stated `terminated_by="terminal"` path.** `scripts/tests/test_fsm_executor.py:11078-11091` (`TestMaxStepsSummaryHook::test_terminated_by_max_steps_after_summary`) and `test_summary_state_runs_on_cap` (`:11050-11060`) assert `result.terminated_by == "max_steps"` for a handler-routed cap termination, using a fixture whose `on_max_steps` handler (`summarize`, non-terminal, `next="done"` into a `terminal: true` state) matches the scenario this issue describes.
- **Mechanism, already landed as ENH-1631/BUG-2204** (comment at `fsm/executor.py:819-821`): the terminal-state check block (`fsm/executor.py:800-835`) special-cases `_summary_state_executed`/`_iteration_summary_executed` — when either flag is set and `current_state` is not the still-pending handler state itself, it returns `_finish("max_steps")`/`_finish("max_iterations_reached")` (`:828`, `:832`) instead of falling through to `else: return self._finish("terminal")` (`:835`, reached only when BOTH flags are `False`). The `next_state is None` fallback (`:980-988`) applies the identical special-case (`:984-987`). The step-cap re-check at the top of `run()`'s loop (`:645-646`) also unconditionally routes to `_finish("max_steps")` (`:685`) on every subsequent pass once the flag is set. A handler-routed cap termination is therefore structurally incapable of reaching `_finish("terminal")` once the handler has been entered.
- **Consequence**: `map_final_status()` (`fsm/persistence.py:152-158`) already maps `"max_steps"`/`"max_iterations_reached"` to `"interrupted"`, a `RESUMABLE_STATUSES` member (`fsm/persistence.py:54-56`). The persisted `status` for a handler-routed cap termination is already `"interrupted"`/resumable today — see the Proposed Solution finding below for the gap this leaves unaddressed.

## Expected Behavior

A run that reached `max_steps` / `max_iterations` and ran its declared `on_max_steps` / `on_max_iterations` handler to a terminal state persists a resumable status (`interrupted`), exactly like the unhandled-cap path does today. Resuming that run restarts execution from the state that was current immediately before the cap fired — not by re-running the terminal summary/handler state — so raising the cap and resuming continues the original work instead of replaying the handler.

## Motivation

- Loops that declare a salvage path for cap terminations (e.g. `on_max_steps: summarize_partial` in `general-task.yaml`) lose resumability entirely, while bare loops with no handler keep it — an inversion that penalizes the more careful configuration.
- Business value: a user hitting a step/iteration cap on a loop with a configured handler currently has no path to continue with a larger budget; the on-disk state falsely reports the run as `completed`/`failed` instead of `interrupted`.
- Technical debt: closes a gap ENH-3473 Decision 1 explicitly deferred (`.issues/enhancements/P2-ENH-3473-best-effort-checkpoint-on-no-acceptance-termination.md:54`) rather than leaving handler-routed caps permanently unresumable.

## Proposed Solution

Decision needed (Option A vs Option B above) before implementation. Regardless of option, three changes are required:

1. Capture `pre_cap_state` — the state that was current immediately before the cap check overwrote `current_state` with `fsm.on_max_steps` / `fsm.on_max_iterations` (`fsm/executor.py:646-680` and `:689-708`) — so it can be persisted and used to restart on resume.
2. Make `map_final_status()` (`fsm/persistence.py:132`) return `"interrupted"` for a terminal reached via the handler route: either a new `terminated_by` value (Option A) or a `cap_handled` keyword derived from `_summary_state_executed` / `_iteration_summary_executed` (Option B).
3. Make `PersistentExecutor.resume()` (`fsm/persistence.py:1287`) restore `current_state` from the persisted `pre_cap_state` when set, instead of unconditionally restoring the raw `LoopState.current_state` as it does today (`fsm/persistence.py:1303`) — which would otherwise re-enter the terminal handler state.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- **Option A/B's premise does not reproduce** (see Current Behavior finding above): `map_final_status()` already returns `"interrupted"` for a handler-routed cap termination today via the existing `"max_steps"`/`"max_iterations_reached"` branch (`fsm/persistence.py:152-158`). No new `terminated_by` value or `cap_handled` keyword is needed to fix the persisted `status`.
- **The verified gap is entirely in `resume()`'s state restoration**, not in status mapping. `ExecutionResult.final_state`/`LoopState.current_state` at finish time is whatever state the executor was sitting on when `_finish("max_steps")` fired — the handler state itself, or whatever it last routed to (e.g. `"done"` in `test_fsm_executor.py`'s `TestMaxStepsSummaryHook` fixture) — never the original pre-cap state. `_summary_state_executed`/`_iteration_summary_executed` are not persisted on `LoopState` and not restored by `resume()` (grepped `fsm/persistence.py`: no hits for either name), so a resumed run starts from that handler-endpoint state with both flags reset to `False`. If that endpoint state is `terminal: true`, `resume()`'s re-entry into `run()` hits the terminal check (`fsm/executor.py:801`) with both flags `False` and immediately returns `_finish("terminal")` (`:835`) — the resumed run completes instantly without continuing any of the original work. This is the concrete, reproducible resumability defect.
- **Narrowed scope**: `pre_cap_state` capture (Implementation Step 2) and its use in `resume()`'s `current_state` restoration (Step 4) remain verified-necessary. The `map_final_status()` change (Step 3) does not — a decision-maker should re-evaluate whether Option A/B remain worth deciding between before implementation, since both presume a code path (`_finish("terminal")` reached via the handler route) that does not exist in current code.
- **Additional restoration gap surfaced by this trace**: even with `pre_cap_state` restored, `_summary_state_executed`/`_iteration_summary_executed` also need restoring (or the resumed run must otherwise be prevented from either re-firing the handler or immediately hitting `_finish("terminal")` on the stale endpoint state) — Implementation Step 4 should account for this, not just the bare `current_state` swap.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — capture `pre_cap_state` in the cap-routing block (lines 646-680, 689-708); thread it through `_finish()` (`:4308`) onto `ExecutionResult`.
- `scripts/little_loops/fsm/persistence.py` — `LoopState` (`:310`) to persist `pre_cap_state`; `resume()` (`:1287`, specifically the `current_state` restore at `:1303`) to restore `current_state` from it and to restore/neutralize `_summary_state_executed` / `_iteration_summary_executed` so the resumed run neither re-fires the handler nor immediately hits `_finish("terminal")` on the stale handler-endpoint state. `map_final_status()` (`:132`) needs no change — it already maps the handler-routed cap path to `interrupted` via the existing `"max_steps"`/`"max_iterations_reached"` branch (verified, see Codebase Research Findings).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py:568-575` — reads `RESUMABLE_STATUSES` to list resumable instances; benefits automatically once the status is corrected, no code change needed.
- `scripts/little_loops/mcp_server/tasks.py:214-227` — `resumable` flag derived from `RESUMABLE_STATUSES` membership; benefits automatically, no code change needed.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/types.py` — `ExecutionResult` (fields + `to_dict()`) is defined here, not in `executor.py`; the `pre_cap_state` field and its `to_dict()` emission must be added in this file, not just threaded through `_finish()` [Agent 1/2 finding].
- `scripts/little_loops/fsm/persistence.py:1241-1249` — `archive_run_only()` independently calls `map_final_status()` and constructs a second `LoopState(...)`; needs `pre_cap_state` threaded here too for consistency with the primary `run()` construction site [Agent 1/2 finding].
- `scripts/little_loops/fsm/executor.py:822,830,984,986` — additional reads of `_summary_state_executed`/`_iteration_summary_executed` inside `run()`'s terminal-check and no-route branches (same method as the known cap-routing block, different lines) [Agent 1 finding].
- `scripts/little_loops/fsm/executor.py:1308-1349` — `_execute_sub_loop()` reads `child_result.terminated_by` to route sub-loop verdicts; distinct method from the cap-routing block [Agent 1 finding].
- `scripts/little_loops/cli/loop/lifecycle.py:733` — `cmd_resume()` constructs `PersistentExecutor` before calling resume machinery [Agent 1 finding].
- `scripts/little_loops/cli/loop/lifecycle.py:161,213,468,777` — `_build_status_dict()`, `_status_single()`, `_stop_instance()`, `_print_last_state()` print/read `state.current_state` verbatim; after this fix, `current_state` on a handler-routed cap run is the stale handler-endpoint state, not what `resume()` will restart from — `ll-loop status` would show a state name that no longer matches the eventual resume target [Agent 2 finding — display correctness gap].
- `scripts/little_loops/cli/loop/runner.py:472,515,588` — `run_foreground()` calls `executor.resume()` and reads `result.terminated_by` to color success/failure and map to `EXIT_CODES` [Agent 1 finding].
- `scripts/little_loops/mcp_server/tasks.py:170-177` — `handle_tasks_get()` reconstructs an `ExecutionResult(...)` directly from persisted disk state, separate from the known `RESUMABLE_STATUSES` read at `:214-227`; never sets `pre_cap_state`, so it silently omits it via `to_dict()`'s conditional-emission pattern — no code change forced but noted for awareness [Agent 2 finding].

### Similar Patterns
- The unhandled-cap path (`fsm/executor.py:685`, `:708` calling `_finish` directly) is the existing precedent for "cap termination stays resumable" — the fix brings the handler-routed path in line with it rather than inventing new behavior.

### Tests
- `scripts/tests/test_fsm_executor.py` — cap-routing / `on_max_steps` / `on_max_iterations` behavior.
- `scripts/tests/test_fsm_persistence.py` — `resume()` state restoration from `pre_cap_state`, and restoration of `_summary_state_executed` / `_iteration_summary_executed` on resume. `map_final_status()` already returns `interrupted` for this path today (verified) — no test changes needed there.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_persistence.py::TestAcceptanceCriteria::test_final_status_interrupted_with_on_max_steps_summary` (:1486-1515) — existing test already proves `map_final_status()` needs no change; extend with `assert state.pre_cap_state == "check"` once the field exists [Agent 3 finding].
- `scripts/tests/test_fsm_persistence.py::TestAcceptanceCriteria::test_run_writes_checkpoint_on_max_steps_with_handler_chaining_to_terminal` (:1947-1982) — closest existing "handler fires, chains to a terminal" fixture; extend with a `pre_cap_state` assertion [Agent 3 finding].
- New `TestPreCapStatePersistence` class in `test_fsm_persistence.py`, modeled on `TestContextPersistence` (:3985-4167) / `TestRateLimitRetriesPersistence` (:3770-3983) — round-trip, omitted-when-none, missing-key-defaults-to-None, `_save_state` inclusion, and resume-restoration tests for the new field [Agent 3 finding].
- A `test_resume_restores_persisted_state_not_initial`-style test (pattern at `test_fsm_persistence.py:4599-4656`) adapted to assert resume restarts from `pre_cap_state`, not the raw persisted `current_state` (the handler-endpoint state) [Agent 3 finding].
- A two-executor, file-based cap→resume cycle test modeled on `test_signal_interrupted_loop_can_be_resumed` (`test_fsm_persistence.py:3532-3607`) — real `on_max_steps` FSM run to cap, then a second independent `PersistentExecutor.resume()`, asserting the handler does not re-execute and the pre-cap state's action runs again [Agent 3 finding].
- `test_fsm_executor.py` — new `FSMExecutor`/`ExecutionResult`-level tests (`test_finish_records_pre_cap_state`, `test_pre_cap_state_none_on_unhandled_cap`) using the existing `_make_fsm()` (:11037) / `_make_maintain_fsm()` (:11461) fixture builders, verifying `_finish()` threads `pre_cap_state` onto `ExecutionResult` [Agent 3 finding].
- `scripts/tests/test_cli_loop_lifecycle.py::TestCmdResume` (:675-2823) — every test mocks `PersistentExecutor`/`StatePersistence` at the class boundary, so `pre_cap_state` restoration is never exercised at the CLI layer; no integration coverage exists for `ll-loop resume` against a real cap-then-resume run — gap to close or explicitly accept [Agent 3 finding].
- `scripts/tests/test_feat_3145_mcp_tasks.py:103,141-160` — `ExecutionResult.to_dict()` field-set test and `resumable`-flag test; confirmed additive-safe (keyword-only construction) but worth a quick check once `pre_cap_state` is added [Agent 3 finding].

### Documentation
- `docs/reference/API.md` — `map_final_status()`, `RESUMABLE_STATUSES`, `PersistentExecutor.resume()` contracts (already listed under Related Key Documentation below).
- `.issues/enhancements/P2-ENH-3473-*.md` — cross-reference note at line 54 should be updated once this issue lands (its own follow-up, not this issue's implementation step).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` § `LoopState` and § `ExecutionResult` field-enumeration code blocks — need a new line for `pre_cap_state`, matching the `continuation_prompt`/`accumulated_ms` style already there [Agent 2 finding].
- `docs/reference/json-output-contracts.md` § `ll-loop status --json` field reference table — exhaustively lists every conditionally-emitted `LoopState.to_dict()` key; adding `pre_cap_state` requires either a new row or an explicit "internal-only, omitted from CLI JSON" callout following the `context`/BUG-2485 precedent documented in that file — decision needed [Agent 2 finding].
- `docs/guides/LOOPS_GUIDE.md` § "Stop, Resume, and Exit Reasons" table and § "What survives `ll-loop stop`/`ll-loop resume`" prose — the `max_steps`/`max_iterations_reached` rows don't yet mention `ll-loop resume`, and the prose claims resume "restores the loop to the exact state where it stopped," which is no longer true for the handler-routed path once this fix restarts from `pre_cap_state` instead [Agent 2 finding].
- `skills/debug-loop-run/SKILL.md` — documents `current_state` as "last active state" for triage; for a handler-routed cap resume this is the stale handler-endpoint state, not the resume target [Agent 2 finding].
- `skills/create-loop/loop-types.md:1075-1083` — documents the `on_max_steps: summarize_partial` hook pattern this issue's scenario is built on [Agent 1 finding].

### Configuration
- N/A — no config schema changes; behavior change is internal to the FSM executor/persistence layer.

## Program Design

### Types

- `pre_cap_state: str | None` — new field on the executor instance (alongside `_summary_state_executed` / `_iteration_summary_executed`, `fsm/executor.py:407`, `:412`) and on `LoopState` (`fsm/persistence.py:310` dataclass), carrying the state name to resume into.

### Signatures

- `FSMExecutor._finish(self, terminated_by: str, error: str | None = None) -> ExecutionResult` (`fsm/executor.py:4308`)
- `map_final_status(terminated_by: str, *, failure_terminal: bool = False) -> str` (`fsm/persistence.py:132`)
- `PersistentExecutor.resume(self) -> ExecutionResult | None` (`fsm/persistence.py:1287`)

### Call Path

`FSMExecutor.run()` cap-check block (`fsm/executor.py:646-680`, `:689-708`) sets `pre_cap_state` before overwriting `current_state` -> `_finish()` (`:4308`) carries it onto `ExecutionResult` -> `PersistentExecutor.run()` persists it on `LoopState` -> `PersistentExecutor.resume()` (`fsm/persistence.py:1287`) restores `current_state` from `pre_cap_state` (instead of `state.current_state` at `:1303`) when it is set.

## Implementation Steps

1. Add `pre_cap_state` capture in the cap-routing block (`fsm/executor.py:646-680`, `:689-708`) and thread it through `_finish()` (`:4308`) onto `ExecutionResult` / `LoopState` (`fsm/persistence.py:310`). No Option A/B decision is needed first: `map_final_status()` already returns `interrupted` for the handler-routed cap path today (verified), so neither a new `terminated_by` value nor a `cap_handled` keyword is required.
2. Update `PersistentExecutor.resume()` (`fsm/persistence.py:1287`, `:1303`) to restore `current_state` from `pre_cap_state` when present, instead of the raw `LoopState.current_state`.
3. Also restore (or otherwise neutralize) `_summary_state_executed` / `_iteration_summary_executed` on resume, so the resumed run neither re-fires the handler nor immediately hits `_finish("terminal")` on the stale handler-endpoint state.
4. Add/extend tests in `test_fsm_executor.py` and `test_fsm_persistence.py` covering: resume restarts from `pre_cap_state` (not the handler-endpoint state), and the handler does not re-execute or immediately terminate on resume.
5. Run `python -m pytest scripts/tests/` and verify the unhandled-cap resumability path is unaffected (regression check).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `pre_cap_state` field and `to_dict()` emission to `ExecutionResult` in `scripts/little_loops/fsm/types.py` — the dataclass lives here, not in `executor.py`.
- Thread `pre_cap_state=result.pre_cap_state` onto the `LoopState(...)` construction in `PersistentExecutor.run()` (`fsm/persistence.py`, alongside the `map_final_status()` call) and onto `LoopState.to_dict()`/`from_dict()`.
- Also thread `pre_cap_state` through the second `LoopState(...)` construction site in `archive_run_only()` (`fsm/persistence.py:1241-1249`) for consistency.
- Decide and document whether `pre_cap_state` is CLI-visible in `ll-loop status --json` (add a row to `docs/reference/json-output-contracts.md`'s field table) or internal-only like the `context` field (BUG-2485 precedent) — document the decision either way.
- Update `docs/reference/API.md`'s `LoopState`/`ExecutionResult` field-enumeration blocks with the new field.
- Consider whether `_status_single()`/`cmd_status()`/`_print_last_state()` (`cli/loop/lifecycle.py`) should surface `pre_cap_state` or otherwise avoid presenting the stale handler-endpoint `current_state` as the resume target during `ll-loop status`.
- Update `test_fsm_persistence.py::test_final_status_interrupted_with_on_max_steps_summary` and `::test_run_writes_checkpoint_on_max_steps_with_handler_chaining_to_terminal` with `pre_cap_state` assertions.
- Add `TestPreCapStatePersistence` (round-trip/defaults/resume-restoration) to `test_fsm_persistence.py`, modeled on `TestContextPersistence`/`TestRateLimitRetriesPersistence`.
- Add a two-executor file-based cap→resume integration test modeled on `test_signal_interrupted_loop_can_be_resumed`.

## Impact

- **Priority**: P3 - Correctness/consistency gap in resume semantics, not a crash or data-loss bug; affects only loops that both hit a cap and declare a handler.
- **Effort**: Medium - Touches the cap-routing block, `map_final_status()`, and `resume()` state restoration directly (Small on their own); Option A additionally ripples through ~6 call sites in the closed `terminated_by` vocabulary (Integration Map), pushing overall effort to Medium.
- **Risk**: Medium - `_finish()`, `map_final_status()`, and `resume()` sit on the core termination/resume path exercised by every loop run; a regression there affects all loops, not just handler-routed caps. Mitigated by the unhandled-cap path already covering the same code with existing test coverage (`test_fsm_persistence.py`) to diff against.
- **Breaking Change**: No - Additive: an existing `completed`/`failed` outcome becomes `interrupted` (resumable) for handler-routed caps only. Option A's new `terminated_by` value is additive to an open-ended string field; only code doing exhaustive matching (the Integration Map call sites) needs an update, which is in scope here.

## Related Key Documentation

| Document | Category | Relevance |
|----------|----------|-----------|
| docs/ARCHITECTURE.md | architecture | FSM executor termination, persistence, and resume flow |
| docs/reference/API.md | architecture | `map_final_status()`, `RESUMABLE_STATUSES`, `PersistentExecutor.resume()` contracts |

## Status

**Open** | Created: 2026-09-16 | Priority: P3

## Success Metrics

## Scope Boundaries

- **In scope**: capturing `pre_cap_state` for handler-routed cap terminations; making `resume()` restart from `pre_cap_state`; restoring `_summary_state_executed` / `_iteration_summary_executed` on resume so the handler does not re-fire or immediately terminate.
- **Out of scope**: modifying `map_final_status()` — it already returns `interrupted` for the handler-routed cap path today (verified, see Codebase Research Findings), so no change is needed there; the Option A/B closed-`terminated_by`-vocabulary ripple (moot now that no new value is needed); automatically raising `max_steps`/`max_iterations` on resume (the user still raises the cap manually first, same as the existing unhandled-cap path); ENH-3473's `best_effort.json` checkpoint behavior (separate issue, cross-referenced but not implemented here); re-executing the summary/handler state itself on resume (resume restarts from `pre_cap_state`, never re-enters the handler).

## Backwards Compatibility

## API/Interface

```python
# Example interface/signature
```


## Session Log
- `/ll:wire-issue` - 2026-09-16T02:36:16 - `6b434db3-d48c-4bb4-adf2-19646e1e0d80.jsonl`
- `/ll:reconcile-issue` - 2026-09-16T02:12:37 - `7a435e29-efad-4c49-9f3c-8d2f500cf069.jsonl`
- `/ll:refine-issue` - 2026-09-16T02:07:09 - `7a435e29-efad-4c49-9f3c-8d2f500cf069.jsonl`
- `/ll:format-issue` - 2026-09-16T01:54:03 - `40e731d3-d53c-4de7-b4f5-5d02be86a0f0.jsonl`
- `/ll:capture-issue` - 2026-09-16T01:44:32 - `7e7f4c6d-9565-4770-b859-052872972b63.jsonl`
