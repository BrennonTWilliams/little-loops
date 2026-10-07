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
confidence_score: 75
outcome_confidence: 50
score_complexity: 5
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 10
risk_factors:
- id: deep-transactional-rewiring
  domain: outcome
  criterion: complexity
  description: Replaces delete-then-replay with guarded reconciliation across prune,
    rebuild, catch-up and two-phase refresh; contract-level changes
- id: enh3747-search-loss-ordering
  domain: readiness
  criterion: dependencies
  description: Preserving unchanged usage rows widens search-row loss unless open
    ENH-3747 lands first or in the same change
- id: generation-witness-storage-undecided
  domain: outcome
  criterion: ambiguity
  description: Ordering/generation proof depends on a durable witness whose ownership
    and shape sit with unresolved ENH-3745
- id: paired-landing-enh3745
  domain: readiness
  criterion: dependencies
  description: Must land with open ENH-3745 (cursor/progress storage); tooling lands
    one issue per branch and epic-branch mode merges unverified
- id: sanitizer-identity-registration
  domain: readiness
  criterion: specification
  description: Proof identity keys must be registered in pii._protocol_rules or retained
    payloads read as unprovable after redaction
- id: slicing-decision-pending
  domain: outcome
  criterion: ambiguity
  description: Opus slicing proposal (defer digest continuity, context-only promotion,
    as-of witness) recorded but not decided; scope unsettled
- id: wide-writer-caller-surface
  domain: outcome
  criterion: change_surface
  description: Touched writer/lifecycle/refresh entry points have 6-10 dependents
    across CLI, schema, readers and many test modules
---

# ENH-3744: Semantic usage-candidate proof, derive-gap retention and held-source derivation

## Summary

Replace BUG-3736's whole-source holdback with shared semantic proof and resume safe appends while preserving retained usage. Separate candidate correspondence, mutation permission and source completion: an observation can be represented without being safe to replace or sufficient to certify progress. Deliver with ENH-3745 before exposing the new writer behavior on `main`.

## Current Behavior

On inspected branch `main`, `_plan_raw_prune` in `scripts/little_loops/session_store/lifecycle.py` treats a checkpoint at/above source max raw ID as sufficient derivation proof. `_backfill_usage_events` skips entire held sources; the incremental max-equals-checkpoint early return also misses outstanding work. `_write_host_usage_observation` uses raw-ID ingestion order to update Claude snapshots and computes cost before checking unchanged replay. Neither order nor a high-water checkpoint proves native source order, safe replacement or complete candidate representation.

Reset/Codex catch-up and `rebuild` delete unheld observations before replay; `refresh_raw_events` deletes linked observations before committing its separate `needs_rebuild` phase. A temporary-store unchanged Claude rebuild replaced row IDs and changed deliberately stored historical costs. Source parsers also skip malformed/non-object lines before retained proof can see them. Codex qualification can legitimately change when a later `task_complete` supplies missing context, even when the request's numeric snapshot is unchanged.

## Expected Behavior

- Every recognized logical candidate requires a committed observation or an actual native coalesced/deduplicated representation before its raw can be pruned. Missing representation reports `usage_derive_gap`; safely derived partial/unknown audit observations satisfy conservation independently of canonical qualification.
- Known terminal omissions under actual producer rules need no fabricated observation: malformed/partial/all-zero current-contract Claude snapshots with message ID, and recognized Codex rate-limit-only notifications. Unsupported/unknown contracts, missing native identity/context and corrupt retained inputs fail closed.
- Keep protected observations unchanged unless a safe mutation is proved. Semantically unchanged or older replay is an idempotent no-op, including row identity, stored cost, timestamps and provenance. A genuinely newer compatible native snapshot may update using its stored/native ordering proof; newly proved native context may permit a separate qualification mutation. Equal numeric values alone do not establish a semantic no-op; path aliases, larger raw IDs and equal values/timestamps alone prove neither generation nor order.
- Verify envelope, native payload/contract and retained observation host/session identity before recognizing correspondence or applying a mutation. A disagreement is unprovable and retains its raw/context; do not create measured cross-session usage, silently reassign existing observations or classify the disagreement as an excluded acquisition channel.
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

Proposed frozen `UsageCandidateProof` has a logical host/session/channel/native identity where provable, bounded `correspondence` (`represented`, `missing`, `intentional_omission`, `excluded_channel`, `unprovable`), bounded `mutation` (`insert`, `replace`, `none`) and a bounded reason. Native keys/source/raw links are internal and never serialized into quality or shareable diagnostics. Representation is independent of mutation. Carry the internal source/generation/native position of the record supplying an observation's current values and the frontier of native context actually used to qualify it; ENH-3745 owns any missing durable witness. Original request position alone cannot locate a later applied snapshot or closure. Inputs must carry these committed witnesses explicitly; the pure helper cannot infer them from file paths or access storage itself.

Proposed `UsageReplayFailure` carries verified source/envelope scope, native position where available and a bounded decode/context error when no usable `UsageReplayRecord` can be produced. The proof input adapter must preserve every raw record, including malformed JSON, non-object payloads, invalid packed bytes and decompression failures; the current `_iter_usage_replay_records`' silent skips cannot be reused as affirmative absence. Also consume ENH-3745's durable failure disposition for source lines rejected before raw insertion: no fabricated raw ID or original malformed bytes are needed. Ordinary corruption produces an unprovable outcome, not a fabricated observation or unchecked crash. Recognized benign non-usage records/blank lines remain distinct from decode failures and producer-specific terminal usage omissions.

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
- Evaluate candidates against the committed observations **before** any reset, per-Codex-source catch-up, rebuild or parser-refresh deletion. Replace broad usage delete/reinsert with source-scoped reconciliation; unchanged unheld rows need the same cost/identity preservation as held rows. A prospective insert/replace is not committed representation. `prune` consumes proof and writes protection only; it does not derive usage or invoke pricing. Dry-run uses the same proof/context plan in one read snapshot and writes nothing.
- Matching a native key proves request identity, not that the current stored values represent every later candidate. `represented` requires a compatible applied snapshot that dominates the candidate under native order, or actual producer coalescing/dedup proof. A later unresolved candidate sharing an older observation's key remains missing/unprovable for source completion and quality; keeping the older observation safe cannot certify it.
- On Claude, compare payload `sessionId` with the verified replay envelope and observation identity; on Codex, also compare header/thread/native request context. Mismatch fails closed before mutation and source completion. Preserve already-stored audit evidence under its recorded identity, without manufacturing a new qualified row. No new Claude resume/fork copy or alias rule is assumed without native fixture proof.
- An unkeyed audit row can correspond through its exact surviving raw link with compatible envelope identity. Without that link/native proof, classify it unprovable, not missing; it still protects itself and may prove ingestion. Never infer correspondence by token/cost/timestamp equality.
- Codex duplicate-copy proof must match the writer's cross-source native-response rules: identical proved copies may share representation; conflicts remain audit/unprovable; unkeyed notifications cannot borrow another source's representation. Retain the relevant dedup context even if the winner's original raw was pruned.
- Existing `source_line_no`/`source_ordinal`, verified native stream/session and compatible committed source-generation witnesses may support ordering. A raw ID orders ingestion only. If generation/order cannot be proved after pruning, preserve the retained observation and report mutation unavailable; do not invent compatibility or accept rollback as a risk. ENH-3745 owns a minimal durable witness if existing state is insufficient.
- Permit bounded context-only audit-to-measured promotion when newly proved compatible native evidence completes current-producer qualification, such as Codex `task_complete` closing an already represented request. This is not unchanged replay or automatic legacy promotion. Require every relevant request-span/model/closure/conflict/dedup dependency to be proved; a gap inside required context blocks promotion, while an unrelated earlier gap may leave the successful source prefix behind a safely qualified request. Preserve request identity, numeric components, value-supplying position/timestamp and any stored historical cost; update only proved qualification facts and their dependency frontier. Pricing is allowed only for a newly proved eligible unpriced observation under existing semantics. Missing/replayed context or identical duplicate copies grant no permission to promote or downgrade. Demotion, conflicts and changed values remain outside this context-only transition.
- Check for unchanged/older/protected replay before calling pricing. No replay or rebuild reprices an unchanged retained observation. New or proved-changed requests follow existing pricing semantics; stored historic costs are not recalculated as a side effect of proof.
- A proved value replacement atomically updates the applied-value source/generation/native position with its numeric values; a context-only mutation updates its actual qualification dependency frontier without pretending that a newer numeric snapshot supplied the values. No-op replay preserves both witnesses along with cost/metadata. A Codex dedup survivor retains its actual supplying source/position; another copy cannot substitute a convenient selected-source boundary.
- Retry outstanding held candidates below the global scan high-water, including when raw max equals it, using ENH-3745's generation-scoped source pending/retry bound. This issue owns candidate iteration/retry; ENH-3745 owns scan validation and source-local completion, consuming these outcomes. Raw-ID bounds schedule retries only; native context/order still decides recognition and mutation.
- Hold release requires all protected observations safely reconstructible or still explicitly protected by equivalent retained guards, and every pending candidate resolved. Preserving an observation is not permission to drop its protection. Per-source release cannot clear a wildcard population hold or another source's guards.
- Compute proof, protect/replace rows, retain context, delete eligible raw and update hold/progress outcomes in the existing `BEGIN IMMEDIATE` transaction. Forced failure rolls everything back. Retained evidence cannot retrospectively certify inventories of older already-pruned history.
- Preserve the public two-phase parser-refresh workflow: raw replacement and a scoped refresh-pending disposition commit together while existing observations and truthful historical boundaries remain protected. A failure before that commit rolls everything back; a crash/failure before the later derive leaves old usage present and pending work durable. Only proved reconciliation can release those guards. Preserve the existing verified original-source refresh's qualification recovery; ordinary retained replay cannot acquire missing ingest-time contracts by itself. ENH-3745 owns pending/invalidation state, not a second global checkpoint reset.

### Delivery Contract

Develop ENH-3744/3745 on one integration branch and land their completed writer changes together. ENH-3745 validation/read-only work may precede semantic work, but final cursor publication must consume this proof. Coordinate one `_USAGE_DERIVE_VERSION` bump for the new proof/reconciliation contract, with protected old-version recovery; no usage-only change bumps `REBUILD_DERIVE_VERSION` or its non-usage fingerprint. Do not add circular `blocked_by` edges. All local-editable consumer projects immediately run this checkout; a temporary cursor-certification gap on `main` is unacceptable.

### Landing Mechanics, Interactions and Scope Note (2026-10-07)

- **Atomic multi-issue landing is not provided by the tooling.** `ll-auto`/`ll-parallel`/`ll-sprint` land one issue per branch. `parallel.epic_branches` is enabled with `merge_to_base_on_complete: true` and `verify_before_merge: false`, so an epic branch would merge to `main` unverified on completion, and an epic-worktree verify gate imports the main-tree editable install (false-negative merge blocks). Satisfy the paired-landing rule by implementing ENH-3744/3745 in one worktree/session and merging once, or by an order in which every intermediate commit is fail-closed (never emits `complete`/fresh it cannot prove; never mutates a protected observation without proof). Do not rely on epic-branch mode.
- **ENH-3751 (done 2026-10-06) changed the refresh seams this issue edits.** `usage_refresh.refresh_raw_events` now compares canonical (history-sanitized) payloads in both stored columns, refuses per-line metadata/contract changes (`source_metadata_changed`, `usage_contract_changed`, `existing_payload_not_preserved`, `parser_changed_during_refresh`) and promotes a NULL `usage_contract` monotonically — a persisted marker is never changed. `_refresh_codex_usage_source` first-cursor certification uses the same canonical comparison. Preserve all of this; "the existing verified original-source refresh's qualification recovery" above is that NULL→marker promotion, distinct from the context-only qualification promotion on `usage_events` specified here. The retained payloads the proof reads are sanitized (and legacy rows may be plaintext, or rewritten later by `ll-session redact`): every identity key the proof relies on must be protected by `pii._protocol_rules` for the host/event type (EPIC-3562 § Shared Delivery Ownership, sanitizer identity contract), because a rewrite of an unprotected identity would read as `missing`/`unprovable`. Treat an unregistered identity path as `unprovable`, never as an absent candidate.
- **ENH-3747 coupling (verified in `lifecycle._derive_usage_incremental_conn` and `rebuild`).** Reset/catch-up delete only unheld non-live usage rows but wipe every `kind = 'usage'` search row, and `rebuild` wipes the whole kind; replay re-indexes only what it re-derives. Today only held and live observations lose search entries. Once reconciliation stops re-deriving unchanged unheld observations, every preserved observation does. Land ENH-3747 first, or in the same change with scope "every surviving committed usage observation that replay does not re-derive", and add a search-survival control to this issue's reset/catch-up/rebuild tests.
- **Scope note — pending decision, not applied.** An Opus consult (confidence 0.72) recommended slicing ENH-3744/3745 into individually landable fail-closed steps and deferring hardening that already has a fail-closed fallback in these specs: full-prefix digest continuity (ENH-3745), context-only audit→measured promotion with its qualification-context frontier (this issue), and the applied-value-witness beyond-prefix as-of check (ENH-3746). Verified premise correction: usage-bearing raw is already pruned today (`_plan_raw_prune` deletes a fully aged, compacted source at or below a valid checkpoint and writes a hold marker), so the semantic prune veto and retained-reader admission are live correctness work, not post-hold-release work. See EPIC-3562 Review Notes (2026-10-07) for the proposed cut and decide before implementation starts.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/writers.py` — factor native recognition/coalescing/dedup, total retained-input decoding and safe observation insert/replace/no-op; resume safe additive work without clearing protection.
- `scripts/little_loops/session_store/claude_usage.py` — reuse actual producer/omission rules without promoting legacy contracts.
- `scripts/little_loops/session_store/lifecycle.py` — semantic `_plan_raw_prune`, held-candidate iteration, pre-deletion comparison in reset/Codex catch-up/rebuild and atomic protection release. Coordinate shared edits with ENH-3745, which owns checkpoint/cursor semantics; keep the non-usage rebuild fingerprint boundary intact.
- `scripts/little_loops/session_store/usage_refresh.py` — reuse safe preservation/replacement decisions before raw replacement; protect observations across its two-phase workflow rather than deleting them for a later rebuild.
- A small pure helper module under `session_store/` is permitted to avoid circular imports; no third-party dependency or new persisted subsystem.

### Dependent Files

- `scripts/little_loops/history_reader/usage.py` — ENH-3732 consumes the pure retained-input proof; export a tested interface without implementing quality here.
- ENH-3745 consumes bounded source outcomes and owns shared durable progress/generation facts. ENH-3746 owns retained-session admission; ENH-3747 owns search restoration.

### Tests

Extend `scripts/tests/test_bug3736_usage_replay_holds.py` and `test_session_store_incremental_usage.py`; add pure-proof parity tests. Drive real Claude/Codex fixture → ingest/derive → production prune → append/recovery → repeated catch-up/rebuild with original files removed. Test below-checkpoint work, decode failure totality, actual cross-source dedup and failure rollback; forbid file reads/pricing/write normalization inside the pure proof. Add envelope/payload/observation identity disagreements and a same-key newer candidate not yet represented. For a safely replaced Claude row originally inside the complete prefix but updated beyond a gap, assert its applied-value witness moves with the replacement; test witness rollback and no-op preservation.

Run unchanged unheld Claude/Codex observations through all reset/catch-up/rebuild seams with pricing patched to raise; assert stable row IDs, costs and metadata. In `test_session_store_usage_refresh.py`, inject pre-commit replacement failure and post-commit/pre-derive crash, then retry after restart; old usage survives and pending guards remain until proved reconciliation. Separate unchanged verified refresh from supported qualification recovery. Use the Codex fixture's first four lines, then append only its duplicate notification/turn closure: qualify the same request once from actual new context, preserve counts/value position, advance the context frontier and prove rollback/no-op replay. Contrast a missing dependency within that request span (no promotion) with an unrelated earlier gap (safe promotion, but ENH-3746 cannot publish the earlier boundary as the changed figure's as-of). Exercise source-admission failures through ENH-3745's bounded evidence, production prune dry-run/actual count and reason parity with no pricing calls, and the existing non-usage rebuild-fingerprint gate.

### Documentation

Update usage/prune/rebuild/refresh contracts in `docs/reference/API.md`, retention diagnostics in `docs/reference/CLI.md` and Stage 1 hold limitations in `docs/guides/HISTORY_SESSION_GUIDE.md`. Describe safe additive held-source work, preserved historical costs, context-only qualification and recoverable parser-refresh pending state; coordinate freshness/storage wording with ENH-3745. Keep internal native keys/witnesses out of end-user diagnostics.

## Acceptance Criteria

- [ ] A current checkpoint cannot hide a missing logical candidate; its raw stays retained with `usage_derive_gap`. Coalesced snapshots and represented audit rows do not create false gaps.
- [ ] Envelope/native/observation host-session disagreements remain unprovable with retained raw/context and cannot insert measured cross-session usage or publish completion. An older matching native key alone cannot certify a newer unresolved candidate.
- [ ] Recognized Claude terminal omissions and Codex rate-limit-only notifications produce no fabricated usage or unnecessary permanent hold; unsupported/unregistered/corrupt evidence remains protected and bounded-unprovable.
- [ ] A newer retained Claude snapshot cannot be rolled back by an older surviving or re-ingested native position with a larger raw ID. Same-path rotation/restore and alias controls do not manufacture compatibility. Repeated unchanged replay leaves cost/metadata untouched even when pricing is patched to fail/change.
- [ ] Reset, Codex catch-up, full rebuild and verified parser refresh compare with existing usage before mutation; unchanged unheld/held row identities and stored costs survive. A crash between committed raw refresh and later derive leaves protected observations and durable pending evidence, never a lost figure or falsely complete source.
- [ ] Codex lost header/model/turn/closure/adjacency context cannot downgrade or duplicate retained requests. Cross-source duplicate/conflict and unkeyed-notification cases match native writer rules.
- [ ] Newly proved compatible Codex closure can qualify an existing audit request without a newer token snapshot or second observation. Counts/value lineage and stored cost remain intact; the qualification frontier changes atomically. Equal values or ordinary legacy replay alone cannot promote qualification.
- [ ] Proved-distinct appends derive while older conservation protection remains; ambiguous/unkeyed/wildcard legacy populations cannot be bypassed. Recovery revisits held candidates below an advanced/equal checkpoint without double counting.
- [ ] Source completion is separate from representation/mutation/hold presence and is handed to ENH-3745. No incomplete proof can publish complete; final writer delivery is tested and landed together.
- [ ] Protection, safe mutation, prune deletion and source-progress outcomes commit atomically; forced failures preserve rows, guards and proof. Source release cannot clear another source or wildcard protections.
- [ ] Applied-value source/generation/native positions change atomically on actual replacements and survive no-op replay. ENH-3746 can distinguish a row updated beyond the completed prefix and a dedup survivor supplied by another source without reopening native files or exporting internal identities.
- [ ] Source decode failures never disappear from proof merely because ingestion skipped their bytes. Recognized non-usage/blank lines remain harmless; prune never derives/prices and dry-run matches the actual semantic retention/context plan without writes.
- [ ] ENH-3732 consumes the pure interface on a read-only connection without source reads, derivation or pricing; statuses expose no native keys/paths.
- [ ] `python -m pytest scripts/tests/` exits 0, including paired progress/freshness tests.

## Implementation Steps

1. Agree with ENH-3745 on bounded source completion and minimal generation/pending evidence; keep storage ownership there.
2. Factor/test total native proof, correspondence and safe mutation separately, with coalescing/cross-source/decode/legacy controls.
3. Replace usage delete-then-replay with guarded reconciliation; integrate transactional prune, two-phase refresh protection, context-only qualification and below-checkpoint held retries. Preserve unchanged costs, row identities and guards.
4. Run real lifecycle, rollback and paired completion tests; land the completed ENH-3744/3745 writer integration together, then the local suite.

## Scope Boundaries

No independent freshness/cursor storage, reader admission, search restoration, legacy promotion or repricing of retained observations. Conservative unprovable evidence can retain storage indefinitely; report a bounded reason rather than silently discarding it.

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-07_

**Readiness Score**: 75/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 50/100 → LOW

### Concerns
- Paired landing with open ENH-3745 is mandatory, but tooling lands one issue per branch and epic-branch mode merges unverified (`verify_before_merge: false`); the landing plan is a process constraint, not an enforced mechanism.
- ENH-3747 (open) must land first or in the same change, otherwise preserving unchanged usage rows widens search-row loss from held/live to every preserved observation.
- Sanitizer identity precondition: every identity key the proof reads must be registered in `pii._protocol_rules`, or redacted retained payloads read as `unprovable`.
- Learning tests: none required. Program Design gate passes; `BUG-3736` (`blocked_by`) is done.

### Outcome Risk Factors
- Deep per-site complexity: replaces delete-then-replay with guarded reconciliation across prune, rebuild, catch-up and two-phase refresh (contract-level change, High risk).
- Scope unsettled: the Opus slicing proposal (defer digest continuity, context-only promotion, as-of witness) is recorded as a pending decision; decide before implementation starts.
- Generation/ordering proof depends on a durable witness whose shape sits with unresolved ENH-3745.
- Wide caller surface (~6-10 dependents across CLI, schema, readers, many test modules).

### Risk Factor Delta
- Baseline: none recorded

## Session Log

- `/ll:confidence-check` - 2026-10-07T16:32:13 - `2231707d-b3c0-49ab-b995-a5f45163a660.jsonl`
- Pre-implementation epic review - 2026-10-07 - Added landing mechanics (tooling lands one issue per branch; epic-branch mode auto-merges unverified), the ENH-3751 refresh-seam interaction and the sanitizer identity precondition for the pure proof, and the ENH-3747 search-loss coupling (verified: reset/rebuild wipe all usage search rows; preserving unchanged rows widens the loss from held/live to every preserved observation). Recorded Opus's slicing proposal as a pending decision with one verified premise correction (raw of usage-bearing sources is pruned today). No implementation or readiness claim.

- Pre-implementation review - 2026-10-06 - Reproduced complete/fresh publication after source decode skips, unchanged rebuild row/cost replacement, and Codex audit-to-measured qualification from later closure with unchanged numeric usage. Required pre-deletion reconciliation, pure prune/dry-run parity, protected two-phase refresh recovery and qualification-context witnesses. Opus consults (confidence 0.76 and 0.80) supported the changes; did not adopt harmless row-ID churn or weaker inode/tail generation proof. Existing targeted producer/retention/incremental/refresh suites: 111 passed; both revised issues passed structural checks. No implementation or readiness score claimed.

- Pre-implementation handoff review - 2026-10-06 - Reproduced a verified current-contract Claude payload becoming measured despite disagreement with the replay envelope's session. Added fail-closed identity controls, snapshot-dominance requirements and applied-value witness publication/rollback, including the older-request/later-update counterexample. Wired retry iteration to ENH-3745's source-local pending bound. Opus confidence 0.74 supported these handoffs; speculative Claude fork-copy reclassification was not adopted without fixture evidence. Targeted existing policy/lifecycle/reader/quality/workspace/dashboard/chokepoint suites: 293 passed. No implementation or readiness score claimed.

- Pre-implementation epic review - 2026-10-05 - Added the shared pure semantic-proof handoff, concrete lifecycle/refresh ownership, atomic hold-release and below-checkpoint recovery controls. A temporary-store probe with one deleted committed observation reproduced checkpoint-only pruning of all four raw rows; the missing candidate must remain protected. No implementation or new readiness score is claimed.

- Pre-implementation review - 2026-10-06 - Separated correspondence, mutation and completion; required safe additive held-source appends, total corrupt-input proof, actual cross-source Codex dedup and unchanged-cost no-ops. Assigned all shared generation/progress storage to ENH-3745 and required paired writer delivery. Opus confidence 0.72; rejected its raw-ID-only replacement rule because larger ingestion IDs can carry older source snapshots. Existing related suites: 188 passed; no implementation/readiness claim.
