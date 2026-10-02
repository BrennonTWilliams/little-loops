---
id: ENH-3668
type: ENH
title: Build strict-read infrastructure for HistoryTarget-aware history readers
priority: P4
status: deferred
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T21:52:34Z'
blocked_by:
- ENH-3677
- ENH-3700
blocks:
- ENH-3684
- ENH-3685
relates_to:
- EPIC-3693
- BUG-3652
- ENH-3657
- ENH-3682
deferred_by: human
deferred_date: '2026-10-02T17:58:39Z'
---

# ENH-3668: Build strict-read infrastructure for HistoryTarget-aware history readers

> **Deferred 2026-10-02** (Opus review of EPIC-3693's children): no known remote read demand. Remote read serving is out of scope for EPIC-3693 and was detached from it so the epic branch can close. Revive when demand exists. Now `blocked_by` ENH-3700 (central guard + read-mode ensure) instead of ENH-3657.
>
> **Revival constraints recorded in the review:**
> - **(A) No `strict` parameter on `open_history_readonly`.** ENH-3700's read-mode remote ensure is already `check_access(write=False)` with no migrate, so a `strict=True` open path would be nearly identical. Keep strictness only in the `strict_reads()` contextvar (the only real delta is raise-instead-of-`None` in `_connect_readonly`).
> - **(B) `HistorySchemaUninitialized` is raised only at the strict boundary**, not in the shared `check_access` read branch. A read-branch raise would change every remote read-only statement, including telemetry, doctor and the `ll-harness` probe, which can hit a version-0 store before first migration.
> - **(C) Stamped-schema rule follows ENH-3700:** serve an exact or behind store, refuse an ahead store (an older client may query renamed/removed columns).

## Summary

Slice **a** of three (2026-09-30 Opus review split). Build the shared machinery that lets a defined set of history readers serve from an opt-in remote libSQL store without ever reporting a failure as "no data": a strict-read mode, a read-mode schema check, a `HistorySchemaUninitialized` error, and one boundary verdict helper. The per-command flips are ENH-3684 (`ll-history rework`, `quality`, `audit-issue-collisions`, `sessions`, `root`); MCP `history_search` and SFT `enrich` are ENH-3685. This issue flips no user-facing row by itself.

## Current Behavior

1. `history_reader/_base.py:_connect_readonly(db_path)` (about 70 call sites across `history_reader/*` and `issue_history/{rework,collisions,agent_quality}`) calls `open_history_readonly(path, ensure=True)` and maps any `HistoryError` to `None`.
2. `open_history_readonly(ensure=True)` runs `backend.ensure_schema`, which for libsql is `remote_schema.check_access(..., write=True)` (`libsql.py:286`). That **write-mode** check raises `HistoryUnsupported` for a store one migration behind, ahead, or unstamped, so a stale-but-readable remote store looks like "no data" on a read path. `check_access(write=False)` would serve it.
3. `remote_schema.read_state()` returns `RemoteState(0, None)` for an empty store (no `meta` table), and read-mode `check_access` does not raise for it, so "reachable but unmigrated" has no detection point today.
4. Several readers do `Path(db)` and `db_path.exists()` before connecting (`lookup_session_metadata`, `conversation_turns`; `collisions`/`rework`/`agent_quality` call `_connect_readonly(Path(db))`). Under remote config a default-shaped path is `.exists()`-False, so a read returns empty silently, and `Path(RemoteTarget)` cannot work.
5. Remote mid-query failures raise `HranaError` (a `HistoryError`, **not** `sqlite3.Error`), so the ~87 `except sqlite3.Error` handlers do **not** swallow them. The real silent-empty leaks are the `None` mapping in `_connect_readonly`, the `.exists()` pre-checks, and three handlers that catch `(sqlite3.Error, HistoryError)`: `history_reader/formatting.py:156`, `history_reader/runs.py:238`, `runs.py:287`.
6. A local "no such table" is swallowed to empty, while the remote twin raises `HranaOperationError`, so a stale remote diverges from the local twin.

## Expected Behavior

- **`strict_reads()` context manager** (a `contextvars.ContextVar`, in `little_loops.session_store`), entered by each serve boundary (CLI/MCP/loop). While active for a resolved `RemoteTarget`, `_connect_readonly` raises instead of returning `None`; local targets retain existing fallbacks. Outside it, behavior is unchanged, so BUG-3652 hook/digest/`ll-harness` callers keep their quiet degrade. A context variable, not a threaded kwarg: the `quality → agent_quality → rework` chain makes kwarg threading easy to miss. (Dissent noted in review: an explicit kwarg or target attribute is more traceable; rejected for the reason above.)
- **Strict remote open** reuses ENH-3700's read-mode remote ensure (`check_access(write=False)`, no ensure/migrate, no write-mode check); there is **no `strict` parameter** on `open_history_readonly`. Per ENH-3700's stamped-schema rule, exact and **behind** (`0 < version < total`) stores are **served** and **ahead** stores are **refused**; project-id mismatch and missing `project_id` still raise.
- **`HistorySchemaUninitialized`**: new subclass of `HistoryUnsupported` (**not** `HistoryUnavailable`, so telemetry `mark_unreachable` cannot fire on a reachable store). Raised **only at the strict boundary** (under `strict_reads()`), when the state is version 0 (no `meta` table); it is **not** raised in the shared `check_access` read branch, which would change every remote read-only statement (telemetry, doctor, the `ll-harness` probe) that can hit a version-0 store before first migration.
- **Success parity, remote failure visibility:** successful remote results match the local twin. Preserve existing local query-error-to-empty behavior, including missing-table/FTS cases. Strict remote open and query failures propagate; they must never become an empty success. Strictness applies only to a resolved `RemoteTarget`, so an explicit local override keeps existing behavior.
- **Error classification:** extend `HranaError` with nullable `http_status: int | None` and retain it through `classify_error` and every typed subclass. HTTP 401/403 are authentication failures; 5xx, timeouts and network failures are unavailable. Do not classify every `SQLITE_UNKNOWN` as schema mismatch: only a proven, narrowly tested missing-schema signal may get that classification; other SQL failures are `query_failed`.
- **`history_error_verdict(exc) -> Verdict`** extends ENH-3657's shared helper with the contract below. Messages come from a fixed safe catalogue, never `str(exc)` (network errors currently contain the endpoint host).
- **Project stamp and recovery:** distinguish missing configured `project_id`, missing store stamp, and a mismatched stamp. A version-0 store reports uninitialized before stamp validation; a migrated but unstamped or foreign store reports project mismatch. Do not retain a version-0 verification result indefinitely: after another process initializes the store, the same long-lived reader must re-probe and recover without a restart.
- **Target-aware guard** `_store_missing(target)` replaces `.exists()` gating: a `RemoteTarget` never enters `Path.exists`, `Path(...)`, `sqlite3.connect`, or `ATTACH`; local missing-file behavior is unchanged.
- **Signatures**: reader and `issue_history` functions accept `Path | str | HistoryTarget | None`; the boundary resolves once with `resolve_history_target(None, root=project_root)` (an absolute `.ll/history.db` is already default-shaped per `_is_default_shaped`, so no separate shadow-file fix is needed there).
- **Static guard test**: audit broad catches on the serve-path call graph, allowing the shared boundary and explicit catches that re-raise under strict remote mode. Pair the AST gate with failure-injection tests; forbidding every catch would also forbid the deliberate local/best-effort fallback.

### Boundary error contract

Every strict remote failure exits **1** at a CLI boundary and emits exactly one safe stderr line (`<operation>: <message>`). When the command supports `--json`, stdout contains `{"error":{"code":"<code>","message":"<safe message>","operation":"<operation>"}}`, with no successful result payload. MCP returns the same error object with `is_error=true`. Use codes `unsupported`, `uninitialized`, `schema_mismatch`, `project_mismatch`, `authentication_failed`, `unavailable`, and `query_failed`; map both missing and foreign project stamps to `project_mismatch` with distinct safe messages. Never include endpoint, host, SQL, token, or raw exception text. A migrated store with zero matching rows succeeds (exit 0).

`strict_reads()` restores its prior ContextVar value in `finally`, including nested scopes and exceptions. Explicit `best_effort=True` (ENH-3682) takes precedence over ambient strict mode and preserves the never-raises contract. ENH-3700 owns the non-strict harness mid-query fallback; the three existing broad catch sites here re-raise only in strict remote mode.

A reachable migrated store with zero rows is an empty result; an unreachable store is unavailable; a reachable unmigrated store is uninitialized; none creates a local file.

## Motivation

An interim clean refusal (ENH-3657) is preferable to a traceback, but remote users cannot use these views. Shipping the strictness machinery once, with its regression surface, keeps the two flip issues small and prevents each from re-inventing failure handling.

## Program Design

### Types

- `HistoryTarget = LocalTarget | RemoteTarget`.
- `class HistorySchemaUninitialized(HistoryUnsupported)`.
- `strict_reads()` context manager plus `strict_reads_active() -> bool`.
- `Verdict` (exit code, message, JSON payload) from `history_error_verdict`.

### Signatures

- `open_history_readonly(target: Path | str | HistoryTarget | None = None, *, ensure: bool = False) -> Connection` — unchanged signature; ENH-3700's remote read-mode ensure already runs `check_access(write=False)`. `_connect_readonly` consults `strict_reads_active()` and raises instead of returning `None`; no `strict` kwarg.
- `history_error_verdict(exc: HistoryError) -> Verdict` — the one classification point for CLI and MCP.

### Call Path

- CLI/MCP boundary → `with strict_reads()` → `resolve_history_target(None, root=project_root)` → reader/`issue_history` graph → `_connect_readonly` → `open_history_readonly` (read-mode ensure, `check_access(write=False)`). Failures propagate to `history_error_verdict`. A `RemoteTarget` never reaches a local `Path` API.

## Scope Boundaries

- **In scope:** remote strict mode, `HistorySchemaUninitialized` at the strict boundary, HTTP-status preservation, negative verification-cache recovery, `history_error_verdict`, `_store_missing`, the static guard test, and regression tests. Reuse ENH-3700's read-mode ensure; do not add a version-0 exception to the shared `check_access` read branch.
- **Out of scope:** flipping any command row (ENH-3684, ENH-3685), keep-refuse/degrade rows (`analyze`, `activity`, `quality --workspace`, `summary`, `ll-logs diff`/`eval-export`, `ll-messages --reader db`, `ll-session search --fts`), writer/startup paths (BUG-3652), hand-built paths (ENH-3658), prepatch reads (ENH-3682).
- **Coordination:** ENH-3700 also edits `_connect_readonly` (re-raises only `HistoryRemoteRefused`); it lands first (`blocked_by`); rebase and re-run its refusal tests.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/{backend.py,remote_schema.py,libsql.py,hrana.py}`, `history_reader/_base.py`, `history_reader/{formatting,runs}.py` (three catch sites), ENH-3657's shared verdict helper, a new `strict` module or section under `session_store`.
- Tests: `test_remote_operation_matrix.py`, focused `session_store` and `history_reader` tests using ENH-3677's shared `remote` fixture, and the AST guard test.
- Docs: `docs/reference/API.md` (new symbols); `docs/reference/CONFIGURATION.md` only if the stale-store read rule is user-visible.

### Similar Patterns

- `session_store.targets.LocalTarget` / `RemoteTarget`, `open_history_readonly`, `cli/doctor.py:_remote_target()`, `remote_telemetry.warn_once`.

## Implementation Steps

1. Add remote-scoped `strict_reads()` with nested/failure reset tests; add `HistorySchemaUninitialized` at the strict boundary only. Reuse read-mode ensure and leave local and ordinary read semantics intact.
2. Preserve `http_status` in Hrana errors; implement the fixed error catalogue, exact exit/JSON/MCP contract, stamp checks and version-0 cache recovery.
3. Add `_store_missing(target)` and thread typed targets through reached readers. Keep local query-error fallbacks; re-raise remote failures under strict mode at the three broad catch sites.
4. Add the AST gate with reasoned catch exemptions and dynamic failure tests. Confirm explicit best-effort overrides strictness.
5. Test exact/behind success, ahead refusal, uninitialized, missing/foreign stamp, 401/403, 503, unreachable and mid-query failure; a long-lived reader recovers after initialization; safe output excludes a canary endpoint/token even when present in the raw exception. Use focused pairs, not a full Cartesian matrix. Run `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/`.

## Impact

- **Priority:** P4 — opt-in remote backend; clean interim refusals available.
- **Effort:** Medium — strict remote failure handling, boundary classification and verification-cache recovery across a shared seam.
- **Risk:** Medium — ambient strictness and verification-cache changes must not alter local or best-effort callers.
- **Breaking Change:** No for local users.

## Acceptance Criteria

- [ ] Under `strict_reads()` on a `RemoteTarget`, `_connect_readonly` raises for unreachable, uninitialized, project-mismatch, and auth-failure stores; local targets and callers outside it keep their behavior (BUG-3652 callers still return `None`/empty quietly).
- [ ] `HistorySchemaUninitialized` is raised for a reachable version-0 store and never triggers `mark_unreachable`; exact and behind stamped stores are served and ahead stores refused on strict reads (ENH-3700's rule); the strict open never migrates or runs a write-mode check; `HistorySchemaUninitialized` is not raised outside `strict_reads()`.
- [ ] A mid-query remote failure raises to the boundary, never an empty success. Successful result parity is preserved; existing local query-error-to-empty behavior is unchanged.
- [ ] HTTP status survives classification: 401/403 map to `authentication_failed`, 503/network/timeout to `unavailable`; generic `SQLITE_UNKNOWN` is not automatically schema mismatch. Every error follows the exact exit-1/JSON/MCP contract above and excludes canary hosts/tokens from raw exceptions.
- [ ] Version 0 is uninitialized; missing/foreign migrated project stamps are rejected; after initialization by another process a long-lived reader recovers without restart.
- [ ] ContextVar state is restored after nested scopes and exceptions; `best_effort=True` overrides ambient strict mode. The catch audit allows deliberate fallback/re-raise and boundary handlers; injected failures prove no strict remote error is swallowed.
- [ ] No `RemoteTarget` reaches `Path.exists`, `Path(...)`, `sqlite3.connect`, or `ATTACH`.
- [ ] `python -m pytest scripts/tests/` passes.

## Related

- ENH-3684 (`ll-history` flips), ENH-3685 (MCP + SFT), ENH-3657 (refuse boundary), ENH-3700 (central guard + read-mode ensure; blocked_by), ENH-3677 (shared remote fixture; blocked_by), ENH-3658, ENH-3682, BUG-3652, FEAT-3535. ENH-3670 was cancelled and absorbed by ENH-3658.

## Related Key Documentation

- `docs/reference/CONFIGURATION.md` (Remote history backend), `docs/reference/API.md`.

## Status

**Deferred** | Created: 2026-09-29 | Priority: P4 | Re-scoped to infrastructure slice 2026-09-30

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Blocked by ENH-3700 (read-mode ensure) and builds on ENH-3657's boundary helper. This issue reuses ENH-3700's read-mode ensure and extends ENH-3657's boundary error-verdict helper (`history_error_verdict`) with the new classes (uninitialized, schema/project mismatch, 401/403, unavailable) and the MCP JSON shape; strict adds remote raise-instead-of-`None`, the boundary-only version-0 check, retained HTTP status, safe error classification and negative-cache recovery. Shared non-strict read access does not gain a version-0 exception. Reconcile the `ll-harness` quiet-degrade wording with ENH-3700's serve verdict when landing.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:25 - `813546cd-0058-4cf8-a1bc-da17040cac6b.jsonl`
