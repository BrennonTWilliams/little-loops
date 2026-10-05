---
id: ENH-3747
type: ENH
title: Preserve usage search evidence across rebuild for held and retained usage
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T20:27:35Z'
parent: EPIC-3562
labels:
- observability
- history
- usage-retention
blocked_by:
- BUG-3736
relates_to:
- BUG-3735
- ENH-3731
- ENH-3732
---

# ENH-3747: Preserve usage search evidence across rebuild for held and retained usage

## Summary

Preserve usage search evidence across rebuild and catch-up for held or retained usage. Split from BUG-3736 as a P3 follow-up: the loss is recoverable and causes no data loss.

## Current Behavior

`rebuild` and the reset path in `_derive_usage_incremental_conn` delete every `search_index` row of kind `usage`, then re-index only what replay re-derives. Retained usage that Stage 1 preserves (held sources) is therefore not searchable after rebuild until the search rows are restored.

## Expected Behavior

Reindex or preserve existing retained and live usage search evidence without duplicates, dangling entries or stale replaced entries. Do not expand search to acquisition channels that were never indexed. Repeated replay is idempotent for search rows.

## Impact

- **Priority**: P3 - follow-up split from BUG-3736 (Stage 1)
- **Effort**: Small - Search reindex/preserve for held usage.
- **Risk**: Low - Recoverable, no data loss.
- **Breaking Change**: No

## Program Design

### Types

Reuse `search_index` rows of kind `usage` and the BUG-3736 hold marker.

### Signatures

- `rebuild(db, *, config=None, max_sessions=None) -> dict[str, int]` — keep the interface; keep retained and live usage search rows for held sources.

### Call Path

`rebuild` → usage search wipe and reindex → `backfill_usage_incremental` reset path → search readers.

### Decision Rules

- Reindex or preserve without duplicates, dangling entries or stale replaced entries; never index channels that were not indexed before.

## Acceptance Criteria

- [ ] After rebuild and incremental reset, retained and live usage search rows for held sources still resolve and have no duplicates.
- [ ] No dangling entries remain for replaced observations; channels never indexed stay unindexed.
- [ ] Repeated replay leaves the search index unchanged.

## Scope Boundaries

Out of scope: prune/replay preservation, freshness, reader admission.

## Status

**Open** | Created: 2026-10-05 | Priority: P3
