---
id: ENH-2723
type: ENH
title: "usage_events run_id column \u2014 schema migration (v29)"
priority: P2
status: done
captured_at: '2026-07-21T18:30:00Z'
completed_at: '2026-07-21T18:56:52Z'
discovered_date: '2026-07-21'
discovered_by: issue-size-review
parent: EPIC-2456
labels:
- token-cost
- observability
- history-db
- schema
relates_to:
- EPIC-2456
- ENH-2721
- ENH-2712
decision_needed: false
spike_needed: false
confidence_score: 95
outcome_confidence: 95
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 23
---

# ENH-2723: `usage_events` `run_id` column — schema migration (v29)

## Summary

Add a `run_id` column to `usage_events` via schema migration v29, following the v21 `ALTER TABLE ... ADD COLUMN` precedent (not the v26-v28 `CREATE TABLE` shape). This is the schema-only slice of ENH-2721, decomposed so the live writer (ENH-2724) and backfill extension (ENH-2725) can build on a landed column rather than bundling everything into one Very-Large issue.

## Current Behavior

`usage_events` (`session_store.py` v20 migration, ~line 739) has no `run_id` column, and `loop_runs` (v23 migration, ~line 799) has no `session_id` column. There is no exact join key between the two tables at the current schema version (28).

## Expected Behavior

`usage_events` schema is at v29 with a nullable, additive `run_id TEXT` column and a companion `idx_usage_events_run_id` index, following the v21 `ALTER TABLE` precedent. No existing consumer behavior changes — the column is unpopulated until the live writer (ENH-2724) and backfill (ENH-2725) land.

## Parent Issue

Decomposed from ENH-2721: `usage_events` `run_id` column + live per-invocation writer (split from ENH-2712)

## Motivation

`usage_events` (`session_store.py` v20 migration, ~line 739) has no `run_id` column and `loop_runs` (v23 migration, ~line 799) has no `session_id`, so there is no exact join key between the two tables today. This issue adds the column only; the write path is out of scope here (see ENH-2724/ENH-2725).

## Implementation Steps

1. Add schema migration **v29**: `run_id` column on `usage_events` via plain `ALTER TABLE ... ADD COLUMN`, following the v21 precedent at `session_store.py:754-764` (which added `invocation_id`/`provider_vendor` as forward-compat NULL columns to this same table) — not the v26-v28 `CREATE TABLE` shape.
2. Add `CREATE INDEX IF NOT EXISTS idx_usage_events_run_id ON usage_events(run_id);` (already proven in the ENH-2712 spike's `_SCHEMA` constant).
3. Bump `SCHEMA_VERSION` from 28 to 29; add it to the `_MIGRATIONS` list.
4. Add `"run_id"` to `TestSchemaV20UsageEvents.test_usage_events_columns`'s expected exact-set (`test_session_store.py:3287`).
5. Add a new `TestSchemaV29` class (template: `TestSchemaV28` at `test_session_store.py:4999`).
6. Bump the 13 hardcoded `SCHEMA_VERSION == 28` literal assertions to 29: 12 in `test_session_store.py` (lines 1380, 1825, 1826, 1995, 1996, 2047, 2048, 2143, 2144, 3724, 3725, 3765, 3766, 4513, 4659, 4880, 4985, 5025) + 1 in `test_assistant_messages.py:88`. Tests that compare against the imported `SCHEMA_VERSION` symbol (`test_enh_2511_mcp_telemetry.py`, `test_enh_2497_agent_type.py`, `test_queue_store.py`) need no edit.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 6's count is understated — verified by direct grep, not just the listed lines.** `grep -c "== 28\b" scripts/tests/test_session_store.py` returns **20**, not 12. The listed 18 line numbers omit two literal `assert int(version[0]) == 28` sites at **line 2126** (`TestSessionEndSummaryCompaction`-area upgrade test) and **line 3820** (an `issue_snapshots`-area upgrade test) — both compare a raw `int(...)` against the literal `28` the same way lines 1826/1996/2048/2144/3725/3766 do, and both need bumping to 29. Combined with `test_assistant_messages.py:88`, the true total is **21 literal sites**, not 13. Re-run `grep -n "== 28\b" scripts/tests/test_session_store.py scripts/tests/test_assistant_messages.py` at implementation time and bump every hit rather than trusting the fixed line list above (line numbers shift if any edit lands first).
- **Spike anchor for the "already proven" index claim** (Step 2): the exact `_SCHEMA` constant is at `scripts/tests/spike/usage_events_run_id_writer/writer.py:16-31`, with the index statement at line 30 (`CREATE INDEX IF NOT EXISTS idx_usage_events_run_id ON usage_events(run_id);`). The spike's `test_writer.py` (5 tests, `TestUsageEventsRunIdWriter`) already proves single-run stamping and concurrency safety — none of that needs re-proving here since this issue is schema-only.
- **A closer shape precedent than v21 alone**: v21 (`session_store.py:754-764`) adds columns but no index. v24 (`session_store.py:818-`, ENH-2497, `agent_type` on `tool_events`) adds a single nullable column *plus a companion index in the same migration block* — the closer template for v29 since this issue also adds `idx_usage_events_run_id` alongside the column.
- **Architecture precedent worth citing in the migration comment**: `.ll/decisions.yaml` `ARCHITECTURE-145` (ENH-2461) already established that `usage_events` is deliberately an independent table joined on `session_id`/`ts`, not FK-linked to other tables ("Option A/B (FK to tool_events.id) — contradicts independent-parser rebuild() architecture"). `run_id` as a plain nullable `TEXT` column (no FK constraint, join done at the application/query level) is consistent with that precedent — worth a one-line callout in the v29 comment block so a future reader doesn't mistake the new column for a policy reversal.
- **Downstream consumers confirmed unaffected** (supports the "no behavior change" acceptance criterion): `_backfill_usage_events`'s `INSERT INTO usage_events(...)` (`session_store.py:2686-2688`), `history_reader.py`'s `recent_usage_events` (:948-952) and `cost_attribution` (:893-902), and `cli/ctx_stats.py`'s `_aggregate_usage_events` (:226-230) all use explicit column lists that omit `run_id` — they remain valid unmodified and the column defaults to `NULL` on rows they write/read. Note for the ENH-2724/2725 follow-ons: `cost_attribution`'s `_COST_ATTR_GROUP_COLUMNS` whitelist (`history_reader.py:843-851`) does not include `run_id` — a natural extension point once the write path lands, not needed for this schema-only slice.

### Wiring Phase (added by `/ll:wire-issue`)

_These documentation touchpoints were identified by wiring analysis and must be included in the implementation — they hardcode the current schema version (28) and were not caught by the grep-based Step 6, which only scans `scripts/tests/`:_

7. Update `docs/reference/API.md:7765,7769` — bump the "Current schema version: **28**" prose and `# 28` inline comment to 29.
8. Update `docs/ARCHITECTURE.md:686` — append a `| v29 |` row to the `history.db schema versions` table.
9. Update `docs/guides/HISTORY_SESSION_GUIDE.md:77-78,85` — append a `| v29 | ENH-2723 | ... |` row to the schema-versions table.

_Confirmed no action needed (reported for completeness, not gaps):_ `ll-verify-kinds`'s `_all_migration_tables()` only regex-matches `CREATE TABLE` statements — an `ALTER TABLE` is invisible to it, so `usage_events` (already registered from its v20 `CREATE TABLE`) needs no re-registration. `config-schema.json` and `.ll/ll-config.json` have no schema-version-mirroring keys. Downstream consumers (`history_reader.py`, `cli/ctx_stats.py`, `test_history_reader.py`, `test_usage_journal.py`) use explicit named-column INSERTs that omit `run_id` and remain valid unmodified since the column is nullable and additive.

## Scope Boundaries

- **Out of scope**: the live per-invocation writer that populates `run_id` on new rows — that is ENH-2724.
- **Out of scope**: backfilling `run_id` on historical rows via `_backfill_usage_events()` — that is ENH-2725.
- **In scope**: the v29 migration itself, the index, and the cascading test-version bumps this migration triggers.

## Acceptance Criteria

- [x] `usage_events` schema is v29 with a `run_id` column (nullable, additive).
- [x] `idx_usage_events_run_id` index exists.
- [x] `TestSchemaV29` passes; `TestSchemaV20UsageEvents.test_usage_events_columns` includes `"run_id"`.
- [x] All 13 hardcoded `SCHEMA_VERSION == 28` assertions are bumped to 29; full suite (`python -m pytest scripts/tests/`) passes.
- [x] No behavior change to existing `usage_events` consumers — additive column only, no writer wired yet.

## Resolution

Added schema migration v29 (`session_store.py`): plain `ALTER TABLE usage_events
ADD COLUMN run_id TEXT` plus `idx_usage_events_run_id` index, following the v21
`ALTER TABLE` precedent and the v24 column+index pairing shape. Bumped
`SCHEMA_VERSION` 28→29 and all 21 hardcoded `== 28` literal assertions (20 in
`test_session_store.py`, 1 in `test_assistant_messages.py` — the true count per
the refine-issue grep, not the stale 13-count in the original Implementation
Steps). Added `"run_id"` to `TestSchemaV20UsageEvents.test_usage_events_columns`
and a new `TestSchemaV29` class (column exists, index exists, v28→v29 upgrade
gains the column). Updated the three hardcoded schema-version doc touchpoints
(`docs/reference/API.md`, `docs/ARCHITECTURE.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`).
Full suite: 15727 passed, 38 skipped. `ruff check` and `mypy` clean.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — v29 migration (`ALTER TABLE`), `_MIGRATIONS` list, `SCHEMA_VERSION` bump
- `scripts/tests/test_session_store.py` — new `TestSchemaV29`, updated `TestSchemaV20UsageEvents`, 12 literal version-bump sites
- `scripts/tests/test_assistant_messages.py:88` — literal version-bump site

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:7765,7769` — "Current schema version: **28**" prose and the `SCHEMA_VERSION,        # 28` inline comment in the `session_store` API doc section both hardcode 28; bump both to 29. [Agent 2 finding, confirmed by direct grep]
- `docs/ARCHITECTURE.md:686` — the `history.db schema versions` table ends at the `| v28 | subagent_runs | ... |` row; append a `| v29 | usage_events.run_id, idx_usage_events_run_id | ... |` row following the same format. [Agent 2 finding, confirmed]
- `docs/guides/HISTORY_SESSION_GUIDE.md:77-78,85` — the schema-versions table (`| Version | Issue | Description |`) has rows through v28 (line 85); add a `| v29 | ENH-2723 | run_id column on usage_events |` row. The `usage_events` row in the "What Gets Recorded" table (line 108) already ends its column list before `run_id` — leave it as-is per this issue's schema-only scope (no consumer wiring yet); ENH-2724 should update it once the column is actually populated. [Agent 2 finding, confirmed]

### Similar Patterns
- `session_store.py:754-764` (v21 migration) — the closest precedent: a plain `ALTER TABLE ... ADD COLUMN` adding forward-compat NULL columns to `usage_events` itself.
- `session_store.py:818-` (v24 migration, ENH-2497) — closer shape match for *this* issue: adds one nullable column *and* a companion index in the same migration block (`agent_type` on `tool_events`), mirroring the column+index pairing v29 needs.
- `scripts/tests/spike/usage_events_run_id_writer/writer.py:16-31` — the ENH-2712 spike's `_SCHEMA` constant, already proving the exact `run_id TEXT` column + `idx_usage_events_run_id` index shape referenced in Implementation Step 2.
- `scripts/tests/test_session_store.py:4999-5041` (`TestSchemaV28`) — template for the new `TestSchemaV29` class: exact-column-set assertion via `PRAGMA table_info`, `SCHEMA_VERSION` assertion, and an upgrade-from-prior-version idempotency check via `_bootstrap_schema_at(db, 28)` → `ensure_db(db)`.

## Impact

- **Priority**: P2 — blocks ENH-2724 and ENH-2725.
- **Effort**: Small — mechanical migration plus test-version bumps; no behavioral logic.
- **Risk**: Low — additive column, no writer wired, no consumer behavior change.

## Status

**Open** | Created: 2026-07-21 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-07-21T18:56:13 - `78c13d86-47e6-42a5-b174-383345255a90.jsonl`
- `/ll:ready-issue` - 2026-07-21T18:45:01 - `523a6b9d-7fce-4d77-b269-c4487d06d459.jsonl`
- `/ll:confidence-check` - 2026-07-21T18:43:08 - `2ce38ef4-9894-4a9d-b226-0c4a107caa1c.jsonl`
- `/ll:wire-issue` - 2026-07-21T18:40:35 - `cafd8b39-40a7-4462-a49e-5beb9611b920.jsonl`
- `/ll:refine-issue` - 2026-07-21T18:33:29 - `e38bd820-d68f-417c-9cac-2fd6bb1b2e4f.jsonl`
- `/ll:issue-size-review` - 2026-07-21T18:30:00 - `1d8fe38e-085a-4ee8-8c6c-5d16d9fd18d7.jsonl`
