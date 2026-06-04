---
id: ENH-1927
title: Recursive cross-session condensation for a project-root summary
type: ENH
priority: P3
status: open
captured_at: "2026-06-04T04:15:05Z"
discovered_date: "2026-06-04"
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
- `scripts/little_loops/session_store.py` — `_compact_sessions()` and `_compact_session_conn()` (cross-session condensation pass, dedup index revision)
- `scripts/little_loops/session_store.py` — `summary_nodes` table schema (add `level`/`depth` column, revise `idx_summary_nodes_condensed_dedup`)
- `scripts/little_loops/history.py` — DAG traversal entry point (start from root, descend)

### Dependent Files (Callers/Importers)
- TBD — use grep to find references: `grep -r "_compact_sessions\|_compact_session_conn\|summary_nodes" scripts/`

### Similar Patterns
- TBD — search for consistency: `grep -r "condensed\|compaction\|summary" scripts/`

### Tests
- `scripts/tests/test_session_store.py` — add idempotency tests for cross-session condensation
- `scripts/tests/test_history.py` — add root-to-leaf traversal tests

### Documentation
- `docs/reference/API.md` — update session store section with new schema and condensation behavior
- `docs/ARCHITECTURE.md` — update DAG structure description

### Configuration
- N/A

## Implementation Steps

1. After per-session condensed nodes exist, add a cross-session condensation pass (likely in `_compact_sessions()`, which already iterates all sessions) that groups condensed nodes by token budget and emits higher-order `condensed` nodes, recursing until a single root remains.
2. Extend the dedup strategy: `idx_summary_nodes_condensed_dedup` is `UNIQUE(session_id) WHERE kind='condensed'`, which assumes one condensed node per session — cross-session/root nodes have `session_id = NULL` and need a different idempotency key (e.g. a content hash or a level column + covered-id set).
3. Consider adding a `level` (or `depth`) column to `summary_nodes` so traversal/rendering can distinguish leaf < session-condensed < higher-order < root.
4. Update `ll-history` DAG traversal to start from the root and descend.

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

## Status

open

## Session Log
- `/ll:format-issue` - 2026-06-04T04:27:34 - `950150ed-ad92-423e-bdeb-698213762597.jsonl`
- `/ll:capture-issue` - 2026-06-04T04:15:05Z - `92ad3505-8fca-44b2-aa0f-0ee9ce80d024.jsonl`
