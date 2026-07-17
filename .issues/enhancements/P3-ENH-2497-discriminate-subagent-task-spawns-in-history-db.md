---
id: ENH-2497
title: Discriminate sub-agent / Task spawns in history.db
type: ENH
priority: P3
status: open
discovered_date: 2026-07-05
captured_at: "2026-07-05T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
decision_needed: false
labels:
  - enhancement
  - history-db
  - agents
  - captured
---

# ENH-2497: Discriminate sub-agent / Task spawns in history.db

## Summary

Sub-agent spawns (the `Task` tool dispatching `codebase-locator`,
`loop-specialist`, `Explore`, etc.) land in the DB as **generic `tool_events`
rows** with `tool_name="Task"` and no `agent_type` — so "which subagents actually
get used, and how often?" can't be answered without parsing the opaque `args_hash`.
That's a real blind spot for the same skill-health story `ll-logs dead-skills` and
`ll-ctx-stats` already serve for skills. Add an `agent_type` discriminator for
Task-tool events (a nullable column on `tool_events`, or a dedicated
`agent_spawn` kind) captured at `post_tool_use` time, so subagent usage is
first-class and joinable.

## Motivation

- **Subagent usage is invisible.** The plugin ships 9 agents
  (`agents/*.md`); nothing tells you which are dead weight vs. load-bearing.
- **Symmetry with the skill-health tooling.** ENH-2460 gave skills exit_code /
  duration; `dead-skills` / `ctx-stats` surface skill usage. Agents deserve the
  same, and the hook already fires on every `Task` call.
- **Cheap, additive, hook-side.** The `post_tool_use` handler already sees the
  `Task` tool invocation and its input (which carries `subagent_type`); it just
  isn't extracted.

## Current Behavior

- A `Task` spawn is recorded by `post_tool_use` as a `tool_events` row with
  `tool_name="Task"`, `args_hash`, byte accounting — no `agent_type`.
- There is no way to `GROUP BY agent_type` or to FTS-search by agent.
- `ll-ctx-stats` / `ll-logs dead-skills` cover skills, not agents.

## Expected Behavior

- Task-tool events carry the dispatched `agent_type` (e.g. `codebase-locator`,
  `Explore`, `loop-specialist`).
- `ll-session recent --kind agent_spawn` (or a filter on `tool_events`) returns
  per-agent rows; agent usage is groupable.
- `ll-ctx-stats` (or a small new surface) can report per-agent invocation counts.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py:102` — `SCHEMA_VERSION = 18`; bump to `19` after the additive `ALTER TABLE` lands (precedent: `skill_event_context` ENH-2460 at v15 uses the same `ALTER TABLE … ADD COLUMN` shape).
- `scripts/little_loops/session_store.py:208` (`_MIGRATIONS` list) — append a new migration entry. Use the v15 ENH-2460 template at `_MIGRATIONS` index 14 (lines 451-459) and the v16 ENH-2462 template at index 15 (line 466-468: `ALTER TABLE … ADD COLUMN` + `CREATE INDEX`) for the column-and-index pair. The agent list is small (≤9 names today), so a single B-tree index on `agent_type` is sufficient.
- `scripts/little_loops/session_store.py:1620-1664` (`_backfill_tool_events`) — also pull `subagent_type` from `args.get("subagent_type")` when backfilling, so historical JSONL sessions are rebuilt with the discriminator; mirror the existing `INSERT INTO tool_events(...)` shape at lines 1649-1654.
- `scripts/little_loops/hooks/post_tool_use.py:159-180` — extend the live insert at lines 163-177 to include `agent_type` populated from `tool_input.get("subagent_type")` when `tool_name == "Task"` (else NULL). Wrap the change in the existing `contextlib.suppress(Exception)` at line 158 (EPIC-1707 best-effort contract — see *Codebase Research Findings* below).
- `scripts/little_loops/hooks/__init__.py:52-55` — the `_USAGE` banner is a static intent list; no edit needed for this issue, but **the reference_dispatch_table_usage_banner memory notes a hook intent list must be updated when adding new intent handlers** (not applicable here since `post_tool_use` already exists).
- `scripts/little_loops/history_reader.py` — add a typed `agent_usage(since=None, db=...)` query (mimics `recent_skill_events` / `summarize_skills` style) and a `recent_tool_events(agent_type=...)` filter returning rows from the existing `tool_events` table joined on the new column. No `ToolEvent` dataclass exists today; either add one (mirroring `IssueEvent` at lines 96-103) or just return dicts.
- `scripts/little_loops/cli/ctx_stats.py:118` (`_aggregate_tool_events`) and `:504-525` (JSON/text rendering) — extend with a per-`agent_type` aggregation when `tool_name == "Task"`; the per-tool-name grouping at line 118 is the closest in-tree analogue to follow.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_store.py:1268-1289` (`recent(db, *, kind)`) — currently emits `SELECT * FROM tool_events`, so the new column will appear in returned dicts automatically for `kind="tool"`. No code change required, but spec the column in any docs that list the `recent` row shape.
- `scripts/little_loops/history_reader.py:752-756` (`lookup_session_metadata`'s `tool_count` query) — runs `SELECT COUNT(*) FROM tool_events WHERE session_id = ?`; will continue to work unchanged.
- `scripts/little_loops/cli/ctx_stats.py:118-130` — currently aggregates `tool_name` for the per-tool summary; would need a sibling query (or UNION) for per-agent summary.

#### Dependent Files (Wiring-pass additions)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/cli/session.py:466-467` — `ll-session recent --kind tool` text-render iterates `row.items()` and prints `f"{k}={v}"` for every non-NULL column. The new `agent_type` column will surface as `agent_type=<name>` in user-facing output for Task rows; non-Task rows remain unaffected (NULL values are filtered). **No code change required** — flagged because the issue Map listed `recent()` as a caller but did not call out the user-facing CLI text change. Verify by `ll-session recent --kind tool --limit 5` after migration lands.

### Similar Patterns
- `scripts/little_loops/session_store.py:451-459` (v15 ENH-2460) — `ALTER TABLE skill_events ADD COLUMN exit_code INTEGER; ALTER TABLE skill_events ADD COLUMN success INTEGER; ALTER TABLE skill_events ADD COLUMN duration_ms INTEGER;`; the docstring at lines 453-454 explicitly describes the additive-nullable convention: *"Nullable so pre-migration dispatch-only rows remain valid (NULL = 'no completion signal recorded')."* Use the same template here.
- `scripts/little_loops/session_store.py:466-468` (v16 ENH-2462) — single-column `ADD COLUMN` plus companion `CREATE INDEX`; closest analogue to v19's `agent_type` + index.
- `scripts/little_loops/history_reader.py:96-121` (`IssueEvent` / `SkillEvent` dataclasses) — declare the new field as `agent_type: str | None = None`; `_row_to_dataclass` at line 252-256 uses `f.name in row.keys()` so an absent DB column yields the dataclass default automatically.
- `scripts/little_loops/cli/ctx_stats.py:354-377` (`_print_json` / `_render` skill_health block) — exact template for a per-entity-type usage summary line.

### Tests
- `scripts/tests/test_session_store.py:3095-3148` (`TestSchemaV15SkillCompletionColumns`) — three-test pattern for the migration: `test_*_has_columns` (PRAGMA), `test_v{N-1}_db_upgrades_preserving_*` (bootstrap at N-1, run upgrade, assert column reads back NULL on pre-existing rows), `test_dispatch_only_*_leaves_*_null`. Mirror this for v19.
- `scripts/tests/test_session_store.py:3075-3094` (`_bootstrap_schema_at` helper) — bootstrap a v18 DB, then `ensure_db()` should bump to v19 with `agent_type` readable and NULL on pre-existing rows.
- `scripts/tests/test_session_store.py:3151-3193` (`TestSkillEventContext`) — round-trip test for ENH-2460; analogous tests for the per-Task-spawn insert site.
- New file (suggested): `scripts/tests/test_enh_2497_agent_type.py` — covers `TestTaskSpawnAgentType` (insert Task with `subagent_type="codebase-locator"`, expect row has `agent_type="codebase-locator"`), `TestNonTaskNullAgent` (insert Write/Edit, expect `agent_type=NULL`), `TestAgentUsageAggregation` (multiple Task rows of mixed agents, expect per-agent counts), and a graceful-missing-field test (insert Task with no `subagent_type` → row has `agent_type=NULL`, no exception).

#### Tests (Wiring-pass additions)

_Wiring pass added by `/ll:wire-issue`:_

- **Version renumber (load-bearing).** `SCHEMA_VERSION = 20` today at `session_store.py:207`; the new migration lands in slot **v21**, not v19 (the issue body's "bump 18→19" text is stale per the Scope Boundary note at the bottom of this file). The suggested class `TestSchemaV19AgentType` and the `_bootstrap_schema_at(db, 19)` bootstrap call in the Implementation Steps below must be renamed to `TestSchemaV21AgentType` and `_bootstrap_schema_at(db, 20)` respectively. Failure to renumber causes the bootstrap fixture to skip the new migration entirely. Mirror `TestSchemaV14.test_schema_version_is_fourteen` at `scripts/tests/test_session_store.py:3691-3700` as the simplest version-bump assertion template.

- **NEW test (mandatory).** `test_live_write_filled_in_search_index` in the suggested `test_enh_2497_agent_type.py` — directly closes the FTS acceptance-criterion gap. The issue's Implementation Step 4 wires `_index()` into `post_tool_use.handle()` with `content=f"{tool_name} {agent_type or ''}".strip()`, but no current test asserts that `_index()` is called after the live INSERT. Closest reusable template: `scripts/tests/test_hook_post_tool_use.py:367-388` (`test_fts5_search_index_updated`) — query `search_index WHERE content LIKE '%<agent>%'` after a `Task` event and assert a `kind="tool"` row exists. Without this test, the FTS acceptance criterion is enforced by no automated check.

- **NEW test (mandatory).** `test_tool_events_backfill_populates_agent_type` — closes the backfill-side gap called out in Implementation Step 3 and Codebase Research Findings line 102. Pattern: write a JSONL with an assistant `tool_use` block whose `input.subagent_type="loop-specialist"`, run `backfill(... also_rebuild=True)`, read `recent(db, kind="tool")[0]["agent_type"]`, assert `"loop-specialist"`. Closest template: `scripts/tests/test_session_store.py:475-502` (`TestBackfill.test_backfill_tool_events_from_jsonl`).

- **NEW test (edge case).** `test_readers_return_empty_on_missing_db` — assert both `agent_usage()` and `recent_tool_events(agent_type=None)` return `[]` (not raise) when called against a non-existent DB path. Mirrors `scripts/tests/test_history_reader.py:1530-1545` (TestNewEventReaders missing-DB pattern); closes the `agent_usage()` reader's no-raise contract gap.

- **No-existing-test breakage (verified).** Existing INSERTs into `tool_events` in `scripts/tests/test_history_reader.py:802-811`, `scripts/tests/test_session_store.py:574-577, 595-598`, and `scripts/tests/test_cli_ctx_stats.py:75-78, 682-683` all use fixed column lists. The new `agent_type` column is nullable and defaults to NULL on omitted INSERTs — these tests continue to pass without modification. **No edit required.**

- **No `test_wiring_skills_and_commands.py` entry required.** That file is a doc-wiring inventory sweep over `skills/` and `commands/` strings only; this issue adds no new skill/command content. The wiring-pass report initially flagged this as a candidate; verification confirmed the inventory does not include test files or column-level code changes.

### Documentation
- `docs/ARCHITECTURE.md` — schema versions table (look for the `_MIGRATIONS`-indexed table; bump `18`→`19` and add a row describing the `tool_events.agent_type` addition).
- `docs/reference/API.md` — `session_store`, `history_reader`, and `hooks/post_tool_use` entries; mention the new column on `tool_events`, the new `agent_usage()` helper, and the EPIC-1707 best-effort contract that applies to `post_tool_use`.
- `thoughts/history-db-expand-wiring.md` — §2 (tool-event granularity) — the issue text already cites this; cross-link from the v19 migration comment if §2 is updated.

#### Documentation (Wiring-pass additions)

_Wiring pass added by `/ll:wire-issue`:_

- `docs/guides/HISTORY_SESSION_GUIDE.md:84` — the `tool_events` row in the column-listing table currently shows `bytes_in`, `bytes_out`, `result_size`, `cache_hit`. Add `agent_type` (nullable TEXT, populated for `tool_name="Task"` from `tool_input.subagent_type`) to this row. Line 55 (initial bootstrap table list) is unchanged — only the column row needs the addition.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:258` — the `post_tool_use` hook description currently lists the `tool_events` row shape as "tool name, bytes in/out, cache-hit, args hash". Add `agent_type` to this enumeration, qualified with "(populated when `tool_name=Task`, NULL otherwise)". Line 455 (prunable-tables list) is unchanged.

### Configuration
- None required. The existing `analytics.enabled` gate at `post_tool_use.py:151` already controls whether the `tool_events` row is written at all; the new column rides the same gate and the same best-effort wrap. No new config key.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on direct reading of `session_store.py`, `post_tool_use.py`, and `history_reader.py`:_

- **`tool_events` DDL**: lives in the v0 bootstrap of `_MIGRATIONS` at `session_store.py:210-220`. Columns are `(id, ts, session_id, tool_name, args_hash, result_size, bytes_in, bytes_out, cache_hit)` — no `NOT NULL` constraints, all nullable, so adding a nullable `agent_type` column will not force any rewrite of existing rows.
- **`tool_events` indexes today**: zero. There are no `CREATE INDEX` statements on `tool_events` anywhere in `_MIGRATIONS`. A new `idx_tool_events_agent ON tool_events(agent_type)` is needed (and is the only index addition the migration requires).
- **Live write path inserts 8 columns** (`ts, session_id, tool_name, args_hash, result_size, bytes_in, bytes_out, cache_hit`) at `post_tool_use.py:163-177`. The `tool_input` dict is already on the local scope (line 147), so adding `agent_type = tool_input.get("subagent_type") if tool_name == "Task" else None` is a single-line read followed by a column append.
- **Backfill path** at `_backfill_tool_events:1620-1664` runs the same INSERT shape; `_index()` is also called there with `kind="tool"` to keep `search_index` in sync. Backfilled rows would currently land without `agent_type` even after v19 lands — the backfill pass should be updated in lockstep to extract `args.get("subagent_type")` from the assistant block and pass it through.
- **EPIC-1707 best-effort contract** is referenced by three call sites (`session_store.py:937-940` for `skill_event_context`, `post_commit.py:14-16`, `pytest_history_plugin.py:17-19`). For `post_tool_use.py` the contract is implemented as `with contextlib.suppress(Exception):` at line 158 wrapping the entire INSERT block. The new `agent_type` write must remain inside that wrap and remain nullable so a partial / malformed payload still produces a valid row (criterion from issue line 111-112).
- **FTS coverage gap**: live `handle()` does NOT call `_index()` after the INSERT; only backfill does (`session_store.py:1655`). Issue line 71 (line "FTS-index the agent name") therefore requires either wiring `_index()` after the live insert (matching the backfill call's `content=tool_name, kind="tool"` shape with `agent_type` appended) or accepting that `ll-session search --fts "loop-specialist"` will only surface backfilled rows. The cheapest additive approach: extend `_index()`'s `content` argument to `f"{tool_name} {agent_type or ''}".strip()` once `agent_type` is populated — this makes both backfilled and live rows searchable without any further code changes.
- **`history_reader` modules covered by `tool_events` today**: only `lookup_session_metadata` (line 752-756) and the generic `recent(kind="tool")` from `session_store.py:1268`. No `recent_tool_events`, no `ToolEvent` dataclass, no `agent_usage`. The new helpers are greenfield; follow `recent_skill_events` / `summarize_skills` structure in `history_reader.py` rather than introducing a typed dataclass.
- **`_KIND_TABLE["tool"] == "tool_events"`** is already wired (`session_store.py:120`) so the existing `--kind tool` filter continues to work post-migration with the new column returned automatically. No `_VALID_KINDS`/`_KIND_TABLE` change required for option (A).
- **No `recent_tool_events()` function exists today** — confirmed by reading `history_reader.py:1-1336` in full. The reference at issue line 95 ("Extend `recent_tool_events()` (if present)…") is speculative; the actual greenfield implementation is `recent_tool_events(agent_type=...)` in `history_reader.py`, returning rows from the existing table. Compatible with the generic `recent(kind="tool")` helper.
- **Live `result_size` quirk**: the column is currently set to `bytes_out` (response size) at `post_tool_use.py:175`. Out of scope for this issue but worth noting if a follow-on fixes the column to actually be the response size — independent change.

### Current-tree verification (2026-07-16)

_Added by `/ll:refine-issue` — verified against the current working tree; existing findings above are preserved:_

- **Migration slot must be dynamic**: `session_store.py:207` currently declares `SCHEMA_VERSION = 20`, and `_MIGRATIONS` begins at `session_store.py:333`; the current v20 entry is near `session_store.py:709-733`. The implementation must append the `agent_type` migration after the current last entry (v21 at the time of this pass), not hard-code the historical 18→19 transition. ENH-2511 and ENH-2505 remain coordination constraints for this schema work.
- **Backfill anchors have moved**: `_backfill_tool_events()` is currently `session_store.py:1836-1875`, with `args = block.get("input", {})` and the eight-column insert around `:1859-1865`; the older `:1620-1664` references in this issue are stale line anchors, although the described data flow remains correct.
- **Live and backfill FTS are asymmetric**: `_backfill_tool_events()` calls `_index()` around `session_store.py:1866-1873`, but `post_tool_use.handle()` has no `_index()` call after its live insert (`post_tool_use.py:158-180`). The FTS acceptance criterion therefore requires an explicit live indexing change and a live-path test; adding only the column will not make `ll-session search --fts "loop-specialist"` find newly captured spawns.
- **Read surface remains the existing `tool` kind**: `session_store.py:224` maps `"tool"` to `tool_events`, and `session_store.py:1462-1484` implements the generic `recent()` query with `SELECT *`. No `VALID_KINDS` or dedicated `agent_spawn` kind change is needed for option (A); `cli/session.py:378-387` and `:430-453` already expose FTS search and recent tool rows.
- **Reader helpers are greenfield**: `history_reader.py:466-528` (`recent_skill_events()` / `summarize_skills()`) are the closest templates. There is no existing `recent_tool_events()`, `agent_usage()`, or `ToolEvent` dataclass; if a dataclass is added, `_row_to_dataclass()` at `history_reader.py:273-277` safely handles both pre-migration rows (column absent) and migrated rows (NULL).
- **CLI anchors differ from the older notes**: `_aggregate_tool_events()` is at `cli/ctx_stats.py:118-139`; the JSON `skill_health` analogue is at `:455-471`, while the text renderer spans `:346-435`. The issue's `:354-377` and `:504-525` references should be treated as stale guidance, not implementation locations.
- **Existing tests provide the exact fixtures**: the schema bootstrap helper is `scripts/tests/test_session_store.py:3891-3911`, the v15 nullable-column migration pattern is `:3914-3967`, and the index/`EXPLAIN QUERY PLAN` pattern is in `TestSchemaV16IssueSessionId` around `:4036-4196`. `scripts/tests/test_hook_post_tool_use.py:100-237` covers analytics-gated live writes and best-effort failures but currently has no `Task`/`subagent_type` case; `scripts/tests/test_history_reader.py:1395-1635` is the reader/aggregation fixture pattern.
- **Documentation is also behind the current schema**: `docs/ARCHITECTURE.md` lists schema history through v20, and `docs/reference/API.md` still contains a `SCHEMA_VERSION` example of 19. The implementation pass should add the new migration row after reconciling those existing v19/v20 references rather than documenting an isolated 19 entry.
- **No configuration or hook-dispatch changes are required**: the `analytics.enabled` gate and `contextlib.suppress(Exception)` best-effort envelope in `post_tool_use.py:151-180` already cover this field, and `hooks/__init__.py:52-56` already lists the existing `post_tool_use` intent.

## Proposed Solution

Two viable shapes; **prefer (A)** for minimal schema churn.

### (A) Nullable `agent_type` column on `tool_events`

> **Selected:** (A) Nullable `agent_type` column on `tool_events` — additive migration matches the v15/v16 nullable-column precedent; reuses `_row_to_dataclass()` column-tolerance, existing `SkillEvent`/`summarize_skills()` reader templates, and lands cleanly in the ENH-2497+ENH-2511 batched migration.

```sql
ALTER TABLE tool_events ADD COLUMN agent_type TEXT;  -- NULL for non-Task tools
CREATE INDEX IF NOT EXISTS idx_tool_events_agent ON tool_events(agent_type);
```

- Populate `agent_type` in the `post_tool_use` handler when
  `tool_name == "Task"`, reading `subagent_type` from the tool input.
- FTS-index the agent name (`kind="tool"`, anchor=agent_type) so
  `ll-session search --fts "loop-specialist"` surfaces spawns.

### (B) Dedicated `agent_spawn` kind (if richer per-spawn fields are wanted)

A separate row with `agent_type`, `prompt_preview`, `result_size`, `duration_ms`.
Heavier; only worth it if we want per-spawn outcome beyond what `tool_events`
already accounts. Start with (A); (B) can follow if needed.

For (A): bump `SCHEMA_VERSION` for the additive column (existing rows get
`NULL`). No new `_VALID_KINDS`/`_KIND_TABLE` entry required (reuses `"tool"`); add
`"agent_spawn"` only if pursuing (B).

### Producer wiring

- In the `post_tool_use` Python handler (`scripts/little_loops/hooks/`), when the
  recorded tool is `Task`, extract `subagent_type` from the tool-input payload and
  pass it through to the `tool_events` insert as `agent_type`.
- Best-effort per the EPIC-1707 contract; a missing field just writes `NULL`.

### Read API

- `history_reader.agent_usage(since=None)` — counts per `agent_type`.
- Extend `recent_tool_events()` (if present) with an `agent_type` filter.

### CLI surface

- `ll-ctx-stats`: add a per-agent usage line (optional, follow-on).
- `ll-session search --fts "<agent>"` already works once indexed.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-16.

**Selected**: (A) Nullable `agent_type` column on `tool_events`

**Reasoning**: The additive-column path is the exact precedent set by v15 (ENH-2460 `skill_events` completion columns at `session_store.py:576-584`) and v16 (ENH-2462 `issue_events.session_id` at `:585-594`), and `_row_to_dataclass()` at `history_reader.py:273-277` already tolerates absent columns for pre-migration rows. Option (B)'s proposed fields (`prompt_preview`, `result_size`, `duration_ms`) are either already on `tool_events` (`result_size`/`bytes_out` exist today; `latency_ms` arrives via ENH-2511's same-migration batch) or have no precedent in any `*_events` table (`prompt_preview`), making a separate `agent_spawn` table redundant. ARCHITECTURE-144/145 in `decisions.yaml:5030-5066` explicitly rejected the sibling-table pattern in favor of additive columns when derivable — the same constraint applies here. The only implementation gap for (A) is wiring `_index()` after the live `post_tool_use` insert (live FTS parity with the backfill path), which is a single-call addition at `post_tool_use.py:~179`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| (A) Nullable `agent_type` column on `tool_events` | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| (B) Dedicated `agent_spawn` kind | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |

**Key evidence**:
- **(A)**: Direct precedent at `session_store.py:576-594` (v15/v16 `ALTER TABLE … ADD COLUMN` + `CREATE INDEX`); `_row_to_dataclass()` compatibility at `history_reader.py:273-277`; existing test patterns at `test_session_store.py:3079-3105` and `test_hook_post_tool_use.py:100-237`; `summarize_skills()` template at `history_reader.py:497-546` for the `agent_usage()` helper. Reuse score: 3/3.
- **(B)**: New-kind call-site cost spans `VALID_KINDS`/`_KIND_TABLE` (`session_store.py:209-236`), new `record_agent_spawn()` writer, new `_backfill_agent_spawns()`, new `AgentSpawnEvent` dataclass, new `recent_agent_spawns()` + `agent_usage()` readers, new `AgentSpawnVariant` in DES_VARIANTS, plus `analytics.capture.agent_spawns` gating expansion. Disrupts the ENH-2497+ENH-2511 batched migration plan (both issues' Scope Boundary sections require a single shared migration). Reuse score: 2/3.

## Acceptance Criteria

- Additive `agent_type` column lands on `tool_events`; `SCHEMA_VERSION` bumped;
  existing rows read back with `agent_type=NULL` (no migration breakage).
- A `Task` spawn of `codebase-locator` records a `tool_events` row with
  `agent_type="codebase-locator"`.
- Non-Task tool events keep `agent_type=NULL`.
- `history_reader.agent_usage()` returns correct per-agent counts.
- `ll-session search --fts "loop-specialist"` surfaces the spawn.
- Writes are best-effort: a malformed/absent `subagent_type` writes `NULL`, never
  raises.
- Tests cover: Task spawn populates agent_type, non-Task stays NULL, usage
  aggregation, missing-field graceful handling.

### Codebase Research Findings (Acceptance-Criteria-Specific)

_Added by `/ll:refine-issue` — concrete verification anchors:_

- **Verify migration applied**: `python -c "from pathlib import Path; from little_loops.session_store import connect; conn = connect('.ll/history.db'); print(conn.execute('PRAGMA schema_version').fetchone() if False else conn.execute('SELECT value FROM meta WHERE key=\"schema_version\"').fetchone())"` — expect the new version (19). Or use `pytest scripts/tests/test_session_store.py -k schema` after the migration entry lands.
- **Verify column exists**: `PRAGMA table_info(tool_events)` must include `agent_type` (column index 9, the highest ordinal position) with `NOT NULL=0`/`dflt_value=NULL`/`type=TEXT`. The migration's `ALTER TABLE` is the only path to that PRAGMA result; backfilled/written rows that pre-date the migration read back as `agent_type=NULL` automatically.
- **Verify live insert**: a `Task` call from a session with `analytics.enabled=true` writes a row whose `tool_name="Task"` and `agent_type` matches the dispatched `subagent_type`. Test fixture pattern: build an `LLHookEvent` with `payload={"tool_name": "Task", "tool_input": {"subagent_type": "codebase-locator", "prompt": "...", "description": "..."}, "tool_response": {}, "session_id": "synthetic", "cache_hit": 0}`, call `post_tool_use.handle(event)`, query `tool_events` by `session_id="synthetic"`, assert `agent_type == "codebase-locator"`.
- **Verify best-effort**: `post_tool_use.py:158`'s `with contextlib.suppress(Exception):` block must remain wrapped around the entire INSERT + `_index()` call. If any failure path raises, that violates EPIC-1707 — run with `SQLITE_BUSY` injected (e.g. another conn holding the lock past `busy_timeout`) and assert the `Task` callsite still completes its hook contract (exit 0).
- **Verify aggregation**: insert N=3 Task rows with `subagent_type="codebase-locator"`, M=2 with `subagent_type="Explore"`, and 1 Write row; call `history_reader.agent_usage()`; assert `[{"agent_type": "codebase-locator", "invocations": 3}, {"agent_type": "Explore", "invocations": 2}]` (order by count desc) and the Write row is excluded by the `tool_name='Task'` predicate.
- **Verify FTS**: after the `_index()` call lands at `post_tool_use.py:~179`, run `ll-session search --fts "loop-specialist" --kind tool --limit 5` against a fixture DB and assert spawn rows surface.
- **Verify nullable discipline**: a `Task` call whose `tool_input` is `{}` (no `subagent_type` key) must write `agent_type=NULL`, not raise. This is enforced by `tool_input.get("subagent_type")` returning `None` on absent keys — already idiomatic; no defensive try/except needed.
- **Verify schema-version-of-meta**: the `meta` row `('schema_version', '19')` must be written as part of the migration by `_apply_migrations()` at `session_store.py:635-639`; the migration's own INSERT/UPDATE pattern means the new column is applied in lockstep with the version bump — partial upgrades are not possible.

## Implementation Steps

1. **Migration v19.** Append a new entry to `_MIGRATIONS` in `scripts/little_loops/session_store.py` (after the v18 entry at lines 521-543). Use the v16 ENH-2462 template (`ALTER TABLE … ADD COLUMN TEXT; CREATE INDEX …`) — schema is:
   ```sql
   ALTER TABLE tool_events ADD COLUMN agent_type TEXT;
   CREATE INDEX IF NOT EXISTS idx_tool_events_agent ON tool_events(agent_type);
   ```
   Bump `SCHEMA_VERSION = 18` → `19` at `session_store.py:102`. Comment block must reference this issue's ID for grep-ability. Pre-migration rows read back with `agent_type=NULL` (no data fix required); `_apply_migrations()` (line 609) handles this automatically.

2. **Live insert site.** In `scripts/little_loops/hooks/post_tool_use.py:handle()` (lines 137-210), inside the existing `with contextlib.suppress(Exception):` block at line 158:
   - Compute `agent_type = tool_input.get("subagent_type") if tool_name == "Task" else None` (note: key is `subagent_type` in the wire format, column is `agent_type`).
   - Extend the INSERT at lines 163-167 to 9 columns: add `agent_type` after `tool_name` in the column list and a 9th `?` in `VALUES`. Add the value after `tool_name` in the tuple at lines 168-176.
   - The `contextlib.suppress(Exception)` at line 158 already covers schema-drift / missing-DB errors per EPIC-1707.

3. **Backfill path.** Update `_backfill_tool_events` at `scripts/little_loops/session_store.py:1620-1664` to also extract `args.get("subagent_type")` (after line 1648 `args = block.get("input", {})`) and pass it as the 9th `?` in the INSERT at lines 1649-1654. Without this, historical JSONL Task spawns will keep `agent_type=NULL` after the backfill runs.

4. **FTS coverage (optional but cheap).** After the live INSERT (line 178), add an `_index()` call mirroring the backfill's at line 1655, with `content=f"{tool_name} {agent_type or ''}".strip()`. This makes `ll-session search --fts "codebase-locator"` return both live and backfilled Task-spawn rows without any further consumer change. The FTS row must only be written when the row is actually inserted — match the `cursor.rowcount`-guarded pattern from `record_commit_event` at `session_store.py:1078-1087`.

5. **Read API.** In `scripts/little_loops/history_reader.py`:
   - Add `agent_usage(since: datetime | None = None, db: Path | str = DEFAULT_DB_PATH) -> list[dict[str, Any]]` (mirrors `summarize_skills`). SQL: `SELECT agent_type, COUNT(*) AS invocations FROM tool_events WHERE tool_name='Task' AND agent_type IS NOT NULL [AND ts >= ?] GROUP BY agent_type ORDER BY invocations DESC`.
   - Add `recent_tool_events(agent_type: str | None = None, limit: int = 20, db: Path | str = DEFAULT_DB_PATH) -> list[dict[str, Any]]` — return rows from `tool_events` filtered by `agent_type=` when supplied.

6. **CLI surface (optional follow-on).** In `scripts/little_loops/cli/ctx_stats.py`:
   - Extend `_aggregate_tool_events` at line 118 with a sibling `_aggregate_agent_spawns(db_path)` that runs the same GROUP BY pattern as `agent_usage` and appends a "Sub-agent usage" rendering block modelled on the existing skill_health rendering at lines 354-377.

7. **Tests.** Add to `scripts/tests/test_session_store.py` (alongside `TestSchemaV15SkillCompletionColumns` at line 3095) or in a new `scripts/tests/test_enh_2497_agent_type.py`:
   - `TestSchemaV19AgentType` — three tests mirroring `TestSchemaV15SkillCompletionColumns`: `test_tool_events_has_agent_type_column` (PRAGMA `tool_events` includes `agent_type`); `test_v18_db_upgrades_preserving_task_rows` (bootstrap at v18, INSERT a Task row, upgrade, assert `agent_type is NULL` on the pre-existing row); `test_backfill_tool_events_populates_agent_type` (write a JSONL with an assistant block carrying `input.subagent_type`, run backfill, assert `agent_type` is populated).
   - `TestTaskSpawnAgentType` — call `post_tool_use.handle` with a synthetic `LLHookEvent` whose `payload` includes `tool_name="Task"` and `tool_input={"subagent_type": "codebase-locator", "prompt": "..."}`; assert a row appears in `tool_events` with `agent_type="codebase-locator"`.
   - `TestNonTaskNullAgent` — same shape but `tool_name="Write"`; assert `agent_type` is NULL.
   - `TestAgentUsageAggregation` — insert several Task rows with varying `agent_type` (mix of `codebase-locator`, `Explore`, `loop-specialist`) plus one Write row; call `agent_usage()`; assert returned list sums correctly and the Write row is excluded.
   - `TestGracefulMissingField` — Task call with `tool_input = {}` (no `subagent_type`); assert no exception, row written with `agent_type=NULL`.

8. **Docs.** Update `docs/ARCHITECTURE.md` schema versions table (currently shows v18) to add v19 with a one-line summary of the additive migration. Update `docs/reference/API.md` `session_store`/`history_reader` sections with the new field and helpers.

### Codebase Research Findings (Implementation-Specific)

_Added by `/ll:refine-issue` — concrete references derived from direct source reading:_

- The `LLHookEvent` envelope shape (`scripts/little_loops/hooks/types.py`) carries `payload["tool_input"]` for any PostToolUse event, so accessing `tool_input["subagent_type"]` is zero-cost — no adapter or layer needs to change.
- `connect()` at `session_store.py:693` calls `ensure_db()` on every open, so the v19 migration auto-applies on first connect after deployment — no separate bootstrap step.
- `_row_to_dataclass` at `history_reader.py:252-256` uses `f.name in row.keys()` to decide whether to populate a field, so adding a `ToolEvent` dataclass with `agent_type: str | None = None` is forward-compatible with v18 DBs (where the column is absent) AND with v19 DBs (where it may be NULL on older rows).
- `_split_sql_statements` at `session_store.py:579` splits on `;`; the migration SQL must not contain `;` inside string literals. The proposed `ALTER TABLE`+`CREATE INDEX` pair has no semicolons inside literals and is safe to append verbatim.
- `result_size` is currently set to `bytes_out` at `post_tool_use.py:175` — **out of scope** for this issue, but if the implementer notices and is tempted to fix it: keep the fix in a separate issue to avoid scope creep.
- Run the suite: `python -m pytest scripts/tests/test_session_store.py scripts/tests/test_history_reader.py -v` to verify both the new migration tests and existing tests still pass.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation alongside the eight steps above:_

9. **Normalize wire-format `ll:` prefix (mandatory).** `subagent_type` arrives in two distinct shapes in the wild: bare names (`Explore`, `general-purpose`) for built-in Claude Code subagents, and `ll:`-prefixed names (`ll:codebase-locator`, `ll:codebase-analyzer`, `ll:codebase-pattern-finder`, `ll:loop-specialist`, etc.) for this plugin's custom agents (verified by Grep across `commands/*.md` and `skills/*/SKILL.md`). The 9-agent catalog at `.claude-plugin/plugin.json:21-31` uses bare names, so the implementation should strip a leading `ll:` before insertion to keep GROUP BY output consistent: `agent_type = (tool_input.get("subagent_type") or "").removeprefix("ll:") or None if tool_name == "Task" else None`. Apply the same normalization in `_backfill_tool_events` after the existing `args = block.get("input", {})` read. Without this step, `agent_usage()` returns two distinct rows for what is logically the same agent (`codebase-locator` vs `ll:codebase-locator`).

10. **Coordinate v21 batched migration with ENH-2511 (mandatory).** Per the Scope Boundary section below, ENH-2511 has `depends_on: [ENH-2497]` and will widen this same migration with `mcp_server`, `mcp_tool`, `mcp_outcome`, and `latency_ms` columns + their indexes. The migration entry added in Step 1 must be the **single shared** v21 `ALTER TABLE tool_events … ADD COLUMN` block; do not land a separate v21 entry. Both issues' indexes (`idx_tool_events_agent`, `idx_tool_events_mcp_*`) are independent `CREATE INDEX IF NOT EXISTS` statements, idempotency-safe. Before landing, read `scripts/little_loops/session_store.py` `SCHEMA_VERSION` directly to confirm the slot is still 21 (it is currently 20 as of this writing); if ENH-2511 has landed first, reconcile.

11. **CLI user-facing output (verification only).** No code change required in `scripts/little_loops/cli/session.py:466-467`. The `ll-session recent --kind tool` text-renderer iterates `row.items()` and prints `f"{k}={v}"` for non-NULL columns; the new `agent_type` column will automatically appear as `agent_type=<name>` for Task rows. Verify by `ll-session recent --kind tool --limit 5` post-implementation. Non-Task rows are unaffected (NULL values filtered out by the existing `v is not None` clause).

12. **Doc updates beyond the two in Step 8.** In addition to `docs/ARCHITECTURE.md` and `docs/reference/API.md`, update:
    - `docs/guides/HISTORY_SESSION_GUIDE.md:84` — add `agent_type` to the column-listing row for `tool_events`.
    - `docs/guides/BUILTIN_HOOKS_GUIDE.md:258` — add `agent_type (populated when tool_name=Task, NULL otherwise)` to the `post_tool_use` row description.

13. **Tests beyond the new file in Step 7.** In `scripts/tests/test_enh_2497_agent_type.py` (the suggested new file), add three additional test cases not in the issue's Tests subsection:
    - `test_live_write_filled_in_search_index` — directly closes the FTS acceptance-criterion gap from Implementation Step 4 (mandatory; without it, no test enforces the `_index()` wiring).
    - `test_tool_events_backfill_populates_agent_type` — directly closes the backfill-side gap from Implementation Step 3 (mandatory).
    - `test_readers_return_empty_on_missing_db` — closes the no-raise-on-missing-DB contract for `agent_usage()` and `recent_tool_events()`.

14. **Version renumber in test classes.** Rename the suggested `TestSchemaV19AgentType` → `TestSchemaV21AgentType` and the suggested `_bootstrap_schema_at(db, 19)` → `_bootstrap_schema_at(db, 20)` calls because `SCHEMA_VERSION = 20` today at `session_store.py:207`. Bootstrap must occur at the version immediately preceding the new migration's slot; a v19 bootstrap skips the v21 entry and the test would falsely pass on a non-migrated DB.

## Sources

- `thoughts/history-db-expand-wiring.md` — §2 (tool-event granularity)
- EPIC-2457 review (2026-07-05) — item #7
- `scripts/little_loops/hooks/post_tool_use.py` — tool_events write-point
- ENH-2460 — sibling success-signal work (skills); this is its agent analog
- `agents/*.md` — the agent catalog whose usage this makes observable
- `reference_dispatch_table_usage_banner` (memory) — hook intent list to update

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader`, hooks |

## Status

**Open** | Created: 2026-07-05 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): **ENH-2511** (MCP tool-call
telemetry) explicitly plans to widen this issue's same `tool_events` v19
migration in a single batch. Verified against current code
(`scripts/little_loops/session_store.py`): `SCHEMA_VERSION` is now **20**
(v17=`commit_events`/ENH-2458 done, v18=`test_run_events`/ENH-2459 done,
v19=`raw_events`/ENH-2581 done, v20=`usage_events`/ENH-2461 done) — this
issue's "bump 18→19" Integration Map text is stale; the actual next-available
slot at implementation time should be read from `SCHEMA_VERSION` directly
rather than assumed. ENH-2511 has been given `depends_on: [ENH-2497]` so this
issue lands first and ENH-2511's `mcp_server`/`mcp_tool`/`mcp_outcome`/
`latency_ms` columns are added to the same migration block this issue creates
(one shared `ALTER TABLE tool_events` batch), not a second competing one.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): **ENH-2505** (subagent
session-tree) also persists `agent_type` for each spawn, in its new
`subagent_runs` table. The authoritative source for the spawn-event
discriminator is `tool_events.agent_type` (this issue); ENH-2505's
`subagent_runs.agent_type` is a query-side denormalization populated from
the same normalized value at write time, not an independent second source.
ENH-2505 already declares `depends_on: [ENH-2497]` in its frontmatter — this
note records that contract.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): **ENH-2506** (hook execution
telemetry) wraps the same `post_tool_use.py` handler. The two issues operate
at distinct nesting levels: this issue's `tool_events` insert (with the new
`agent_type` column) and `_index()` live-write remain the **inner** operation,
already best-effort-wrapped in `contextlib.suppress(Exception)` at
`post_tool_use.py:158`. ENH-2506's `hook_event_context` is the **outer,
independently-failing** write — it MUST NOT alter, roll back, or wrap
`tool_events` persistence. A telemetry failure must never suppress an
agent-spawn write, and vice versa.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-17T18:48:49 - `ff04da3c-210f-4c14-9967-762b390ae67c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-17T13:59:18 - `ff04da3c-210f-4c14-9967-762b390ae67c.jsonl`
- `/ll:wire-issue` - 2026-07-16T23:53:35 - `116f385e-2818-4c79-8ce3-a15f63040329.jsonl`
- `/ll:decide-issue` - 2026-07-16T19:35:50 - `c62633a6-bc8a-42d5-88d1-7b034101e282.jsonl`
- `/ll:refine-issue` - 2026-07-16T15:36:00 - `5d02fdfe-927a-4f1f-aa0e-5f159a6cee91.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-14T00:22:08 - `33e15d2a-429d-48f8-8998-aca5080acdd5.jsonl`
- `/ll:refine-issue` - 2026-07-07T01:16:27 - `84c84b8b-bd4f-4743-8789-7aa8fa03818a.jsonl`
- audit - 2026-07-06 - Corrected agent count: `agents/*.md` contains 9 agent definitions, not ~15.
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
