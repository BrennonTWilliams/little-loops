---
discovered_commit: 8c6cf90
discovered_branch: main
discovered_date: 2026-03-19T00:00:00Z
discovered_by: audit-architecture
focus_area: large-files
---

# ENH-820: Extract FSM executor result types and runners

## Summary

Architectural issue found by `/ll:audit-architecture`.

`fsm/executor.py` is 1,050 lines containing 6 classes: result types (`ExecutionResult`, `ActionResult`), a protocol (`ActionRunner`), two runner implementations (`DefaultActionRunner`, `SimulationActionRunner`), and the core `FSMExecutor` class.

## Location

- **File**: `scripts/little_loops/fsm/executor.py`
- **Line(s)**: 1-1050 (entire file)
- **Module**: `little_loops.fsm.executor`

## Finding

### Current State

The file combines three distinct concerns:

1. **Result types** (lines ~44-128): `ExecutionResult`, `ActionResult` dataclasses
2. **Runner implementations** (lines ~106-325): `ActionRunner` protocol, `DefaultActionRunner` (subprocess-based), `SimulationActionRunner` (test/dry-run)
3. **FSM executor** (lines ~337-1050): Core `FSMExecutor` class with state machine logic

The runner implementations are independent of the executor and could be consumed separately for testing.

### Impact

- **Development velocity**: Working on runner behavior requires navigating the full executor file
- **Maintainability**: Result types are imported by `fsm/persistence.py` — extracting them would make the dependency cleaner
- **Risk**: Low

## Proposed Solution

Split into focused modules within the existing `fsm/` package:

### Suggested Approach

1. Extract `ExecutionResult` and `ActionResult` to `fsm/types.py` (or extend `fsm/schema.py`)
2. Extract `ActionRunner` protocol + `DefaultActionRunner` + `SimulationActionRunner` to `fsm/runners.py`
3. Keep `FSMExecutor` in `fsm/executor.py` importing from the new modules
4. Update `fsm/__init__.py` re-exports

## Impact Assessment

- **Severity**: Low
- **Effort**: Small
- **Risk**: Low — internal refactor within an already well-structured package
- **Breaking Change**: No (re-exports preserved via `__init__.py`)

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

---

## Status

**Open** | Created: 2026-03-19 | Priority: P4
