---
id: ENH-1691
type: ENH
priority: P2
status: open
parent: ENH-1686
discovered_date: 2026-05-24
decision_needed: false
labels:
- enhancement
confidence_score: 95
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
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

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — `undefer_issue()` (line 832), `skip_issue()` (line 785): add `event_bus` param + emit
- `scripts/little_loops/issue_manager.py` — `process_issue_inplace()` (line 453): add `event_bus` param and thread through; `AutoManager.__init__()` (line 947): wire transport; `AutoManager._process_issue()` (line 1217): pass `self.event_bus` to `process_issue_inplace`
- `scripts/little_loops/parallel/orchestrator.py` — `_on_worker_complete()` (line 893), `_merge_sequential()` (line 1020): Option A or TODO; `_complete_issue_lifecycle_if_needed()` (line 1196): separate parallel-path gap (see Step 8)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/auto.py` — constructs `AutoManager` but does not call `wire_transports()`; no transport is currently attached
- `scripts/little_loops/cli/parallel.py:230–235` — reference pattern: creates `EventBus()`, calls `wire_transports()` externally, passes bus to `ParallelOrchestrator.__init__()`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/run.py` — `main_sprint()` calls `process_issue_inplace(info=issue, config=config, logger=logger, dry_run=args.dry_run)` in two places (sequential single-issue wave block and sequential retry loop) **without** passing `event_bus`; after the change these calls will silently skip event emission — consider plumbing `event_bus` through the sprint sequential path or document the gap [Agent 1 / Agent 2 finding]
- `scripts/little_loops/cli/issues/skip.py` — `cmd_skip()` calls `skip_issue(path, new_path, args.reason)` with no bus available; intentional CLI gap, but means `ll-issues skip` never live-writes events — document limitation [Agent 2 finding]

### Similar Patterns
- `scripts/little_loops/cli/loop/run.py:351–355` — `wire_transports(executor.event_bus, _config.events)` pattern to model after
- `scripts/little_loops/transport.py:652–655` — `wire_transports()` SQLite branch: `bus.add_transport(SQLiteTransport(base / "history.db"))`
- `scripts/little_loops/issue_lifecycle.py:594–603` — existing emit pattern in `close_issue()` to follow for new emits

### Tests
- `scripts/tests/test_issue_lifecycle.py` — `TestEventBusEmission` (line 1172): add `test_undefer_issue_emits_event`, `test_skip_issue_emits_event` following `test_close_issue_emits_event` (line 1175)
- `scripts/tests/test_issue_manager.py` — new integration test: `AutoManager` with `db_path=tmp_path/"session.db"`, assert `issue_events` row after `close_issue()` without `backfill()`
- `scripts/tests/test_issue_history_cli.py` — `TestSummaryDbSource` (line 139): add variant seeded via live-write instead of `backfill()`
- `scripts/tests/test_issue_history_parsing.py` — `TestScanCompletedIssuesFromDb` (line 438): add test verifying `scan_completed_issues_from_db()` finds live-written rows

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_workflow_integration.py` — `TestSequentialWorkflowIntegration` (line 24) constructs real `AutoManager` with `tempfile.TemporaryDirectory()`; after the change `AutoManager.__init__()` creates a `SQLiteTransport` — these tests will silently create a DB file unless `db_path=tmp_path/...` is passed explicitly; **medium risk of unexpected DB I/O in CI** [Agent 3 finding]
- `scripts/tests/test_cli_e2e.py` — no `ll-auto` equivalent of `test_ll_parallel_wires_transports` (line 357) exists; add `test_ll_auto_wires_sqlite` to verify `SQLiteTransport` is instantiated in `main_auto()` (model after the parallel variant: patch `little_loops.issue_manager.SQLiteTransport`, assert it is instantiated in `__init__`) [Agent 3 finding]
- `scripts/tests/test_orchestrator.py` — `test_on_worker_complete_close_verdict` (line 1547) and `test_merge_sequential_close` (line 1800) patch `close_issue` via module-level patch; these remain valid for Option B; if Option A is chosen, add assertions that `self._event_bus` is passed to those call sites [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — `AutoManager.__init__` signature (`db_path` param)
- `docs/reference/CLI.md:1062` — update "run `ll-session backfill`" framing
- `docs/reference/CONFIGURATION.md:883` — update backfill description

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — Extensions/Transports table (line ~512–517) lists four CLI entry points but is missing the `ll-auto` row entirely; after the change `AutoManager.__init__()` wires `SQLiteTransport` directly (not via `wire_transports()`), so the row description will differ from other entries [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md` — master event-type table (lines ~909–916) lists existing event types but is missing `issue.skipped` and `issue.started` (emitted by `skip_issue()` and `undefer_issue()` respectively); individual `###` sections also absent [Agent 2 finding]
- `docs/reference/CLI.md:1291` — `### ll-session` description states the DB is "populated by `SQLiteTransport` and `ll-session backfill`"; after the change `AutoManager` also populates via live-write — update framing [Agent 2 finding]
- `docs/reference/API.md` — pre-existing omissions: `#### complete_issue_lifecycle` signature block missing `event_bus: EventBus | None = None`; `### defer_issue` signature block also missing `event_bus` — worth fixing here since this PR touches the same area [Agent 2 finding]

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical — `process_issue_inplace` is a module-level function, not a method**: The call sites at lines 658, 832, 889, 899 are all inside `process_issue_inplace()` at line 453 — a standalone function with no access to `self.event_bus`. Step 2 as written will not compile. The correct approach:
1. Add `event_bus: EventBus | None = None` to `process_issue_inplace()` signature (line 453)
2. Thread `event_bus` through to all lifecycle call sites inside that function
3. Update `AutoManager._process_issue()` (line 1217) to pass `self.event_bus` when calling `process_issue_inplace()`

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
> **Selected:** Option B (defer) — Keeps ENH-1691 focused on the AutoManager sequential path; `_complete_issue_lifecycle_if_needed()` at line 1196 is a local reimplementation requiring a deeper refactor that warrants its own issue.

Document the decision in the PR description.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Additional parallel-path gap**: `_complete_issue_lifecycle_if_needed()` (line 1196) inlines its own lifecycle logic (calls `update_frontmatter` + git commit directly) rather than delegating to `complete_issue_lifecycle()` from `issue_lifecycle.py`. It is called by `_merge_sequential`. It emits no events. Consider explicitly adding this function to the Option A scope (wire `self._event_bus` and emit `issue.completed`) or to the Option B TODO list — leaving it unaddressed means some parallel-path completions are silently omitted from the event stream even with Option A applied to `_on_worker_complete` and `_merge_sequential`.

**`_on_worker_complete` context**: `self._event_bus` is already used in this method (lines 988–998) to emit `"parallel.worker_completed"` directly — confirming the bus is live and usable. Passing it to `close_issue()` is a one-liner addition.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store.py` — `_ISSUE_TRANSITION_MAP`: confirm that `undefer_issue()` emits `"issue.started"` (not `"issue.undeferred"`); `"issue.started": "in_progress"` is already in the map but `"issue.undeferred"` is **absent** — if the wrong string is used, `_derive_transition` produces `"undeferred"` (non-canonical) and breaks `scan_completed_issues_from_db()` queries [Agent 2 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. `scripts/little_loops/cli/sprint/run.py` — two sequential-path `process_issue_inplace(...)` calls lack `event_bus`; decide whether to plumb the bus through or document the silent-skip gap in the PR description; wiring it requires threading the local `event_bus` from the outer scope into both the single-issue wave block and the retry loop
2. `scripts/tests/test_issue_workflow_integration.py` — add `db_path=tmp_path / ".ll" / "history.db"` to `AutoManager(...)` constructor calls (lines ~87 and ~123) to prevent unexpected DB I/O in CI after the transport wiring change
3. `scripts/tests/test_cli_e2e.py` — add `test_ll_auto_wires_sqlite`: patch `little_loops.issue_manager.SQLiteTransport` and assert it is instantiated during `main_auto()`, modelled on `test_ll_parallel_wires_transports` (line 357)
4. `docs/ARCHITECTURE.md` — add `ll-auto` row to Extensions/Transports table (~line 512–517); note that `AutoManager` wires `SQLiteTransport` directly in `__init__`, not via `wire_transports()`
5. `docs/reference/EVENT-SCHEMA.md` — add `issue.skipped` and `issue.started` entries to the master event-type table (~lines 909–916) and add `### issue.skipped` / `### issue.started` section blocks
6. `docs/reference/API.md` — also fix pre-existing omissions: add `event_bus: EventBus | None = None` to `complete_issue_lifecycle` and `defer_issue` signature blocks (these have the param in code already)

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-24.

**Selected**: Option B (defer) — add TODO comments at parallel-path call sites

**Reasoning**: Option B scores 10/12 vs Option A's 8/12. The `_complete_issue_lifecycle_if_needed()` function at line 1196 is a local reimplementation of `complete_issue_lifecycle()` with its own `_git_lock`-based commit logic — passing `event_bus` there requires either an inline emit block or a deeper refactor, adding risk beyond ENH-1691's scope. Three existing `test_orchestrator.py` tests (lines 1566, 1817, 2346) remain valid without modification under Option B, and `self._event_bus` is already live at the site making the TODO a deliberate, traceable deferral.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (expand scope) | 2/3 | 2/3 | 2/3 | 2/3 | 8/12 |
| Option B (defer) | 1/3 | 3/3 | 3/3 | 3/3 | 10/12 |

**Key evidence**:
- Option A: `close_issue()` already accepts `event_bus` (reuse score 2), but `_complete_issue_lifecycle_if_needed()` at line 1196 is a local reimplementation requiring inline emit logic or refactoring — adds risk and complexity.
- Option B: `(ENH-NNN)` inline annotation convention already used throughout `_on_worker_complete()`; three existing `close_issue()` patch tests remain valid with no modification; TODO is a deliberate, traceable deferral.

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
Add new test methods for `undefer_issue` and `skip_issue` following the pattern of `test_close_issue_emits_event` at line 1175. Pattern: `received: list[dict] = []; bus = EventBus(); bus.register(lambda e: received.append(e))` — assert `len(received) == 1`, `event["event"] == "issue.undeferred"` / `"issue.skipped"`, `event["issue_id"]`, `event["ts"]`. Also add `test_no_emission_without_event_bus` for each (backward-compat, follows line 1312).

### `TestSummaryDbSource` companion (`test_issue_history_cli.py`)
Seed DB via live-write (not `backfill()`), assert `ll-history summary` returns data — exercises the cold-start acceptance criterion. Follow `TestSummaryDbSource` (line 139): DB placed at `project_root / ".ll" / "history.db"`, pass `--config project_root` to `main_history()`. Existing tests use `backfill()` for seeding; the new test seeds via `SQLiteTransport.send({"event": "issue.completed", ...})` directly or via `AutoManager` with `db_path=`.

### `test_issue_history_parsing.py` companion
Add test verifying `scan_completed_issues_from_db()` finds live-written rows; validates that `transition = 'done'` from `send()` matches the `WHERE transition = 'done'` query. Follow `TestScanCompletedIssuesFromDb` (line 438) — use `tmp_path` (not `:memory:`) consistent with all existing `SQLiteTransport` tests. Seed via `SQLiteTransport.send({"event": "issue.completed", "ts": "...", "issue_id": "ENH-1", ...})` rather than `backfill()`.

## Acceptance Criteria

- [ ] After `/ll:capture-issue` + status change, `ll-session recent --kind issue` shows the row without `ll-session backfill`
- [ ] `ll-history summary` works cold (no prior backfill) after issue lifecycle operations
- [ ] Running `ll-session backfill` after live writes does not duplicate rows
- [ ] Existing `ll-session backfill` path still works for fresh projects with no history
- [ ] Parallel path decision is explicit (wired or TODO-commented)
- [ ] All new and updated tests pass

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-24 (re-run after `/ll:decide-issue`)_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- **Sprint sequential path choice unresolved**: `cli/sprint/run.py` has two `process_issue_inplace()` calls (lines 360, 464) that will silently skip event emission after the change; make a deliberate in-PR decision (plumb `event_bus` through the local sprint scope, or add `# TODO(ENH-1686)` comments).
- **Test fixture side effects**: `test_issue_workflow_integration.py` constructs a real `AutoManager`; after transport wiring, tests will write a DB file unless `db_path=tmp_path / ".ll" / "history.db"` is added to constructor calls at lines ~87 and ~123 — apply this alongside the wiring change.
- **`_complete_issue_lifecycle_if_needed()` TODO scope**: orchestrator.py:1196 is an inline reimplementation not automatically covered by Option B TODOs on `_on_worker_complete` / `_merge_sequential`; confirm it gets a TODO annotation or is addressed in the PR description.

## Session Log
- `/ll:confidence-check` - 2026-05-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/35bbabac-1f2b-42ef-8053-1780201465c4.jsonl`
- `/ll:decide-issue` - 2026-05-25T01:03:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7745eb24-b502-4f62-a85c-2e699d8c21a0.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0719b6aa-570e-4737-9190-bda2db553e6d.jsonl`
- `/ll:wire-issue` - 2026-05-25T00:54:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dff803e6-0bfa-4001-a614-6606f8e05671.jsonl`
- `/ll:refine-issue` - 2026-05-25T00:47:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/37d51f7b-b713-4828-844a-8a05ffc3ff75.jsonl`
- `/ll:issue-size-review` - 2026-05-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/898f7f18-27df-4e97-81bc-d975051952e8.jsonl`
