---
discovered_date: 2026-04-02
discovered_by: capture-issue
testable: false
---

# ENH-925: Document EventBus Event Types and Payload Schemas

## Summary

Create formal documentation of all EventBus event types and their payload schemas so that third-party extension authors and external consumers (like loop-viz) can integrate without reverse-engineering source code.

## Current Behavior

The EventBus emits 12+ event types across 4 subsystems (FSM executor, StateManager, issue lifecycle, parallel orchestrator). Event type names and payload shapes are only discoverable by reading `fsm/persistence.py`, `state.py`, `issue_lifecycle.py`, and `parallel/orchestrator.py`. There is no centralized reference.

## Expected Behavior

A single reference document (and optionally a machine-readable JSON Schema) that catalogs every event type, its source subsystem, and the exact payload fields with types and descriptions. For example:

```
Event: fsm.state_enter
Source: FSM executor (fsm/persistence.py)
Payload:
  state: str        # Name of the state being entered
  loop_name: str    # Name of the running loop
  iteration: int    # Current loop iteration count
```

## Motivation

Three audiences need this today:

1. **loop-viz** (planned external project) — needs to parse `events.jsonl` files; currently must infer field names from sample data
2. **Extension authors** — the `LLExtension` Protocol gives them `on_event(event: LLEvent)` but no catalog of what events to expect or what fields they carry
3. **Internal development** — as more subsystems wire into the bus, a schema reference prevents drift and undocumented fields

FEAT-916 proposes auto-generating JSON Schema from dataclasses as part of a full Extension SDK, but that's a large effort gated behind scaffolding and test harness work. Standalone event docs are independently useful and unblock loop-viz immediately.

## Proposed Solution

1. Audit all `event_bus.emit()` call sites to catalog every event type and its payload fields
2. Create `docs/reference/EVENT-SCHEMA.md` with a table per subsystem listing event types, payload fields, types, and descriptions
3. Optionally add a `schemas/events.json` JSON Schema file for machine-readable validation
4. Add a cross-reference from `docs/reference/API.md` (which already documents `EventBus`)

## Implementation Steps

1. Grep all `.emit()` calls across the codebase to build the complete event catalog
2. For each event type, document the payload fields with types and descriptions
3. Write `docs/reference/EVENT-SCHEMA.md` organized by subsystem
4. Optionally generate `schemas/events.json` from the catalog
5. Update `docs/reference/API.md` to link to the new schema reference

## Impact

- **Priority**: P3 - Unblocks third-party integration and loop-viz project
- **Effort**: Small - Auditing emit sites is mechanical; the bus already has well-structured events
- **Risk**: Low - Documentation only, no code changes
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Event persistence patterns and FSM executor design |
| architecture | docs/reference/API.md | EventBus and extension API reference |

## Scope Boundaries

- No changes to EventBus implementation, event emission code, or payload structures
- No changes to FSM executor, StateManager, issue lifecycle, or parallel orchestrator
- JSON Schema file (`schemas/events.json`) is optional — not required for the doc to be complete
- FEAT-916 Extension SDK scaffolding and test harness are explicitly out of scope

## Labels

`enh`, `extension-api`, `documentation`, `captured`

## Verification Notes

**Verdict**: VALID — Verified 2026-04-02

- Confirmed `event_bus.emit()` calls across 4 subsystems: `fsm/persistence.py:394`, `issue_lifecycle.py:529,619,695,794`, `parallel/orchestrator.py:916`, `state.py:107` ✓
- FEAT-911 is COMPLETED — `extension.py` exists with `LLExtension` Protocol and `EventBus` wiring
- No `docs/reference/EVENT-SCHEMA.md` exists — documentation gap is real
- Enhancement not yet applied

---

## Resolution

- **Status**: Completed
- **Date**: 2026-04-02
- **Files changed**:
  - `docs/reference/EVENT-SCHEMA.md` — created; catalogs all 19 event types across 4 subsystems with payload field tables
  - `docs/reference/API.md` — added cross-reference link in the `little_loops.events` section

All 19 event types documented: 11 FSM executor events, 1 FSM persistence event, 2 StateManager events, 4 issue lifecycle events, 1 parallel orchestrator event.

## Status

**Completed** | Created: 2026-04-02 | Priority: P3

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-03T03:26:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b73bcde2-df61-4356-b3d0-8afde9dcd38e.jsonl`
- `/ll:manage-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:ready-issue` - 2026-04-03T03:21:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e3630281-fc7f-486c-9eed-1e0b2282b20e.jsonl`
- `/ll:verify-issues` - 2026-04-03T02:58:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b02a8b8-608b-4a1c-989a-390b7334b1d4.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/997b167f-013b-46d4-a03f-9ff27d26a2a1.jsonl`
