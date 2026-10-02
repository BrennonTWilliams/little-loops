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

## Ordering and Exception Contract (2026-09-30 Opus review, revised)

**No longer a prerequisite of ENH-3657** (edge dropped 2026-09-30). ENH-3657 narrows its `_connect_readonly` re-raise to the guard's own `HistoryRemoteRefused` subclass, so remote `ensure_schema` refusals (`HistoryUnsupported` for a behind, foreign or read-only-token store) still degrade to `None`, and `read_base_sha`/`read_base_dirty` use the relative `DEFAULT_DB_PATH`, which the guard never touches. This issue keeps independent value: it removes the ~10 s black-holed-endpoint stall per read and sets the unreachable marker. It is `blocked_by` ENH-3677 because it plans `HranaStub` tests and must use the hoisted `remote` fixture rather than add a seventh copy.

**Sequencing (2026-10-02 Opus review):** land after ENH-3700 (3657b) so the `HistoryUnsupported`-still-yields-`None` regression test is written against the final `_connect_readonly` contract rather than the interim one; it passes in either order, but writing it once avoids rework. Both issues add a keyword to `open_history_readonly`/`_connect_readonly` (`best_effort` here, the guard and read-mode ensure in ENH-3700): rebase and keep defaults unchanged.

The `best_effort` path still skips ensure **and** catches `HistoryError` including `HistoryUnsupported`, so the never-raises contract of these two readers holds regardless of what any other issue does to `_connect_readonly`.

## Expected Behavior

Best-effort prepatch reads share one cumulative `history.backend.telemetry_timeout_ms` deadline across access verification and the data query, skip remote ensure/migration, and return `None` on an unavailable endpoint. On a cold connection `_guard` verification and the query are separate HTTP requests: giving each a fresh timeout is insufficient. Carry the monotonic deadline through `LibsqlConnection` and `HranaClient`, including retries, connect, response headers and body reads. Check remaining time before each request and blocking step; do not send the query after verification consumes the budget. The first timeout sets the file-backed unreachable marker; another advisory read while it is active makes no request. Other history reads retain existing timeout/errors; local behavior is unchanged.

Explicit `best_effort=True` wins over ambient `strict_reads()` (ENH-3668): both open and mid-query `HistoryError`/`sqlite3.Error` return `None`, never raise. The marker is the existing endpoint-scoped TTL file, shared across processes; no replacement cache or new configuration is needed.

## Motivation

Base-SHA/dirty-state history is advisory to prepatch. A slow remote store should not delay an FSM step twice when the same step can continue using its existing branch/merge-base fallback.

## Proposed Solution

Add `open_history_readonly(..., best_effort: bool = False)` and a remote `LibsqlBackend.connect_readonly_telemetry` path. For `RemoteTarget` plus `best_effort=True`, skip `ensure_schema`, use a read-only `LibsqlConnection` with telemetry timeout and marker behavior, and return `None` on `HistoryError` through the existing reader helper. Set `best_effort=True` only in the two prepatch readers. `telemetry_scope()` alone is insufficient because `open_history_readonly` does not consult it. Keep the relative default path so backend config is resolved normally and no shadow local database is created.

## Scope Boundaries

- **In scope:** only `read_base_sha` and `read_base_dirty`, the best-effort readonly connection seam, timeout/marker tests and API docs.
- **Out of scope:** typed-target propagation to user-facing reader CLIs/MCP (ENH-3668), all other reader timeouts, remote migrations, and changes to prepatch fallback decisions.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/{backend.py,libsql.py,hrana.py}` (readonly best-effort connection and shared request deadline), `history_reader/_base.py` (narrow parameter), `history_reader/runs.py` (two call sites), focused prepatch/remote tests, and `docs/reference/API.md`.

### Similar Patterns and Configuration

- Reuse the existing telemetry timeout and unreachable marker from the remote writer connection. No new config key or schema migration.

## Program Design

### Signatures

- `open_history_readonly(target=None, *, ensure: bool = False, best_effort: bool = False)` — keeps the default standard read behavior.

### Call Path

`history_reader.runs.read_base_sha` / `read_base_dirty` → `_connect_readonly(..., best_effort=True)` → `open_history_readonly(..., best_effort=True)` → bounded remote readonly query or `None` fallback. A local target follows the existing local path.

## Implementation Steps

1. Implement the opt-in remote readonly telemetry connection and marker-aware cumulative deadline at the backend/Hrana seam, including cold access verification.
2. Enable it at only the two prepatch reads. Preserve the existing `None` fallback on open and mid-query errors.
3. Test with a socket that accepts but never replies, plus a local twin; update API docs and run the suite.

## Impact

- **Priority:** P4 — an opt-in remote backend can delay an advisory FSM step.
- **Effort:** Small/Medium — one connection seam and two callers; uses the ENH-3677 `remote` fixture.
- **Risk:** Medium — timeout or marker behavior must not leak into normal reads.
- **Breaking Change:** No.

## Acceptance Criteria

- [ ] A black-holed-socket test shows each prepatch read returns `None` within the configured telemetry timeout budget, sets the unreachable marker, and sends no new request while that marker is active.
- [ ] Cold and warm verification-cache tests enforce one total read deadline. A slow successful verification followed by a black-holed query cannot consume two budgets; an exhausted verification budget prevents another request. Assert request counts and a small documented scheduling tolerance as well as elapsed time.
- [ ] Inside `strict_reads()`, explicit best-effort still returns `None` on open and mid-query failure and restores the enclosing mode; standard readers retain their own timeout and error policy.
- [ ] Both readers still return actual remote data through a reachable `HranaStub`; local SQLite and standard reader timeouts remain unchanged.
- [ ] Open and mid-query remote failures preserve each function's documented never-raises/`None` fallback, including a behind/foreign-schema store and a read-only token (`HistoryUnsupported`); no local shadow DB is created.
- [ ] A regression test for the `HistoryUnsupported` case passes both before and after ENH-3657's (narrowed) `_connect_readonly` re-raise lands, whichever order they merge in.
- [ ] `python -m pytest scripts/tests/` passes; the new API behavior is documented.

## Related

- BUG-3652 (done startup/read path correction), ENH-3668 (larger remote-reader feature; independent), FEAT-3535 (remote backend).

## Related Key Documentation

- `docs/reference/API.md` (history reader and backend opener), `docs/reference/CONFIGURATION.md` (remote timeout).

## Confidence Check Notes

_Updated 2026-10-02 after the EPIC-3693 pre-implementation review._

Prior 86/72 scores were cleared: the old plan omitted cumulative cold verification/query latency. Implementation remains blocked by ENH-3677. Re-run `/ll:confidence-check` after that prerequisite; prove readonly telemetry plus one deadline through Hrana, explicit best-effort precedence and the file-backed marker with the planned cold/warm/black-hole tests. Prefer integration after ENH-3700, without adding a functional dependency.

## Status

**Open** | Created: 2026-09-30 | Priority: P4

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Ordering/policy vs ENH-3657 and ENH-3700: the `_connect_readonly` narrowing/re-raise and read-mode ensure are owned by ENH-3700 (ENH-3657 makes no contract change there) — read "ENH-3657's (narrowed) `_connect_readonly` re-raise" as ENH-3700's; sequence softly, no new `blocked_by`. Best-effort cold verification uses `check_access(write=False)` per ENH-3700, which serves behind/ahead stores and read-only tokens; only foreign or unstamped stores are expected to raise `HistoryUnsupported`.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:04 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
- `/ll:confidence-check` - 2026-09-30T05:10:31 - `defb8cbc-fb4d-4d9b-9b95-eac7264d3124.jsonl`
