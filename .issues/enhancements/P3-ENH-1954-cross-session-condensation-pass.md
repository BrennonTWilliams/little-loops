---
id: ENH-1954
title: Cross-session condensation pass with config gating
type: ENH
priority: P3
status: open
parent: ENH-1927
relates_to:
- FEAT-1712
- ENH-1953
labels:
- enhancement
- history
- session-store
- condensation
---

# ENH-1954: Cross-session condensation pass with config gating

## Summary

Add the recursive cross-session condensation pass to `_compact_sessions()` that rolls up per-session condensed nodes into higher-order nodes, terminating at a single project-root summary. Includes config gating, serialization, and schema validation for new `CompactionConfig` fields.

## Parent Issue

Decomposed from ENH-1927: Recursive cross-session condensation for a project-root summary

## Dependencies

- **ENH-1953** must be completed first (schema v12 with `level` column must exist before condensation can set it).

## Scope

This child covers the cross-session condensation algorithm itself and the configuration surface that gates it. It depends on the schema foundation from ENH-1953 but does NOT include the N-level DAG traversal reader changes (those are in ENH-1955).

## Implementation Steps

### 1. Cross-session condensation pass in `_compact_sessions()`

`session_store.py:1418` — After the per-session `for` loop:

1. Query all existing condensed nodes: `SELECT id, content, tokens FROM summary_nodes WHERE kind='condensed'`
2. Group by token budget using the greedy algorithm from `_compact_session_conn():1331-1347` (Pattern 1)
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

## Tests

- Add `test_cross_session_condensation_produces_root()` to `TestCompactSession` in `test_session_store.py:1683`: seed ≥2 sessions, compact each, run cross-session pass, assert exactly one root node exists with `session_id IS NULL` and `level = max`.
- Add `test_cross_session_condensation_idempotent()`: run the cross-session pass twice on the same DB, assert no duplicate root/higher-order nodes.
- Add `test_cross_session_condensation_parent_id_links_existing()`: re-run condensation on already-compacted sessions, assert existing condensed nodes' `parent_id` is correctly set.

## Files to Modify

- `scripts/little_loops/session_store.py:1400-1426` — `_compact_sessions()` (add cross-session pass)
- `scripts/little_loops/config/features.py:722` — `CompactionConfig` (add `cross_session_enabled`, `max_level`)
- `scripts/little_loops/config/core.py:664` — `ConfigDefaults.to_dict()` (serialize new fields)
- `config-schema.json:1507` — `history.compaction` schema (add property declarations)
- `scripts/tests/test_session_store.py:1683` — add condensation tests
- `scripts/tests/test_config.py:2770` — add config field assertions
- `scripts/tests/test_config_schema.py:304` — add schema property assertions

## Acceptance Criteria

- After `backfill()` with compaction enabled on a project with ≥2 sessions, exactly one project-root summary node exists (`session_id IS NULL`, `level = max`)
- Re-running compaction is idempotent (no duplicate root/higher-order nodes, no orphan condensed nodes)
- Existing per-session condensed nodes' `parent_id` is correctly set on re-run
- `cross_session_enabled: false` disables the cross-session pass entirely
- Config round-trips through `to_dict()` without dropping new fields

## Session Log
- `/ll:issue-size-review` - 2026-06-04T19:28:00Z - `8b66735f-5337-46b3-ba3c-44648e5faca2.jsonl`
