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
3. Verify access once with `remote_schema.check_access(client, cfg, write=True, persist=True)` on that deadline-bound client — the same policy as the ordinary `ensure=True` path, so behind/ahead/unstamped/foreign stores are refused with `HistoryUnsupported` and a read-only token still works (metadata SELECTs only) — and run the data query on the **same client without a second lazy verification**. Cold: verification POST + data POST; warm file cache: data POST only; marker active: zero. Retain `write=True`: it chooses the exact-version/stamp policy, not a mutating SQL operation; using `write=False` would wrongly admit behind/ahead/unstamped stores.
4. The first failure of kind timeout/connect/unavailable at verification **or** data request writes the **read-scoped** marker (same TTL and file location scheme as the write marker, distinct kind) before returning `None`. A normal empty row, schema/query error or project-policy refusal (`HistoryUnsupported`) must not create a marker.

Keep the backend opener's **connection-or-typed-error** contract. `open_history_readonly` returns a connection on success; active-marker suppression raises an existing safe `HistorySuppressed`, and expected opening/verification failures remain typed `HistoryError`. Only `_connect_readonly` and the two advisory readers map these outcomes to `None`; the backend must not return an unadvertised `None` that another caller later dereferences. Suppression is quiet after the designated first safe warning, still before any request. All opened connections close on verification failure as well as query completion. Preserve ENH-3657's original-intent setup handling if it has landed; do not make its temporary forwarding or ENH-3700's future guard a prerequisite of this remote latency branch.

**Why read-scoped (Opus 2026-10-04):** `LibsqlConnection._run` marks the shared write marker on any `HistoryUnavailable` when `telemetry=True`, and deadline expiry raises `HranaUnavailable`. A cumulative 1.5s budget (two POSTs cold) can expire on a slow-but-healthy endpoint where per-request writes succeed; marking the shared marker would then suppress all telemetry writes across processes for 60s. Best-effort reads therefore **read** both markers but **write only the read marker**. Writes consult only the write marker and are unaffected by a read timeout. (Alternative if the read marker proves awkward: introduce `HranaDeadlineExpired` and mark the shared marker only on zero-byte/connect failures.)

The deadline is per reader invocation/connection: verification and its data query share one budget. The two SHA/dirty calls do not share an FSM-wide timer; the read marker suppresses the second call after the first timeout. Successful calls each consume their own budget. Do not add another timer or automatic retry; use ENH-3720's documented DNS/CPU limits. Do not send the query after verification consumes the budget.

Explicit `best_effort=True` wins over any ambient reader mode: both open and mid-query `HistoryError`/`sqlite3.Error` return `None`. `strict_reads()` is planned only by deferred ENH-3668; do not introduce it. Add the nesting/restoration test only if that API exists when implementing, otherwise record this precedence for its future integration. Suppression applies only to best-effort consumers; ordinary explicit reads ignore both the read marker and this branch.

**Sanitized diagnostics (owned here only):** `_connect_readonly`'s remote warning and the remote branch of `runs._log_query_failure` use fixed operation/category text — no `str(exc)`, endpoint, token, SQL or `exc_info=True`. Local diagnostics stay unchanged.

### Connection-scoped verification completion

The current `LibsqlConnection._guard` calls `check_access` for every statement, and `persist=True` file-cache hits deliberately do **not** populate process `_VERIFIED`. Eagerly checking and then using the unchanged connection therefore causes a second verification POST in a fresh process with a warm file cache. This issue includes a narrow seam in `session_store/libsql.py`: on the opened connection, a private best-effort verification method checks its deadline, calls `check_access` on **its own deadline-bound client**, and marks that connection verified only after success. `_guard` skips only the access check for that verified connection; read-only write denial and deadline checks still run for every statement.

Default connections remain lazily verified. Do not set `config=None`, populate global `_VERIFIED` from file cache, set `telemetry=True`, or expose a caller-controlled preverified boolean that can bypass access checks before successful verification. The same connection retains its config and client. A file-cache hit followed by an ordinary explicit connection must still cause the explicit connection's uncached verification. No ambient strict/read mode is introduced.

Read-marker completion belongs to the entire advisory read: open/verification failure is handled at the opener, query/fetch failure is handled by each prepatch reader. Mark read-unreachable only for transport/unavailable/deadline failures (not policy/schema/query failures), and clear the read marker after a successful query/fetch, including a legitimate empty result. Every path closes the opened connection; no retry or second connection is created. Active-marker suppression precedes any verification request. Use a fresh process or explicitly cleared process cache when proving the warm **file-cache** request count; a warm `_VERIFIED` alone does not test this hole.

### Cache/marker state is advisory, including malformed state

**Review #4 evidence:** existing `remote_telemetry.unreachable_active` casts `float(data.get("at", 0))` outside a decoding guard. Probes with `at="bad"`, `null` and `{}` returned `ValueError`/`TypeError`; `Infinity` remained active indefinitely. `load_verified` similarly casts its timestamp before the guarded schema-version conversion. This new branch consults both existing helpers, so hardening only the new read-marker decoder would leave exceptions/suppression outside the promised never-raises contract.

Validate timestamps at the reached shared decoding seam: malformed/missing/nonfinite/future/expired state is a cache miss or inactive marker. Use the existing TTLs; invalid state cannot authorize access, permanently suppress reads, or populate `_VERIFIED`. With an invalid verified-cache entry, perform normal deadline-bound verification on the same client. Treat expected cache/marker filesystem failures as bookkeeping failure rather than read failure: a successful query still returns its real result if clearing the read marker fails, and a failed query still returns `None` if writing its marker fails. Diagnostics stay fixed and safe. Do not add locking/replay or redesign writer suppression; existing well-formed state keeps its behavior.

**Validate the complete verification-cache payload, not only its timestamp (review #5).** A temporary decoder probe returned `OverflowError` for `version=Infinity`, silently accepted `47.9` as version `47`, and accepted `true` as version `1`. The current `int(data["version"])` conversion both escapes the never-raises boundary and can turn malformed cache data into accepted access evidence. Require the written JSON schema-version shape (a non-boolean, non-negative integer); missing, fractional, nonfinite, string/container or boolean versions are cache misses, without coercion. Validate cached project/stamp field shapes against their written string-or-null contract before constructing `RemoteState`; normal access checks still decide whether a well-formed stamp/version is acceptable. Reject the malformed entry before process/connection verification completion, then perform the ordinary bounded verification. This is reached advisory-cache decoding only; remote schema/migration policy is unchanged.

The local branch has a reached setup exception outside the current `HistoryError` taxonomy: a regular file used as the DB's parent makes `read_base_sha` escape `FileExistsError` from `ensure_db`. Preserve normal local setup, but in explicit best-effort mode normalize/catch expected `OSError` setup failures as well as `HistoryError`/SQLite failures and return `None` without setting a remote marker. Use narrow catches around the named operations, not blanket suppression of process-control exceptions or unrelated programming errors. A missing endpoint/configuration is unavailable configuration, not proof of an unreachable endpoint; marker handling must not call a failing `cfg.endpoint()` again from its exception path.

### Live verification metadata also crosses the error boundary

**Review #6 probe:** a migrated `HranaStub` whose live `meta.schema_version` contained a nonnumeric canary caused `read_base_sha` to escape `ValueError`; the raw metadata appeared in the exception message. `remote_schema.read_state` currently constructs `RemoteState(int(kv.get("schema_version") or 0), ...)` outside the typed error taxonomy. Validating only the file cache does not protect cold verification, ordinary ensure-read opening, or ENH-3700's required readers.

Normalize malformed **live** state at `read_state` before either verification cache can receive it: version must be a non-boolean non-negative integer or its ASCII decimal TEXT representation, matching the remote `meta` table's written contract. Missing/null version retains the existing unmigrated version-0 behavior. Project stamp retains the string-or-null representation; missing stamp/behind/ahead/foreign disposition still belongs to unchanged `check_access` policy. Do not apply the file-cache's integer-only JSON rule to valid live decimal TEXT. Invalid shapes/conversions raise a fixed-text `HistoryOperationError` without the raw value; do not blanket-catch programming errors. Neither process/file cache nor connection completion accepts malformed evidence. The advisory reader returns `None`, emits its safe warning, and creates no unreachable marker for this metadata failure. An ordinary explicit reader receives a typed failure. This is reached decoder normalization, not a new schema/access policy or remote migration.

## Motivation

Base-SHA/dirty-state history is advisory to prepatch. A slow remote store should not delay an FSM step twice when the same step can continue using its existing branch/merge-base fallback, and a slow advisory read must not cost the user their telemetry writes.

## Proposed Solution

Add `open_history_readonly(..., best_effort: bool = False)`. For `RemoteTarget` plus `best_effort=True`, follow Expected Behavior using existing primitives (`Deadline`, `LibsqlBackend.connect_readonly(deadline=)`, `check_access(..., persist=True)`, `remote_telemetry` markers) plus a small read-marker pair in `remote_telemetry` (e.g. `mark_read_unreachable` / `read_unreachable_active`, same TTL, cleared on a successful best-effort read). Do not route reads through writable `connect_telemetry`. The existing helper returns `None` on opening failures; each prepatch reader separately catches query/fetch failures and returns `None`. Set `best_effort=True` only in the two prepatch readers (`telemetry_scope()` alone is insufficient: `open_history_readonly` does not consult it). Keep the relative default path so backend config resolves normally and no shadow local database is created.

## Scope Boundaries

- **In scope:** `read_base_sha` and `read_base_dirty`, the best-effort readonly seam and connection-scoped verification completion, the read-scoped marker plus the reached marker/file-cache and live verification-state decoding helpers, expected setup/bookkeeping failure fallbacks, sanitized `_connect_readonly`/`_log_query_failure` remote text, timeout/marker tests and API docs.
- **Out of scope:** ENH-3720's deadline primitive, socket enforcement and stub controls (landed); typed-target propagation to user-facing reader CLIs/MCP (ENH-3668); all other reader timeouts, remote migrations, new retries, changes to prepatch fallback decisions; the central guard and catch widening (ENH-3700).

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/backend.py` — best-effort branch in `open_history_readonly`; preserve the local and ordinary-reader branches.
- `scripts/little_loops/session_store/libsql.py` — connection-scoped best-effort verification completion and `_guard`'s narrow verified-connection branch; keep ordinary `connect_readonly` defaults, read-only denial, config and deadline enforcement.
- `scripts/little_loops/session_store/remote_telemetry.py` — read-scoped marker kind/helpers, timestamp validation in the reached existing `unreachable_active`/`load_verified` paths, and strict written-payload shape validation for cached version/project/stamp fields; expected bookkeeping I/O failures stay advisory.
- `scripts/little_loops/session_store/remote_schema.py` — only live `read_state` payload validation and fixed typed decode errors before cache admission; preserve missing-version handling and all access/migration policy.
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
- `_connect_readonly(db_path, *, best_effort: bool = False)` — forwards the mode, preserves selected local intent if ENH-3657's annotation/forwarding has landed, and catches open/setup failures only. ENH-3657 and this issue remain independently eligible after ENH-3677; integrate their separate changes without dropping target support or this keyword.
- `LibsqlConnection._verify_best_effort_access() -> None` — planned private connection method: deadline check, exact-version/stamp `check_access(write=True, persist=True)` on its own client, then set connection-scoped verification completion; defaults never call it. Naming may follow local conventions, but completion cannot precede successful verification.
- `remote_telemetry.mark_read_unreachable(endpoint: str) -> None` / `read_unreachable_active(endpoint: str) -> bool` — read-scoped marker (names indicative).

### Call Path

`history_reader.runs.read_base_sha` / `read_base_dirty` → `_connect_readonly(..., best_effort=True)` → `open_history_readonly(..., best_effort=True)` → marker check → deadline-bound `connect_readonly` → one `check_access` → query on the same client, or `None`. A local target follows the existing local path.

## Implementation Steps

1. After ENH-3677, add the read-marker helpers and the best-effort branch (one `Deadline`, marker check, skip `ensure_schema`, single verification on the opened connection, connection-scoped completion, same-client query).
2. Enable it at only the two prepatch reads; keep the `None` fallback on open/setup and mid-query errors; harden reached marker/cache/live-state decoding and bookkeeping failure paths; preserve connection-or-typed-error at the backend and sanitize the remote warnings.
3. Test with a socket that accepts but never replies and ENH-3720's `delays` / `stall_body` / `trickle` controls, plus a local twin; update API docs and run the suite.

## Impact

- **Priority:** P4 — an opt-in remote backend can delay an advisory FSM step.
- **Effort:** Medium — best-effort opener and two callers, connection-scoped verification, read/write marker isolation, reached cache validation and transport failure tests.
- **Risk:** Medium — timeout or marker behavior must not leak into normal reads or silence writes.
- **Breaking Change:** No.

## Acceptance Criteria

- [ ] A black-holed-socket test shows each prepatch read returns `None` within the configured telemetry timeout budget, sets the **read** marker, and sends no new request while a marker is active.
- [ ] Cold and warm verification tests consume one ENH-3720 `Deadline`: cold success makes two POSTs, warm (file-cached) one, a marker-suppressed read zero, and verification consuming the budget prevents the data POST. A slow verification followed by a stalled/trickling query cannot consume two budgets (use the prerequisite's named small scheduling tolerance and fault controls). No duplicate lazy verification on the data query.
- [ ] A fresh process with a warm file cache performs zero verification POSTs and one data POST; that file-cache hit never populates `_VERIFIED`. A later ordinary explicit connection still verifies independently. Connection-scoped completion skips only access verification: writes on that read-only connection remain denied and deadline expiry still prevents a statement; unsuccessful verification never sets completion.
- [ ] **Deadline expiry on a responding (slow-but-healthy) endpoint does not suppress telemetry writes:** after a best-effort read times out and sets the read marker, a telemetry write to the same endpoint still issues its request; a write-side failure still suppresses best-effort reads.
- [ ] The best-effort branch never calls `ensure_schema` (no un-deadlined 10s client); it applies the same access policy as ordinary `ensure=True` (behind/ahead/unstamped/foreign refused via `HistoryUnsupported`, read-only token works) and `HistoryUnsupported` degrades to `None` without a marker.
- [ ] Explicit best-effort returns `None` on open/mid-query/guard failure; standard readers retain their timeout/error policy. If deferred ENH-3668's ambient strict API exists, test nesting/restoration and best-effort precedence; otherwise no strict-reader implementation is required.
- [ ] Both readers still return actual remote data through a reachable `HranaStub`; local SQLite and standard reader timeouts remain unchanged. Default remote reads create no shadow DB.
- [ ] Separate open-error and query/fetch-error tests preserve each reader's never-raises/`None` fallback.
- [ ] Verification/query timeout sets the read marker; second-reader/fresh-process suppression sends zero requests; TTL expiry (and a later success) permits recovery. Empty rows and policy/query errors do not mark the endpoint down, and ordinary explicit reads ignore the marker. Captured logs/stderr contain no raw exception/endpoint/token/SQL canaries (`_connect_readonly` and `runs._log_query_failure`).
- [ ] Malformed/missing/nonfinite/future/expired timestamps in either unreachable-marker kind and the verified cache never raise or suppress permanently. Invalid verified state triggers normal bounded verification, without process-cache contamination. Inject marker write/clear failure and assert failed reads still return `None`, while healthy reads return their actual data; expected local setup `OSError` returns `None` without a remote marker. Missing endpoint configuration does not cause a second exception from attempted marker creation.
- [ ] Malformed verified-cache versions (including Infinity, fractional values, bool, strings, null, missing and containers) and wrong-type project/stamp fields are cache misses, never truncated/coerced access evidence or escaped exceptions. A cold-process test with a current-looking fractional version performs normal verification, so a behind/foreign live store is still refused; a well-formed warm cache retains its one-data-POST behavior. Invalid entries cannot set connection completion or populate `_VERIFIED` by themselves.
- [ ] Malformed live metadata through the actual stub verification path is a fixed safe typed failure, advisory `None`, no unreachable marker and no admitted verification evidence. Cover nonnumeric canary TEXT, fractional/negative/wrong-type versions and wrong-type stamps; valid decimal TEXT and missing/null-version unmigrated behavior remain supported. A later repaired live value can be verified normally, with no malformed-state cache poisoning or raw-value traceback.
- [ ] Direct backend success returns a connection and marker suppression/open failure raises a typed error; `_connect_readonly` alone maps those outcomes to `None` without duplicate suppression warnings. Verification failure closes its opened connection, and the local-target setup contract composes with either ENH-3657 integration order.
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
- EPIC-3693 review #6 - 2026-10-06 - actual stub probe found a raw ValueError from malformed live schema metadata, distinct from the already-planned JSON cache validation; added narrow live-state typed normalization and cache-admission tests. Backend connection-or-error/suppression ownership clarified. Follow-up Opus consult did not run: advisor consult budget exhausted for this task (advisor.max_consults_per_task). Implementation not performed.
- EPIC-3693 review #5 - 2026-10-05 - complete verified-cache payload validation added after probes found OverflowError on Infinity and silent fractional/bool version coercion; normal access policy and warm-cache behavior retained. Opus consult skipped at the existing 3/3 session budget; implementation not performed.
- EPIC-3693 review #4 - 2026-10-05 - malformed/nonfinite marker/cache timestamps and expected setup/bookkeeping failures added to the never-raises contract; selected-local forwarding integration synchronized with ENH-3657. Fresh Opus consult skipped: existing per-chat budget exhausted; implementation not performed.
- EPIC-3693 review #3 + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.80) - 2026-10-05 - real connection-scoped verification seam, cold-process/file-cache gate and query/fetch marker completion specified; write=True policy retained after confirming metadata-only SELECTs; implementation not performed
- `/ll:audit-issue-conflicts` - 2026-10-05T03:38:26 - `a86cd5e0-6077-4ee6-8374-60b76cefc32b.jsonl`
- EPIC-3693 review #2 + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.78) - 2026-10-04 - ENH-3720 dependency removed (landed); read-scoped marker, no-ensure_schema/single-verification and sanitization ownership pinned; implementation not performed
- EPIC-3693 pre-implementation review + `/ll:advise` (claude-opus-5-5, user_requested) - 2026-10-04 - guard ownership, per-invocation deadline, marker recovery/scope and safe best-effort diagnostics clarified; deferred strict API removed as a required gate
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:04 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
- `/ll:confidence-check` - 2026-09-30T05:10:31 - `defb8cbc-fb4d-4d9b-9b95-eac7264d3124.jsonl`
