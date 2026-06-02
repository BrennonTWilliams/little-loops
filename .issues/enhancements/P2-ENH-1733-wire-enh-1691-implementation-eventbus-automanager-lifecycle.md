---
id: ENH-1733
type: ENH
priority: P2
status: done
parent: ENH-1691
discovered_date: 2026-05-26
completed_at: 2026-05-27 01:02:21+00:00
labels:
- enhancement
size: Large
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
decision_needed: false
---

# ENH-1733: Wire EventBus to AutoManager and Lifecycle Functions (ENH-1691 Implementation)

## Summary

Implement the source-code and test changes from ENH-1691: add `event_bus` param to `undefer_issue()` and `skip_issue()`, thread `event_bus` through `process_issue_inplace()`, wire `SQLiteTransport` in `AutoManager.__init__()`, add TODO annotations for the parallel orchestrator path, decide the sprint sequential path, and add all accompanying integration and unit tests.

## Parent Issue

Decomposed from ENH-1691: Wire Issue Lifecycle EventBus to SQLiteTransport

## Current Behavior

`AutoManager`, `process_issue_inplace()`, `skip_issue()`, and `undefer_issue()` do not pass `event_bus` to lifecycle functions, so skip, undefer, and complete operations are not live-written to SQLite. Issue history is only available after running `ll-session backfill`.

## Expected Behavior

`AutoManager` wires `SQLiteTransport` at init time, all lifecycle operations emit events live to `.ll/history.db`, and `ll-session recent --kind issue` returns rows immediately after any `ll-auto` run — no `backfill()` required.

## Current Pain Point

Issue lifecycle events from `ll-auto` runs are not live-written to SQLite. Users must run `ll-session backfill` after each run, breaking workflows that depend on real-time event queries (e.g., downstream loop triggers, session analytics).

## Impact

- **Priority**: P2 — required to complete ENH-1691 live-write coverage for `ll-auto`
- **Effort**: Large (4 source files + 6 test files; all changes are additive optional params)
- **Risk**: Low-moderate — backward-compatible; callers without `event_bus` are unaffected

## Scope

Covers Steps 1, 2, 3, 8 from ENH-1691's Implementation Steps plus Wiring Phase items 1–3.

**In scope**:
- `issue_lifecycle.py` — `undefer_issue()` (line 832), `skip_issue()` (line 785): add `event_bus: EventBus | None = None` param + emit `issue.started` / `issue.skipped` following `close_issue()` pattern
- `issue_manager.py` — add `event_bus: EventBus | None = None` to `process_issue_inplace()` (line 453) signature; thread through to all lifecycle call sites inside that function; `AutoManager.__init__()` (line 947): wire `SQLiteTransport(DEFAULT_DB_PATH)` + add optional `db_path: Path | None = None` param; `AutoManager._process_issue()` (line 1217): pass `self.event_bus`
- `parallel/orchestrator.py` — Option B: add `# TODO(ENH-1686)` comments at `_on_worker_complete()` (line 920), `_merge_sequential()` (line 1032), `_complete_issue_lifecycle_if_needed()` (line 1196) call sites
- `cli/sprint/run.py` — make explicit decision: plumb `event_bus` through or add `# TODO(ENH-1686)` at the two `process_issue_inplace()` call sites (lines ~360, ~464)
- Tests:
  - `test_issue_lifecycle.py` — `TestEventBusEmission`: add `test_undefer_issue_emits_event`, `test_skip_issue_emits_event`, `test_no_emission_without_event_bus` for each, following `test_close_issue_emits_event` (line 1175) / `test_no_emission_without_event_bus` (line 1312) patterns
  - `test_issue_manager.py` — integration test: `AutoManager` with `db_path=tmp_path/"session.db"`, call `close_issue()`, assert `issue_events` row exists without `backfill()`
  - `test_issue_history_cli.py` — `TestSummaryDbSource` variant seeded via `SQLiteTransport.send()` instead of `backfill()`
  - `test_issue_history_parsing.py` — `TestScanCompletedIssuesFromDb` variant: seed via live-write, assert `scan_completed_issues_from_db()` finds rows
  - `test_issue_workflow_integration.py` — add `db_path=tmp_path / ".ll" / "history.db"` to `AutoManager(...)` calls at lines ~87 and ~123 to prevent unexpected CI DB I/O
  - `test_cli_e2e.py` — add `test_ll_auto_wires_sqlite`: patch `little_loops.issue_manager.SQLiteTransport`, call `main_auto()`, assert `call_count == 1` (model on `test_ll_parallel_wires_transports` line 357)
  - `test_orchestrator.py` — if Option A chosen for parallel path: add assertions that `self._event_bus` is passed; Option B: no changes needed
  - `test_session_store.py` — run `TestDeriveTransition.test_known_mappings` (line 538) and `TestSQLiteTransportIssueEvents.test_issue_event_transition_mapping` (line 576) as correctness guard after Step 1 (no edits, just verify pass)

**Out of scope**: Documentation updates (ENH-1734), transport-layer changes (ENH-1690 — already done), schema migrations.

## Implementation Steps

### Step 1 — `issue_lifecycle.py`: add `event_bus` to `undefer_issue()` and `skip_issue()`

Follow the emit pattern in `close_issue()` (line 517):
```python
if event_bus is not None:
    event_bus.emit({"event": "issue.started", "issue_id": ..., "ts": ...})
```
Use `"issue.started"` for `undefer_issue()` (maps to `in_progress` via `_ISSUE_TRANSITION_MAP`).
Use `"issue.skipped"` for `skip_issue()` (maps to `cancelled`).

Run `test_session_store.py::TestDeriveTransition::test_known_mappings` as a guard after this step.

### Step 2 — `issue_manager.py`: thread `event_bus` through `process_issue_inplace()`

`process_issue_inplace()` at line 453 is a module-level function — Steps 2 as written in ENH-1691 will not compile. Correct approach:
1. Add `event_bus: EventBus | None = None` to `process_issue_inplace()` signature
2. Thread through to call sites at lines 658, 832, 889, 899 inside that function
3. Update `AutoManager._process_issue()` (line 1217) to pass `self.event_bus`

### Step 3 — `issue_manager.py`: wire `SQLiteTransport` in `AutoManager.__init__()`

```python
from little_loops.session_store import SQLiteTransport, DEFAULT_DB_PATH

# in __init__:
self.event_bus = EventBus()
self.event_bus.add_transport(SQLiteTransport(db_path or DEFAULT_DB_PATH))
```

Add `db_path: Path | None = None` parameter. Call `close_transports()` on teardown. Follow `scripts/little_loops/cli/loop/run.py:352–355`.

### Step 8 — `parallel/orchestrator.py`: parallel path decision (Option B)

Add `# TODO(ENH-1686): parallel-path close events not yet live-written` at:
- `_on_worker_complete()` line 920 — `close_issue()` call site
- `_merge_sequential()` line 1032 — `close_issue()` call site
- `_complete_issue_lifecycle_if_needed()` line 1196 — note it is a local reimplementation with its own git-lock logic

### Sprint Path — `cli/sprint/run.py`

Decide explicitly at lines ~360 and ~464 (`process_issue_inplace()` calls in the sequential single-issue wave block and retry loop):
- Option A: plumb `event_bus` from outer scope through both calls
- Option B: add `# TODO(ENH-1686): sprint sequential path not yet live-written` comments

> **Selected:** Option B (TODO comments) — defers sprint sequential-path event coverage to ENH-1686; avoids constructing a new EventBus inside the out-of-scope single-issue `if` branch

Document the decision in PR description.

> **Scope note (added by `/ll:wire-issue`):** If choosing Option A, the `event_bus` local variable constructed at line 424 is inside the multi-issue `else:` branch — it is NOT in scope at lines 360 and 464, which are in the single-issue `if:` branch. Option A requires either (a) constructing a separate `EventBus()` + `SQLiteTransport` within the single-issue branch, or (b) hoisting the `EventBus` construction above the `if len(wave) == 1` guard. Option B (TODO comments) avoids this scoping complexity entirely.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-26.

**Selected**: Option B — add `# TODO(ENH-1686): sprint sequential path not yet live-written` comments

**Reasoning**: The `event_bus` local variable at sprint/run.py:424 is inside the multi-issue `else:` branch and is not accessible from the single-issue `if` branch at line 360. Option A requires either hoisting the EventBus construction above line 353 or creating a separate bus in the single-issue branch — both add structural complexity without immediate user-facing benefit. Option B is consistent with Step 8's parallel-path deferral treatment and carries zero behavioral risk while tracking the coverage gap in ENH-1686.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (plumb event_bus) | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |
| Option B (TODO comments) | 2/3 | 3/3 | 3/3 | 3/3 | 11/12 |

**Key evidence**:
- Option A: `event_bus` at sprint/run.py:424 is scoped to the `else:` branch; line 360 (single-issue `if` branch) has no bus in scope — structural hoisting required; `process_issue_inplace()` also lacks an `event_bus` param today
- Option B: consistent with Step 8's parallel-path deferral to ENH-1686; introduces the intentional `# TODO(ENH-NNNN):` notation for deferred transport coverage with no behavioral change

## Integration Map

### Files to Modify (Source)
- `scripts/little_loops/issue_lifecycle.py:785` — `skip_issue()`: add `event_bus: EventBus | None = None` + emit `"issue.skipped"` after move
- `scripts/little_loops/issue_lifecycle.py:832` — `undefer_issue()`: add `event_bus: EventBus | None = None` + emit `"issue.started"` on success path
- `scripts/little_loops/issue_manager.py:453` — `process_issue_inplace()`: add `event_bus: EventBus | None = None`; thread through to call sites at 658, 832, 889, 899
- `scripts/little_loops/issue_manager.py:947` — `AutoManager.__init__()`: add `db_path: Path | None = None`; wire `SQLiteTransport(db_path or DEFAULT_DB_PATH)` into existing `self.event_bus` (line 994)
- `scripts/little_loops/issue_manager.py:1162` — `AutoManager.run()` `finally:` block: add `self.event_bus.close_transports()`
- `scripts/little_loops/issue_manager.py:1217` — `AutoManager._process_issue()`: pass `self.event_bus` to `process_issue_inplace()` at line ~1240
- `scripts/little_loops/parallel/orchestrator.py:920,1032,1196` — add `# TODO(ENH-1686)` comments (Option B)
- `scripts/little_loops/cli/sprint/run.py:360,464` — wire or TODO-annotate `event_bus` on `process_issue_inplace()` calls

### New Import Required
- `scripts/little_loops/issue_manager.py` — add: `from little_loops.session_store import SQLiteTransport, DEFAULT_DB_PATH`

### Internal Call Sites to Thread (inside `process_issue_inplace`)
- Line 658: `close_issue(...)` — add `event_bus=event_bus`
- Line 832: `create_issue_from_failure(...)` — add `event_bus=event_bus` (`create_issue_from_failure` already has the param at `issue_lifecycle.py:413`)
- Line 889: `complete_issue_lifecycle(...)` — add `event_bus=event_bus`
- Line 899: `complete_issue_lifecycle(...)` — add `event_bus=event_bus`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/auto.py` — `main_auto()` constructs `AutoManager(config, ...)` at line 92; no code change needed (`db_path` defaults to `None`), but after ENH-1733 lands `ll-auto` will unconditionally write to `.ll/history.db` on every run [Agent 1]
- `scripts/little_loops/cli/issues/skip.py` — `cmd_skip()` calls `skip_issue(path, new_path, args.reason)` at line 60 without an `event_bus`; after ENH-1733 `ll-issues skip` will NOT write skip events to SQLite because the issues CLI has no `EventBus` in scope — this is a coverage gap, not a code-change blocker [Agent 2]
- `scripts/little_loops/__init__.py` — re-exports `undefer_issue`, `close_issue`, `complete_issue_lifecycle`, `create_issue_from_failure`; adding optional keyword params to these functions is backward-compatible, no changes required [Agent 1]

### Transition Map Coverage (Verified)
`session_store.py:309` — `_ISSUE_TRANSITION_MAP` already contains both new event types:
- `"issue.started"` → `"in_progress"` (line 315)
- `"issue.skipped"` → `"cancelled"` (line 313)
No new map entries needed.

### Test Files to Modify
- `scripts/tests/test_issue_lifecycle.py:1172` — `TestEventBusEmission`: add `test_skip_issue_emits_event`, `test_undefer_issue_emits_event`, `test_no_emission_without_event_bus` for each; follow `test_close_issue_emits_event` (line 1175) using `bus.register(lambda e: received.append(e))` pattern
- `scripts/tests/test_issue_manager.py` — add `AutoManager` integration test with `db_path=tmp_path/"session.db"`; call `close_issue()`; assert `issue_events` row exists without `backfill()`
- `scripts/tests/test_issue_history_cli.py:139` — `TestSummaryDbSource`: add live-write variant seeded via `SQLiteTransport.send()`
- `scripts/tests/test_issue_history_parsing.py:438` — `TestScanCompletedIssuesFromDb`: add variant with live-write seeding
- `scripts/tests/test_issue_workflow_integration.py:92,128` — add `db_path=tmp_path / ".ll" / "history.db"` to both `AutoManager(...)` calls
- `scripts/tests/test_cli_e2e.py:357` — add `test_ll_auto_wires_sqlite`; patch `little_loops.issue_manager.SQLiteTransport`; call `main_auto()`; assert `call_count == 1`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_manager.py` — beyond the integration test already planned, the following test classes construct real `AutoManager(config, ...)` without `db_path`: `TestDependencyAwareSequencing` (lines 513–626), `TestAutoManagerPriorityFilter` (675–723), `TestAutoManagerLabelFilter` (766–808), `TestAutoManagerQuietMode` (813–959), `TestAutoManagerRun` (2471+); when `SQLiteTransport` is wired in `__init__`, each will create `.db` files at `tmp_path/.ll/history.db`; add `db_path=tmp_path / ".ll" / "history.db"` to all these `AutoManager(...)` constructions to prevent unexpected CI DB I/O [Agent 3]
- `scripts/tests/test_issue_lifecycle.py` — `skip_issue()` has **zero** existing test coverage; `test_skip_issue_emits_event` will be its first test; add a companion `test_skip_issue_success` (basic behavior: file moves to correct path, no event_bus) in a new `TestSkip` class before writing the event variant [Agent 3]

## Similar Patterns

- `scripts/little_loops/cli/loop/run.py:371–387` — `wire_transports(executor.event_bus, _config.events)` + `executor.close_transports()` in `finally`
- `scripts/little_loops/transport.py:652–655` — `wire_transports()` SQLite branch (lazy import + `SQLiteTransport(base / "history.db")`)
- `scripts/little_loops/issue_lifecycle.py:594–603` — existing emit pattern in `close_issue()` (also `defer_issue()` at 751, `create_issue_from_failure()` at 408)
- `scripts/tests/test_transport.py:257–277` — `bus.close_transports()` before asserting DB: `test_sqlite_records_issue_event_end_to_end`
- `scripts/tests/test_session_store.py:558` — `TestSQLiteTransportIssueEvents.test_records_issue_completed_event` — direct `SQLiteTransport.send()` seeding pattern
- `scripts/tests/test_cli_e2e.py:357` — `test_ll_parallel_wires_transports` — model for `test_ll_auto_wires_sqlite` (`patch("little_loops.transport.wire_transports")` + `mock_wire.assert_called_once()`)

## Acceptance Criteria

- [ ] After AutoManager lifecycle operation, `ll-session recent --kind issue` shows row without `ll-session backfill`
- [ ] `ll-session backfill` after live writes does not duplicate rows
- [ ] All new and updated tests pass
- [ ] `test_issue_workflow_integration.py` passes without creating unexpected DB files in CI
- [ ] Parallel path decision is explicit (TODO-commented)
- [ ] Sprint path decision is explicit (wired or TODO-commented)
- [ ] `test_session_store.py` transition mapping tests pass unchanged

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-26_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- **Breadth across 10 sites**: 4 source files + 6 test files require coordinated changes; no single site is deep but scope requires disciplined threading — implement test_issue_workflow_integration.py AutoManager db_path additions early to prevent CI DB I/O from masking wiring failures
- **Open decision on sprint path**: Option A vs B in cli/sprint/run.py must be resolved during implementation; scope note from /ll:wire-issue favors Option B (avoids the single-issue branch scoping problem) but the choice is not locked in — document in PR description
- **Test file coordination**: 6 test files to modify including db_path additions to several existing AutoManager() constructions across multiple test classes; implement test_issue_workflow_integration.py fixes first

## Status

**Open** | Created: 2026-05-26 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-05-27T00:45:03 - `286197ae-98a9-4aa6-b5c5-d2963679ed9a.jsonl`
- `/ll:confidence-check` - 2026-05-26T12:00:00 - `8f67938c-cbb3-4914-bee5-0317a112a94e.jsonl`
- `/ll:decide-issue` - 2026-05-27T00:37:56 - `276b0668-a79f-456b-bedc-b6bd95271676.jsonl`
- `/ll:wire-issue` - 2026-05-27T00:26:54 - `5a2da53f-ade1-48e2-8a09-0e650fb19ad2.jsonl`
- `/ll:refine-issue` - 2026-05-27T00:20:38 - `21e49b9e-3c83-40d1-a35b-97b257dfb713.jsonl`
- `/ll:confidence-check` - 2026-05-26T00:00:00 - `d400ece7-07d5-43bb-8540-467d196b59b8.jsonl`
- `/ll:issue-size-review` - 2026-05-26T00:00:00Z - `0f138859-02cf-4887-806e-2fe090003148.jsonl`
