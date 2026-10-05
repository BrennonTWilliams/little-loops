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
- ENH-3671
- ENH-3672
- ENH-3673
- ENH-3674
- ENH-3675
- ENH-3676
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

Additional temporary-database probes on 2026-10-05 confirmed three holes:

- After production prune deletes all four Claude raw rows, the two committed observations still exist, but `_compute_cache_rate_from_usage` returns `session_not_ingested` instead of the previous 77% as-of rate. Its raw-row existence check runs before usage selection; retaining usage alone does not repair this consumer.
- With `transcript-changing-usage-observed.jsonl`, pruning lines 3–5 retains the latest committed observation (481 output tokens, source line 5) alongside older raw snapshots. Full rebuild and incremental max-below-checkpoint replay both replace it with 4 output tokens from line 2. Preserving only rows whose raw pointer is missing is insufficient if subsequent replay updates the retained key.
- With `rollout-exec-resume-v0.158.0.jsonl`, pruning only the three `session_meta`/`turn_context` rows leaves both native usage raw rows intact. Rebuild downgrades both committed observations from `measured` to `unknown`. Replay needs supporting identity/model/turn evidence, not just the usage-bearing row's surviving pointer.

There is also a separate ordinary-append deletion path: `_derive_usage_incremental_conn` deletes every rollout observation for a touched Codex `source_path` before replaying its surviving raw rows. It needs the same preservation policy as version/reset replay. The current Codex normalizer consumes per-request usage and `last_token_usage`, not deltas derived from cumulative totals.

## Expected Behavior

Committed replay-derived usage whose latest source evidence has been pruned survives full rebuild, first-enable/version-mismatch/max-below-checkpoint catch-up and repeated calls. Preserve components, provenance, contract, logical identity, run/state/cost attribution and original as-of boundary. Missing raw or originals does not prove a retraction or fresh zero. Replayable records still update under their proved native identity/mutation rules, without duplicating retained observations or replacing a later retained value with an older surviving snapshot.

Before deleting a usage-bearing candidate, pruning proves it is covered by successful, matching-version derivation, or retains the candidate with an explicit reason. A missing/invalid/stale checkpoint cannot certify processing. Irrelevant non-usage raw records follow existing retention rules. Automatic prune/replay needs no original-source reads, implicit requalification or optional pricing/backfill. Source-loss freshness remains stale/unknown while qualified historical/as-of figures remain retained.

Treat supporting Codex source/turn/model/closure and adjacent-notification evidence as part of replayability. It may be pruned only when the retained observations remain protected from incomplete subsequent replay; otherwise retain the necessary context. Ordinary irrelevant non-usage records keep existing retention eligibility. A missing header or turn context must not turn a retained measured request into an unknown replacement, a duplicate audit request, or a silently lost request.

The selected-session reader recognizes ingestion from verified, source-attributed committed retained usage when raw evidence is gone. Match the requested host/session and the selected source spelling/resolved path; an unrelated source, another host with the same session ID, unverified legacy row or cursor alone cannot supply a usage figure. Keep the four existing absence diagnostics for genuinely absent evidence. Retain source-cursor as-of/freshness semantics; row timestamps are not a replacement for a committed source boundary.

## Motivation

Retained observations are the accounting evidence for historical reports and quality windows. Routine retention followed by automatic replay must not erase that evidence or make a partially derived session appear complete.

## Proposed Solution

Preserve committed usage that can no longer be reconstructed faithfully, reconcile remaining replay by durable logical/source identity, and keep underived usage candidates out of retention deletion. Validate partial-source replay before choosing a deletion predicate; channel alone and a surviving usage-row pointer are insufficient. A conservative source-level holdback is acceptable where individual replacement cannot be proved, provided it reports why newly surviving candidates remain pending and never duplicates retained consumption. Keep public call signatures and ingest-time evidence; make prune proof/count/delete atomic and repair retained-session ingest recognition.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — full/reset/per-Codex-source replay replacement, retention eligibility, transactional proof/count/delete, source freshness and `compact(and_prune=True)` diagnostic propagation.
- `scripts/little_loops/session_store/writers.py` — logical-key conflict/update handling where needed; share native candidate/coalescing/dedup semantics with the prune proof instead of a second payload heuristic.
- `scripts/little_loops/cli/ctx_stats.py` — recognize selected-source retained usage in `_compute_cache_rate_from_usage` before its raw-only absence check; keep shared coverage selection and committed freshness policy.
- `scripts/little_loops/cli/session.py` — render additive retention holdback counts/reasons in prune and compact-and-prune text/JSON.
- `scripts/tests/test_session_store_incremental_usage.py` and `scripts/tests/test_session_store_lifecycle.py` — production prune/replay, mixed retained/replayable/live rows, supporting-context loss, candidate holdback, search evidence and concurrency controls.
- `scripts/tests/test_enh3656_stored_cache_rate.py`, `scripts/tests/test_enh3549_codex_stored_ctx_stats.py` and `scripts/tests/test_ll_session.py` — actual retained-session readers, absence diagnostics and prune/compact output.
- `scripts/little_loops/session_store/usage_refresh.py`, `scripts/tests/test_session_store_usage_refresh.py` — guard explicit parser-upgrade replacement when a source also has non-replayable retained usage; compatibility/rollback controls.
- `scripts/tests/rebuild_fingerprint.py`, `scripts/tests/test_enh3678_rebuild_derive_gate.py` — usage-only helper boundary/version controls if replay factoring changes the traversed function set.
- `docs/reference/API.md`, `docs/reference/CLI.md` and `docs/guides/HISTORY_SESSION_GUIDE.md` — usage retention, held raw rows and as-of limits.

### Dependent Files

- `scripts/little_loops/history_reader/usage.py` — shared coverage/identity checks remain authoritative for committed retained observations. ENH-3732's future derive-status consumer must use the documented candidate/retention contract; it is not an implementation dependency of this bug.
- ENH-3671–3676 — host adapters extend this retained-history baseline before production publication; the `blocks` edges encode that prerequisite.

### Similar Patterns

BUG-3530 preserved live usage that has no raw replay source. BUG-3715 preserved retention summary nodes after their raw rows were pruned. Both are done; this defect concerns replay-derived usage that becomes non-replayable after pruning.

### Tests

Use temporary databases, committed fixtures and production ingestion/prune/rebuild. Remove the copied originals before replay to prove the repair does not reopen them. Compare the complete stored observation, including cost, provenance/contract, source/logical identity, run/state and observed/as-of fields; counts alone miss downgrades. Cover:

- Both all-raw-pruned paths and repeated calls; first-enable/missing derive metadata, normalizer mismatch, max-below-checkpoint and ordinary Codex-source append replacement.
- Claude latest snapshot pruned with an older survivor; replay cannot modify protected retained cost/run/as-of or downgrade retained provenance through an older conflicting copy. Repeated unchanged replay is idempotent under unchanged derivation inputs. Proved newer snapshots and newly observed conflicting-copy audit rules still work. Legacy observations without source links or observation keys are preserved conservatively, without value/timestamp matching or duplicate replay.
- Codex usage raw survives while header/model/turn/closure or adjacent dedup evidence is lost; preserve committed request qualification and do not reconstruct requests from cumulative counters. Include unknown and conflicting request copies: `request_id` alone is not a database uniqueness contract.
- Checkpoint current but a recognized usage candidate lacks committed representation; missing/NULL/non-integer/negative/stale/lagging proof; successful unknown-provenance audit derivation; coalesced snapshots and mirrored notifications legitimately represented by another committed row. A per-raw-row usage FK is not required.
- Holdback dry-run/apply parity, repeated prune, normal non-usage age/size gates, source isolation, and two-connection proof/delete serialization. Inject failures before commit and separately after commit at VACUUM.
- Retained-source Claude/Codex cache-rate text/JSON after raw/source loss, including same-ID other-host/source rejection, cursor-only absence, and legacy-unknown controls. Source/snapshot usage and usage search evidence survive repeated replay; new raw appends keep AUTOINCREMENT ordering and cannot disappear below a reset checkpoint.
- Explicit parser-upgrade refresh on a partially pruned source with no compacted surviving rows: the existing compacted-row check alone cannot protect orphaned retained usage. Reject unsafe replacement or apply the same preservation proof. Fully replayable refresh retains its existing evidence-recovery behavior and rollback.

## Program Design

### Types

Reuse stored usage observations, source/raw links, logical observation keys and existing version/checkpoint metadata; no new persisted retention subsystem is assumed. Missing legacy source/key information is uncertainty, not proof of replayability. If a minimal new marker becomes necessary to distinguish a real source gap, justify it with a failing partial-source control before expanding schema scope.

### Signatures

- `rebuild(db, *, config=None, max_sessions=None) -> dict[str, int]` — retain interface; replace only faithfully replayable usage.
- `backfill_usage_incremental(db) -> int` / `_derive_usage_incremental_conn(conn) -> int` — preserve retained observations during catch-up and checkpoint-reset replay.
- `prune(db, *, config=None, dry_run=False) -> dict` — keep interface, age/size gates and dry-run discipline; retain uncovered usage candidates with a diagnostic.

The prune result keeps existing keys and adds `retained: {"raw_events": int}` for age/compaction-eligible rows held by usage safety, plus stable sorted `retention_reasons: list[str]`. The allowed codes are `usage_derive_unverified` (missing/invalid/stale proof), `usage_derive_pending` (checkpoint lags), `usage_derive_gap` (no proved committed representation) and `usage_replay_context_required` (supporting context must survive). `deleted` counts only safe deletion, and dry-run predicts both counts without writes or VACUUM; label it a prediction because a later apply may see a newer revision. Held rows count once even with multiple reasons; zero/default fields remain present on gated/no-op calls. Propagate these fields through `compact(and_prune=True)` and render them in `ll-session` text/JSON so holdback is distinguishable from no old data.

### Call Path

`backfill_raw_events` → `backfill_usage_incremental` / `_derive_usage_incremental_conn` → committed raw/usage checkpoint → compacted raw retention → `prune` coverage check → `rebuild` or `backfill_usage_incremental` → retained and newly replayed usage → shared source/snapshot/session/quality readers.

### Decision Rules

- **One replacement policy across all paths.** Apply the same proof to full rebuild, first-enable/version/reset replay, ordinary per-Codex-source append replay and explicit parser-upgrade source replacement. Retain rows lacking reconstructible latest evidence. Do not overwrite them with an older survivor, alter their cost/run/as-of fields or downgrade provenance through an older conflicting copy; proved new native observations still update under existing mutation/conflict rules. Preserve live rows, unknown audit rows and conflicting copies. If legacy identity is insufficient to match replay, hold the affected source/population conservatively rather than inventing a join, duplicating it or deleting unlinked usage merely because some raw survives. Existing repricing behavior for fully replayable observations is outside this retention repair.
- **Codex supporting evidence.** Preserve the native header/thread, model/turn/closed-span and adjacent-notification context needed by `_backfill_usage_events`, or hold incomplete source replay with an explicit pending/unverified diagnostic. A surviving request raw pointer does not prove this context exists. A conservative whole-source prune/holdback policy is acceptable; retain the native header where future stored-only append replay requires it. Document the availability/storage tradeoff for long-lived sources. Current replay does not derive cumulative deltas; cumulative totals, timestamps, counts and token equality cannot substitute for native identity or prove deduplication.
- **Semantic prune proof.** A valid current checkpoint is necessary but traversal alone is insufficient: require a committed observation or proved native coalesced/dedup representation for recognized usage candidates. The proof permits safely derived unknown/partial audit observations; it must not require canonical/measured qualification or promote provenance. Reuse native recognition rules and fail closed on unrecognized/unsupported usage-bearing evidence. Protect required supporting context or prove its loss cannot cause destructive replay. Do not import ENH-3732's future derive-status helper; document the shared interpretation for that downstream consumer.
- **Atomicity.** Derive already uses `BEGIN IMMEDIATE`; preserve it. Prune must acquire its write transaction before reading mutable derive/source proof, counting safe/held rows and deleting, then commit them together. Roll back on pre-commit failure. Dry-run uses a consistent read snapshot without mutating usage/raw/checkpoint/cursors; VACUUM remains post-commit best effort.
- **Explicit refresh guard.** A source can have orphaned retained observations even when none of its surviving raw rows is marked compacted. `refresh_raw_events` must either preserve those observations under the shared proof or reject the source with a bounded diagnostic before invalidating usage/cursors/checkpoints. Proved replacement of a wholly replayable source keeps its existing recovery semantics. No automatic source read/re-ingestion is added.
- **Search and freshness.** Rebuild/reset clears usage search rows today. Reindex or preserve existing retained/live usage search evidence without duplicates, dangling entries or stale replaced entries; do not expand search to acquisition channels that were never indexed. Preserve source cursor boundaries; a retained figure does not establish a current complete source or justify a synthetic zero. A held replay cannot advance a source's derived boundary or mark skipped candidates fresh/complete merely because the global raw checkpoint advanced. If a cursor is absent, report unknown as-of/freshness rather than fabricating a boundary from row timestamps.
- **Usage-only version boundary.** Ship any `_USAGE_DERIVE_VERSION` bump in the same change as the preservation fix: the bump itself triggers the formerly destructive reset path in every local-editable consuming project. A new usage-only helper called by `rebuild` would enter the non-usage fingerprint walk unless it is explicitly excluded in `scripts/tests/rebuild_fingerprint.py:PRUNED_NAMES`. That walker blanks only simple statements naming an excluded helper; keep usage-only mutations in that boundary rather than inline/compound rebuild changes. Pin the boundary with a meaningful control; keep the non-usage digest/`REBUILD_DERIVE_VERSION` unchanged when unrelated derivation is unchanged. Do not exempt real non-usage changes or merely regenerate away a failing fingerprint.

## Implementation Steps

1. Add production prune → full/incremental and retained-reader reproductions, then partial-Claude and missing-Codex-context controls. Record the replacement/holdback rule before changing deletion predicates.
2. Preserve non-replayable committed usage across every replacement path, including explicit refresh, and prevent older/incomplete replay from downgrading or repricing protected retained rows; preserve correct new observations, conflicts, live rows and search evidence. Keep the usage-only fingerprint boundary explicit.
3. Add semantic candidate/supporting-context prune proof inside an atomic transaction, stable retained counts/reasons, dry-run parity and CLI/compact propagation; preserve ordinary non-usage retention.
4. Repair retained-session ingest recognition and drive actual stored source/snapshot/session readers, source loss/unchanged refresh and complete-snapshot controls. Align the ENH-3732 handoff without depending on its future helper.
5. Exercise concurrency/rollback/version gates, document the conservative availability/retention limits and run `python -m pytest scripts/tests/`.

## Impact

- Priority: P1 — routine replay can erase recorded consumption after pruning.
- Effort: Medium to large — multiple replay paths, semantic retention proof and actual retained-session reader/CLI wiring. Implement in the bounded stages above; this is more than a deletion-predicate patch.
- Risk: High — partial native context, skipped/coalesced candidates and legacy identity require conservative preservation; numeric rollback can remain measured and evade a row-count-only test.

## Steps to Reproduce

1. In a temporary directory, copy scripts/tests/fixtures/claude/transcript-v2.1.284.jsonl to session.jsonl. Create two temporary history databases, one for each replay mode.
2. For each database run ensure_db, backfill_raw_events with host claude-code, and backfill_usage_incremental. There are four raw rows and two measured transcript usage observations.
3. Set raw_events.compacted to 1 and raw_events.ts to 2020-01-01T00:00:00Z in the temporary database. Call prune with analytics.retention.raw_event_max_age_days=1, min_project_age_days=0 and min_db_size_mb=0.
4. Confirm raw count is 0 and usage count is still 2. On the first database call rebuild; on the second call backfill_usage_incremental. Both usage counts incorrectly become 0.

## Root Cause

- File: scripts/little_loops/session_store/lifecycle.py
- Anchors: `_REBUILD_TABLE_PREDICATES`, `rebuild`, `_derive_usage_incremental_conn`, `prune`; `cli/ctx_stats.py:_compute_cache_rate_from_usage`
- Cause: non-live channel or touched source is treated as proof of faithful replayability, while retention removes latest/supporting evidence. Prune lacks semantic derive coverage and a proof/delete transaction. The stored session reader independently treats surviving raw evidence as the only proof of prior ingestion.

## Acceptance Criteria

- [ ] Production prune followed by two full rebuilds or two incremental catch-ups preserves the complete logical usage snapshot when its raw evidence is gone; both ordinary max-below-checkpoint and normalizer-mismatch paths are covered.
- [ ] The same preservation rule covers first-enable/missing metadata and ordinary per-Codex-source append replacement. Mixed live, retained non-replayable, unknown/conflicting and replayable rows do not duplicate, disappear or downgrade; legacy missing links/keys fail closed.
- [ ] Partial pruning cannot replace the retained 481-token Claude snapshot with its 4-token predecessor or downgrade measured Codex requests when only header/model/turn/closure/dedup context is lost. Older replay/conflicting copies cannot modify protected retained cost/run/as-of/provenance/contract fields; repeated unchanged replay is idempotent, and proved later snapshots/new native conflicts keep their existing rules.
- [ ] Missing/NULL/malformed/negative/version-mismatched or lagging proof cannot permit pruning an underived usage candidate. Even a current checkpoint cannot hide a recognized candidate without committed or proved coalesced/dedup representation. Successfully derived unknown audit observations are not held merely for lacking measured qualification. Required supporting context is retained or incomplete replay is safely held; unrelated non-usage retention and dual age/size gates keep their contract.
- [ ] Prune proof/count/delete uses one write transaction; a concurrent derive/source replacement cannot invalidate its proof. Additive retained counts/reasons reach prune/compact text/JSON, count held rows once and match dry-run without data/meta/cursor writes.
- [ ] Retained ingest-time qualification, cost and logical/run attribution survive; automatic prune/replay does not read original sources, requalify or reprice protected retained usage, or infer a fresh zero. New raw appends after pruning cannot reuse IDs or silently disappear below a stale checkpoint.
- [ ] Actual Claude/Codex stored cache-rate readers recognize verified selected-source retained usage after all raw evidence is pruned; same-ID other-host/source, unverified legacy and cursor-only controls do not produce a figure. Existing absence diagnostics, source-cursor as-of, source-loss freshness and text/JSON unavailable-vs-zero semantics remain truthful.
- [ ] An injected failure before prune/replay commit rolls back affected usage/raw/checkpoint state; post-commit VACUUM failure does not undo retention. Source loss and unchanged refresh retain historical evidence conservatively; explicit parser-upgrade refresh rejects or safely preserves sources with non-replayable retained observations before invalidating evidence, while fully replayable refresh still recovers new producer evidence. Source/snapshot readers, usage search evidence and the documented downstream quality derive-status contract agree; repeated replay does not erase retained/live search entries or create duplicates.
- [ ] The usage-only version bump and preservation ship together; upgrading an already-pruned store retains its evidence and the non-usage fingerprint remains unchanged when its semantics are unchanged. Docs state retention/holdback/as-of limits and `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- In scope: retained usage, faithful replay and pruning/derive safety across the shared lifecycle; actual retained-session ingest recognition and bounded holdback diagnostics.
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
- Pre-implementation issue review - 2026-10-05 - Production temporary-database probes confirmed raw-pruned sessions return `session_not_ingested`, Claude partial replay rolls 481 output tokens back to 4, and removing only Codex header/model context downgrades both retained measured requests to unknown. Added the real reader, ordinary Codex append path, semantic candidate/context retention proof, atomic prune/dry-run diagnostics, complete-snapshot/search/version controls and delivery dependencies. Existing focused selector/reader/lifecycle/version tests passed (86 tests); no implementation is claimed.
- `/ll:advise` - 2026-10-05 - Opus (`claude-opus-5-5`, confidence 0.78) supported shared replacement/candidate proof and identified explicit parser-upgrade refresh as another destructive path, plus the simple-statement fingerprint boundary. Adopted those controls and documented whole-source Codex holdback as an allowed conservative implementation. Did not adopt raw-pointer existence as sufficient replay proof (the missing-context probe disproves it), destructive legacy-unlinked fallback (advisor acknowledged residual data loss), or a new equal-replay pricing policy. Legacy uncertainty remains held; derivation availability/storage tradeoffs must be explicit.
