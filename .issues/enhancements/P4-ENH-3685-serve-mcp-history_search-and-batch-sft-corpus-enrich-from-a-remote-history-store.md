---
id: ENH-3685
type: ENH
title: Serve MCP history_search and batch sft-corpus enrich from a remote history
  store
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T05:20:51Z'
blocked_by:
- ENH-3668
- ENH-3657
relates_to:
- ENH-3684
- ENH-3677
- ENH-3682
---

# ENH-3685: Serve MCP history_search and batch sft-corpus enrich from a remote history store

## Summary

Serve MCP `history_search` and the `sft-corpus` `enrich` state from an opt-in remote libSQL store, using the strict-read infrastructure from ENH-3668. `enrich` gets a batched `lookup_session_metadata_batch` so remote cost is O(chunks), not O(examples). Split from the original ENH-3668 (2026-09-30 Opus review).

## Current Behavior

- MCP `_tool_history_search` resolves `resolve_history_db(project_root / DEFAULT_DB_PATH, root=project_root)` and calls `history_reader.search`; under remote config ENH-3657 refuses it.
- `loops/sft-corpus.yaml` `enrich` loops over JSONL examples calling `lookup_session_metadata(session_id)` with no `db` argument (cwd-assumed). Each call does `Path(db).exists()` (False for the default path under remote config, so it silently returns `{}`) and then about four sequential `SELECT`s on a fresh connection. Served remotely as-is this would cost N examples x 4 round trips plus connection setup.

## Expected Behavior

- MCP `history_search` enters `strict_reads()`, resolves with `resolve_history_target(None, root=project_root)`, and serves from remote under a foreign cwd; failures surface through `history_error_verdict()` as a structured MCP error. An explicit local override (`LL_HISTORY_DB`) remains local.
- Add `lookup_session_metadata_batch(session_ids, *, db=...) -> dict[str, dict]`: one connection, four grouped `IN` queries in chunks of 500 parameters, same per-session dict shape as `lookup_session_metadata`. The loop becomes two-pass (collect ids, one batch call, join). `lookup_session_metadata` stays for single lookups and is reimplemented over the batch.
- On a strict error `enrich` prints one stderr line and exits non-zero, with explicit `on_error`/failure routing in the loop; it must not write `metadata: {}` for every example. Verify how the FSM treats a non-zero exit from a shell state that only has `next:`.
- Update `sft-corpus.yaml` to pass the project db target explicitly rather than rely on cwd.

## Motivation

MCP `history_search` and SFT enrichment are the two non-CLI consumers; the SFT loop also needs a batch API to be usable remotely.

## Proposed Solution

Enter `strict_reads()` in `_tool_history_search`; add `lookup_session_metadata_batch` and rewrite `enrich` to use it. See Expected Behavior.

## Integration Map

### Files to Modify
- `scripts/little_loops/mcp_server/tools.py` (`_tool_history_search`), `history_reader/sessions.py` (new `lookup_session_metadata_batch`, re-export in `history_reader/__init__.py`), `scripts/little_loops/loops/sft-corpus.yaml` (`enrich`).

### Dependent Files (Callers/Importers)
- `cli/logs.py` (`lookup_session_metadata` at ~line 1996; may adopt the batch), `history_reader.search`.

### Similar Patterns
- ENH-3171/BUG-3181 project-root resolution in the MCP tools; FSM `$${...}` brace escaping in shell actions.

### Tests
- `test_mcp_server.py`, `test_enh_3171_mcp_project_root.py`, a batch-parity test for `history_reader/sessions.py`, `test_builtin_loops.py` (sft-corpus), remote-stub request-count test.

### Documentation
- `docs/guides/MCP_SERVER_GUIDE.md`, `docs/reference/CONFIGURATION.md` (reader table), `docs/reference/API.md`.

### Configuration
- No new config key.

## Program Design

### Types

- Reuses `strict_reads()` and `Verdict` from ENH-3668. Batch result type is `dict[str, dict]` keyed by session id, each value the existing `lookup_session_metadata` dict shape.

### Signatures

- `lookup_session_metadata_batch(session_ids: Sequence[str], *, db: Path | str | HistoryTarget | None = None) -> dict[str, dict]` — one connection, four grouped `IN` queries in chunks of 500 parameters; a session with no rows maps to the zero-valued dict, an unreachable store raises under `strict_reads()`.
- `lookup_session_metadata(session_id: str, *, db: Path | str | HistoryTarget | None = None) -> dict` — reimplemented over the batch; unchanged local behavior.

### Call Path

- MCP: `mcp_server.tools._tool_history_search` → `strict_reads()` → `resolve_history_target(None, root=project_root)` → `history_reader.search` → `history_error_verdict`.
- SFT: `sft-corpus.yaml` `enrich` → `lookup_session_metadata_batch` → `_connect_readonly`; a strict error exits non-zero with one stderr line.

## Implementation Steps

1. Land ENH-3668 (infra) and ENH-3657.
2. Implement `lookup_session_metadata_batch`; add local-twin parity tests against `lookup_session_metadata`.
3. Update `_tool_history_search`; add tests in `test_mcp_server.py` and `test_enh_3171_mcp_project_root.py` with config at `project_root` and a foreign cwd, plus local override.
4. Rewrite `enrich` in `sft-corpus.yaml` (mind `$${...}` brace escaping); `ll-loop validate sft-corpus`; test with a remote stub and count round trips.
5. Docs: `docs/guides/MCP_SERVER_GUIDE.md`, `docs/reference/CONFIGURATION.md` reader table, `API.md`. Run `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/`.

## Impact

- **Priority:** P4 — opt-in remote backend.
- **Effort:** Medium.
- **Risk:** Low-Medium — loop rewrite and MCP error shape.

## Scope Boundaries

- **In scope:** MCP `history_search`, `lookup_session_metadata_batch`, `sft-corpus.yaml` `enrich`.
- **Out of scope:** `ll-history` command flips (ENH-3684), infra (ENH-3668), `ll-logs eval-export` and other `lookup_session_metadata` callers unless trivially covered by the batch, prepatch reads (ENH-3682).

## Acceptance Criteria

- [ ] MCP `history_search` returns the same shape from a migrated remote stub and a local twin, resolves against `project_root` under a foreign cwd, and reports unavailable / uninitialized as structured errors.
- [ ] `enrich` against a remote stub issues O(chunks) requests (asserted by request count for N > 500 sessions), and batch output equals per-session `lookup_session_metadata` on the local twin.
- [ ] A strict failure in `enrich` halts the loop non-zero with one stderr line; it never writes empty metadata for all examples.
- [ ] No `.ll/history.db` is created under remote config; `python -m pytest scripts/tests/` and `ll-loop validate sft-corpus` pass.

## Related

- ENH-3668 (infra; blocked_by), ENH-3657, ENH-3677, ENH-3684 (`ll-history` command flips), ENH-3682, FEAT-3535.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-30 | Priority: P4
