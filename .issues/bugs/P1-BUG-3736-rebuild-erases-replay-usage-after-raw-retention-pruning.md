---
id: BUG-3736
type: BUG
title: Rebuild erases replay usage after raw retention pruning
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T18:19:36Z'
parent: EPIC-3562
labels:
- observability
- history
- usage-retention
testable: true
blocks:
- ENH-3732
relates_to:
- ENH-3731
- ENH-3732
- ENH-3733
- BUG-3735
- BUG-3530
- BUG-3715
---

# BUG-3736: Rebuild erases replay usage after raw retention pruning

## Summary

After retention pruning removes compacted raw transcript rows, both full rebuild and incremental usage catch-up delete their already committed replay-derived usage observations. Retain the recorded consumption and ingest-time qualification when replay evidence is no longer available; pruning must also not erase a usage candidate before successful derivation. This is shared lifecycle correctness for EPIC-3562, separate from reader qualification and individual host adapters.

## Current Behavior

A temporary-database probe on 2026-10-05 used the committed Claude transcript-v2.1.284 fixture, production backfill_raw_events/backfill_usage_incremental and production prune. Marking the fixture's four raw rows compacted and old made them eligible for retention. Two usage observations remained immediately after pruning, then became zero observations after either rebuild or backfill_usage_incremental. Each mode used a separate temporary database; no project history data was changed.

Full rebuild deletes all non-live usage through _REBUILD_TABLE_PREDICATES. Incremental catch-up uses the same broad deletion on a normalizer-version mismatch or when current MAX(raw_events.id) is below the checkpoint. Prune deletes old compacted raw rows without checking their usage derive coverage. These operations can destroy retained usage or remove an underived candidate and the evidence needed to detect its gap. BEGIN IMMEDIATE already protects derivation and checkpoint writes from concurrent writers, and raw_events uses AUTOINCREMENT; neither needs redesign to fix this defect.

## Expected Behavior

Committed replay-derived usage whose latest source evidence has been pruned survives full rebuild, first-enable/version-mismatch/max-below-checkpoint catch-up and repeated calls. Preserve components, provenance, contract, logical identity, run/state/cost attribution and original as-of boundary. Missing raw or originals does not prove a retraction or fresh zero. Replayable records still update under their proved native identity/mutation rules, without duplicating retained observations or replacing a later retained value with an older surviving snapshot.

Before deleting a usage-bearing candidate, pruning proves it is covered by successful, matching-version derivation, or retains the candidate with an explicit reason. A missing/invalid/stale checkpoint cannot certify processing. Known non-usage raw records follow existing retention rules. No source reads, implicit requalification or optional pricing/backfill are needed. Source-loss freshness remains stale/unknown while qualified historical/as-of figures remain retained.

## Motivation

Retained observations are the accounting evidence for historical reports and quality windows. Routine retention followed by automatic replay must not erase that evidence or make a partially derived session appear complete.

## Proposed Solution

Preserve committed usage that can no longer be reconstructed faithfully, reconcile remaining replay by durable logical/source identity, and keep underived usage candidates out of retention deletion. Validate partial-source replay before choosing a deletion predicate; channel alone is insufficient. Keep existing transactions, public interfaces and ingest-time evidence.

## Integration Map

### Files to Modify

- scripts/little_loops/session_store/lifecycle.py — replay replacement and retention eligibility; preserve transactional rollback/checkpoint behavior.
- scripts/little_loops/session_store/writers.py — only if logical-key conflict/update handling must preserve a latest retained observation against older surviving replay.
- scripts/tests/test_session_store_incremental_usage.py and scripts/tests/test_session_store_lifecycle.py — actual production prune/replay, mixed retained/replayable/live rows and pending-candidate retention controls.
- scripts/tests/test_enh3678_rebuild_derive_gate.py — usage-derivation fingerprint/version checks when affected.
- docs/reference/API.md, docs/reference/CLI.md and docs/guides/HISTORY_SESSION_GUIDE.md — usage retention and as-of limits.

### Dependent Files

- history_reader/usage.py and ENH-3732's planned select_session_derive_status — read committed retained observations without inferring complete usage from lost candidates.
- scripts/little_loops/session_store/usage_refresh.py — unchanged-source and source-loss refresh must not bypass the retention policy.
- ENH-3671–3676 — host adapters extend this retained-history baseline before production publication.

### Similar Patterns

BUG-3530 preserved live usage that has no raw replay source. BUG-3715 preserved retention summary nodes after their raw rows were pruned. Both are done; this defect concerns replay-derived usage that becomes non-replayable after pruning.

### Tests

Use temporary databases and production writers/prune/rebuild. Include Claude coalesced snapshots and Codex rollout source-prefix requirements, all/raw-partially-pruned cases, a retained latest observation with an older surviving snapshot, normalizer mismatch, unchanged refresh, failure rollback, and new raw append after pruning. No source files or real project database may be needed for retained-history replay.

## Program Design

### Types

Reuse stored usage observations, source/raw links, logical observation keys and the existing version/checkpoint metadata; no new persisted retention subsystem is assumed.

### Signatures

- `rebuild(db, *, config=None, max_sessions=None) -> dict[str, int]` — retain interface; replace only faithfully replayable usage.
- `backfill_usage_incremental(db) -> int` / `_derive_usage_incremental_conn(conn) -> int` — preserve retained observations during catch-up and checkpoint-reset replay.
- `prune(db, *, config=None, dry_run=False) -> dict` — keep interface, age/size gates and dry-run discipline; retain uncovered usage candidates with a diagnostic.

### Call Path

`backfill_raw_events` → `backfill_usage_incremental` / `_derive_usage_incremental_conn` → committed raw/usage checkpoint → compacted raw retention → `prune` coverage check → `rebuild` or `backfill_usage_incremental` → retained and newly replayed usage → shared source/snapshot/session/quality readers.

### Decision Rules

Keep existing prune/rebuild/backfill_usage_incremental interfaces. Determine replay replacement from durable logical observation/source evidence, not solely channel or a vanished raw pointer. A simple orphan-preservation predicate is acceptable only if partial source replay cannot downgrade or duplicate retained observations. For Codex, preserve required cumulative/prefix evidence or fail closed rather than deriving an invented delta from an incomplete tail. Keep updates, retained observations and checkpoints transactional; use existing AUTOINCREMENT and BEGIN IMMEDIATE guarantees.

## Implementation Steps

1. Add the production prune → full/incremental reproduction and partial-prune controls.
2. Preserve non-replayable committed usage and prevent older/incomplete replay from downgrading it; keep proved replacements and live rows correct.
3. Guard pruning of underived usage candidates and expose a bounded retention/derive diagnostic; preserve ordinary non-usage retention.
4. Drive stored source/snapshot/session-reader and ENH-3732 derive-status compatibility controls, rollback/version gates and docs.
5. Run python -m pytest scripts/tests/.

## Impact

- Priority: P1 — routine replay can erase recorded consumption after pruning.
- Effort: Medium — shared replay replacement, retention gate and regression controls.
- Risk: Medium — partial native sources and legacy rows require conservative preservation rather than an unconditional orphan rule.

## Steps to Reproduce

1. In a temporary directory, copy scripts/tests/fixtures/claude/transcript-v2.1.284.jsonl to session.jsonl. Create two temporary history databases, one for each replay mode.
2. For each database run ensure_db, backfill_raw_events with host claude-code, and backfill_usage_incremental. There are four raw rows and two measured transcript usage observations.
3. Set raw_events.compacted to 1 and raw_events.ts to 2020-01-01T00:00:00Z in the temporary database. Call prune with analytics.retention.raw_event_max_age_days=1, min_project_age_days=0 and min_db_size_mb=0.
4. Confirm raw count is 0 and usage count is still 2. On the first database call rebuild; on the second call backfill_usage_incremental. Both usage counts incorrectly become 0.

## Root Cause

- File: scripts/little_loops/session_store/lifecycle.py
- Anchors: _REBUILD_TABLE_PREDICATES, rebuild, _derive_usage_incremental_conn, prune
- Cause: non-live channel is treated as proof that an observation is still replayable, while retention intentionally removes raw replay evidence. Prune has no matching derive-coverage prerequisite.

## Acceptance Criteria

- [ ] Production prune followed by two full rebuilds or two incremental catch-ups preserves the complete logical usage snapshot when its raw evidence is gone; both ordinary max-below-checkpoint and normalizer-mismatch paths are covered.
- [ ] Mixed live, retained non-replayable and still-replayable rows do not duplicate, disappear or downgrade. Partial pruning cannot replace a retained latest Claude snapshot with an older survivor or invent Codex deltas from an insufficient source prefix.
- [ ] Missing/invalid/version-mismatched or lagging proof cannot permit pruning an underived usage candidate; its raw evidence is retained until successful covered derivation. Non-usage retention and existing dual age/size gates keep their contract.
- [ ] Retained ingest-time qualification, cost and logical/run attribution survive; no source-read, requalification, price recomputation or fresh-zero inference is introduced. New raw appends after pruning cannot reuse IDs or silently disappear below a stale checkpoint.
- [ ] An injected failure before the prune/replay transaction commits rolls back affected usage/raw/checkpoint state; post-commit VACUUM failure does not undo committed retention. Source loss and unchanged refresh retain historical/as-of values with conservative freshness; source/snapshot/session-reader and quality derive-status controls agree.
- [ ] Usage-only derive-version/fingerprint requirements are met without changing unrelated rebuild semantics; docs state the retention exception and python -m pytest scripts/tests/ exits 0.

## Scope Boundaries

- In scope: retained usage and pruning/derive safety across the shared lifecycle.
- Out of scope: requalifying unknown history, repricing stored costs, generic retention of all derived tables, changes to quality population or host metric semantics, and native-source retraction without evidence.

## Related Key Documentation

- docs/ARCHITECTURE.md — raw-to-derived history lifecycle.
- docs/reference/API.md — history rebuild/prune and stored usage contracts.
- docs/reference/CLI.md — user-visible retained/as-of usage.

## Status

**Open** | Created: 2026-10-05 | Priority: P1

## Session Log

- `/ll:capture-issue` - 2026-10-05T18:25:26 - `e0d3fb45-7fc3-4e7a-a2c8-9ad8bfdb517e.jsonl`
- Pre-implementation epic review - 2026-10-05 - Captured after Opus's retention critique (confidence 0.72) and separate production full/incremental temporary-database probes both reduced two committed usage observations to zero after four raw rows were pruned. The current write transaction and AUTOINCREMENT were verified; no checkpoint or ID redesign is requested. No implementation is claimed.
