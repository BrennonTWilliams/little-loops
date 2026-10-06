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
- ENH-3732
- ENH-3745
- ENH-3746
- ENH-3747
testable: true
---

# ENH-3744: Semantic usage-candidate proof, derive-gap retention and held-source derivation

## Summary

Replace BUG-3736's whole-source holdback with shared semantic proof and resume safe appends while preserving retained usage. Separate candidate correspondence, mutation permission and source completion: an observation can be represented without being safe to replace or sufficient to certify progress. Deliver with ENH-3745 before exposing the new writer behavior on `main`.

## Current Behavior

On inspected branch `main`, `_plan_raw_prune` in `scripts/little_loops/session_store/lifecycle.py` treats a checkpoint at/above source max raw ID as sufficient derivation proof. `_backfill_usage_events` skips entire held sources; the incremental max-equals-checkpoint early return also misses outstanding work. `_write_host_usage_observation` uses raw-ID ingestion order to update Claude snapshots and computes cost before checking unchanged replay. Neither order nor a high-water checkpoint proves native source order, safe replacement or complete candidate representation.

## Expected Behavior

- Every recognized logical candidate requires a committed observation or an actual native coalesced/deduplicated representation before its raw can be pruned. Missing representation reports `usage_derive_gap`; safely derived partial/unknown audit observations satisfy conservation independently of canonical qualification.
- Known terminal omissions under actual producer rules need no fabricated observation: malformed/partial/all-zero current-contract Claude snapshots with message ID, and recognized Codex rate-limit-only notifications. Unsupported/unknown contracts, missing native identity/context and corrupt retained inputs fail closed.
- Keep protected observations unchanged unless a safe mutation is proved. Unchanged/equal/older replay is an idempotent no-op, including stored cost, timestamps and provenance. A genuinely newer compatible native snapshot may update using its stored/native ordering proof; path aliases, larger raw IDs and equal values/timestamps alone prove neither generation nor order.
- Allow proved-distinct new requests on a source that still has conservation protection. Preserve old protected rows and the hold while unrelated new appends derive safely; hold removal is not a prerequisite for safe additive work. Unkeyed/wildcard legacy populations may prevent proving distinctness and stay conservative.
- Retain Codex header/thread, model/turn/closure and adjacency/dedup context or keep affected work unprovable. A request pointer alone is insufficient. Retain enough context for safe future replay or explicitly keep retained observations protected; document the availability/storage tradeoff.

## Impact

- **Priority**: P2 — follow-up to the landed retention safety floor.
- **Effort**: Large — shared native proof and guarded replay/mutation across destructive paths.
- **Risk**: High — a false correspondence/mutation proof can lose or double-count usage; paired source-completion delivery is required.
- **Breaking Change**: No

## Proposed Solution

Factor the existing native producer recognition/omission/coalescing into pure proof outcomes, then use them transactionally in prune, held-source derivation, rebuild and parser refresh. Keep proof separate from pricing and qualification. ENH-3745 owns progress/boundary storage and publishes completion from these outcomes.

## Program Design

### Types

Proposed frozen `UsageCandidateProof` has a logical host/session/channel/native identity where provable, bounded `correspondence` (`represented`, `missing`, `intentional_omission`, `excluded_channel`, `unprovable`), bounded `mutation` (`insert`, `replace`, `none`) and a bounded reason. Native keys/source/raw links are internal and never serialized into quality or shareable diagnostics. Representation is independent of mutation.

Proposed `UsageReplayFailure` carries retained envelope identity and a bounded decode/context error when no usable `UsageReplayRecord` can be produced. The proof input adapter must preserve every raw record, including malformed JSON, non-object payloads, invalid packed bytes and decompression failures; the current `_iter_usage_replay_records`' silent skips cannot be reused as affirmative absence. Ordinary corruption produces an unprovable outcome, not a fabricated observation or unchecked crash.

ENH-3745 owns the source-local completion/boundary result and any durable source-generation/pending evidence needed by both issues. No separate candidate ledger, registry framework or competing boundary migration here.

### Signatures

- Keep `prune(db, *, config=None, dry_run=False) -> dict` and `backfill_usage_incremental(db) -> int` public contracts.
- `inspect_usage_candidates(records: Iterable[UsageReplayRecord | UsageReplayFailure], observations: Iterable[Mapping[str, Any]], *, channel: str | None = None) -> tuple[UsageCandidateProof, ...]` — new pure helper. Records include a deterministically ordered retained window plus required native context. Observation inputs include the affected hosts/sessions' relevant representations across sources, not just rows with this source path. Inspect compatible source windows independently and compose only actual native cross-source dedup rules. No SQL writes, file reads, pricing or write normalizer calls.

### Call Path

`backfill_usage_incremental` → `_derive_usage_incremental_conn` → `inspect_usage_candidates` → `_backfill_usage_events` → source completion.

`prune` → `_plan_raw_prune` → `inspect_usage_candidates` → transactional raw/usage protection. `rebuild` and `refresh_usage_source` consume the same safe-replay decisions; ENH-3745 publishes progress, and quality reads the pure proof.

### Decision Rules

| Correspondence outcome | Retention/replay | Transcript quality |
| --- | --- | --- |
| Represented | Raw eligible only with needed context/protected usage; mutation requires separate permission | Correspondence passes; row qualification remains separate |
| Recognized intentional omission | No usage fabricated; retain context another candidate needs | Not an observed zero and cannot hide another gap |
| Missing | Keep raw; incomplete source | `derive_gap` |
| Unprovable identity/contract/context or corrupt input | Keep raw/context and protected observations; incomplete source | `derive_status_unavailable` |
| Proved excluded channel | No prune/hold-release permission; prune inspects all channels | `out_of_scope` only if all session evidence is positively excluded |

- Proof is total over retained inputs and respects producer grain. Several Claude snapshots with the same qualified host/session/message ID coalesce; two candidates with one observation remain a gap. Do not requalify legacy missing ingest-time markers. Known terminal omissions require the actual verified host/version/native-ID rule, not a generic malformed/zero heuristic.
- An unkeyed audit row can correspond through its exact surviving raw link with compatible envelope identity. Without that link/native proof, classify it unprovable, not missing; it still protects itself and may prove ingestion. Never infer correspondence by token/cost/timestamp equality.
- Codex duplicate-copy proof must match the writer's cross-source native-response rules: identical proved copies may share representation; conflicts remain audit/unprovable; unkeyed notifications cannot borrow another source's representation. Retain the relevant dedup context even if the winner's original raw was pruned.
- Existing `source_line_no`/`source_ordinal`, verified native stream/session and compatible committed source-generation witnesses may support ordering. A raw ID orders ingestion only. If generation/order cannot be proved after pruning, preserve the retained observation and report mutation unavailable; do not invent compatibility or accept rollback as a risk. ENH-3745 owns a minimal durable witness if existing state is insufficient.
- Check for unchanged/older/protected replay before calling pricing. No replay or rebuild reprices an unchanged retained observation. New or proved-changed requests follow existing pricing semantics; stored historic costs are not recalculated as a side effect of proof.
- Retry outstanding held candidates below the global checkpoint, including when raw max equals it. This issue owns candidate iteration/retry; ENH-3745 owns checkpoint validation/floors and source-local completion, consuming these outcomes.
- Hold release requires all protected observations safely reconstructible or still explicitly protected by equivalent retained guards, and every pending candidate resolved. Preserving an observation is not permission to drop its protection. Per-source release cannot clear a wildcard population hold or another source's guards.
- Compute proof, protect/replace rows, retain context, delete eligible raw and update hold/progress outcomes in the existing `BEGIN IMMEDIATE` transaction. Forced failure rolls everything back. Retained evidence cannot retrospectively certify inventories of older already-pruned history.

### Delivery Contract

Develop ENH-3744/3745 on one integration branch and land their completed writer changes together. ENH-3745 validation/read-only work may precede semantic work, but final cursor publication must consume this proof. Do not add circular `blocked_by` edges. All local-editable consumer projects immediately run this checkout; a temporary cursor-certification gap on `main` is unacceptable.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/writers.py` — factor native recognition/coalescing/dedup, total retained-input decoding and safe observation insert/replace/no-op; resume safe additive work without clearing protection.
- `scripts/little_loops/session_store/claude_usage.py` — reuse actual producer/omission rules without promoting legacy contracts.
- `scripts/little_loops/session_store/lifecycle.py` — semantic `_plan_raw_prune`, held-candidate iteration, all destructive replay guards and atomic protection release. Coordinate shared edits with ENH-3745, which owns checkpoint/cursor semantics.
- `scripts/little_loops/session_store/usage_refresh.py` — reuse safe preservation/replacement decisions; parser refresh cannot independently clear guards or certify skipped work.
- A small pure helper module under `session_store/` is permitted to avoid circular imports; no third-party dependency or new persisted subsystem.

### Dependent Files

- `scripts/little_loops/history_reader/usage.py` — ENH-3732 consumes the pure retained-input proof; export a tested interface without implementing quality here.
- ENH-3745 consumes bounded source outcomes and owns shared durable progress/generation facts. ENH-3746 owns retained-session admission; ENH-3747 owns search restoration.

### Tests

Extend `scripts/tests/test_bug3736_usage_replay_holds.py` and `test_session_store_incremental_usage.py`; add pure-proof parity tests. Drive real Claude/Codex fixture → ingest/derive → production prune → append/recovery → repeated catch-up/rebuild with original files removed. Test below-checkpoint work, decode failure totality, actual cross-source dedup and failure rollback; forbid file reads/pricing/write normalization inside the pure proof.

## Acceptance Criteria

- [ ] A current checkpoint cannot hide a missing logical candidate; its raw stays retained with `usage_derive_gap`. Coalesced snapshots and represented audit rows do not create false gaps.
- [ ] Recognized Claude terminal omissions and Codex rate-limit-only notifications produce no fabricated usage or unnecessary permanent hold; unsupported/unregistered/corrupt evidence remains protected and bounded-unprovable.
- [ ] A newer retained Claude snapshot cannot be rolled back by an older surviving or re-ingested native position with a larger raw ID. Same-path rotation/restore and alias controls do not manufacture compatibility. Repeated unchanged replay leaves cost/metadata untouched even when pricing is patched to fail/change.
- [ ] Codex lost header/model/turn/closure/adjacency context cannot downgrade or duplicate retained requests. Cross-source duplicate/conflict and unkeyed-notification cases match native writer rules.
- [ ] Proved-distinct appends derive while older conservation protection remains; ambiguous/unkeyed/wildcard legacy populations cannot be bypassed. Recovery revisits held candidates below an advanced/equal checkpoint without double counting.
- [ ] Source completion is separate from representation/mutation/hold presence and is handed to ENH-3745. No incomplete proof can publish complete; final writer delivery is tested and landed together.
- [ ] Protection, safe mutation, prune deletion and source-progress outcomes commit atomically; forced failures preserve rows, guards and proof. Source release cannot clear another source or wildcard protections.
- [ ] ENH-3732 consumes the pure interface on a read-only connection without source reads, derivation or pricing; statuses expose no native keys/paths.
- [ ] `python -m pytest scripts/tests/` exits 0, including paired progress/freshness tests.

## Implementation Steps

1. Agree with ENH-3745 on bounded source completion and minimal generation/pending evidence; keep storage ownership there.
2. Factor/test total native proof, correspondence and safe mutation separately, with coalescing/cross-source/decode/legacy controls.
3. Integrate transactional prune/replay/refresh protection and below-checkpoint held retries; preserve unchanged stored costs and guards.
4. Run real lifecycle, rollback and paired completion tests; land the completed ENH-3744/3745 writer integration together, then the local suite.

## Scope Boundaries

No independent freshness/cursor storage, reader admission, search restoration, legacy promotion or repricing of retained observations. Conservative unprovable evidence can retain storage indefinitely; report a bounded reason rather than silently discarding it.

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Session Log

- Pre-implementation epic review - 2026-10-05 - Added the shared pure semantic-proof handoff, concrete lifecycle/refresh ownership, atomic hold-release and below-checkpoint recovery controls. A temporary-store probe with one deleted committed observation reproduced checkpoint-only pruning of all four raw rows; the missing candidate must remain protected. No implementation or new readiness score is claimed.

- Pre-implementation review - 2026-10-06 - Separated correspondence, mutation and completion; required safe additive held-source appends, total corrupt-input proof, actual cross-source Codex dedup and unchanged-cost no-ops. Assigned all shared generation/progress storage to ENH-3745 and required paired writer delivery. Opus confidence 0.72; rejected its raw-ID-only replacement rule because larger ingestion IDs can carry older source snapshots. Existing related suites: 188 passed; no implementation/readiness claim.
