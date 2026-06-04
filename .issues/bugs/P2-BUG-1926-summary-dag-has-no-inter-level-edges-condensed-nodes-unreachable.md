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
- `/ll:capture-issue` - 2026-06-04T04:15:05Z - `92ad3505-8fca-44b2-aa0f-0ee9ce80d024.jsonl`
