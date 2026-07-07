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
relates_to: [EPIC-2456, FEAT-2476, ENH-2477, FEAT-2478]
blocks: [FEAT-2123]
labels:
  - enhancement
  - history-db
  - analytics
  - cost
  - captured
decision_needed: true
learning_tests_required:
  - anthropic
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Pricing module already exists** — `scripts/little_loops/pricing.py` is already in place with `MODEL_PRICING` (`:10-55`) and `estimate_cost_usd(model, input_tokens, output_tokens, cache_read_tokens=0, cache_creation_tokens=0) -> float | None` (`:58-78`) returning `None` for unknown models — exactly matching the contract this issue's Proposed Solution asks for. **Skip Step 5 (creating `usage_pricing.py`)**; import directly: `from little_loops.pricing import estimate_cost_usd`. The `scripts/tests/test_pricing.py` suite already covers the contract. The "missing-model → `cost_usd=NULL` no-warning" AC is therefore already satisfied by the pricing layer — only the writer integration is new.
- **Callback line is stale** — the `on_usage_detailed` invocation site lives at `subprocess_utils.py:457-470`, not `~289`. The summary's reference to "line ~289" is the parameter declaration site (line 292), not the call site.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Schema migration** — verify with `PRAGMA table_info(usage_events)` after the v19 migration lands (test pattern: `scripts/tests/test_session_store.py:3098-3148`). Migration must append `_MIGRATIONS[18]` (next index) with comment `# v19 (ENH-2461): real LLM token usage persistence`.
- **`on_usage_detailed` payload** — verify by passing a synthetic `TokenUsage` to `record_usage_event()` and asserting all five token fields round-trip via `recent_usage_events()`. Real producer-side test: synthesize a JSON-line `{"type":"result","usage":{"input_tokens":...,"output_tokens":...,"cache_read_input_tokens":...,"cache_creation_input_tokens":...},"model":"claude-sonnet-4-6"}` and feed it through `run_claude_command()`'s parser to confirm the `TokenUsage` builder at `subprocess_utils.py:457-470` populates correctly.
- **`cost_usd` NULL contract** — already covered by `TestEstimateCostUsd.test_unknown_model_returns_none` (`scripts/tests/test_pricing.py:`); the new writer must thread `cost_usd=None` (not raise, not 0.0) when `MODEL_PRICING.get(model)` returns `None`.
- **`ll-ctx-stats` from DB** — extend `_aggregate_tool_events` (`scripts/little_loops/cli/ctx_stats.py:118-166`) to fold in `usage_events` rows; the `bytes_in`/`bytes_out`/`cache_hit` filter (`:131`) is the model for filtering NULL rows. Confirm `--json` payload (`ctx_stats.py:380-395`) includes `total_input_tokens`/`total_output_tokens`/`total_cost_usd` after the change.
- **`ll-session recent --kind usage`** — `--kind` choice arrays duplicated at `scripts/little_loops/cli/session.py:88-141` (both `search` and `recent` parsers) need `"usage"` added; if either is missed, argparse errors at runtime. End-to-end test pattern: `test_recent_kind_commit_outputs_row` at `scripts/tests/test_ll_session.py:949-960`.
- **Provider-agnostic** — Codex/OpenCode producer integration lives in `host_runner.py:CodexRunner.build_streaming` (`:467-525`) and `OpenCodeRunner` (`:628-697`); FEAT-2123 owns that wiring. ENH-2461 only needs to land the schema + writer + read API + Claude-side integration; Codex/OpenCode are an AC for the post-FEAT-2123 follow-on.
- **Tests cover writer / pricing / aggregation** — three layered test classes: `TestRecordUsageEvent` (writer round-trip + FTS indexing), `TestEstimateCostUsd` extension or `TestUsagePricingKnownModelAbsent` (cost_usd contract), `TestRecentUsageEvents` + `TestAggregateUsage` (read API). All grounded in existing templates listed in Implementation Steps §Codebase Research Findings.

## Sources

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 (schema migration)** — append a new SQL string to `_MIGRATIONS` at `scripts/little_loops/session_store.py:208-545`; the migration convention is `# vN (FEAT-/ENH-/BUG-XXXX): <one-line description>` (see v14/v15/v16/v17/v18 for examples). `_apply_migrations()` (`:609-645`) re-stamps the `meta.schema_version` row automatically; current `SCHEMA_VERSION = 18` (line 102) → bump to **19** when adding `usage_events`. Closest prior-art templates: **v17 commit_events** (`ENH-2458`, sibling-table) and **v18 test_run_events** (`ENH-2459`, sibling-table); model the `CREATE TABLE` + `CREATE INDEX` block on these.
- **Step 3 (kind registration)** — three coupled edits: `_VALID_KINDS` (`session_store.py:104`), `_KIND_TABLE` (`session_store.py:119-130` mapping `usage → usage_events`), and `_EXPORT_TABLE_MAP` (`session_store.py:2791-2814`, add `"usage_event": ("usage_events", "ts")` so `ll-session export` auto-discovers it).
- **Step 4 (writer)** — no `record_tool_event()` function exists today; the live writer is inline in `scripts/little_loops/hooks/post_tool_use.py:158-180`. New `record_usage_event()` should follow the `record_commit_event` template at `session_store.py:1041-1091` (or `record_test_run_event` at `:1171-1233`) which both call `_index(conn, content=..., kind="usage", ref=..., anchor=..., ts=...)` (`:705-718`) to populate the FTS5 `search_index` row. Consider `INSERT OR IGNORE` + a uniqueness key (e.g. `(session_id, ts, model)`) so duplicate callbacks don't double-write.
- **Step 5 (pricing)** — `scripts/little_loops/pricing.py` **already exists** with `MODEL_PRICING` (`pricing.py:10-55`) and `estimate_cost_usd(model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens) -> float | None` (`pricing.py:58-78`) returning `None` when model is unknown. **Skip the proposed new `usage_pricing.py`**; import `from little_loops.pricing import estimate_cost_usd` directly. The "missing model → `cost_usd=NULL`, no warning" AC is already implemented. See `scripts/tests/test_pricing.py:1-62` for the contract tests.
- **Step 6 (callback wiring)** — `TokenUsage` dataclass already exists at `subprocess_utils.py:44-52` with fields `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `model` (note: dataclass names use `cache_read_tokens`/`cache_creation_tokens` — that's the mapping target for the API's `cache_read_input_tokens`/`cache_creation_input_tokens` already applied at the payload reader in `subprocess_utils.py:457-470`). The callback fires inside the `etype == "result"` branch of the JSON-line scan loop (`run_claude_command()` `:449-470`); the proposed `~289` line in the original summary is stale. The current pipeline also re-emits the same data through `fsm/runners.py:DefaultActionRunner._collect_usage` (`:141-160`) → `ActionResult.usage_events` (`:180`) → `fsm/executor.py:_run_action` aggregates (`:1314-1422`) → `fsm/persistence.py:PersistentExecutor._handle_event` writes `${run_dir}/usage.jsonl` (`:669-697`). **Decide** whether `record_usage_event()` writes at the `on_usage_detailed` call site only, or also at the FSM aggregation site (one row per state vs. one row per LLM call).
- **Step 7 (Codex/OpenCode wiring)** — `CodexRunner.build_streaming` at `scripts/little_loops/host_runner.py:467-525` currently emits `codex exec --json` argv with **no callback integration** for usage; `OpenCodeRunner` at `:628-697` raises `HostNotConfigured` (stubs only). FEAT-2123 owns extending the same `on_usage_detailed` contract after the producer-side schema and writer land here. `docs/reference/HOST_COMPATIBILITY.md:144` documents the gap with `✗`; flip to `✓` for the codepath once this issue's writer is in place.
- **Step 8 (ll-ctx-stats)** — extend `scripts/little_loops/cli/ctx_stats.py:_aggregate_tool_events` (`:118-166`) and the `--json` payload at `:380-395` (currently exposes `cache_read_tokens` / `cache_write_tokens`) to add `total_input_tokens`, `total_output_tokens`, `total_cost_usd` from `usage_events`. The JSONL re-parse path `_compute_cache_rate_from_jsonl` (`ctx_stats.py:180-252`) becomes dead code once `usage_events` is populated; mark deprecated, keep for one release for back-compat.
- **Step 9 (read API)** — model on `recent_skill_events` at `scripts/little_loops/history_reader.py:441-469` (parametrized `WHERE` + `ORDER BY id DESC LIMIT`) and `summarize_skills` at `:472-521` (`GROUP BY` rollup). Add `UsageEvent` dataclass next to existing typed event classes (`:106-161`). `_connect_readonly(db_path)` at `:235` is the connection helper; `_row_to_dataclass` at `:252` already filters unknown columns.
- **Step 10 (tests)** — three layered test templates to follow:
  - **Writer round-trip + dedup + FTS indexing**: `TestRecordCommitEvent` at `scripts/tests/test_session_store.py:3416-3465` (specifically `test_roundtrip`, `test_dedupe_on_sha`, `test_fts_searchable_by_message_fragment`).
  - **Schema-version upgrade with column-additivity**: `TestSchemaV15SkillCompletionColumns` at `:3098-3148`, plus `_bootstrap_schema_at(db, version)` helper at `:3075-3095` for "upgrade from historical N → N+1" tests.
  - **CLI `ll-session recent --kind usage` output**: `test_recent_kind_commit_outputs_row` and `test_recent_kind_test_run_outputs_row` at `scripts/tests/test_ll_session.py:949-975`. Note both `--kind` choices arrays in `cli/session.py:88-141` need `"usage"` added to match `_VALID_KINDS`.
  - **Analytics gate**: `test_record_correction_gate_disabled` and `test_write_file_event_gate_disabled` at `scripts/tests/test_session_store.py:1483-1511` are the precedence for "suppress write when `analytics.capture.<flag>` is false" tests.
- **Step 11 (docs)** — bump `docs/ARCHITECTURE.md` schema-versions table from v18 → v19; add `docs/reference/CONFIGURATION.md` row for `analytics.capture.usage_events` (gates the new writer). `docs/reference/HOST_COMPATIBILITY.md:144` flips `Token reporting` to `✓` for Claude host (Codex/OpenCode remain `✗` until FEAT-2123).

- **Gating & config wiring** — the new writer should be gated on `analytics.enabled` (current default `false` per `config-schema.json:1568-1610`); per-event gate goes on a new `analytics.capture.usage_events` flag, modeled on `AnalyticsCaptureConfig.from_dict` at `scripts/little_loops/config/features.py:528-556`. Update `_ANALYTICS_CAPTURE_KEYS` in `scripts/little_loops/init/core.py:16` to include `"usage_events"` so `ll-init` emits it. The graceful-degradation contract (DB write never blocks LLM run) is established by `pytest_history_plugin.py:81-100` and `hooks/post_commit.py:85-101` (`main()` always exits 0); use `contextlib.suppress(Exception)` at the call site in the callback path.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify

- `scripts/little_loops/session_store.py` — append v19 migration to `_MIGRATIONS` (`:208-545`); extend `_VALID_KINDS` (`:104`), `_KIND_TABLE` (`:119-130`), `_EXPORT_TABLE_MAP` (`:2791-2814`); add `record_usage_event()` following `record_commit_event` (`:1041-1091`) / `record_test_run_event` (`:1171-1233`); export.
- `scripts/little_loops/subprocess_utils.py` — wire `record_usage_event(...)` into the `on_usage_detailed` invocation site (`:449-470`); keep existing `usage.jsonl` writer intact for transitional period.
- `scripts/little_loops/fsm/persistence.py` — decide whether `PersistentExecutor._handle_event` (`:669-697`) also calls `record_usage_event()` per-state, or only the per-callback path writes.
- `scripts/little_loops/host_runner.py` — `CodexRunner.build_streaming` (`:467-525`) and `OpenCodeRunner` (`:628-697`) integration is gated on FEAT-2123.
- `scripts/little_loops/history_reader.py` — add `UsageEvent` dataclass (next to `:106-161`) and `recent_usage_events()` / `aggregate_usage()` (modeled on `recent_skill_events` at `:441-469` and `summarize_skills` at `:472-521`).
- `scripts/little_loops/cli/session.py` — extend `--kind` choice arrays (`:88-141`) to include `"usage"`.
- `scripts/little_loops/cli/ctx_stats.py` — extend `_aggregate_tool_events` (`:118-166`) and `--json` payload (`:380-395`) to surface tokens/cache/cost from DB; deprecate `_compute_cache_rate_from_jsonl` (`:180-252`).
- `scripts/little_loops/config/features.py` — add `usage_events: bool` field to `AnalyticsCaptureConfig` (`:528-556`); default `True`.
- `scripts/little_loops/init/core.py` — extend `_ANALYTICS_CAPTURE_KEYS` (`:16`) to include `"usage_events"`.
- `config-schema.json` — add `"analytics.capture.usage_events"` (next to existing capture keys at `:1568-1610`); default `true`.
- `docs/ARCHITECTURE.md` — schema-versions table: add v19 row.
- `docs/reference/CONFIGURATION.md` — document `analytics.capture.usage_events`.
- `docs/reference/HOST_COMPATIBILITY.md` — flip `Token reporting` row (`:144`) from `✗` to `✓` for Claude host.

### Dependent Files (Callers / Importers)

- `scripts/little_loops/cli/loop/_helpers.py:_print_usage_summary` (`:1652-1714`) — currently parses `${run_dir}/usage.jsonl`; will transition to DB-backed rollup.
- `scripts/little_loops/hooks/post_tool_use.py:handle()` (`:137-209`) — already gates on `analytics.enabled` (`:151`); sets the precedent for the new writer's gate.
- `scripts/little_loops/pytest_history_plugin.py:LLHistoryPlugin` (`:81-`) — establishes the graceful-degradation contract for "DB write never blocks parent op" (`contextlib.suppress(Exception)`).

### Tests

- `scripts/tests/test_session_store.py` — add `TestRecordUsageEvent` (model on `TestRecordCommitEvent` `:3416-3465`), `TestSchemaV19UsageEventsColumns` (model on `TestSchemaV15SkillCompletionColumns` `:3098-3148`), `TestUsageEventsAnalyticsGate` (model on `test_record_correction_gate_disabled` `:1483-1511`).
- `scripts/tests/test_history_reader.py` — add `TestRecentUsageEvents` / `TestAggregateUsage`.
- `scripts/tests/test_ll_session.py` — add `test_recent_subcommand_usage_accepted` (model on `test_recent_subcommand_commit_accepted` `:78-86`) and `test_recent_kind_usage_outputs_row` (model on `:949-960`).
- `scripts/tests/test_cli_ctx_stats.py` — add `TestCtxStatsFromDb` (mirror `_populate_tool_events` helper at `:64-81`).
- `scripts/tests/test_pricing.py` — already covers `estimate_cost_usd` known/unknown/zero paths.

### Documentation

- `docs/ARCHITECTURE.md` — schema-versions table (v19 row).
- `docs/reference/CONFIGURATION.md` — `analytics.capture.usage_events` definition.
- `docs/reference/HOST_COMPATIBILITY.md` — `Token reporting` parity matrix update.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — usage-events section (how to query).

### Configuration

- `.ll/ll-config.json` — `analytics.capture.usage_events` (default `true`) gates the per-event write; `analytics.enabled` (default `false`) gates the whole feature. Existing `analytics.capture.{skills,cli_commands,corrections,file_events}` set the precedent.

### Open Questions for Implementer

- **Should `usage_events.tool_event_id` be a foreign-key to `tool_events.id`** (per the issue's Option B schema) so a single tool invocation can be joined back to its byte columns? Or keep the tables independent and join on `(session_id, ts)`? Trade-off: FK preserves a 1:1 mapping but requires `tool_events` to write first; independent keeps writer order free.
- **Migration grain** — one row per `TokenUsage` (per LLM call, ~one per loop iteration) vs. one row per FSM state (aggregated rollup). The current JSONL writer at `fsm/persistence.py:684` uses the latter; the historical `on_usage_detailed` fires N times per state. Pick one, document why.

## Sources

- `thoughts/history-db-expand-wiring.md` — recommendations §2 row 4 ("Token/cost usage"), §3 ranked recommendation #4
- `scripts/little_loops/hooks/post_tool_use.py:handle()` (FEAT-1623) — `bytes_in/bytes_out/cache_hit` writer (analogous structural site)
- `scripts/little_loops/subprocess_utils.py:run_claude_command()` — `on_usage_detailed` callback (~line 289)
- `scripts/little_loops/cli/ctx_stats.py` — current consumer; re-parses JSONL

## Cross-issue coordination — name mapping with FEAT-2478 (OTel emission)

_Added 2026-07-05 from `/ll:explore-api phoenix` findings._

FEAT-2478 (F5) emits OTel `gen_ai.usage.*` attributes **derived from** the
columns this issue persists. Keep the two name spaces distinct and lock the
mapping at the boundary:

| ENH-2461 internal column (this issue) | FEAT-2478 OTel attribute it maps to |
|---|---|
| `input_tokens` | `gen_ai.usage.input_tokens` |
| `output_tokens` | `gen_ai.usage.output_tokens` |
| `cache_read_input_tokens` | `gen_ai.usage.cache_read.input_tokens` *(dotted)* |
| `cache_creation_input_tokens` | `gen_ai.usage.cache_creation.input_tokens` *(dotted)* |

The **internal columns stay underscore** (they mirror the Anthropic API usage
fields — do not rename them). The subtlety is only on the *OTel* side: the two
cache attributes use **dotted** OTel sub-namespaces
(`gen_ai.usage.cache_read.input_tokens`), **not** a naive
`gen_ai.usage.` + `<column_name>` concatenation, which would wrongly produce
`gen_ai.usage.cache_read_input_tokens` and is **silently dropped** by
OTel-semconv consumers (verified live against Arize Phoenix 17.18.0; see
FEAT-2478 § Premise Note and `.ll/learning-tests/phoenix.md`). If FEAT-2478
generates OTel names programmatically from column names, it needs an explicit
per-field mapping for the cache columns, not string prefixing.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/CONFIGURATION.md` | `analytics.enabled` gating the writer |
| `docs/reference/API.md` | `session_store` module reference |
| FEAT-2123 (open) | Codex/OpenCode usage source research; sibling effort |
| FEAT-2478 (open) | F5 OTel emission consumes these columns; cache-name mapping locked above |

## Status

**Open** | Created: 2026-07-02 | Priority: P3

## Session Log
- `/ll:refine-issue` - 2026-07-06T23:57:55 - `393e0dc2-c1c3-43c5-b47a-60f52a6d21c0.jsonl`
- `/ll:explore-api phoenix` - 2026-07-05 - Added Cross-issue coordination note: internal token columns stay underscore, but FEAT-2478's OTel mapping for the two cache columns must use DOTTED names (`gen_ai.usage.cache_read.input_tokens`) — string-prefixing the column name silently breaks OTel-semconv consumers (Phoenix verified). Locked the column→attribute mapping table.
- backlog-grooming - 2026-07-03T00:00:00Z - Consolidated token-telemetry workstream: this issue is sequenced first (Claude host; `on_usage_detailed` already exists), it `blocks` FEAT-2123 (Codex/OpenCode extension of the same callback contract), and it `relates_to` EPIC-2456 whose F5 (OTel `gen_ai.usage.*` emission) and F6 (per-state cost attribution) consume the persisted usage rows.
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
