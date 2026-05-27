---
id: ENH-1734
type: ENH
priority: P2
status: open
parent: ENH-1691
discovered_date: 2026-05-26
labels:
- enhancement
- documentation
size: Small
---

# ENH-1734: Documentation Updates for ENH-1691 EventBus Wiring

## Summary

Update all documentation and schema files to reflect the ENH-1691 wiring: new `AutoManager.__init__` signature, new event types (`issue.skipped`, `issue.started`), updated backfill framing, and `config-schema.json` description corrections.

## Parent Issue

Decomposed from ENH-1691: Wire Issue Lifecycle EventBus to SQLiteTransport

## Scope

Covers Wiring Phase items 4–7 from ENH-1691 plus the three referenced doc files in "Files to Modify".

**In scope** (all from Wiring Phase added by `/ll:wire-issue`):
- `docs/reference/API.md` — add `db_path: Path | None = None` to `AutoManager.__init__` signature block; fix pre-existing omissions: add `event_bus: EventBus | None = None` to `complete_issue_lifecycle` and `defer_issue` signature blocks
- `docs/reference/CLI.md` (line 1062) — update "run `ll-session backfill`" framing to reflect live writes; (line 1291) update `### ll-session` description to note `AutoManager` also populates via live-write
- `docs/reference/CONFIGURATION.md` (line 883) — update backfill description to reflect live transport
- `docs/ARCHITECTURE.md` (line ~512–517) — add `ll-auto` row to Extensions/Transports table; note `AutoManager` wires `SQLiteTransport` directly in `__init__`, not via `wire_transports()`
- `docs/reference/EVENT-SCHEMA.md` (lines ~909–916) — add `issue.skipped` and `issue.started` to master event-type table; add `### issue.skipped` and `### issue.started` section blocks
- `config-schema.json` (line ~1178) — update `sqlite` block description from "FSM loop events only" to include issue lifecycle events; note `AutoManager.__init__()` wires directly rather than via config-driven `wire_transports`

**Out of scope**: Source code and test changes (ENH-1733).

**Dependency**: Should be done after ENH-1733 merges so actual signatures and event names can be confirmed against the implementation. Can proceed in parallel if the implementer confirms the design decisions match the issue spec.

## Implementation Notes

- Confirm `undefer_issue()` emits `"issue.started"` (not `"issue.undeferred"`) and `skip_issue()` emits `"issue.skipped"` before updating EVENT-SCHEMA.md
- The ARCHITECTURE.md row for `ll-auto` differs from other CLI entry points: `AutoManager` calls `SQLiteTransport` in `__init__()` directly, not via the external `wire_transports()` helper
- `config-schema.json` `sqlite` block should clarify both FSM loop events AND issue lifecycle events are written; `AutoManager` is the wiring mechanism for the latter

## Acceptance Criteria

- [ ] `docs/reference/API.md` shows `AutoManager.__init__(db_path=None)` signature
- [ ] `docs/reference/EVENT-SCHEMA.md` has `issue.skipped` and `issue.started` entries
- [ ] `docs/ARCHITECTURE.md` Extensions/Transports table includes `ll-auto` row
- [ ] `docs/reference/CLI.md` backfill references updated to reflect live writes
- [ ] `config-schema.json` sqlite description updated to include issue lifecycle events
- [ ] All existing doc links and cross-references remain valid

## Session Log
- `/ll:issue-size-review` - 2026-05-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0f138859-02cf-4887-806e-2fe090003148.jsonl`
