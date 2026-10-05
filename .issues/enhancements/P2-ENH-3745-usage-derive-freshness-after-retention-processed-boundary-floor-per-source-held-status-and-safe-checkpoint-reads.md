---
id: ENH-3745
type: ENH
title: 'Usage derive freshness after retention: processed-boundary floor, per-source
  held status and safe checkpoint reads'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T20:27:34Z'
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
---

# ENH-3745: Usage derive freshness after retention: processed-boundary floor, per-source held status and safe checkpoint reads

## Summary

Make usage derive freshness accurate after retention: a retained, already-processed boundary must not look pending, a held source must not look complete, and malformed checkpoint metadata must not crash readers. Split from BUG-3736 because these defects cause no data loss once Stage 1 makes the max-below-checkpoint reset non-destructive.

## Current Behavior

Probed 2026-10-05 on temporary stores:

- With an unchanged, available Claude source and all raw pruned, catch-up resets `usage_derive_raw_id` to 0 via `_set_usage_derive_checkpoint`, and `usage_source_freshness` reports `stale/derive_pending`.
- Setting `usage_derive_raw_id` to a malformed string makes `usage_source_freshness` and the selected-session cache-rate reader raise `ValueError` (the `int(...)` in `_derive_usage_incremental_conn` has the same exposure).
- Source refresh can publish a complete cursor boundary for work that was skipped because the source is held.

## Expected Behavior

- Retention of already-processed current-version evidence does not lower a proved processed boundary or create `derive_pending` for an unchanged verifiable source. Neither `sqlite_sequence` nor a retained row proves derivation; missing/invalid/version-changed metadata and genuinely held or new candidates remain unverified/pending.
- Malformed checkpoint metadata yields a bounded unknown/unverified diagnostic in every reader, not an exception.
- A held replay never advances a source's derived boundary, in either source-refresh cursor writer, and never marks skipped candidates fresh because the global checkpoint advanced. Held status is per source: an unrelated completed source can be fresh, and held candidates stay retryable after relevant inputs change. If a cursor is absent, report unknown as-of; never fabricate a boundary from row timestamps.

## Impact

- **Priority**: P2 - follow-up split from BUG-3736 (Stage 1)
- **Effort**: Small-medium - Checkpoint validation plus per-source held status and cursor-writer guards.
- **Risk**: Medium - Cursor semantics feed freshness readers.
- **Breaking Change**: No

## Program Design

### Types

Reuse `meta` keys `usage_derive_version` and `usage_derive_raw_id`, source cursors and the BUG-3736 hold marker; allocation high-water is never processing proof.

### Signatures

- `usage_source_freshness(db, source) -> dict[str, int | str | None]` — keep the interface; validate checkpoint metadata safely and report held status per source.
- `backfill_usage_incremental(db) -> int` — keep the interface; preserve the processed floor when raw is pruned.

### Call Path

`backfill_usage_incremental` → `_set_usage_derive_checkpoint` → `refresh_usage_source` cursor writers → `usage_source_freshness` → selected-session reader.

### Decision Rules

- Malformed, negative, NULL or non-integer proof returns a bounded unknown/unverified diagnostic, never an exception.
- A held replay never advances a source boundary; held status is per source and survives global checkpoint advance.
- An absent cursor reports unknown as-of; never derive a boundary from row timestamps.

## Acceptance Criteria

- [ ] Available unchanged source with current-version proof stays fresh after all/partial raw pruning, catch-up and rebuild; version mismatch, missing/invalid proof and source loss stay stale/unknown.
- [ ] Malformed, negative, NULL or non-integer checkpoint metadata returns a bounded diagnostic from `usage_source_freshness` and the selected-session reader (candidate to ship first as its own small bug).
- [ ] Codex append refresh after pruning and a source held by Stage 1 do not publish a new complete cursor boundary; unchanged source re-ingestion preserves the historical boundary.
- [ ] Mixed-source store: the held source stays diagnosed and retryable while an unrelated completed source is fresh; a later native append or context recovery derives the held candidates below an advanced global checkpoint.
- [ ] Allocation high-water and old-version proof never certify processing.

## Scope Boundaries

Out of scope: prune eligibility and replacement proof (BUG-3736, usage-proof sibling), reader admission, search.

## Status

**Open** | Created: 2026-10-05 | Priority: P2
