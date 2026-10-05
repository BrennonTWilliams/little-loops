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
- ENH-3732
- ENH-3744
- ENH-3746
testable: true
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

Reuse/factor `_valid_usage_checkpoint` for a single current-version, non-negative integer validation rule in pruning, catch-up, freshness and ENH-3732's read-only proof. Missing is distinct from a proved zero. Retain an already proved processing floor only across retention under the same derive version; changing the version or losing proof cannot stamp old retained observations as processed by the new normalizer.

### Signatures

- `usage_source_freshness(db, source) -> dict[str, int | str | None]` — keep the interface; validate checkpoint metadata safely and report held status per source.
- `backfill_usage_incremental(db) -> int` — keep the interface; preserve the processed floor when raw is pruned.

### Call Path

`backfill_usage_incremental` → `_set_usage_derive_checkpoint` → `refresh_usage_source` cursor writers → `usage_source_freshness` → selected-session reader.

### Decision Rules

- Malformed, negative, NULL or non-integer proof returns a bounded unknown/unverified diagnostic, never an exception.
- A held replay never advances a source boundary; held status is per source and survives global checkpoint advance.
- An absent cursor reports unknown as-of; never derive a boundary from row timestamps.
- Reader validation fails closed. Writers with invalid/missing/version-changed metadata either perform a successful protected replay of safely replayable evidence or report a bounded incomplete/failure result while retaining rows and holds; never silently coerce invalid proof to zero and publish a fresh boundary.
- ENH-3744 owns semantic proof, hold lifting and replay/retry of held candidates below the global checkpoint. This issue owns validated processing floors and source-local cursor publication from the resulting completion/held outcome. A global floor may cover other sources but cannot certify skipped work. Keep coordination as a delivery-stage integration contract, not a circular dependency; checkpoint-validation work can proceed immediately.
- Use existing `usage_source_cursors.derived_raw_event_id`/`status` for tracked source completion and `meta` for the same-version proved global floor. Define one bounded source-local completion/held result consumed by both cursor writers. Untracked sources remain unknown as-of; no new cursor is fabricated. If durable source-version or pending-state evidence cannot fit the existing metadata safely, this issue owns the single next append-only migration and its shared write/read interface; ENH-3744 must not independently add competing boundary storage. A source's surviving raw maximum and allocation sequence alone are never successful-derive proof.
- Factor a pure retained-state completion predicate from the stat-based `usage_source_freshness` logic for ENH-3732. It reads validated committed progress and actual outstanding held/candidate proof, never source files. Quality's retained-as-of rows do not require a source cursor and are not rejected solely because a conservation hold exists; actual unrepresented or unprovable in-scope work remains unavailable.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — `_valid_usage_checkpoint`, `_set_usage_derive_checkpoint`, `_derive_usage_incremental_conn`, `_refresh_codex_usage_source`, `refresh_usage_source`, `usage_source_freshness` and rebuild checkpoint stamping. Both Claude and Codex cursor writers need a source-local success/held result.
- `scripts/little_loops/session_store/usage_refresh.py` — preserve the meaning of checkpoint invalidation after parser changes; do not let a successful source read certify skipped derivation.

### Dependent Files

- `scripts/little_loops/session_store/writers.py` — ENH-3744's semantic representation/hold disposition.
- `scripts/little_loops/cli/ctx_stats.py` and `history_reader/usage.py` — consume bounded diagnostics; ENH-3746 separately fixes ingestion admission and ENH-3732 session derive completeness.

### Tests

- Extend `scripts/tests/test_session_store_incremental_usage.py`, `test_session_store_usage_refresh.py`, `test_enh3549_codex_usage_refresh.py` and `test_bug3736_usage_replay_holds.py` with prune/catch-up/rebuild floors, invalid proof and held-versus-unrelated-source cases.
- Drive freshness and stored-cache-rate text/JSON through malformed checkpoint values, not just the validator. Source loss retains the last as-of figure with stale/unknown freshness; it never becomes a fresh zero. Test parser-version invalidation separately from raw retention.

## Acceptance Criteria

- [ ] Available unchanged source with current-version proof stays fresh after all/partial raw pruning, catch-up and rebuild; version mismatch, missing/invalid proof and source loss stay stale/unknown.
- [ ] Malformed, negative, NULL or non-integer checkpoint metadata returns a bounded diagnostic from `usage_source_freshness` and the selected-session reader (candidate to ship first as its own small bug).
- [ ] Codex append refresh after pruning and a source held by Stage 1 do not publish a new complete cursor boundary; unchanged source re-ingestion preserves the historical boundary.
- [ ] Mixed-source store: the held source stays diagnosed and retryable while an unrelated completed source is fresh; a later native append or context recovery derives the held candidates below an advanced global checkpoint.
- [ ] Allocation high-water and old-version proof never certify processing.
- [ ] Invalid proof in catch-up/rebuild causes a protected recovery or bounded incomplete/failure result with retained observations/holds intact; it cannot certify skipped candidates. Forced derive failure cannot advance global/source-local proof or release holds.
- [ ] ENH-3744's representation/held result governs source-local completion; context recovery revisits older pending IDs. Quality's read-only proof can distinguish held/pending candidates from legitimately retained as-of usage after the global floor advances.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Implementation Steps

1. Share checkpoint validation and prove bounded reader behavior for malformed, negative, missing and version-mismatched metadata.
2. Preserve only a justified same-version processed floor across retention; protect replay on invalid/version-changed proof.
3. Guard both source cursor writers with source-local completion, integrating ENH-3744's held/pending outcomes and retrying work below the floor after recovery.
4. Run real Claude/Codex prune/freshness/reader and mixed-source rollback/recovery tests, then the local suite.

## Scope Boundaries

Out of scope: prune eligibility, replacement proof and held-candidate retry (BUG-3736/ENH-3744), reader admission, search.

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Session Log

- Pre-implementation epic review - 2026-10-05 - Reproduced unchanged-source `stale/derive_pending` after all four raw rows were pruned and catch-up ran, plus `ValueError` on malformed checkpoint metadata. Added shared validation, protected writer recovery, both cursor writers and the ENH-3744/3732 per-source handoff; no implementation or new score is claimed.
