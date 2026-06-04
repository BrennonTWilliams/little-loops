---
id: BUG-1926
title: Summary DAG has no inter-level edges; condensed nodes unreachable via expand
type: BUG
priority: P2
status: open
captured_at: "2026-06-04T04:15:05Z"
discovered_date: "2026-06-04"
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

## Proposed Solution

In `_compact_session_conn()` (`scripts/little_loops/session_store.py`, ~line 1132), after inserting the condensed node, add the missing linkage. Two implementation options:

**Option A: `parent_id` back-link (recommended — simpler, single UPDATE)**
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

## Expected Behavior

A condensed node is reachable to its constituent leaves, which are in turn reachable to their `message_events`, so an agent can traverse condensed → leaf → original message. `ll_expand(condensed_id)` returns the covered content (either the leaf summaries directly, or the underlying messages via two-hop traversal — pick the contract and document it).

## Current Behavior

`ll_expand(condensed_id)` returns `[]` because the condensed node has no `summary_spans`. `parent_id` is always `NULL`. The DAG is effectively a flat two-level forest with no edges.

## Implementation Steps

1. In `_compact_session_conn()`, after inserting the condensed node, capture its `lastrowid` and either:
   - **(a)** set `parent_id = <condensed_id>` on every leaf row for the session, **or**
   - **(b)** insert `summary_spans` rows linking the condensed node to its leaf `summary_nodes.id`s (note: `summary_spans.message_event_id` currently FK-references `message_events` — decide whether condensed→leaf spans reuse this column or whether a `parent_id` back-link is the cleaner edge representation).
2. Decide and document the `ll_expand(condensed_id)` contract (return leaf summaries, or recurse to messages).
3. Add a `TestCompactSession` assertion that the condensed node links to its leaves (the assertion FEAT-1712 specified but omitted), and a `ll_expand` test over a condensed node.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — `_compact_session_conn()` (~L1122-1139)
- `scripts/little_loops/history_reader.py` — `ll_expand()` and `ll_describe()` docstrings

### Tests
- `scripts/tests/test_session_store.py` — existing `test_compact_session_condensed_node_when_multiple_leaves`, `test_compact_session_creates_spans` (add linkage assertions)
- `scripts/tests/test_history_reader.py` — new: `test_expand_condensed_node_returns_leaves`

### Documentation
- `docs/reference/API.md` — update `ll_expand` / `ll_describe` behavior for condensed nodes

### Configuration
- N/A

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

## Session Log
- `/ll:format-issue` - 2026-06-04T04:26:10 - `1581336d-4181-4074-85b0-16f72458869b.jsonl`
- `/ll:capture-issue` - 2026-06-04T04:15:05Z - `92ad3505-8fca-44b2-aa0f-0ee9ce80d024.jsonl`
