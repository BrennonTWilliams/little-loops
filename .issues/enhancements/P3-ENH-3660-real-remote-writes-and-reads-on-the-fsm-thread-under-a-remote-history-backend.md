---
id: ENH-3660
type: ENH
title: Real remote writes and reads on the FSM thread under a remote history backend
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T06:56:59Z'
blocked_by:
- BUG-3652
---

# ENH-3660: Real remote writes and reads on the FSM thread under a remote history backend

## Summary

BUG-3652 (3652a) stops remote-configured `ll-parallel`, `ll-sprint` and `ll-loop` from crashing under `history.backend.provider: libsql`. It deliberately leaves the FSM-thread executor writers and the prepatch read silently skipped (today's behavior). This issue turns them into real remote writes and reads, and adds the latency controls that requires. Split out of BUG-3652 after a third `/ll:advise` review (2026-09-29): crash fixes and new FSM-thread network latency should not ship together.

## Current Behavior

Under a remote backend with `LL_HISTORY_DB` unset, these sites pre-resolve through `resolve_history_db()` inside `try/except Exception: pass`, so they silently write nothing:

- `fsm/executor.py` `_finish` (`:4681`) — `record_loop_run_summary`.
- `fsm/executor.py` (`:4700`-`:4730`) — `record_usage_event`, called once per collected `TokenUsage` in a loop. `_usage_events_collected` gets one entry per action invocation (`:2776`, `:3936`), not per state, so a long run holds hundreds of rows. Each row opens its own telemetry connection and costs one Hrana POST.
- `fsm/executor.py` (`:2689`) and `runner_spec.py:_run_cmd` (`:326`) — `write_credential_scope`.
- `fsm/executor.py:_check_prepatch_check` (`:2017`) and `work_verification.py:_run_non_fsm_prepatch_check` (`:280`) — `read_base_sha` / `read_base_dirty`. BUG-3652 makes these skip to the `base_branch` fallback on a `RemoteTarget`.

## Expected Behavior

Remote users' `loop_runs`, `usage_events` and `credential_scope_events` rows reach the remote store. Prepatch reads the stamped base SHA remotely. None of this can stall the FSM thread for more than the telemetry budget against a dead or slow endpoint.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

- **Batched usage events.** Add `record_usage_events(db, rows)` in `session_store/writers.py`: one `_connect_telemetry`, a chunked multi-row INSERT (about 200 rows per statement; 17 params × 200 is well under SQLite's variable limit). Request count becomes ceil(K/200) plus `check_access`, and one transaction locally. Switch the executor's loop to it. Do not drop the `usage_events` pre-resolve without this.
- **Executor `_finish` and credential-scope writes.** Drop the `resolve_history_db()` pre-resolve; pass `resolve_history_store()` once (loop summary + usage batch) or `DEFAULT_DB_PATH` (one-shot `write_credential_scope`, `runner_spec._run_cmd`, following `advisor.py:512`). Keep the `except Exception` guards. `SQLiteTransport()` equivalence to the old pre-resolve was verified in BUG-3652 review (both resolve from cwd, absolute locally).
- **Prepatch remote read.** The readonly read (`history_reader/_base.py:_connect_readonly`, `ensure=True`) uses the 10 s `DEFAULT_TIMEOUT_S`, ignores the unreachable marker and does not `mark_unreachable` on failure. A caller-side `unreachable_active` guard therefore only helps if another write already set the marker, and `events.transports` defaults to `[]`, so a dead endpoint would stall every prepatch check about 10 s. Add a telemetry-budgeted, breaker-participating readonly open (overlaps ENH-3657's reader-layer work; coordinate), then call `read_base_sha(issue_id)` / `read_base_dirty(issue_id)` with the default `db`; `HistoryError` -> `None`.
- **Latency criteria.** Measure the per-write request counts against `HranaStub` and pin them (estimates from BUG-3652: loop event 2, issue event with snapshot 5, credential scope 1, loop summary TBD, plus one `check_access` per verification TTL).

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- [ ] Under the Hrana stub, a loop run's `loop_runs`, `usage_events` and `credential_scope_events` rows arrive (a silently disabled sink does not pass).
- [ ] `record_usage_events` issues ceil(K/chunk) statement requests plus verification for K rows; local behavior is byte-identical to K single writes.
- [ ] Slow-but-alive stub (`telemetry_timeout_ms=200`, 50 ms per-request delay): each write kind issues its pinned request count and wall time ≤ count × (delay + 100 ms). A delay above the budget trips the unreachable marker.
- [ ] Dead endpoint (`remote.stop()`, `telemetry_timeout_ms=200`): `_finish` completes in under ~3 s regardless of K; no `Traceback`, no auth-token sentinel in stderr.
- [ ] Under the stub with a stamped `orchestration_runs` row, the prepatch check's `base_source` is the stamped SHA; against a dead endpoint the first read takes ≤ the telemetry budget and marks the endpoint unreachable, later reads skip without a network call.
- [ ] Local-provider twin unchanged. `python -m pytest scripts/tests/` passes.

## Related

- BUG-3652 — the crash fixes; land it first (this issue depends on its `RemoteTarget` type widening and meta-test allowlist entries for the deferred executor sites).
- BUG-3659 — introduces `_DEGRADE_ERRORS`.
- ENH-3657 — reader CLIs; shares the reader-layer remote-read work.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-29 | Priority: P3
