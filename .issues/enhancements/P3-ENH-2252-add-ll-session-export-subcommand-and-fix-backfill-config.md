---
id: ENH-2252
type: ENH
priority: P3
status: done
title: "Add ll-session export subcommand and fix backfill to read project config"
discovered_by: capture-issue
discovered_date: 2026-06-21
captured_at: 2026-06-21T00:44:04Z
completed_at: 2026-06-21T00:44:04Z
---

# ENH-2252: Add ll-session export subcommand and fix backfill to read project config

## Summary

Added `ll-session export` to dump `history.db` tables as JSONL for visualization or external tooling. Also fixed `ll-session backfill` to read the project config file and pass it to `backfill()`, so `history.compaction.enabled` is respected and `summary_nodes` (LCM hierarchical summaries) are generated automatically on backfill. Added `--max-sessions N` to cap compaction scope for large databases.

## Changes

### `scripts/little_loops/session_store.py`
- Added `export_history()` generator — yields rows from selected tables as dicts with a `"type"` field (JSONL stream)
- Added `_EXPORT_TABLE_MAP` and `_EXPORT_DEFAULT_TABLES` constants mapping public type names to `(table, ts_column)` pairs
- Added `max_sessions: int | None` parameter to `_compact_sessions()` (limits per-session compaction, newest-first order)
- Threaded `max_sessions` through `backfill()` signature
- Added `"export_history"` to `__all__`

### `scripts/little_loops/cli/session.py`
- Fixed `backfill` handler to read project config via `resolve_config_path()` and pass it to `backfill()` and `backfill_incremental()` — matches the existing `prune` handler pattern; compaction and correction-mining settings are now respected
- Added `--max-sessions N` flag to `backfill` subparser
- Added `export` subcommand with `--tables`, `--since`, `--include-messages`, and `-o/--output` options
- Added `export` handler in `main_session()` that streams JSONL to stdout or a file with a completion count logged

### `.ll/ll-config.json`
- Enabled `history.compaction` (`enabled: true`, `budget_tokens: 4096`, `cross_session_enabled: true`) so the next `ll-session backfill` generates LCM summary nodes

## Exported Tables

| type | source table | default? |
|---|---|---|
| `session` | `sessions` | yes |
| `issue_event` | `issue_events` | yes |
| `issue_snapshot` | `issue_snapshots` | yes |
| `skill_event` | `skill_events` | yes |
| `loop_event` | `loop_events` | yes |
| `correction` | `user_corrections` | yes |
| `summary_node` | `summary_nodes` | yes |
| `message_event` | `message_events` | opt-in via `--include-messages` |

## Usage

```bash
# Export all tables (no messages) — 12,477 records
ll-session export -o .ll/export.jsonl

# Export with date filter
ll-session export --since 2026-06-01 -o .ll/june.jsonl

# Include message_events (~46K rows)
ll-session export --include-messages -o .ll/full.jsonl

# Just LCM graph for visualization
ll-session export --tables summary_node session -o .ll/lcm-viz.jsonl

# Generate summaries (LLM calls) before exporting — cap to 50 sessions for first run
ll-session backfill --max-sessions 50
```

## Motivation

User needed to export `history.db` data to JSON/JSONL for visualization. The `summary_nodes` (LCM memory) table was empty because compaction was disabled by default and `ll-session backfill` was not passing the project config to `backfill()`, preventing the compaction setting from taking effect.

## Session Log
- `hook:posttooluse-status-done` - 2026-06-21T00:44:49 - `03dca35f-bebf-43f7-bd08-e8ef750ba530.jsonl`
- `export` implementation - 2026-06-21T00:44:04Z
