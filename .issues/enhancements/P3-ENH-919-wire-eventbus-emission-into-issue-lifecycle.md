---
discovered_date: 2026-04-02
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
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

In `scripts/little_loops/issue_lifecycle.py`, add an optional `event_bus: EventBus | None = None` parameter to each of the four lifecycle functions. At each transition point, build a raw event dict (matching the `PersistentExecutor` pattern) and emit via `event_bus.emit()`:

```python
from little_loops.events import EventBus
from datetime import datetime, timezone

def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# In each function, after the operation succeeds:
if event_bus is not None:
    event_bus.emit({
        "event": "issue.closed",  # or issue.completed, issue.deferred, issue.failure_captured
        "ts": _iso_now(),
        "issue_id": info.issue_id,
        "file_path": str(info.path),
    })
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **API correction**: `EventBus.emit()` at `events.py:93` accepts `dict[str, Any]`, not `LLEvent`. The `PersistentExecutor` pattern at `persistence.py:394` emits raw dicts directly. Use `event_bus.emit({"event": ..., "ts": ..., **payload})` — not `event_bus.emit(LLEvent(...))`
- **`LLEvent` constructor requires 3 args** (`type`, `timestamp`, `payload`) at `events.py:27` — the 2-arg form in the original proposal would fail. Use raw dicts for emission (matching `PersistentExecutor`) or call `LLEvent(...).to_dict()` if structured construction is preferred
- **Emit placement**: emit after the operation succeeds (after `_move_issue_to_completed` / file write), following the `PersistentExecutor` pattern where `emit()` is the final step after all bookkeeping

## Scope Boundaries

- **In scope**: Adding event emission to `close_issue()`, `complete_issue_lifecycle()`, `defer_issue()`, and `create_issue_from_failure()` in `issue_lifecycle.py`
- **Out of scope**: Wiring EventBus into other modules (StateManager, ParallelOrchestrator — tracked separately as ENH-920, ENH-921), adding event subscribers or handlers, modifying EventBus or LLEvent core classes

## Success Metrics

- All 4 lifecycle functions emit events with correct type and payload
- Tests verify event emission for each function (6 acceptance criteria pass)
- No regression in existing issue lifecycle behavior (existing tests continue to pass)

## API/Interface

```python
# Updated function signatures in issue_lifecycle.py (actual current signatures + event_bus)
def close_issue(
    info: IssueInfo, config: BRConfig, logger: Logger,
    close_reason: str | None, close_status: str | None,
    fix_commit: str | None = None, files_changed: list[str] | None = None,
    event_bus: EventBus | None = None,
) -> bool:

def complete_issue_lifecycle(
    info: IssueInfo, config: BRConfig, logger: Logger,
    event_bus: EventBus | None = None,
) -> bool:

def defer_issue(
    info: IssueInfo, config: BRConfig, logger: Logger,
    reason: str | None = None,
    event_bus: EventBus | None = None,
) -> bool:

def create_issue_from_failure(
    error_output: str, parent_info: IssueInfo, config: BRConfig, logger: Logger,
    event_bus: EventBus | None = None,
) -> Path | None:
```

### Event Payloads

```python
# issue.closed — emitted after _move_issue_to_completed in close_issue()
{"event": "issue.closed", "ts": "<iso>", "issue_id": str, "file_path": str, "close_reason": str | None}

# issue.completed — emitted after _move_issue_to_completed in complete_issue_lifecycle()
{"event": "issue.completed", "ts": "<iso>", "issue_id": str, "file_path": str}

# issue.deferred — emitted after _move_issue_to_completed in defer_issue()
{"event": "issue.deferred", "ts": "<iso>", "issue_id": str, "file_path": str, "reason": str | None}

# issue.failure_captured — emitted after file write in create_issue_from_failure()
{"event": "issue.failure_captured", "ts": "<iso>", "issue_id": str, "file_path": str, "parent_issue_id": str}
```

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — Add `event_bus` param and emission to `close_issue` (line 525), `complete_issue_lifecycle` (line 604), `defer_issue` (line 697), `create_issue_from_failure` (line 437)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` — `process_issue_inplace()` (line 288) calls `close_issue` (line 465), `complete_issue_lifecycle` (lines 637, 647), `create_issue_from_failure` (line 580). Needs `event_bus` threaded through or left as `None` initially
- `scripts/little_loops/parallel/orchestrator.py` — `_on_worker_complete` (line 830; `close_issue` call at line ~857) and `_merge_sequential` (line 930; `close_issue` call at line ~942) call `close_issue`. `ParallelOrchestrator` has no `event_bus` attribute currently. Note: `_complete_issue_lifecycle_if_needed` (line 1100) does inline resolution, not calling `complete_issue_lifecycle` directly
- `scripts/little_loops/__init__.py` — re-exports these functions (lines 8, 32–33); no changes needed unless signature changes break the re-export
- `scripts/tests/test_issue_manager.py` — patches `close_issue` (line 1431), `create_issue_from_failure` (line 1551), `complete_issue_lifecycle` (line 1634); may need to verify `event_bus=` kwarg doesn't break mocks
- `scripts/tests/test_orchestrator.py` — patches `close_issue` (lines 1286, 1458); same consideration

### Similar Patterns
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor._handle_event` (line 367–394): raw dict emission via `self.event_bus.emit(event)` at line 394. `EventBus()` instantiated at line 344. This is the canonical pattern.
- `scripts/little_loops/cli/loop/_helpers.py:484` — observer wiring: `executor.event_bus.register(display_progress)` with `hasattr` guard for backward compat

### Tests
- `scripts/tests/test_issue_lifecycle.py` — existing tests for all 4 functions at lines 842, 983, 1187, 634. Add emission tests using real `EventBus()` + list accumulator pattern (from `test_events.py:97–110`). Reuse existing fixtures: `mock_logger`, `sample_issue_info`, `sample_config`
- `scripts/tests/test_events.py` — reference test patterns for EventBus emission (lines 97–110)

### Documentation
- `docs/reference/API.md` — update function signatures to include `event_bus` parameter

### Configuration
- N/A

### Notes
- `defer_issue` has no production callers (only tests) — adding `event_bus` param is safe with no upstream threading needed
- Since `event_bus` defaults to `None`, all existing callers continue to work without changes — upstream `event_bus` threading is a follow-up concern (likely when ENH-920/921 are also implemented)

## Implementation Steps

1. Add `from little_loops.events import EventBus` import in `issue_lifecycle.py` and a local `_iso_now()` helper (or reuse `datetime.now()` already imported at line 14)
2. Add `event_bus: EventBus | None = None` as the final keyword parameter to all 4 functions (`close_issue` at line 525, `complete_issue_lifecycle` at line 604, `defer_issue` at line 697, `create_issue_from_failure` at line 437)
3. In each function, emit a raw dict event after the operation succeeds — `close_issue`: after `_move_issue_to_completed` (line 584); `complete_issue_lifecycle`: after `_commit_issue_completion` (line 658); `defer_issue`: after `_commit_issue_completion` (line 746); `create_issue_from_failure`: after file write (line 517)
4. Add tests in `test_issue_lifecycle.py` using real `EventBus()` + list accumulator pattern (see `test_events.py:97-110`). Reuse existing fixtures (`mock_logger`, `sample_issue_info`, `sample_config`). Verify each function emits correct event type and payload fields
5. Run existing tests to verify no regression: `python -m pytest scripts/tests/test_issue_lifecycle.py scripts/tests/test_issue_manager.py scripts/tests/test_orchestrator.py -v`

## Acceptance Criteria

- [x] `close_issue()` emits `issue.closed` event
- [x] `complete_issue_lifecycle()` emits `issue.completed` event
- [x] `defer_issue()` emits `issue.deferred` event
- [x] `create_issue_from_failure()` emits `issue.failure_captured` event
- [x] All events include issue ID and file path in payload
- [x] Tests verify emission for each function

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

**Completed** | Created: 2026-04-02 | Completed: 2026-04-02 | Priority: P3

## Resolution

- **Action**: improve
- **Status**: Completed
- **Date**: 2026-04-02
- **Changes**:
  - Added `event_bus: EventBus | None = None` parameter to `close_issue()`, `complete_issue_lifecycle()`, `defer_issue()`, `create_issue_from_failure()`
  - Each function emits the appropriate event (`issue.closed`, `issue.completed`, `issue.deferred`, `issue.failure_captured`) via EventBus after successful operation
  - Added `_iso_now()` helper and `EventBus` import to `issue_lifecycle.py`
  - Added 5 tests in `TestEventBusEmission` class verifying emission for all 4 functions plus backward compatibility
- **Files Modified**:
  - `scripts/little_loops/issue_lifecycle.py`
  - `scripts/tests/test_issue_lifecycle.py`

## Session Log
- `/ll:refine-issue` - 2026-04-02T18:54:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/41b7e13f-e7a5-4e5d-9839-ca0cca6a202b.jsonl`
- `/ll:format-issue` - 2026-04-02T18:47:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8eeca827-dfcc-4857-981f-5b6e7a04f182.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ec33f5e-0af1-4604-bdc4-0c4331282e3e.jsonl`
- `/ll:confidence-check` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/121e99c6-8412-4e37-9a57-c5f047090d07.jsonl`
- `/ll:ready-issue` - 2026-04-02T20:37:22 - `no-session-resolved`
