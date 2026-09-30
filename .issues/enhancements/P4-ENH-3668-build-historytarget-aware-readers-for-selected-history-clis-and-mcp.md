---
id: ENH-3668
type: ENH
title: Build HistoryTarget-aware readers for selected history CLIs and MCP
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T21:52:34Z'
blocked_by:
- ENH-3657
relates_to:
- BUG-3652
- ENH-3682
---

# ENH-3668: Build HistoryTarget-aware readers for selected history CLIs and MCP

## Summary

Serve a **defined set** of `ll-history` readers, MCP `history_search`, and SFT enrichment from an opt-in remote libSQL store. ENH-3657 gives them interim refuse/degrade verdicts. This issue replaces only the serve rows below with real remote reads through typed `HistoryTarget` plumbing. Local-only analysis and workspace modes retain their named refusal until separately scoped.

## Current Behavior

After ENH-3657, the listed reader CLIs and MCP tool refuse cleanly under remote config, while `history summary` degrades to the file scan. Many readers accept `Path | str`, test `.exists()`, or coerce with `Path(db)`; an absolute default-shaped path can become a `LocalTarget` and create an empty shadow `.ll/history.db`. `_connect_readonly` also maps ordinary `HistoryError` to `None`, conflating an unreachable endpoint with empty data.

## Expected Behavior

Resolve once at each CLI/MCP boundary with the owning project root; pass a `HistoryTarget` through the in-scope reader call graph. The following matrix is the acceptance boundary:

| Site | Remote outcome after this issue | Main call path |
|---|---|---|
| `ll-history rework` | **serve** | `issue_history.rework` |
| `ll-history quality` without `--workspace` | **serve** | `issue_history.quality_regressions`, `agent_quality`, `rework` |
| `ll-history audit-issue-collisions` | **serve** | `issue_history.collisions` |
| `ll-history sessions`, `root` | **serve** | `history_reader.sessions`, `history_reader` digest/root helpers; `root` has a direct connection site |
| MCP `history_search` | **serve** | `mcp_server.tools` → `history_reader.search` with `root=project_root` |
| `loops/sft-corpus.yaml` `enrich` | **serve** | `history_reader.sessions.lookup_session_metadata` |
| `ll-history analyze`, `activity`, `quality --workspace` | **keep ENH-3657 refusal** | `evolution._open_db` and workspace aggregation remain local/SQLite-specific |
| `ll-history summary` | **keep file-scan degrade** | Correct interim fallback; remote summary is not promised here |
| `ll-logs diff`, `eval-export`; `ll-messages --reader db`; `ll-session search --fts` | **keep existing verdicts** | Not part of this serve slice |

A reachable migrated store with zero rows returns an empty result. An unreachable store gives an unavailable error, and a reachable but unmigrated store gives an uninitialized-schema error; neither is reported as "no data" or creates a local file. A local `LL_HISTORY_DB` override remains local. Only CLIs that actually define `--db` retain that flag's local behavior.

## Motivation

An interim clean refusal is preferable to a traceback, but remote users still cannot use these history views. Typed targets are necessary because dropping `resolve_history_db()` pre-resolves while retaining absolute-path coercion can silently read or create a shadow local store.

## Proposed Solution

1. Accept `Path | str | HistoryTarget | None` at the in-scope `history_reader` and `issue_history` functions. Resolve at the boundary with `resolve_history_target(path, root=project_root)`; pass the target onward without `Path(RemoteTarget)` or `.exists()` on remote targets. Keep local missing-file behavior.
2. Make readonly open/reporting distinguish empty migrated, reachable unmigrated, and unreachable remote stores. Reuse ENH-3657's read-mode `check_access(write=False)`; do not migrate a remote store on read.
3. Flip only the **serve** rows in the matrix. For `quality`, cover single-project mode; preserve a named refusal for its `ATTACH`-based workspace mode. Remove each flipped row from the interim remote-support table and retain rows that still refuse/degrade.
4. Keep the prepatch base-SHA best-effort timeout change separate in ENH-3682; it is not a prerequisite for the served commands.

## Scope Boundaries

- **In scope:** the exact serve rows and their reader/issue-history call paths, MCP project-root resolution, SFT metadata enrichment, local twins and remote-state errors.
- **Out of scope:** the explicit keep-refuse/degrade rows, writer/startup paths (BUG-3652), hand-built artifact paths (ENH-3658), and budgeted advisory prepatch reads (ENH-3682).

## Integration Map

### Files to Modify

- `scripts/little_loops/history_reader/{_base,sessions,search,summary_dag,usage,runs,context,formatting}.py` only where reached by a serve row; `issue_history/{rework,quality_regressions,agent_quality,collisions}.py`; `cli/history.py`; `mcp_server/tools.py`; the `session_store` readonly adapter as needed. Re-trace the call graph before editing so an in-scope path cannot coerce `Path(RemoteTarget)`.
- Tests: `test_remote_operation_matrix.py`, `test_cli_history.py`, `test_mcp_server.py`, `test_enh_3171_mcp_project_root.py`, and focused reader/issue-history tests using ENH-3677's shared `remote` fixture. Include local twins and a foreign-cwd MCP case.
- Docs: `docs/reference/CLI.md`, `CONFIGURATION.md` remote reader table, `API.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/guides/MCP_SERVER_GUIDE.md`.

### Similar Patterns and Configuration

- `session_store.targets.LocalTarget` / `RemoteTarget`, `open_history_readonly`, and `cli/doctor.py:_remote_target()` are the typed-target patterns. No new config key is required.

## Program Design

### Types

- `HistoryTarget = LocalTarget | RemoteTarget`; a readonly result/error distinguishes `empty`, `uninitialized_schema`, and `unavailable` without exposing a token or remote URL.

### Signatures

- `open_history_readonly(target: HistoryTarget, *, ensure: bool = False) -> Connection` — opens the already-resolved target without a local Path coercion.
- In-scope reader functions accept `Path | str | HistoryTarget | None` during migration; the CLI/MCP boundary supplies a `HistoryTarget` so inner calls do not resolve again.

### Call Path

- CLI/MCP boundary → `resolve_history_target(..., root=project_root)` → typed reader/issue-history call graph → readonly backend. A `RemoteTarget` never enters a local `Path.exists`, `sqlite3.connect`, or `ATTACH` path.
- Keep-refuse rows still use ENH-3657's boundary helper. `quality --workspace` refuses before local aggregation. Never turn a remote failure into a successful empty result.

## Implementation Steps

1. Land ENH-3657 and confirm the interim verdict table. Trace every serve-row call path and propagate `HistoryTarget` through it, including `issue_history` and the `root` direct connection.
2. Implement remote empty/uninitialized/unavailable distinctions and flip serve rows one at a time, removing only their interim refusal text.
3. Add remote-stub and local-twin tests for each matrix row; assert no local `.ll/history.db` is created. Exercise MCP with config at `project_root` and a foreign cwd.
4. Update docs; run `python -m pytest scripts/tests/`, `ruff check scripts/`, and `python -m mypy scripts/little_loops/`.

## Impact

- **Priority:** P4 — opt-in remote backend, with clean interim refusals available.
- **Effort:** Large — typed-target plumbing through shared readers and several `issue_history` modules.
- **Risk:** Medium — local behavior and error classification must remain stable.
- **Breaking Change:** No for local users.

## Acceptance Criteria

- [ ] Every **serve** row in the matrix returns the same data shape from a migrated remote stub and a local twin; every keep-refuse/degrade row retains its named ENH-3657 behavior.
- [ ] No served path creates `.ll/history.db` under remote config or coerces `Path(RemoteTarget)`; `quality --workspace` refuses before `ATTACH` or local member-file checks.
- [ ] Empty migrated, reachable unmigrated, and unreachable remote stores are distinguished in CLI and MCP results without exposing endpoint secrets.
- [ ] MCP `history_search` resolves against `project_root` under a foreign cwd; an applicable explicit local override remains local.
- [ ] SFT `enrich` serves session metadata remotely; existing local behavior and `python -m pytest scripts/tests/` pass.

## Related

- ENH-3657 (interim reader verdicts; land first), ENH-3677 (shared remote fixture), ENH-3658 (artifact path sibling), ENH-3682 (separate advisory prepatch timeout), BUG-3652 (done startup/write audit), FEAT-3535 (remote libSQL backend). ENH-3670 was cancelled and absorbed by ENH-3658.

## Related Key Documentation

- `docs/reference/CONFIGURATION.md` (Remote history backend), `docs/reference/CLI.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/guides/MCP_SERVER_GUIDE.md`.

## Status

**Open** | Created: 2026-09-29 | Priority: P4
