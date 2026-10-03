---
id: BUG-3715
type: BUG
title: rebuild() unconditionally wipes summary_nodes including irreplaceable retention
  summaries
priority: P3
status: open
relates_to:
- ENH-3698
- ENH-3666
- ENH-3678
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:46:14Z'
---

# BUG-3715: rebuild() unconditionally wipes summary_nodes including irreplaceable retention summaries

## Summary

`rebuild()` (`little_loops.session_store.lifecycle`) wipes every table in `_REBUILD_TABLES` with an unconditional `DELETE`; only `usage_events` has a row predicate in `_REBUILD_TABLE_PREDICATES`. `summary_nodes` (and `summary_spans`) are therefore fully deleted, including `kind='retention'` rows written by `compact()` whose source `raw_events` rows `prune()` already deleted. Those rows cannot be re-derived, so any rebuild on a pruned store silently loses them. Derived rows for pruned periods are likewise deleted and never replayed.

## Current Behavior

- Any rebuild (SessionStart auto-rebuild after a `REBUILD_DERIVE_VERSION` bump, or manual `ll-session rebuild`) deletes all `summary_nodes`/`summary_spans`, including irreplaceable `kind='retention'` summaries.
- The hook worker passes `config=None`: summaries are wiped and never regenerated.
- `ll-session rebuild` loads the project config, so with `history.compaction.enabled` it re-summarizes every session via blocking host-LLM calls inside the single `BEGIN IMMEDIATE` transaction (lock hold scales with LLM latency x sessions; one failure rolls everything back). The two paths produce different results.

## Expected Behavior

- `rebuild()` preserves `kind='retention'` summary rows (and their spans, handled consistently) whose source `raw_events` were pruned; only re-derivable kinds are wiped and replayed.
- Hook and manual rebuild paths agree on what happens to summaries, and LLM summarization does not run inside the write transaction (or the divergence is explicitly documented).

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Add a predicate to `_REBUILD_TABLE_PREDICATES` excluding `kind='retention'` from the `summary_nodes` wipe, with `summary_spans` handled consistently; add tests for a pruned+compacted store surviving `rebuild()`.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P3 - latent: no derive bump has landed yet, but it is a hard precondition on any `REBUILD_DERIVE_VERSION` bump (data loss on pruned stores)
- **Effort**: Small-Medium
- **Risk**: Low-Medium

## Steps to Reproduce

1. Build a store with `raw_events`, run `compact(and_prune=True)` so `kind='retention'` rows exist and the source rows are pruned.
2. Run `rebuild(db)`.
3. Observe the `kind='retention'` rows are gone and cannot be recovered.

## Related

ENH-3698 (size gate; its review surfaced this), ENH-3666 (restructuring `rebuild()`), ENH-3678.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-03 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-10-03T17:46:28 - `32f52444-a659-4ef8-933a-2361ae6c6aff.jsonl`
