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
- BUG-3761
- BUG-3766
- BUG-3735
- ENH-3731
- ENH-3732
- ENH-3744
- ENH-3770
testable: true
---

# ENH-3747: Preserve usage search evidence across rebuild for held and retained usage

## Summary

Preserve usage search evidence across rebuild and catch-up for held or retained usage. Split from BUG-3736 as a P3 follow-up: the loss is recoverable and causes no data loss.

## Current Behavior

`rebuild` and the reset path in `_derive_usage_incremental_conn` delete every `search_index` row of kind `usage`, then re-index only what replay re-derives. Retained usage that Stage 1 preserves (held sources) is therefore not searchable after rebuild until the search rows are restored.

## Expected Behavior

Reindex or preserve existing retained and live usage search evidence without duplicates, dangling entries or stale replaced entries. Do not expand search to acquisition channels that were never indexed. Repeated replay is idempotent for search rows.

Restore evidence against surviving committed observations using the existing search key/anchor/preview conventions; a pruned raw pointer is not a valid new anchor. After ENH-3744 releases a hold or replaces a represented observation, old entries must be removed/rebuilt consistently. Keep reindexing in the replay transaction so failed replay cannot publish a half-restored index; retain existing preview sanitization rather than introducing raw source text.

The actual `_write_host_usage_observation` search row uses `ref=model` and `anchor=source_label`, not a usage-row ID. Preserve/reconcile that source/model/time identity, or reconstruct using the existing writer convention; do not join `search_index.ref` to `usage_events.id`. Inspect the separate live and Codex paths to retain the indexed-channel set. A released-hold fixture can exercise replacement without making ENH-3744 a scheduling prerequisite.

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

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — `rebuild` and `_derive_usage_incremental_conn` usage-search deletion/reindex order.
- `scripts/little_loops/session_store/writers.py` — reuse/factor the actual usage search insertion and anchor conventions for retained observations; handle replacements without duplicating search entries.

### Dependent Files

- Existing search reader and schema stay unchanged unless an actual missing reconstruction field requires an append-only migration. Inspect the existing usage-search writer before choosing preservation or reconstruction; preserve the existing indexed-channel set.
- ENH-3744 owns hold release/replacement. Its future transitions are regression controls here, not a hard blocker on restoring Stage 1 search evidence. This issue is independent of canonical numeric publication but remains required for epic closure.
  **Ordering (2026-10-07):** ENH-3744's source-scoped reconciliation stops re-deriving unchanged unheld observations. Verified in `lifecycle._derive_usage_incremental_conn` (the reset path deletes every `kind = 'usage'` search row but only unheld non-live usage rows) and `rebuild` (blanket kind wipe): today only held and live observations lose search entries, but once reconciliation preserves unchanged rows every preserved observation does. Implement this issue before ENH-3744's reconciliation lands (it is unblocked now, BUG-3736 being done) and scope the restoration to *every surviving committed usage observation that replay does not re-derive*, not only held-source and live rows.
- BUG-3761 is done: `scripts/little_loops/session_store/lifecycle.py:1838` re-indexes surviving tools/corrections after the blanket search-kind deletion and suppresses their replay twins; it does not add survivor exclusions to that DELETE. Preserve this restoration when implementing usage search retention, and keep the kinds independent in regression tests. BUG-3766 separately covers live skill telemetry and a subsequent derive-version bump. Neither related bug is a prerequisite or imposes a landing order here; whichever patch lands later must retain earlier preservation logic and update its own derivation fingerprint/version together.

### Tests

- Extend `scripts/tests/test_bug3736_usage_replay_holds.py` and existing session-store search/rebuild tests with retained-only, live, unheld replay, replacement and forced-rollback cases. Exercise the real search reader after replay, not just index row counts.

## Acceptance Criteria

- [ ] After rebuild and incremental reset, retained and live usage search rows for held sources still resolve and have no duplicates. The restoration covers every surviving committed usage observation replay does not re-derive, so ENH-3744's preserved-unheld rows need no second mechanism (test with an unheld Claude/Codex observation that a future reconciliation would preserve rather than re-derive).
- [ ] No dangling entries remain for replaced observations; channels never indexed stay unindexed.
- [ ] Repeated replay leaves the search index unchanged.
- [ ] Search previews/anchors retain existing sanitization and resolve after raw pruning/source loss; hold release/replacement removes stale entries and preserves unrelated live searches. A forced replay failure rolls back index and observation changes together.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Implementation Steps

1. Inspect the existing usage search keys/anchors and indexed channels; preserve surviving evidence or reconstruct it from committed observations.
2. Apply the same transaction-safe restoration in rebuild and incremental reset, then test prune/source loss, idempotence, live preservation and rollback through the reader.
3. Coordinate replacement controls with ENH-3744, without blocking the Stage 1 repair; run the local suite.

## Scope Boundaries

Out of scope: prune/replay preservation, freshness, reader admission.

## Status

**Open** | Created: 2026-10-05 | Priority: P3

## Session Log

- Pre-implementation epic review - 2026-10-07 - Widened restoration scope and fixed ordering: ENH-3744's reconciliation will preserve unchanged unheld observations without re-deriving them, which would widen today's search loss (held + live) to every preserved observation unless this lands first. Verified against the reset and rebuild paths. Opus consult (confidence 0.72) independently flagged the same coupling. No implementation claim.
- Pre-implementation epic review - 2026-10-05 - Temporary-store rebuild retained two usage observations but reduced usage search entries from two to zero. Added concrete index/reader ownership, sanitization, replacement and rollback controls; kept search independent of numeric publication and required for epic closure. No implementation or new score is claimed.
- BUG-3766 pre-implementation review - 2026-10-06 - Corrected the BUG-3761 integration note to the landed blanket-delete/survivor-reindex behavior and removed the obsolete shared-rollout assumption. No usage-search implementation is claimed.
