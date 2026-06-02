---
discovered_commit: 02d8d383
discovered_branch: main
discovered_date: 2026-05-31 00:00:00+00:00
discovered_by: audit-docs
doc_file: docs/reference/EVENT-SCHEMA.md
testable: false
completed_at: 2026-05-31 05:15:36+00:00
status: done
---

# ENH-1821: Document `cycle_detected` event in EVENT-SCHEMA.md

## Summary

The `cycle_detected` event has a JSON schema file on disk but no corresponding documentation section in the event catalog.

## Location

- **File**: `docs/reference/EVENT-SCHEMA.md`
- **Section**: Subsystem: FSM Executor

## Current Behavior

The `cycle_detected` event is not documented in EVENT-SCHEMA.md at all. There is no section describing its payload fields, when it is emitted, or what subsystem it belongs to.

## Problem

The event is emitted by `FSMExecutor._finish()` in `scripts/little_loops/fsm/executor.py` when a cycle is detected in state transitions. A JSON schema file exists at `docs/reference/schemas/cycle_detected.json`, and it is referenced in code and other issue files. The event catalog should include it for completeness.

## Expected Behavior

Add a `### cycle_detected` section under "Subsystem: FSM Executor" with:
- Description of when the event is emitted
- Payload field table (likely `state`, `iteration`, or similar cycle-related fields from the existing schema)
- Example JSON

## Scope Boundaries

- **In scope**: Add `cycle_detected` documentation section under "Subsystem: FSM Executor" with payload fields and example JSON
- **Out of scope**: Modifying the schema itself, changing executor behavior, documenting other undocmented events, adding new fields
- **Related areas intentionally excluded**: Other FSM executor events (`stall_detected`, `max_iterations`, `timeout`, `error`) — already documented or out of scope

## Impact

- **Severity**: Low — event is functional but undocumented
- **Effort**: Small — read schema file and executor source, write ~15 lines
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `auto-generated`

## Session Log
- `/ll:ready-issue` - 2026-05-31T05:13:01 - `803b0613-e60e-42c8-b77d-61a3fe02a83c.jsonl`
- `/ll:manage-issue enhancement fix ENH-1821` - 2026-05-31T05:15:36 - `570dacae-878d-4005-8418-6e391850d9dd.jsonl`

---

## Resolution

Added `### cycle_detected` section under "Subsystem: FSM Executor" in `docs/reference/EVENT-SCHEMA.md`, between `stall_detected` and `rate_limit_exhausted`. Documents all 7 payload fields (`event`, `ts`, `edge`, `from`, `to`, `count`, `max`) with types, descriptions, and an example JSON block. Fields verified against `docs/reference/schemas/cycle_detected.json`. Emission behavior confirmed from `scripts/little_loops/fsm/executor.py:461-477`.

---

## Status

**Done** | Created: 2026-05-31 | Completed: 2026-05-31T05:15:36Z | Priority: P3
