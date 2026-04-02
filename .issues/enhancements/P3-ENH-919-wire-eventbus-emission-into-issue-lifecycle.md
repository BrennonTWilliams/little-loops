---
discovered_date: 2026-04-02
discovered_by: capture-issue
---

# ENH-919: Wire EventBus Emission into Issue Lifecycle

## Summary

Add EventBus event emission to the key issue lifecycle functions in `issue_lifecycle.py` so that extensions can observe issue state transitions. This is the highest-impact follow-up wiring after the core EventBus was connected to the FSM layer in FEAT-911.

## Context

Identified from FEAT-911 session continuation prompt. FEAT-911 established the EventBus and wired it into `PersistentExecutor` for FSM events. The issue lifecycle functions are the next most impactful emission points — they represent issue-level state changes that extensions (dashboards, notifications, analytics) need visibility into.

## Current Behavior

`close_issue()`, `complete_issue_lifecycle()`, `defer_issue()`, and `create_issue_from_failure()` in `issue_lifecycle.py` perform their operations silently with no event emission. Extensions have no visibility into issue state transitions.

## Expected Behavior

Each function emits an `LLEvent` via the EventBus at key transition points:
- `close_issue()` → emits `issue.closed`
- `complete_issue_lifecycle()` → emits `issue.completed`
- `defer_issue()` → emits `issue.deferred`
- `create_issue_from_failure()` → emits `issue.failure_captured`

Event payloads should include issue ID, file path, and relevant metadata.

## Motivation

Issue lifecycle events are the most valuable for extension consumers after FSM events — they represent the business-level state changes that dashboards, notification integrations, and analytics tools care about most.

## Proposed Solution

In `scripts/little_loops/issue_lifecycle.py`, add an optional `event_bus: EventBus | None = None` parameter to each of the four lifecycle functions. At each transition point, emit an `LLEvent` with the appropriate event type:

- `close_issue()` → `event_bus.emit(LLEvent("issue.closed", {"issue_id": ..., "file_path": ...}))`
- `complete_issue_lifecycle()` → `event_bus.emit(LLEvent("issue.completed", {"issue_id": ..., "file_path": ...}))`
- `defer_issue()` → `event_bus.emit(LLEvent("issue.deferred", {"issue_id": ..., "file_path": ...}))`
- `create_issue_from_failure()` → `event_bus.emit(LLEvent("issue.failure_captured", {"issue_id": ..., "file_path": ...}))`

Follow the same emission pattern established in `PersistentExecutor` for FSM events (FEAT-911).

## Scope Boundaries

- **In scope**: Adding event emission to `close_issue()`, `complete_issue_lifecycle()`, `defer_issue()`, and `create_issue_from_failure()` in `issue_lifecycle.py`
- **Out of scope**: Wiring EventBus into other modules (StateManager, ParallelOrchestrator — tracked separately as ENH-920, ENH-921), adding event subscribers or handlers, modifying EventBus or LLEvent core classes

## Success Metrics

- All 4 lifecycle functions emit events with correct type and payload
- Tests verify event emission for each function (6 acceptance criteria pass)
- No regression in existing issue lifecycle behavior (existing tests continue to pass)

## API/Interface

```python
# Updated function signatures in issue_lifecycle.py
def close_issue(issue_path: Path, ..., event_bus: EventBus | None = None) -> ...:
def complete_issue_lifecycle(issue_path: Path, ..., event_bus: EventBus | None = None) -> ...:
def defer_issue(issue_path: Path, ..., event_bus: EventBus | None = None) -> ...:
def create_issue_from_failure(..., event_bus: EventBus | None = None) -> ...:
```

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — Add event emission to 4 functions

### Dependent Files (Callers/Importers)
- TBD — use `grep -r "close_issue\|complete_issue_lifecycle\|defer_issue\|create_issue_from_failure" scripts/` to find callers that may need to pass `event_bus`

### Similar Patterns
- `scripts/little_loops/persistent_executor.py` — FSM event emission pattern from FEAT-911

### Tests
- `scripts/tests/test_issue_lifecycle.py` — Add event emission tests for each function

### Documentation
- `docs/reference/API.md` — Update function signatures if documented

### Configuration
- N/A

## Implementation Steps

1. Import `EventBus` and `LLEvent` in `issue_lifecycle.py`
2. Accept an optional `event_bus` parameter in each function (or access via a shared instance)
3. Emit appropriately typed events with issue metadata payloads
4. Add tests for event emission in each function

## Acceptance Criteria

- [ ] `close_issue()` emits `issue.closed` event
- [ ] `complete_issue_lifecycle()` emits `issue.completed` event
- [ ] `defer_issue()` emits `issue.deferred` event
- [ ] `create_issue_from_failure()` emits `issue.failure_captured` event
- [ ] All events include issue ID and file path in payload
- [ ] Tests verify emission for each function

## Impact

- **Priority**: P3 — Important follow-up to FEAT-911 but not blocking; extensions can function without issue-level events
- **Effort**: Small — 4 functions need the same pattern (emit call + optional parameter), following established EventBus pattern from FEAT-911
- **Risk**: Low — Additive change only; `event_bus` parameter is optional so existing callers are unaffected
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | System design for event flow |
| architecture | docs/reference/API.md | EventBus and LLEvent API reference |

## Labels

`enhancement`, `captured`, `extension-system`

---

## Status

**Open** | Created: 2026-04-02 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-04-02T18:47:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8eeca827-dfcc-4857-981f-5b6e7a04f182.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ec33f5e-0af1-4604-bdc4-0c4331282e3e.jsonl`
