---
id: BUG-3432
type: BUG
title: ll-queue list and ll-mcp queue_list crash with traceback and empty stdout on
  locked queue.db
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T01:41:55Z'
---

# BUG-3432: ll-queue list and ll-mcp queue_list crash with traceback and empty stdout on locked queue.db

## Summary

`ll-queue list` (`scripts/little_loops/cli/queue.py:249`) calls `queue_store.list_entries(QUEUE_DB_PATH)` with no exception guard, and `ll-mcp`'s `queue_list` tool (`scripts/little_loops/mcp_server/tools.py:478-489`) calls the same `list_entries` the same way. `.ll/queue.db` is a separate file from `history.db` with its own 5000 ms `PRAGMA busy_timeout` (`queue_store.py:202-214`). When a concurrent writer (`ll-queue run --watch`, `ll-auto`, `ll-parallel` workers) holds the lock past that timeout, `sqlite3.OperationalError("database is locked")` propagates straight out of `cmd_list`: traceback on stderr, exit 1, nothing on stdout. A machine consumer of `ll-queue list --json` gets an empty payload with no JSON to parse.

Split out of ENH-3426, which was captured from an ll-console report of exactly this symptom (`ll-queue list --json` dying with empty stdout) but mis-attributed it to a locked `history.db`. ENH-3426's own verification showed the `cli_event_context` history writer already guards that lock path and cannot produce a non-zero exit with empty stdout; the unguarded `queue.db` read here is the plausible cause. ENH-3426 hardens the history writer only and explicitly leaves this path out of scope.

## Current Behavior

- `cmd_list` (`cli/queue.py:245-260`) reads `list_entries(QUEUE_DB_PATH)` before any output is produced. A lock held past `busy_timeout` raises out of the command with a traceback and exit 1; `--json` consumers see empty stdout.
- `_tool_queue_list` (`mcp_server/tools.py:478-489`) has the same exposure over MCP stdio; ll-console's `queue_client.py` moved onto this tool on 2026-09-09 (commit `56448d3` in ll-console), so the MCP path is now the primary consumer.
- `queue_store.connect` (`queue_store.py`) applies `PRAGMA busy_timeout = 5000` and WAL best-effort, so short contention already waits; only contention longer than 5 s reaches the caller.

## Expected Behavior

A read-only `ll-queue list` (CLI and MCP tool) should not crash with a traceback on lock contention. `--json` should still emit a parseable payload on stdout. Either the read is retried briefly on `database is locked` (the store already has a backoff helper for writers, `queue_store.py:190-198`), or the failure is reported as a structured error: one-line stderr diagnostic plus a JSON error object on stdout for `--json`, and a `McpError`/structured error for the MCP tool. Decide which; do not silently return `[]` for a lock, since an empty queue and an unreadable queue must stay distinguishable to consumers.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/queue.py` (`cmd_list`, `:245-260`)
- `scripts/little_loops/mcp_server/tools.py` (`_tool_queue_list`, `:478-489`)
- Possibly `scripts/little_loops/queue_store.py` if a read-side retry helper is added next to the existing writer backoff

### Tests
- `scripts/tests/test_cli_queue.py` (autouse fixture already isolates `.ll/queue.db` per test via `monkeypatch.chdir(tmp_path)`)
- `scripts/tests/test_feat_queue_mcp_tools.py`
- `scripts/tests/test_queue_store.py`

## Program Design

### Signatures

- `cmd_list(args: argparse.Namespace) -> int` (`cli/queue.py:245`) — wrap the existing `list_entries` call in `try`/`except sqlite3.OperationalError`
- `_tool_queue_list(_arguments: dict[str, Any], *, project_root: Path) -> Any` (`mcp_server/tools.py:478`) — same wrap

### Call Path

`cmd_list` -> `queue_store.list_entries` (raises `sqlite3.OperationalError` on lock) -> caught -> `cli.output.print_json({"error": msg, "locked": True})` (json mode) or `print(msg, file=sys.stderr)` (text mode), `return 1` — mirrors the existing `AmbiguousEntryIdError`/not-found handling in `cli/queue.py:283-300`.

`_tool_queue_list` -> `queue_store.list_entries` (raises `sqlite3.OperationalError` on lock) -> caught -> `raise ValueError(msg)` — matches the `raise ValueError(...)` convention used by every other `_tool_*` function in `mcp_server/tools.py` for tool-level failures (e.g. `:141`, `:502`, `:600`).

## Impact

- **Priority**: P3 - Read-only CLI/MCP crash under lock contention; hits automation consumers (`ll-auto`, `ll-parallel`, `ll-queue run --watch`) but is not data loss and has a race-dependent trigger, consistent with existing P3.
- **Effort**: Small - Reuses the `try`/`except` + `print_json({"error": ...})` + `return 1` pattern already present in `cmd_status`/`cmd_remove` (`cli/queue.py:283-300`) and the `raise ValueError` convention already used by every other `_tool_*` function in `tools.py`; no new abstractions or store-layer changes needed.
- **Risk**: Low - Read-only path, purely additive exception handling around an existing call; behavior on the non-locked path is unchanged.
- **Breaking Change**: No - `--json` success-case payload shape is unchanged; the failure case, which previously exited with a traceback, now gains a distinguishable `error`/`locked` key instead.

## Steps to Reproduce

1. Open a second connection to `.ll/queue.db` and hold `BEGIN IMMEDIATE` for longer than 5 s (or monkeypatch `queue_store.connect` to raise `sqlite3.OperationalError("database is locked")`, the pattern used throughout `scripts/tests/` for locked-DB cases).
2. Run `ll-queue list --json`.
3. Observe traceback on stderr, exit 1, empty stdout.

## Related

- ENH-3426 — hardens `cli_event_context` (history.db side); this BUG covers the queue.db side it scoped out.
- ENH-2927 — default queue.db path resolution (`_resolve_queue_db_path`).
- BUG-2706 — the analogous locked-DB fix for `cli_event_context`.

## Status

**Open** | Created: 2026-09-10 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-10T02:20:14 - `53454f7b-c63c-4adf-8a13-82f32f7513d8.jsonl`
