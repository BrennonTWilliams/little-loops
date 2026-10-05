---
id: ENH-3744
type: ENH
title: Semantic usage-candidate proof, derive-gap retention and held-source derivation
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T20:27:33Z'
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

# ENH-3744: Semantic usage-candidate proof, derive-gap retention and held-source derivation

## Summary

Replace BUG-3736's conservative whole-source usage holdback with semantic proof where proof exists, and let held sources derive new appends again. Stage 1 (BUG-3736) stops the data loss by holding any source whose raw rows cannot all be safely pruned and by guarding every destructive replay path; this child makes that hold precise and releasable.

## Current Behavior

After BUG-3736, prune treats "checkpoint at or above the source's max raw ID" as derivation proof and holds a whole source when any of its rows is ineligible. A recognized usage candidate with no committed representation is not detected, and a held source that keeps appending derives nothing new until its hold is lifted.

## Expected Behavior

- Prune proof requires a committed observation or a proved native coalesced/dedup representation for each recognized usage candidate, using shared native normalization rather than a payload-key heuristic. Unproved candidates are retained with `usage_derive_gap`. Safely derived unknown/partial audit observations satisfy the proof without canonical qualification.
- Terminal non-candidates under the current normalizer (malformed/partial/all-zero Claude snapshots with a native message ID; Codex rate-limit-only notifications) need no fabricated usage row and no indefinite holdback. Unsupported usage-bearing evidence still fails closed.
- Replacement can be per record where proved: replayable records update under native identity/mutation rules; a later retained value is never replaced by an older surviving snapshot; native positions compare only within a proved compatible source (raw IDs and path aliases prove nothing).
- Codex supporting context (header/thread, model/turn/closed-span, adjacent-notification) is retained or the source stays held; a surviving request pointer does not prove it. Document the availability/storage tradeoff.
- A hold marker is lifted only by this proof; new appends to a held source derive without duplicating retained consumption. Legacy observations lacking source links or observation keys stay held conservatively (no value/timestamp matching).

## Impact

- **Priority**: P2 - follow-up split from BUG-3736 (Stage 1)
- **Effort**: Medium-large - Per-record proof needs native normalization sharing and Codex context handling.
- **Risk**: Medium-high - Wrong proof could duplicate or drop retained usage.
- **Breaking Change**: No

## Program Design

### Types

Reuse stored usage observations, source/raw links, logical observation keys and the BUG-3736 hold marker; no new persisted subsystem.

### Signatures

- `prune(db, *, config=None, dry_run=False) -> dict` — keep the interface; replace whole-source hold with candidate proof, adding the `usage_derive_gap` reason.
- `backfill_usage_incremental(db) -> int` — keep the interface; derive appends to held sources and lift holds only under proof.

### Call Path

`backfill_raw_events` → `backfill_usage_incremental` → `prune` candidate proof → hold lift → `rebuild` → retained usage readers.

### Decision Rules

- Share native normalization (recognition, intentional no-observation, coalescing) with the proof; never use a payload-key heuristic.
- Unsupported usage-bearing evidence fails closed; legacy unlinked usage stays held.
- Compare native positions only within a proved compatible source; raw IDs and path aliases prove nothing.

## Acceptance Criteria

- [ ] A recognized candidate without committed or proved-coalesced representation keeps its raw rows and reports `usage_derive_gap`; a current checkpoint alone does not hide it.
- [ ] Ignored malformed/partial/zero Claude snapshots (with and without a prior valid snapshot) and Codex rate-limit-only notifications are not held and produce no usage row; unsupported candidate evidence stays held.
- [ ] Claude latest snapshot pruned with an older survivor, and re-ingested older source positions with larger raw IDs, never roll back, duplicate or reprice the retained observation; repeated unchanged replay is idempotent and proved newer snapshots still update.
- [ ] Codex usage raw surviving with header/model/turn/closure context lost never downgrades a retained measured request or duplicates it.
- [ ] Appends to a held source derive after the hold is lifted or the context is retained, without double counting retained rows.

## Scope Boundaries

Out of scope: freshness/cursor semantics (see the freshness sibling), reader admission, search reindex, requalifying unknown history, repricing stored costs.

## Status

**Open** | Created: 2026-10-05 | Priority: P2
