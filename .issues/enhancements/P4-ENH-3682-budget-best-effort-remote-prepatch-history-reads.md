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
- ENH-3720
blocked_by:
- ENH-3677
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T01:30:56Z'
parent: EPIC-3693
epic: EPIC-3693
blocks:
- ENH-3700
---

# ENH-3682: Budget best-effort remote prepatch history reads

## Summary

Bound the remote advisory reads used by FSM prepatch (`read_base_sha` and `read_base_dirty`) with ENH-3720's shared `Deadline`, and suppress repeat advisory reads after a timeout through a **read-scoped** unreachable marker that never silences telemetry writes. This independent latency fix was split from ENH-3668's larger typed-reader work. It also owns sanitizing `_connect_readonly`'s remote warning (ENH-3700 is `blocked_by` this issue).

## Current Behavior

BUG-3652 made the two prepatch reads remote-aware through relative `DEFAULT_DB_PATH`. They use the standard readonly path with `ensure=True`; a black-holed endpoint can hold the FSM thread for about 10 seconds per read (`ensure_schema` builds a client with the default timeout and no deadline), and these reads do not set any unreachable marker. A stopped stub fails immediately and does not test the stall. `_connect_readonly`'s remote `warn_once` embeds raw `{exc}` text, and `runs._log_query_failure` does the same for remote failures.

## Prerequisites (updated 2026-10-04)

- **ENH-3720 is done** (completed 2026-10-04): `session_store/deadline.py` (`Deadline`, `now()` fake clock), `deadline=` on every `connect_readonly` (`LibsqlBackend.connect_readonly(target, *, timeout, deadline=None)` builds a deadline-bound `HranaClient`; expiry raises `HranaUnavailable`), and default-off `HranaStub` controls (`delays`, `stall_body`, `trickle`, `trickle_part`). Do not reimplement cumulative budgeting.
- **ENH-3677** supplies the hoisted `remote` fixture.
- ENH-3700 is `blocked_by` this issue, so it lands afterwards; there is no guard re-raise to order against (ENH-3700 maps its guard refusal to `None`). Do not add a functional dependency in the other direction.

## Expected Behavior

For `RemoteTarget` plus `best_effort=True`, per reader invocation:

1. Check both markers first (write marker `remote_telemetry.unreachable_active` and the new read marker); if either is active, return `None` with **zero requests**.
2. Skip `ensure_schema` entirely. Build **one** `Deadline.after(telemetry_timeout_ms / 1000.0)` and use `LibsqlBackend.connect_readonly(target, deadline=deadline)` (read-only, deadline-bound; no automatic telemetry marking).
3. Verify access once with `remote_schema.check_access(client, cfg, write=True, persist=True)` on that deadline-bound client — the same policy as the ordinary `ensure=True` path, so behind/ahead/unstamped/foreign stores are refused with `HistoryUnsupported` and a read-only token still works (metadata SELECTs only) — and run the data query on the **same client without a second lazy verification** (do not leave the connection's lazy `_guard` to re-verify; it would not see a file-cached state). Cold: verification POST + data POST; warm file cache: data POST only; marker active: zero.
4. The first failure of kind timeout/connect/unavailable at verification **or** data request writes the **read-scoped** marker (same TTL and file location scheme as the write marker, distinct kind) before returning `None`. A normal empty row, schema/query error or project-policy refusal (`HistoryUnsupported`) must not create a marker.

**Why read-scoped (Opus 2026-10-04):** `LibsqlConnection._run` marks the shared write marker on any `HistoryUnavailable` when `telemetry=True`, and deadline expiry raises `HranaUnavailable`. A cumulative 1.5s budget (two POSTs cold) can expire on a slow-but-healthy endpoint where per-request writes succeed; marking the shared marker would then suppress all telemetry writes across processes for 60s. Best-effort reads therefore **read** both markers but **write only the read marker**. Writes consult only the write marker and are unaffected by a read timeout. (Alternative if the read marker proves awkward: introduce `HranaDeadlineExpired` and mark the shared marker only on zero-byte/connect failures.)

The deadline is per reader invocation/connection: verification and its data query share one budget. The two SHA/dirty calls do not share an FSM-wide timer; the read marker suppresses the second call after the first timeout. Successful calls each consume their own budget. Do not add another timer or automatic retry; use ENH-3720's documented DNS/CPU limits. Do not send the query after verification consumes the budget.

Explicit `best_effort=True` wins over any ambient reader mode: both open and mid-query `HistoryError`/`sqlite3.Error` return `None`. `strict_reads()` is planned only by deferred ENH-3668; do not introduce it. Add the nesting/restoration test only if that API exists when implementing, otherwise record this precedence for its future integration. Suppression applies only to best-effort consumers; ordinary explicit reads ignore both the read marker and this branch.

**Sanitized diagnostics (owned here only):** `_connect_readonly`'s remote warning and the remote branch of `runs._log_query_failure` use fixed operation/category text — no `str(exc)`, endpoint, token, SQL or `exc_info=True`. Local diagnostics stay unchanged.

## Motivation

Base-SHA/dirty-state history is advisory to prepatch. A slow remote store should not delay an FSM step twice when the same step can continue using its existing branch/merge-base fallback, and a slow advisory read must not cost the user their telemetry writes.

## Proposed Solution

Add `open_history_readonly(..., best_effort: bool = False)`. For `RemoteTarget` plus `best_effort=True`, follow Expected Behavior using existing primitives (`Deadline`, `LibsqlBackend.connect_readonly(deadline=)`, `check_access(..., persist=True)`, `remote_telemetry` markers) plus a small read-marker pair in `remote_telemetry` (e.g. `mark_read_unreachable` / `read_unreachable_active`, same TTL, cleared on a successful best-effort read). Do not route reads through writable `connect_telemetry`. The existing helper returns `None` on opening failures; each prepatch reader separately catches query/fetch failures and returns `None`. Set `best_effort=True` only in the two prepatch readers (`telemetry_scope()` alone is insufficient: `open_history_readonly` does not consult it). Keep the relative default path so backend config resolves normally and no shadow local database is created.

## Scope Boundaries

- **In scope:** `read_base_sha` and `read_base_dirty`, the best-effort readonly seam, the read-scoped marker, sanitized `_connect_readonly`/`_log_query_failure` remote text, timeout/marker tests and API docs.
- **Out of scope:** ENH-3720's deadline primitive, socket enforcement and stub controls (landed); typed-target propagation to user-facing reader CLIs/MCP (ENH-3668); all other reader timeouts, remote migrations, new retries, changes to prepatch fallback decisions; the central guard and catch widening (ENH-3700).

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/backend.py` — best-effort branch in `open_history_readonly`; preserve the local and ordinary-reader branches.
- `scripts/little_loops/session_store/remote_telemetry.py` — read-scoped marker kind and helpers.
- `scripts/little_loops/history_reader/_base.py` — narrow best-effort parameter, open-error fallback, sanitized remote warning.
- `scripts/little_loops/history_reader/runs.py` — opt in only `read_base_sha`/`read_base_dirty`; query/fetch fallback separate from opening fallback; sanitize the remote branch of `_log_query_failure`.
- `scripts/tests/test_remote_callers_bug3652.py` and `scripts/tests/test_remote_ingestion_telemetry.py` — focused prepatch deadline/marker/mode tests, using ENH-3677's shared fixture and ENH-3720's stub fault controls.
- `docs/reference/API.md` — best-effort opener/reader contract and read-scoped marker. `session_store/hrana.py` and `deadline.py` are consumed unchanged.

### Similar Patterns and Configuration

- Reuse `history.backend.telemetry_timeout_ms` and the marker TTL. No new config key or schema migration.

## Program Design

### Types

- `Deadline` — import the connection-lifetime value from `little_loops.session_store.deadline` (landed); no second budget type or config setting.

### Signatures

- `open_history_readonly(target=None, *, ensure: bool = False, best_effort: bool = False)` — keeps default standard read behavior.
- `_connect_readonly(db_path, *, best_effort: bool = False)` — forwards the mode, preserves the existing `db_path` handling (ENH-3700 later widens it to `Path | LocalTarget`), and catches open failures only.
- `remote_telemetry.mark_read_unreachable(endpoint: str) -> None` / `read_unreachable_active(endpoint: str) -> bool` — read-scoped marker (names indicative).

### Call Path

`history_reader.runs.read_base_sha` / `read_base_dirty` → `_connect_readonly(..., best_effort=True)` → `open_history_readonly(..., best_effort=True)` → marker check → deadline-bound `connect_readonly` → one `check_access` → query on the same client, or `None`. A local target follows the existing local path.

## Implementation Steps

1. After ENH-3677, add the read-marker helpers and the best-effort branch (one `Deadline`, marker check, skip `ensure_schema`, single verification, same-client query).
2. Enable it at only the two prepatch reads; keep the `None` fallback on open and mid-query errors; sanitize the remote warnings.
3. Test with a socket that accepts but never replies and ENH-3720's `delays` / `stall_body` / `trickle` controls, plus a local twin; update API docs and run the suite.

## Impact

- **Priority:** P4 — an opt-in remote backend can delay an advisory FSM step.
- **Effort:** Small/Medium — one best-effort seam, a marker pair and two callers.
- **Risk:** Medium — timeout or marker behavior must not leak into normal reads or silence writes.
- **Breaking Change:** No.

## Acceptance Criteria

- [ ] A black-holed-socket test shows each prepatch read returns `None` within the configured telemetry timeout budget, sets the **read** marker, and sends no new request while a marker is active.
- [ ] Cold and warm verification tests consume one ENH-3720 `Deadline`: cold success makes two POSTs, warm (file-cached) one, a marker-suppressed read zero, and verification consuming the budget prevents the data POST. A slow verification followed by a stalled/trickling query cannot consume two budgets (use the prerequisite's named small scheduling tolerance and fault controls). No duplicate lazy verification on the data query.
- [ ] **Deadline expiry on a responding (slow-but-healthy) endpoint does not suppress telemetry writes:** after a best-effort read times out and sets the read marker, a telemetry write to the same endpoint still issues its request; a write-side failure still suppresses best-effort reads.
- [ ] The best-effort branch never calls `ensure_schema` (no un-deadlined 10s client); it applies the same access policy as ordinary `ensure=True` (behind/ahead/unstamped/foreign refused via `HistoryUnsupported`, read-only token works) and `HistoryUnsupported` degrades to `None` without a marker.
- [ ] Explicit best-effort returns `None` on open/mid-query/guard failure; standard readers retain their timeout/error policy. If deferred ENH-3668's ambient strict API exists, test nesting/restoration and best-effort precedence; otherwise no strict-reader implementation is required.
- [ ] Both readers still return actual remote data through a reachable `HranaStub`; local SQLite and standard reader timeouts remain unchanged. Default remote reads create no shadow DB.
- [ ] Separate open-error and query/fetch-error tests preserve each reader's never-raises/`None` fallback.
- [ ] Verification/query timeout sets the read marker; second-reader/fresh-process suppression sends zero requests; TTL expiry (and a later success) permits recovery. Empty rows and policy/query errors do not mark the endpoint down, and ordinary explicit reads ignore the marker. Captured logs/stderr contain no raw exception/endpoint/token/SQL canaries (`_connect_readonly` and `runs._log_query_failure`).
- [ ] `python -m pytest scripts/tests/` passes; the new API behavior is documented.

## Related

- ENH-3677 (shared fixture; prerequisite), ENH-3720 (done; shared deadline), ENH-3700 (guard + catch widening; lands after this), BUG-3652 (done), ENH-3668 (deferred strict-reader feature; not a prerequisite), FEAT-3535 (remote backend).

## Related Key Documentation

- `docs/reference/API.md` (history reader and backend opener), `docs/reference/CONFIGURATION.md` (remote timeout).

## Confidence Check Notes

_Updated 2026-10-04 after the second EPIC-3693 review._

Prior scores were cleared (the plan changed: read-scoped marker, single same-client verification, ENH-3720 landed). Re-run `/ll:confidence-check` after ENH-3677 lands; prove the single `Deadline`, the read-vs-write marker isolation and the cold/warm/black-hole tests.

## Status

**Open** | Created: 2026-09-30 | Priority: P4

## Review Notes

Revised 2026-10-04 (twice). First pass consumed ENH-3720's shared deadline rather than duplicating transport work. Second pass (Opus): ENH-3720 landed so the `blocked_by` was removed and the proposed `connect_readonly_telemetry` replaced by existing `connect_readonly(deadline=)`; deadline expiry is isolated to a read-scoped marker so it cannot suppress telemetry writes; the "behind/ahead readable" and "either merge order" text was dropped because ENH-3700 no longer changes read-mode policy or re-raises; sanitization of `_connect_readonly` is owned here only.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-10-05T03:38:26 - `a86cd5e0-6077-4ee6-8374-60b76cefc32b.jsonl`
- EPIC-3693 review #2 + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.78) - 2026-10-04 - ENH-3720 dependency removed (landed); read-scoped marker, no-ensure_schema/single-verification and sanitization ownership pinned; implementation not performed
- EPIC-3693 pre-implementation review + `/ll:advise` (claude-opus-5-5, user_requested) - 2026-10-04 - guard ownership, per-invocation deadline, marker recovery/scope and safe best-effort diagnostics clarified; deferred strict API removed as a required gate
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:04 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
- `/ll:confidence-check` - 2026-09-30T05:10:31 - `defb8cbc-fb4d-4d9b-9b95-eac7264d3124.jsonl`
