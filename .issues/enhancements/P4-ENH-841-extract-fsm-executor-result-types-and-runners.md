---
discovered_commit: 8c6cf90
discovered_branch: main
discovered_date: 2026-03-19T00:00:00Z
discovered_by: audit-architecture
focus_area: large-files
confidence_score: 100
outcome_confidence: 70
---

# ENH-841: Extract FSM executor result types and runners

## Summary

`fsm/executor.py` is 1,070 lines combining three distinct concerns: result types (`ExecutionResult`, `ActionResult`), runner implementations (`ActionRunner` protocol + `DefaultActionRunner` + `SimulationActionRunner`), and the core `FSMExecutor` class. Splitting into focused modules reduces file size and clarifies dependency boundaries.

## Current Behavior

`scripts/little_loops/fsm/executor.py` (1,070 lines) contains 6 classes across three unrelated concerns:

1. **Result types** (lines ~44-128): `ExecutionResult`, `ActionResult` dataclasses
2. **Runner implementations** (lines ~106-325): `ActionRunner` protocol, `DefaultActionRunner` (subprocess-based), `SimulationActionRunner` (test/dry-run)
3. **FSM executor** (lines ~337-1050): Core `FSMExecutor` class with state machine logic

The runner implementations are independent of the executor and are already consumed separately (e.g., `cli/loop/testing.py` imports only `SimulationActionRunner`). Result types are imported by `fsm/persistence.py`, creating indirect coupling to the executor module.

## Expected Behavior

`fsm/executor.py` contains only `FSMExecutor` and related state machine logic. Result types live in `fsm/types.py` (or are merged into `fsm/schema.py`). Runner classes live in `fsm/runners.py`. Existing public imports remain available via `fsm/__init__.py` re-exports — no downstream breakage.

## Motivation

- Navigating runner behavior requires scrolling through 1,070 lines of unrelated executor logic
- `fsm/persistence.py` importing result types from `executor.py` creates an indirect coupling — `fsm/types.py` would clarify the dependency
- Runner classes (`DefaultActionRunner`, `SimulationActionRunner`) are already consumed independently in test setups; extraction improves testability without requiring the full executor module

## Proposed Solution

Split into focused modules within the existing `fsm/` package:

1. Extract `ExecutionResult` and `ActionResult` to `fsm/types.py` (or extend `fsm/schema.py`)
2. Extract `ActionRunner` protocol + `DefaultActionRunner` + `SimulationActionRunner` to `fsm/runners.py`
3. Keep `FSMExecutor` in `fsm/executor.py` importing from the new modules
4. Update `fsm/__init__.py` re-exports to maintain public API

## Scope Boundaries

**In scope:**
- Creating `fsm/types.py` with result type dataclasses
- Creating `fsm/runners.py` with runner protocol and implementations
- Updating `fsm/__init__.py` to re-export from new modules
- Updating `fsm/executor.py` imports

**Out of scope:**
- Behavioral changes to any runner or executor logic
- Adding new runner types or result fields
- Renaming existing public symbols
- Modifying test logic (tests may need import path updates only)

## Implementation Steps

1. Create `fsm/types.py` — move `ExecutionResult`, `ActionResult` from `executor.py`
2. Create `fsm/runners.py` — move `ActionRunner`, `DefaultActionRunner`, `SimulationActionRunner` from `executor.py`
3. Update `fsm/executor.py` — replace removed classes with imports from new modules
4. Update `fsm/__init__.py` — add re-exports from `types` and `runners` modules
5. Update test patch paths if any patch targets reference `little_loops.fsm.executor.<RunnerClass>`
6. Run test suite to verify no regressions

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — remove result types and runners, import from new modules
- `scripts/little_loops/fsm/__init__.py` — add re-exports from `types` and `runners`

### New Files
- `scripts/little_loops/fsm/types.py` — `ExecutionResult`, `ActionResult`
- `scripts/little_loops/fsm/runners.py` — `ActionRunner`, `DefaultActionRunner`, `SimulationActionRunner`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/persistence.py` — imports `ActionResult`, `ExecutionResult`, `EventCallback`, `FSMExecutor`
- `scripts/little_loops/cli/loop/testing.py` — imports `DefaultActionRunner`, `ActionResult`, `SimulationActionRunner`, `FSMExecutor`

### Tests
- `scripts/tests/test_fsm_executor.py` — patches `little_loops.fsm.executor.*`; runner-related patches may need path updates
- `scripts/tests/test_fsm_persistence.py` — imports `ActionResult` from executor
- `scripts/tests/test_ll_loop_execution.py` — imports `ActionResult`, `FSMExecutor`; patches `little_loops.fsm.executor.*`
- `scripts/tests/test_ll_loop_display.py` — imports `ExecutionResult` from executor
- `scripts/tests/test_ll_loop_state.py` — patches `little_loops.fsm.executor.subprocess.run`

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P4 — Low-priority architectural cleanup; no user-facing impact
- **Effort**: Small — mechanical extraction with no behavioral changes
- **Risk**: Low — internal refactor within a well-structured package; re-exports via `__init__.py` prevent breaking changes
- **Breaking Change**: No

## Verification Notes

**Verdict**: VALID — Verified 2026-03-19

- `executor.py` is exactly 1,070 lines (confirmed)
- `ExecutionResult` at line 44, `ActionResult` at line 86 (within stated ~44-128 range)
- `ActionRunner` at line 106, `DefaultActionRunner` at line 130, `SimulationActionRunner` at line 216 (within stated ~106-325 range)
- `FSMExecutor` at line 337 (exactly matches stated ~337-1050)
- `fsm/types.py` and `fsm/runners.py` do not exist — issue's proposed new files are accurate
- All dependent files and test files confirmed to import from `executor.py` as described
- **Confidence**: High

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-03-19_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Concerns
- **Patch path breakage**: 14 test patches targeting `little_loops.fsm.executor.subprocess.*` and `little_loops.fsm.executor.time.*` will break once those modules move to `runners.py`. Step 5 acknowledges this, but the scope is broader than "minor" — `test_ll_loop_execution.py` alone has ~10 affected patches across `subprocess.Popen` and `subprocess.run`.

## Session Log
- `/ll:verify-issues` - 2026-04-01T17:45:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/712d1434-5c33-48b6-9de5-782d16771df5.jsonl`
- `/ll:verify-issues` - 2026-03-23T03:43:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/11c70934-6502-4380-92e1-3f88c099af60.jsonl`
- `/ll:verify-issues` - 2026-03-19T23:57:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:format-issue` - 2026-03-19T23:57:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`

---

## Status

**Open** | Created: 2026-03-19 | Priority: P4
