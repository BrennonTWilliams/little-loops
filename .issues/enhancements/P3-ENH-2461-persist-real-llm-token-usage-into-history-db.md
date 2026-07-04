---
id: ENH-2461
title: Persist real LLM token usage into history.db
type: ENH
priority: P3
status: open
discovered_date: 2026-07-02
captured_at: "2026-07-02T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
relates_to: [EPIC-2456]
blocks: [FEAT-2123]
labels:
  - enhancement
  - history-db
  - analytics
  - cost
  - captured
---

# ENH-2461: Persist real LLM token usage into history.db

## Summary

`tool_events` (FEAT-1623) tracks context-window bytes (`bytes_in`, `bytes_out`, `cache_hit`) which are computed from `len(json.dumps(payload))` — they are NOT the actual LLM token counts the API returned. `ll-ctx-stats` re-parses JSONL transcripts ad hoc each invocation rather than reading persisted counts. **Real** token counts (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, plus `cost_usd` when the model pricing is known) are never persisted. Add them as columns on `tool_events` (or a sibling `usage_events` table) and populate them at the source: where the `subprocess_utils.run_claude_command()` `on_usage_detailed` callback fires. Per `thoughts/history-db-expand-wiring.md` §3 ranked recommendation #4: *"persist `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` (already parsed ad hoc by `ll-ctx-stats` from JSONL) into `tool_events` or a new `usage_events` table, so cost analysis doesn't require re-scanning raw transcripts every time."*

## Motivation

Real token counts unlock:

- **Cost analysis** — `ll-ctx-stats` can answer "tokens used per skill per day, in dollars" instead of re-parsing every session.
- **Cache effectiveness** — `cache_read_input_tokens` vs `cache_creation_input_tokens` reveals how well the cache is being hit per loop / per skill.
- **Per-iteration loop cost** — `ll-loop run` can surface actual cost per state instead of estimates.
- **Trend analysis** — historical token usage under a given model supports model-migration impact assessment.

The existing `bytes_in`/`bytes_out` columns are proxies; they correlate loosely but don't equal actual token counts (a prompt's serialized JSON form vs. its tokenized form differs by ~4× for chatty JSON and ~1× for prose). Persisting real tokens alongside bytes preserves both for analysis.

## Current Behavior

- `tool_events` schema: `id, ts, session_id, tool_name, args_hash, result_size, bytes_in, bytes_out, cache_hit` (per FEAT-1623 schema).
- `on_usage_detailed` callback in `subprocess_utils.run_claude_command()` (line ~289) fires for `claude` runs with the API's usage block — but currently writes to `.ll/usage.jsonl` (per `FEAT-2123` summary), not history.db.
- `ll-ctx-stats` re-parses session JSONL each run to derive per-tool bytes; no token/cost summary surfaces.
- Non-Claude hosts (Codex, OpenCode): the findings report notes FEAT-2123 (open) explores whether codex/opencode event payloads expose usage; until that's resolved, this enhancement focuses on the Claude path.

## Expected Behavior

- Either (preferred) extend `tool_events` with `input_tokens INTEGER, output_tokens INTEGER, cache_read_input_tokens INTEGER, cache_creation_input_tokens INTEGER, cost_usd REAL` columns (nullable for non-token events).
- Or a sibling `usage_events` table keyed to `(tool_event_id, ts, session_id, ...)` if normalization is preferred; the existing `tool_events` table grows narrow.
- A writer at the `on_usage_detailed` callback site calls `record_usage_event()` (or the extension to `record_tool_event` accepts token fields), correlating the usage block back to the most-recent `tool_event` row when feasible.
- `ll-ctx-stats` reports per-tool token and cache stats without re-scanning JSONL; cost section reflects `cost_usd` (computed from a pricing table keyed by model).
- `ll-session search --fts "<skill name>" --kind usage` surfaces usage rows; `ll-session recent --kind usage` shows recent entries.

## Proposed Solution

### Schema option A (additive columns on `tool_events`)

```sql
ALTER TABLE tool_events ADD COLUMN input_tokens INTEGER;
ALTER TABLE tool_events ADD COLUMN output_tokens INTEGER;
ALTER TABLE tool_events ADD COLUMN cache_read_input_tokens INTEGER;
ALTER TABLE tool_events ADD COLUMN cache_creation_input_tokens INTEGER;
ALTER TABLE tool_events ADD COLUMN cost_usd REAL;
ALTER TABLE tool_events ADD COLUMN model TEXT;  -- model name for cost calc
```

Bump `SCHEMA_VERSION`. Add `"usage"` to `_VALID_KINDS` for any sibling table variant.

### Schema option B (sibling `usage_events` table)

```sql
CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT,
    tool_event_id INTEGER REFERENCES tool_events(id),
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_input_tokens INTEGER,
    cache_creation_input_tokens INTEGER,
    cost_usd REAL
);
CREATE INDEX IF NOT EXISTS idx_usage_events_session ON usage_events(session_id);
CREATE INDEX IF NOT EXISTS idx_usage_events_model ON usage_events(model);
```

Option B is cleaner for queries ("what did this session cost?") and avoids populating token columns on every `tool_event` row (most tools don't have usage). Recommend Option B.

### Producer wiring

- In `subprocess_utils.py` `on_usage_detailed` callback (line ~289) plus `scripts/little_loops/host_runner.py:CodexRunner`/`OpenCodeRunner` (per FEAT-2123): call `record_usage_event(...)` with the token block.
- Pricing: a small `scripts/little_loops/usage_pricing.py` module keyed by `model` → `{input: $/MTok, output: $/MTok, cache_read: $/MTok, cache_creation: $/MTok}`. Update via `ll-init`-style data file.
- The pricing layer is best-effort: missing model → write `cost_usd=NULL`; no failure blocks the run.

### Read API

`recent_usage_events(session_id=None, model=None, since=None)` returning `list[UsageEvent]`. Optional: `aggregate_usage(group_by: Literal["model","skill","session"], since=None)` returning rollup totals.

## Acceptance Criteria

- Either `tool_events` gains the token columns (option A) or `usage_events` exists (option B). Schema migration lands without data loss.
- An `on_usage_detailed` payload populates the new columns / new row with the API's values.
- `cost_usd` is computed when the model is in the pricing table; `NULL` otherwise (no warning).
- `ll-ctx-stats` reports per-tool / per-session token totals from the DB, not from JSONL re-parse.
- `ll-session recent --kind usage` returns rows.
- Provider-agnostic: the same code path serves Claude (today) and Codex/OpenCode (post-FEAT-2123).
- Tests cover: writer, pricing table (model present / absent), read API aggregation.

## Implementation Steps

1. Decide and implement schema migration (recommend Option B — `usage_events` sibling).
2. Bump `SCHEMA_VERSION` if option A; otherwise natural addition.
3. Add `"usage"` to `_VALID_KINDS` and `_KIND_TABLE`.
4. Implement `record_usage_event()` in `session_store.py`; export.
5. Add `scripts/little_loops/usage_pricing.py` with model → pricing dict; lazy import.
6. Wire `record_usage_event()` into `subprocess_utils.on_usage_detailed` callback.
7. Wire (after FEAT-2123 lands) `CodexRunner`/`OpenCodeRunner` to the same callback.
8. Extend `ll-ctx-stats` to surface tokens/cache/cost from the DB (deprecate the JSONL re-parse path).
9. Read API: `recent_usage_events()` and optional `aggregate_usage()` in `history_reader.py`.
10. Tests: `TestRecordUsageEvent`, `TestUsagePricing`, `TestCtxStatsFromDb` (no JSONL needed), fallback when model absent.
11. Docs: `docs/ARCHITECTURE.md` schema row, `docs/reference/CONFIGURATION.md` analytics gates.

## Sources

- `thoughts/history-db-expand-wiring.md` — recommendations §2 row 4 ("Token/cost usage"), §3 ranked recommendation #4
- `scripts/little_loops/hooks/post_tool_use.py:handle()` (FEAT-1623) — `bytes_in/bytes_out/cache_hit` writer (analogous structural site)
- `scripts/little_loops/subprocess_utils.py:run_claude_command()` — `on_usage_detailed` callback (~line 289)
- `scripts/little_loops/cli/ctx_stats.py` — current consumer; re-parses JSONL

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/CONFIGURATION.md` | `analytics.enabled` gating the writer |
| `docs/reference/API.md` | `session_store` module reference |
| FEAT-2123 (open) | Codex/OpenCode usage source research; sibling effort |

## Status

**Open** | Created: 2026-07-02 | Priority: P3

## Session Log
- backlog-grooming - 2026-07-03T00:00:00Z - Consolidated token-telemetry workstream: this issue is sequenced first (Claude host; `on_usage_detailed` already exists), it `blocks` FEAT-2123 (Codex/OpenCode extension of the same callback contract), and it `relates_to` EPIC-2456 whose F5 (OTel `gen_ai.usage.*` emission) and F6 (per-state cost attribution) consume the persisted usage rows.
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
