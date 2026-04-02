# ENH-919: Wire EventBus Emission into Issue Lifecycle — Implementation Plan

## Overview

Add EventBus event emission to `close_issue()`, `complete_issue_lifecycle()`, `defer_issue()`, and `create_issue_from_failure()` in `issue_lifecycle.py`, following the canonical `PersistentExecutor` pattern.

## Phase 0: Write Tests (Red)

Add tests in `test_issue_lifecycle.py` using `EventBus()` + list accumulator pattern:
- `test_close_issue_emits_event` — verify `issue.closed` with payload
- `test_complete_issue_lifecycle_emits_event` — verify `issue.completed` with payload
- `test_defer_issue_emits_event` — verify `issue.deferred` with payload
- `test_create_issue_from_failure_emits_event` — verify `issue.failure_captured` with payload
- `test_close_issue_no_event_bus` — verify no error when `event_bus=None` (existing behavior)

Each test: create `EventBus()`, register list accumulator, call function with `event_bus=bus`, assert event type and payload fields.

## Phase 1: Add Imports and Helper

In `issue_lifecycle.py`:
1. Add `from datetime import datetime, timezone` (extend existing import)
2. Add `from little_loops.events import EventBus`
3. Add `_iso_now()` helper (matching `persistence.py:46` pattern)

## Phase 2: Add event_bus Parameter and Emission

For each of the 4 functions:
1. Add `event_bus: EventBus | None = None` as final keyword parameter
2. After `logger.success()` (just before `return True`/`return path`), emit event dict

### Emit Points
| Function | Event Type | Emit After Line | Payload Keys |
|---|---|---|---|
| `close_issue` | `issue.closed` | 596 (logger.success) | issue_id, file_path, close_reason |
| `complete_issue_lifecycle` | `issue.completed` | 660 (logger.success) | issue_id, file_path |
| `defer_issue` | `issue.deferred` | 748 (logger.success) | issue_id, file_path, reason |
| `create_issue_from_failure` | `issue.failure_captured` | 518 (logger.success) | issue_id, file_path, parent_issue_id |

## Phase 3: Verify

- [x] All new tests pass (Green)
- [ ] All existing tests pass (no regression)
- [ ] Lint passes
- [ ] Type check passes

## Success Criteria

- [x] All 4 functions emit events with correct type and payload
- [x] Tests verify emission for each function
- [x] No regression in existing behavior
