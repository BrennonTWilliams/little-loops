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

Restore usage search evidence for surviving observations across rebuild and source catch-up, including evidence already missing after an earlier rebuild. Split from BUG-3736 as a P3 follow-up: numeric observations survive, but their historical search evidence disappears. ENH-3770's guarded reconciliation depends on this repair covering every preserved observation from an already indexed producer path.

## Current Behavior

`rebuild` deletes every `search_index` row of kind `usage`, then replay re-indexes only observations inserted by `_write_host_usage_observation`. Stage 1 preserves held transcript observations, so a rebuild loses their search evidence. ENH-3745 changed established missing/invalid/version-mismatched checkpoints to skip untouched: there is no longer an incremental reset that wipes the whole usage search kind. The actual incremental mutation seam is `_derive_usage_incremental_disposition`'s Codex-source catch-up, which deletes usage search entries by source anchor before source replay.

The indexed producer population is also narrower than the old prose implied. `_write_host_usage_observation` indexes transcript observations, including unknown other-host audit observations, using model/source/timestamp. The live `record_usage_event` writer and Codex rollout insertion do not index usage. Claude same-key updates return without updating their original search entry, so model/timestamp replacement can leave stale evidence. Production observations retain model, timestamp and source attribution after raw pruning, allowing repair without reading the original or requiring an old search row to survive.

## Expected Behavior

Reconstruct search evidence from surviving committed observations belonging to the existing indexed transcript producer population, even when prior rebuilds already removed all usage search rows. Preservation of existing index rows alone is insufficient. Do not begin indexing ordinary live or rollout observations. Repeated replay is idempotent for the complete usage-search population.

Restore evidence against surviving committed observations using the existing search key/anchor/preview conventions; a pruned raw pointer is not a valid new anchor. ENH-3770 owns guarded reconciliation, hold release and protected replacement; its preserved rows must retain search without requiring another replay insertion. Reconcile same-ID model/timestamp updates as well as delete/replace transitions, removing stale entries while preserving unrelated searches. Keep restoration in the replay transaction so failed replay cannot publish a half-restored index. Reuse stored sanitized fields and the writer's preview convention rather than introducing raw source text.

The actual `_write_host_usage_observation` search row uses `content=f"{model or ''} usage"`, `ref=str(model or "")`, `anchor=source_label` and the observation timestamp, not a usage-row ID. Reconstruct/reconcile those arguments from the committed row; do not join `search_index.ref` to `usage_events.id` or infer request identity from equal search tuples. Distinct observations can share model/source/timestamp: retain their existing per-observation multiplicity while preventing replay-created twins. A historical source-path anchor remains historical when the file is gone; search must work without opening it, and must not claim that the original file still resolves. Replacement fixtures require no ENH-3770 implementation or scheduling prerequisite.

## Impact

- **Priority**: P3 - follow-up split from BUG-3736 (Stage 1)
- **Effort**: Small to medium - Scoped survivor reconstruction and stale-update controls.
- **Risk**: Low - Recoverable, no data loss.
- **Breaking Change**: No

## Program Design

### Types

Reuse committed `usage_events`, `search_index` rows of kind `usage`, logical channel classification and existing transcript writer search arguments. Holds determine preservation, not which producer channels are searchable.

### Signatures

- `rebuild(db, *, config=None, max_sessions=None) -> dict[str, int]` — keep the interface and restore indexed survivor evidence inside the existing transaction.
- `_derive_usage_incremental_disposition(conn)` / `_derive_usage_incremental_conn(conn)` — preserve the landed disposition/count contracts; reconcile affected usage-search evidence without reviving destructive checkpoint reset.

### Call Path

`rebuild` or source catch-up → usage replay and survivor restoration through the shared usage seam → committed search → existing `history_reader.search` / `session_store.search` readers. Same-key transcript updates use the same search reconciliation convention.

### Decision Rules

- Restore missing index rows from committed observations without stat/parsing/pricing or changing observations/holds; retain logical NULL transcript channel compatibility only where stored source/model/time supplies the existing writer arguments.
- Reconcile current observation state, including same-ID model/timestamp updates; remove obsolete indexed evidence without deleting another observation's matching search tuple or an unrelated source's entries.
- The indexed population is `row_channel(row) == "transcript"` with the stored source attribution required to reconstruct the writer's anchor; use the shared logical mapping for supported NULL channels. Keep eligibility independent of numeric qualification: unknown transcript audit rows were already indexed; ordinary live and Codex rollout rows were not. Missing stored source attribution cannot justify inventing an anchor or a new indexed channel.
- Equal model/source/timestamp search tuples are not a unique observation key. Use affected-scope transactional restoration/reconciliation that reproduces fresh writer arguments and multiplicity; no synthetic unique upsert or inefficient whole-index regeneration is required. Future reconciliation reuses the same seam.
- Preserve the non-usage rebuild fingerprint and `REBUILD_DERIVE_VERSION`; isolate usage-only restoration in the usage derivation seam. This repair must not bump `_USAGE_DERIVE_VERSION` merely to force checkpoint replay: ENH-3770 owns any justified usage-version change.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — `rebuild` and `_derive_usage_incremental_disposition` source-catch-up deletion/restoration order, using the shared usage seam and preserving established checkpoint skips.
- `scripts/little_loops/session_store/writers.py` — factor/reuse the actual transcript usage search arguments, reconstruct missing survivor evidence and reconcile same-ID updates without duplicating search entries or pricing observations.

### Dependent Files

- Existing search reader and schema stay unchanged unless an actual missing reconstruction field requires an append-only migration. Inspect the existing usage-search writer before choosing preservation or reconstruction; preserve the existing indexed-channel set.
- ENH-3744's proof/prune veto and ENH-3745's checkpoint/source-state are done. ENH-3770 owns guarded reconciliation and hold release/replacement; it remains blocked on this issue. Implement this restoration first for *every surviving committed observation from an indexed producer path that replay does not re-derive*, including future preserved unheld transcript rows. Current Codex/live channels stay unindexed. ENH-3770's implementation is a regression scenario, not a prerequisite here. This issue independently gates epic closure.
- BUG-3761 and BUG-3766 are done: `lifecycle.rebuild` restores surviving tools/corrections and `_reindex_skill_survivors` restores surviving skills after the blanket search-kind deletion, suppressing their replay twins. Keep all three mechanisms and kinds independent. `REBUILD_DERIVE_VERSION` is already `bug3766-v1`; usage restoration must retain the non-usage fingerprint checked by `scripts/tests/test_enh3678_rebuild_derive_gate.py`, rather than claiming a new generic rebuild-version bump.

### Tests

- Extend `scripts/tests/test_bug3736_usage_replay_holds.py`, `test_history_reader_search.py` and existing session-store search/rebuild controls with retained transcript survivors, unknown transcript audit rows, legacy logical NULL transcript rows with reconstructible attribution, future preserved unheld transcript rows, and live/rollout negative indexing controls. Explicitly delete the original usage search rows before repair to prove reconstruction, then remove/prune the original raw/source and verify real search readers still return the expected stored preview and historical anchor.
- Drive same-ID Claude model/timestamp updates and replacement/deletion fixtures, repeated rebuild/catch-up and equal search tuples for distinct observations. Compare freshly indexed and restored `(content, kind, ref, anchor, ts)` rows including multiplicity; assert stale searches disappear, unrelated searches survive, no observation/cost/hold changes occur merely for reindexing, and an injected failure rolls search and replay changes back together. Invalid-checkpoint incremental skips leave observations and search byte-for-byte unchanged. Run tool/correction/skill preservation controls and the unchanged non-usage fingerprint gate.

## Acceptance Criteria

- [ ] Rebuild and relevant source catch-up restore search evidence from surviving indexed transcript observations even when all prior usage search rows are absent; held and future preserved-unheld controls pass without raw/original-file access. Existing invalid/missing/version-mismatched checkpoint skips remain non-destructive.
- [ ] Unknown transcript audit and supported logical NULL transcript survivors retain search; ordinary live/rollout observations remain unindexed. Missing stored source attribution never creates a guessed anchor.
- [ ] Same-ID model/timestamp updates and deletion/replacement remove obsolete search entries while preserving unrelated observations and searches; equal source/model/time tuples for distinct observations retain stable per-observation multiplicity.
- [ ] Repeated rebuild/catch-up leaves the usage-search population unchanged, and reconstruction alone performs no observation/cost/hold mutation or pricing.
- [ ] Real search readers return existing stored preview/ref/timestamp/historical-source anchors after pruning/source loss. A forced replay failure rolls back index and observation changes together; tool/correction/skill preservation controls and the unchanged `test_enh3678_rebuild_derive_gate.py` fingerprint gate pass.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Implementation Steps

1. Factor the transcript writer's actual search arguments and indexed-population policy; reconstruct survivor evidence from committed observations, including previously missing index rows and supported logical NULL channels.
2. Apply transaction-safe restoration in rebuild/source catch-up and same-ID updates through the usage seam, then test pruning/source loss, stable multiplicity, stale replacements, unindexed channels and rollback through both readers.
3. Preserve the landed tool/correction/skill restoration and non-usage fingerprint. Verify ENH-3770's future preserved-unheld scenario without depending on its implementation; run the local suite.

## Scope Boundaries

Out of scope: prune/replay preservation, freshness, reader admission.

## Status

**Open** | Created: 2026-10-05 | Priority: P3

## Session Log

- Pre-implementation unblocked-child review - 2026-10-07 - Corrected the landed ENH-3745 checkpoint/catch-up baseline and ENH-3770 ownership. Verified only the transcript host writer indexes usage; live and Codex rollout writers do not. Required reconstruction when earlier rebuilds already removed search rows, same-ID model/timestamp reconciliation, stable equal-tuple multiplicity, historical anchors without source access and non-usage fingerprint preservation. No implementation or readiness score claimed.
- Pre-implementation epic review - 2026-10-07 - Widened restoration scope and fixed ordering: ENH-3744's reconciliation will preserve unchanged unheld observations without re-deriving them, which would widen today's search loss (held + live) to every preserved observation unless this lands first. Verified against the reset and rebuild paths. Opus consult (confidence 0.72) independently flagged the same coupling. No implementation claim.
- Pre-implementation epic review - 2026-10-05 - Temporary-store rebuild retained two usage observations but reduced usage search entries from two to zero. Added concrete index/reader ownership, sanitization, replacement and rollback controls; kept search independent of numeric publication and required for epic closure. No implementation or new score is claimed.
- BUG-3766 pre-implementation review - 2026-10-06 - Corrected the BUG-3761 integration note to the landed blanket-delete/survivor-reindex behavior and removed the obsolete shared-rollout assumption. No usage-search implementation is claimed.
