---
id: ENH-3684
type: ENH
title: Serve ll-history rework, quality, collisions, sessions, root from a remote
  history store
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T05:20:50Z'
blocked_by:
- ENH-3657
- ENH-3668
relates_to:
- ENH-3677
- ENH-3658
- ENH-3682
- BUG-3652
---

# ENH-3684: Serve ll-history rework, quality, collisions, sessions, root from a remote history store

## Summary

Flip the `ll-history` reader rows `rework`, `quality` (single-project), `audit-issue-collisions`, `sessions`, and `root` from ENH-3657's interim refusal to real remote reads, using the strict-read infrastructure from ENH-3668 (`strict_reads()`, `history_error_verdict()`, `HistorySchemaUninitialized`, read-mode `check_access`). Split from the original ENH-3668 (2026-09-30 Opus review).

## Current Behavior

After ENH-3657, these commands refuse cleanly under `history.backend.provider: libsql`. The nine `resolve_history_db(project_root / DEFAULT_DB_PATH)` sites in `cli/history.py` pass no `root=`, so backend config is found by a cwd walk rather than from `project_root`. Reader functions do `Path(db)` and some `.exists()`-gate, so a remote target cannot pass through them.

## Expected Behavior

| Site | Remote outcome | Main call path |
|---|---|---|
| `ll-history rework` | **serve** | `issue_history.rework.analyze_rework` |
| `ll-history quality` without `--workspace` | **serve** | `quality_regressions`, `agent_quality`, `rework` |
| `ll-history audit-issue-collisions` | **serve** | `issue_history.collisions.audit_issue_collisions` |
| `ll-history sessions`, `root` | **serve** | `history_reader.sessions`, digest/root helpers; `root` has a direct connection site |
| `analyze`, `activity`, `quality --workspace` | **keep ENH-3657 refusal** | `evolution._open_db` and `ATTACH` aggregation are SQLite-specific; `quality --workspace` refuses before `ATTACH` or member-file checks |
| `summary` | **keep file-scan degrade** | unchanged |

Each serve row enters `strict_reads()` at the CLI boundary, resolves once with `resolve_history_target(None, root=project_root)`, and reports failures through `history_error_verdict()` (one stderr line, non-zero exit, no traceback, no endpoint or token). `ll-history` defines no `--db`, so no local-override flag clause applies to these rows; `LL_HISTORY_DB` still forces local.

A reachable migrated store with zero rows returns an empty result; a local "no such table" and its remote twin (`HranaOperationError` classified as schema mismatch) must give the same user-visible result as the local twin.

## Motivation

Remote users cannot use these history views until the interim refusals are replaced with real reads; the strictness work is shared and lives in ENH-3668.

## Proposed Solution

Wrap each serve row's CLI handler in `strict_reads()`, resolve once at the boundary, drop `Path(db)`/`.exists()` on the reached call paths, and route failures through `history_error_verdict()`. See Expected Behavior and Implementation Steps.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py` (nine `resolve_history_db` sites), `issue_history/{rework,quality_regressions,agent_quality,collisions}.py`, `history_reader/{sessions,digest}.py` where reached.

### Dependent Files (Callers/Importers)
- `cli/history.py` handlers for `rework`, `quality`, `audit-issue-collisions`, `sessions`, `root`; `aggregate_history_dbs` (workspace mode stays refused).

### Similar Patterns
- ENH-3657's boundary refusal helper; ENH-3668's `strict_reads()`.

### Tests
- `test_remote_operation_matrix.py`, `test_cli_history.py`, focused reader/issue-history tests with ENH-3677's `remote` fixture, local twins.

### Documentation
- `docs/reference/CLI.md`, `docs/reference/CONFIGURATION.md` (reader table), `docs/reference/API.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`.

### Configuration
- No new config key.

## Program Design

### Types

- Reuses `HistoryTarget`, `strict_reads()` and `Verdict` from ENH-3668; no new types.

### Signatures

- `analyze_rework(db: Path | str | HistoryTarget | None = None, ...) -> ReworkAnalysis` — accepts the boundary-resolved target; no `Path(db)` coercion.
- `audit_issue_collisions(db: Path | str | HistoryTarget | None, issues_dir: Path | str) -> list[CollisionGroup]` — same union; raises under `strict_reads()` instead of returning `[]` on open failure.

### Call Path

- `cli.history.main` → `strict_reads()` → `resolve_history_target(None, root=project_root)` → `analyze_rework` / `audit_issue_collisions` / `sessions_for_issue` → `_connect_readonly` → `history_error_verdict` on `HistoryError`.

## Implementation Steps

1. Land ENH-3657 and ENH-3668 (infra). Confirm the interim verdict table.
2. Trace each serve row's call graph; remove `Path(db)` coercion and `.exists()` gates on paths reached by these rows (keep local missing-file behavior); accept `Path | str | HistoryTarget | None`.
3. Flip rows one at a time; remove only that row's interim refusal text from the CONFIGURATION.md reader table.
4. Tests (use the shared `remote` fixture from ENH-3677): remote-stub + local-twin per row; assert no local `.ll/history.db` is created; `fail_next` mid-query failure reports unavailable; uninitialized store reports `HistorySchemaUninitialized`; exit-code and JSON error shape.
5. Docs: `docs/reference/CLI.md`, `CONFIGURATION.md` reader table, `API.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`. Run `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/`.

## Impact

- **Priority:** P4 — opt-in remote backend; clean interim refusals exist.
- **Effort:** Medium — plumbing through four `issue_history` modules and `history_reader.sessions`.
- **Risk:** Medium — local behavior must stay byte-stable.

## Scope Boundaries

- **In scope:** the serve rows above and their `issue_history` / `history_reader` call paths; `cli/history.py` boundary.
- **Out of scope:** MCP `history_search` and SFT `enrich` (ENH-3685), infra (ENH-3668), keep-refuse/degrade rows, writer/startup paths (BUG-3652), hand-built paths (ENH-3658), prepatch reads (ENH-3682).

## Acceptance Criteria

- [ ] Every serve row returns the same data shape from a migrated remote stub and a local twin; keep rows retain their ENH-3657 behavior.
- [ ] No serve row creates `.ll/history.db` under remote config or coerces `Path(RemoteTarget)`; `quality --workspace` refuses before `ATTACH`.
- [ ] Empty migrated, uninitialized, unreachable, and mid-query-failure stores are distinguished in CLI output with the shared exit code and error shape, without exposing secrets.
- [ ] A stale (behind or ahead) but stamped store is served or reported per ENH-3668's rule; project-id mismatch and 401/403 give a distinct, secret-free message.
- [ ] Non-serve callers (hooks, digest, `ll-harness`) keep their BUG-3652 quiet-degrade behavior (regression test).
- [ ] `python -m pytest scripts/tests/` passes.

## Related

- ENH-3668 (infra; blocked_by), ENH-3657 (interim verdicts; blocked_by), ENH-3677 (shared fixture), ENH-3685 (MCP `history_search` + SFT `enrich`), ENH-3658, ENH-3682, BUG-3652, FEAT-3535.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-30 | Priority: P4
