---
id: ENH-3359
status: deferred
priority: P3
discovered_commit: 1f1a8e76c
discovered_branch: main
discovered_date: 2026-08-29
discovered_by: tradeoff-review
focus_area: large-files
labels:
- enhancement
- architecture
- refactoring
parent: EPIC-2789
relates_to:
- ENH-2775
---

# ENH-3359: Extract `_prepatch_*` and `_tamper_guard_*` collaborators from `fsm/executor.py`

## Summary

Split out from ENH-2775 (which originally bundled a `history_reader.py` split
and an `fsm/executor.py` split into one issue; the executor half carried all
the outcome risk and is rescoped here to the one extraction the research shows
is actually missing).

`fsm/executor.py` (3,887 lines and growing) is a single 65-method
`FSMExecutor` class. The concerns the original issue proposed extracting —
retry/backoff, handoff, continuity compaction — are **already extracted** into
collaborator modules (`fsm/rate_limit_circuit.py`, `fsm/handoff_handler.py`,
`fsm/continuity.py`), with only orchestration glue remaining in the executor
class. The remaining unextracted naming-prefix method groups are `_prepatch_*`
(~250 lines) and `_tamper_guard_*` (~110 lines), which have no dedicated
FSM-side collaborator module.

Deferred (not cancelled) because `executor.py` is among the most-edited files
in the repo right now — an extraction racing active development is a
merge-conflict generator. Pick this up when executor churn subsides.

## Location

- **File**: `scripts/little_loops/fsm/executor.py`
- `_tamper_guard_*` group: `_effective_tamper_guard_policy`,
  `_tamper_guard_candidate_paths`, `_tamper_guard_changed_files`,
  `_check_tamper_guard` (L1433-1545, ~110 lines)
- `_prepatch_*` group: `_effective_prepatch_check_policy`, `_prepatch_git`,
  `_prepatch_step_diff`, `_prepatch_existing_forks`, `_prepatch_teardown`,
  `_check_prepatch_check` (L1546-1794, ~250 lines)

## Proposed Solution

Extract each group into a collaborator module following the existing
`RateLimitCircuit` / `HandoffHandler` precedent: a class in
`fsm/prepatch_orchestrator.py` (or similar) and `fsm/tamper_guard.py`, with
`FSMExecutor` retaining thin orchestration wrappers that delegate. Note a
deterministic prepatch-check *core* (no FSM/CLI knowledge) already exists at
`scripts/little_loops/prepatch_check.py` outside the `fsm/` package — the
extracted module is the FSM-side orchestration around it, not a duplicate.

Explicitly **not** in scope (dropped from the original ENH-2775 plan):

- No `fsm/retry.py` / `fsm/session_continuity.py` — already satisfied by
  `rate_limit_circuit.py` / `handoff_handler.py` / `continuity.py`.
- No package conversion of `executor.py` (`fsm/executor/__init__.py`); the
  step-loop core (`run()` L525, `_execute_state()` L1795, `__init__` L197)
  stays in the flat file.
- No split of `scripts/tests/test_fsm_executor.py` (13,256 lines, no existing
  per-concern class boundaries) — a test-file split is a separate decision.

## Constraints carried over from ENH-2775 research

- **Re-export surface**: `from little_loops.fsm.executor import ...` must keep
  serving `FSMExecutor`, `ActionResult`, `ActionRunner`, `DefaultActionRunner`,
  `SimulationActionRunner`, `ExecutionResult`, `EventCallback`, `RouteContext`,
  `RouteDecision`, `derive_run_id`, `PROMPT_SIZE_WARN_EVENT`,
  `RATE_LIMIT_EXHAUSTED_EVENT`, `RATE_LIMIT_STORM_EVENT`,
  `RATE_LIMIT_WAITING_EVENT`, `STALL_DETECTED_EVENT`, `THROTTLE_HARD_EVENT`,
  `THROTTLE_STOP_EVENT`, `THROTTLE_WARN_EVENT`, plus private constants
  `scripts/tests/test_fsm_executor.py` imports mid-function
  (`_DEFAULT_RATE_LIMIT_RETRIES`, `_DEFAULT_API_ERROR_RETRIES`,
  `_DEFAULT_INFRA_RETRY_RETRIES`). 13 direct importers, 31-file transitive
  impact set (`ll-code impact-of`).
- **Attribute-level coupling**: `scripts/little_loops/extension.py:
  wire_extensions()` (L238-267) reads `fsm_executor._contributed_actions`,
  `._contributed_evaluators`, `._interceptors` directly — these attribute
  names must survive on the executor object unchanged.
- **Docs**: `docs/reference/API.md` `FSMExecutor` entries (~L5474 module
  table, L6058-6116 class doc, scattered `_run_action`/`_drain_inbound`/etc.
  call-outs) and `docs/ARCHITECTURE.md` (Event Emitters row L597, prose path
  mentions L904/L1540) reference the current layout.

## Program Design

### Signatures

- `FSMExecutor._check_tamper_guard(...) -> None` — gate entry point for the tamper-guard group; becomes a thin delegation wrapper (`scripts/little_loops/fsm/executor.py:1433` region, L1433-1545).
- `FSMExecutor._check_prepatch_check(...) -> None` — gate entry point for the prepatch group; same disposition (`scripts/little_loops/fsm/executor.py:1546` region, L1546-1794).
- `RateLimitCircuit.record_rate_limit(backoff_seconds: float) -> None` — the collaborator-class precedent the new modules follow (`scripts/little_loops/fsm/rate_limit_circuit.py:44`).
- `HandoffHandler.handle(loop_name: str, continuation: str | None) -> HandoffResult` — second precedent (`scripts/little_loops/fsm/handoff_handler.py:68`).

### Call Path

- `FSMExecutor._execute_state` -> `_check_tamper_guard` / `_check_prepatch_check` -> (new collaborator classes) -> `prepatch_check` core (`scripts/little_loops/prepatch_check.py`) — mirrors the existing `_handle_rate_limit` -> `RateLimitCircuit` and `_handle_handoff` -> `HandoffHandler` delegation shape.

### Decision Rules
N/A — structural extraction; no new gate, threshold, or classification rule.

## Impact Assessment

- **Severity**: Medium
- **Effort**: Medium
- **Risk**: Medium
- **Breaking Change**: No

## Acceptance Criteria

- [ ] `_prepatch_*` and `_tamper_guard_*` logic lives in dedicated `fsm/`
      collaborator modules; `FSMExecutor` retains only delegation wrappers.
- [ ] Full re-export surface above importable unchanged; `wire_extensions()`
      attribute access unchanged.
- [ ] `python -m pytest scripts/tests/` green with no importer changes.
- [ ] API.md / ARCHITECTURE.md references updated.

---

## Status

**Deferred** | Created: 2026-08-29 | Priority: P3
