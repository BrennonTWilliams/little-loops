---
id: ENH-3668
type: ENH
title: Build HistoryTarget-aware history readers so reader CLIs and MCP serve remote
  reads
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T21:52:34Z'
blocked_by:
- ENH-3657
relates_to:
- BUG-3652
---

# ENH-3668: Build HistoryTarget-aware history readers so reader CLIs and MCP serve remote reads

## Summary

Build `HistoryTarget`-aware history readers so `ll-history` reader subcommands and MCP `history_search` can read from a remote libSQL store (`history.backend.provider: libsql`, FEAT-3535) instead of refusing. ENH-3657 stops the tracebacks with refuse/degrade verdicts and serves only `ll-harness`; this issue replaces the interim refusals with real remote reads. Split out of ENH-3657 after the `/ll:advise` (Opus) review of 2026-09-29.

## Current Behavior

After ENH-3657, the in-scope `ll-history` subcommands and MCP `history_search` refuse under a remote backend with a named `HistoryUnsupported` (exit 1 / `is_error`); `history summary` degrades to the file scan. The readers cannot serve remote data because they take `Path | str`, gate on `.exists()`, and coerce with `Path(db)`.

## Expected Behavior

Each in-scope site reads from the remote store through a typed `HistoryTarget`, returns the same data a local store would, creates no local `.ll/history.db`, and reports an unreachable endpoint distinctly from an empty store.

## Motivation

ENH-3657 originally proposed "serving" ~11 reader sites by dropping the `resolve_history_db()` pre-resolve. That is unsafe for every site that passes an absolute path: `_resolve_once` treats an absolute path as a `LocalTarget` (BUG-3181), and `history_reader._connect_readonly` opens with `open_history_readonly(db, ensure=True)`, whose `ensure_schema` on a `LocalTarget` **creates an empty shadow `.ll/history.db`** and returns "no data". Only the relative-path `ll-harness` sites are safe to serve without typed-target plumbing. Remote users therefore lose these reads until this issue lands.

## Proposed Solution

1. Thread a typed target through the reader layer: accept `Path | str | HistoryTarget | None` in `history_reader.*` (no `Path(db)` coercion of a `RemoteTarget`, which raises `TypeError`); resolve once at the CLI/MCP boundary with `resolve_history_target(path, root=...)`.
2. Replace `.exists()` gates with a target-aware reachability check (`_target_available(target)`); an unreachable remote must be distinguishable from an empty store (today `_connect_readonly` maps `HistoryError` to `None`).
3. ~~Give `_connect_readonly` a read-mode remote check~~ — done in ENH-3657 (read-mode ensure in `open_history_readonly`); reuse it and verify each served subcommand against `HranaStub`.
4. Flip the ENH-3657 interim refusals to serve, one subcommand at a time; remove the refuse verdict and its row in the ENH-3657 `CONFIGURATION.md` reader-support table (ENH-3657 adds no `_REMOTE_REFUSALS`/`_REJECTED` entries).
5. `evolution._open_db` (sqlite-only, shared by `analyze` and CT-0): make it remote-aware or keep refusing.

## Integration Map

### Files to Modify
- `scripts/little_loops/history_reader/{_base,summary_dag,usage,runs,search,context,formatting,sessions,harness}.py`, `session_store/backend.py` (`open_history_readonly`, `_resolve_once`), `cli/history.py`, `mcp_server/tools.py`, `issue_history/evolution.py` (`_open_db`); refine with `/ll:refine-issue` before implementing.

### Dependent Files (Callers/Importers)
- Callers of `history_reader.*`: `cli/history.py`, `cli/harness.py`, `cli/logs.py`, `cli/ctx_stats.py`, `cli/history_context.py`, `cli/session.py` (`search --fts`), `user_messages.py`, `mcp_server/tools.py`.

### Similar Patterns
- `refuse_on_remote` / `open_history_readonly` typed-target handling in `session_store/`; `cli/doctor.py:_remote_target()`.

### Tests
- `scripts/tests/test_remote_operation_matrix.py`, `test_cli_history.py`, `test_mcp_server.py`, `test_enh_3171_mcp_project_root.py`, `test_history_store_chokepoint_gate.py`; shared `remote` fixture from BUG-3652.

### Documentation
- `docs/reference/CLI.md`, `CONFIGURATION.md` (Remote history backend), `API.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/guides/MCP_SERVER_GUIDE.md`; remove the interim-refusal notes ENH-3657 added.

### Configuration
- N/A or list config files

## Implementation Steps

1. Accept `HistoryTarget` in `history_reader.*` and resolve once at each boundary (`resolve_history_target(path, root=...)`); replace `.exists()` gates with a target-aware reachability check.
2. Flip ENH-3657's interim refusals to serve, one subcommand at a time, removing the matching row from the ENH-3657 reader-support table (no `_REMOTE_REFUSALS`/`_REJECTED` entries exist to delete); decide `evolution._open_db` (remote-aware vs keep refusing).
3. `HranaStub` tests per site plus local twins; assert no local `.ll/history.db` is created and that an unreachable endpoint is reported distinctly; run `python -m pytest scripts/tests/`, `ruff check`, `mypy`.

## Impact

- **Priority**: P4 - opt-in remote-backend users only; ENH-3657 already removes the tracebacks and keeps `ll-harness` and `ll-history summary` working.
- **Effort**: Large - typed-target plumbing through `history_reader.*`, a reachability probe, and per-subcommand flips of the interim refusals.
- **Risk**: Medium - touches the shared reader chokepoint (`_connect_readonly`); local behavior must stay unchanged.
- **Breaking Change**: No

## Scope Boundaries

In scope (sites ENH-3657 refuses in the interim):

- `cli/history.py`: `rework` (`:592`), `quality` (`:628`), `audit-issue-collisions` (`:755`), `sessions` (`:780`), `root` (`:797`), and, if a remote-capable path exists, `analyze` (`:551`) and `activity` (`:731`); `summary` already degrades to the file scan in ENH-3657.
- `mcp_server/tools.py:_tool_history_search` (`:172`, `root=project_root`).
- The `history_reader.*` readers those sites call (`summary_dag`, `usage`, `runs`, `search`, `context`, `formatting`) plus `history_reader.sessions` `.exists()` gates (`lookup_session_metadata`, `conversation_turns`) if `logs diff`/`eval-export` and `user_messages --reader db` are to be served.

Out of scope: refuse/degrade verdicts (ENH-3657), startup/write paths (BUG-3652), hand-built path sites (ENH-3658).

Also in scope (2026-09-30): serving `loops/sft-corpus.yaml` `enrich` (`lookup_session_metadata`), which ENH-3657 only degrades explicitly. Deleting ENH-3657's interim single support table entry per subcommand as each flips to serve.

## Acceptance Criteria

- [ ] Each in-scope site returns data through `HranaStub` under a remote config and creates **no** local `.ll/history.db` (assert absence).
- [ ] An unreachable endpoint is reported as such (not as "no data"), with no endpoint token in stderr.
- [ ] `--db` / `LL_HISTORY_DB` still read the local file; `python -m pytest scripts/tests/` passes.
- [ ] MCP `history_search` resolves the backend against `project_root`, with a remote-config-at-`project_root` + foreign-cwd test.
- [ ] **Budgeted best-effort read (moved from BUG-3652, sixth `/ll:advise` review, 2026-09-29).** BUG-3652 (landed `62ac0fc89`) ships the prepatch base-SHA read (`read_base_sha` / `read_base_dirty`) on the standard reader connection, so a black-holed endpoint can stall it for up to about 10 s per read. Add `open_history_readonly(..., best_effort: bool = False)`: for a `RemoteTarget` with `best_effort=True`, skip `ensure_schema` and open `LibsqlConnection(client(timeout=telemetry_timeout_ms), read_only=True, config=…, telemetry=True)` through a new `LibsqlBackend.connect_readonly_telemetry`, so `_guard` honors and `_run` sets the unreachable marker. Thread it through `_connect_readonly(..., best_effort=True)` for the two prepatch readers only. Add a black-holed-socket test double (accepts, never replies; `remote.stop()` fails instantly and cannot see the stall) asserting the read returns `None`, sets the marker, and sends no request once it is set. `telemetry_scope()` is not a shortcut: it only affects `schema.connect`.
- ~~**Read-only token limitation**~~ — moved into ENH-3657 (2026-09-30): harness serve needs the read-mode ensure (`check_access(write=False)`), so it lands there; ENH-3668 inherits it.

## Related

- ENH-3669 (batch loop-end `usage_events` writes) and ENH-3670 (skill/loop hand-built `.ll/history.db` paths) are siblings split from the same BUG-3652 review.

- ENH-3657 (interim refuse/degrade verdicts; land first).
- BUG-3652 (startup/write path).
- FEAT-3535 (remote libSQL history backend).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-29 | Priority: P4
