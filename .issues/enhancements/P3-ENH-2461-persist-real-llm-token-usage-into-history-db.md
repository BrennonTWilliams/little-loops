---
id: ENH-2461
title: Persist real LLM token usage into history.db
type: ENH
priority: P3
status: done
discovered_date: 2026-07-02
captured_at: '2026-07-02T00:00:00Z'
completed_at: '2026-07-13T03:41:05Z'
discovered_by: capture-issue
parent: EPIC-2457
relates_to:
- EPIC-2456
- FEAT-2476
- ENH-2477
- FEAT-2478
- ENH-2581
blocks:
- FEAT-2123
blocked_by:
- ENH-2581
depends_on:
- ENH-2581
labels:
- enhancement
- history-db
- analytics
- cost
- captured
decision_needed: false
learning_tests_required:
- anthropic
confidence_score: 96
outcome_confidence: 72
score_complexity: 15
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 15
---

# ENH-2461: Persist real LLM token usage into history.db

> **⚠️ Superseding architecture decision (2026-07-12) — read before implementing.**
> This issue was written against the pre-`raw_events` architecture and its
> Proposed Solution (add a `usage_events`/`usage_event` *sibling table* at schema
> **v19**, wire `record_usage_event()` straight off the `on_usage_detailed`
> callback) is now **out of date**. [[ENH-2581]] introduces `raw_events` as the
> single source of truth and lands **first** (schema v19 belongs to ENH-2581, not
> this issue — the two silently collided on v19). After ENH-2581 lands, this issue
> becomes a **usage `event_type` parser over `raw_events`** plus a *query* surface
> (a `usage_events` view/table is added only if a query needs one, per ENH-2581's
> "schema grows for the query, not the ingest" principle), **not** a new
> per-feature ingest table.
>
> **What stays valid:** the motivation, the `pricing.py`/`estimate_cost_usd`
> reuse (Step 5 — already done, do not create `usage_pricing.py`), the read-API
> shape (`recent_usage_events`/`aggregate_usage`), the `ll-ctx-stats` consumer
> wiring (the `_aggregate_usage_events` stub at `cli/ctx_stats.py:169` already
> waits for this), the `ll-session --kind usage` surface, and the FEAT-2478 OTel
> column→attribute mapping table below.
>
> **What is now wrong:** "bump `SCHEMA_VERSION` to 19", "append `_MIGRATIONS[18]`
> for a `usage_events` table", the Option A vs Option B schema choice (the former
> `decision_needed`), and wiring the writer directly off the JSONL callback
> instead of through the `raw_events` parser path. Re-derive the writer as a
> `_backfill_*`-style parser once ENH-2581's `_iter_events()` exists.

### Post-ENH-2581 Codebase Research Findings (raw_events architecture — 2026-07-12)

_Added by `/ll:refine-issue` — ENH-2581 has now landed (commit `15a69d21`,
schema v19). This section fills the gap the superseding banner above flagged
but didn't yet detail: what the "usage `event_type` parser over `raw_events`"
actually looks like in the current code._

- **`raw_events` schema** — `scripts/little_loops/session_store.py:577-601`
  (migration comment `:567-576`): `id, ts, session_id, host, source_path,
  line_no, event_type, raw_line, parsed_json, compacted, summary_node_id`.
  `event_type` mirrors the JSONL `"type"` field verbatim (`"user"`,
  `"assistant"`, `"result"`, etc.) — there is no custom "usage" `event_type`;
  a usage parser filters on whichever existing `type` value carries the usage
  block, the same way `_backfill_tool_events` filters on `type == "assistant"`.
- **⚠️ Critical distinction — two separate usage data sources, not one.**
  `raw_events` is populated by `_backfill_raw_events()`
  (`session_store.py:2468-2511`) from **on-disk session transcript JSONL
  files** (globbed by `cli/backfill_worker.py:36-39`), each row's
  `parsed_json` holding the full re-dumped transcript line. This is a
  **different stream** than the `on_usage_detailed` callback in
  `subprocess_utils.py:449-470`, which fires from the **live subprocess
  stdout** during `run_claude_command()` and is never itself written to a
  file `raw_events` ingests (it currently only reaches
  `${run_dir}/usage.jsonl` via `fsm/persistence.py:669-697`). Whether the
  transcript JSONL also carries a per-turn usage block on `type: "result"` (or
  `type: "assistant"` → `message.usage`) needs verification against a real
  session file before committing to the parser filter — the two research
  passes above disagreed on which `type` carries it. **Open question for
  implementer**: inspect an actual `~/.claude/projects/.../<session>.jsonl` to
  confirm the `type` value and field path before writing
  `_backfill_usage_events()`.
- **Parser template** — `_backfill_tool_events()`
  (`session_store.py:1702-1741`) is the direct shape to follow: `for line,
  source_label in _iter_events(source): json.loads(line) → filter
  record.get("type") → extract fields → INSERT → _index(...) → count += 1`.
  `_iter_events()` (`:1677-1699`) is the shared dual-mode iterator (accepts
  either a JSONL file list or a `raw_events` cursor) every `_backfill_*`
  parser already uses — no new iteration helper needed.
- **Dispatch wiring** — `rebuild()` (`session_store.py:2567-2625`) is the
  dispatcher; a new `_backfill_usage_events(conn, _raw_events_cursor())` call
  is added to its sequence, and the new table name added to `_REBUILD_TABLES`
  (`:2554-2560`) plus `_REBUILD_SEARCH_KINDS` (`:2561`) if it should get FTS
  coverage and be wiped/re-derived on every `rebuild()` call (consistent with
  `compact()`/`prune()` only ever touching `raw_events`, never the derived
  tables directly — confirmed at `:2761-2965`).
- **`record_commit_event`/`record_test_run_event` are NOT the model anymore**
  — this corrects the pre-ENH-2581 research findings below (§ Step 4, Step 10
  test patterns). Those two functions are **direct-write siblings** for data
  sourced outside session JSONL (git log, pytest runs), called at their own
  producer call sites — not routed through `raw_events`/`rebuild()` at all.
  Usage data (sourced from session transcript JSONL) follows the
  **`_backfill_tool_events` raw-events-first pattern** instead: no new
  producer call site in `subprocess_utils.py`, no `record_usage_event()`
  direct writer — just a new `_backfill_usage_events()` parser plumbed into
  `rebuild()`. The corresponding test pattern is `TestRebuild`
  (`scripts/tests/test_session_store.py:2744-2841`, seed-raw-events →
  `rebuild()` → assert counts), not `TestRecordCommitEvent`'s direct-call
  round-trip shape.
- **Kind/table registration still applies** — `VALID_KINDS` and `_KIND_TABLE`
  (`session_store.py:108-133`) still need a `"usage"` entry mapping to the new
  table name, same as originally researched; only the *writer* pattern changes,
  not the read-side registration (`_EXPORT_TABLE_MAP`, `cli/session.py`
  `--kind` arrays, `history_reader.py` read API) documented below.
- **Pricing reuse unchanged** — `pricing.py:estimate_cost_usd()` is already
  called elsewhere from `fsm/cost_graph.py:233,335`, always guarding the
  `None` (unknown-model) return before summing — confirms the existing
  Codebase Research Findings on pricing reuse (below) are still accurate
  post-ENH-2581.
- **Open question resolved: `type: "result"` carries the usage block, not
  `"assistant"`.** `subprocess_utils.py:449-469` (the live-stream path) is
  authoritative: it filters `etype == "result"`, then reads
  `event.get("usage", {})` and builds a `TokenUsage(...)`. This differs from
  every existing `_backfill_*` parser (`_backfill_tool_events`,
  `_backfill_assistant_messages`), which both filter
  `record.get("type") != "assistant"` (`session_store.py:1748, 1852`) — the
  new `_backfill_usage_events()` needs `record.get("type") != "result"`
  instead, a filter value no existing `_backfill_*` parser uses today. (`/ll:wire-issue` finding, 2026-07-12)
- **`fsm/cost_graph.py` already has a gated consumer waiting on this
  table** — a `from_usage_db()` method (`cost_graph.py:184-348`, alongside
  the existing `from_usage_jsonl()`) reads from a `usage_event` table and
  calls `estimate_cost_usd()` per row, but is inactive until `usage_events`
  exists. `CostReport`/`PerStateCost` are re-exported from
  `scripts/little_loops/__init__.py`. This is a second gated consumer beyond
  the `ll-ctx-stats` stub already flagged in the superseding banner above —
  neither was previously listed in this issue's Integration Map. (`/ll:wire-issue` finding, 2026-07-12)
- **`ll-verify-kinds` (`scripts/little_loops/cli/verify_kinds.py`) is a hard
  registration gate**, not just `cli/session.py`'s `--kind` choices — it
  scans `_MIGRATIONS` for every `CREATE TABLE` and asserts each is in
  `_KIND_TABLE.values()` or the explicit `_KINDLESS_TABLES` frozenset
  (`session_store.py:170`). If the `usage_events` migration lands without a
  matching `_KIND_TABLE["usage"]` entry, `ll-verify-kinds` fails with exit 1.
  `TestValidKindsCentralization.test_every_valid_kind_has_a_kind_table_entry`
  (`test_session_store.py:3112-3113`) is the companion in-suite guardrail —
  a set-equality check that passes only if `VALID_KINDS` and `_KIND_TABLE`
  gain the `"usage"` entry together. (`/ll:wire-issue` finding, 2026-07-12)
- **Two more registration points distinct from `_KIND_TABLE`/`_EXPORT_TABLE_MAP`**:
  `rebuild()`'s hand-written `counts` dict (`session_store.py:2681-2689`,
  keys `sessions`/`tools`/`messages`/`assistant_messages`/`skill_events`/`corrections`/`summaries`)
  needs a `"usage_events"` key added alongside the new `_backfill_usage_events(...)`
  call, or the returned counts silently omit the new table even though it's
  populated; and `_REBUILD_SEARCH_KINDS` (`session_store.py:2659`) is a
  separate tuple from `_REBUILD_TABLES` gating which `search_index` kinds
  get wiped/rewritten each `rebuild()` call — needs its own `"usage"` entry
  if FTS coverage on usage rows is desired. (`/ll:wire-issue` finding, 2026-07-12)

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

- **Step 1 (schema migration)** — append a new SQL string to `_MIGRATIONS` at `scripts/little_loops/session_store.py:208-545`; the migration convention is `# vN (FEAT-/ENH-/BUG-XXXX): <one-line description>` (see v14/v15/v16/v17/v18 for examples). `_apply_migrations()` (`:609-645`) re-stamps the `meta.schema_version` row automatically; current `SCHEMA_VERSION = 19` (`session_store.py:135`) → bump to **20** when adding `usage_events` (v19 is already taken by ENH-2581's `raw_events` migration; confirmed live in the working tree 2026-07-12, see Confidence Check Notes below). Closest prior-art templates: **v17 commit_events** (`ENH-2458`, sibling-table) and **v18 test_run_events** (`ENH-2459`, sibling-table); model the `CREATE TABLE` + `CREATE INDEX` block on these.
- **Step 3 (kind registration)** — three coupled edits: `_VALID_KINDS` (`session_store.py:104`), `_KIND_TABLE` (`session_store.py:119-130` mapping `usage → usage_events`), and `_EXPORT_TABLE_MAP` (`session_store.py:2791-2814`, add `"usage_event": ("usage_events", "ts")` so `ll-session export` auto-discovers it).
- **Step 4 (writer)** — no `record_tool_event()` function exists today; the live writer is inline in `scripts/little_loops/hooks/post_tool_use.py:158-180`. New `record_usage_event()` should follow the `record_commit_event` template at `session_store.py:1041-1091` (or `record_test_run_event` at `:1171-1233`) which both call `_index(conn, content=..., kind="usage", ref=..., anchor=..., ts=...)` (`:705-718`) to populate the FTS5 `search_index` row. Consider `INSERT OR IGNORE` + a uniqueness key (e.g. `(session_id, ts, model)`) so duplicate callbacks don't double-write.
- **Step 5 (pricing)** — `scripts/little_loops/pricing.py` **already exists** with `MODEL_PRICING` (`pricing.py:10-55`) and `estimate_cost_usd(model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens) -> float | None` (`pricing.py:58-78`) returning `None` when model is unknown. **Skip the proposed new `usage_pricing.py`**; import `from little_loops.pricing import estimate_cost_usd` directly. The "missing model → `cost_usd=NULL`, no warning" AC is already implemented. See `scripts/tests/test_pricing.py:1-62` for the contract tests.
- **Step 6 (callback wiring)** — `TokenUsage` dataclass already exists at `subprocess_utils.py:44-52` with fields `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `model` (note: dataclass names use `cache_read_tokens`/`cache_creation_tokens` — that's the mapping target for the API's `cache_read_input_tokens`/`cache_creation_input_tokens` already applied at the payload reader in `subprocess_utils.py:457-470`). The callback fires inside the `etype == "result"` branch of the JSON-line scan loop (`run_claude_command()` `:449-470`); the proposed `~289` line in the original summary is stale. The current pipeline also re-emits the same data through `fsm/runners.py:DefaultActionRunner._collect_usage` (`:141-160`) → `ActionResult.usage_events` (`:180`) → `fsm/executor.py:_run_action` aggregates (`:1314-1422`) → `fsm/persistence.py:PersistentExecutor._handle_event` writes `${run_dir}/usage.jsonl` (`:669-697`). **Closed by the Decision Rationale/Addendum 2 below**: `record_usage_event()` writes at the `on_usage_detailed` call site only, one row per LLM call, via the `raw_events` parser — not also called from the FSM aggregation site. `fsm/persistence.py:684`'s existing `usage.jsonl` writer is untouched and continues to serve `PerStateCost.from_usage_jsonl()`. A live per-state writer is deferred to a separate future FEAT (Addendum 2) — this issue adds a nullable `state` column for forward compat but does not populate it.
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
- `scripts/little_loops/fsm/persistence.py` — no change. `PersistentExecutor._handle_event` (`:669-697`) keeps writing `usage.jsonl` unmodified; it does not also call `record_usage_event()`. A live per-state writer is out of scope for this issue (see Addendum 2) — `usage_events` gains a nullable `state` column but is populated only via the `raw_events` parser, which never has state context.
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

_Wiring pass added by `/ll:wire-issue`, 2026-07-12:_
- `scripts/little_loops/cli/verify_kinds.py` — scans `_MIGRATIONS` for `CREATE TABLE` and asserts each is registered in `_KIND_TABLE.values()` or `_KINDLESS_TABLES`; fails with exit 1 if `usage_events` lands without a `_KIND_TABLE["usage"]` entry. No code change needed if `_KIND_TABLE`/`VALID_KINDS` are updated in tandem, but must be run as a gate before merge.
- `scripts/little_loops/fsm/cost_graph.py:_from_history()`/`PerStateCost.from_history` (`:279-359`) — **retired, not un-gated** (see § Addendum: consumer-schema conflict resolved above): per-state grain isn't derivable from per-call `usage_events` rows, so this speculative history-DB-backed reader is removed rather than rewritten; true per-state cost stays served by the existing live `PerStateCost.from_usage_jsonl()` path. `CostReport`/`PerStateCost` re-exported from `scripts/little_loops/__init__.py`.

### Tests

- `scripts/tests/test_session_store.py` — add `TestRecordUsageEvent` (model on `TestRecordCommitEvent` `:3416-3465`), `TestSchemaV19UsageEventsColumns` (model on `TestSchemaV15SkillCompletionColumns` `:3098-3148`), `TestUsageEventsAnalyticsGate` (model on `test_record_correction_gate_disabled` `:1483-1511`).
- `scripts/tests/test_history_reader.py` — add `TestRecentUsageEvents` / `TestAggregateUsage`.
- `scripts/tests/test_ll_session.py` — add `test_recent_subcommand_usage_accepted` (model on `test_recent_subcommand_commit_accepted` `:78-86`) and `test_recent_kind_usage_outputs_row` (model on `:949-960`).
- `scripts/tests/test_cli_ctx_stats.py` — add `TestCtxStatsFromDb` (mirror `_populate_tool_events` helper at `:64-81`).
- `scripts/tests/test_pricing.py` — already covers `estimate_cost_usd` known/unknown/zero paths.

_Wiring pass added by `/ll:wire-issue`, 2026-07-12:_
- `scripts/tests/test_verify_kinds.py` — run as a gate; passes automatically once `"usage"` is added to both `VALID_KINDS` and `_KIND_TABLE` in the same change.
- `scripts/tests/test_fsm_cost_graph.py` — tests `CostReport`/`PerStateCost`/`from_usage_jsonl()` (unchanged; still the live per-state path). Remove `TestFromHistory`'s two gating tests (`test_from_history_falls_back_when_table_absent`, `test_from_history_returns_list_type`, `:239-`) along with the retired `_from_history()`/`PerStateCost.from_history` — no replacement test needed since the function no longer exists (see § Addendum above).
- `scripts/tests/test_cli_cost_table.py` — per-state cost JSON output shape; unaffected (still sourced from the live `usage.jsonl` path, not `usage_events`).
- `scripts/tests/test_session_store.py::TestRebuild` (`:2847-2943`) — no existing test asserts `_REBUILD_TABLES`'/`rebuild()`'s returned `counts` dict keys as an exact set, so nothing breaks, but add a case asserting `counts["usage_events"]` appears (mirror `test_rebuild_materializes_from_raw_events_without_original_files`, `:2866-2895`) and an idempotency case mirroring `test_rebuild_is_idempotent` (`:2897-2907`). Use a `_result_record()` synthetic-fixture helper (no existing `_backfill_*` test builds a `"type": "result"` record — closest template is `TestBackfillSkillEvents._user_record()`, `:1550-1561`) with `"usage": {...}` and `"model"` at the top level, not nested under `"message"`.

### Documentation

- `docs/ARCHITECTURE.md` — schema-versions table (v19 row).
- `docs/reference/CONFIGURATION.md` — `analytics.capture.usage_events` definition.
- `docs/reference/HOST_COMPATIBILITY.md` — `Token reporting` parity matrix update.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — usage-events section (how to query).

_Wiring pass added by `/ll:wire-issue`, 2026-07-12:_
- `docs/reference/API.md` — hardcodes the `--kind` enum literally twice (`search` at `:4041`, `recent` at `:4042`: `{tool,file,issue,loop,correction,message,skill,cli,snapshot,commit,test_run}`) — both need `usage` appended, or the reference goes stale. The `little_loops.session_store` module reference prose ("the five JSONL-derived `_backfill_*` functions", `:7244`) also becomes a stale count once a sixth (`_backfill_usage_events`) is added.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — beyond the general "usage-events section" already noted: a per-table reference row (pattern: `commit_events` row `:92`, `test_run_events` row `:93`), a `--kind` enum list at `:166` (`tool, file, issue, loop, correction, message, skill, cli, commit, test_run`), and worked `ll-session recent --kind X` examples in the task→command table (`:32-41`) all need a `usage` entry.

### Configuration

- `.ll/ll-config.json` — `analytics.capture.usage_events` (default `true`) gates the per-event write; `analytics.enabled` (default `false`) gates the whole feature. Existing `analytics.capture.{skills,cli_commands,corrections,file_events}` set the precedent.

### Additional findings (2026-07-07 re-research)

_Added by `/ll:refine-issue` — gaps surfaced by re-running codebase research:_

- **`_EXPORT_DEFAULT_TABLES` is a separate registration** — `_EXPORT_TABLE_MAP` is documented at `session_store.py:2791-2814`, but the companion `_EXPORT_DEFAULT_TABLES` list (`:2804-2814`) is the default set `ll-session export` ships when no `--tables` is passed. Both need `"usage_event"` added — only `_EXPORT_TABLE_MAP` was called out in the prior pass. Missing the default-list entry makes `ll-session export` skip `usage_events` until a user passes `--tables usage_event` explicitly.
- **`observability/schema.py:460` schema docstring** — module docstring lists the per-table schemas; new table needs an entry alongside the existing `skill_events` mention. This is the only docs surface that auto-syncs with the table list (no separate docs page for `usage_events`).
- **`record_usage_event()` should accept `config: dict | None = None`** — both `record_commit_event` and `record_test_run_event` accept a `config` forward-compat parameter that's currently unused but reserved for future `analytics.capture.commits` / `analytics.capture.test_runs` gating. Mirror the same shape on `record_usage_event()` so the `analytics.capture.usage_events` gate can be activated without a signature change.

## Producer-side test pattern (closer than `--kind commit`)

_Added by `/ll:refine-issue` — re-research surfaced a more direct test template:_

- `scripts/tests/test_subprocess_utils.py:1552-1759` already covers the `on_usage_detailed` callback at the producer site (`test_on_usage_detailed_callback_called_with_result_event`, `test_on_usage_detailed_not_called_when_no_usage`, `TokenUsage.model` init-event fallback). Add `test_on_usage_detailed_writes_usage_event_to_history_db` here — feeds a synthetic `{"type":"result","usage":{...},"model":"claude-sonnet-4-6"}` JSON-line through `run_claude_command()` and asserts the new `usage_events` row was inserted. This locks the producer-side integration closer to the source than the CLI `--kind usage` test in `test_ll_session.py:949-975`, and reuses fixtures already set up for callback behavior tests.

### Open Design Decision: usage_events join key + write grain

Two orthogonal axes were left unresolved by prior research passes:

1. **Join key** — should `usage_events.tool_event_id` be a foreign key to
   `tool_events.id` (1:1 mapping, requires `tool_events` to write first), or
   should the tables stay independent and join on `(session_id, ts)` (writer
   order free)?
2. **Write grain** — one row per `TokenUsage` (per LLM call, ~one per loop
   iteration — matches when `on_usage_detailed` actually fires), or one row
   per FSM state (aggregated rollup — matches the existing
   `fsm/persistence.py:684` `usage.jsonl` writer, which fires N times per
   state and sums)?

Because the two axes combine, the options below enumerate all four
combinations so one can be selected outright rather than decided piecemeal.

### Option A: FK to `tool_events` + per-call grain

`usage_events.tool_event_id REFERENCES tool_events(id)`, one row written per
`on_usage_detailed` invocation (per LLM call). Preserves exact 1:1 joinability
to the byte-count row for the same call, at the cost of requiring
`record_tool_event`-equivalent write-ordering (`tool_events` row must exist
first) and finer-grained storage (more rows).

### Option B: FK to `tool_events` + per-state grain

`usage_events.tool_event_id REFERENCES tool_events(id)`, one row written per
FSM state (sum of all `TokenUsage` calls within the state), matching the
current `fsm/persistence.py:684` rollup semantics. Fewer rows, but loses
per-call granularity and still carries the FK write-ordering constraint.

### Option C: Independent table (join on `session_id, ts`) + per-call grain

> **Selected:** Option C — matches the landed `_backfill_*`/`rebuild()` architecture (independent per-row parsing over `raw_events`, no cross-table FK), and per-call grain is the only grain the transcript stream actually carries.

No FK; `usage_events` is written independently keyed on
`(session_id, ts, model)`, one row per `on_usage_detailed` call. Writer order
is unconstrained (matches the `record_commit_event`/`record_test_run_event`
sibling-table precedent this issue's Codebase Research Findings already point
to), and per-call granularity is preserved for cost/cache analysis.

### Option D: Independent table (join on `session_id, ts`) + per-state grain

No FK; one row per FSM state, aggregated the same way as the current
`usage.jsonl` writer. Simplest migration off the existing rollup behavior,
but loses per-call granularity and makes `(session_id, ts)` join keys
ambiguous when a state has more than one LLM call inside the same second.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-12.

**Selected**: Option C — Independent table (join on `session_id, ts`) + per-call grain

**Reasoning**: The superseding-architecture banner and Post-ENH-2581 Codebase Research
Findings (top of this issue) already establish that `usage_events` is populated by a
`_backfill_usage_events()` parser plumbed into `rebuild()`, not a live writer at the
`on_usage_detailed` callback site. Reading `session_store.py` confirms `tool_events`
itself is now derived the same way (`_backfill_tool_events(conn, _raw_events_cursor())`,
`session_store.py:2610`), and every table in `_REBUILD_TABLES` (`:2554-2563`) is rebuilt
independently by replaying `raw_events` through its own `_backfill_*` parser — there is no
cross-table FK dependency or write-ordering constraint anywhere in `rebuild()`
(`:2596-2615`). That eliminates Options A/B outright: an FK to `tool_events.id` would
require `tool_events` to be populated first specifically for this join, which contradicts
the independent-parser pattern every sibling table already follows. Grain is decided by
the source stream, not a design preference: `raw_events` rows are individual transcript
lines with no FSM-state boundary information, so only per-call grain (Option C) is
derivable — per-state grain (Options B/D) would require correlating rows back to loop
state via out-of-band bookkeeping the transcript doesn't carry. Option C is therefore the
only option consistent with the architecture this issue's own research already locked in.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| A: FK + per-call | 0/3 | 1/3 | 1/3 | 1/3 | 3/12 |
| B: FK + per-state | 0/3 | 0/3 | 0/3 | 0/3 | 0/12 |
| C: Independent + per-call | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| D: Independent + per-state | 1/3 | 1/3 | 1/3 | 1/3 | 4/12 |

**Key evidence**:
- Option C: mirrors `_backfill_tool_events()` (`session_store.py:1702-1741`) directly —
  same `_iter_events()`/filter/insert/`_index()` shape every `_backfill_*` parser uses;
  test template is `TestRebuild` (`test_session_store.py:2744-2841`, seed-raw-events →
  `rebuild()` → assert counts).
- Options A/B: an FK to `tool_events.id` conflicts with every table in `_REBUILD_TABLES`
  (`session_store.py:2554-2563`) being wiped and re-derived independently
  (`rebuild()` `:2596-2615`) — no backfill parser today reads another backfilled table's
  rows to resolve a foreign key.
- Options B/D: `raw_events` carries transcript lines, not FSM-state boundaries — per-state
  aggregation isn't derivable from the source `_backfill_*` parsers read from.

### Addendum: consumer-schema conflict resolved (2026-07-12, session handoff follow-up)

`/ll:confidence-check` (Outcome Risk Factors, below) surfaced that two
already-existing gated consumers —
`fsm/cost_graph.py::_from_history`/`PerStateCost.from_history`
(`cost_graph.py:279-359`) and `cli/ctx_stats.py::_aggregate_usage_events`
(`ctx_stats.py:169-222`) — both query a **singular** `usage_event` table
grouped **by FSM `state`**, which conflicts with Option C's **plural**
`usage_events`, independent, **per-call**-grain schema. (Addendum 2 below adds
a nullable `state` column for forward compat, but this issue's parser never
populates it — see Addendum 2 for why.)

**Verified before deciding**: both consumers are dead stubs today — grep
confirms no caller invokes `PerStateCost.from_history()` or
`_aggregate_usage_events()` anywhere outside their own definitions and the
gating tests, and their gating tests
(`test_from_history_falls_back_when_table_absent`,
`test_from_history_returns_list_type` in
`scripts/tests/test_fsm_cost_graph.py:239-`) only assert graceful
degradation when the table is absent — neither locks the singular table
name or the `state`-grouping shape against real data. `PerStateCost.to_dict()`'s
key set (including `state`) *is* locked by
`TestPerStateCost::test_to_dict_exact_keys`, but that test only constructs
`PerStateCost` instances directly — it says nothing about what
`_from_history` must query or bucket by. So both functions are safe to
rewrite; they were written speculatively before Option C existed, not as
locked contracts.

**Resolution — Path 1, with a semantic split rather than a forced fit**:
per-call `usage_events` rows carry no FSM-state boundary (confirmed by the
Decision Rationale above: `raw_events` lines have no state info), so forcing
them into `PerStateCost`'s `state`-keyed shape would require inventing a
fake state label. Instead:

- **True per-state cost stays served by the existing live path** —
  `CostReport`/`PerStateCost.from_usage_jsonl()` (already implemented,
  reading `${run_dir}/usage.jsonl`, which **does** carry state because
  `fsm/persistence.py:684`'s writer fires per-state during a live run).
  Nothing changes here.
- **`_from_history`/`PerStateCost.from_history` is retired**, not rewritten
  onto the new schema — it was speculative history-DB-backed per-state
  cost, and per-state grain is architecturally undependable from
  `usage_events`. Remove the `_from_history` function and the
  `PerStateCost.from_history` classmethod attachment
  (`cost_graph.py:279-359`), along with their two gating tests. If a
  history-DB-backed cost view is wanted later, it belongs on the
  already-planned `aggregate_usage(group_by: Literal["model","skill","session"], ...)`
  Read API (Proposed Solution § Read API, this issue's own scope) — a
  plain rollup dict, not a `PerStateCost` list.
- **`ctx_stats.py::_aggregate_usage_events` is rewritten, not retired** —
  it's already wired into `ll-ctx-stats`'s `--json` payload path (per the
  superseding banner: "the `ll-ctx-stats` consumer wiring ... already waits
  for this"), so it needs a working body. Query `usage_events` (plural,
  Option C columns: `session_id, ts, model, state, input_tokens, output_tokens,
  cache_read_input_tokens, cache_creation_input_tokens, cost_usd` — no
  `wallclock_ms`; `state` exists per Addendum 2 but is always `NULL` on
  parser-written rows) and aggregate **by `model`**, not by `state`.
  Rename the returned dict's `"per_state"` key to `"per_model"` in both the
  function body and its docstring (`ctx_stats.py:190-201`); drop
  `wallclock_ms` from the per-bucket shape since `usage_events` doesn't
  carry it. Update Implementation Steps §8 / Integration Map / Tests
  entries below accordingly when implementation starts.

This directly changes two references elsewhere in this issue:
- Integration Map's `from_usage_db()` bullet (§ Files to Modify /
  Dependent section) — that method name/shape no longer applies; see the
  corrected Integration Map bullet.
- Tests § `test_fsm_cost_graph.py` bullet — no "symmetrical test for
  `from_usage_db()`" is needed; add a removal/deprecation test instead
  (assert the retired classmethod/function no longer exists, or simply
  delete the two now-obsolete gating tests as part of the removal).

### Addendum 2: nullable `state` column added for forward compat; live per-state writer deferred (2026-07-13)

Revisits the "per-call vs per-state grain" question above after further
discussion. Verified two facts against the current codebase before deciding:

- **`raw_events` is post-hoc only, never live.** `_backfill_raw_events()` is
  invoked exclusively via `backfill_worker.py`, spawned as a detached
  subprocess from the **next session's** `SessionStart` hook
  (`hooks/session_start.py:124-179`), plus `backfill_incremental()`/`backfill()`
  batch sweeps. No hook ingests JSONL into `raw_events` during an active
  session. This means grain (per-call vs per-state) was never the blocker for
  "realtime artifacts" — the producer path itself lags by at least one session
  boundary regardless of grain. Building a genuinely live per-state view
  requires a *different* producer (writing at the `on_usage_detailed` callback
  during the run), not a change to how the `raw_events`-derived parser buckets
  rows.
- **FSM state is not threaded to the callback today.** `_run_action()`
  (`fsm/executor.py:1452`) calls `action_runner.run()` passing `on_usage` but
  **not** `on_usage_detailed` — the executor drops it on the floor even though
  `DefaultActionRunner.run()` (`fsm/runners.py:91-100`) already accepts the
  parameter. Wiring a live per-state writer would need `on_usage_detailed`
  threaded from `_run_action()` through the runner call, plus a new state-name
  parameter threaded into `run_claude_command()` (`subprocess_utils.py:282`)
  down to the callback invocation site (`:457-470`). Concretely scoped
  (3-5 call sites), but it is new producer wiring outside the
  "parser over `raw_events`" pattern this issue is scoped to.

**Decision**: keep Option C (independent table, per-call grain, populated only
by the `raw_events` parser) as this issue's scope — do not add a live writer
here. But add a nullable `state TEXT` column to the schema now as a free
forward-compat hook: rows written by this issue's parser always have
`state = NULL` (the transcript stream carries no state boundary, per the
Decision Rationale above), but the column exists so a future live writer can
populate it without a schema migration. Concrete schema:

```sql
CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT,
    model TEXT,
    state TEXT,  -- NULL for all rows written by this issue's raw_events parser;
                 -- reserved for a future live per-state writer (see below)
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_input_tokens INTEGER,
    cache_creation_input_tokens INTEGER,
    cost_usd REAL
);
CREATE INDEX IF NOT EXISTS idx_usage_events_session ON usage_events(session_id);
CREATE INDEX IF NOT EXISTS idx_usage_events_model ON usage_events(model);
```

**Follow-on scoped separately, not in this issue**: a live per-state usage
writer (bypassing `raw_events`, writing at the `on_usage_detailed` callback
site with FSM state context threaded through) is real future value — it's
the only path to both realtime artifacts and true per-state cost attribution
without waiting on `usage.jsonl`'s file-based rollup. This belongs under
EPIC-2457 as its own FEAT (the backlog-grooming session log already flags an
"F6 per-state cost attribution" item there) — scope it once this issue's
batch/parser path has landed and the `state` column exists to populate.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-12_

**Readiness Score**: 89/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 58/100 → Low confidence

### Concerns
- Target `SCHEMA_VERSION` is stale in the issue text: `SCHEMA_VERSION` is currently **19** and `_MIGRATIONS` index 18 ("v19") is already ENH-2581's `raw_events` table. The `usage_events` migration must target **v20**, not v19 (the superseding banner already flags v19 collision generally, but the concrete replacement value — 20 — wasn't stated anywhere in the issue).
- `subprocess_utils.py` line citation for the `on_usage_detailed`/`etype == "result"` block should read **449–465**, not 449–470 (confirmed against current working tree).

### Outcome Risk Factors
- Open decision: resolve before implementing — the two already-existing gated consumers (`scripts/little_loops/fsm/cost_graph.py::_from_history` / `PerStateCost.from_history`, lines 279–359; `scripts/little_loops/cli/ctx_stats.py::_aggregate_usage_events`, lines 169–221) both query a **singular** `usage_event` table with **per-FSM-state grain** — columns `state`, `wallclock_ms`, `cache_read_tokens`/`cache_creation_tokens` (no `_input` suffix), grouped by `state` for `PerStateCost` buckets. This directly conflicts with the issue's own Decided Option C schema: **plural** `usage_events`, independent **per-call** grain keyed on `(session_id, ts, model)`, no `state` column, and `cache_read_input_tokens`/`cache_creation_input_tokens` naming (locked by the FEAT-2478 OTel mapping table). Neither the `/ll:wire-issue` pass (which found these consumers) nor the `/ll:decide-issue` Option C selection (decided on write-ordering/architecture-consistency grounds only) accounted for this contract mismatch. The `on_usage_detailed` callback also has no FSM-state context available at its call site (`subprocess_utils.run_claude_command()`, decoupled from `fsm/executor.py`), so per-state aggregation isn't free to add. This needs an explicit resolution — e.g. rewrite both consumers to bucket per-call rows by another key, thread state context into the callback, or accept the consumers are rewritten as part of this issue rather than reused as-is — before implementation starts.
- Deep per-site complexity: reconciling the two mismatched consumers (beyond the enumerated Integration Map, which lists them only as "gated, gets un-gated" — not as needing a schema-shape rewrite) adds unplanned Moderate-complexity work on top of the otherwise mechanical `_backfill_*`/kind-registration fanout.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-12_

**Readiness Score**: 96/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- Deep per-site complexity: two Implementation Steps bullets (Step 6, and the
  Integration Map `fsm/persistence.py` bullet) still pose "decide whether
  `record_usage_event()` also writes per-state at the FSM aggregation site" as
  an open choice, but the Addendum above (2026-07-12) already closed this —
  Option C is per-call grain only, independent of `tool_events`/FSM-state
  bookkeeping. These two bullets are stale text left over from before the
  Addendum and should be edited to state the closed answer (no per-state
  write) rather than re-posing it as a decision, or an implementer may
  needlessly re-litigate it.
- Broad enumeration across 9+ sites: schema migration, kind registration
  (3 coupled points plus `rebuild()`'s `counts` dict and
  `_REBUILD_SEARCH_KINDS`), writer, read API, CLI `--kind` arrays, `ll-ctx-stats`
  rewrite, config gating (2 files + schema), `cost_graph.py` retirement, and
  4 docs files. Individually mechanical (matches `_backfill_tool_events`/
  `record_commit_event` templates), but the sheer count raises the chance of
  missing one registration point on the first pass — `ll-verify-kinds` and
  `TestValidKindsCentralization` catch the kind-table case, but there's no
  automated gate for the `_REBUILD_SEARCH_KINDS`/`counts`-dict/docs-drift
  omissions the `/ll:wire-issue` pass already had to backfill once.

## Resolution

_Implemented 2026-07-13 via `/ll:manage-issue`._

Landed Option C (independent `usage_events` table, per-call grain, populated by a
`raw_events` parser) exactly as decided, at **schema v20** (v19 was ENH-2581's
`raw_events`, as flagged).

**Corrected the decided-but-wrong parser filter.** The `/ll:decide-issue` and
`/ll:wire-issue` passes concluded the parser should filter `type == "result"`.
That is wrong for the `raw_events` path — verified by inspecting real
`~/.claude/projects/.../*.jsonl` transcripts (which the issue itself flagged as a
required implementer check, lines 94–97): **on-disk transcripts contain no
`type == "result"` events at all**; the usage block lives on `type ==
"assistant"` records at `message.usage` (fields `input_tokens`, `output_tokens`,
`cache_read_input_tokens`, `cache_creation_input_tokens`; model at
`message.model`). The `type == "result"` shape only exists in the *live
subprocess stdout* stream (`subprocess_utils.py`), which `raw_events` never
ingests. `_backfill_usage_events()` therefore filters `type == "assistant"` — the
same filter `_backfill_tool_events` uses.

**Delivered:**
- `session_store.py`: v20 `usage_events` migration (with forward-compat nullable
  `state`), `SCHEMA_VERSION → 20`, kind registration (`VALID_KINDS`,
  `_KIND_TABLE`, `_EXPORT_TABLE_MAP`, `_EXPORT_DEFAULT_TABLES`),
  `_backfill_usage_events()` (parses `message.usage`, computes `cost_usd` via
  `pricing.estimate_cost_usd`, `_index(kind="usage")`), wired into `rebuild()`
  (`_REBUILD_TABLES`, `_REBUILD_SEARCH_KINDS`, `counts` dict).
- `history_reader.py`: `UsageEvent` dataclass, `recent_usage_events()`,
  `aggregate_usage(group_by="model"|"session")`.
- `cli/ctx_stats.py`: `_aggregate_usage_events()` rewritten to read `usage_events`
  (plural) and aggregate by **model** (`per_model` / `totals`); JSON payload key
  `per_state_cost` → `usage_by_model`.
- `fsm/cost_graph.py`: retired the speculative `_from_history` /
  `PerStateCost.from_history` (per-state grain isn't derivable from per-call
  rows); live `from_usage_jsonl()` still serves true per-state cost.
- Config: `analytics.capture.usage_events` (default `true`) in
  `config/features.py`, `init/core.py`, `config-schema.json` (forward-compat gate
  — parser path is currently ungated like every other `_backfill_*`).
- Tests: parser/rebuild/FTS/idempotency + schema-column + read-API + CLI `--kind
  usage` + ctx-stats aggregation; removed the two retired `from_history` gating
  tests; bumped schema-version guard assertions 19 → 20.
- Docs: ARCHITECTURE (v20 row), CONFIGURATION, API (`--kind` enums ×2), and
  HISTORY_SESSION_GUIDE.

Codex/OpenCode producer wiring remains out of scope (FEAT-2123); a live per-state
writer remains a separate future FEAT under EPIC-2457 (the `state` column exists
to receive it). Full suite: 14829 passed, 36 skipped; mypy/ruff/verify-kinds clean.

## Status

**Done** | Created: 2026-07-02 | Completed: 2026-07-13 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-07-13T03:40:10Z - `3b600dd8-fd2d-4f5d-b24d-8db33c7e0cda.jsonl` - Implemented Option C at schema v20. Corrected the decided-but-wrong parser filter: verified against real transcript JSONL that usage lives on `type == "assistant"` `message.usage` (no `type == "result"` events exist on disk — that shape is live-stream-only), so `_backfill_usage_events()` filters `assistant`. Added schema+parser+kind-registration+read-API+ctx-stats rewrite, retired `cost_graph._from_history`, wired `analytics.capture.usage_events`, added tests and docs. Full suite green (14829 passed).
- `/ll:ready-issue` - 2026-07-13T03:12:39 - `c2c3ae67-1a28-414c-8910-f4f88f571f3e.jsonl`
- session-followup - 2026-07-13 - Revisited the per-call-vs-per-state write question after pushback: verified `raw_events` is populated only post-hoc (via the next session's `SessionStart` hook spawning `backfill_worker`, `hooks/session_start.py:124-179`), so grain was never the blocker for realtime — and confirmed `_run_action()` (`fsm/executor.py:1452`) currently drops `on_usage_detailed` entirely rather than passing it to the runner, so live per-state writing needs new threading regardless. Added Addendum 2: kept Option C (per-call, parser-only) as this issue's scope, added a nullable `state` column to the schema now as a free forward-compat hook (always `NULL` on parser-written rows), and pointed the actual live per-state writer at a separate future FEAT under EPIC-2457 (F6). Updated the Step 6 and `fsm/persistence.py` Integration Map bullets and the `ctx_stats.py` rewrite bullet to reference the new column.
- `/ll:confidence-check` - 2026-07-12T00:00:00Z - `000ba01e-76b0-4308-a39e-fdaf76f9715c.jsonl` - Re-ran after the session-handoff-followup addendum resolved the consumer-schema conflict. Verified against current codebase: `SCHEMA_VERSION` still 19 (v20 target confirmed correct), `cost_graph.py::_from_history`/`ctx_stats.py::_aggregate_usage_events` still unmodified stubs (retirement/rewrite not yet implemented, as expected pre-implementation), ENH-2581's `raw_events` confirmed landed. Readiness 89→96 (dependency now satisfied), Outcome Confidence 58→72 (ambiguity resolved by the Addendum; residual risk is two stale "Decide" bullets not yet edited to reflect the closed decision, plus broad 9+-site enumeration). Cleared `decision_needed` (true→false): no unresolved decision phrase remains once the Addendum's resolution is accounted for.
- session-handoff-followup - 2026-07-12 - Resolved the consumer-schema conflict the confidence-check flagged (Outcome Risk Factors, below): verified both gated consumers are dead stubs (no external callers, gating tests only assert table-absent fallback), then decided to retire `fsm/cost_graph.py::_from_history`/`PerStateCost.from_history` (per-state grain isn't derivable from per-call `usage_events`; the live `from_usage_jsonl()` path already serves true per-state cost) while rewriting `ctx_stats.py::_aggregate_usage_events` to aggregate by `model` instead of `state` (it's actively wired into `ll-ctx-stats --json`, so needs a working body). Added § Addendum documenting the resolution and updated the two stale Integration Map/Tests bullets. Also corrected the stale `SCHEMA_VERSION` target (18→19 bump was written before ENH-2581 landed; now 19→20) in the Codebase Research Findings text itself, not just the Confidence Check Notes. `decision_needed: true` left as-is per the confidence-check's own guidance — re-run `/ll:confidence-check` next to confirm the Outcome Confidence score improves.
- `/ll:confidence-check` - 2026-07-12T00:00:00Z - `c2ff78ca-05db-43cc-a456-2007dca1d30b.jsonl`
- `/ll:wire-issue` - 2026-07-12 - Ran 3 parallel wiring agents against the decided Option C architecture. Resolved the issue's open question (`type: "result"` carries the usage block, not `"assistant"`). Found two previously-undocumented gated consumers (`fsm/cost_graph.py:from_usage_db()`, already-wired `ctx_stats.py:_aggregate_usage_events()`), the `ll-verify-kinds` hard registration gate, `rebuild()`'s hand-written `counts` dict and `_REBUILD_SEARCH_KINDS` as registration points distinct from `_KIND_TABLE`, and added `docs/reference/API.md` (hardcoded `--kind` enum, twice) plus test-gate/idempotency guidance to Tests.
- `/ll:decide-issue` - 2026-07-13T02:06:25 - `a7c5487e-f796-4e58-b6f5-9fbe53a24e59.jsonl`
- `/ll:decide-issue` - 2026-07-13T01:56:12 - `0dc38829-e8c5-4a7a-8b8e-ddf3d621f576.jsonl`
- `/ll:refine-issue` - 2026-07-13T01:53:23 - `78982ff4-eb9c-4c6e-97ff-8c3a0cb73668.jsonl`
- sequencing-review - 2026-07-12 - Resolved the v19 schema collision with [[ENH-2581]]: ENH-2581 owns v19 (`raw_events`) and lands first; this issue is now `blocked_by`/`depends_on` ENH-2581 and reframed from "add a `usage_events` sibling table" to "add a usage `event_type` parser over `raw_events`". Closed the Option A/B `decision_needed` (both obsolete — neither sibling-table form; parser path instead). Added superseding-decision banner at top. FEAT-2123 (blocked by this) is not urgent, so foundation-first ordering was chosen.
- `/ll:refine-issue` - 2026-07-07T06:54:22 - `d46e494f-5673-4564-b202-2b832d02834f.jsonl`
- `/ll:refine-issue` - 2026-07-06T23:57:55 - `393e0dc2-c1c3-43c5-b47a-60f52a6d21c0.jsonl`
- `/ll:explore-api phoenix` - 2026-07-05 - Added Cross-issue coordination note: internal token columns stay underscore, but FEAT-2478's OTel mapping for the two cache columns must use DOTTED names (`gen_ai.usage.cache_read.input_tokens`) — string-prefixing the column name silently breaks OTel-semconv consumers (Phoenix verified). Locked the column→attribute mapping table.
- backlog-grooming - 2026-07-03T00:00:00Z - Consolidated token-telemetry workstream: this issue is sequenced first (Claude host; `on_usage_detailed` already exists), it `blocks` FEAT-2123 (Codex/OpenCode extension of the same callback contract), and it `relates_to` EPIC-2456 whose F5 (OTel `gen_ai.usage.*` emission) and F6 (per-state cost attribution) consume the persisted usage rows.
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
