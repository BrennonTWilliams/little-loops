---
id: ENH-1927
title: Recursive cross-session condensation for a project-root summary
type: ENH
priority: P3
status: done
captured_at: '2026-06-04T04:15:05Z'
discovered_date: '2026-06-04'
discovered_by: capture-issue
parent: EPIC-1707
relates_to:
- FEAT-1712
- BUG-1926
labels:
- enhancement
- history
- session-store
- context-management
- captured
decision_needed: false
confidence_score: 100
outcome_confidence: 74
size: Very Large
score_complexity: 13
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-1927: Recursive cross-session condensation for a project-root summary

## Motivation

FEAT-1712 condenses each session into at most **one** `condensed` node — there is no apex unifying sessions and no re-condensation of condensed nodes. At month scale this yields N orphan condensed nodes (one per session) with no parent, so the feature's stated motivation ("month-scale project history navigation without context saturation") and Use Case ("traverse the summary DAG from the project root summary downward") are not structurally delivered: **the project-root summary node does not exist.**

The LCM paper's DAG is "high-fanout" with condensed summaries defined as "a higher-order summary of multiple existing summaries, enabling the DAG structure" — and explicitly retrievable "regardless of how many rounds of compaction have occurred." Our implementation stops at a fixed two levels per session, which is a forest, not a multi-resolution DAG.

This enhancement depends on [[BUG-1926]] (inter-level edges must exist before higher-order condensation has anything to link to).

## Current Behavior

`_compact_session_conn()` creates leaf nodes per token-budget block and at most one condensed node per `session_id`. Condensation never spans sessions and never re-condenses condensed nodes. No root node is created.

## Expected Behavior

After compaction, the DAG has a navigable apex: condensed session nodes roll up (recursively, by token budget) into one or more higher-order condensed nodes, terminating in a single project-root summary. Traversal from the root reaches any session's leaves and originals.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py:1400` — `_compact_sessions()`: add cross-session condensation pass after the per-session `for` loop (natural insertion point; see Pattern 4)
- `scripts/little_loops/session_store.py:1307` — `_compact_session_conn()`: add `level` column to INSERT, revise `parent_id` UPDATE to set from higher-order nodes
- `scripts/little_loops/session_store.py:316` — `summary_nodes` table schema (v10 migration): add `level` column, revise `idx_summary_nodes_condensed_dedup` (via new migration v12)
- `scripts/little_loops/session_store.py:334` — `idx_summary_nodes_condensed_dedup`: partial unique index on `session_id WHERE kind='condensed'` excludes `session_id IS NULL` rows; needs a second index for cross-session dedup (e.g., content hash or `(level, ts_start, ts_end)`)
- `scripts/little_loops/history_reader.py:715` — `ll_expand()`: currently hard-codes exactly 2 levels (condensed → leaf); needs to generalize to N levels via iterative parent_id walking or recursive CTE
- `scripts/little_loops/history_reader.py:627` — `ll_grep()`: same 2-level limit for condensed-node filtering; needs N-level support
- `scripts/little_loops/history_reader.py:108` — `SummaryNode` dataclass: add `level` field
- `scripts/little_loops/cli/history.py` — `ll-history` CLI: add root-traversal subcommand (or modify `summary`/`analyze`) to start from the project-root node
- `scripts/little_loops/cli/session.py:330` — `ll-session grep/expand/describe`: expose new N-level traversal options
- `scripts/little_loops/config/features.py:722` — `CompactionConfig`: may add `cross_session_enabled` or `max_level` field
- `scripts/little_loops/config/core.py:664` — `ConfigDefaults.to_dict()`: must serialize new `CompactionConfig` fields (cross_session_enabled, max_level) or they are silently dropped from config output

_Wiring pass added by `/ll:wire-issue`:_
- `session_store.py:305` — module docstring comment describing v10 schema (two-level structure); should be updated to reflect v12 multi-level DAG [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/session_start.py:122` — calls `backfill_incremental()` (no compaction); any auto-compaction gating lives here
- `scripts/little_loops/session_store.py:1541` — `backfill()` calls `_compact_sessions()` as its final phase (line 1541); cross-session pass runs after this
- `scripts/little_loops/session_store.py:1548` — `backfill_incremental()`: does NOT trigger compaction (missing `"summaries"` key in counts dict)
- `scripts/tests/test_session_store.py:1593` — `TestSchemaV10.test_summary_nodes_condensed_dedup_index_exists` — needs companion test for new cross-session dedup index
- `scripts/tests/test_session_store.py:1645` — `TestCompactSession._make_db_with_messages()` — test helper for DB seeding
- `scripts/tests/test_history_reader.py:845` — `TestSummaryDagRetrieval` — condensed-node traversal tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/__init__.py:44` — re-exports `CompactionConfig` in `__all__`; pass-through but all public consumers of the class import through this path [Agent 1 finding]
- `scripts/little_loops/config/core.py:664` — `ConfigDefaults.to_dict()` serializes current `CompactionConfig` fields; new fields must be mirrored here or they are silently dropped from serialized config [Agent 2 finding]
- `scripts/pyproject.toml` — registers `ll-history`, `ll-session`, `ll-history-context` as console entry points; only changes if a new CLI subcommand is registered as a separate entry point [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/session_store.py:1373-1396` — Per-session condensed node creation (Pattern 3): `_compact_session_conn()` creates one condensed per session from ≥2 leaves, re-uses `_summarize_block()` for the summary. This is the template to extend one more level upward across sessions.
- `scripts/little_loops/session_store.py:1331-1347` — Token-budget greedy block accumulation (Pattern 1): the same bucketing logic in `_compact_session_conn()` can be reused to group per-session condensed nodes into higher-order blocks.
- `scripts/little_loops/session_store.py:1132` — `_summarize_block()` three-level LCM Algorithm 3 escalation (Pattern 2): the same convergence-guaranteed summarizer is reused for all levels — leaf, session-condensed, higher-order, root.
- `scripts/little_loops/session_store.py:1389-1394` — Insert-then-update parent_id linking (Pattern 17): after inserting a higher-order condensed node, UPDATE existing condensed nodes' `parent_id` to point to it.
- `scripts/little_loops/session_store.py:164` — `_MIGRATIONS` list (Pattern 5a): append a v12 migration for `ALTER TABLE summary_nodes ADD COLUMN level INTEGER` + new cross-session dedup index.
- `scripts/little_loops/session_store.py:375` — `_apply_migrations()` (Pattern 5a): auto-applies all migrations newer than DB version; no manual DDL needed.
- `scripts/little_loops/session_store.py:1400` — `_compact_sessions()` multi-session orchestration (Pattern 4): after the per-session `for` loop, query all condensed nodes and run the cross-session pass.

### Tests
- `scripts/tests/test_session_store.py` — add idempotency tests for cross-session condensation
- `scripts/tests/test_history.py` — add root-to-leaf traversal tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_config.py:2770` — `TestHistoryConfig.test_compaction_defaults` and `test_compaction_override` need assertions for new `cross_session_enabled`/`max_level` fields; `test_history_to_dict_round_trip:2831` will see new keys in dict output [Agent 3 finding]
- `scripts/tests/test_config_schema.py:304` — `test_history_compaction_in_schema` validates `additionalProperties: false` on the compaction object; must add new property type assertions or schema validation rejects configs with new keys [Agent 2 finding]
- `scripts/tests/test_assistant_messages.py:87` — `test_schema_version_is_11` asserts `SCHEMA_VERSION == 11`; must update to 12 after v12 migration [Agent 3 finding]
- `scripts/tests/test_ll_session.py:529` — `TestGrepExpandDescribe` CLI integration tests for expand/grep with condensed nodes; need N-level variants; `test_describe_returns_node_metadata:622` asserts on describe text output which changes if `level` is printed [Agent 3 finding]
- `scripts/tests/test_ll_session.py:678` — `test_expand_condensed_node_returns_messages_cli` and `test_grep_with_condensed_summary_id_cli` test 2-level traversal via CLI; need N-level extension [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — update session store section with new schema and condensation behavior
- `docs/ARCHITECTURE.md` — update DAG structure description

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/CONFIGURATION.md:1150` — documents compaction config under `history.compaction` section (lines 1150-1182); currently describes "two-hop traversal path" and lists only 4 config keys; must add `cross_session_enabled`/`max_level`, update "two-hop" to "N-level", add cross-session condensation description. Has an existing `update-docs` TODO stub for BUG-1928/FEAT-1712 [Agent 2 finding]
- `docs/reference/CLI.md:1755` — `ll-session describe` already says "Show metadata (level, block span, parent)" preemptively; `ll-history` section may need new root-traversal subcommand docs [Agent 2 finding]
- `CONTRIBUTING.md:246` — `session_store.py` line describes "v1–v10 migrations"; should become "v1–v12 migrations" after this enhancement [Agent 2 finding]

### Configuration
- `config-schema.json:1507` — `history.compaction` section has `additionalProperties: false`; adding `cross_session_enabled`/`max_level` requires explicit property declarations or relaxing `additionalProperties`; otherwise schema validation rejects configs with new keys
- `scripts/little_loops/config/core.py:664` — `ConfigDefaults.to_dict()` serializes the 4 current `CompactionConfig` fields; adding new fields requires updating this dict literal or they are silently dropped from serialized config output

_Wiring pass added by `/ll:wire-issue`:_

- `session_store.py:305` — module docstring comment block describing v10 `summary_nodes` schema; two-level structure comment becomes stale after v12 adds `level` column [Agent 2 finding]
- `scripts/little_loops/config/__init__.py:44` — re-exports `CompactionConfig` in `__all__`; pass-through, no change needed unless renaming [Agent 2 finding]

## Proposed Solution

Three approaches identified based on codebase patterns.

### Option A: Extend `_compact_sessions()` inline (Recommended)

> **Selected:** Option A — least risk, reuses existing bucketing + summarization patterns directly

Add the cross-session pass directly inside `_compact_sessions()` (`session_store.py:1418-1425`) after the per-session `for` loop completes. Query all per-session condensed nodes, group them by token budget using the same greedy algorithm from `_compact_session_conn():1331-1347` (Pattern 1), and recursively call `_summarize_block():1132` (Pattern 2) to create higher-order condensed nodes. Each level sets `parent_id` on the level below (Pattern 17). Terminate when one root node remains.

- **Pros**: Minimal new code; reuses existing bucketing + summarization; fits naturally in existing orchestration
- **Cons**: Makes `_compact_sessions()` longer; cross-session pass is coupled to per-session iteration
- **Precedent**: `_compact_session_conn():1373-1396` already does one-level-up condensation; this adds one more recursion level

### Option B: Separate `_compact_cross_session()` function

Add a new `_compact_cross_session(conn, config)` function called from `backfill():1541` as an additional phase after `_compact_sessions()` returns. Keeps per-session and cross-session logic in separate functions.

- **Pros**: Cleaner separation of concerns; easier to test independently; no modification to `_compact_sessions()`
- **Cons**: More code duplication (token-budget grouping replicated); two functions to maintain
- **Precedent**: `backfill()` already decomposes into separate `_backfill_*` phases (Pattern 8)

### Option C: Generalize into recursive `_compact_level()` helper

Refactor `_compact_session_conn()` to accept a level parameter (leaf=0, session=1, cross-session=2+, root=max). Pass rows (message_events or existing summary_nodes) instead of session_id. The recursive call pattern: `_compact_level(rows, level) → parent_ids` until one row remains.

- **Pros**: Most general; single function handles all levels; natural fit for `level` column
- **Cons**: Largest refactoring; risk of breaking existing per-session compaction; highest implementation cost
- **Precedent**: No existing recursive compaction in codebase; BFS in `fsm/validation.py:1487` is the closest tree walk

**Recommendation**: Option A — least risk, reuses existing patterns directly, fits naturally in the current code structure.

*Added by `/ll:refine-issue` based on codebase analysis by codebase-pattern-finder and codebase-analyzer.*

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-04.

**Selected**: Option A — Extend `_compact_sessions()` inline

**Reasoning**: Option A scores 11/12 by reusing existing Patterns 1, 2, and 17 directly with minimal new code. The per-session compaction loop in `_compact_sessions()` (`session_store.py:1400`) is the natural orchestration point, and the greedy bucketing + `_summarize_block()` components are already proven for both leaf and per-session condensed summarization. Option B's cleaner separation is outweighed by token-budget grouping duplication. Option C's generalization would break working per-session compaction with no recursive precedent in the codebase.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Extend inline | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |
| Option B — Separate function | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| Option C — Recursive helper | 1/3 | 0/3 | 1/3 | 0/3 | 2/12 |

**Key evidence**:
- **Option A**: Reuses `_summarize_block()` (Pattern 2) and greedy bucketing (Pattern 1) from `_compact_session_conn()`, which already does one-level-up condensation. The `parent_id` UPDATE pattern (Pattern 17) is established. Insertion point at `session_store.py:1418` is already identified.
- **Option B**: Follows `backfill()`'s existing phase decomposition (Pattern 8) but would duplicate the token-budget grouping logic across two functions, increasing maintenance cost.
- **Option C**: No recursive compaction precedent in the codebase; BFS in `fsm/validation.py:1487` is the closest tree walk and is structurally different. Would refactor working per-session compaction, risking regression.

## Implementation Steps

1. **Schema migration (v12)**: Append to `_MIGRATIONS` (`session_store.py:164`) an `ALTER TABLE summary_nodes ADD COLUMN level INTEGER DEFAULT 0` + a new partial unique index for cross-session dedup (e.g., `CREATE UNIQUE INDEX idx_summary_nodes_cross_dedup ON summary_nodes(level, ts_start, ts_end) WHERE kind='condensed' AND session_id IS NULL`). Follow Pattern 5a/5d for migration structure and testing.
   - *Test*: Add `TestSchemaV12` to `scripts/tests/test_session_store.py` following `TestSchemaV10` pattern (`test_session_store.py:1614-1639`).

2. **Add `level` to `SummaryNode` dataclass** (`history_reader.py:108`): Add `level: int | None` field, update `ll_describe()` (`history_reader.py:785`) to populate it.

3. **Cross-session condensation pass in `_compact_sessions()`** (`session_store.py:1418`): After the per-session `for` loop:
   - Query all existing condensed nodes: `SELECT id, content, tokens FROM summary_nodes WHERE kind='condensed'`
   - Group by token budget using the greedy algorithm from `_compact_session_conn():1331-1347` (Pattern 1)
   - Call `_summarize_block()` on each group (Pattern 2) to produce higher-order summaries
   - INSERT with `INSERT OR IGNORE`, `kind='condensed'`, `session_id=NULL`, `level=N`
   - UPDATE lower-level condensed nodes' `parent_id` (Pattern 17); handle the edge case where existing condensed nodes' `parent_id` was never set (re-runs must also link already-compacted sessions)
   - Recurse: re-query higher-order condensed nodes, repeat until one root remains
   - *Test*: Add `test_cross_session_condensation_produces_root()` and `test_cross_session_condensation_idempotent()` to `TestCompactSession` in `test_session_store.py:1683`.

4. **Revise dedup for cross-session nodes** (`session_store.py:334`): The current `idx_summary_nodes_condensed_dedup` (`UNIQUE(session_id) WHERE kind='condensed'`) does not cover `session_id IS NULL` rows. The v12 migration adds a second partial unique index. Alternatively, compute a content hash column and index it.

5. **Generalize DAG traversal to N levels** (`history_reader.py:715` — `ll_expand()`):
   - Replace the hard-coded 2-level check (`if kind_row["kind"] == "condensed": ... else: ...`) with an iterative `parent_id` walk: start at the given node, collect descendant leaf nodes via recursive SQL or Python loop, then join to `summary_spans → message_events`.
   - *Alternative*: Use a SQLite recursive CTE (`WITH RECURSIVE`) to walk `parent_id` chains — no precedent in this codebase (tree traversal is Python-based; see `dependency_graph.py:272` Kahn's algorithm) but SQLite supports it.
   - *Test*: Add `test_expand_root_node_returns_all_messages()` to `TestSummaryDagRetrieval` in `test_history_reader.py:845`.

6. **Update `ll-history` CLI** (`cli/history.py`): Add a root-traversal path — identify the root node as the condensed node with `session_id IS NULL` (or max `level`) that has no parent (`parent_id IS NULL`). Expose via a new subcommand or as the default starting point for `summary`.

7. **Config gating** (optional): Add `cross_session_enabled: bool = True` to `CompactionConfig` (`config/features.py:722`) for feature-flag gating. Update `config-schema.json:1507`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. **Config serialization** (`config/core.py:664`): When adding `cross_session_enabled`/`max_level` to `CompactionConfig`, update `ConfigDefaults.to_dict()` to serialize the new fields. Without this, new config values are silently dropped from `BRConfig.to_dict()` output. [Agent 2 finding]

9. **Schema validation** (`config-schema.json:1507-1533`): The `history.compaction` object has `additionalProperties: false`. Adding `cross_session_enabled`/`max_level` without declaring them in `properties` causes schema validation to reject configs containing those keys. Either add explicit property declarations or relax `additionalProperties`. [Agent 2 finding]

10. **Config tests** (`test_config.py:2770`, `test_config_schema.py:304`): Add assertions for `cross_session_enabled` and `max_level` defaults in `test_compaction_defaults` and `test_compaction_override`. Update `test_history_to_dict_round_trip` for new dict keys. Update `test_history_compaction_in_schema` for new property types. [Agent 3 finding]

11. **CLI output format** (`cli/session.py:374-377`, `test_ll_session.py:622`): If `level` is added to `describe` text output, update `test_describe_returns_node_metadata` assertions. The CLI print block at line 374 hardcodes which fields are shown; adding `level=` changes output. [Agent 2 finding]

12. **Version bump surface** (`test_assistant_messages.py:87`, `test_session_store.py`): `test_schema_version_is_11` (and any other test asserting `SCHEMA_VERSION == 11`) must be updated to 12. The `_MIGRATIONS[:9]` slice in `test_v9_to_v10_migration` still works correctly but the version assertion at line 1636 must bump from 11 to 12. [Agent 3 finding]

13. **Session store docstring** (`session_store.py:305-314`): The module-level comment describes v10's two-level `summary_nodes` schema. After v12 adds `level` and cross-session dedup, this comment should reflect the multi-level DAG structure. [Agent 2 finding]

14. **Documentation updates**:
    - `docs/reference/CONFIGURATION.md:1150-1182`: Add `cross_session_enabled`/`max_level` to config key table and JSON example; update "two-hop traversal" to "N-level"; remove the `update-docs` TODO stub after completing the write-up. [Agent 2 finding]
    - `CONTRIBUTING.md:246`: Update `session_store.py` description from "v1–v10 migrations" to "v1–v12 migrations". [Agent 2 finding]
    - `docs/reference/CLI.md:1755`: If a root-traversal subcommand is added to `ll-history`, document it; `ll-session describe` already mentions "level" preemptively. [Agent 2 finding]

## API/Interface

- Possible new `summary_nodes.level`/`depth` column (schema migration).
- `ll-history` cross-session traversal entry point starting at the root node.
- New idempotency key for cross-session/root condensed nodes (the current partial unique index does not cover `session_id IS NULL`).

## Acceptance Criteria

- After `backfill()` with compaction enabled on a project with ≥ 2 sessions, exactly one project-root summary node exists and is reachable to every session's condensed node.
- Re-running compaction is idempotent (no duplicate root/higher-order nodes).
- `ll-history` can answer a cross-session question by descending from the root.

## Scope Boundaries

- **In scope**: Cross-session condensation pass (`_compact_sessions()`), recursive higher-order condensation terminated by a single project-root summary node, schema migration for `level`/`depth` column and revised dedup index, `ll-history` DAG traversal from the root.
- **Out of scope**: Changes to per-session compaction logic (FEAT-1712), inter-level edge fixes (BUG-1926), condensation content/quality tuning, changes to the `backfill()` entry-point signature.

## Success Metrics

- **Root node exists**: After compaction on ≥2 sessions, exactly one root summary node with `depth` = max (or `session_id IS NULL` as the apex).
- **Idempotency**: Re-running compaction produces zero net changes (no duplicate root/higher-order nodes, no orphan condensed nodes).
- **Traversal reachability**: From the root, `ll-history` can reach every leaf/original node across all condensed sessions within 3 hops (root → higher-order → session-condensed → leaf).

## Impact

- **Who benefits**: agents/users running month-scale cross-session queries — the EPIC-1707 headline use case.
- **Cost**: additive (one extra LLM call per higher-order group); confined to opt-in/rate-limited background compaction.
- **Relationship**: completes the "DAG" structure FEAT-1712 began; pairs with [[BUG-1926]] (edges) to make traversal real.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Current Compaction Architecture (from codebase-analyzer)

- **Entry point**: `backfill()` at `session_store.py:1541` calls `_compact_sessions()` as its final phase. `backfill_incremental()` (`session_store.py:1548`) does NOT trigger compaction (missing `"summaries"` key in its counts dict). The session-start hook (`hooks/session_start.py:122`) calls `backfill_incremental()` in a daemon thread — compaction is never triggered automatically at session start.
- **`_compact_sessions()`** (`session_store.py:1400-1426`): Reads `CompactionConfig` from config, iterates all `sessions` rows, delegates to `_compact_session_conn()` per session. Returns total leaf count. No post-iteration cross-session pass exists.
- **`_compact_session_conn()`** (`session_store.py:1307-1397`): Greedy block accumulation by token budget (`len(content) // 4` via `_estimate_tokens():1129`), calls `_summarize_block():1132` per block (LCM Algorithm 3 escalation: level 1 LLM → level 2 bullet → level 3 truncation), INSERTs leaf rows with `INSERT OR IGNORE`, then if ≥2 leaves exist, creates one condensed node summarizing all leaf summaries. Updates `parent_id` on leaves.
- **Critical edge case**: The `parent_id` UPDATE only runs when `cursor.rowcount > 0` (a new condensed node was created this call; `session_store.py:1389`). If compaction is re-run on an already-compacted session, `INSERT OR IGNORE` returns `rowcount=0`, so existing condensed nodes' `parent_id` is never updated. The cross-session pass must explicitly UPDATE `parent_id` on existing condensed nodes.
- **No `level` or `depth` column** exists in `summary_nodes`. The schema (`session_store.py:316-326`) has `id, kind, content, tokens, parent_id, session_id, ts_start, ts_end, created_at`. No mechanism distinguishes session-condensed from higher-order from root.

### Index Constraint Gap (from codebase-analyzer)

- **`idx_summary_nodes_condensed_dedup`** (`session_store.py:334`): `CREATE UNIQUE INDEX ... ON summary_nodes(session_id) WHERE kind = 'condensed'`. SQLite partial unique indexes do NOT enforce uniqueness for rows where the indexed columns are NULL. Cross-session/root condensed nodes would have `session_id = NULL` and would NOT be covered. A new dedup mechanism is required.

### DAG Traversal Limitation (from codebase-analyzer)

- **`ll_expand()`** (`history_reader.py:715-768`): Hard-codes exactly 2 levels — checks `kind` for `'condensed'` vs. `'leaf'`, uses different SQL for each. No recursive or N-level traversal.
- **`ll_grep()`** (`history_reader.py:627-712`): Same 2-level limitation for `--summary-id` filtering.
- **`ll-history` CLI** (`cli/history.py`): Has NO DAG traversal capability at all. Subcommands (`summary`, `analyze`, `export`, `sessions`) do not consult `summary_nodes`. The `ll_expand`/`ll_grep` functions are exposed through `ll-session` CLI (`cli/session.py:330`), not `ll-history`.

### Schema Migration Pattern (from codebase-pattern-finder)

- **`_MIGRATIONS`** list at `session_store.py:164` — versioned list; `SCHEMA_VERSION = 11` at `session_store.py:75`. v12 would be the next migration.
- **`_apply_migrations()`** at `session_store.py:375` — auto-applies all migrations newer than DB version; idempotent (`ensure_db()` can be called safely at any time).
- **Test pattern**: `TestSchemaV10.test_v9_to_v10_migration` at `test_session_store.py:1614-1639` — bootstrap old schema version, run `ensure_db()`, assert version bumped and new tables/indexes exist.
- **`ALTER TABLE` precedent**: migration v2 (`session_store.py:220-225`) adds columns via `ALTER TABLE ... ADD COLUMN ...`.

### Existing Reusable Components (from codebase-pattern-finder)

- **`_summarize_block():1132`**: Already used for both leaf and per-session condensed summarization. Same function can generate higher-order and root summaries — no new summarizer needed.
- **Greedy block grouping** (`_compact_session_conn():1331-1347`): Same algorithm can bucket condensed nodes by token budget for higher-order grouping.
- **`INSERT OR IGNORE` + partial unique index** pattern used throughout for idempotency.
- **No recursive CTE precedent**: Tree/DAG traversal is Python-based (Kahn's algorithm in `dependency_graph.py:272`, BFS in `fsm/validation.py:1487`). SQLite recursive CTEs would be new to the codebase.
- **`CompactionConfig`** at `config/features.py:722`: Feature-gating dataclass with `enabled`, `budget_tokens`, `model`, `timeout` fields. Cross-session config (e.g., `cross_session_enabled`, `max_level`) would extend this.

## Status

done

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-04_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Concerns
- **Wide file surface**: 21 change sites across code (10), tests (6), and docs (5). The breadth is mechanical but increases the chance of missing a site during implementation — use the enumerated "Files to Modify" list as a checklist.
- **`decision_needed` stale?**: Frontmatter carries `decision_needed: true`, but the issue body clearly recommends Option A (extend `_compact_sessions()` inline). The three options are framed with pros/cons and a stated recommendation — consider clearing this flag before starting.

### Outcome Risk Factors
- **Broad change surface**: 21 files across code, tests, and docs — the wide mechanical fanout increases the risk of missing a site during implementation. Mitigation: use the enumerated file list in Integration Map as a checklist.
- **Novel recursive algorithm**: The cross-session condensation pass (greedy grouping + recursive `_summarize_block()` calls + parent_id management) is new to the codebase. While it reuses existing components (Patterns 1, 2, 17), the recursive termination logic and idempotency edge cases (re-linking existing condensed nodes whose `parent_id` was never set) are novel and deserve extra test attention.
- **N-level traversal generalization**: Replacing hardcoded 2-level DAG traversal in `ll_expand()` and `ll_grep()` requires care to avoid breaking existing condensed-node queries. The current 2-level path must remain correct while adding N-level support.
- **Schema migration risk**: v12 migration adds `level` column and a new partial unique index with `session_id IS NULL` filtering. Test this against already-compacted databases to ensure the migration doesn't conflict with existing condensed nodes.

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-04
- **Reason**: Issue too large for single session (score: 11/11 Very Large). 31+ files across code, tests, docs, config. Decomposed into 3 focused children by architectural layer.

### Decomposed Into
- ENH-1953: Schema v12 and data layer foundation for cross-session condensation
- ENH-1954: Cross-session condensation pass with config gating
- ENH-1955: N-level DAG traversal and CLI for project-root summary

## Session Log
- `/ll:issue-size-review` - 2026-06-04T19:28:00Z - `8b66735f-5337-46b3-ba3c-44648e5faca2.jsonl`
- `/ll:decide-issue` - 2026-06-05T00:22:33 - `d8dc11ff-3f97-4891-860f-b70216ab8915.jsonl`
- `/ll:confidence-check` - 2026-06-04T22:15:00Z - `48acba14-5b46-4147-80f5-0ae8381496be.jsonl`
- `/ll:wire-issue` - 2026-06-05T00:15:09 - `65f10d05-7c19-4afe-8cfe-e333863941be.jsonl`
- `/ll:refine-issue` - 2026-06-05T00:07:59 - `04984f87-2cce-495d-9412-485498c97895.jsonl`
- `/ll:format-issue` - 2026-06-04T04:27:34 - `950150ed-ad92-423e-bdeb-698213762597.jsonl`
- `/ll:capture-issue` - 2026-06-04T04:15:05Z - `92ad3505-8fca-44b2-aa0f-0ee9ce80d024.jsonl`
- `/ll:confidence-check` - 2026-06-05T00:30:00Z - `117acacb-0bbe-4c10-aa8f-45a530c6ee73.jsonl`
