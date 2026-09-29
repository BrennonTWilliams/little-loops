---
id: BUG-3652
type: BUG
title: Audit resolve_history_db callers under a remote history backend
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T04:19:08Z'
---

# BUG-3652: Audit resolve_history_db callers under a remote history backend

## Summary

Under `history.backend.provider: libsql` (FEAT-3535), `resolve_history_db()` raises `HistoryBackendNotLocal` for the default location because a remote store has no local path. FEAT-3535 converted the event writers and hooks (which open through the target-aware `schema.connect` seam), but about 49 other call sites outside `session_store/` still call it. Nobody audited whether each sits inside a best-effort guard, so a remote-configured `ll-parallel`, `ll-sprint` or `ll-loop` run may fail at startup instead of degrading.

## Current Behavior

`resolve_history_db()` raises `HistoryBackendNotLocal` (a `HistoryUnsupported` subclass) when `history.backend` selects a remote provider and the path is default-shaped with `LL_HISTORY_DB` unset. Callers that do not catch it propagate the error. Call sites by file (counts from `grep "resolve_history_db("` outside `session_store/`): `cli/history.py` (8), `cli/harness.py` (5), `parallel/orchestrator.py` (4), `fsm/executor.py` (4), `parallel/worker_pool.py` (3), `cli/sprint/run.py` (3), `parallel/merge_coordinator.py` (2), `cli/loop/run.py` (2), `cli/logs.py` (2), `cli/doctor.py` (2, already remote-aware), and one each in `workspace.py`, `work_verification.py`, `user_messages.py`, `transport.py`, `runner_spec.py`, `mcp_server/tools.py`, `fsm/continuity.py`, `decisions.py`, `cli/parallel.py`, `cli/issues/set_status.py`, `cli/issues/research_triage.py`, `cli/ctx_stats.py`, `issue_history/workspace_quality.py`, `history_reader/_base.py`.

## Expected Behavior

Every caller either reaches the remote store correctly (a history read or write routed through `resolve_history_store` or the target-aware `schema.connect` seam), is guarded so a remote target degrades to "skip" for best-effort telemetry, or raises a clear `HistoryUnsupported` for an operation the remote store does not support. No `ll-*` startup path fails with an unhandled `HistoryBackendNotLocal`.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Audit each call site and classify it: (a) history read or write, so convert to `resolve_history_store` or pass the default-shaped path through the seam; (b) best-effort telemetry, so guard and skip on a remote target; (c) a local-file operation, so raise `HistoryUnsupported` naming the operation via `refuse_on_remote`. Add a test that drives `ll-parallel`, `ll-sprint` and `ll-loop` startup under the Hrana stub backend.

## Integration Map

### Files to Modify
- The call sites listed above.

### Dependent Files
- `scripts/little_loops/session_store/db.py` (`resolve_history_db`, `resolve_history_store`, `resolve_history_target`)
- `scripts/tests/hrana_stub.py` (test double)

### Tests
- New test module driving the three orchestrators under the remote stub; existing `test_remote_hooks.py` shows the fixture shape.

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P3. Affects only opt-in remote-backend users, but a startup failure in a main orchestrator is severe for them.
- **Effort**: Medium.
- **Risk**: Low; local SQLite behavior must stay byte-identical (`resolve_history_store` returns a plain `Path` for a local store).

## Steps to Reproduce

1. Configure `history.backend.provider: libsql` with a reachable endpoint (or the `tests/hrana_stub.py` double).
2. Run `ll-parallel`, `ll-sprint run` or `ll-loop run` with `LL_HISTORY_DB` unset.
3. Observe whether startup fails at a `resolve_history_db()` call.

## Acceptance Criteria

- [ ] Every non-`session_store/` caller of `resolve_history_db()` is classified and either routed, guarded or refused with a named `HistoryUnsupported`.
- [ ] `ll-parallel`, `ll-sprint` and `ll-loop` start under a remote (Hrana stub) backend without an unhandled `HistoryBackendNotLocal`.
- [ ] With the default local store, `python -m pytest scripts/tests/` passes unchanged.

## Related

- FEAT-3535 (remote libSQL history backend); see its Deviations and Resolution sections.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-29 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-29T04:19:18 - `4d45d755-73ff-4de3-8bd1-bb8e866143f2.jsonl`
