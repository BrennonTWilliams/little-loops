---
id: ENH-3682
type: ENH
title: Budget best-effort remote prepatch history reads
priority: P4
status: open
relates_to:
- BUG-3652
- ENH-3668
- ENH-3657
- ENH-3700
blocked_by:
- ENH-3677
- ENH-3720
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T01:30:56Z'
parent: EPIC-3693
epic: EPIC-3693
---

# ENH-3682: Budget best-effort remote prepatch history reads

## Summary

Bound the remote advisory reads used by FSM prepatch (`read_base_sha` and `read_base_dirty`) and reuse the remote unreachable marker. This independent latency fix was split from ENH-3668's larger typed-reader work.

## Current Behavior

BUG-3652 made the two prepatch reads remote-aware through relative `DEFAULT_DB_PATH`. They use the standard readonly path with `ensure=True`; a black-holed endpoint can hold the FSM thread for about 10 seconds per read, and these reads do not set the telemetry unreachable marker. A stopped stub fails immediately and does not test the stall.

## Ordering and Exception Contract (revised 2026-10-04)

**Dependencies:** ENH-3677 supplies the hoisted `remote` fixture; ENH-3720 supplies the shared monotonic `Deadline` and strict read-only backend/transport enforcement. Land this integration after both. Do not reimplement cumulative request budgeting in this issue.

**Soft sequencing:** prefer integration after ENH-3700 so tests use the final `_connect_readonly` guard/read-mode contract; no functional dependency on ENH-3700 or ENH-3657 is added. ENH-3700 owns the central remote-local guard, its narrowed re-raise, shared read-stamp policy and ordinary read-mode ensure; ENH-3657 owns the CLI refusal boundary. Preserve ENH-3720's optional `deadline=` plumbing and no-deadline defaults when rebasing the common seams.

**Exception policy:** the best-effort path skips remote ensure/migration, verifies with the shared `check_access(write=False)` policy, and catches `HistoryError`/`sqlite3.Error` at both open and query/fetch boundaries. The open helper cannot catch a later query failure. Behind/ahead stamped stores and read-only tokens remain readable when supported by that policy; foreign/access-policy refusals degrade on `HistoryUnsupported`. Do not duplicate ENH-3700's missing-stamp predicate here or assert that the currently unchanged policy already rejects unstamped reads. The prepatch readers keep their documented `None` fallback regardless of the ambient reader mode; a guard refusal also degrades without opening a shadow local store.

## Expected Behavior

Best-effort prepatch reads share one cumulative `history.backend.telemetry_timeout_ms` deadline across access verification and the data query, skip remote ensure/migration, and return `None` on an unavailable endpoint. On a cold connection `_guard` verification and the query are separate HTTP requests: giving each a fresh timeout is insufficient. Construct one connection-lifetime `Deadline` from the telemetry timeout at entry to the best-effort remote opener and pass it to ENH-3720's read-only connection machinery. Reuse its verification/query/socket enforcement and documented DNS/CPU limits; do not add another timer or automatic retry. Do not send the query after verification consumes the budget. The first timeout sets the file-backed unreachable marker; another advisory read while it is active makes no request. Other history reads retain existing timeout/errors; local behavior is unchanged.

The deadline is per reader invocation/connection: verification and its data query share one budget, not one budget each. The two separate SHA/dirty calls do not share a new FSM-wide timer; the endpoint marker suppresses the second call after the first timeout. Successful calls may each consume their own budget.

Explicit `best_effort=True` wins over any ambient reader mode: both open and mid-query `HistoryError`/`sqlite3.Error` return `None`. `strict_reads()` is planned only by deferred ENH-3668; do not introduce it or require that deferred issue to implement this fix. Add the nesting/restoration test if that API exists when implementing, otherwise record this precedence for its future integration. The marker is the existing endpoint-scoped TTL file, shared across processes; no replacement cache or new configuration is needed.

Mark unreachable on timeout/unavailability at verification **or** data request, before returning `None`; a normal empty row, schema/query error or project-policy refusal must not create an outage marker. Suppression applies only to telemetry/best-effort consumers, and ordinary explicit reads ignore it. Test a second reader and a fresh process observing the same marker, TTL expiry followed by recovery, and unchanged standard-reader behavior. Use fixed operation/category warnings without raw exception/endpoint/token/SQL text in `_connect_readonly` and `runs._log_query_failure`; this applies even if ENH-3700 lands later.

## Motivation

Base-SHA/dirty-state history is advisory to prepatch. A slow remote store should not delay an FSM step twice when the same step can continue using its existing branch/merge-base fallback.

## Proposed Solution

Add `open_history_readonly(..., best_effort: bool = False)` and a remote `LibsqlBackend.connect_readonly_telemetry` path. For `RemoteTarget` plus `best_effort=True`, create one `Deadline.after(telemetry_timeout_ms / 1000.0)`, skip `ensure_schema`, and use a read-only connection built on ENH-3720's deadline plumbing plus the existing telemetry marker policy. Do not route reads through writable `connect_telemetry`. The existing helper returns `None` on opening failures; each prepatch reader separately catches query/fetch failures and returns `None`. Set `best_effort=True` only in the two prepatch readers. `telemetry_scope()` alone is insufficient because `open_history_readonly` does not consult it. Keep the relative default path so backend config is resolved normally and no shadow local database is created.

## Scope Boundaries

- **In scope:** only `read_base_sha` and `read_base_dirty`, the best-effort readonly connection seam, timeout/marker tests and API docs.
- **Out of scope:** ENH-3720's deadline primitive, socket enforcement and SQLite adapters; typed-target propagation to user-facing reader CLIs/MCP (ENH-3668); all other reader timeouts, remote migrations, new retries, and changes to prepatch fallback decisions.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/backend.py` — best-effort branch in `open_history_readonly`; preserve the local and ordinary-reader branches.
- `scripts/little_loops/session_store/libsql.py` — proposed readonly telemetry connection that consumes ENH-3720's `Deadline` and adds existing marker/cache policy.
- `scripts/little_loops/history_reader/_base.py` — narrow best-effort parameter and open-error fallback.
- `scripts/little_loops/history_reader/runs.py` — opt in only `read_base_sha`/`read_base_dirty`; enforce query/fetch fallback separately from opening fallback and sanitize the remote branch of `_log_query_failure` while retaining local diagnostics.
- `scripts/tests/test_remote_callers_bug3652.py` and `scripts/tests/test_remote_ingestion_telemetry.py` — focused prepatch deadline/marker/mode tests, using ENH-3677's shared fixture and ENH-3720's fault controls.
- `docs/reference/API.md` — best-effort opener/reader contract. `scripts/little_loops/session_store/hrana.py` is consumed unchanged; transport enforcement belongs to ENH-3720.

### Similar Patterns and Configuration

- Reuse the existing telemetry timeout and unreachable marker from the remote writer connection. No new config key or schema migration.

## Program Design

### Types

- `Deadline` — import the connection-lifetime value supplied by ENH-3720; no second budget type or config setting.

### Signatures

- `open_history_readonly(target=None, *, ensure: bool = False, best_effort: bool = False)` — keeps the default standard read behavior.
- `_connect_readonly(db_path, *, best_effort: bool = False)` — forwards the mode, preserves any narrow local-target provenance added by ENH-3700, and catches open failures only. Its exception order must return `None` for explicit best-effort before ENH-3700's ordinary `HistoryRemoteRefused` re-raise.
- `LibsqlBackend.connect_readonly_telemetry(target: Path | HistoryTarget, *, deadline: Deadline) -> LibsqlConnection` — proposed new read-only telemetry seam, given the one deadline created by the opener; marker/cache policy extends the existing strict read-only enforcement.

### Call Path

`history_reader.runs.read_base_sha` / `read_base_dirty` → `_connect_readonly(..., best_effort=True)` → `open_history_readonly(..., best_effort=True)` → bounded remote readonly query or `None` fallback. A local target follows the existing local path.

## Implementation Steps

1. After ENH-3677 and ENH-3720, implement the opt-in readonly telemetry connection and marker policy using the existing shared deadline/transport enforcement. Construct the deadline once before remote advisory work; skip ensure/migration.
2. Enable it at only the two prepatch reads. Preserve the existing `None` fallback on open and mid-query errors.
3. Test with a socket that accepts but never replies, plus a local twin; update API docs and run the suite.

## Impact

- **Priority:** P4 — an opt-in remote backend can delay an advisory FSM step.
- **Effort:** Small/Medium — one connection seam and two callers; uses the ENH-3677 `remote` fixture.
- **Risk:** Medium — timeout or marker behavior must not leak into normal reads.
- **Breaking Change:** No.

## Acceptance Criteria

- [ ] A black-holed-socket test shows each prepatch read returns `None` within the configured telemetry timeout budget, sets the unreachable marker, and sends no new request while that marker is active.
- [ ] Cold and warm verification-cache tests consume one ENH-3720 `Deadline`: cold success makes two POSTs, warm success one, a marker-suppressed read zero, and verification consuming the budget prevents the data POST. A slow verification followed by a stalled/trickling query cannot consume two budgets; use the prerequisite's named small scheduling tolerance and fault controls.
- [ ] Explicit best-effort returns `None` on open/mid-query/guard failure; standard readers retain their timeout/error policy. If deferred ENH-3668's ambient strict API is present, test nesting/restoration and best-effort precedence; otherwise no strict-reader implementation is required.
- [ ] Both readers still return actual remote data through a reachable `HranaStub`; local SQLite and standard reader timeouts remain unchanged.
- [ ] Separate open-error and query/fetch-error tests preserve each reader's never-raises/`None` fallback. Injected shared access-policy `HistoryUnsupported` degrades; behind/ahead stamped stores and read-only tokens use read-mode verification rather than write-mode ensure. This issue does not duplicate or depend on ENH-3700's stamp-policy implementation. Default remote reads create no shadow DB.
- [ ] Verification/query timeout sets the existing marker; second-reader/fresh-process suppression sends zero requests; TTL expiry permits recovery. Empty rows and policy/query errors do not mark the endpoint down, and ordinary explicit reads ignore the advisory marker. Captured logs/stderr contain no raw exception/endpoint/token/SQL canaries.
- [ ] Regression tests for `HistoryUnsupported` degradation remain valid before and after ENH-3700's `_connect_readonly` guard/read-mode changes; explicit best-effort never re-raises the guard's own refusal.
- [ ] `python -m pytest scripts/tests/` passes; the new API behavior is documented.

## Related

- ENH-3677 (shared fixture) and ENH-3720 (shared deadline), both prerequisites; ENH-3700 (shared reader policy/seam, prefer integration first); BUG-3652 (done), ENH-3668 (deferred strict-reader feature; not a prerequisite), FEAT-3535 (remote backend).

## Related Key Documentation

- `docs/reference/API.md` (history reader and backend opener), `docs/reference/CONFIGURATION.md` (remote timeout).

## Confidence Check Notes

_Updated 2026-10-04 after the deadline ownership review._

Prior 86/72 scores were cleared: the old plan omitted cumulative cold verification/query latency. Implementation remains blocked by ENH-3677 and ENH-3720. Re-run `/ll:confidence-check` after both prerequisites; prove consumption of the shared deadline, readonly telemetry policy, explicit best-effort precedence and the file-backed marker with the planned cold/warm/black-hole tests. Prefer integration after ENH-3700, without adding a functional dependency.

## Status

**Open** | Created: 2026-09-30 | Priority: P4

## Review Notes

Revised 2026-10-04 to consume ENH-3720's shared deadline rather than duplicate transport work. The previous appended scope correction is incorporated into the ordering/exception contract above: ENH-3700 owns read-mode verification and guard policy; ENH-3657 does not change that helper contract. Reader opening and query/fetch degradation are separate acceptance obligations.

## Session Log
- EPIC-3693 pre-implementation review + `/ll:advise` (claude-opus-5-5, user_requested) - 2026-10-04 - guard ownership, per-invocation deadline, marker recovery/scope and safe best-effort diagnostics clarified; deferred strict API removed as a required gate
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:04 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
- `/ll:confidence-check` - 2026-09-30T05:10:31 - `defb8cbc-fb4d-4d9b-9b95-eac7264d3124.jsonl`
