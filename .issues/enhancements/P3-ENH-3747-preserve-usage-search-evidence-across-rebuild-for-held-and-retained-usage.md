---
id: ENH-3747
type: ENH
title: Preserve usage search evidence across rebuild for held and retained usage
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T20:27:35Z'
completed_at: '2026-10-08T20:47:01Z'
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
confidence_score: 95
outcome_confidence: 78
score_complexity: 17
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
risk_factors:
- id: reconciliation-batch-bound-unspecified
  domain: outcome
  criterion: ambiguity
  description: Bounded-batch size and old-anchor capture mechanics for same-ID updates
    are left to implementation
- id: survivor-reindex-sibling-exists
  domain: readiness
  criterion: duplicate_implementations
  description: Tool/correction/skill survivor reindex already exists in rebuild; usage
    reconciler must stay independent, not duplicate it
- id: transaction-final-reconciler-depth
  domain: outcome
  criterion: complexity
  description: Shared old/new-anchor reconciler across rebuild, catch-up and same-ID
    updates carries cross-function transactional state
- id: usage-write-seam-fanout
  domain: outcome
  criterion: change_surface
  description: Shared usage write/replay seam has several callers (writer, backfill,
    rebuild, incremental derive) plus future ENH-3770 reuse
---

# ENH-3747: Preserve usage search evidence across rebuild for held and retained usage

## Summary

Restore usage search evidence for surviving observations across rebuild and source catch-up, including evidence already missing after an earlier rebuild. Split from BUG-3736 as a P3 follow-up: numeric observations survive, but their historical search evidence disappears. ENH-3770's guarded reconciliation depends on this repair covering every preserved observation from an already indexed producer path.

## Current Behavior

`rebuild` deletes every `search_index` row of kind `usage`, then replay re-indexes only observations inserted by `_write_host_usage_observation`. Stage 1 preserves held transcript observations, so a rebuild loses their search evidence. ENH-3745 changed established missing/invalid/version-mismatched checkpoints to skip untouched: there is no longer an incremental reset that wipes the whole usage search kind. The actual incremental mutation seam is `_derive_usage_incremental_disposition`'s Codex-source catch-up, which deletes usage search entries by source anchor before source replay.

The indexed producer population is also narrower than the old prose implied. `_write_host_usage_observation` indexes transcript observations, including unknown other-host audit observations, using model/source/timestamp. The live `record_usage_event` writer and Codex rollout insertion do not index usage. Claude same-key updates return without updating their original search entry, so source/model/timestamp replacement can leave stale evidence. Source catch-up deletes only rollout observations but every usage search at that anchor, including a surviving transcript observation's evidence. Production observations retain model, timestamp and source attribution after raw pruning, allowing repair without reading the original or requiring an old search row to survive; legacy rows without stored source attribution cannot supply an anchor.

The fresh writer renders the Python model before SQLite applies `TEXT` affinity. Unknown audit rows accept non-string models: `False` or `0` stores as `"0"` while its original search ref is empty; `True` stores as `"1"` while its original ref is `"True"`; floating-point formatting can also change. Exact reconstruction of that pre-storage rendering is impossible after raw/index loss. `_index` inserts its arguments directly; it does not sanitize or resolve anchors. `search_index.anchor` and `ref` are FTS5 `UNINDEXED` columns, so repeated source-wide reconciliation per observation would repeatedly scan/recreate the same population.

## Expected Behavior

Rebuild regenerates the entire indexed transcript search population from final committed observations after replay, even when prior rebuilds already removed all usage search rows. Discard any inline replay entries before that final regeneration; distinguishing replayed rows from survivors is unnecessary. Successful incremental replay/catch-up reconciles its affected source scopes, including held-source append skips and scopes whose observation insert count is zero. Preservation of existing index rows alone is insufficient. Valid no-new-raw/retention-lowered-max catch-up and unusable-checkpoint skips remain untouched; explicit rebuild repairs missing historical evidence outside touched scopes. Do not begin indexing ordinary live or rollout observations. Repeated replay is idempotent for the complete usage-search population.

Restore evidence against surviving committed observations using the existing search key/anchor/preview conventions; a pruned raw pointer is not a valid new anchor. ENH-3770 owns guarded reconciliation, hold release, protected replacement and parser-refresh integration; its preserved rows must retain search without requiring another replay insertion. Reconcile permitted same-ID source/model/timestamp updates as well as delete/replace transitions, removing stale entries while preserving unrelated searches. Capture old and new source scopes before mutation, then reconcile from final committed rows in the same transaction. Reuse stored fields and the writer's preview convention rather than introducing raw source text or another sanitization pass.

Use one renderer for fresh, updated and restored search: `content=f"{stored_model or ''} usage"`, `ref=str(stored_model or "")`, `anchor=stored_source_path` and the stored timestamp, read back from SQLite by the actual observation ID. `str(original_model)` before insertion is insufficient. Normal string/NULL model behavior is unchanged. Apply the same committed-value rule to every eligible row; a stored `"0"` cannot distinguish an original numeric/boolean model from the literal model string. This deliberately changes former non-string audit rendering on fresh writes or affected-scope repair, while untouched legacy search stays unchanged until its scope or rebuild is repaired. Do not preserve unrecoverable pre-storage distinctions by inventing metadata or altering usage observations. List/dict model bind failures are outside this repair. Empty model/timestamp values supported by the writer remain searchable; only missing/empty source attribution prevents reconstruction. There is no usage-row ID in the search ref: do not join it to `usage_events.id` or infer request identity from equal search tuples. Distinct observations, including sanitizer-induced collisions, retain one search entry each while replay creates no twins. A historical source-path anchor remains historical when the file is gone; existing search readers need no file resolution or redesign. Replacement fixtures require no ENH-3770 implementation or scheduling prerequisite.

## Impact

- **Priority**: P3 - follow-up split from BUG-3736 (Stage 1)
- **Effort**: Medium - Batched survivor reconstruction, canonical rendering and stale-update controls.
- **Risk**: Medium - Collateral search deletion or duplicate evidence is possible if scope/multiplicity is wrong; numeric usage remains outside this repair.
- **Breaking Change**: No

## Program Design

### Types

Reuse committed `usage_events`, `search_index` rows of kind `usage`, logical channel classification and transcript writer preview conventions. Holds determine preservation, not which producer channels are searchable. An affected-source collection records old and new stored anchors; full-population mode is reserved for rebuild.

### Signatures

- `rebuild(db, *, config=None, max_sessions=None) -> dict[str, int]` — keep the interface and restore indexed survivor evidence inside the existing transaction.
- `_derive_usage_incremental_disposition(conn)` / `_derive_usage_incremental_conn(conn)` — preserve the landed disposition/count contracts; reconcile affected usage-search evidence without reviving destructive checkpoint reset.
- A private committed-row renderer returns the existing `(content, kind, ref, anchor, ts)` tuple or no entry for an ineligible/unattributed observation. A shared transaction-local reconciler accepts either an explicit old/new source-scope collection or rebuild's full-population mode; search repair has no observation-insert count or checkpoint-publication effect.

### Call Path

`rebuild` or successful affected-source catch-up → accumulate affected old/new anchors → usage replay → final committed-row search reconciliation through the shared usage seam → existing `history_reader.search` / `session_store.search` readers. Fresh inserts read back persisted values for rendering; same-key updates join the batch. ENH-3770 reuses this seam within each observation-mutation transaction, including parser refresh's separately committed acquisition phase.

### Decision Rules

- Restore missing index rows from committed observations without stat/parsing/pricing or changing observations/holds. Search repair must not manufacture derive progress, source completion, freshness or changed insert counts.
- Reconcile current observation state, including same-ID source/model/timestamp updates. Capture both old and new source anchors before writing; replace usage searches at the deduplicated affected anchors with one entry per final eligible committed observation, in observation-ID order. This drops stale/orphaned or historically ineligible usage searches within the repaired scope while retaining other kinds/anchors. An older replay that does not update the observation cannot move its evidence; a provenance-only update creates no extra search-dirty scope.
- Eligibility is `row_channel(row) == "transcript"` plus nonempty stored source attribution. Reuse the actual fallback for both NULL and empty channels, which uses truthy `session_id`; do not replace it with SQL `session_id IS NOT NULL`. Keep eligibility independent of numeric qualification and optional model/time presence: unknown transcript audit rows were indexed, while ordinary live, Codex rollout and unsupported explicit channels were not. Missing source attribution cannot justify inventing an anchor.
- Equal model/source/timestamp search tuples are not a unique observation key. Canonical rendering from actual SQLite values must preserve per-observation multiplicity, including already sanitized equal models and SQLite-coerced audit values. No synthetic unique upsert, new search identity, schema migration or second sanitization pipeline is required.
- Accumulate affected scopes and reconcile in bounded batches once per replay transaction, rather than source-wide regeneration after each observation. Fresh inserts use the same committed-row renderer. Keep incremental reconciliation source-scoped; full-population restoration belongs to explicit rebuild. Successful held-source append skips and zero-insert affected-source catch-up still repair their touched scopes; valid no-work and unusable-checkpoint early returns leave search untouched. ENH-3770 reuses this seam and must reconcile affected old/new scopes before each separately committed refresh/recovery phase completes.
- The reconciler requires the caller's open transaction, never begins/commits one itself, and grants no observation-mutation permission. Rebuild must index final state even when today's replay of an unheld copy moves a preserved held row through the shared observation key; whether that move is permitted belongs to ENH-3770.
- Preserve the non-usage rebuild fingerprint and `REBUILD_DERIVE_VERSION`; pass rebuild-only full-population mode through its existing `_backfill_usage_events` call statement, which the fingerprint already excludes. Regenerate after final replay state is known. Do not add a new direct `rebuild` statement, modify `_REBUILD_SEARCH_KINDS`, expand `PRUNED_NAMES` or refresh the frozen snapshot to hide the change. This repair must not bump `_USAGE_DERIVE_VERSION` merely to force checkpoint replay: ENH-3770 owns any justified usage-version change.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — affected-source collection and transaction-final catch-up reconciliation, including collateral transcript searches at a Codex anchor, held append skips and zero-insert replay; preserve checkpoint no-work/skipped paths and rebuild's excluded usage call seam.
- `scripts/little_loops/session_store/writers.py` — factor committed-row rendering, reconstruct missing survivor evidence and batch old/new source scopes for same-ID updates without duplicating search entries or pricing observations.

### Dependent Files

- Existing search readers and schema stay unchanged. Stored source attribution is required; a legacy missing source or erased pre-storage model distinction is not recoverable by adding a migration. `token_provenance.row_channel` owns logical compatibility. `scripts/little_loops/session_store/usage_refresh.py` is a future ENH-3770 integration site: phase 1 currently commits source-anchor search deletion separately from replay. Its observation deletion by `source_raw_event_id` can also delete a copied observation whose own source anchor differs from the refreshed source, leaving stale search outside `source_keys`. ENH-3770 must capture actual old/new anchors from every affected observation, including raw-link matches, and reconcile each phase before commit. This issue delivers/tests the reusable deletion/replacement seam without changing refresh's observation algorithm.
- ENH-3744's proof/prune veto and ENH-3745's checkpoint/source-state are done. ENH-3770 owns guarded reconciliation and hold release/replacement; it remains blocked on this issue. Implement this restoration first for *every surviving committed observation from an indexed producer path that replay does not re-derive*, including future preserved unheld transcript rows. Current Codex/live channels stay unindexed. ENH-3770's implementation is a regression scenario, not a prerequisite here. This issue independently gates epic closure.
- BUG-3761 and BUG-3766 are done: `lifecycle.rebuild` restores surviving tools/corrections and `_reindex_skill_survivors` restores surviving skills after the blanket search-kind deletion, suppressing their replay twins. Keep all three mechanisms and kinds independent. `REBUILD_DERIVE_VERSION` is already `bug3766-v1`; usage restoration must retain the non-usage fingerprint checked by `scripts/tests/test_enh3678_rebuild_derive_gate.py`, rather than claiming a new generic rebuild-version bump.

### Tests

- Extend `scripts/tests/test_bug3736_usage_replay_holds.py`, `test_session_store_incremental_usage.py`, `test_history_reader_search.py` and session-store search/rebuild controls with held/pruned and future preserved-unheld transcript rows, unknown audit rows, NULL/empty channel fallbacks with truthy/empty/missing session IDs, unsupported explicit channels, missing/empty source attribution, empty model/time and live/rollout negative controls. Delete every prior usage search before rebuild; remove/prune raw/source, and patch original-file access/stat and pricing to raise during survivor-only repair. Use both actual search readers to check preview/ref/time/historical anchors.
- Compare fresh/restored canonical `(content, kind, ref, anchor, ts)` multisets for string/NULL, numeric/boolean and floating-point audit models, including `0`/`False`/`0.0`/`True`/`1e20`, literal `"0"`, NULL/empty model twins, legacy pre-canonical searches and already sanitized collisions. Assert normalization is limited to search representation and never changes usage fields. Drive same-ID Claude model/time updates and source-only A→B moves with equal-tuple neighbors in both scopes; older no-update replay keeps the committed anchor. Cover final rebuild state after a current unheld-copy update of a held observation. Exercise future preserved-unheld and deletion/replacement fixtures, including deletion of a raw-linked observation at another anchor, through the shared reconciler in a caller-owned transaction without changing today's observation-deletion predicate or implementing ENH-3770.
- Add the actual catch-up regression: a newly appended Codex raw row at an anchor shared by surviving transcript observations returns zero new observations but restores the collateral search population. Cover held-source append skips, unrelated absent-index sources left untouched by scoped catch-up, and explicit rebuild repairing those sources. Valid no-new-raw/retention-lowered-max and unusable-checkpoint skips leave observations/search unchanged. Assert search repair and same-ID updates do not inflate returned observation counts.
- Survivor-only helper entry/exit checks snapshot every usage column including IDs and live rows, complete hold rows and checkpoint/source-proof state; the existing `_usage` test helper omits IDs/live and is insufficient. Public replay/rebuild tests separately permit existing checkpoint, held-pending and negative invalidation bookkeeping: search restoration itself must add no effects on that state. Inject failure during replay, final reconciliation and after reconciliation/before commit; reopen and verify observation/search rollback. Assert no-work/skipped dispositions make zero search-index writes. A structural reconciliation-call-count control over many same-source updates proves batching without timing thresholds or model subprocesses. Run tool/correction/skill preservation controls and the unchanged non-usage fingerprint gate.

## Acceptance Criteria

- [ ] Rebuild restores the whole indexed transcript population with every prior usage search absent; successful affected-source catch-up, held append skips and zero-insert mixed Codex/transcript controls restore only touched scopes. Raw/original-file access and pricing patched to raise do not prevent survivor-only restoration. Valid no-work/retention-lowered-max and unusable-checkpoint skips leave observations/search unchanged.
- [ ] Unknown audit and supported NULL/empty-channel transcript survivors retain search; ordinary live/rollout and unsupported explicit channels remain unindexed. Missing/empty source attribution never creates a guessed anchor; empty model/time remains supported.
- [ ] Fresh, updated and restored search multisets match the committed-row renderer, including SQLite-coerced numeric/boolean/float audit models, canonicalized legacy search and sanitized model collisions. One entry per eligible observation survives without a migration or observation mutation.
- [ ] Same-ID source/model/timestamp updates and deletion/replacement reconcile old and new scopes, remove obsolete evidence and preserve equal-tuple neighbors/unrelated searches. Older replay leaves the committed anchor unchanged; many same-source updates reconcile in a bounded batch rather than per observation.
- [ ] Repeated rebuild/catch-up leaves usage-search multiplicity unchanged; reconciler entry/exit full-row/hold/checkpoint/source-proof snapshots are unchanged, independently of callers' existing replay bookkeeping, and search repair/same-ID updates do not increase observation counts.
- [ ] Both real search readers return canonical stored preview/ref/time/historical anchors after pruning/source loss. Forced replay or reconciliation failure rolls back index and observation changes together; tool/correction/skill preservation and unchanged `test_enh3678_rebuild_derive_gate.py` fingerprint controls pass.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Implementation Steps

1. Factor the committed-row search renderer and exact logical eligibility policy; use SQLite readback for fresh inserts and canonicalize unrecoverable pre-storage audit rendering without changing observations/schema.
2. Add transaction-final scoped reconciliation with old/new anchor capture, full-population rebuild restoration beneath the excluded usage seam, and explicit no-work/invalid-checkpoint behavior. Prove mixed-source catch-up, held skips, zero counts, source-only moves, multiplicity and batching.
3. Test raw/source loss, coercion/legacy/sanitizer collisions, complete preservation snapshots, both readers and replay/reconciliation rollback. Preserve tool/correction/skill restoration and the non-usage fingerprint. Verify ENH-3770's future preserved-unheld and deletion/refresh-phase handoff without depending on its implementation; run the local suite.

## Scope Boundaries

Out of scope: permission to mutate/preserve usage observations, hold release, parser-refresh observation algorithms, freshness, reader admission, new indexed producer channels or search-identity/schema migrations. ENH-3770 owns future guarded refresh integration and permitted usage mutations; this issue only reconciles search against the observation state committed by its caller.

## Resolution

**Implemented** | 2026-10-08

- `writers.py`: `_usage_search_entry` renders one `(content, kind, ref, anchor, ts)` entry from a committed `usage_events` row (eligibility: `row_channel == "transcript"` plus non-empty `source_path`); `UsageSearchScope` collects old/new anchors; `_reconcile_usage_search` deletes and regenerates usage search for the scoped anchors (or the whole population) in id order, in bounded batches, inside the caller's transaction. `_write_host_usage_observation` no longer indexes inline; inserts and same-ID source/model/timestamp updates mark their scopes. `_backfill_usage_events` gained `search_scope=` (deferred, caller reconciles) and `reindex_all=` (rebuild).
- `lifecycle.py`: `rebuild` passes `reindex_all=True` through its existing (fingerprint-excluded) usage call. Incremental catch-up accumulates Codex sources and held append skips into one scope and reconciles once before publishing the checkpoint; the per-source blanket search delete is gone. No-work and unusable-checkpoint returns remain untouched.
- No schema change, `REBUILD_DERIVE_VERSION` / `_USAGE_DERIVE_VERSION` unchanged, fingerprint gate green.
- Tests: `scripts/tests/test_enh3747_usage_search_reconcile.py` (25).
- Full suite: only pre-existing, unrelated failures remain (`test_next_loop_golden` float rounding; `test_libsql_integration` live-endpoint errors) and 2 ruff findings in `tests/spike/bug3762_*`.

## Status

**Completed** | Created: 2026-10-05 | Priority: P3

## Session Log

- `/ll:manage-issue` - 2026-10-08T20:47:01 - `47715e04-be7b-4db5-b59b-c0eb2159e1cb.jsonl`
- `/ll:ready-issue` - 2026-10-08T20:34:18 - `9863dd16-8fe5-4773-bd13-c58a56df5bde.jsonl`
- `/ll:confidence-check` - 2026-10-08T20:32:28 - `432fb4c5-e9d6-4d88-8204-e76c48d15678.jsonl`
- Pre-implementation review - 2026-10-08 - Proved SQLite model coercion makes exact pre-storage audit search recovery impossible; chose one committed-row renderer with explicit touched-scope legacy normalization and no migration. Added source-only old/new-anchor updates, mixed Codex/transcript collateral deletion, batched reconciliation, final-state global rebuild and exact NULL/empty logical channel controls. Kept no-work/unusable-checkpoint paths untouched while successful touched-source/held-append skips repair search. Required ID-inclusive helper snapshots, no-source-access/no-pricing checks, zero-count repair and rollback after reconciliation. Synchronized ENH-3770's per-phase refresh/raw-link cross-anchor handoff and EPIC-3562's indexed-transcript scope. `/ll:advise` with Opus (confidence 0.80) supported committed rendering, anchor regeneration and the existing fingerprint-excluded rebuild call; a rendered-search migration/tuple-targeted alternative and its suggestion to leave successful held-source append scopes unrepaired were not adopted. Existing relevant regression baseline: 176 passed. No implementation, status change or numeric rescoring.
- Pre-implementation unblocked-child review - 2026-10-07 - Corrected the landed ENH-3745 checkpoint/catch-up baseline and ENH-3770 ownership. Verified only the transcript host writer indexes usage; live and Codex rollout writers do not. Required reconstruction when earlier rebuilds already removed search rows, same-ID model/timestamp reconciliation, stable equal-tuple multiplicity, historical anchors without source access and non-usage fingerprint preservation. No implementation or readiness score claimed.
- Pre-implementation epic review - 2026-10-07 - Widened restoration scope and fixed ordering: ENH-3744's reconciliation will preserve unchanged unheld observations without re-deriving them, which would widen today's search loss (held + live) to every preserved observation unless this lands first. Verified against the reset and rebuild paths. Opus consult (confidence 0.72) independently flagged the same coupling. No implementation claim.
- Pre-implementation epic review - 2026-10-05 - Temporary-store rebuild retained two usage observations but reduced usage search entries from two to zero. Added concrete index/reader ownership, sanitization, replacement and rollback controls; kept search independent of numeric publication and required for epic closure. No implementation or new score is claimed.
- BUG-3766 pre-implementation review - 2026-10-06 - Corrected the BUG-3761 integration note to the landed blanket-delete/survivor-reindex behavior and removed the obsolete shared-rollout assumption. No usage-search implementation is claimed.
