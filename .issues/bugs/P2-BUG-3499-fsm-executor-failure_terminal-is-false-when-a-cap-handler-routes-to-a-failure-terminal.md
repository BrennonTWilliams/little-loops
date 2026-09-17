---
id: BUG-3499
type: BUG
title: 'FSM executor: failure_terminal is False when a cap handler routes to a failure
  terminal'
priority: P2
status: open
discovered_by: ll-issues-create
parent: EPIC-3493
epic: EPIC-3493
discovered_date: '2026-09-17'
captured_at: '2026-09-17T06:08:37Z'
labels:
- fsm
- policy-builder
blocks:
- ENH-3492
relates_to:
- ENH-2814
- EPIC-3493
---

# BUG-3499: FSM executor: failure_terminal is False when a cap handler routes to a failure terminal

## Summary

`FSMExecutor._finish` computes `failure_terminal` only when `terminated_by == "terminal"` (`scripts/little_loops/fsm/executor.py:4337`). When the step cap fires and `on_max_steps` (or `on_max_iterations`) routes to a terminal state that declares `failure: true`, the run finishes with `terminated_by == "max_steps"` and `failure_terminal == False`, even though the final state is a failure terminal.

Found during the 2026-09-17 review of ENH-3492 (policy builder terminal destinations), which routes `on_max_steps` to a `needs_attention` terminal with `failure: true` in all three builder modes and needs the result to report failure.

## Current Behavior

Probe loop (`max_steps: 2`, a self-looping shell state, `on_max_steps: needs_attention` where `needs_attention: {terminal: true, failure: true}`) run through `FSMExecutor(fsm).run()`:

```
final_state needs_attention  terminated_by max_steps  failure_terminal False
```

The same applies today to every generated policy-builder loop (`on_max_steps: failed`, `failed` has `failure: true`): budget exhaustion reports `failure_terminal == False` to any consumer that checks that flag.

## Expected Behavior

ENH-2814 made the terminal state's own `failure:` flag the single source of truth for "did this run fail?". That should hold when the failure terminal is reached through a cap handler: `failure_terminal` is `True` whenever the final state is in `fsm.get_failure_states()`, regardless of whether `terminated_by` is `terminal`, `max_steps`, or `max_iterations_reached`. `terminated_by` keeps its current value so audit tooling and `PersistentExecutor` still see the cap.

## Steps to Reproduce

1. Define an FSM with `max_steps: 2`, a self-looping shell state, and `on_max_steps: needs_attention` where `needs_attention: {terminal: true, failure: true}`.
2. Run it via `FSMExecutor(fsm).run()` and let the step cap fire (loop back past `max_steps` without reaching a terminal state on its own).
3. Observe: the returned `ExecutionResult` has `final_state == "needs_attention"`, `terminated_by == "max_steps"`, and `failure_terminal == False` — even though `needs_attention` is a failure terminal.

## Root Cause

- **File**: `scripts/little_loops/fsm/executor.py`
- **Anchor**: `FSMExecutor._finish` (line 4337)
- **Cause**: `failure_terminal = terminated_by == "terminal" and self.current_state in (self.fsm.get_failure_states())` short-circuits to `False` whenever `terminated_by` is `"max_steps"` or `"max_iterations_reached"`, regardless of whether `self.current_state` is actually a failure terminal per `fsm.get_failure_states()`.

## Proposed Solution

In `_finish`, derive `failure_terminal` as `self.current_state in self.fsm.get_failure_states()` when `terminated_by in ("terminal", "max_steps", "max_iterations_reached")`. Audit consumers of `failure_terminal` (`PersistentExecutor`, sub-loop propagation at `executor.py:1326-1364`, `ll-auto`/`ll-sprint`/queue result handling) for behavior changes when a cap-routed run now reports failure. Add executor tests for `on_max_steps` and `on_max_iterations` routing to a `failure: true` terminal and to a plain terminal.

## Integration Map

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/persistence.py:1256,1318` — `PersistentExecutor`/checkpoint code reads `result.failure_terminal`
- `scripts/little_loops/fsm/executor.py:1326-1349` — sub-loop propagation reads `child_result.failure_terminal`
- `scripts/little_loops/cli/loop/audit.py:63,207-262,313` — `LoopRunStats.failure_terminal`
- `scripts/little_loops/cli/loop/runner.py:513-586` — exit-code branching on `result.failure_terminal`
- `scripts/little_loops/cli/loop/evidence.py:56,576` — evidence bundle allowlist
- `scripts/little_loops/transport.py:1751` — transport event payload
- `scripts/little_loops/history_reader/models.py:187`, `usage.py:313-314`, `runs.py:332` — history reader queries
- `scripts/little_loops/session_store/writers.py:1849-2936`, `queries.py:159`, `schema.py:934-1145` — persisted `loop_runs.failure_terminal` column

### Codebase Research Findings

### Files to Modify
- `scripts/little_loops/fsm/executor.py:4337` — `_finish()`'s `failure_terminal` computation; widen the `terminated_by == "terminal"` guard to also cover `"max_steps"` and `"max_iterations_reached"`

### Conventions in Force
- `terminated_by` membership checks are inlined per call site as ad-hoc string tuples, not a shared enum/set constant — `executor.py:1336-1377` (sub-loop routing), `persistence.py:147-184` (`map_final_status`), `runner.py:39-58` (`EXIT_CODES`) each maintain independent buckets; widening one site's tuple does not imply widening another's
- Every prior widening of one of these buckets carries an inline comment naming the originating issue and the rationale for why the new value belongs (e.g. `executor.py:1338-1343` BUG-3375, `:1364-1367` ENH-3019; `runner.py:51-57` BUG-3375/ENH-3471) — follow this precedent for the `_finish` change
- `get_failure_states()` is otherwise consulted as plain set-membership with no `terminated_by` equality gate layered on top (`structural_rules.py:1052-1102`, `executor.py:1738`, `:2038`) — `_finish()` is the one site pairing it with a `terminated_by` equality check, which is exactly the guard this issue widens
- `persistence.py:147-184`'s `map_final_status()` independently buckets `max_steps`/`max_iterations_reached` as `"interrupted"` unconditionally, without consulting `failure_terminal` — a second, structurally similar narrow-membership site touching the same termination reasons; the issue's Proposed Solution does not include changing it, and research found no requirement that it change, but it is noted here as a related site in case scope is revisited
- BUG-3375 is the closest prior precedent and cuts the other direction: it kept `_finish`'s `terminated_by == "terminal"` guard narrow (declined to make `workdir_vanished` failure-terminal-eligible) and instead special-cased the exit-code table consumer (`runner.py:51-54`) — no single rule dictates guard-widening vs. consumer-special-casing; each `terminated_by` value's treatment has been decided per-value with its own rationale comment

### Tests
- No existing test in `test_fsm_executor.py` builds an `on_max_steps`/`on_max_iterations` handler routing to a `StateConfig(terminal=True, failure=True)` state — confirmed by direct search; all current cap-handler tests route to plain terminals
- Nearest cap-routing test fixtures to extend: `TestSummaryHookOnMaxSteps._make_fsm()` (`test_fsm_executor.py:11203-11229`, `on_max_steps`) and `TestMaxIterationFullPassCap._make_maintain_fsm()` (`test_fsm_executor.py:11665-11737`, `on_max_iterations`) — both use a private `_make_*_fsm()` helper parameterized on the handler name plus a `MockActionRunner` driven to the cap; neither currently sets `failure=True` on the handler's terminal state
- AC #4's "existing `TestGeneratedPolicyRouterFailureRouting` cases" are the plain-terminal (`terminated_by == "terminal"`) counterpart at `test_fsm_executor.py:2810` and the dedicated `test_enh2814_failure_terminal_e2e.py` suite — these must keep passing unchanged since this fix does not alter the `terminated_by == "terminal"` branch's outcome

### Documentation
- `docs/reference/API.md:6376-6386` documents `ExecutionResult.failure_terminal` and, immediately below the field block, states "`terminated_by == \"terminal\"` does **not** imply success — read `failure_terminal` for that" without mentioning the cap-handler case — this is the prose AC #5 asks to update
- `docs/reference/EVENT-SCHEMA.md:1061` independently documents the same stale contract ("`true` only when `terminated_by=\"terminal\"` **and** the reached terminal state declares `failure: true`") — not named in AC #5 but states the identical incorrect contract and would drift from API.md if only API.md is updated

### Configuration
- `scripts/little_loops/templates/policy_builder_core.mjs:1136,1223,1399,1435` — the ENH-3492/policy-builder generator that emits `on_max_steps: failed` with `failed: {terminal: true, failure: true}` in all three builder modes; this is the concrete generator referenced by the issue's Summary ("every generated policy-builder loop") and the production path that will observe this fix

## Program Design

### Signatures

- `FSMExecutor._finish(self, terminated_by: str, error: str | None = None) -> ExecutionResult` (unchanged signature; only the `failure_terminal` derivation at line 4337 changes)

### Call Path

`FSMExecutor.run()` (cap-fired routes at lines 1002, 1030) -> `FSMExecutor._finish()` -> `self.fsm.get_failure_states()`

## Impact

- **Priority**: P2 - Silent correctness bug: any consumer that branches on `failure_terminal` (queue/sprint result handling, sub-loop propagation) misreports success for budget-exhausted runs that land on a declared failure terminal; not P1 because it requires a cap-routed run to reach a `failure: true` terminal, which only ENH-2814/ENH-3492-style configs currently do.
- **Effort**: Small - One-line condition change in `_finish` plus new executor tests; no new types or call paths.
- **Risk**: Low - Narrows a `terminated_by == "terminal"` guard to also cover the two cap-routed reasons; existing terminal-reached tests are unaffected since their `terminated_by` is already `"terminal"`.
- **Breaking Change**: No - `failure_terminal` was already documented (ENH-2814) as reflecting the terminal's `failure:` flag; this fixes it to match that contract for two more `terminated_by` values rather than changing the contract.

## Acceptance Criteria

- [ ] A loop whose `on_max_steps` handler is a `failure: true` terminal finishes with `final_state == <handler>`, `terminated_by == "max_steps"`, and `failure_terminal is True`.
- [ ] The same holds for `on_max_iterations` with `terminated_by == "max_iterations_reached"`.
- [ ] A cap handler without `failure: true` still reports `failure_terminal is False`.
- [ ] Existing `TestGeneratedPolicyRouterFailureRouting` cases and the sub-loop `failure_terminal` propagation tests pass unchanged.
- [ ] `docs/reference/API.md` (`ExecutionResult.failure_terminal`) states the cap-handler behavior.

## Status

**Open** | Created: 2026-09-17 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-09-17T06:25:28 - `6e94b71a-0dcd-458c-b8a3-312ff9bed181.jsonl`
- `/ll:format-issue` - 2026-09-17T06:10:54 - `bdd11f79-301a-46b5-9233-83f283efd28d.jsonl`
