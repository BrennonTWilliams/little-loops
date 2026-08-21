---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:44+00:00
discovered_by: scan-codebase
completed_at: '2026-07-25T04:55:07Z'
relates_to:
- ENH-1686
parent: EPIC-2791
confidence_score: 96
outcome_confidence: 75
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 15
score_change_surface: 20
status: done
priority: P3
---

# ENH-2783: Parallel/sprint issue-close events are not live-written to the history event bus

## Summary

ENH-1686 (done) added live-writing of issue-close events to `.ll/history.db`,
but the parallel-worker path (`ll-parallel`) and sprint sequential path
(`ll-sprint`) were left out — five `TODO(ENH-1686)` sites mark closures on
those paths that still bypass the live event write, so those closures only
appear in history after the next backfill.

## Location

- **File**: `scripts/little_loops/parallel/orchestrator.py`
- **Line(s)**: 1071, 1490, 1719 (at scan commit: fb567390)
- **Anchor**: `comment "# TODO(ENH-1686): parallel-path close events not yet live-written"`
- **Code**:
```python
        if result.should_close:
            from little_loops.issue_lifecycle import close_issue
            ...
            if info:
                # TODO(ENH-1686): parallel-path close events not yet live-written
                if close_issue(...):
```
- Also: `scripts/little_loops/cli/sprint/run.py` lines 646, 781
  (`# TODO(ENH-1686): sprint sequential path not yet live-written`).

## Current Behavior

Closures via `ll-parallel`/`ll-sprint` emit no live `issue_events` row;
history queries between the closure and the next backfill miss them.

## Expected Behavior

All five close sites emit the same live event write the single-issue path
uses, keeping `.ll/history.db` consistent regardless of orchestration entry
point.

## Proposed Solution

Extract the live-write call used by the ll-auto/single-issue close path into
a shared helper (or fold it into `close_issue` itself behind a flag) and
invoke it at the five TODO sites; remove the TODOs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

No extraction is needed — `close_issue()` (`scripts/little_loops/issue_lifecycle.py:648`)
already emits the live `issue.closed` event internally, gated purely on
whether a non-`None` `event_bus: EventBus | None = None` kwarg is passed in
(emit block at `close_issue():728-739`). The single-issue/`ll-auto` path
(`AutoManager.__init__()`, `issue_manager.py:1194-1203`) constructs
`self.event_bus = EventBus()` and unconditionally calls
`self.event_bus.add_transport(SQLiteTransport(self.db_path))` — regardless
of `events.transports` config — then threads it into
`process_issue_inplace(..., event_bus=self.event_bus)` →
`close_issue(..., event_bus=event_bus)`. The fix is call-site wiring, not a
new abstraction:

- **`orchestrator.py:1071`** (`_on_worker_complete`) and **`orchestrator.py:1490`**
  (`_merge_sequential`) both call `close_issue(...)` with `interceptors=None`
  and no `event_bus` kwarg — despite `ParallelOrchestrator` already owning
  `self._event_bus` (constructor param, `orchestrator.py:121`; already used
  to emit `parallel.worker_completed` at lines 1236-1246, closed via
  `self._event_bus.close_transports()` at 1825-1826). **Fix**: add
  `event_bus=self._event_bus` to both calls.
- **Critical gap `self._event_bus` alone won't close**: the bus that
  `cli/parallel.py:313-324` and `cli/sprint/run.py:741-749` construct and
  pass into `ParallelOrchestrator` is wired via
  `wire_transports(event_bus, config.events)`
  (`transport.py` — a `"sqlite"` branch exists at line ~651-654 and adds
  `SQLiteTransport(base / "history.db")`, but only if `"sqlite"` is
  explicitly listed in `config.events.transports`). `EventsConfig.transports`
  defaults to `[]` (`config/features.py:981`), so **by default the
  orchestrator's `event_bus` has no `SQLiteTransport` attached at all** —
  passing `event_bus=self._event_bus` into `close_issue()` would silently
  still write nothing to `issue_events` unless `events.transports` happens
  to include `"sqlite"`. To match the single-issue path's unconditional
  behavior, the fix must also `add_transport(SQLiteTransport(...))`
  unconditionally somewhere the orchestrator's bus is constructed (mirroring
  `AutoManager.__init__()`), not rely on config-driven `wire_transports`.
- **`orchestrator.py:1719`** (`_complete_issue_lifecycle_if_needed`) is a
  different shape than the other four sites — it never calls `close_issue()`
  or `complete_issue_lifecycle()` at all; it writes `status:` directly to
  frontmatter via `update_frontmatter()` and commits via
  `_stage_and_commit_issue_scoped()`. Threading `event_bus=` through here
  isn't enough — this site needs either (a) a manual
  `event_bus.emit({"event": "issue.closed", ...})` call (same shape as
  `close_issue()`'s emit block) at the point the frontmatter write succeeds,
  or (b) rerouting this function through `complete_issue_lifecycle()` in
  `issue_lifecycle.py` instead of its current inline logic.
- **`sprint/run.py:646`** (single-issue/contention-subwave sequential loop,
  calls `_run_issue_with_wall_clock_timeout()` at `run.py:48` →
  `process_issue_inplace()`) has **no `event_bus` in scope at all** — the
  local `event_bus = EventBus()` at `run.py:741` is constructed only inside
  the `else` branch for wave sizes > 1 (the `ParallelOrchestrator` branch),
  not reachable from the single-issue branch. This site needs its own
  `EventBus` + unconditional `SQLiteTransport` construction, threaded through
  `_run_issue_with_wall_clock_timeout()` into `process_issue_inplace(...,
  event_bus=...)` (which already accepts and forwards the kwarg,
  `issue_manager.py:581`).
- **`sprint/run.py:781`** (sequential retry-after-failure loop) is the
  simplest of the five: it runs in the same scope as the `event_bus`
  constructed at `run.py:741` for that wave's `ParallelOrchestrator`, so the
  fix is just adding `event_bus=event_bus` to the existing
  `process_issue_inplace(...)` call — provided that bus is also given the
  unconditional `SQLiteTransport` fix described above.

**Test pattern to follow**: `TestSQLiteTransportIssueEvents` in
`scripts/tests/test_session_store.py:934-999` asserts a `transport.send(...)`
call produces an `issue_events` row queryable via `recent(db, kind="issue")`;
an ENH-2783 test would drive this through `close_issue()`/
`process_issue_inplace()` with a real wired `EventBus`, or construct an
`Orchestrator`/sprint run with a wired bus and assert a row appears after
`_merge_sequential`/the worker-completion closure path runs.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — add `event_bus=self._event_bus`
  at `_on_worker_complete()` (line 1071) and `_merge_sequential()` (line
  1490); add manual `event_bus.emit(...)` or reroute through
  `complete_issue_lifecycle()` at `_complete_issue_lifecycle_if_needed()`
  (line 1719); ensure `self._event_bus` has an unconditional `SQLiteTransport`
  attached (currently only wired if `"sqlite"` is in `config.events.transports`,
  which defaults to `[]`)
- `scripts/little_loops/cli/sprint/run.py` — construct an `EventBus` +
  unconditional `SQLiteTransport` for the single-issue/contention-subwave
  branch (no bus in scope near line 646) and thread it through
  `_run_issue_with_wall_clock_timeout()` (line 48) into
  `process_issue_inplace(..., event_bus=...)`; add `event_bus=event_bus`
  (already in scope from line 741) to the retry-loop call at line 781
- `scripts/little_loops/cli/parallel.py` (lines 313-324) and
  `scripts/little_loops/cli/sprint/run.py` (lines 741-749) — where the
  orchestrator's `event_bus` is constructed via `wire_transports`; likely
  where the unconditional `SQLiteTransport` attach should live (mirroring
  `AutoManager.__init__()`, `issue_manager.py:1200-1201`)
- `scripts/little_loops/config-schema.json` — `events.sqlite.description`
  documents the `ll-auto`-only override precedent; extend to also name
  `ll-parallel`/`ll-sprint` once their issue-close events bypass
  `events.transports` (wiring pass finding)

### Reference Implementation (already working)
- `scripts/little_loops/issue_lifecycle.py:648` — `close_issue()`, emit block
  at lines 728-739
- `scripts/little_loops/issue_manager.py:1194-1203` — `AutoManager.__init__()`
  constructs `EventBus()` + unconditional `SQLiteTransport(self.db_path)`
- `scripts/little_loops/issue_manager.py:788-795` — `process_issue_inplace()`
  passes `event_bus=event_bus` into `close_issue()`

### Tests
- `scripts/tests/test_session_store.py:934-999` — `TestSQLiteTransportIssueEvents`,
  the pattern to model a new orchestrator/sprint-level assertion after
- `scripts/tests/test_orchestrator.py` — existing parallel orchestrator close
  scenarios (add coverage for `issue_events` row after
  `_on_worker_complete`/`_merge_sequential`)
- `scripts/tests/test_sprint_integration.py` / `scripts/tests/test_cli_sprint_commands.py`
  — existing sprint close scenarios (add coverage for `issue_events` row after
  sequential/retry closes)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — CLI entry-point table rows for `ll-parallel`/`ll-sprint`
  currently describe transport wiring as `wire_transports()`-only; the prose
  sentence right after the table singles out `AutoManager.__init__()` as the
  sole exception that wires `SQLiteTransport` unconditionally — both need
  updating to also cover `ll-parallel`/`ll-sprint` once this fix lands. The
  "Event Emitters" table row for `Parallel Orchestrator` doesn't yet list
  `issue.closed`.
- `docs/reference/CONFIGURATION.md` — the `### events.transports` section's
  "`ll-auto` exclusion" note (~line 1354) explains `ll-auto` bypasses the
  config-driven `sqlite` gate; extend it to note `ll-parallel`/`ll-sprint`
  issue-close events also bypass the gate post-fix (other transports stay
  config-gated).
- `scripts/little_loops/config-schema.json` — the `events.sqlite.description`
  field currently calls out only `ll-auto`'s unconditional `SQLiteTransport`
  wiring as the override precedent; extend the description to include
  `ll-parallel`/`ll-sprint` issue-close events.

### Tests (wiring-pass additions)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_orchestrator.py` — `test_merge_sequential_close` (~line
  3512) mocks `close_issue` with a bare `return_value=True` and doesn't assert
  on kwargs; add an assertion that `event_bus=orchestrator._event_bus` is
  forwarded so a future regression (dropped kwarg) is caught. Add a new
  `TestOrchestratorAlwaysWiresSqliteTransport`-style test combining the real
  `EventBus` + listener pattern from `test_on_worker_complete_emits_event_on_success`
  (~line 2596) with `TestSQLiteTransportIssueEvents`'s `recent(db, kind="issue")`
  assertion shape to prove an `issue_events` row lands after
  `_merge_sequential`/`_complete_issue_lifecycle_if_needed` regardless of
  `events.transports` config.
- `scripts/tests/test_sprint_integration.py` — `test_sprint_wires_transports_per_wave`
  (~line 497) only covers the multi-issue wave (`ParallelOrchestrator`) branch;
  it has zero coverage for the single-issue/sequential branch (`run.py` ~646)
  or the sequential-retry loop (~781) — the exact two ENH-2783 target sites.
  Add coverage for both using the same `MockOrchestrator`/`_setup_multi_wave_project`
  harness pattern.
- `scripts/tests/test_cli_e2e.py`, `scripts/tests/test_issue_workflow_integration.py`
  — both construct `ParallelOrchestrator` directly; verify their `db_path`/
  `.ll/history.db` fixtures are isolated per-test before this fix lands, since
  an unconditional `SQLiteTransport` attach means these tests will start
  producing real `issue_events` writes (test-isolation risk, not a signature
  break).

## Impact

- **Effort**: Medium
- One coherent piece of missing wiring across both orchestration entry
  points; closes the observability gap ENH-1686 intended to fix.

## Resolution

- **Action**: improve
- **Completed**: 2026-07-25
- **Status**: Completed
- **Implementation**: Wired `event_bus=self._event_bus` into the two `close_issue()`
  call sites in `parallel/orchestrator.py` (`_on_worker_complete`,
  `_merge_sequential`); added a manual `issue.closed` emit (mirroring
  `close_issue()`'s emit block) to `_complete_issue_lifecycle_if_needed()` for
  `terminal_status == "done"`; unconditionally attached `SQLiteTransport` to the
  orchestrator's `EventBus` in `cli/parallel.py` and to both the multi-issue-wave
  and single-issue/contention-subwave buses in `cli/sprint/run.py` (guarded
  against double-attach when `events.transports` already lists `"sqlite"`);
  threaded `event_bus=` through `_run_issue_with_wall_clock_timeout()` and the
  sequential-retry `process_issue_inplace()` call.

### Files Changed
- `scripts/little_loops/parallel/orchestrator.py`
- `scripts/little_loops/cli/parallel.py`
- `scripts/little_loops/cli/sprint/run.py`
- `scripts/little_loops/config-schema.json`
- `docs/ARCHITECTURE.md`
- `docs/reference/CONFIGURATION.md`
- `scripts/tests/test_orchestrator.py`
- `scripts/tests/test_sprint_integration.py`

### Verification Results
- `python -m pytest scripts/tests/test_orchestrator.py scripts/tests/test_sprint_integration.py scripts/tests/test_cli_sprint_commands.py scripts/tests/test_cli_e2e.py scripts/tests/test_issue_workflow_integration.py` — 248 passed
- `ruff check` on all changed source/test files — clean
- Full suite (`python -m pytest scripts/tests/`) has 7 pre-existing failures, all in a schema-version WIP diff (`session_store.py`/`test_session_store.py`) already dirty before this issue was started and unrelated to this change; confirmed by reproducing the same failures with all ENH-2783 changes stashed.

### Commits
- See git log for details

## Status

`open` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:manage-issue` - 2026-07-25T04:54:22Z - `d494ef59-295f-4e49-900a-1b0e766eb614.jsonl`
- `/ll:ready-issue` - 2026-07-25T04:41:01 - `e445108e-1e11-43b1-be66-ea4bd04fab6a.jsonl`
- `/ll:confidence-check` - 2026-07-24T22:31:44Z - `ed8da4a8-c2ae-4a63-b4bd-069f2b4ad8be.jsonl`
- `/ll:wire-issue` - 2026-07-25T04:38:02 - `9aaeea2e-5461-4919-b1c9-9d2523bc77a7.jsonl`
- `/ll:refine-issue` - 2026-07-25T04:32:06 - `a64709cc-d44d-494f-88ae-614c39e26300.jsonl`
- `/ll:scan-codebase` - 2026-07-24T22:41:56 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
