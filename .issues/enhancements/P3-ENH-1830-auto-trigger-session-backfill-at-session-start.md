---
id: ENH-1830
type: ENH
priority: P3
status: done
discovered_date: 2026-06-01
captured_at: '2026-06-01T01:10:54Z'
completed_at: '2026-06-01T04:57:16Z'
discovered_by: capture-issue
relates_to:
- FEAT-1262
- EPIC-1707
labels:
- enhancement
- captured
parent: EPIC-1707
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1830: Auto-trigger `session_store.backfill()` at session start

## Summary

The `session_start` hook currently only bootstraps the DB schema (`ensure_db()`).
It never calls `backfill()`, so interactive session content — user messages and tool
calls from JSONL — only reaches `history.db` if the user manually runs
`ll-session backfill`. Wire an automatic backfill call into the session start hook
so historical data is populated without manual intervention.

## Current Behavior

`session_start` hook (`hooks/session_start.py`) calls only `ensure_db()` to bootstrap the SQLite schema. It never invokes `backfill()`, so `message_events` and `tool_events` tables remain empty for interactive sessions unless the user manually runs `ll-session backfill`. As a result, `ll-session search`, `ll-history`, and the `history_reader` API return partial or no results for most projects.

## Motivation

`history.db` is designed to be a queryable record of project activity, but the
data it contains is largely incomplete for interactive sessions. The `message_events`
and `tool_events` tables depend on JSONL-backed backfill, which is never triggered
automatically. This means `ll-session search`, `ll-history`, and the `history_reader`
read API return partial or empty results for most projects unless someone remembers
to run `ll-session backfill` manually. FEAT-1262 (session-event-capture-hook) was
the original vehicle for continuous capture but was deferred/superseded by the
hook-intent abstraction (FEAT-1116) with no replacement created.

## Expected Behavior

- `session_start` hook (or its Python intent handler) calls `session_store.backfill()`
  after `ensure_db()` succeeds
- Backfill is incremental: only JSONL files modified since the last backfill timestamp
  are processed (avoid re-scanning all files on every session start)
- Backfill runs in a background thread or subprocess so it does not add latency to
  session startup (the hook's response must be fast)
- Errors in backfill are silently swallowed (same `contextlib.suppress` pattern as
  `ensure_db()`) so a backfill failure never blocks a session
- A `last_backfill_ts` timestamp is written to the `meta` table after each successful
  incremental run

## Scope Boundaries

- **Out of scope**: Real-time/continuous event capture during a session (deferred FEAT-1262 scope)
- **Out of scope**: Backfill of non-JSONL sources
- **Out of scope**: Changes to query interfaces (`ll-session search`, `ll-history`, `history_reader`)
- **Out of scope**: Surfacing backfill progress to the user (runs silently in background)

## Implementation Steps

1. Add `last_backfill_ts` key to the `meta` table (new migration, v6 — current `SCHEMA_VERSION = 5`
   in `session_store.py`; next migration is index 5 in `_MIGRATIONS`)
2. Discover JSONL files in `session_start.py` `handle()` before spawning the backfill thread
   (likely `~/.claude/projects/<project-hash>/*.jsonl`); resolve via `ll-logs discover` or
   equivalent; pass resulting list as `jsonl_files` arg to `backfill_incremental()`
3. Add `backfill_incremental(db_path, since_ts)` variant in `session_store.py` that
   filters the provided `jsonl_files` list by `path.stat().st_mtime >= since_ts`; reads
   `last_backfill_ts` from the meta table, writes updated timestamp on success
4. Update `hooks/session_start.py` `handle()` to spawn a daemon background thread calling
   `backfill_incremental` after `ensure_db()`, wrapped in `contextlib.suppress(Exception)`;
   use `threading.Thread(target=..., daemon=True)` pattern (see `transport.py:170`)
5. Update `ll-session backfill` CLI (`cli/session.py:96`) to accept `--since` flag;
   ISO 8601 string → `datetime.fromisoformat()` with Z-stripping (see `cli/messages.py:137`)
6. Add unit tests in `test_session_store.py` (follow `TestBackfill` pattern with `tmp_path`) and
   `test_hook_session_start.py` covering: incremental mtime filter, meta timestamp write,
   failure isolation, daemon thread spawned and does not block hook response

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/ARCHITECTURE.md` — add v6 row to schema version table for `last_backfill_ts` meta key
8. Update `docs/reference/CLI.md` — add `--since` flag table under `backfill` subcommand (follow `search`/`recent` flag-table pattern); update "Requires a prior backfill pass" notes in `recent --issue` and `ll-history sessions` entries to reflect automatic session-start trigger
9. Update `docs/reference/API.md` — add `--since` to `main_session` backfill subcommand entry
10. Update `docs/reference/CONFIGURATION.md` — revise "Use `ll-session backfill` to import historical data" sentence to note that `session_start` now triggers incremental backfill automatically for interactive sessions
11. Update `scripts/tests/test_ll_session.py` — add `--since` tests (follow `TestMainMessagesIntegration::test_main_messages_with_since_date` pattern in `test_cli.py`); verify mock target for `backfill`/`backfill_incremental` in `TestMainSession.test_backfill_runs`
12. **Guard** `test_enh1734_doc_wiring.py` assertions: preserve `"historical"` / `"before ENH-1691"` phrases in CLI.md and CONFIGURATION.md when writing doc updates (tests at lines 167 and 190 assert these strings exist)

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — `backfill_incremental()`, v6 migration (`last_backfill_ts`)
- `scripts/little_loops/hooks/session_start.py` — call backfill in background
- `scripts/little_loops/cli/session.py` — `--since` flag for `backfill` subcommand
- `scripts/tests/test_session_store.py` — incremental backfill tests
- `scripts/tests/test_ll_session.py` — add `--since` flag tests; verify mock target for `backfill_incremental` if imported separately from `backfill` [Agent 3 finding]
- `docs/ARCHITECTURE.md` — add v6 row to schema version table (currently ends at v5) [Agent 2 finding]
- `docs/reference/CLI.md` — add `--since` flag subsection for `backfill`; update "Requires a prior backfill pass" framing in `recent --issue` and `ll-history sessions` descriptions [Agent 2 finding]
- `docs/reference/API.md` — add `--since` to `main_session` backfill subcommand entry [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — update "Use `ll-session backfill` to import historical data" framing to reflect automatic session-start trigger [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/session_start.py` — imports `session_store`
- No existing callers read `last_backfill_ts` from the `meta` table (new key)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/history_reader.py` — `_connect_readonly()` calls `ensure_db()` before opening a read-only connection; silently applies v6 migration on first use after upgrade; no code change required but confirms v6 migration is additive-safe [Agent 1 finding]
- `scripts/little_loops/workflow_sequence/io.py` — `_load_messages_from_db()` calls `connect()` → `ensure_db()` silently; same migration propagation; no code change required [Agent 2 finding]
- `scripts/little_loops/transport.py` — `wire_transports()` instantiates `SQLiteTransport` which calls `ensure_db()` in `__init__()`; applies v6 migration transparently at startup of `ll-loop run`, `ll-parallel`, `ll-sprint`, and `AutoManager` [Agent 1 finding]
- `scripts/little_loops/__init__.py` — exports `SQLiteTransport` (line 43); no change needed but confirms public API surface [Agent 1 finding]
- `scripts/little_loops/cli/__init__.py` — imports and re-exports `main_session`; entry point unchanged but confirms dispatch chain [Agent 1 finding]
- `scripts/pyproject.toml` — line 72: `ll-session = "little_loops.cli:main_session"` entry point; no change needed [Agent 1 finding]
- `hooks/hooks.json` — SessionStart entry (lines 4-15) routes to `python -m little_loops.hooks session_start`; no change needed but confirms hook wiring is in place [Agent 1 finding]
- `hooks/adapters/claude-code/session-start.sh` — bash adapter that pipes input to `python -m little_loops.hooks session_start`; no change needed [Agent 1 finding]
- `scripts/little_loops/hooks/__init__.py` — `_dispatch_table()` (line 81) registers `session_start.handle`; no change needed [Agent 1 finding]

### Similar Patterns
- `hooks/session_start.py` already uses `contextlib.suppress` for `ensure_db()` — apply the same pattern for the backfill call
- `ll-session backfill` CLI provides the existing full-scan baseline to extend with `--since`

### Tests
- `scripts/tests/test_session_store.py` — incremental filter, meta timestamp write, failure isolation
- `scripts/tests/test_hook_session_start.py` — daemon thread spawning, non-blocking hook response

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_session.py` — update: add `--since` flag tests for `backfill` subcommand following `test_main_messages_with_since_date` pattern in `test_cli.py`; check `TestMainSession.test_backfill_runs` and `test_backfill_reports_messages_count` mock targets if `backfill_incremental` is imported separately [Agent 3 finding]
- `scripts/tests/test_enh1734_doc_wiring.py` — **caution**: `TestCliMdBackfillFraming.test_backfill_framed_as_legacy` (line 167) and `TestConfigurationMdBackfill.test_backfill_framed_as_legacy` (line 190) assert `"historical" in content or "before ENH-1691" in content` — these will break if doc updates remove the historical-data framing; preserve those phrases when updating docs [Agent 2 finding]
- `scripts/tests/test_issue_history_cli.py` — uses `backfill()` at lines 160, 176 for test-fixture seeding; safe if `since_ts` is keyword-only with default [Agent 3 finding]
- `scripts/tests/test_workflow_sequence_analyzer.py` — `test_db_source_preferred_when_populated()` calls `backfill()` for fixture setup; same safety condition as above [Agent 3 finding]
- New: `TestSchemaV6` class in `test_session_store.py` — v5→v6 upgrade path asserting `last_backfill_ts` key in meta table; follow `TestSchemaV5` pattern bootstrapping a v5 DB, calling `ensure_db()`, asserting final version equals `SCHEMA_VERSION` [Agent 3 finding]
- New: `TestBackfillIncremental` class in `test_session_store.py` — mtime filter, `since_ts` parameter, meta timestamp write on success, failure isolation; follow `TestBackfill` pattern with `tmp_path` [Agent 3 finding]
- New: `TestSessionStartBackfillThread` class in `test_hook_session_start.py` — daemon thread spawned, hook response not blocked, errors suppressed via `contextlib.suppress`; patch `threading.Thread` to verify `daemon=True` [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — schema version table ends at v5; add v6 row for `last_backfill_ts` meta key [Agent 2 finding]
- `docs/reference/CLI.md` — `ll-session backfill` subcommand has no `--since` flag section (unlike `search`/`recent` which have flag tables); also contains "Requires a prior `backfill` pass" framing in `recent --issue` (line ~1526) and `ll-history sessions` descriptions that may need nuancing [Agent 2 finding]
- `docs/reference/API.md` — `main_session` backfill entry has no `--since` flag; add it [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — "Use `ll-session backfill` to import historical data captured before ENH-1691" framing becomes conditionally accurate; update to note automatic backfill for interactive sessions [Agent 2 finding]

### Configuration
- N/A (backfill runs automatically; no new config toggles)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Exact callsite**: `session_start.py:111` — the `if config_path is not None:` block with `contextlib.suppress(Exception)` is where the background thread call goes, immediately after the `ensure_db(...)` call
- **Current schema version**: `SCHEMA_VERSION = 5` (`session_store.py`); five migrations at indices 0–4; next migration is index 5 → v6
- **`backfill()` JSONL gap**: `backfill()` accepts `jsonl_files: list[Path] | None`; when `None` (as in the current CLI call at `cli/session.py:226`), JSONL-backed tables (`tool_events`, `message_events`, `sessions`) return 0 counts — `backfill_incremental()` must receive a non-empty file list to be useful; JSONL file discovery is **not yet in `session_store.py`** and must be solved (e.g., scanning `~/.claude/projects/<project-hash>/`)
- **Meta table upsert pattern**: `ON CONFLICT(key) DO UPDATE SET value = excluded.value` — see `session_store.py:207-211` in `_apply_migrations()`; same upsert writes `last_backfill_ts`
- **Threading pattern**: `threading.Thread(target=..., daemon=True).start()` from `transport.py:170`; `session_store.py` already uses `threading.Lock()` for write serialization in `SQLiteTransport`
- **`--since` implementation model**: `cli/messages.py:137-148` — ISO 8601 string with `Z → +00:00` replacement, falls back to `YYYY-MM-DD` strptime; most flexible existing pattern for a float/ISO `last_backfill_ts`
- **No incremental logic exists today**: `backfill()` is a full-pass; mtime gating must be added as a new `since_ts: float | None` parameter threaded into `_backfill_tool_events()`, `_backfill_messages()`, and `_backfill_sessions()`

## API/Interface

```python
# New function in session_store.py
def backfill_incremental(db_path: Path, since_ts: float) -> None:
    """Backfill only JSONL files with mtime >= since_ts."""

# Updated CLI flag
# ll-session backfill --since <iso8601-or-unix-ts>

# New meta table key: "last_backfill_ts" → ISO 8601 timestamp string
```

## Impact

- **Priority**: P3 — Improves history completeness for `ll-session`/`ll-history` without blocking other work
- **Effort**: Small — Adds one new function variant, hooks into existing `session_start.py` pattern, extends one CLI flag
- **Risk**: Low — Errors suppressed via `contextlib.suppress`; runs in a background thread so session startup latency is unaffected
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-01 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-06-01T04:57:16Z - `6c038258-5fb6-4884-a0c7-aff569f156b8.jsonl`
- `/ll:ready-issue` - 2026-06-01T04:45:03 - `21eedb93-d9a3-4c98-b7a0-d0c464f0300f.jsonl`
- `/ll:confidence-check` - 2026-05-31T00:00:00Z - `b8be480e-e52e-4ab8-a8c5-3b5902d7ffb7.jsonl`
- `/ll:wire-issue` - 2026-06-01T04:41:12 - `63c41eaa-7fd8-4ee8-928e-3494f14e0cda.jsonl`
- `/ll:refine-issue` - 2026-06-01T04:35:07 - `daf899d9-17da-4a19-8188-be850e758c59.jsonl`
- `/ll:refine-issue` - 2026-06-01T04:34:57 - `daf899d9-17da-4a19-8188-be850e758c59.jsonl`
- `/ll:format-issue` - 2026-06-01T01:16:58 - `b36ecc52-50ca-45d3-a937-1a07c2c7a5ee.jsonl`
- `/ll:capture-issue` - 2026-06-01T01:10:54Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
