---
id: ENH-3744
type: ENH
title: Semantic usage-candidate proof, derive-gap retention and prune veto
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
- ENH-3751
- ENH-3770
testable: true
confidence_score: 75
outcome_confidence: 50
score_complexity: 5
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 10
risk_factors:
- id: paired-landing-enh3745
  domain: readiness
  criterion: dependencies
  description: Shares cursor/progress storage with open ENH-3745; delivered as ordered
    fail-closed merge points (see Delivery Plan, 2026-10-07), not one atomic landing
- id: sanitizer-identity-registration
  domain: readiness
  criterion: specification
  description: Proof identity keys must be registered in pii._protocol_rules or retained
    payloads read as unprovable after redaction
- id: slicing-decided-rescore-needed
  domain: outcome
  criterion: ambiguity
  description: Slicing decided 2026-10-07 (merge points MP1-MP3, Phase 2 deferrals);
    scores above predate it — rerun /ll:confidence-check per merge point
- id: wide-writer-caller-surface
  domain: outcome
  criterion: change_surface
  description: Touched writer/lifecycle/refresh entry points have 6-10 dependents
    across CLI, schema, readers and many test modules
---

# ENH-3744: Semantic usage-candidate proof, derive-gap retention and prune veto

## Summary

Replace BUG-3736's whole-source holdback with shared semantic proof and resume safe appends while preserving retained usage. Separate candidate correspondence, mutation permission and source completion: an observation can be represented without being safe to replace or sufficient to certify progress. Delivered with ENH-3745 as ordered fail-closed merge points (see Delivery Plan; reconciliation/held-source derivation/hold release split out as ENH-3770 on 2026-10-07); no merge may expose writer behavior that is not independently fail-closed.

## Current Behavior

On inspected branch `main`, `_plan_raw_prune` in `scripts/little_loops/session_store/lifecycle.py` treats a checkpoint at/above source max raw ID as sufficient derivation proof. `_backfill_usage_events` skips entire held sources; the incremental max-equals-checkpoint early return also misses outstanding work. `_write_host_usage_observation` uses raw-ID ingestion order to update Claude snapshots and computes cost before checking unchanged replay. Neither order nor a high-water checkpoint proves native source order, safe replacement or complete candidate representation.

Reset/Codex catch-up and `rebuild` delete unheld observations before replay; `refresh_raw_events` deletes linked observations before committing its separate `needs_rebuild` phase. A temporary-store unchanged Claude rebuild replaced row IDs and changed deliberately stored historical costs. Source parsers also skip malformed/non-object lines before retained proof can see them. Codex qualification can legitimately change when a later `task_complete` supplies missing context, even when the request's numeric snapshot is unchanged.

## Expected Behavior

- Every recognized logical candidate requires a committed observation or an actual native coalesced/deduplicated representation before its raw can be pruned. Missing representation reports `usage_derive_gap`; safely derived partial/unknown audit observations satisfy conservation independently of canonical qualification.
- Known terminal omissions under actual producer rules need no fabricated observation: malformed/partial/all-zero current-contract Claude snapshots with message ID, and recognized Codex rate-limit-only notifications. Unsupported/unknown contracts, missing native identity/context and corrupt retained inputs fail closed.
- Verify envelope, native payload/contract and retained observation host/session identity before recognizing correspondence or applying a mutation. A disagreement is unprovable and retains its raw/context; do not create measured cross-session usage, silently reassign existing observations or classify the disagreement as an excluded acquisition channel.
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
- Evaluate candidates against the committed observations **before** any prune deletion. A prospective insert/replace is not committed representation. `prune` consumes proof and writes protection only; it does not derive usage or invoke pricing. Dry-run uses the same proof/context plan in one read snapshot and writes nothing. Pre-deletion comparison for reset, Codex catch-up, rebuild and parser refresh belongs to ENH-3770.
- Matching a native key proves request identity, not that the current stored values represent every later candidate. `represented` requires a compatible applied snapshot that dominates the candidate under native order, or actual producer coalescing/dedup proof. A later unresolved candidate sharing an older observation's key remains missing/unprovable for source completion and quality; keeping the older observation safe cannot certify it.
- On Claude, compare payload `sessionId` with the verified replay envelope and observation identity; on Codex, also compare header/thread/native request context. Mismatch fails closed before mutation and source completion. Preserve already-stored audit evidence under its recorded identity, without manufacturing a new qualified row. No new Claude resume/fork copy or alias rule is assumed without native fixture proof.
- An unkeyed audit row can correspond through its exact surviving raw link with compatible envelope identity. Without that link/native proof, classify it unprovable, not missing; it still protects itself and may prove ingestion. Never infer correspondence by token/cost/timestamp equality.
- Codex duplicate-copy proof must match the writer's cross-source native-response rules: identical proved copies may share representation; conflicts remain audit/unprovable; unkeyed notifications cannot borrow another source's representation. Retain the relevant dedup context even if the winner's original raw was pruned.
- Compute proof, protect rows, retain context and delete eligible raw in the existing `BEGIN IMMEDIATE` transaction (per source). Forced failure rolls that source back. Retained evidence cannot retrospectively certify inventories of older already-pruned history. Row replacement and hold/progress outcomes are ENH-3770 / ENH-3745.

### Delivery Contract

Superseded 2026-10-07: the "one branch, land together, one version bump" contract is replaced by the ordered fail-closed merge points in **Delivery Plan** below. Constraints that still hold: ENH-3745 final cursor publication consumes this issue's proof; no usage-only change bumps `REBUILD_DERIVE_VERSION` or its non-usage fingerprint; no circular `blocked_by` edges; all local-editable consumer projects immediately run this checkout, so every merge to `main` must be fail-closed on its own (see the non-regression definition).

### Landing Mechanics, Interactions and Scope Note (2026-10-07)

- **Atomic multi-issue landing is not provided by the tooling.** `ll-auto`/`ll-parallel`/`ll-sprint` land one issue per branch. `parallel.epic_branches` is enabled with `merge_to_base_on_complete: true` and `verify_before_merge: false`, so an epic branch would merge to `main` unverified on completion, and an epic-worktree verify gate imports the main-tree editable install (false-negative merge blocks). Resolved 2026-10-07 by the Delivery Plan: every merge point is independently fail-closed, so no multi-issue atomic landing is needed. Do not rely on epic-branch mode.
- **ENH-3751 (done 2026-10-06) changed the refresh seams this issue edits.** `usage_refresh.refresh_raw_events` now compares canonical (history-sanitized) payloads in both stored columns, refuses per-line metadata/contract changes (`source_metadata_changed`, `usage_contract_changed`, `existing_payload_not_preserved`, `parser_changed_during_refresh`) and promotes a NULL `usage_contract` monotonically — a persisted marker is never changed. `_refresh_codex_usage_source` first-cursor certification uses the same canonical comparison. Preserve all of this; "the existing verified original-source refresh's qualification recovery" above is that NULL→marker promotion, distinct from the context-only qualification promotion on `usage_events` specified here. The retained payloads the proof reads are sanitized (and legacy rows may be plaintext, or rewritten later by `ll-session redact`): every identity key the proof relies on must be protected by `pii._protocol_rules` for the host/event type (EPIC-3562 § Shared Delivery Ownership, sanitizer identity contract), because a rewrite of an unprotected identity would read as `missing`/`unprovable`. Treat an unregistered identity path as `unprovable`, never as an absent candidate.
- **ENH-3747 coupling (verified in `lifecycle._derive_usage_incremental_conn` and `rebuild`).** Reset/catch-up delete only unheld non-live usage rows but wipe every `kind = 'usage'` search row, and `rebuild` wipes the whole kind; replay re-indexes only what it re-derives. Today only held and live observations lose search entries. Once reconciliation stops re-deriving unchanged unheld observations, every preserved observation does. Land ENH-3747 first, or in the same change with scope "every surviving committed usage observation that replay does not re-derive", and add a search-survival control to this issue's reset/catch-up/rebuild tests.
- **Scope note — decided 2026-10-07** (second Opus consult, confidence 0.74; refines the 0.72 proposal): slice into fail-closed merge points and defer hardening that has a fail-closed fallback. See **Delivery Plan**. Verified premise: usage-bearing raw is already pruned today (`_plan_raw_prune` deletes a fully aged, compacted source at or below a valid checkpoint and writes a hold marker; code re-read 2026-10-07), so the semantic prune veto and retained-reader admission are live correctness work, not post-hold-release work.

### Delivery Plan (decided 2026-10-07)

Fail-closed non-regression definition (applies to every merge point): a merge may only *subtract* trust relative to today's `main` — it never newly emits `complete`/fresh for something unproven and never mutates a protected observation without proof. It must **not** convert existing sources' freshness to permanent `unknown`: legacy cursors/checkpoints keep today's semantics until new evidence exists, and new storage starts as negative evidence only.

| Merge point | Contents | Owner |
| --- | --- | --- |
| **MP0** (independent, first) | ENH-3747 standalone: preserve search rows for every surviving committed usage observation that replay does not re-derive | ENH-3747 |
| **MP1** | **S0** checkpoint safety: skip-derive and report incomplete (never reset) on malformed/contradictory checkpoint; floor = `max(previous same-version floor, MAX(raw_events.id))`; contradiction = checkpoint > `sqlite_sequence.seq` for `raw_events` (AUTOINCREMENT, `schema.py`); changes confined to `_valid_usage_checkpoint`/`_set_usage_derive_checkpoint`. **S2a** pure `inspect_usage_candidates` correspondence proof + prune veto (including the `not capable` branch of `_plan_raw_prune`) + sanitizer-identity parity test | ENH-3745 (S0), this issue (S2a) |
| **MP2** | **S1** next append-only migration: source-local pending/failure/`sanitization_refused`/derived-boundary storage, negative evidence only. **S2b** first positive completion: ENH-3744 outcomes → ENH-3745 source completion and both cursor writers | ENH-3745 + this issue |
| **MP3** | **S3** reconciliation replacing delete-then-replay in reset/Codex catch-up/rebuild/parser refresh, below-checkpoint held retries, hold release, writer identity enforcement. Requires MP0, MP1 and MP2. **Split out as ENH-3770 on 2026-10-07** (`blocked_by` ENH-3744, ENH-3745, ENH-3747) so ENH-3732/ENH-3746 unblock after MP2 and the confidence gate scores MP1/MP2 scope | ENH-3770 |

Deferred to **Phase 2** (spec kept, non-gating, fail-closed fallback stated): (a) beyond-gap and held-source context-only audit→measured promotion with its qualification-context frontier (fallback: audit rows stay audit until a genuinely newer numeric snapshot; ENH-3746 then publishes figure `as_of` as unknown); (b) full-prefix digest continuity (ENH-3745; fallback: today's inode + 64-byte tail witness for freshness and native-offset mutation reported "mutation unavailable"); (c) the applied-value-witness beyond-prefix as-of check (ENH-3746). **Not deferred:** full-raw-source Codex requalification for fully retained, unheld sources (MP3 must keep today's per-Codex-source catch-up requalification — a later `task_complete` in a later append — or it regresses) and same-generation retained-raw mutation ordering via `source_line_no`/`source_ordinal`.

Hazards the plan must respect:
- **Version bump:** none in MP1/MP2 (they must run under the existing `_USAGE_DERIVE_VERSION`; legacy rows read as unknown). MP3 must re-justify its bump against what a mismatch replay may mutate once reconciliation exists — likely unnecessary. Bumping earlier makes every editable consumer run the legacy destructive reset against already-pruned data.
- **Do not route an invalid checkpoint into the existing reset branch** (`_derive_usage_incremental_conn`, `max_id < checkpoint`): that converts today's loud `ValueError` into a silent destructive reset plus current-version restamp.
- **Rebuild fingerprint:** any new non-pruned usage call inside `rebuild()` trips `test_enh3678`'s fingerprint and forces a `REBUILD_DERIVE_VERSION` bump (global wipe-and-replay on every consumer). Keep MP1/MP2 changes out of `rebuild()` or prove the fingerprint is unchanged.
- **No non-destructive replay before MP3:** Codex's plain `INSERT INTO usage_events` hits the unique `source_raw_event_id` index (derive rollback stall) and the Claude path reprices/overwrites by raw-ID order, so MP1/MP2 must not introduce any replay path that re-derives an already-linked raw row.
- **Prune veto cost:** decoding all aged sources under one `BEGIN IMMEDIATE` holds the write lock on multi-GB stores and blocks Stop-hook ingest. Run the veto per source (plan, delete, marker in one short `IMMEDIATE` transaction per source); dry-run still reads one snapshot and writes nothing. No size guards (history.db size is not a problem; contention is).
- **Sanitizer identity registration:** unregistered identity paths make every post-ENH-3751 source `unprovable` and silently disable prune. MP1 needs a parity test that every identity path the proof reads is protected in `pii._protocol_rules` for each host/event type, failing loudly, plus a bounded retention reason surfaced by prune.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/writers.py` — factor native recognition/coalescing/dedup, total retained-input decoding and safe observation insert/replace/no-op; resume safe additive work without clearing protection.
- `scripts/little_loops/session_store/claude_usage.py` — reuse actual producer/omission rules without promoting legacy contracts.
- `scripts/little_loops/session_store/lifecycle.py` — semantic per-source `_plan_raw_prune` veto (held-candidate iteration, pre-deletion comparison in reset/catch-up/rebuild and hold release are ENH-3770). Coordinate shared edits with ENH-3745, which owns checkpoint/cursor semantics; keep the non-usage rebuild fingerprint boundary intact.
- `scripts/little_loops/session_store/usage_refresh.py` — reuse safe preservation/replacement decisions before raw replacement; protect observations across its two-phase workflow rather than deleting them for a later rebuild.
- A small pure helper module under `session_store/` is permitted to avoid circular imports; no third-party dependency or new persisted subsystem.

### Dependent Files

- `scripts/little_loops/history_reader/usage.py` — ENH-3732 consumes the pure retained-input proof; export a tested interface without implementing quality here.
- ENH-3745 consumes bounded source outcomes and owns shared durable progress/generation facts. ENH-3746 owns retained-session admission; ENH-3747 owns search restoration.

### Tests

Extend `scripts/tests/test_bug3736_usage_replay_holds.py` and `test_session_store_incremental_usage.py`; add pure-proof parity tests. Drive real Claude/Codex fixture → ingest/derive → production prune → append/recovery → repeated catch-up/rebuild with original files removed. Test below-checkpoint work, decode failure totality, actual cross-source dedup and failure rollback; forbid file reads/pricing/write normalization inside the pure proof. Add envelope/payload/observation identity disagreements and a same-key newer candidate not yet represented.


### Documentation

Update usage/prune/rebuild/refresh contracts in `docs/reference/API.md`, retention diagnostics in `docs/reference/CLI.md` and Stage 1 hold limitations in `docs/guides/HISTORY_SESSION_GUIDE.md`. Describe safe additive held-source work, preserved historical costs, context-only qualification and recoverable parser-refresh pending state; coordinate freshness/storage wording with ENH-3745. Keep internal native keys/witnesses out of end-user diagnostics.

## Acceptance Criteria

- [ ] A current checkpoint cannot hide a missing logical candidate; its raw stays retained with `usage_derive_gap`. Coalesced snapshots and represented audit rows do not create false gaps.
- [ ] Envelope/native/observation host-session disagreements remain unprovable with retained raw/context and cannot insert measured cross-session usage or publish completion. An older matching native key alone cannot certify a newer unresolved candidate.
- [ ] Recognized Claude terminal omissions and Codex rate-limit-only notifications produce no fabricated usage or unnecessary permanent hold; unsupported/unregistered/corrupt evidence remains protected and bounded-unprovable.
- [ ] Codex lost header/model/turn/closure/adjacency context cannot downgrade or duplicate retained requests. Cross-source duplicate/conflict and unkeyed-notification cases match native writer rules.
- [ ] Source completion is separate from representation/mutation/hold presence and is handed to ENH-3745. No incomplete proof can publish complete; every merge point passes the full local suite on its own and satisfies the Delivery Plan's non-regression definition (MP1/MP2 introduce no `_USAGE_DERIVE_VERSION` bump, no `rebuild()` fingerprint change and no replay of an already-linked raw row).
- [ ] Every identity path the proof reads is protected in `pii._protocol_rules` for each supported host/event type (parity test fails loudly); an unregistered path yields a bounded `unprovable` retention reason in `prune`, never an absent candidate.
- [ ] `prune` evaluates the semantic veto per source in short `BEGIN IMMEDIATE` transactions (plan, delete, marker per source); a forced failure on one source rolls back only that source and leaves the others' result intact; dry-run matches the actual per-source plan with no writes.
- [ ] A malformed/contradictory checkpoint (including `usage_derive_raw_id` > `raw_events` `sqlite_sequence.seq`) makes derive skip and report incomplete without deleting or restamping any usage row or checkpoint.
- [ ] Protection, prune deletion and source-progress outcomes commit atomically per source; forced failures preserve rows, guards and proof. Source release cannot clear another source or wildcard protections.
- [ ] Source decode failures never disappear from proof merely because ingestion skipped their bytes. Recognized non-usage/blank lines remain harmless; prune never derives/prices and dry-run matches the actual semantic retention/context plan without writes.
- [ ] ENH-3732 consumes the pure interface on a read-only connection without source reads, derivation or pricing; statuses expose no native keys/paths.
- [ ] `python -m pytest scripts/tests/` exits 0, including paired progress/freshness tests.

## Implementation Steps

0. **MP0:** land ENH-3747 standalone first (not part of this issue's diff).
1. **MP1:** with ENH-3745's S0 (checkpoint safety, no reset on invalid checkpoint), factor and test the pure correspondence proof (`inspect_usage_candidates`) with coalescing/cross-source/decode/legacy controls; wire it into `_plan_raw_prune` as a per-source deletion veto including the `not capable` branch; add the `pii._protocol_rules` identity parity test. No mutation, no storage, no version bump.
2. **MP2:** agree with ENH-3745 on the minimal pending/failure/boundary storage (its migration); hand it this issue's candidate outcomes for the first positive source completion. Negative evidence first; legacy cursors keep today's semantics.
3. **MP3:** moved to ENH-3770 (reconciliation, held-source derivation, hold release, parser-refresh pending protection). Not part of this issue's diff.
4. Each merge point: real lifecycle, rollback and completion tests, then `python -m pytest scripts/tests/`; re-run `/ll:confidence-check` for the next slice. Phase 2 items (context-only promotion for held/beyond-gap, digest continuity, applied-value witness) are separate follow-ups.

## Scope Boundaries

No independent freshness/cursor storage, reader admission, search restoration, legacy promotion or repricing of retained observations. Conservative unprovable evidence can retain storage indefinitely; report a bounded reason rather than silently discarding it.

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-07_

**Readiness Score**: 75/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 50/100 → LOW

### Concerns
- _Superseded 2026-10-07:_ the mandatory paired landing was replaced by ordered fail-closed merge points (Delivery Plan), removing the process-only constraint. Scores above predate the slicing; rerun `/ll:confidence-check` for MP1 scope before starting (current outcome 50 is below the 65 gate).
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

- Pre-implementation review #3 - 2026-10-07 - Re-verified the Current Behavior claims against `lifecycle.py` (unguarded `int()` of the checkpoint, `max_id < checkpoint` destructive reset, `max_id == checkpoint` early return, checkpoint-only prune proof, `raw_events` AUTOINCREMENT, unique `source_raw_event_id` index, `test_enh3678` rebuild-fingerprint gate). `/ll:advise` with `claude-opus-5-5` (confidence 0.74) resolved the pending slicing decision: ordered fail-closed merge points MP0-MP3 instead of one atomic landing, Phase 2 deferrals, no version bump before MP3, per-source prune veto, sanitizer-identity parity gate, and "never route invalid checkpoint to the reset branch". Opus dissent noted: if MP3's version bump has a normalizer-output justification, dropping it would leave stale-meaning rows. Added 3 ACs, rewrote steps and the Delivery Contract. No implementation or new score claimed.
- `/ll:confidence-check` - 2026-10-07T16:32:13 - `2231707d-b3c0-49ab-b995-a5f45163a660.jsonl`
- Pre-implementation epic review - 2026-10-07 - Added landing mechanics (tooling lands one issue per branch; epic-branch mode auto-merges unverified), the ENH-3751 refresh-seam interaction and the sanitizer identity precondition for the pure proof, and the ENH-3747 search-loss coupling (verified: reset/rebuild wipe all usage search rows; preserving unchanged rows widens the loss from held/live to every preserved observation). Recorded Opus's slicing proposal as a pending decision with one verified premise correction (raw of usage-bearing sources is pruned today). No implementation or readiness claim.

- Pre-implementation review - 2026-10-06 - Reproduced complete/fresh publication after source decode skips, unchanged rebuild row/cost replacement, and Codex audit-to-measured qualification from later closure with unchanged numeric usage. Required pre-deletion reconciliation, pure prune/dry-run parity, protected two-phase refresh recovery and qualification-context witnesses. Opus consults (confidence 0.76 and 0.80) supported the changes; did not adopt harmless row-ID churn or weaker inode/tail generation proof. Existing targeted producer/retention/incremental/refresh suites: 111 passed; both revised issues passed structural checks. No implementation or readiness score claimed.

- Pre-implementation handoff review - 2026-10-06 - Reproduced a verified current-contract Claude payload becoming measured despite disagreement with the replay envelope's session. Added fail-closed identity controls, snapshot-dominance requirements and applied-value witness publication/rollback, including the older-request/later-update counterexample. Wired retry iteration to ENH-3745's source-local pending bound. Opus confidence 0.74 supported these handoffs; speculative Claude fork-copy reclassification was not adopted without fixture evidence. Targeted existing policy/lifecycle/reader/quality/workspace/dashboard/chokepoint suites: 293 passed. No implementation or readiness score claimed.

- Pre-implementation epic review - 2026-10-05 - Added the shared pure semantic-proof handoff, concrete lifecycle/refresh ownership, atomic hold-release and below-checkpoint recovery controls. A temporary-store probe with one deleted committed observation reproduced checkpoint-only pruning of all four raw rows; the missing candidate must remain protected. No implementation or new readiness score is claimed.

- Pre-implementation review - 2026-10-06 - Separated correspondence, mutation and completion; required safe additive held-source appends, total corrupt-input proof, actual cross-source Codex dedup and unchanged-cost no-ops. Assigned all shared generation/progress storage to ENH-3745 and required paired writer delivery. Opus confidence 0.72; rejected its raw-ID-only replacement rule because larger ingestion IDs can carry older source snapshots. Existing related suites: 188 passed; no implementation/readiness claim.
