---
id: ENH-1686
type: ENH
priority: P2
status: done
discovered_date: 2026-05-24
captured_at: '2026-05-24T22:13:08Z'
discovered_by: capture-issue
decision_needed: true
labels:
- enhancement
- captured
confidence_score: 100
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
size: Very Large
---

# ENH-1686: Live-Write Issue Events to history.db (Eliminate Backfill Requirement)

## Summary

Wire issue lifecycle events (capture, status transitions, completion) to be written live to the `issue_events` table in `.ll/history.db` via the existing `SQLiteTransport` / `EventBus` infrastructure, so that `ll-history summary` and `ll-session` queries reflect current issue state without requiring a manual `ll-session backfill`.

## Motivation

The `session_store.py` module has a fully-built `issue_events` table and a `backfill()` function that seeds it from on-disk markdown files. However, `IssueOrchestrator` in `issue_manager.py` has an `EventBus` instance (`self.event_bus`) that is never connected to a `SQLiteTransport` sink for issue events. As a result:

- `ll-history summary` shows no data until a developer manually runs `ll-session backfill`
- Issue creation, status changes (open → in_progress → done), and deferrals are invisible to the DB in real time
- The DB's `issue_events` table only ever reflects a point-in-time snapshot from the last backfill, not live state

This creates friction: developers expect `ll-history` to reflect current work, but must remember to backfill first.

## Current Behavior

`scripts/little_loops/issue_manager.py:994` creates `self.event_bus = EventBus()` but only wires it to the FSM executor (for loop events). Issue lifecycle methods (`close_issue`, `defer_issue`, `update_issue_status`, etc.) do not emit events to the bus, and `SQLiteTransport` is never registered as a subscriber for issue-kind events. `session_store.backfill()` is the only path that writes rows to `issue_events`.

## Expected Behavior

1. **Live writes on status change**: When any issue transitions status (created, in_progress, done, deferred, cancelled), an `"issue"` event is emitted on the `EventBus` and `SQLiteTransport` writes a row to `issue_events` immediately.
2. **`ll-history summary` works cold**: A fresh project with no prior backfill shows accurate issue history if the toolkit has been used to manage issues.
3. **Backfill remains for import**: `ll-session backfill` still works for bootstrapping from pre-existing markdown files, but becomes optional rather than required for day-to-day use.
4. **Deduplication**: The `issue_events` insert logic uses `INSERT OR IGNORE` (or a content hash) so running backfill after live writes does not create duplicates.

## Scope Boundaries

- **In scope**: wiring `SQLiteTransport` to `IssueOrchestrator.event_bus` for `"issue"` kind events; emitting events at existing status-change entry points; updating `_backfill_issues` to use `INSERT OR IGNORE` deduplication; one integration test.
- **Out of scope**: changes to the `issue_events` schema or table structure; migrating loop/FSM events to SQLite (separate concern); real-time sync to external systems (GitHub Issues, Linear); any UI or dashboard work; backfill of non-issue event kinds.

## Implementation Steps

1. **Identify issue lifecycle entry points** in `issue_manager.py` where status changes occur (look for file writes that mutate `status:` frontmatter).
2. **Emit an EventBus event** at each entry point with payload: `{issue_id, transition, issue_type, priority, discovered_by, captured_at, completed_at}`.
3. **Register `SQLiteTransport`** (or a lightweight `IssueEventSink`) on `self.event_bus` at `IssueOrchestrator.__init__` so it receives `"issue"` events.
4. **Update `_backfill_issues`** in `session_store.py` to use `INSERT OR IGNORE` based on `(issue_id, transition)` uniqueness — prevents duplicates when backfill runs after live events already populated the table.
5. **Add integration test**: create an issue file via `IssueOrchestrator`, verify `issue_events` row appears in DB without calling `backfill()`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file:line references for each step:_

**Step 0 — Fix `SQLiteTransport.send()` first (prerequisite):**
- `scripts/little_loops/session_store.py:326` — `send()` method; add `elif event_type.startswith("issue."):` branch before the `return` at line 332; this branch maps the event dict fields → `issue_events` columns and calls `_index(conn, ...)` for FTS; without this, all issue events are silently discarded

**Step 1 — Entry points (correct locations):**
- `scripts/little_loops/issue_lifecycle.py` — all four emit-capable functions: `close_issue()` line 517, `complete_issue_lifecycle()` line 611, `defer_issue()` line 706, `create_issue_from_failure()` line 408; all have `event_bus` param and `if event_bus is not None: event_bus.emit(...)` blocks already — no emit changes needed here
- `scripts/little_loops/issue_lifecycle.py` — add `event_bus: EventBus | None = None` param + emit call to `undefer_issue()` (line 832) and `skip_issue()` (line 785)

**Step 2 — Pass `event_bus` at all call sites in `issue_manager.py`:**
- Line 658: `close_issue(..., event_bus=self.event_bus)`
- Line 832: `create_issue_from_failure(..., event_bus=self.event_bus)`
- Lines 889, 899: `complete_issue_lifecycle(..., event_bus=self.event_bus)`

**Step 3 — Wire `SQLiteTransport` in `AutoManager.__init__()` (`issue_manager.py:994`):**
```python
from little_loops.session_store import SQLiteTransport, DEFAULT_DB_PATH
self.event_bus = EventBus()
self.event_bus.add_transport(SQLiteTransport(DEFAULT_DB_PATH))
```
Pattern from `scripts/little_loops/transport.py:wire_transports()` (line 603, sqlite branch lines 652–655); don't forget `close_transports()` on teardown.

**Step 4 — Deduplication in `_backfill_issues()` (`session_store.py:448`):**
- Change `INSERT INTO issue_events(...)` → `INSERT OR IGNORE INTO issue_events(...)` and add `UNIQUE(issue_id, transition)` constraint (via a new migration in `_MIGRATIONS`); or use `INSERT OR REPLACE` if latest-wins semantics are preferred

**Step 5 — Integration test:**
- Add to `scripts/tests/test_session_store.py` in `TestSQLiteTransport` following pattern of `test_records_loop_event()`: construct `SQLiteTransport(tmp_path / "session.db")`, call `transport.send({"event": "issue.closed", "ts": "...", "issue_id": "ENH-1686", ...})`, assert `recent(db, kind="issue")` returns one row with correct `issue_id`
- Also add end-to-end test: `AutoManager` + `close_issue` → assert `issue_events` row without `backfill()`

## API/Interface

- `IssueOrchestrator.__init__` accepts optional `db_path: Path | None = None` (defaults to `DEFAULT_DB_PATH`) to wire the SQLite sink; tests can pass `:memory:` via `connect()`.
- No public CLI changes required — `ll-history summary` and `ll-session recent` already query `issue_events`; they just need rows to exist.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — `IssueOrchestrator.__init__` (wire `SQLiteTransport`); `close_issue`, `defer_issue`, `update_issue_status`, and any other status-mutating methods (emit `"issue"` events)
- `scripts/little_loops/session_store.py` — `_backfill_issues` (change `INSERT` → `INSERT OR IGNORE` on `(issue_id, transition)`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` is imported by: `ll-auto`, `ll-parallel`, `ll-sprint`, and skill scripts that call `IssueOrchestrator` — all benefit automatically once wired
- `scripts/little_loops/session_store.py` → `SQLiteTransport` is already defined here; no new public API

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/orchestrator.py` — `_on_worker_complete()` (line 920) and `_merge_sequential()` (line 1032) both call `close_issue` without `event_bus`; `self._event_bus` exists on `ParallelOrchestrator` but is not threaded through to lifecycle calls — parallel-path close events will not be live-written unless this is also wired (may be out of scope per scope boundaries, but must be a conscious decision) [Agent 1 + Agent 2 finding]
- `scripts/little_loops/cli/issues/skip.py` — `cmd_skip()` calls `skip_issue()` without `event_bus`; skip events from the `ll-issues skip` command will not be live-written unless wired after `undefer_issue`/`skip_issue` gain the new `event_bus` param [Agent 1 + Agent 2 finding]
- `scripts/little_loops/sync.py` — calls issue lifecycle functions for GitHub sync path; not a live-write concern but is a caller of the lifecycle layer [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/fsm_executor.py` — already registers `SQLiteTransport` on the loop `EventBus`; follow the same pattern for the issue bus
- `scripts/little_loops/event_bus.py` — `EventBus.subscribe()` / `SQLiteTransport` registration pattern to copy

### Tests
- `scripts/tests/test_issue_manager.py` (or new `test_issue_events_live.py`) — integration test: create issue via `IssueOrchestrator`, assert `issue_events` row exists in DB without calling `backfill()`
- `scripts/tests/test_session_store.py` — test `INSERT OR IGNORE` deduplication: insert same event twice, assert single row

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_history_cli.py` — `TestSummaryDbSource.test_summary_uses_db_when_populated` seeds DB via `backfill()`; add companion test asserting `ll-history summary` returns data after live-write (no `backfill()` call), exercising the full `ll-history` cold-start acceptance criterion [Agent 2 + Agent 3 finding]
- `scripts/tests/test_issue_history_parsing.py` — `test_rebuilds_completed_issue_from_db_row` and `test_returns_empty_when_no_done_rows` (lines 446, 461) seed via `backfill()`; add companion test verifying `scan_completed_issues_from_db()` finds live-written rows — critical because `ll-history summary` read path queries `WHERE transition = 'done'` and the live `send()` branch must produce that exact value [Agent 2 + Agent 3 finding]
- **New test (write)**: `TestSQLiteTransport.test_records_issue_event` — follow pattern of `test_records_loop_event` (line 123 in `test_session_store.py`): `transport.send({"event": "issue.completed", "issue_id": "ENH-99", ...})` → `assert recent(db, kind="issue")[0]["issue_id"] == "ENH-99"` [Agent 3 finding]
- **New test (write)**: `TestSQLiteTransport.test_loop_event_does_not_create_issue_row` — verify existing `_LOOP_EVENT_TYPES` events still route to `loop_events` only after the new branch is added [Agent 3 finding]
- **New test (write)**: `TestBackfill` dedup test — call `backfill()` twice on same DB with same issue file, assert single row after second call (validates `INSERT OR IGNORE`) [Agent 3 finding]
- **Tests to update**: `TestEventBusEmission` in `test_issue_lifecycle.py` — add two new test methods for `undefer_issue` and `skip_issue` once `event_bus` param is added to those functions; follow pattern of `test_close_issue_emits_event` at line 1175 [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — `IssueOrchestrator.__init__` signature change (`db_path` param)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — line 1062 instructs users "run `ll-session backfill`" as setup for `ll-history summary`; after this change that step becomes optional for ongoing use — update framing to "backfill is only needed for bootstrapping historical data" [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — line 883 states "Use `ll-session backfill` to populate the store from existing on-disk sources without a live transport"; framing changes after ENH-1686 wires issue events live [Agent 2 finding]

### Configuration
- N/A — no config file changes; `DEFAULT_DB_PATH` already defined in `session_store.py`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Correction — Primary files to modify:**
- `scripts/little_loops/issue_lifecycle.py` is the **primary** file to modify: `close_issue()` (line 517), `complete_issue_lifecycle()` (line 611), `defer_issue()` (line 706), `create_issue_from_failure()` (line 408) — each already has `event_bus: EventBus | None = None` param and conditional emit blocks, but **callers never pass the bus**
- `scripts/little_loops/issue_manager.py` — `AutoManager.__init__()` at line 994 (class is `AutoManager`, not `IssueOrchestrator`); lifecycle call sites that omit `event_bus`: lines 658 (`close_issue`), 832 (`create_issue_from_failure`), 889 and 899 (`complete_issue_lifecycle`)

**Missing `event_bus` param — two lifecycle functions need it added:**
- `scripts/little_loops/issue_lifecycle.py` — `undefer_issue()` (line 832) has no `event_bus` parameter; writes `{"status": "open"}` via `update_frontmatter()` but emits nothing
- `scripts/little_loops/issue_lifecycle.py` — `skip_issue()` (line 785) has no `event_bus` parameter; renames the file but emits nothing

**Critical blocker in `SQLiteTransport.send()` — not mentioned in issue:**
- `scripts/little_loops/session_store.py:332` — `send()` returns early if `event_type not in _LOOP_EVENT_TYPES`; `_LOOP_EVENT_TYPES` (line 55) is a frozenset of FSM-only names (`loop_start`, `state_enter`, etc.) and contains no `"issue.*"` names — all issue events would be silently dropped even after wiring; the `send()` method must be extended with an `elif event_type.startswith("issue.")` branch that maps the event dict to `issue_events` columns and calls `_index()`

**`_index()` call required alongside INSERT:**
- `scripts/little_loops/session_store.py:_backfill_issues()` calls `_index(conn, content=..., kind="issue", ref=str(issue_id), anchor=str(issue_file), ts=ts)` after every INSERT to populate the FTS5 `search_index` table — the live-write path in `send()` must do the same, or FTS search will miss live-written events

**Established wiring pattern to replicate:**
- `scripts/little_loops/cli/loop/run.py:352–355` — `wire_transports(executor.event_bus, _config.events)` calls `bus.add_transport(SQLiteTransport(base / "history.db"))`; for issues, call `self.event_bus.add_transport(SQLiteTransport(DEFAULT_DB_PATH))` directly in `AutoManager.__init__()` (line 994) since there is no config-driven transport list for issue context

**`issue_events` full column set (v1 + v2 migration):**
- `id`, `ts`, `issue_id`, `transition` (holds status value: `"done"`, `"deferred"`, etc.), `discovered_by`, `issue_type`, `priority`, `completed_date`, `captured_at`, `completed_at`
- The live `send()` branch will need to map event dict fields to these columns (e.g., `event["event"]` → derive `transition`; event dict doesn't carry all columns — supplementary frontmatter read or partial insert needed)

**Test files to extend:**
- `scripts/tests/test_session_store.py` — `TestSQLiteTransport` class (pattern: `transport.send(event_dict)` → assert row via `recent(db, kind="issue")`); `TestBackfill` for `INSERT OR IGNORE` dedup test
- `scripts/tests/test_issue_lifecycle.py` — `TestEventBusEmission` class (lines 1175, 1245) already tests emit patterns; add new cases for `undefer_issue` and `skip_issue` once `event_bus` param is added

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Add DB schema migration** in `session_store.py:_MIGRATIONS` — append migration at index 2 (after current v2 migration at index 1):
   ```sql
   CREATE UNIQUE INDEX IF NOT EXISTS idx_issue_events_dedup ON issue_events(issue_id, transition);
   ```
   Bump `SCHEMA_VERSION` from `2` → `3`. **Critical**: without this unique constraint, `INSERT OR IGNORE` from step 4 is a no-op (no conflict can occur, so nothing is ever ignored). Note: the issue's scope boundary says "no schema changes" — this is a constraint index addition rather than a column change; clarify with implementer whether this crosses the boundary or falls within the spirit of the deduplication requirement.

7. **Verify `transition` value alignment** in `SQLiteTransport.send()` new `issue.*` branch — the new branch must write `transition = 'done'` for `issue.completed` events (not `"issue.completed"` or `"completed"`). `scan_completed_issues_from_db()` in `issue_history/parsing.py` queries `WHERE transition = 'done'`; a mismatch silently breaks `ll-history summary` cold-start acceptance criterion.

8. **Parallel path decision** — document whether `ParallelOrchestrator._on_worker_complete()` and `_merge_sequential()` (two `close_issue` calls in `scripts/little_loops/parallel/orchestrator.py`) are in scope. `self._event_bus` already exists on `ParallelOrchestrator` but is not passed to these lifecycle calls. If out of scope, add a TODO comment at those call sites noting that parallel-path close events are not live-written.

9. **Update tests in `test_issue_history_cli.py`** — add companion test to `TestSummaryDbSource` that seeds DB via live-write (not backfill) and asserts `ll-history summary` returns data.

10. **Update tests in `test_issue_history_parsing.py`** — add companion test verifying `scan_completed_issues_from_db()` finds live-written rows (validates the `transition = 'done'` column mapping from step 7).

## Acceptance Criteria

- [ ] After `/ll:capture-issue "foo"` (or any status-changing operation), `ll-session recent --kind issue` shows the new row without running `ll-session backfill`
- [ ] Running `ll-session backfill` after live writes does not duplicate rows
- [ ] Existing `ll-session backfill` path still works for fresh projects with no history
- [ ] Unit/integration tests cover the live-write path

## Impact

- **Priority**: P2 — Eliminates developer friction (manual `ll-session backfill` before any `ll-history` query); affects every developer using `ll-history summary` day-to-day.
- **Effort**: Medium — Requires wiring `SQLiteTransport` to the issue `EventBus`, adding emit calls at ~4–6 lifecycle entry points, and updating backfill deduplication; reuses fully-built infrastructure (no schema changes).
- **Risk**: Low — Additive change only; `ll-session backfill` remains functional as a fallback; existing `issue_events` table schema is unchanged; no breaking API changes.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-05-24 | Priority: P2

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-24 (re-run after refine + wire passes)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- **`transition` alignment is a silent-failure risk**: the new `send()` elif branch must write `transition='done'` (not `'issue.completed'`). `scan_completed_issues_from_db()` queries `WHERE transition = 'done'`; a mismatch makes `ll-history summary` show nothing without any error. Step 7 documents the correct mapping explicitly.
- **Open decision — parallel path scope**: `ParallelOrchestrator._on_worker_complete()` and `_merge_sequential()` both call `close_issue` without `event_bus`. Decide before starting: wire it (expands scope) or add a TODO comment at those call sites. Step 8 documents both resolution paths.
- **Schema boundary interpretation**: step 6 requires adding a `UNIQUE INDEX` migration and bumping `SCHEMA_VERSION` 2 → 3. Scope says "no schema changes" — a constraint index is additive, but confirm this interpretation before touching `_MIGRATIONS`.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-24
- **Reason**: Issue too large for single session (score 9/11 — Very Large)

### Decomposed Into
- ENH-1690: Extend SQLiteTransport to Handle Issue Events
- ENH-1691: Wire Issue Lifecycle EventBus to SQLiteTransport

## Session Log
- `/ll:issue-size-review` - 2026-05-24T00:00:00Z - `898f7f18-27df-4e97-81bc-d975051952e8.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00Z - `d9dd53cb-1947-49f3-931d-c84cd8f105dc.jsonl`
- `/ll:confidence-check` - 2026-05-24T22:30:00Z - `9f9a6182-6d7f-455d-b3ae-341b705fa79b.jsonl`
- `/ll:wire-issue` - 2026-05-25T00:03:45 - `08c5063a-9c10-4456-8e64-60f69ee7a67b.jsonl`
- `/ll:refine-issue` - 2026-05-24T23:57:44 - `3421ff4b-05fc-4e80-bb1d-cb7ee266a185.jsonl`
- `/ll:format-issue` - 2026-05-24T22:15:49 - `e7f2a1ff-6ab8-498b-a8bf-37c6705ab902.jsonl`
- `/ll:capture-issue` - 2026-05-24T22:13:08Z - `a11f6dae-ce13-409d-bf3c-b60b0ed7aabe.jsonl`
