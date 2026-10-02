---
id: ENH-3668
type: ENH
title: Build strict-read infrastructure for HistoryTarget-aware history readers
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T21:52:34Z'
blocked_by:
- ENH-3677
- ENH-3657
blocks:
- ENH-3684
- ENH-3685
relates_to:
- BUG-3652
- ENH-3657
- ENH-3682
parent: EPIC-3693
epic: EPIC-3693
---

# ENH-3668: Build strict-read infrastructure for HistoryTarget-aware history readers

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

- **`strict_reads()` context manager** (a `contextvars.ContextVar`, in `little_loops.session_store`), entered by each serve boundary (CLI/MCP/loop). While active, `_connect_readonly` raises instead of returning `None`. Outside it, behavior is unchanged, so BUG-3652 hook/digest/`ll-harness` callers keep their quiet degrade. A context variable, not a threaded kwarg: the `quality → agent_quality → rework` chain makes kwarg threading easy to miss. (Dissent noted in review: an explicit kwarg or target attribute is more traceable; rejected for the reason above.)
- **Strict remote open** uses `ensure=False` plus an eager `check_access(write=False)` probe; it never migrates and never runs the write-mode check. Stale (`0 < version < total`) and ahead stores are **served**; project-id mismatch and missing `project_id` still raise.
- **`HistorySchemaUninitialized`**: new subclass of `HistoryUnsupported` (**not** `HistoryUnavailable`, so telemetry `mark_unreachable` cannot fire on a reachable store). Raised in the read branch of `check_access` when the state is version 0 (no `meta` table). Note: this changes every remote read-only statement that passes `_guard`, including telemetry reads, so it needs its own regression tests.
- **Schema-mismatch classification**: a remote "no such table" `HranaOperationError` is classified as schema mismatch at the boundary, giving the same user-visible result as the local twin.
- **`history_error_verdict(exc) -> Verdict`** in one shared boundary helper used by CLI and MCP: maps `HistoryUnavailable`, `HistorySchemaUninitialized`, schema mismatch, project mismatch, and auth 401/403 to a stable exit code, one stderr line, and a JSON error shape; never includes the endpoint or token.
- **Target-aware guard** `_store_missing(target)` replaces `.exists()` gating: a `RemoteTarget` never enters `Path.exists`, `Path(...)`, `sqlite3.connect`, or `ATTACH`; local missing-file behavior is unchanged.
- **Signatures**: reader and `issue_history` functions accept `Path | str | HistoryTarget | None`; the boundary resolves once with `resolve_history_target(None, root=project_root)` (an absolute `.ll/history.db` is already default-shaped per `_is_default_shaped`, so no separate shadow-file fix is needed there).
- **Static guard test**: an AST test asserting no function on a serve-path call graph catches `HistoryError` or bare `Exception` (the three sites above are widened or re-raise under `strict_reads()`).

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

- `open_history_readonly(target: Path | str | HistoryTarget | None = None, *, ensure: bool = False, strict: bool = False) -> Connection` — `strict=True` (used by `_connect_readonly` when `strict_reads()` is active) skips `ensure_schema` for remote, runs `check_access(write=False)`, and raises rather than relying on caller-side `None` mapping.
- `history_error_verdict(exc: HistoryError) -> Verdict` — the one classification point for CLI and MCP.

### Call Path

- CLI/MCP boundary → `with strict_reads()` → `resolve_history_target(None, root=project_root)` → reader/`issue_history` graph → `_connect_readonly` → `open_history_readonly(strict=True)` → `check_access(write=False)`. Failures propagate to `history_error_verdict`. A `RemoteTarget` never reaches a local `Path` API.

## Scope Boundaries

- **In scope:** `strict_reads()`, strict open, `HistorySchemaUninitialized`, read-mode `check_access` change, `history_error_verdict`, `_store_missing`, the static guard test, and regression tests. Touches `session_store/{backend,remote_schema,libsql}.py`, `history_reader/_base.py`, and the three `HistoryError` catch sites.
- **Out of scope:** flipping any command row (ENH-3684, ENH-3685), keep-refuse/degrade rows (`analyze`, `activity`, `quality --workspace`, `summary`, `ll-logs diff`/`eval-export`, `ll-messages --reader db`, `ll-session search --fts`), writer/startup paths (BUG-3652), hand-built paths (ENH-3658), prepatch reads (ENH-3682).
- **Coordination:** ENH-3657 also edits `_connect_readonly` (narrows its re-raise to `HistoryRemoteRefused`); land in either order but rebase and re-run the ENH-3657 refusal tests.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/{backend.py,remote_schema.py,libsql.py}`, `history_reader/_base.py`, `history_reader/{formatting,runs}.py` (three catch sites), a new `strict` module or section under `session_store`.
- Tests: `test_remote_operation_matrix.py`, focused `session_store` and `history_reader` tests using ENH-3677's shared `remote` fixture, and the AST guard test.
- Docs: `docs/reference/API.md` (new symbols); `docs/reference/CONFIGURATION.md` only if the stale-store read rule is user-visible.

### Similar Patterns

- `session_store.targets.LocalTarget` / `RemoteTarget`, `open_history_readonly`, `cli/doctor.py:_remote_target()`, `remote_telemetry.warn_once`.

## Implementation Steps

1. Add `HistorySchemaUninitialized` and the read-branch version-0 check in `check_access`; regression-test telemetry reads and no `mark_unreachable` on uninitialized.
2. Add `strict` to `open_history_readonly` (remote: `ensure=False` + `check_access(write=False)`); add `strict_reads()` and make `_connect_readonly` honor it.
3. Add `_store_missing(target)` and `history_error_verdict`; classify remote "no such table" as schema mismatch.
4. Widen or re-raise the three `HistoryError` catch sites under `strict_reads()`; add the AST guard test.
5. Tests: behind, ahead, uninitialized, project mismatch, 401/403, unreachable, mid-query `fail_next`, local twin parity; BUG-3652 regression that non-strict callers still degrade quietly. Run `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/`.

## Impact

- **Priority:** P4 — opt-in remote backend; clean interim refusals available.
- **Effort:** Medium — one shared seam, but with a wide regression surface (`check_access` read branch).
- **Risk:** Medium — the read-branch change touches every remote read-only statement.
- **Breaking Change:** No for local users.

## Acceptance Criteria

- [ ] Under `strict_reads()`, `_connect_readonly` raises for unreachable, uninitialized, project-mismatch, and auth-failure stores; outside it, behavior is unchanged (BUG-3652 callers still return `None`/empty quietly).
- [ ] `HistorySchemaUninitialized` is raised for a reachable version-0 store and never triggers `mark_unreachable`; stale-but-stamped and ahead stores are served on strict reads; the strict open never migrates or runs a write-mode check.
- [ ] A mid-query remote failure (`fail_next` after a successful open) raises through to `history_error_verdict` on a serve-path call, never an empty result; a remote "no such table" matches the local twin's user-visible result.
- [ ] `history_error_verdict` yields a stable exit code, one stderr line, and a JSON error shape for each class, with no endpoint or token in any output.
- [ ] No serve-path function catches `HistoryError`/`Exception` (AST test), and no `RemoteTarget` reaches `Path.exists`, `Path(...)`, `sqlite3.connect`, or `ATTACH`.
- [ ] `python -m pytest scripts/tests/` passes.

## Related

- ENH-3684 (`ll-history` flips), ENH-3685 (MCP + SFT), ENH-3657 (interim verdicts; coordinate on `_connect_readonly`), ENH-3677 (shared remote fixture; blocked_by), ENH-3658, ENH-3682, BUG-3652, FEAT-3535. ENH-3670 was cancelled and absorbed by ENH-3658.

## Related Key Documentation

- `docs/reference/CONFIGURATION.md` (Remote history backend), `docs/reference/API.md`.

## Status

**Open** | Created: 2026-09-29 | Priority: P4 | Re-scoped to infrastructure slice 2026-09-30

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Blocked by ENH-3657. This issue reuses ENH-3657's read-mode ensure and extends its boundary error-verdict helper (`history_error_verdict`) with the new classes (uninitialized, schema/project mismatch, 401/403, unavailable) and the MCP JSON shape; strict adds only raise-instead-of-`None` and the version-0 `HistorySchemaUninitialized` check. Reconcile the `ll-harness` quiet-degrade wording with ENH-3657's serve verdict when landing.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:25 - `813546cd-0058-4cf8-a1bc-da17040cac6b.jsonl`
