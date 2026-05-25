---
id: ENH-1691
type: ENH
priority: P2
status: open
parent: ENH-1686
discovered_date: 2026-05-24
labels:
- enhancement
---

# ENH-1691: Wire Issue Lifecycle EventBus to SQLiteTransport

## Summary

Wire the `IssueOrchestrator`/`AutoManager` event bus to `SQLiteTransport` so issue lifecycle events (status transitions) are written live to `issue_events` in `.ll/history.db`. Add `event_bus` param to the two lifecycle functions that lack it, pass the bus at all call sites, decide the parallel orchestrator path, and add end-to-end integration tests plus doc updates.

## Parent Issue

Decomposed from ENH-1686: Live-Write Issue Events to history.db (Eliminate Backfill Requirement)

**Depends on**: ENH-1690 (SQLiteTransport must handle `issue.*` events before wiring has any effect)

## Scope

- **In scope**: `event_bus` param on `undefer_issue()` and `skip_issue()`; passing `event_bus` at all call sites in `issue_manager.py`; wiring `SQLiteTransport` in `AutoManager.__init__()`; parallel path decision + handling; end-to-end integration tests; doc updates.
- **Out of scope**: transport-layer changes (ENH-1690); schema migrations (ENH-1690); changes to `issue_events` table structure.

## Implementation Steps

### Step 1 — Add `event_bus` param to missing lifecycle functions (`issue_lifecycle.py`)

- `undefer_issue()` (line 832): add `event_bus: EventBus | None = None` + emit call for `issue.started` transition
- `skip_issue()` (line 785): add `event_bus: EventBus | None = None` + emit call for `issue.skipped` transition

Follow the existing emit pattern in `close_issue()` (line 517), `complete_issue_lifecycle()` (line 611), `defer_issue()` (line 706), and `create_issue_from_failure()` (line 408) — each already has `if event_bus is not None: event_bus.emit(...)` blocks.

### Step 2 — Pass `event_bus` at all call sites in `issue_manager.py`

- Line 658: `close_issue(..., event_bus=self.event_bus)`
- Line 832: `create_issue_from_failure(..., event_bus=self.event_bus)`
- Lines 889, 899: `complete_issue_lifecycle(..., event_bus=self.event_bus)`
- Add pass-through for `undefer_issue()` and `skip_issue()` once Step 1 is done

### Step 3 — Wire `SQLiteTransport` in `AutoManager.__init__()` (`issue_manager.py:994`)

```python
from little_loops.session_store import SQLiteTransport, DEFAULT_DB_PATH

self.event_bus = EventBus()
self.event_bus.add_transport(SQLiteTransport(DEFAULT_DB_PATH))
```

Follow pattern from `scripts/little_loops/cli/loop/run.py:352–355`. Call `close_transports()` on teardown.

Add optional `db_path: Path | None = None` parameter to `AutoManager.__init__()` (defaults to `DEFAULT_DB_PATH`) so tests can pass `:memory:` via `connect()`.

### Step 8 — Parallel path decision (`parallel/orchestrator.py`)

`ParallelOrchestrator._on_worker_complete()` (line 920) and `_merge_sequential()` (line 1032) both call `close_issue` without `event_bus`. `self._event_bus` exists on `ParallelOrchestrator`. Make a conscious decision:

**Option A** (expand scope): wire `self._event_bus` to these call sites — parallel-path close events are live-written.
**Option B** (defer): add TODO comments at those call sites: `# TODO(ENH-1686): parallel-path close events not yet live-written`.

Document the decision in the PR description.

## Files to Modify

- `scripts/little_loops/issue_lifecycle.py` — `undefer_issue()`, `skip_issue()` (add `event_bus` param + emit)
- `scripts/little_loops/issue_manager.py` — `AutoManager.__init__()` (wire transport), all lifecycle call sites (pass `event_bus`)
- `scripts/little_loops/parallel/orchestrator.py` — parallel path decision (Option A or TODO comments)
- `scripts/tests/test_issue_lifecycle.py` — new test methods for `undefer_issue` and `skip_issue` in `TestEventBusEmission`
- `scripts/tests/test_issue_history_cli.py` — companion test: seed via live-write, assert `ll-history summary` returns data
- `scripts/tests/test_issue_history_parsing.py` — companion test: `scan_completed_issues_from_db()` finds live-written rows (validates `transition = 'done'` mapping)
- `docs/reference/API.md` — `AutoManager.__init__` signature (`db_path` param)
- `docs/reference/CLI.md` (line 1062) — update "run `ll-session backfill`" framing to "backfill is only needed for bootstrapping historical data"
- `docs/reference/CONFIGURATION.md` (line 883) — update backfill description to reflect live transport

## Tests

### Integration test (end-to-end)
Add to `scripts/tests/test_issue_manager.py` (or new `test_issue_events_live.py`):
- Create an issue via `AutoManager` with `db_path=tmp_db`, call `close_issue()`, assert `issue_events` row exists in DB **without calling `backfill()`**.

### `TestEventBusEmission` updates (`test_issue_lifecycle.py`)
Add new test methods for `undefer_issue` and `skip_issue` following the pattern of `test_close_issue_emits_event` at line 1175.

### `TestSummaryDbSource` companion (`test_issue_history_cli.py`)
Seed DB via live-write (not backfill), assert `ll-history summary` returns data — exercises the cold-start acceptance criterion.

### `test_issue_history_parsing.py` companion
Add test verifying `scan_completed_issues_from_db()` finds live-written rows; validates that `transition = 'done'` from `send()` matches the `WHERE transition = 'done'` query.

## Acceptance Criteria

- [ ] After `/ll:capture-issue` + status change, `ll-session recent --kind issue` shows the row without `ll-session backfill`
- [ ] `ll-history summary` works cold (no prior backfill) after issue lifecycle operations
- [ ] Running `ll-session backfill` after live writes does not duplicate rows
- [ ] Existing `ll-session backfill` path still works for fresh projects with no history
- [ ] Parallel path decision is explicit (wired or TODO-commented)
- [ ] All new and updated tests pass

## Session Log
- `/ll:issue-size-review` - 2026-05-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/898f7f18-27df-4e97-81bc-d975051952e8.jsonl`
