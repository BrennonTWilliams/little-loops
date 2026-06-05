---
id: ENH-1954
title: Cross-session condensation pass with config gating
type: ENH
priority: P3
status: done
completed_at: 2026-06-05 01:41:44+00:00
parent: ENH-1927
relates_to:
- FEAT-1712
- ENH-1953
labels:
- enhancement
- history
- session-store
- condensation
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1954: Cross-session condensation pass with config gating

## Summary

Add the recursive cross-session condensation pass to `_compact_sessions()` that rolls up per-session condensed nodes into higher-order nodes, terminating at a single project-root summary. Includes config gating, serialization, and schema validation for new `CompactionConfig` fields.

## Current Behavior

Sessions are compacted independently by `_compact_session_conn()` — each session produces its own leaf and condensed `summary_nodes` scoped to that session. There is no cross-session rollup: running compaction on N sessions produces N isolated summary DAGs. The `_compact_sessions()` loop at `session_store.py:1416` iterates over sessions, calls `_compact_session_conn()` for each, and returns a leaf count — no higher-order condensation step exists.

## Expected Behavior

After `backfill()` with `history.compaction.enabled: true` on a project with ≥2 sessions:

1. Per-session leaf/condensed nodes are created as before
2. A cross-session pass groups existing condensed nodes by token budget, summarizes each group, and inserts higher-order condensed nodes (`session_id=NULL`, `level=1+`)  
3. Recursion continues level-by-level until exactly one project-root summary node remains (`session_id IS NULL`, `level = max`)
4. Re-running compaction is idempotent — no duplicate nodes, no orphan condensed nodes
5. `cross_session_enabled: false` disables the cross-session pass entirely, preserving current behavior
6. New `CompactionConfig` fields (`cross_session_enabled`, `max_level`) survive round-trip through `to_dict()` and are declared in `config-schema.json`

## Impact

- **Priority**: P3 — Medium priority; enables project-level session comprehension but depends on opt-in compaction which is already gated. Not a blocker for other work.
- **Effort**: Medium — Algorithm is straightforward (BFS-level grouping + summarization following existing patterns) but touches 5+ files across config, schema, tests, and docs.
- **Risk**: Low — Feature is gated behind `cross_session_enabled` (default `true`), so existing compaction-only users get the new behavior transparently. Users who want the old behavior can disable it. No schema migration needed (ENH-1953 already added the `level` column).
- **Breaking Change**: No — New fields have defaults that preserve existing behavior semantics.

## Parent Issue

Decomposed from ENH-1927: Recursive cross-session condensation for a project-root summary

## Dependencies

- **ENH-1953** must be completed first (schema v12 with `level` column must exist before condensation can set it).

## Scope

This child covers the cross-session condensation algorithm itself and the configuration surface that gates it. It depends on the schema foundation from ENH-1953 but does NOT include the N-level DAG traversal reader changes (those are in ENH-1955).

## Implementation Steps

### 1. Cross-session condensation pass in `_compact_sessions()`

`session_store.py:1416` — After the per-session `for` loop:

1. Query all existing condensed nodes: `SELECT id, content, tokens FROM summary_nodes WHERE kind='condensed'`
2. Group by token budget using the greedy algorithm from `_compact_session_conn():1347-1363` (Pattern 1)
3. Call `_summarize_block()` on each group (Pattern 2) to produce higher-order summaries
4. INSERT with `INSERT OR IGNORE`, `kind='condensed'`, `session_id=NULL`, `level=N`
5. UPDATE lower-level condensed nodes' `parent_id` (Pattern 17); handle the edge case where existing condensed nodes' `parent_id` was never set (re-runs must also link already-compacted sessions — see codebase research findings in parent issue)
6. Recurse: re-query higher-order condensed nodes, repeat until one root remains

**Critical edge case**: The `parent_id` UPDATE in `_compact_session_conn()` only runs when `cursor.rowcount > 0` (a new condensed node was created). If compaction is re-run on an already-compacted session, `INSERT OR IGNORE` returns `rowcount=0`, so existing condensed nodes' `parent_id` is never updated. The cross-session pass must explicitly UPDATE `parent_id` on existing condensed nodes.

### 2. Config gating

`scripts/little_loops/config/features.py:722` — Add optional fields to `CompactionConfig`:
- `cross_session_enabled: bool = True` — feature flag
- `max_level: int | None = None` — optional depth limit (None = terminate at single root)

### 3. Config serialization

`scripts/little_loops/config/core.py:664` — Update `ConfigDefaults.to_dict()` to serialize the new `CompactionConfig` fields (`cross_session_enabled`, `max_level`). Without this, new config values are silently dropped from `BRConfig.to_dict()` output.

### 4. Schema validation

`config-schema.json:1507-1533` — The `history.compaction` object has `additionalProperties: false`. Adding `cross_session_enabled`/`max_level` requires explicit property declarations in the schema. Add `cross_session_enabled` (boolean) and `max_level` (integer, nullable) to `properties`.

### 5. Config tests

- `scripts/tests/test_config.py:2770` — Add assertions for `cross_session_enabled` and `max_level` defaults in `test_compaction_defaults` and `test_compaction_override`. Update `test_history_to_dict_round_trip` for new dict keys.
- `scripts/tests/test_config_schema.py:304` — Update `test_history_compaction_in_schema` for new property types.

### 6. Documentation updates (added by `/ll:wire-issue`)

_Wiring pass added by `/ll:wire-issue`:_
- Update `docs/reference/CONFIGURATION.md:1150` — add `cross_session_enabled` (boolean, default `true`) and `max_level` (integer\|null, default `null`) to the `history.compaction` config key table and example JSON; extend prose description to cover cross-session recursive condensation [Agent 2 finding]
- Update `docs/ARCHITECTURE.md:636` — extend Components table entry for `compact_session()` to describe cross-session condensation producing a multi-level DAG [Agent 2 finding]
- Extend `scripts/tests/test_config.py:2858` — add assertions for `cross_session_enabled` and `max_level` to `test_history_round_trip_from_dict` [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Cross-session dedup index edge case**: The v12 dedup index `idx_summary_nodes_cross_dedup` keys on `(level, ts_start, ts_end)`, but per-session condensed nodes have `ts_start=NULL, ts_end=NULL`. If cross-session higher-order condensed nodes also have `ts_start=NULL, ts_end=NULL`, then at each level, ALL condensed nodes collide on `(level, NULL, NULL)`, and `INSERT OR IGNORE` will silently keep only the first one inserted. **The cross-session pass must populate `ts_start`/`ts_end` on higher-order nodes** (e.g., `MIN(children.ts_start)`, `MAX(children.ts_end)`) or the dedup index must be redesigned. Update implementation step 1 item 4 to note this.

- **`backfill_incremental()` gap**: `backfill_incremental()` at `session_store.py:1564` never calls `_compact_sessions()`. If users rely on incremental backfill (as the `session_start` hook does), compaction — including the cross-session pass — will never run. This is not in scope for ENH-1954 but may need a follow-up issue for hook integration.

- **Recursive pattern**: The codebase uses BFS-style `deque` iteration (not stack recursion) for graph traversal. `_find_reachable_states()` at `fsm/validation.py:1484` is the closest analogue — iterate while frontier non-empty, track visited, process each level. The cross-session pass should follow this pattern: `while` loop querying condensed nodes at current level, grouping, summarizing, inserting at `level+1`, repeating until ≤1 node at the new level (the project root).

- **Test convention for idempotency**: `test_compact_session_idempotent()` at `test_session_store.py:1757` asserts `len(condensed_rows) <= 1` (not `== 1`) because `INSERT OR IGNORE` silently skips on re-run. Cross-session idempotency tests should use the same `<=` convention.

- **`additionalProperties: false` constraint**: The `history.compaction` schema object at `config-schema.json:1532` has `additionalProperties: false`. Any new `CompactionConfig` fields (`cross_session_enabled`, `max_level`) MUST be declared in the schema or valid config files will fail validation. Similarly, the `history` object at line 1535 also has `additionalProperties: false`, but `compaction` is already declared — only changes within `compaction.properties` are needed.

- **ENH-1955 integration point**: `history_reader.py:628-749` (`ll_expand`, `ll_grep`) currently walks at most two hops (leaf → condensed). ENH-1955 will extend this to N levels using the `level` column. The cross-session condensation pass creates the N-level DAG that ENH-1955 will traverse. No reader changes are needed in ENH-1954 — it only writes the hierarchy.

## Tests

- Add `test_cross_session_condensation_produces_root()` to `TestCompactSession` in `test_session_store.py:1716`: seed ≥2 sessions, compact each, run cross-session pass, assert exactly one root node exists with `session_id IS NULL` and `level = max`.
- Add `test_cross_session_condensation_idempotent()`: run the cross-session pass twice on the same DB, assert no duplicate root/higher-order nodes.
- Add `test_cross_session_condensation_parent_id_links_existing()`: re-run condensation on already-compacted sessions, assert existing condensed nodes' `parent_id` is correctly set.

## Files to Modify

- `scripts/little_loops/session_store.py:1416-1443` — `_compact_sessions()` (add cross-session pass)
- `scripts/little_loops/config/features.py:722` — `CompactionConfig` (add `cross_session_enabled`, `max_level`)
- `scripts/little_loops/config/core.py:664` — `ConfigDefaults.to_dict()` (serialize new fields)
- `config-schema.json:1507` — `history.compaction` schema (add property declarations)
- `scripts/tests/test_session_store.py:1716` — add condensation tests
- `scripts/tests/test_config.py:2770` — add config field assertions
- `scripts/tests/test_config_schema.py:304` — add schema property assertions

## Integration Map

### Callers (consume compaction)
- `scripts/little_loops/session_store.py:1557` — `backfill()` calls `_compact_sessions(conn, config)` as final step before `conn.commit()`
- `scripts/little_loops/session_store.py:1445` — `compact_session()` public entry for single-session compaction (does NOT trigger cross-session pass)
- `scripts/tests/test_session_store.py:1858` — `test_backfill_with_compaction_enabled` passes explicit config with `enabled: True`
- `scripts/little_loops/session_store.py:1564` — `backfill_incremental()` does NOT call `_compact_sessions()`; compaction only triggers on full `backfill()`
- `scripts/little_loops/cli/session.py:319` — `ll-session backfill` CLI calls `backfill()` without config, so compaction defaults to disabled

### Test Patterns to Follow
- `scripts/tests/test_session_store.py:1757` — `test_compact_session_idempotent()`: run twice, assert no duplicates (model for cross-session idempotency test)
- `scripts/tests/test_config.py:2770` — `test_compaction_defaults()`: assert new fields have correct defaults
- `scripts/tests/test_config.py:2778` — `test_compaction_override()`: assert new fields can be overridden
- `scripts/tests/test_config.py:2831` — `test_history_to_dict_round_trip()`: assert new fields survive round-trip through `to_dict()`
- `scripts/tests/test_config_schema.py:304` — `test_history_compaction_in_schema()`: assert new properties declared with correct types/defaults
- `scripts/tests/test_config.py:2858` — `test_history_round_trip_from_dict()`: does a `from_dict(to_dict())` round-trip via `HistoryConfig`; new fields silently pass through but explicit assertions are recommended for completeness [Agent 3 finding]

### Algorithm Patterns to Follow
- `scripts/little_loops/fsm/validation.py:1484` — `_find_reachable_states()`: BFS with `deque` frontier, `reachable` set, iterates until exhaustion (model for level-by-level condensation loop)
- `scripts/little_loops/session_store.py:1347-1363` — greedy block accumulation algorithm (reuse verbatim for grouping condensed nodes by token budget)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:1150` — `history.compaction` section documents the 4 current config keys with a TODO stub; must add `cross_session_enabled` (boolean, default `true`) and `max_level` (integer|null, default `null`) to the config key table and example JSON block, and extend prose description to cover the cross-session recursive condensation pass [Agent 2 finding]
- `docs/ARCHITECTURE.md:636` — Components table entry for `compact_session()` describes only per-session LCM-style compaction; should be extended to reflect that `_compact_sessions()` now also performs recursive cross-session condensation producing a multi-level DAG of condensed nodes [Agent 2 finding]

### Schema State (post ENH-1953)
- `scripts/little_loops/session_store.py:368` — v12 migration: `ALTER TABLE summary_nodes ADD COLUMN level INTEGER DEFAULT 0`
- `scripts/little_loops/session_store.py:370-372` — cross-session dedup index: `CREATE UNIQUE INDEX idx_summary_nodes_cross_dedup ON summary_nodes(level, ts_start, ts_end) WHERE kind='condensed' AND session_id IS NULL`
- `scripts/little_loops/history_reader.py:108` — `SummaryNode` dataclass includes `level: int = 0` field
- `scripts/little_loops/history_reader.py:628-749` — `ll_expand()` and `ll_grep()` two-hop condensed-node traversal (currently level-0 only; ENH-1955 extends to N-level)

## Acceptance Criteria

- After `backfill()` with compaction enabled on a project with ≥2 sessions, exactly one project-root summary node exists (`session_id IS NULL`, `level = max`)
- Re-running compaction is idempotent (no duplicate root/higher-order nodes, no orphan condensed nodes)
- Existing per-session condensed nodes' `parent_id` is correctly set on re-run
- `cross_session_enabled: false` disables the cross-session pass entirely
- Config round-trips through `to_dict()` without dropping new fields

## Resolution

Implemented cross-session recursive condensation pass in `_compact_sessions()` with config gating, schema validation, and full test coverage (TDD: red → green). All acceptance criteria met:

- After `backfill()` with compaction enabled on ≥2 sessions, exactly one project-root summary node exists (`session_id IS NULL`, `level = max`)
- Re-running compaction is idempotent (no duplicate root/higher-order nodes)
- Existing per-session condensed nodes' `parent_id` is correctly set on re-run
- `cross_session_enabled: false` disables the cross-session pass entirely (preserving pre-ENH-1954 behavior)
- Config round-trips through `to_dict()` without dropping new fields
- `max_level` depth cap supported (`null` = unlimited, integer = stop after N levels)

### Files Modified
- `scripts/little_loops/session_store.py:1416-1520` — `_compact_sessions()`: added 100-line cross-session condensation loop after per-session pass
- `scripts/little_loops/config/features.py:722-748` — `CompactionConfig`: added `cross_session_enabled: bool = True`, `max_level: int | None = None`
- `scripts/little_loops/config/core.py:664-671` — `ConfigDefaults.to_dict()`: serialise new fields
- `config-schema.json:1507-1545` — schema: declared `cross_session_enabled` (boolean, default true) and `max_level` (integer|null, default null)
- `scripts/tests/test_session_store.py:1924-2066` — 4 new cross-session tests (produces root, idempotent, parent links, disabled gate)
- `scripts/tests/test_config.py:2770-2792` — updated compaction defaults/override assertions
- `scripts/tests/test_config_schema.py:304-328` — updated schema property assertions
- `docs/reference/CONFIGURATION.md:1150-1193` — replaced TODO stub with full documentation of new keys
- `docs/ARCHITECTURE.md:636` — updated Components table entry for cross-session condensation

### Design Decisions
- **BFS-level iteration**: Used `while` loop with `level` counter (not recursive function) following the `_find_reachable_states()` pattern at `fsm/validation.py:1484`. Simpler, no stack limit, natural depth tracking.
- **ts_start/ts_end computation**: For level-1 nodes, queries leaf descendants through `session_id` to get real timestamps (per-session condensed nodes have `ts_start=NULL`). For level-2+, reads timestamps directly from member nodes (they were set at level 1). This ensures the v12 dedup index `idx_summary_nodes_cross_dedup` works correctly — SQLite treats NULLs as distinct in unique indexes, so non-NULL timestamps are required for effective dedup.
- **parent_id edge case**: The UPDATE runs unconditionally on `parent_id IS NULL` members regardless of whether the INSERT created a new node or found an existing one (idempotent re-run). On re-run, new members get linked to the existing parent; already-linked members are left unchanged.
- **Greedy grouping reuse**: The same greedy block accumulation algorithm from `_compact_session_conn():1347-1363` is used verbatim for grouping condensed nodes by token budget, maintaining consistency.

## Session Log
- `/ll:manage-issue` - 2026-06-05T01:41:44Z - implementation and verification session
- `/ll:ready-issue` - 2026-06-05T01:30:00 - `ed1c364e-7bc3-4b8b-bd7a-45a9006d88bd.jsonl`
- `/ll:wire-issue` - 2026-06-05T01:20:37 - `801fdfff-9112-4c51-a008-cdddcd62c977.jsonl`
- `/ll:refine-issue` - 2026-06-05T01:12:13 - `df7102cc-f7bc-47e4-a67f-cacbe6b536dc.jsonl`
- `/ll:issue-size-review` - 2026-06-04T19:28:00Z - `8b66735f-5337-46b3-ba3c-44648e5faca2.jsonl`
- `/ll:confidence-check` - 2026-06-04T20:00:00Z - `4949904b-0efc-4aaa-85c2-5bb743e1ecba.jsonl`
