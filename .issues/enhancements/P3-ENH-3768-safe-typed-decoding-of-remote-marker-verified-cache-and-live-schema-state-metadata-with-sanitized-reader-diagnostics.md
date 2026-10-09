---
id: ENH-3768
type: ENH
title: Safe typed decoding of remote marker, verified-cache and live schema-state
  metadata, with sanitized reader diagnostics
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-07'
captured_at: '2026-10-07T08:25:20Z'
blocked_by:
- ENH-3677
blocks:
- ENH-3682
- ENH-3700
relates_to:
- ENH-3657
- BUG-3652
parent: EPIC-3693
epic: EPIC-3693
---

# ENH-3768: Safe typed decoding of remote marker, verified-cache and live schema-state metadata, with sanitized reader diagnostics

> **Origin (EPIC-3693 review #7, 2026-10-07):** extracted from ENH-3682 after an Opus consult (confidence 0.80). ENH-3682's deadline/read-marker/connection-verification seam is a P4 latency fix that ENH-3700 (P3) never needed; ENH-3700 consumed only the decoder normalization and sanitized warning that ENH-3682 happened to own. Those are shared-helper correctness fixes (the marker decoder is also on the telemetry **write** path), so they move here and both siblings depend on this issue instead of ENH-3700 waiting on the `libsql.py` `_guard` surgery.

## Summary

The shared remote-state decoders cast untrusted on-disk and on-wire metadata outside the typed-error boundary, and two reader diagnostics interpolate raw exception text. Normalize the decoders at the shared seam so malformed marker/cache/live state is a cache miss, an inactive marker or a fixed-text typed failure — never a raw `ValueError`/`OverflowError`, access evidence, or indefinite suppression — and sanitize the remote branches of `_connect_readonly`'s warning and `runs._log_query_failure`.

## Current Behavior

Verified against the code on 2026-10-07:

- `session_store/remote_telemetry.py:unreachable_active` returns `bool(data) and _now() - float(data.get("at", 0)) < UNREACHABLE_TTL_S` with the cast outside any guard. Probes with `at="bad"`, `null` and `{}` raised `ValueError`/`TypeError`; JSON `Infinity` (accepted by `json.loads`) keeps the marker active indefinitely. The telemetry **write** path consults this helper, so the defect is not prepatch-specific.
- `remote_telemetry.load_verified` casts `float(data.get("at", 0))` unguarded, then `int(data["version"])` inside a `except (KeyError, TypeError, ValueError)` that misses `OverflowError`: `version=Infinity` escapes, `47.9` is truncated to `47`, and `true` becomes `1`. Truncated/coerced values can be admitted as access evidence. Project/stamp fields are not shape-checked.
- `session_store/remote_schema.py:read_state` returns `RemoteState(int(kv.get("schema_version") or 0), kv.get("project_id"))` after the `meta` query. A nonnumeric live value (a probe with a canary string) escaped as `ValueError` whose message carried the raw value, past the typed `HistoryError` taxonomy and every cache.
- `history_reader/_base.py:_connect_readonly`'s remote `warn_once` interpolates `{type(exc).__name__}: {exc}`, and the non-`sqlite3.Error` branch of `history_reader/runs.py:_log_query_failure` does the same (`"%s (%s: %s)"`), so an endpoint/SQL fragment inside a remote exception can reach logs.
- The shared I/O helpers `_read`, `_write` and `_remove` already swallow `OSError`/`ValueError` and `_read` already returns only a `dict` or `None`; the defects are the value casts above, not filesystem handling.

## Expected Behavior

### Marker and cache decoding is advisory (never raises, never suppresses indefinitely)

Validate at the reached shared decoding seam. A single module-private timestamp decoder in `remote_telemetry.py` accepts only a finite, non-boolean number not in the future; anything else (missing, string, null, nested, `NaN`, `±Infinity`, boolean, future) is an inactive marker / cache miss. Use the existing TTLs and file locations; no new config key. ENH-3682's read-scoped marker reuses this decoder rather than adding its own.

`load_verified` validates the **complete written payload** before constructing `RemoteState`: version must be a non-boolean, non-negative **integer** (no coercion of floats, bools, strings or containers; `Infinity` is a cache miss, not an `OverflowError`); cached project/stamp fields must match their written string-or-null contract. Normal `check_access` still decides whether a well-formed stamp/version is acceptable; well-formed warm-cache behavior is unchanged. A rejected entry is a cache miss, so the caller performs its ordinary bounded verification, and it cannot populate `_VERIFIED`.

### Live schema metadata is normalized before cache admission

`read_state` converts live `meta` values with their written contract: `schema_version` is a non-boolean non-negative integer or its ASCII decimal TEXT representation (the remote `meta` table stores TEXT; do not apply the file cache's integer-only JSON rule to it). Missing/null/empty retains the existing unmigrated version-0 behavior. `project_id` retains its string-or-null representation. Invalid shapes or conversions raise a fixed-text `HistoryOperationError` (existing class in `session_store/backend.py`) that never contains the raw value; do not blanket-catch programming errors. Neither the process cache nor the file cache accepts malformed evidence, and a later repaired live value verifies normally. This normalizes reached decoding only — no schema/access policy, migration or stamp-tightening change (those stay with the dropped-2026-10-04 items).

### Sanitized reader diagnostics

The remote branch of `_connect_readonly`'s warning and of `runs._log_query_failure` use fixed operation/category text: no `str(exc)`, endpoint, token, SQL or `exc_info=True`. Local diagnostics (`logger.warning(..., exc_info=True)` for `sqlite3.Error`, the local `_connect_readonly` message) are unchanged. ENH-3700's widened-catch helper reuses these sanitized paths rather than adding a third formatter.

## Motivation

ENH-3682 (advisory prepatch) and ENH-3700 (required harness lookups) both need malformed remote state to be a typed failure or cache miss, and both need a leak-free warning. Owning that here lets each consume it without one waiting on the other, and fixes the telemetry-write path's marker decode as a side benefit.

## Scope Boundaries

- **In scope:** the timestamp decoder and its use in `unreachable_active`/`load_verified`, full verified-cache payload validation, `read_state` live normalization with the fixed typed error, the two remote diagnostic sanitizations, tests and the API-doc sentence.
- **Out of scope:** the read-scoped marker, `best_effort` keyword, `Deadline`/connection-scoped verification and the prepatch readers (ENH-3682 — it consumes this decoder); `required` keyword, guard, catch widening and `ll-harness` (ENH-3700); schema/access/stamp policy and remote migrations; marker locking/replay or writer-suppression redesign; `_connect_readonly`'s target annotation/forwarding (ENH-3657).

## Behavior Parity

Well-formed state behaves exactly as today: a fresh `at` timestamp keeps a marker active for its existing TTL, a well-formed verified-cache entry still hits (a warm file cache costs no verification POST), valid decimal-TEXT `schema_version` and a missing/null version (unmigrated version 0) are unchanged, and local diagnostics in `history_reader/_base.py` and `history_reader/runs.py` keep their wording and `exc_info`. Only malformed state and the two remote warning strings change.

## Proposed Solution

1. `remote_telemetry.py`: add the private finite-timestamp decoder; route `unreachable_active` and `load_verified` through it; replace the `int(data["version"])` cast with explicit shape validation of version/project/stamp before building `RemoteState`.
2. `remote_schema.py:read_state`: validate/convert live values with the written contract; raise the fixed typed error on invalid input before any cache write.
3. `history_reader/_base.py` and `runs.py`: replace the remote-branch format strings with fixed text; leave local branches alone.
4. Add the API/CONFIGURATION sentence that malformed cache/marker/live state is advisory (cache miss / inactive marker / typed failure).

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/remote_telemetry.py` — `unreachable_active`, `load_verified`, new private decoder; `_read`/`_write`/`_remove` unchanged.
- `scripts/little_loops/session_store/remote_schema.py` — `read_state` only.
- `scripts/little_loops/history_reader/_base.py` — `_connect_readonly` remote warning text. If ENH-3657/ENH-3682 have landed, preserve their target forwarding and `best_effort` keyword.
- `scripts/little_loops/history_reader/runs.py` — `_log_query_failure` remote branch.
- `docs/reference/API.md` / `docs/reference/CONFIGURATION.md` — one advisory-state sentence (cite `little_loops.<module>`, no `scripts/tests/` paths).

### Dependent Files (Callers/Importers)
- `session_store/remote_schema.py` — `check_access` calls `load_verified` then `read_state` (~:247–249); the migration helpers call `read_state` at ~:140/:180/:195/:205 (a malformed live version now aborts a migration with the typed error instead of `ValueError` — still an abort, never a silent proceed).
- `cli/doctor.py` (~:780) and `session_store/raw_redaction.py` (~:772, `ll-session redact`, ENH-3752) also call `read_state`; confirm each already handles `HistoryError` so the typed error replaces a raw `ValueError` traceback.
- `session_store/libsql.py` (~:194) calls `unreachable_active` on the telemetry **write** path; it gains the never-raises behavior.

### Tests
- Use ENH-3677's shared `remote` fixture for the through-the-stub cases (stub with `meta.schema_version` set to a nonnumeric canary, fractional, negative and wrong-type values; wrong-type stamp). Pure decoder tests (timestamps, version shapes) are unit tests on temporary `.ll/` marker/cache files.
- Marker: `at` of `"bad"`, `null`, `{}`, `NaN`, `Infinity`, `-Infinity`, `true`, a future value and an expired value → inactive, no exception; a valid fresh value → active; behavior of a well-formed marker unchanged.
- Verified cache: version `Infinity`, `47.9`, `true`, `"47"`, `null`, missing, a list; project/stamp of the wrong type; each is a cache miss that triggers ordinary verification and does not populate `_VERIFIED`; a well-formed entry still hits. A cold-process test with a current-looking fractional version still refuses a behind/foreign live store.
- Live metadata: canary TEXT, fractional, negative and wrong-type versions and a wrong-type stamp raise the fixed typed error with **no raw value in the exception, log or stderr**; valid decimal TEXT and missing/null-version (unmigrated) behavior stay supported; neither cache is poisoned and a later repaired value verifies.
- Diagnostics: capture logging/stderr with endpoint/token/SQL canaries in a remote open failure and a remote query failure; assert fixed text, no `exc_info`, and unchanged local messages.
- Keep green: `test_remote_hooks.py`, `test_remote_ingestion_telemetry.py`, `test_remote_callers_bug3652.py`, `test_libsql_backend.py`, `test_remote_schema.py`.

## Program Design

### Types
- `RemoteState(version: int, project_id: str | None)` in `little_loops.session_store.remote_schema` — unchanged shape; construction now follows validated input only.
- `HistoryOperationError(HistoryError)` in `little_loops.session_store.backend` — fixed-text decode failure from `read_state`.

### Signatures
- `read_state(client: HranaClient) -> RemoteState` — same signature; raises `HistoryOperationError` (fixed text) on malformed live metadata.
- `unreachable_active(endpoint: str) -> bool` and `load_verified(endpoint: str, project_id: str | None) -> RemoteState | None` — same signatures; never raise on malformed on-disk state.
- `_finite_timestamp(value: object) -> float | None` — planned private helper in `remote_telemetry.py` (name indicative); returns `None` for any unacceptable value, including future timestamps.

### Call Path
- `LibsqlConnection._guard` / `check_access` → `load_verified` (file cache) → on miss `read_state` (live) → validated `RemoteState` → `store_verified` / `_VERIFIED`. Telemetry write path → `unreachable_active`.

### Decision Rules
- Malformed state is a miss, never evidence; never a raw conversion exception; never a raw value in a message.

## Implementation Steps

Prerequisite: ENH-3677 landed (hoisted `remote` fixture) for the stub-driven cases; the pure decoder tests need nothing else.

1. Decoder + `load_verified` payload validation, with unit tests.
2. `read_state` normalization and stub tests.
3. Diagnostic sanitization with canary tests.
4. Docs sentence; run `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/` (scope `ruff format` to changed files).

## Impact

- **Priority**: P3 — correctness of shared remote-state decoding that two P3/P4 siblings and the telemetry write path depend on.
- **Effort**: Small/Medium — three small shared-helper edits, two diagnostic strings, focused tests.
- **Risk**: Low-Medium — well-formed state must keep its exact behavior (warm-cache hit counts, unmigrated version 0); tests pin both sides.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] Malformed, missing, nonfinite, boolean, future or expired marker timestamps never raise and never suppress permanently; a fresh well-formed marker still suppresses.
- [ ] Malformed verified-cache versions (Infinity, fractional, bool, string, null, missing, container) and wrong-type project/stamp fields are cache misses, never truncated/coerced evidence or escaped exceptions; invalid entries cannot populate `_VERIFIED`; a well-formed warm cache still hits.
- [ ] Malformed live `meta` metadata through the real stub verification path raises one fixed-text `HistoryOperationError` with no raw value in the message, log or stderr; valid decimal TEXT and missing/null-version behavior remain; neither cache is poisoned and a repaired value verifies.
- [ ] The remote branches of `_connect_readonly`'s warning and `runs._log_query_failure` emit fixed text with no exception text, endpoint, token, SQL or `exc_info`; local diagnostics are unchanged.
- [ ] No schema/access/stamp policy, migration or retry behavior changes; the ENH-3682 read marker and ENH-3700 required channel can consume this decoder without reimplementing it.
- [ ] `python -m pytest scripts/tests/` passes.

## Related

- ENH-3682 (prepatch read budget; consumes this decoder, `blocked_by` this), ENH-3700 (required reader/guard; `blocked_by` this), ENH-3677 (shared fixture; `blocked_by`), ENH-3657 (reader target forwarding in the same `_connect_readonly`), BUG-3652 (done), FEAT-3535 (remote libSQL backend).

## Related Key Documentation

- `docs/reference/API.md` (session-store backend and history reader), `docs/reference/CONFIGURATION.md` (Remote history backend).

## Status

**Open** | Created: 2026-10-07 | Priority: P3

## Confidence Check Notes

New 2026-10-07; no score. Run `/ll:confidence-check` after ENH-3677 lands. The decoder probes (Infinity marker, `47.9`/`true` cache versions, nonnumeric live metadata) were recorded in EPIC-3693 reviews #4–#6; re-run them against landed code at implementation.

## Session Log

- EPIC-3693 review #7 + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.80) - 2026-10-07 - extracted from ENH-3682 so ENH-3700 no longer waits on the deadline/read-marker seam; code claims re-verified (`unreachable_active`/`load_verified`/`read_state` casts, raw `{exc}` in `_connect_readonly` and `_log_query_failure`). Implementation not performed.
