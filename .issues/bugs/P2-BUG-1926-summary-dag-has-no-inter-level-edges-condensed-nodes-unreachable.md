---
id: BUG-1926
title: Summary DAG has no inter-level edges; condensed nodes unreachable via expand
type: BUG
priority: P2
status: done
captured_at: '2026-06-04T04:15:05Z'
completed_at: '2026-06-04T06:11:04Z'
discovered_date: '2026-06-04'
discovered_by: capture-issue
parent: EPIC-1707
relates_to:
- FEAT-1712
labels:
- bug
- history
- session-store
- context-management
- captured
decision_needed: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
implementation_order_risk: true
---

# BUG-1926: Summary DAG has no inter-level edges; condensed nodes unreachable via expand

## Summary

FEAT-1712's `compact_session()` builds `leaf` and `condensed` summary nodes but never links them: the condensed node gets no `summary_spans` rows and the leaves keep `parent_id = NULL`. The result is not a traversable DAG — it is two disconnected node sets that only share a `session_id` column. `ll_expand(condensed_id)` returns `[]`, and `ll_describe` always reports `parent_id = None`. The feature's own Use Case ("traverse the summary DAG from the project root summary downward … use `ll_expand` to drill into specific sessions") cannot be executed.

## Steps to Reproduce

1. Create or select a session with ≥ 2 leaf summary nodes.
2. Call `compact_session()` to generate a condensed node for that session.
3. Call `ll_expand(<condensed_node_id>)` to attempt DAG traversal from the condensed node.
4. Observe: returns `[]` (empty list — no `summary_spans` rows link the condensed node to its leaves).
5. Verify leaf linkage: `ll_describe <leaf_id>` reports `parent_id = None` for every leaf in the session.

## Motivation

- **Feature integrity**: FEAT-1712 shipped with `compact_session()` claiming to build a traversable summary DAG, but the DAG has no inter-level edges — condensed nodes are unreachable. This bug means the feature does not deliver its central promise.
- **EPIC-1707 impact**: The "history DB as agent context layer" epic depends on DAG traversal (`ll_expand` drill-down from project root to individual sessions). Without this fix, the multi-resolution narrative is broken at the first condensation step.
- **User impact**: Any agent or user calling `ll_expand(<condensed_id>)` gets an empty result, making session condensation useless for context drill-down.

## Root Cause

`scripts/little_loops/session_store.py` — `_compact_session_conn()` (~lines 1122-1139). After inserting the per-session `condensed` node:

```python
conn.execute(
    "INSERT OR IGNORE INTO summary_nodes"
    "(kind, content, tokens, session_id, ts_start, ts_end, created_at)"
    " VALUES('condensed', ?, ?, ?, NULL, NULL, ?)",
    (condensed_text, _est(condensed_text), session_id, now),
)
```

No `summary_spans` rows are inserted for the condensed node, and the leaves' `parent_id` is never updated. FEAT-1712's Integration Map explicitly required one of the two linkage mechanisms ("the condensed node covering them via its own `summary_spans` (or a `parent_id` back-link from leaves — pick one and assert it in `TestCompactSession`)"); **neither** was implemented. The existing tests only assert the condensed node *exists* and that *leaf* spans exist (`test_session_store.py:test_compact_session_condensed_node_when_multiple_leaves`, `test_compact_session_creates_spans`), so the missing edges slipped through.

This is also the exact failure mode LCM's referential-integrity requirement (Appendix B, "Provenance … preventing orphaned context") exists to prevent — but Decision 3 made FKs decorative, so nothing catches it at the DB layer either.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`ll_expand()` at `history_reader.py:520-526` only traverses `summary_spans`**: The query is `SELECT me.* FROM message_events me JOIN summary_spans ss ON ss.message_event_id = me.id WHERE ss.summary_id = ?`. It does NOT use `parent_id` at all. Even after setting `parent_id` on leaves (Option A), `ll_expand(condensed_id)` will still return `[]` because no `summary_spans` rows exist for the condensed node. **The read side must also be modified.**
- **`ll_grep()` with `summary_id` at `history_reader.py:469-471` has the same gap**: The `summary_id` filter path (`WHERE ss.summary_id = ?`) also exclusively joins through `summary_spans`. Passing a condensed node ID returns `[]`.
- **`ll_describe()` at `history_reader.py:551` DOES read `parent_id`**: The SELECT includes `parent_id` in its column list and `SummaryNode` unpacks it at line 568. Option A alone would fix `ll_describe()` output but not traversal.
- **`parent_id` column has no index** (`session_store.py:317`): The column exists as `parent_id INTEGER REFERENCES summary_nodes(id)` with no accompanying `CREATE INDEX`. A two-hop traversal query (`condensed → leaves via parent_id → message_events via summary_spans`) will table-scan `summary_nodes` without one.
- **`_compact_session_conn()` at line 1132 discards `cursor.lastrowid`**: The condensed node's INSERT never captures its generated ID, so even if we wanted to set `parent_id` or insert `summary_spans`, we'd need to re-query for it (or capture `lastrowid`).

## Proposed Solution

In `_compact_session_conn()` (`scripts/little_loops/session_store.py`, ~line 1132), after inserting the condensed node, add the missing linkage. Two implementation options:

**Option A: `parent_id` back-link (recommended — simpler, single UPDATE)**

> **Selected:** Option A — `parent_id` back-link; highest codebase fit (11/12 vs 5/12). One UPDATE, reuses purpose-built `parent_id` column that already has full read-side support.
```python
# After the leaf-insert loop, add:
condensed_id = cursor.lastrowid
conn.execute(
    "UPDATE summary_nodes SET parent_id = ? WHERE session_id = ? AND kind = 'leaf' AND parent_id IS NULL",
    (condensed_id, session_id),
)
```
`ll_expand` queries `WHERE parent_id = ?` — already compatible with existing indices.

**Option B: `summary_spans` rows (richer, but column-reuse question)**
Insert a `summary_spans` row per leaf linking the condensed node to each leaf `summary_nodes.id`. Requires deciding whether `summary_spans.message_event_id` (FK-references `message_events`) is the right column for node→node edges, or whether a schema change is needed.

**Recommendation**: Option A. It is one UPDATE, doesn't fight the FK, and `parent_id` already exists on the table — it's just unused by compaction today.

### Read-Side Changes Required (Both Options)

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Regardless of which write-side option is chosen, `ll_expand()` at `history_reader.py:505-533` must be modified.** The current query exclusively joins `summary_spans` → `message_events` and has no path for resolving a condensed node's children.

**Required `ll_expand()` modification** — add a two-hop traversal for condensed nodes:

```python
def ll_expand(summary_id: int, *, db: Path | str = DEFAULT_DB_PATH) -> list[dict]:
    conn = _connect_readonly(Path(db))
    if conn is None:
        return []
    try:
        # Check node kind first
        node = conn.execute(
            "SELECT kind FROM summary_nodes WHERE id = ?", (summary_id,)
        ).fetchone()
        if node is None:
            return []
        
        if node["kind"] == "condensed":
            # Two-hop: condensed → leaves (via parent_id) → message_events (via summary_spans)
            rows = conn.execute(
                "SELECT me.id, me.session_id, me.ts, me.content"
                " FROM message_events me"
                " JOIN summary_spans ss ON ss.message_event_id = me.id"
                " JOIN summary_nodes leaf ON leaf.id = ss.summary_id"
                " WHERE leaf.parent_id = ?"
                " ORDER BY me.ts, me.id",
                (summary_id,),
            ).fetchall()
        else:
            # Leaf node: direct summary_spans traversal (existing path)
            rows = conn.execute(
                "SELECT me.id, me.session_id, me.ts, me.content"
                " FROM message_events me"
                " JOIN summary_spans ss ON ss.message_event_id = me.id"
                " WHERE ss.summary_id = ?"
                " ORDER BY me.ts, me.id",
                (summary_id,),
            ).fetchall()
    except sqlite3.Error:
        logger.warning(...)
        return []
    finally:
        conn.close()
    return [dict(row) for row in rows]
```

**`ll_grep()` at `history_reader.py:464-474`** — the `summary_id` filter path has the same gap. If `summary_id` points to a condensed node, the `JOIN summary_spans ss ON ss.message_event_id = me.id WHERE ss.summary_id = ?` returns no rows. Fix with the same two-hop pattern when `summary_id` is a condensed node.

**`parent_id` index** — the column at `session_store.py:317` has no index. Add `CREATE INDEX IF NOT EXISTS idx_summary_nodes_parent_id ON summary_nodes(parent_id)` to the v10 migration (or a new v11 migration) so the `WHERE leaf.parent_id = ?` query doesn't table-scan. Without this index, every `ll_expand(condensed_id)` call scans all summary_nodes rows.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-04.

**Selected**: Option A — `parent_id` back-link

**Reasoning**: Option A leverages the purpose-built `parent_id` column on `summary_nodes` (`session_store.py:317`) which already has full read-side support in the `SummaryNode` dataclass (`history_reader.py:106`) and `ll_describe()` (`history_reader.py:551,568`). The `lastrowid` capture and UPDATE-after-INSERT patterns both exist in the same file (lines 1115 and 556). Option B would repurpose `summary_spans.message_event_id` for node→node edges, creating semantic ambiguity across all 3 read paths and contradicting the documented design intent in both the schema comment (`session_store.py:305-306`) and `ARCHITECTURE.md:562`. The `parent_id` column was created for exactly this purpose and is currently unused — this bug is the gap it was designed to fill.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A: `parent_id` back-link | 3/3 | 3/3 | 3/3 | 2/3 | **11/12** |
| Option B: `summary_spans` rows | 1/3 | 1/3 | 2/3 | 1/3 | **5/12** |

**Key evidence**:
- **Option A**: `parent_id` column exists at `session_store.py:317` with FK to `summary_nodes(id)`; `lastrowid` capture pattern at line 1115 (same function); `UPDATE` + captured ID pattern at line 556 (same file); `ll_describe()` already reads and surfaces `parent_id` (3 lines); zero writes to `parent_id` today — this is the first use, exactly as designed.
- **Option B**: `message_event_id` FK targets `message_events(id)` — inserting `summary_nodes.id` values creates semantic ambiguity; all 3 read paths hard-code `JOIN ... ON ss.message_event_id = me.id` against `message_events`; documented design intent scopes `summary_spans` to leaf→message linkage only; repurposing the column contradicts both the schema comment and `ARCHITECTURE.md`.

## Expected Behavior

A condensed node is reachable to its constituent leaves, which are in turn reachable to their `message_events`, so an agent can traverse condensed → leaf → original message. `ll_expand(condensed_id)` returns the covered content (either the leaf summaries directly, or the underlying messages via two-hop traversal — pick the contract and document it).

## Current Behavior

`ll_expand(condensed_id)` returns `[]` because the condensed node has no `summary_spans`. `parent_id` is always `NULL`. The DAG is effectively a flat two-level forest with no edges.

## Implementation Steps

### Phase 1: Write-Side Fix (`session_store.py`)

1. In `_compact_session_conn()` at line 1132, capture `cursor.lastrowid` after the condensed node INSERT:
   ```python
   cursor = conn.execute(
       "INSERT OR IGNORE INTO summary_nodes"
       "(kind, content, tokens, session_id, ts_start, ts_end, created_at)"
       " VALUES('condensed', ?, ?, ?, NULL, NULL, ?)",
       (condensed_text, _est(condensed_text), session_id, now),
   )
   if cursor.rowcount:
       condensed_id = cursor.lastrowid
   ```
2. After capturing `condensed_id`, set `parent_id` on all leaf nodes for the session (Option A):
   ```python
   conn.execute(
       "UPDATE summary_nodes SET parent_id = ?"
       " WHERE session_id = ? AND kind = 'leaf' AND parent_id IS NULL",
       (condensed_id, session_id),
   )
   ```
   The `all_leaves` IDs from the SELECT at line 1123 are already available; can use `WHERE id IN (...)` for a tighter UPDATE, but the `session_id + kind + parent_id IS NULL` filter is idempotent-safe.

### Phase 2: Read-Side Fix (`history_reader.py`)

3. Modify `ll_expand()` at line 505 to handle condensed nodes with a two-hop traversal:
   - Check the node's `kind` first (SELECT kind FROM summary_nodes WHERE id = ?)
   - If `kind = 'condensed'`: traverse `parent_id` → leaf nodes → `summary_spans` → `message_events`
   - If `kind = 'leaf'`: keep the existing direct `summary_spans` query
   - Update the docstring to document the condensed-node contract (returns the underlying messages, same as leaf expansion)
4. Modify `ll_grep()` at line 464 — the `summary_id` filter path — with the same two-hop traversal when `summary_id` points to a condensed node.
5. Add a `parent_id` index to the schema (`session_store.py` v10 migration or a new v11 migration):
   ```sql
   CREATE INDEX IF NOT EXISTS idx_summary_nodes_parent_id ON summary_nodes(parent_id);
   ```

### Phase 3: Tests

6. Add linkage assertions to `TestCompactSession.test_compact_session_condensed_node_when_multiple_leaves` in `test_session_store.py` (~line 1690):
   - Assert `parent_id` is set on all leaf nodes for the session
   - Assert `parent_id` points to the condensed node's ID
7. In `TestCompactSession.test_compact_session_creates_spans` (~line 1672), add an assertion that the condensed node's leaves have non-NULL `parent_id`.
8. Add a new test in `test_history_reader.py:TestSummaryDAG` — `test_expand_condensed_node_returns_messages`:
   - Seed a DB with enough messages to produce ≥ 2 leaves and a condensed node (follow the pattern at `test_compact_session_condensed_node_when_multiple_leaves:1690` — use a tiny budget of 10 tokens to force multiple blocks)
   - Call `ll_expand(condensed_id)` and assert the result is non-empty and contains the original messages
9. Add `test_grep_with_condensed_summary_id` — verify `ll_grep(pattern, summary_id=condensed_id)` returns matching messages.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `docs/ARCHITECTURE.md` — document `parent_id` linkage mechanism in schema migration table (line 562) and component table (line 634). Mention both edge types: `summary_spans` for leaf→message, `parent_id` for condensed→leaf. [Agent 2]
11. Add `test_summary_nodes_parent_id_index_exists` to `test_session_store.py` — follow the pattern from `test_summary_nodes_leaf_dedup_index_exists` (line 1557). Verify `idx_summary_nodes_parent_id` index exists after `ensure_db()`. [Agent 2 + Agent 3]
12. Add condensed-node CLI integration tests to `test_ll_session.py` (`TestGrepExpandDescribe` class, ~L529): `test_expand_condensed_node_returns_messages_cli` and `test_grep_with_condensed_summary_id_cli`. Follow existing patterns at lines 601 and 585. Requires multi-leaf fixture (≥2 leaves + condensed node; follow `test_compact_session_condensed_node_when_multiple_leaves` at line 1690 with 30 messages, budget=10 tokens). [Agent 1 + Agent 3]
13. Add parent_id assertion to `test_backfill_with_compaction_enabled` in `test_session_store.py` (~L1729) — the full `backfill()` → `_compact_sessions()` → `_compact_session_conn()` chain gets incidental coverage; add explicit assertion that leaf nodes have non-NULL `parent_id` when a condensed node exists. [Agent 3]
14. Decide schema migration approach for `parent_id` index: amend v10 migration (simpler, idempotent-safe via `IF NOT EXISTS`) or create new v11 migration with `SCHEMA_VERSION` bump to 11 (cleaner migration hygiene). If v11: add `TestV11Migration` class following `TestSchemaV10` pattern at line 1532. [Agent 2]
15. Coordinate merge order with BUG-1928: apply BUG-1926 first (simpler change to `_compact_session_conn()`), then rebase BUG-1928 on top. BUG-1928 also touches `_compact_session_conn()` and proposes promoting `_est` to module-level — applying BUG-1926 first avoids merge conflicts. [Agent 2 — inter-issue coupling]
16. Document that ENH-1927 (recursive cross-session condensation) depends on this fix: ENH-1927's cross-session condensation pass needs the `parent_id` links to understand existing DAG structure. The Option A (parent_id) vs. Option B (summary_spans) choice here affects ENH-1927's design for finding children of condensed nodes. [Agent 2 — inter-issue coupling]

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — `_compact_session_conn()` (~L1122-1137): capture `lastrowid`, set `parent_id` on leaves; add `parent_id` index to v10/v11 migration
- `scripts/little_loops/history_reader.py` — `ll_expand()` (~L505): add two-hop condensed-node traversal; `ll_grep()` (~L464): fix `summary_id` filter for condensed nodes; update both docstrings

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/session.py:354` — `main_session()` dispatches `expand` subcommand to `ll_expand()`
- `scripts/little_loops/cli/session.py:367` — `main_session()` dispatches `describe` subcommand to `ll_describe()`

### Tests
- `scripts/tests/test_session_store.py` — existing `test_compact_session_condensed_node_when_multiple_leaves` (~L1690): add parent_id linkage assertions; `test_compact_session_creates_spans` (~L1672): add parent_id assertion; `test_backfill_with_compaction_enabled` (~L1729): add parent_id assertion (incidental coverage from full backfill→compact pipeline)
- `scripts/tests/test_history_reader.py` — new: `test_expand_condensed_node_returns_messages` (needs ≥2-leaf fixture, follows `test_compact_session_condensed_node_when_multiple_leaves` pattern); new: `test_grep_with_condensed_summary_id`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_session.py` — `TestGrepExpandDescribe` (~L529) exercises the full CLI dispatch path (`ll-session expand/describe/grep` → `main_session()` → `ll_expand/ll_describe/ll_grep`). All existing CLI tests use single-leaf fixtures (no condensed node). Add condensed-node CLI integration tests: `test_expand_condensed_node_returns_messages_cli` and `test_grep_with_condensed_summary_id_cli`, following the patterns at lines 601 and 585. [Agent 1 — CLI caller; Agent 3 — test gap]
- `scripts/tests/test_session_store.py` — new: `test_summary_nodes_parent_id_index_exists` in `TestSchemaV10` (or `TestSchemaV11` if new migration). Follow the pattern from `test_summary_nodes_leaf_dedup_index_exists` at line 1557 — verify `idx_summary_nodes_parent_id` exists in `sqlite_master` after `ensure_db()`. [Agent 2 — schema coupling; Agent 3 — test gap]

### Documentation
- `docs/reference/API.md` — update `ll_expand` / `ll_describe` behavior for condensed nodes

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — line 562 (Schema migration table v10) describes `summary_nodes`/`summary_spans` but says "`summary_spans` links each node back to its source messages for lossless drill-down." After the fix, inter-level edges use `parent_id` (not `summary_spans`). Update to mention both mechanisms: leaf→message via `summary_spans`, condensed→leaf via `parent_id`. Line 634 (Component table) documents `compact_session()` — mention `parent_id` linkage. [Agent 2 — doc coupling]

### Configuration
- `scripts/little_loops/session_store.py` — Schema migration: decide whether to add `idx_summary_nodes_parent_id` as a new v11 migration (requires bumping `SCHEMA_VERSION` from 10 to 11 at line 72, plus `TestV11Migration` class) or amend the v10 migration block (~L302-332). Amending v10 is simpler and idempotent-safe (`IF NOT EXISTS`); new v11 is cleaner for migration hygiene. [Agent 2 — schema coupling]

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/features.py` — `CompactionConfig` at line 720. No config key changes needed, but the dataclass docstring references `summary_nodes`. Document that compaction now sets `parent_id` linkage. [Agent 2 — config coupling, informational]

## API/Interface

No new public surface. `ll_expand` / `ll_describe` behavior changes (condensed nodes become traversable); update their docstrings in `history_reader.py`.

## Acceptance Criteria

- After `compact_session()` on a session with ≥ 2 leaves, the condensed node is linked to all its leaves (via `parent_id` or `summary_spans`).
- `ll_expand(<condensed_id>)` returns a non-empty result per the documented contract.
- A regression test asserts condensed→leaf linkage and fails against the current implementation.

## Impact

- **Who benefits**: any agent/user relying on DAG traversal (the EPIC-1707 core deliverable). Today the "DAG" claim overstates the shipped structure.
- **Severity**: P2 — the shipped feature does not deliver its central promise (traversable multi-resolution DAG), though compaction is opt-in (`history.compaction.enabled=false`) so no live path is broken.

## Status

---

open

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-03_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- **Moderate per-site complexity across 8 files**: The two-hop traversal change to `ll_expand()` and `ll_grep()` is multi-function logic (not a simple substitution), touching both the compaction write path and the read/query path across `session_store.py` and `history_reader.py`. Mitigation: the code paths are well-isolated (2 callers), and the refactored query logic follows existing JOIN patterns.
- **Open decision: v10 amendment vs v11 migration**: The `parent_id` index addition requires a schema migration decision — amend the existing v10 migration block (simpler, `IF NOT EXISTS`-safe) or create a new v11 migration with `SCHEMA_VERSION` bump (cleaner hygiene). Either approach is correct; resolve before implementing.
- **Test gap for condensed-node traversal**: Existing `ll_expand`/`ll_grep` tests use single-leaf fixtures only. The 8 new tests enumerated in the Implementation Steps (spanning `test_session_store.py`, `test_history_reader.py`, and `test_ll_session.py`) are co-deliverables — implement them alongside the fix to close the coverage gap.

## Session Log
- `/ll:ready-issue` - 2026-06-04T05:09:26 - `817738ef-041a-4abf-9c02-5316ebb6a0fe.jsonl`
- `/ll:decide-issue` - 2026-06-04T05:02:04 - `fbf58583-e671-4e96-8ee0-69f89f6369c2.jsonl`
- `/ll:confidence-check` - 2026-06-03 - `c8a2cd54-95c1-4e49-9641-8490445ddeea.jsonl`
- `/ll:confidence-check` - 2026-06-04T19:24:00 - `89e17d9b-7d91-497e-9480-aa3f158be3a0.jsonl`
- `/ll:wire-issue` - 2026-06-04T04:52:34 - `e810a662-a9ca-4dbd-be16-bc9daca66935.jsonl`
- `/ll:refine-issue` - 2026-06-04T04:43:30 - `2e1648a6-b5ec-4c5d-9a10-85d3c6b75e22.jsonl`
- `/ll:format-issue` - 2026-06-04T04:26:10 - `1581336d-4181-4074-85b0-16f72458869b.jsonl`
- `/ll:capture-issue` - 2026-06-04T04:15:05Z - `92ad3505-8fca-44b2-aa0f-0ee9ce80d024.jsonl`
- `/ll:manage-issue` - 2026-06-04T06:11:04Z - `bea53332-cc7d-4500-956f-e77ffd6231cd.jsonl`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-06-04
- **Status**: Completed

### Changes Made
- `scripts/little_loops/session_store.py`: Captured `cursor.lastrowid` after condensed node INSERT; set `parent_id` on leaf nodes via UPDATE; added `idx_summary_nodes_parent_id` index to v10 migration
- `scripts/little_loops/history_reader.py`: Added two-hop condensed-node traversal to `ll_expand()` (condensed→leaves via parent_id→messages via summary_spans); added same two-hop traversal to `ll_grep()` summary_id filter; updated docstrings
- `scripts/tests/test_session_store.py`: Added `parent_id` linkage assertions to `test_compact_session_condensed_node_when_multiple_leaves`, `test_compact_session_creates_spans`, `test_backfill_with_compaction_enabled`; added `test_summary_nodes_parent_id_index_exists`
- `scripts/tests/test_history_reader.py`: Added `test_expand_condensed_node_returns_messages` and `test_grep_with_condensed_summary_id` with multi-leaf condensed-node fixture
- `scripts/tests/test_ll_session.py`: Added `test_expand_condensed_node_returns_messages_cli` and `test_grep_with_condensed_summary_id_cli` CLI integration tests

### Verification Results
- Tests: PASS (test_history_reader: 62 passed, test_ll_session: 56 passed, test_session_store: parent_id index + targeted compaction tests pass)
- Lint: PASS (ruff check: All checks passed)
