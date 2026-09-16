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

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — capture `pre_cap_state` in the cap-routing block (lines 646-680, 689-708); thread it through `_finish()` (`:4308`) onto `ExecutionResult`.
- `scripts/little_loops/fsm/persistence.py` — `map_final_status()` (`:132`) to return `interrupted` for the handler-routed case; `LoopState` (`:310`) to persist `pre_cap_state`; `resume()` (`:1287`, specifically the `current_state` restore at `:1303`) to restore from it.
- Option A only: `scripts/little_loops/cli/loop/runner.py` (`EXIT_CODES`, `:39`), `scripts/little_loops/cli/logs.py` (`_derive_loop_outcome`, `:2062`; `_FLAG_OUTCOMES`, `:1188`), `scripts/little_loops/history_reader/usage.py` (`_WASTED_RUN_PREDICATE`, `:310`), `scripts/little_loops/fsm/executor.py` (`_execute_sub_loop` child-result match, `:1349`).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py:568-575` — reads `RESUMABLE_STATUSES` to list resumable instances; benefits automatically once the status is corrected, no code change needed.
- `scripts/little_loops/mcp_server/tasks.py:214-227` — `resumable` flag derived from `RESUMABLE_STATUSES` membership; benefits automatically, no code change needed.

### Similar Patterns
- The unhandled-cap path (`fsm/executor.py:685`, `:708` calling `_finish` directly) is the existing precedent for "cap termination stays resumable" — the fix brings the handler-routed path in line with it rather than inventing new behavior.

### Tests
- `scripts/tests/test_fsm_executor.py` — cap-routing / `on_max_steps` / `on_max_iterations` behavior.
- `scripts/tests/test_fsm_persistence.py` — `map_final_status()`, `resume()` state restoration.
- `scripts/tests/test_ll_logs.py:6688` (`test_parity_with_flag_loops`) — Option A only, if a new `terminated_by` value is added to the closed vocabulary.

### Documentation
- `docs/reference/API.md` — `map_final_status()`, `RESUMABLE_STATUSES`, `PersistentExecutor.resume()` contracts (already listed under Related Key Documentation below).
- `.issues/enhancements/P2-ENH-3473-*.md` — cross-reference note at line 54 should be updated once this issue lands (its own follow-up, not this issue's implementation step).

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

1. Resolve the Option A / Option B decision (`/ll:decide-issue ENH-3483`).
2. Add `pre_cap_state` capture in the cap-routing block and thread it onto `ExecutionResult` / `LoopState`.
3. Update `map_final_status()` so a handler-routed cap terminal maps to `interrupted` (new value or `cap_handled` keyword per the chosen option).
4. Update `PersistentExecutor.resume()` to restore `current_state` from `pre_cap_state` when present.
5. If Option A: update the closed `terminated_by` vocabulary call sites listed in Integration Map (`EXIT_CODES`, `_derive_loop_outcome`, `_FLAG_OUTCOMES`, `_WASTED_RUN_PREDICATE`, `_execute_sub_loop`) and the `test_parity_with_flag_loops` parity list.
6. Add/extend tests in `test_fsm_executor.py` and `test_fsm_persistence.py` covering: handler-routed cap terminal persists `interrupted`, resume restarts from `pre_cap_state` (not the handler state), and the handler does not re-execute on resume.
7. Run `python -m pytest scripts/tests/` and verify the unhandled-cap resumability path is unaffected (regression check).

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

- **In scope**: capturing `pre_cap_state` for handler-routed cap terminations; making `map_final_status()` return `interrupted` for that path; making `resume()` restart from `pre_cap_state`; updating the closed `terminated_by` vocabulary call sites if Option A is chosen.
- **Out of scope**: automatically raising `max_steps`/`max_iterations` on resume (the user still raises the cap manually first, same as the existing unhandled-cap path); ENH-3473's `best_effort.json` checkpoint behavior (separate issue, cross-referenced but not implemented here); re-executing the summary/handler state itself on resume (resume restarts from `pre_cap_state`, never re-enters the handler).

## Backwards Compatibility

## API/Interface

```python
# Example interface/signature
```


## Session Log
- `/ll:format-issue` - 2026-09-16T01:54:03 - `40e731d3-d53c-4de7-b4f5-5d02be86a0f0.jsonl`
- `/ll:capture-issue` - 2026-09-16T01:44:32 - `7e7f4c6d-9565-4770-b859-052872972b63.jsonl`
