---
discovered_commit: 02d8d383
discovered_branch: main
discovered_date: 2026-05-31T00:00:00Z
discovered_by: audit-docs
doc_file: docs/reference/EVENT-SCHEMA.md
---

# ENH-1821: Document `cycle_detected` event in EVENT-SCHEMA.md

## Summary

The `cycle_detected` event has a JSON schema file on disk but no corresponding documentation section in the event catalog.

## Location

- **File**: `docs/reference/EVENT-SCHEMA.md`
- **Section**: Subsystem: FSM Executor

## Current Content

The `cycle_detected` event is not documented in EVENT-SCHEMA.md at all. There is no section describing its payload fields, when it is emitted, or what subsystem it belongs to.

## Problem

The event is emitted by `FSMExecutor._finish()` in `scripts/little_loops/fsm/executor.py` when a cycle is detected in state transitions. A JSON schema file exists at `docs/reference/schemas/cycle_detected.json`, and it is referenced in code and other issue files. The event catalog should include it for completeness.

## Expected Content

Add a `### cycle_detected` section under "Subsystem: FSM Executor" with:
- Description of when the event is emitted
- Payload field table (likely `state`, `iteration`, or similar cycle-related fields from the existing schema)
- Example JSON

## Impact

- **Severity**: Low — event is functional but undocumented
- **Effort**: Small — read schema file and executor source, write ~15 lines
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-05-31 | Priority: P3
