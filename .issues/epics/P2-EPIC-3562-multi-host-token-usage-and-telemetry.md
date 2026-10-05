---
id: EPIC-3562
title: Multi-Host Token Usage and Telemetry
type: EPIC
priority: P2
status: open
captured_at: "2026-09-24T18:44:15Z"
discovered_date: 2026-09-24
discovered_by: link-epics
relates_to: []
---

# EPIC-3562: Multi-Host Token Usage and Telemetry

## Summary

Coordinate stored token consumption, provenance, coverage qualification, context-occupancy labeling and runtime telemetry across the eight production hosts (Claude Code, Codex, OpenCode, Pi, Qwen, Gemini, OMP, Kimi Code). Current inventory: **42 direct children plus three nested qualification children, 45 descendants: 24 done and 21 unresolved (14 open, six blocked deliveries, one deferred optional pricing decision)**. ENH-3723 is terminal by decomposition; its core child ENH-3731 is done, while ENH-3732/3733 still own quality/snapshot integration. BUG-3735's scoped wildcard repair, BUG-3736's retention Stage 1 and ENH-3748's logical channel scope are also done. Remaining work includes six evidence/delivery pairs, quality/snapshot integration, ENH-3744–3747's semantic retention/progress/reader/search followups, ENH-3730's coverage-value decision, the pricing footer and the deferred fallback decision. Native availability, ingestion support, observation provenance, coverage and occupancy remain separate contracts.

## Goal

Every canonical token-consumption figure for a production host comes from stored, normalized observations with explicit provenance and coverage qualification. Proven coverage is counted once. When overlap cannot be resolved, channel subtotals remain available for audit, but the canonical total and derived rate are unavailable rather than a potentially double-counted sum. Context occupancy is a separate context-state metric with estimate and staleness labels; it is never presented as consumption or as a `usage_events` observation.

## Scope

- **In scope**: host usage ingestion (Codex rollout, remaining hosts), Claude/Codex producer contracts, provider/version qualification, live/rollout identity and coverage selection, shared canonical eligibility, typed telemetry availability, context-hook occupancy labels, stored-usage consumers (`ll-ctx-stats`, dashboard, quality regressions), verified Anthropic pricing/default-model tables, usage-report diagnostics, heterogeneous model/batch cost attribution, and the optional fallback value decision.
- **Out of scope**: pricing for non-Anthropic models, general estimator/tokenizer accuracy, cache-marking minimums (standalone ENH-3725), occupancy monitors for non-Claude hosts, Claude live/transcript overlap reconciliation, and general session-reader isolation (ENH-3649). ENH-3703 remains a deferred child for traceability; approximate pricing is not approved by this epic until its value/policy decision is resolved.

## Composition Review

The 42 direct and three nested children cover the epic's named contracts and the explicitly retained optional pricing decision. Claude and Codex have completed stored paths, with BUG-3736's conservative retention safety floor implemented and ENH-3744–3747 owning the remaining retention/progress/reader/search defects; the six remaining hosts each have a separate evidence issue and delivery issue. ENH-3534 (done 2026-09-30) owned only shared replay/refresh infrastructure:

| Contract | Children | Remaining evidence or handoff |
|----------|----------|-------------------------------|
| Observation provenance and host attribution | ENH-3528, BUG-3542, ENH-3580, ENH-3546 | Done for proven Claude/Codex paths; new hosts retain host-specific proof gates |
| Codex rollout identity and live coverage | ENH-3532, ENH-3647, ENH-3655, ENH-3543 | Done; unresolved overlap remains audit-only |
| Stored usage freshness and consumers | ENH-3651, ENH-3656, ENH-3549 | Done for Claude/Codex; remaining hosts need their own triggers and readers |
| Remaining production hosts | ENH-3648, ENH-3534, ENH-3544, ENH-3660–3665, ENH-3671–3676 | Evidence issues prove native contracts; matching delivery issues own producer → trigger → reader |
| Context occupancy | BUG-3587, ENH-3545 | Done; general reader isolation is standalone ENH-3649 |
| Shared canonical qualification | ENH-3723 → ENH-3731/3732/3733; ENH-3748 | Parent decomposed; core and channel scope done; quality/workspace and snapshot/dashboard remain open |
| Scoped overlap correctness | BUG-3735 | Done: output narrowing preserves possible sessionless/unknown-host counterparts |
| Retained usage after pruning | BUG-3736; ENH-3744/3745/3746/3747 | Stage 1 done; semantic candidate proof, safe progress, retained-reader admission and search restoration remain open |
| Store-wide coverage scope | ENH-3730 | Separate coverage-contract design; the ENH-3731/3732 transcript-only quality scope does not depend on it |
| Pricing and action accounting | BUG-3696, BUG-3701, ENH-3719, BUG-3724 | Exact rate, alias/rank and mixed-model/batch repairs done; footer remains open |
| Optional pricing fallback decision | ENH-3703 | Deferred child; evaluate the footer before deciding implement/cancel; other implementation may proceed |

Each delivery issue's matching host evidence is its remaining hard blocker; its recorded BUG-3736 edge is satisfied. The completed core/coverage/Stage 1 controls plus ENH-3732/3733 and ENH-3744/3745 form the production usage publication gate. ENH-3746 additionally gates reader cutover/closeout; ENH-3747 independently gates epic closure. Native capture, adapter development, raw retention and isolated-fixture derivation can proceed before those delivery-stage gates. Existing reports automatically discover newly published `usage_events`, so each delivery tests that production ingress stays disabled until the shared consumer/retention matrix passes. A host with unknown evidence or no proved stored trigger stays explicitly unavailable and incomplete.

## Eight-host completion ledger

Track each host's canonical source and possible duplicate channels, native evidence, stored producer, current-session trigger, and reader verdict independently. An undecided source is not a selected canonical path. The issue IDs below are owners for remaining proofs, not claims that their work has already landed:

| Host | Canonical source / possible duplicate | Native evidence | Stored producer | Current-session trigger | Reader verdict |
|------|---------------------------------------|-----------------|-----------------|-------------------------|----------------|
| Claude Code | Transcript assistant usage; live result is not summed with it | Verified Claude 2.1.284 live/transcript captures (ENH-3546) | Stored measured observations with replay eligibility (ENH-3546/3651) | Captured Stop hook and trailing derive (ENH-3651) | Stored, host/session selected, freshness-qualified cache rate (ENH-3656) |
| Codex | Rollout requests; live/rollout overlap stays unresolved and audit-only | 0.158.0 rollout/live captures; live-to-rollout native join refuted (ENH-3532/3655) | Stored rollout requests and live identity (ENH-3532/3647) | Captured Stop hook and detached derive (ENH-3549) | Stored, coverage-qualified rate; unresolved overlap has audit subtotals only (ENH-3543/3549) |
| OpenCode | Undecided: stored step-finish parts are a candidate; live parts may duplicate them (ENH-3660) | Partial real 1.1.53 live/stored evidence; component, part identity, and real storage layout need proof | ENH-3671 | ENH-3671 | ENH-3671; incomplete |
| Pi | Undecided: no usage-bearing native source captured (ENH-3661) | Unknown; 0.84.2 probe lacked API key | ENH-3672 | ENH-3672 | ENH-3672; incomplete |
| Qwen | Undecided: assistant usageMetadata and UI event may duplicate one response (ENH-3662) | Partial real 0.24.6 pair; parser-ready source and duplicate identity need proof | ENH-3673 | ENH-3673 | ENH-3673; incomplete |
| Gemini | Undecided: stored message tokens are a candidate; repeated IDs need classification (ENH-3663) | Unknown current-version contract; configured capture and message identity needed | ENH-3674 | ENH-3674 | ENH-3674; incomplete |
| OMP | Undecided: real native source not captured (ENH-3664) | Unknown; CLI absent and existing fixtures synthetic | ENH-3675 | ENH-3675 | ENH-3675; incomplete |
| Kimi Code | Undecided: stored usage.record is a candidate; context copies and live channel need classification (ENH-3665) | Partial real 0.30.0 stored evidence; components and replay identity need proof | ENH-3676 | ENH-3676 | ENH-3676; incomplete |

Each ENH-3660–3665 evidence issue also hands off runtime provider/version evidence and an exact-match or specifically evidenced compatibility rule to its matching delivery issue. The delivered observation must match that rule using verified native evidence; an absent/unmatched provider/version or unproved identity stays audit-only/unavailable. Persist ingest-time contract/evidence on `raw_events` and reuse it on rebuild instead of substituting later machine configuration. No all-provider matrix or automatic schema extension is required.

Each ENH-3660–3665 evidence issue selects the canonical native channel/source, or records an evidence-backed no-source verdict, in its fixture README and this ledger before it can close. Record provider and CLI version, any observed copy that could duplicate a selected source, and why an excluded auxiliary channel cannot change the canonical figure. The selected path's input, output, cache-read, and cache-creation semantics, request grain/identity, and reasoning/output relation need evidence wherever they affect canonical figures. An unselected auxiliary channel may remain `unknown` only with that explicit exclusion and non-duplication reason.

`TelemetryCapability` describes native availability for fields named like normalized `usage_events` components. It does not certify stored measurement, evidence tier, or a separate reasoning-token column. A raw field that cannot yet be mapped to the named component (for example inclusive `tokens.input` with unknown cache splitting) stays `unknown`. A captured native field marked `supported` can still have unresolved normalization or identity and cannot by itself produce a measured observation. `token_reporting_summary: full` means native field availability across channels, never a measured stored total.

The fixture README records provider, version, evidence tier, inclusivity, omission behavior, and reasoning/output relationship for each metric/channel. Source-cited producer evidence is provisional: a source-only typed-map entry stays `unknown` with a source-cited note until captured native evidence supports `supported` or affirmative evidence supports `unsupported`. A host-level `supported` claim needs at least one captured provider/version case and a note naming its scope; it does not certify every provider. Table-backed `TelemetryCapability.note` entries cite stable `README:<row-id>` evidence IDs for the shared test.

Record reasoning inclusion in the README and the `output_tokens` note; an unresolved output/reasoning relation prevents a measured normalized output figure. The first of ENH-3660/3665 to prepare a closing change adds one shared, parameterized README-to-map evidence test and table format; ENH-3665 owns it if both proceed together. The test covers only the six remaining hosts with a structured table, and each later evidence issue adds its host's rows. Claude/Codex and not-yet-captured hosts retain their existing verification until their tables exist. A nonzero-cache capture is required to claim a supported cache component's measured semantics when cache behavior affects a canonical figure or rate. It is not required for an evidence-backed unsupported cache component.

Before closing the epic, replace each owner entry with an evidence-backed verdict: implemented with a stored producer, actual after-usage trigger, and freshness-qualified reader for every supported in-scope metric; or explicitly unavailable where native absence is proved. Failed authentication, absent CLI installation, and zero-only samples are `unknown`, never evidence-backed no-source verdicts. Partial native support is recorded per metric/channel. Supported components may be stored with missing components null as audit observations. Under the current row-level provenance contract, a row missing a required canonical component remains `unknown`, even if its present fields are proved; dependent canonical totals and rates remain unavailable. A partial-host delivery issue may close after it stores proved components with replay and freshness qualification and emits an explicit unavailable diagnostic for dependent canonical figures, with the ledger explaining that audit-only disposition. A host delivery issue may propose a separately tested component-level qualification contract if it needs a measured component figure from such a row. A missing trigger for a supported current-session path, an in-scope `unknown`, or an open/deferred host child keeps the epic open. Each host delivery issue owns retiring its direct transcript fallback after a proved stored cutover or replacing it with an explicit unavailable diagnostic after a proved native absence or evidence-backed partial support. Close the epic only when all retained descendants, including scoped-overlap correctness, shared qualification, pricing/accounting and ENH-3703's optional decision, are `done` or `cancelled`, with no unresolved in-scope verdict; a cancellation requires the ledger to explain why no work remains. If intended scope shrinks, revise this goal and ledger explicitly.

## Impact

- **Priority**: P2 — six production hosts still lack proved stored usage paths; silent accounting errors remain possible if native duplicates or partial fields are guessed.
- **Effort**: Large — 21 unresolved descendants span native evidence/delivery, shared qualification, scoped coverage, retained usage, pricing/accounting and one optional decision; shared replay baseline is done.
- **Risk**: Medium — accounting errors are silent; mitigated by fixture-backed contracts and conservative unresolved defaults.

## Children

**Terminal direct children (23)**

- **ENH-3528** — Label token provenance per observation in ll-ctx-stats and exports
- **BUG-3542** — Attribute raw-event backfill to each verified source host
- **ENH-3580** — Carry usage provenance into shareable export
- **BUG-3587** — Separate invocation consumption from context occupancy
- **ENH-3532** — Ingest historical Codex rollout usage
- **ENH-3543** — Select qualified live/rollout coverage
- **ENH-3544** — Type runtime telemetry availability
- **ENH-3545** — Label occupancy estimates and measurement staleness
- **ENH-3546** — Establish measured Claude producer provenance
- **ENH-3549** — Read Codex stored usage for cache rate
- **ENH-3647** — Carry Codex live thread/invocation identity
- **ENH-3648** — Survey six remaining host contracts
- **ENH-3651** — Incrementally derive current-session usage
- **ENH-3655** — Refute the native Codex live-to-rollout join
- **ENH-3656** — Read Claude stored usage for cache rate
- **ENH-3534** — Shared infrastructure for remaining-host ingestion
- **BUG-3696** — Exact Sonnet 5.5 pricing and alias/rank/price coverage
- **BUG-3724** — Model/batch/date contribution accounting
- **BUG-3701** — Sonnet 5.5 alias/rank correction
- **ENH-3723** — Closed by decomposition; ENH-3732/3733 still open
- **BUG-3735** — Preserve wildcard overlap before scoped output narrowing
- **BUG-3736** — Retention Stage 1: preserve held usage through replay
- **ENH-3748** — Logical-channel acquisition scope

**Open evidence children (6)**

- **ENH-3660** — Prove OpenCode cache/reasoning and real source-layout semantics
- **ENH-3661** — Capture Pi with configured model access
- **ENH-3662** — Prove Qwen live/cache, parser-ready source and duplicate semantics
- **ENH-3663** — Capture versioned Gemini usage and repeated-ID mutation identity
- **ENH-3664** — Capture real OMP usage
- **ENH-3665** — Prove Kimi components and copied-record replay identity

**Blocked host delivery (6)**

- **ENH-3671** — OpenCode stored usage (remaining blocker ENH-3660)
- **ENH-3672** — Pi stored usage (remaining blocker ENH-3661)
- **ENH-3673** — Qwen stored usage (remaining blocker ENH-3662)
- **ENH-3674** — Gemini stored usage (remaining blocker ENH-3663)
- **ENH-3675** — OMP stored usage (remaining blocker ENH-3664)
- **ENH-3676** — Kimi Code stored usage (remaining blocker ENH-3665)

All six preserve the satisfied BUG-3736 edge and the shared delivery-stage publication/cutover contracts without new whole-issue scheduling edges to quality, snapshot or retention followups.

**Open direct retention, coverage and pricing (6)**

- **ENH-3744** — Shared semantic candidate proof, safe hold release and held-source derivation
- **ENH-3745** — Validated processed floor and per-source completion/freshness
- **ENH-3746** — Retained-source admission in the stored cache-rate reader
- **ENH-3747** — Restore retained/live usage search evidence across rebuild/reset
- **ENH-3730** — Coverage-domain value/design decision; not a publication prerequisite
- **ENH-3719** — Contribution-aware unpriced-model footer/docs; independent lane

**Deferred optional decision (1)**

- **ENH-3703** — Evaluate family-prefix approximation after ENH-3719; implement or cancel with rationale before closure, unless scope is explicitly revised

Standalone ENH-3649 (reader isolation/diagnostics) is done. Standalone ENH-3725 (cacheable-prefix minimum) relates to completed EPIC-2456. Neither is counted here.

## Nested qualification owners

These remain children of decomposed ENH-3723:

- **ENH-3731** — Done: shared core/source qualification; transcript acquisition delivered separately by done ENH-3748
- **ENH-3732** — Open: quality/workspace proof and per-metric baselines; remaining prerequisites ENH-3744/3745, completed ENH-3731/3748 and BUG-3736 edges retained
- **ENH-3733** — Open: snapshot/dashboard qualification; core prerequisite satisfied, can proceed independently

## Implementation Order and Readiness

1. **Shared baseline and policy:** ENH-3534, ENH-3731, BUG-3735/3736 and ENH-3748 are done. ENH-3733 can implement snapshot/dashboard qualification now against the landed `UsageQualification` API. ENH-3744 owns pure native candidate/correspondence proof, atomic hold release and replay/retry; ENH-3745 owns validated processing floors and source-local completion/freshness, with a single shared boundary-storage owner if a migration is needed. ENH-3732 consumes both handoffs before quality integration. ENH-3746 develops retained-reader admission independently and composes with ENH-3745 before reader closeout. ENH-3747 restores search independently. Revised ENH-3732/3733 historical scores were cleared; rerun verification/confidence for their actual contracts. ENH-3730 remains separate value/design work. Native evidence/adapters/raw retention and isolated-fixture derivation may proceed.
2. **Independent pricing lane:** BUG-3696's exact Sonnet 5.5 price/coverage change and BUG-3724's mixed-model/batch accounting repair are done. BUG-3701's alias/rank correction is also done. ENH-3719's contribution-aware footer/docs can proceed independently of native evidence; preserve the completed contribution-accounting contract. Keep ENH-3703 deferred until footer evaluation supports an implement/cancel decision; it does not block other implementation.
3. **Host evidence:** ENH-3660–3665 prove native metric, grain, identity, provider/version qualification and canonical source/no-source disposition, plus a candidate after-usage trigger and source-write timing. OpenCode and Kimi proceed first with their partial real captures. Pi, Qwen, Gemini and OMP retain unsatisfied external access gates; failed access remains unknown, never unsupported.
4. **Host delivery:** when its matching evidence contract is sufficient, each ENH-3671–3676 issue develops its real native adapter, ingest-time qualification, replay/update handling, trigger and freshness proof. Other hosts' evidence does not block it. OpenCode needs real-tree partial/final/revised/add/replacement and source-loss tests and recovery; Gemini needs changed-token repeated-ID replacement-versus-new-request tests and recovery. Source disappearance retains historical usage and cannot certify a fresh zero; invalidation requires an evidenced authoritative retraction. Coordinate shared seams under the ownership rule below.
5. **Production publication and reader cutover:** complete the shared ENH-3732/3733 and ENH-3744/3745 gates, retain the completed core/coverage/Stage 1 regressions, and pass ENH-3746 with combined freshness controls before reader cutover/closeout. Each host tests disabled production ingress until publication is safe. Add the host's qualified/partial/mismatch cases to ENH-3723's source/snapshot/quality/session-reader matrix and prove full/incremental/repeated-refresh parity before enabling its new production usage derivation, stored cutover or closeout. A mismatch or absent runtime provider/version remains audit-only/unavailable, not measured from a broad host capability.
6. **Closeout:** an evidence-backed absent/partial path must settle the direct-fallback behavior and explicit unavailable diagnostic. An in-scope unknown or missing supported-path trigger keeps the epic open. All retained children, including the optional implement/cancel decision, require done/cancelled verdicts or an explicit scope revision before closure; cancellation must explain why no work remains.

## Shared Delivery Ownership

For ENH-3671–3676, the first delivery issue to land a required shared `refresh_usage_source`, `_derive_usage_incremental_conn`, `usage_source_freshness`, `usage_stop.handle`/`_run_usage_trigger` dispatch or shared-test extension owns that change. Later hosts extend host-keyed dispatch, add their cases and rebase; they do not duplicate the shared seam. Each delivery owns its native adapter, integration and end-to-end proof. ENH-3731 owns shared canonical eligibility, with ENH-3732/3733 owning quality and snapshot integration; the host evidence issues own provider/version-scoped native contracts. The separate ENH-3660/3665 rule continues to govern the common README-to-typed-map evidence test.

**Ingress routing:** that first-lander ownership also covers host-keyed contract resolution for historical `_backfill_raw_events`, current `refresh_usage_source`/host equivalent, parser-upgrade `usage_refresh.refresh_raw_events` and direct `_iter_usage_replay_records`. Test matching qualification across supported routes and explicit rejection of unsupported layouts. Preserve unchanged ingest-time markers on parser refresh; later contract/parser changes do not silently requalify old unknowns. Failed derive/rebuild cannot become fresh merely because a later source read is unchanged.

**Quality raw-evidence handoff:** every selected host contract declares its acquisition channel, logical candidate/key, intentional omissions, required source context and known non-usage kinds. ENH-3744 owns the shared pure recognition/coalescing/correspondence interface; ENH-3745 owns the validated retained-state progress predicate. Prune/replay and read-only quality consume these shared semantics, never independent candidate algorithms. ENH-3732 checks all candidates before certifying an observed session, treats unregistered/unproved raw evidence as unavailable, and reads proof/contributors consistently per member. Host deliveries extend this pure retained-evidence seam before publication; no file reads or derivation occur in the quality helper.

**Source retention and freshness:** missing, empty, unreadable, retention-pruned or compacted originals retain committed historical observations and their ingest-time qualification, with a diagnostic and stale/unknown current-source freshness. As-of proof does not advance and dependent current-session rates cannot appear as a fresh zero. Only native evidence of authoritative retraction within a present, valid source permits invalidation; otherwise retain recorded usage and mark current-source freshness stale/unknown. BUG-3736 implements the conservative Stage 1 replay/retention floor. ENH-3744 supplies semantic representation proof and atomic hold release; ENH-3745 prevents skipped held work from advancing source-local completion. Both remaining followups are publication gates. ENH-3746 admits verified source-attributed retained usage without treating a cursor or hold as session identity; ENH-3747 search restoration is a separate closure gate. This extends the conservative ENH-3534 baseline without requiring a retraction subsystem.

**As-of compatibility and mutable witnesses:** otherwise qualified Claude/Codex numeric as-of values remain available with existing freshness/lag/as-of metadata; stale/unknown values are never described as current. Component-incomplete rates are unavailable even if some selected rows are complete. OpenCode's witness covers its usage-bearing part set; Gemini's covers the full message collection, including earlier counter revisions with an unchanged final record. A source mutation during refresh cannot certify a fresh inconsistent snapshot.

**Qualification rule:** ENH-3723 evaluates all coverage-selected contributors for each aggregate figure; an ineligible contributor makes the full figure unavailable with a reason while audit subtotals remain labeled. Cost/rate prerequisites cannot be bypassed by an already numeric stored cost. **Policy decided 2026-10-04 (ENH-3723):** legacy NULL is treated exactly like explicit unknown (audit-only, labeled audit subtotals; no discriminator column). Complete `estimated` rows are admitted in general consumption reports with `estimated`/`mixed` labels, cache rate stays measured-only, and quality baselines/verdicts require an all-measured composition. Local measurement showed no published figure changes outside quality windows: unscoped reports are already coverage-blocked by the store-wide `ambiguous_cross_channel` gate. Host deliveries must not decide this independently.

**Action accounting handoff:** BUG-3724 is done with durable per-contribution model/batch/date attribution. Preserve its observed time/basis and effective pricing date. Buckets distinguish model, batch mode and pricing date, with the documented completion-date fallback for absent event times and legacy rows. ENH-3719 consumes the landed contract and makes the footer inspect every contribution, preserves single action/iteration accounting, and tests an earlier unpriced model followed by a known last model.

## Schema coordination

`SCHEMA_VERSION` is 59, including BUG-3736's `usage_replay_holds`. ENH-3745 owns any necessary durable source-progress extension; ENH-3744 writes through that shared interface rather than allocating a competing migration. ENH-3532, ENH-3647, ENH-3546, and ENH-3651 have already landed their shared replay, identity, eligibility, and derive-checkpoint migrations. A host delivery issue that needs a new column takes the next append-only version in landing order. Attributes needed after rebuild must survive on `raw_events`; source/request identity, verified host attribution, and reader-visible derive freshness must remain consistent through incremental derive and full rebuild.

## Shared-consumer notes

- `quality_regressions.py` and `agent_quality.py` remain channel-pinned so newly identified Codex rows do not silently change existing aggregates. ENH-3731/3732 own their recorded qualification, transcript-scoped coverage, member-local raw-to-usage completeness and per-metric measured trend contracts, including observed-zero baselines. The settled ENH-3723 policy and these children's implementation contracts are authoritative; original-source freshness and ENH-3730's store-wide ambiguity redesign remain separate.
- `select_usage_coverage` reconciles candidates for a verified host/thread pair before report filters. `select_usage_observations` delegates to the same policy. An ID-only call is rejected.

## Cross-Issue Acceptance Criteria

- [ ] ENH-3744/3745 prove semantic candidate completeness, missing-context failure, atomic proof/prune/hold transitions, validated same-version processing floors, source-local cursor completion and recovery below an advanced checkpoint. No source hold or allocation high-water alone certifies work. Pure read proof and writer recognition agree.
- [ ] ENH-3746 preserves the existing payload/absence contract and host/session metric population after raw pruning/source loss; retained as-of values carry stale/unknown freshness when appropriate, and hold/cursor-only controls cannot admit a session. Combined ENH-3745 freshness controls pass before reader cutover/closeout.
- [ ] ENH-3747 restores retained/live usage search without stale/duplicate entries, changed indexed-channel scope or failed-replay half commits; it is required for epic closure independently of numeric publication.
- [x] BUG-3735 prevents host/session output narrowing from hiding possible wildcard overlap, and composes with declared transcript acquisition and report filters. Its scoped-reader controls pass before any remaining-host usage publication or reader cutover.

- [ ] ENH-3731/3732/3733 implement the recorded ENH-3723 legacy-NULL/estimated/mixed policy, preserve audit subtotals and safe qualification labels, and prove source/snapshot/dashboard/quality/session-reader parity for measured, estimated, mixed, explicit unknown and legacy rows across complete/partial components and resolved/unresolved coverage. Its quality scope/completeness/baseline controls pass before enabling production derivation of new remaining-host usage rows. Existing checked ENH-3543 coverage work below is baseline evidence, not certification of this new eligibility matrix.
- [ ] Each remaining-host runtime provider/version matches a captured contract or an explicitly evidenced compatibility rule; absent/mismatched evidence and unproved identity remain audit-only/unavailable. Ingest-time qualification survives raw replay/rebuild and cannot be promoted by a later CLI/provider change.
- [ ] OpenCode part finalization/revision/add/delete and Gemini repeated-ID token changes have ordered mutation tests, correct replacement/counting, full/incremental parity, stale/unknown failure behavior and successful recovery.
- [ ] Exact Sonnet 5.5 pricing, required alias/rank/docs corrections and missing-price diagnostics pass their lane's checks. The completed BUG-3724 exact model/batch/date contribution accounting remains intact. ENH-3703 records its implement/cancel decision without blocking other implementation.
- [x] Source usage/cost/waste and built-in snapshot/dashboard aggregates share the completed coverage-selection and audit-subtotal baseline (ENH-3543). Core provenance qualification is done in ENH-3731; quality/snapshot parity remains the open ENH-3732/3733 gate above.
- [x] Canonical token components, event/request identity, run/state attribution, and report-window rules remain consistent through ingest, rebuild and export (ENH-3532/3543/3647).
- [x] Legacy/unverified producer evidence is never promoted by rebuild; missing originals/usage remain explicit rather than fabricated measurements (ENH-3546 and ENH-3534's shared refresh checkpoint).
- [x] Adding session identity to live or rollout rows never silently changes an existing aggregate (`quality_regressions` and `agent_quality` pins; ENH-3532/3647).
- [x] A Codex observation is counted once across forks, resumes, paginated threads, re-emitted notifications and both `token_usage_record`/`token_count` event shapes; `session_id` means the same thing in ENH-3532, ENH-3647 and ENH-3549.
- [x] Mixed/partial Codex event streams never lose old-shape-only usage through file-wide suppression; overlapping old/new records are counted once only when request coverage is proven, otherwise remain explicitly unresolved (ENH-3532).
- [x] First-enable and normalizer-version catch-up materialize previously ingested raw usage in either ENH-3532/ENH-3651 landing order; incremental rows and their checkpoint commit atomically, rebuild preserves the checkpoint contract, and Codex rollout reaches the stored reader without a per-turn full rebuild (ENH-3651/3532/3549).
- [x] ENH-3651's committed derive progress gives ENH-3656/ENH-3549 an as-of boundary for the selected session; a new append followed by a failed/skipped worker cannot silently look fresh.
- [x] Claude stored usage and the direct reader are compared on repeated assistant records, partial components and missing identity before ENH-3656's cutover; any deliberate numeric correction is documented and tested, and full/incremental replay agree on observation identity.
- [x] ENH-3656 can ship the Claude stored reader after ENH-3651 without waiting for Codex ingestion; ENH-3549 retires `_codex_cache_usage` only after a real Codex adapter trigger → ingest → derive → read test.
- [x] Unresolved overlap leaves canonical totals and derived rates unavailable while preserving per-channel audit subtotals; source and built-in snapshot/dashboard aggregates apply the same rule.
- [x] A selected session is qualified by verified host plus thread ID; same-ID rows from another host or unverified host attribution cannot enter its cache-rate figure (ENH-3543/3549).
- [x] Context consumption and occupancy have separate semantics (done in BUG-3587); baseline freshness survives estimate updates and fallback output exposes it (ENH-3545).
- [ ] ENH-3660–3665 select each host's canonical source or prove no native source, classify possible duplicate channels in the ledger, then record per-metric/channel native verdicts and replay identity with versioned evidence. Failed authentication, absent CLI access, or zero-only samples remain `unknown`, never `unsupported`. Source-only evidence stays a provisional README tier and typed-map `unknown`; no evidence issue closes with an unresolved in-scope canonical-path verdict. One shared README-to-map evidence test covers all six hosts.
- [ ] For each supported remaining-host path, its matching ENH-3671–3676 issue proves discovery of the real native source layout → stored qualified observation → actual current-session trigger → incremental derive → host/session-selected, freshness-qualified reader; replay and duplicate sources do not inflate canonical totals. Each delivery owns its native integration and regression tests under Shared Delivery Ownership; shared canonical eligibility belongs to ENH-3731, with ENH-3732/3733 consumer integration.
- [ ] Every production host has an evidence-backed terminal ledger verdict, including partial-component and direct-fallback disposition; in-scope unknown capability, absent trigger, or open/deferred per-host child leaves the epic open.

## Review Notes

Pre-implementation review 2026-10-05 (current pass), `/ll:advise` with Opus (confidence 0.72): reviewed all 19 previously unresolved descendants. Reproduced raw-prune → replay loss in separate temporary databases: four raw rows and two measured Claude observations became zero raw rows and two retained observations after prune, then zero observations after either full rebuild or incremental catch-up. Added P1 BUG-3736 as the shared retention/pruning owner and ENH-3732 integration prerequisite, and included it in all six publication gates. Tightened quality gap-before-usage ordering, unregistered-contract failure, coherent member proof and diagnostic precedence; extended all six evidence/delivery handoffs with channel/logical-candidate and affirmative no-source branches. Reconciled snapshot Option C instructions, logical legacy-channel pair selection, invalid audit arithmetic, empty-selection reasons and optional fallback contribution accounting. Opus's checkpoint redesign was rejected because the production deriver already uses BEGIN IMMEDIATE; local raw IDs already use AUTOINCREMENT. Kept the accepted member-additive workspace population, recorded qualification policy and snapshot version home. No implementation or fresh confidence score is claimed. Current inventory: 37 direct + three nested children, 20 terminal records and 20 unresolved. Native external gates, optional deferred decision and ENH-3731's 63/65 confidence gap remain.

Current-pass verification: all 19 touched issue files pass structural formatting, design and private-reference checks; references resolve and the dependency graph is acyclic. EPIC-3562's direct-child consistency check has no discrepancies. All six evidence/delivery pairs carry the matching channel/candidate handoff and conditional no-source branch. Production temporary-database probes reproduced BUG-3736 in both replay modes; no implementation or new full-suite baseline is claimed.

Pre-implementation review 2026-10-05, `/ll:advise` with `claude-opus-5-5` (confidence 0.74): reviewed all 18 previously unresolved descendants and captured BUG-3735 after synthetic same-host/sessionless and unknown-host probes reproduced scoped false certification. Updated all six deliveries to require ENH-3731/3732/3733 plus that repair before publication, keeping native capture/adapters/raw work independent. Added shared numeric validity, policy-version/result and safe-reason handoffs; resolved snapshot scope/bucketing/label/cost and rate-scope questions; clarified logical derive gaps and workspace diagnostics without changing the documented member-additive population. Reconciled ENH-3719 with completed contribution accounting. ENH-3730 now has a conservative domain/value decision: current read-only live distribution is 33 host-wildcard and 262 verified-host/unproved-session rows, so restored all-history availability is not promised. Opus’s cross-member quarantine and empty-snapshot stamping suggestions were not adopted because they change existing population/version decisions; labeled additive scope and empty-no-figures controls address their risks. Current inventory is 39 descendants, 20 terminal records and 19 unresolved. No implementation or fresh confidence pass is claimed. Verification: all 14 touched issue files pass structural formatting and private-reference checks; all dependency IDs resolve; design checks pass for BUG-3735 and ENH-3730/3731/3732/3733. Existing focused coverage/snapshot/Claude-Codex stored-reader/cost/workspace baseline: 49 passed. ENH-3731 readiness still exits 1 with persisted outcome confidence 63 below 65; rerun its confidence gate for the revised contract.

ENH-3723 review 2026-10-04, `/ll:advise` with `claude-opus-5-5` (confidence 0.72): carried the settled policy and channel decision into its implementation contract, specified member-local stored derive proof for quality/workspace reports, and replaced zero-as-missing baseline semantics with explicit eligibility. Source freshness remains separate. Focused baseline suite: 101 passed; specification changes only, with a fresh confidence gate still required. Linked independent ENH-3730 and reconciled the current child inventory (35 total, 18 done); BUG-3696/3724 are already done. Full qualification rules remain in ENH-3723.

Pre-implementation follow-up review 2026-10-04, `/ll:advise` with Opus (confidence 0.72): audited all 18 unresolved children; no scope drift or >14-day stall found. Updated ENH-3723 and all six deliveries so shared qualification gates production usage publication, rather than only reader cutover; named all ingestion routes and preserved unchanged ingest-time evidence. Temporary-database probes confirmed an unknown/partial row currently becomes 16 tokens and fully priced in `agent_quality`, and stale/source-missing Claude retains a 77% as-of rate. Assigned quality/dashboard and complete-denominator controls to ENH-3723 while preserving existing as-of presentation. Added OpenCode/Gemini whole-source mutation witnesses and BUG-3724's existing `TokenUsage.observed_at` pricing-date handoff. Tightened the historical baseline checkbox and exact-attribution closeout wording. Pricing/default sources were rechecked against the official pages; BUG-3696/3701, ENH-3719/3703 and native evidence/access gates need no new scope. No new child, status/dependency change or implementation is claimed; legacy/estimated policy, the pricing confidence gate and external access remain prerequisites.

Pre-implementation review 2026-10-04, `/ll:advise` with Opus (confidence 0.76): reviewed all 18 unresolved children against current code and their handoffs. Tightened aggregate qualification, source-loss versus authoritative-retraction semantics, exact mixed-action closeout and contribution-aware footer coordination in existing owners; corrected ENH-3703's body status. No new child or dependency edge is needed. ENH-3723's legacy policy was subsequently decided on 2026-10-04 after scoped report-impact measurement (see that issue), BUG-3696 still needs its fresh confidence gate, and the four existing external-access gates remain unsatisfied. Pricing/default claims were rechecked against the official pricing and model-configuration pages on 2026-10-04. No implementation is claimed.

Pre-implementation follow-up 2026-10-03, after `/ll:advise` with Opus: added ENH-3723 for the reproduced source/snapshot qualification gap and explicit legacy policy decision; added BUG-3724 for reproduced last-model/batch pricing; all six evidence/delivery pairs now require durable runtime provider/version qualification. Strengthened OpenCode and Gemini mutation/recovery tests, centralized six-host seam ownership, and reconciled counts/order/closure and the independent pricing lane. ENH-3703 stays under this epic at the user's direction, deferred for footer evaluation and an implement/cancel decision. Standalone ENH-3725 tracks the verified Sonnet 5.5 cache minimum without reopening EPIC-2456. BUG-3701's coding example is a required edit. BUG-3696's stale confidence scores still require its configured gate to run before implementation. These are issue-specification changes only.

Pre-implementation issue revision 2026-09-29: split ENH-3534 to shared replay/refresh work, created host delivery children ENH-3671–3676 with one evidence blocker each, and assigned their producer/trigger/reader ownership in the ledger. ENH-3660–3665 now require per-metric/channel evidence verdicts and explicit access blockers; Qwen needs a parser-ready native capture. A Sonnet follow-up tightened the in-scope unknown, partial-support, missing-trigger, and direct-fallback closeout rules. Counts, implementation order, and schema version reflect the current issue graph and code. No host ingestion implementation is claimed by these issue edits.

Implementation review 2026-09-29: the full local suite passed (27,525 passed, 301 skipped); lint, format, host-map and private-reference verification passed. The configured mypy command is blocked by this environment's untyped `ruamel` dependency and older mypy/dependency stubs; no type-check pass is claimed. Eleven more epic children reached done, as did standalone ENH-3649. Six native producer contracts remained unproved; ENH-3534 was unresolved at that checkpoint, and the epic remained open.

Pre-implementation review 2026-09-24 applied to specifications only. Review 2026-09-28: refreshed stale child statuses (ENH-3580, BUG-3587 done); closed ENH-3532 gates 2–3 from fixtures and proposed a gate-1 key; split ENH-3543 → ENH-3647, ENH-3534 → ENH-3648, ENH-3549 → ENH-3649; added schema coordination, the `quality_regressions` consumer and ENH-3549's current-session freshness gate. Historical confidence scores do not certify the revised scopes. Child frontmatter is authoritative for status/progress.

Review 2026-09-29 (corpus check of `~/.codex/sessions` plus an opus consult): ENH-3532's `(host, session_id, ordinal)` key collides on forks and paginated threads and cannot dedupe duplicate notifications; newer Codex writes `token_usage_record` alongside `token_count`; `agent_quality._usage_totals` needed the same channel pin as `quality_regressions`; the ENH-3543 spike moved to step 1; ENH-3549 staged Claude-first with the hook-driven ingest split out; added missing `blocks` backlinks on ENH-3532 and normalized ENH-3549 to `blocked_by`. Fixtures are `codex-cli 0.152.1` while local sessions come from 0.154–0.158 alphas, so every Codex contract needs a current-version fixture.

Follow-up review 2026-09-29: assigned shared incremental derivation and first-enable catch-up to ENH-3651, with Codex normalization remaining in ENH-3532; replaced file-wide `token_count` suppression with a mixed-stream evidence gate; fixed the thread/root ID contradiction; required host-qualified session filtering; and removed ENH-3549's superseded freshness options. These are specification changes only, and the producer fixtures, join spike and checkpoint design remain implementation gates.

Readiness follow-up 2026-09-29 (Sonnet critique and issue-graph check): ENH-3655 now owns the unblocked join spike, and ENH-3656 owns the Claude-first stored-reader stage. ENH-3543 and ENH-3549 retain hard dependencies for their production selector and Codex cutover. ENH-3651 supplies a selected-session as-of proof with its shared derive and Claude trigger; ENH-3549 owns the later Codex runtime trigger. A stale stored value and a manually driven Codex fixture cannot certify current-session freshness. Removed ENH-3549's superseded option-B acceptance text.

Review follow-up 2026-09-29: added Claude numeric-parity and transcript-identity gates, made unresolved sums audit-only rather than canonical rates, required an explicit eight-host closure verdict, and added ENH-3543 as a Codex reader-cutover blocker. General session-reader isolation (ENH-3649) is now standalone; its empty-discovery diagnostic still coordinates with ENH-3656. No implementation is claimed by these specification edits.

## Status

**Open** | Created: 2026-09-24 | Priority: P2

## Review notes (2026-09-30, `/ll:advise` Opus)

- Pi (ENH-3661), Qwen (ENH-3662), Gemini (ENH-3663) and OMP (ENH-3664) carry a structured `gate: external` (`satisfied: false`, owner `user`) so autodev defers them at dequeue; `status: blocked` is deliberately not used because autodev does not skip `blocked`. Flip `satisfied: true` when access is provided.
- Sequencing: Kimi (ENH-3665 → ENH-3676) and OpenCode (ENH-3660 → ENH-3671) first; the gated hosts follow when access exists.
- Evidence tiers: source-cited producer evidence is a distinct lower tier (provider-keyed and version-pinned in the fixture README, with a typed-map `unknown` note until native capture); it never satisfies a delivery issue's Completion Rule. A supported cache component affecting a canonical figure or rate needs captured nonzero-cache semantics before that figure is measured; an evidence-backed unsupported cache component does not.
- Partial support: a component may be stored null only when it is evidence-backed unsupported or the ledger names it outside the canonical path — never while `unknown`. Unblocking a host on a partial contract needs an explicit per-host ledger revision here.
- The first of ENH-3660/3665 to prepare a closing change owns the shared parameterized fixture README-to-typed-map evidence gate; ENH-3665 owns it if both proceed together. Each other host adds its rows. `test_verify_host_map.py` currently checks completeness only.

## Pre-implementation specification follow-up (2026-09-30)

- OpenCode 1.1.53 on this machine stores separate session, message, and part JSON files under its data storage tree, while current session discovery assumes `~/.opencode/projects/*.jsonl`. ENH-3660 must capture the actual layout; ENH-3671 owns a real source adapter and storage-tree fixture before claiming end-to-end coverage.
- ENH-3660–3665 now own explicit canonical-source or no-source and duplicate-channel decisions. Their README records source-cited versus captured evidence and reasoning/output semantics; the typed map represents native metric-field availability and keeps source-only claims `unknown` until native capture.
- ENH-3671–3676 own any extension to the completed ENH-3534 baseline, including source refresh, incremental derivation, freshness, and runtime trigger integration. Partial rows remain audit-only under the present row-level provenance contract.

---

## Session Log

Pre-implementation review 2026-10-05, `/ll:advise` with `claude-opus-5-5` (confidence 0.70): reviewed all 21 unresolved descendants against the landed core/channel/scoped-coverage/Stage 1 code. Reconciled 42 direct + three nested children (24 done), schema 59 and active readiness prose. Expanded ENH-3744–3747 with shared pure proof, source-local progress/validation, retained-reader payload/admission and search ownership, steps and regression controls; aligned quality/workspace and all six evidence/delivery handoffs. Kept snapshot/footer and search scheduling independent and optional decisions/access gates intact. Opus's suspected source-narrowed rate was refuted: the reader's source check is admission only, followed by full host/session coverage selection. Its blanket legacy-hold quality exclusion would change recorded retained-as-of policy, so actual pending/unprovable candidate checks remain authoritative. Search `ref` is model, not usage ID; restoration follows actual writer keys. Temporary-store probes reproduced retained-reader absence (77% before prune), false derive-pending after catch-up, malformed-checkpoint `ValueError`, search loss (two to zero) and pruning with an unrepresented candidate. Focused landed-code baseline: 147 passed. Verification: all 20 touched issue files pass structural format checks and private-reference checks; all seven revised design contracts pass the design gate; epic child consistency has no discrepancies, references resolve and the dependency graph is acyclic. The 147-test focused baseline passes. No implementation or fresh readiness score is claimed; ENH-3732/3733 need fresh verification/confidence for the revised contracts.

- Pre-implementation epic review - 2026-10-05 - Reviewed 19 unresolved descendants and added reproduced P1 BUG-3736. Updated 19 issue files, repaired direct/nested child documentation, and tightened shared quality, native handoff, no-source, snapshot and optional pricing contracts. Inventory is 40 descendants (20 terminal, 20 unresolved); implementation and new confidence passes are not claimed.

- Pre-implementation epic review - 2026-10-05 - Reconciled 35 direct + 3 nested children (20 terminal records, 18 unresolved). ENH-3723 was decomposed, not implemented; ENH-3731/3732/3733 jointly gate production usage publication. BUG-3701 is done. Reviewed all unresolved descendants; no off-theme child or >14-day inactivity stall was found. Native access gates and the human-deferred optional pricing decision remain unchanged.
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:31 - `b32e58bb-e3b8-4048-9c71-1c2f63665ce9.jsonl`