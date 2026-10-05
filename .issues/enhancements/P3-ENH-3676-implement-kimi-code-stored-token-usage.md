---
id: ENH-3676
type: ENH
title: Implement Kimi Code stored token usage
priority: P3
status: blocked
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:24:22Z'
parent: EPIC-3562
labels:
- observability
- multi-host
- usage-ingestion
blocked_by:
- ENH-3665
- BUG-3736
relates_to:
- ENH-3723
- ENH-3731
- ENH-3732
- ENH-3733
- BUG-3735
- BUG-3736
- ENH-3744
- ENH-3745
- ENH-3746
---

# ENH-3676: Implement Kimi Code stored token usage

## Summary

Deliver Kimi Code token usage from a proved native source to stored, normalized observations and a freshness-qualified session reader. ENH-3665 owns the producer contract; ENH-3534 owns shared replay and refresh infrastructure. This issue owns Kimi Code parsing, identity, normalization, current-session trigger, capability entries, and reader cutover. It has no dependency on another host's evidence.

## Current Behavior

Real 0.30.0 stored usage.record entries coexist with matching context.append_loop_event copies. Input components and a durable request key remain unproved; the sampled live stream had no usage. The shared usage Stop worker and ll-ctx-stats stored cache-rate path currently serve Claude and Codex only. Other hosts retain the direct transcript fallback where it applies.

## Expected Behavior

Read native usage.record, exclude duplicate context.append_loop_event copies, and use a proved native or replay-safe source-position key. Derive disjoint input, cache-read, cache-creation, and output components only where ENH-3665 proves the semantics. A supported native field is not automatically a measured stored observation. Keep unproved components null/unknown; do not infer zero, request identity, or non-overlap from matching counts. Use the shared coverage selector and verified host/session identity for canonical reporting.

If ENH-3665 proves partial native support, store the proved components with null evidence-backed unsupported components as `unknown`, audit-only rows under the current row-level provenance contract; canonical totals/rates that require missing components stay unavailable. If native absence is proved for every in-scope path, this issue still owns the direct-fallback disposition and explicit unavailable diagnostic; mark it done after that work, or cancel only if no change remains. An in-scope unknown keeps this issue blocked and the epic incomplete. If no after-usage event exists, prove another current-session trigger or keep this issue open for an explicit epic scope decision.

ENH-3534 is done and supplies the baseline `UsageReplayRecord`, `HostUsageState`, `normalize_host_usage` where applicable, `refresh_raw_events`, and derive checkpoint contract. This delivery issue owns its native adapter and required integration, coordinating shared source refresh, incremental derive, freshness, and trigger changes under EPIC-3562 § Shared Delivery Ownership, with shared regression tests. Preserve the baseline replay guarantees; no other host's evidence becomes a hard blocker.

## Runtime Qualification and Cutover Gate

Qualify each observation using the runtime provider and source/CLI version from the evidence issue's verified native source. Match the captured contract exactly or apply its specifically evidenced compatibility policy. Absent/unmatched provider/version or unproved attribution/identity remains audit-only with a visible reason and unavailable dependent canonical figures. A broad typed host capability never substitutes for this check.

Persist the ingest-time contract reference, provider/version evidence and qualification disposition on `raw_events`, using existing metadata where sufficient, so incremental derive and rebuild make the same decision. A later CLI upgrade or provider configuration must not promote old unknowns; requalification requires new source evidence and an explicit tested operation.

ENH-3723 was closed by decomposition. ENH-3731 (core/source), BUG-3735 (wildcard coverage), BUG-3736 (retention Stage 1) and ENH-3748 (channel scope) are done; ENH-3732 (quality/workspace), ENH-3733 (snapshot/dashboard) and ENH-3744/3745 (semantic retention/progress) remain open. ENH-3746 owns retained-reader admission before cutover. The links preserve these delivery-stage gates. The quality/snapshot implementations, semantic retention and source-local progress controls, completed core/scoped-coverage/Stage 1 controls, and their consumer tests are required before enabling production derivation of this host's newly recognized usage rows, as well as reader cutover/closeout; the parent's terminal status does not satisfy this gate. Existing source, snapshot and quality readers automatically discover `usage_events`; postponing only the session-reader switch would expose audit-only rows before shared qualification exists. Native capture, parser/adapter development, raw-event retention and isolated-fixture derivation may proceed first. Add this host's qualified/partial/mismatch rows to the shared source/snapshot/session-reader matrix before publication. Keep these as tested delivery-stage gates: adapter/raw-retention work can proceed after this host's matching evidence issue. The retained `blocked_by: BUG-3736` edge is already satisfied; no new whole-issue scheduling edge to ENH-3732/3733/3744/3745/3746 is introduced. Reader cutover/closeout tests additionally incorporate ENH-3746's retained-source admission and combined ENH-3745 freshness controls; failing those tests prevents cutover, while adapter work remains independent; ENH-3747 search restoration remains an epic-closeout gate.

**Ingress parity:** cover historical `lifecycle._backfill_raw_events`, current `refresh_usage_source` or the proved host equivalent, parser-upgrade `usage_refresh.refresh_raw_events`, and direct-source `writers._iter_usage_replay_records`. The first delivery lander owns the shared host-keyed contract-resolution seam under the epic's ownership rule. Each supported route uses the same native provider/version evidence and preserves its ingest-time marker through raw storage and derive. Unchanged previously unqualified rows cannot be promoted by a later parser/contract change; requalification remains an explicit operation outside this delivery. A legacy direct-source route that cannot handle this native shape must explicitly reject it rather than apply Claude's contract or silently certify different usage. Do not require every host to adopt the single-file interface.

**Quality derive-status integration:** the shared delivery seam also extends ENH-3732's pure retained-raw source/channel and logical-candidate classification for this host's selected contract. A matched transcript candidate with no derived observation must report `derive_gap` (or pending/lagging proof), even if another request in the session is already stored. Proved excluded-channel-only sources remain `out_of_scope`; a missing/unmatched channel or identity is unavailable rather than guessed from the host name. Extend ENH-3744's shared pure recognition/key/coalescing/correspondence interface using ingest-time evidence; never add a second quality-only candidate algorithm. The read-only helper never reads native files, calls the write normalizer or invokes derivation. Raw pruning and held-source append/context-recovery must use the same producer rule, with ENH-3745's source-local progress contract; unprovable context cannot become intentional non-usage. Include this path in the host's quality publication matrix and follow the first-lander shared ownership rule.

**No-source closeout:** if the evidence issue proves no in-scope usage-bearing path, the producer/replay/trigger criteria below are inapplicable. The delivery still proves the explicit unavailable diagnostic, retirement of any unqualified direct fallback, retained-history behavior and scoped ledger disposition. This branch cannot be used for missing access, an unproved field or an unproved trigger on a supported source. A partial source still needs its real ingestion/replay/trigger proofs.

## Program Design

- **Producer input**: the canonical source selected by ENH-3665, with stored usage.record as the current candidate and context.append_loop_event as a possible duplicate; ENH-3665 supplies the versioned field and component contract.
- **Replay identity**: the ENH-3665 proved native or replay-safe source-position key. The key is scoped by verified host and session and survives full rebuild; copied or conflicting records remain unknown until resolved.
- **Stored path**: adapt the native record at the session parser or replay-writer seam into `usage_events` with disjoint nullable components and durable source attribution. Reuse ENH-3534's refresh and ENH-3651's incremental derive checkpoint.
- **Current session**: use the evidence issue's event and source-write timing candidate, then prove a real trigger after usage is persisted. Extend `usage_stop.handle`/`backfill_worker._run_usage_trigger` or a host-specific equivalent. A read-time refresh is acceptable only when tested against a real post-write source and committed as-of boundary; a manually invoked worker alone does not prove current-session freshness.
- **Reader**: `ll-ctx-stats` selects the verified host/session through `select_usage_coverage`, checks `usage_source_freshness`, and exposes a canonical rate only for qualified non-overlapping components.

### Signatures

- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — existing parser entry point; preserve native usage needed by this host.
- `_backfill_usage_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int` — existing replay writer; extend through a host-specific normalizer when the contract is proved.
- `_run_usage_trigger(db_path: Path, source: Path, host: str, requested_at_ns: int) -> int` — existing Claude/Codex worker path; reuse only after this host's event timing and source are proved.

### Call Path

- Verified native source layout → host discovery/parser adapter (`iter_events` where applicable) → `raw_events` → `_backfill_usage_events` → `usage_events` → `select_usage_coverage` → `_compute_cache_rate_from_usage` → `ll-ctx-stats`.
- Proved post-write host event or read-time refresh → host adapter/worker or tested equivalent → incremental derive checkpoint → reader freshness check.

## Integration Map

- Session discovery/parser/normalizer and replay writer under scripts/little_loops/session_store/; coordinate extensions to `refresh_usage_source`, `_derive_usage_incremental_conn`, `usage_source_freshness`, and shared tests under EPIC-3562 § Shared Delivery Ownership; ENH-3731 owns shared canonical eligibility; ENH-3732/3733 own quality and snapshot integration. Verify append, overwrite, rotation, or file-tree mutation behavior against the real native source before reusing a cursor.
- Include `lifecycle._backfill_raw_events`, `usage_refresh._event_signature`/`refresh_raw_events`, and `writers._iter_usage_replay_records` in contract-routing changes; those seams currently calculate Claude-specific markers. Preserve stored evidence for unchanged rows and test explicit rejection of unsupported direct-source layouts.
- Kimi Code lifecycle adapter and scripts/little_loops/hooks/usage_stop.py or another proved after-usage trigger; scripts/little_loops/cli/backfill_worker.py and incremental derivation.
- scripts/little_loops/cli/ctx_stats.py and scripts/little_loops/history_reader/usage.py shared selection; scripts/little_loops/host_runner.py typed telemetry entries.
- Real versioned fixtures and contract notes under scripts/tests/fixtures/kimi-code/; parser, replay, hook-worker, reader, and capability tests; update the CLI/host compatibility documentation.

## Acceptance Criteria

- [ ] An actual ingress/registration test proves that the host's new production usage derivation remains disabled until the publication gate passes; exercise historical/current/parser-refresh/direct-source routes that this host supports. Native adapter/raw-retention and isolated-fixture work cannot switch it on early. Enable only with the shared qualified/partial/mismatch/wildcard consumer matrix; evaluate shipped qualification/retention behavior rather than looking up issue statuses at runtime, and do not add a general feature-flag framework solely for this gate.
- [ ] Native candidate/coalescing proof composes with ENH-3744 pruning/held-source recovery and ENH-3745 source-local completion; missing retained context and pending work below a global checkpoint stay unavailable. Reader cutover/closeout also proves ENH-3746 admission after raw pruning without narrowing the host/session metric population. Search restoration is independently owned by ENH-3747.
- [ ] The selected transcript contract extends member-local retained-raw derive-status classification: an existing observation cannot hide another missing logical candidate; excluded-channel-only and unmatched/identity-missing controls fail safely. A proved no-source branch instead passes the unavailable-reader/fallback/ledger tests without fabricating producer or trigger proof; supported/partial paths pass the producer criteria below.
- [ ] Production enablement happens only after ENH-3731/3732/3733, BUG-3735/3736 and ENH-3744/3745 pass. Until then, native adapter/raw-retention work cannot register a production derive route that publishes these observations into existing unqualified readers; isolated-fixture derivation is allowed. After enablement, the real source/snapshot/quality/session-reader matrix keeps partial/mismatch/wildcard cases unavailable, without changing coverage-only selected-row counts to hide rejected contributors.

- [ ] Runtime matching, unmatched provider, absent provider/version, unproved version, and unproved identity fixtures enforce the evidence-backed qualification policy. Unsupported versions/providers cannot inherit a measured host-level verdict; diagnostics explain audit-only/unavailable results.
- [ ] Ingest-time qualification evidence survives on `raw_events`; incremental derive, full rebuild, and later CLI/provider changes produce the same qualified or unknown disposition without promoting old rows.
- [ ] Before enabling production derivation of new native usage observations and before reader cutover/closeout, ENH-3731/3732/3733 implement the recorded policy, BUG-3735 preserves wildcard coverage through scoped selection, BUG-3736 preserves the Stage 1 safety floor, ENH-3744/3745 prove semantic retention and source-local completion, ENH-3746 passes retained-reader admission before cutover, and this host's source/snapshot/quality/session-reader parity cases pass, including partial/mismatch rows and any documented stricter measured-only rate rule. Capture/adapter/raw-retention work can proceed first without publishing unqualified canonical figures through existing readers.
- [ ] Historical ingest, current refresh, parser-upgrade refresh and supported direct-source replay agree on the native fixture's contract evidence and derived qualification; unsupported direct-source shapes have an explicit tested rejection. Repeated parser refresh preserves unchanged ingest-time markers and does not qualify old unknowns. A failed derive/rebuild stays unavailable or freshness-unknown until an explicit successful retry, even if the next source read is unchanged; no fresh-zero result is certified.
- [ ] Preserve ENH-3723's as-of compatibility contract: otherwise qualified retained historical values carry freshness/lag/as-of metadata and are never described as current when freshness is stale/unknown. Source loss retains historical observations; component-incomplete session rates remain unavailable rather than using a complete subset.
- [ ] ENH-3665 records a versioned, sanitized producer contract for every implemented metric/channel: fields, inclusivity, omissions, request grain/reset behavior, reasoning/output relation, and stable source identity; unresolved items remain explicit unknowns.
- [ ] A parser-replayable fixture in the real native source layout passes through discovery/parser, raw_events, usage_events, and the shared selector. It preserves the native usage fields needed for this host and does not change unrelated normalized content; a reduced JSONL excerpt alone cannot satisfy this gate.
- [ ] Proven repeated, resumed, live/stored, and copied records are counted once per native request. Full rebuild, incremental derive, and repeated refresh of available originals agree; missing originals or unverified attribution never manufacture measured usage.
- [ ] A proved Kimi Code current-session trigger runs after native usage is persisted and drives the real adapter or read-time equivalent → ingest → incremental derive → stored read path. The selected host/session has a committed as-of/freshness proof; a failed or skipped refresh cannot appear fresh.
- [ ] A row with a proved component but a null evidence-backed unsupported canonical component remains `unknown` and audit-only under the current row-level provenance contract; missing dependent totals/rates stay unavailable. Any component-level measured exception requires an explicit tested contract and epic ledger revision.
- [ ] A partial host may close when proved components are stored with replay and freshness qualification as audit-only rows, the selected reader emits an explicit unavailable diagnostic for dependent canonical figures, and the epic ledger records that terminal partial disposition; in-scope unknowns still block closure.
- [ ] This issue owns the Kimi Code direct-fallback disposition. `ll-ctx-stats` switches to the stored reader only after the end-to-end path passes, or emits an explicit unavailable diagnostic after proved native absence. Missing store, partial components, and unresolved overlap never produce a fabricated canonical rate; audit subtotals remain labeled.
- [ ] The typed telemetry map and epic ledger record supported, unsupported, or unknown for each metric/channel separately from ingestion status. Documentation and tests cover the host's actual native shape.

## Scope Boundaries

- **In scope**: Kimi Code native usage ingestion, request identity, current-session trigger, freshness-qualified stored read, capability entries, and fixture-backed tests.
- **Out of scope**: non-Anthropic pricing, non-Claude context occupancy, and other hosts' producer contracts.

## Implementation Steps

1. Consume ENH-3665's provider/version-qualified native contract, real layout, identity and source-write timing evidence.
2. Implement the native adapter and durable ingest-time qualification; coordinate shared seams under the epic ownership rule.
3. Prove replay/update behavior, incremental/full parity, a real current-session trigger and freshness recovery.
4. Add this host's qualification matrix cases across ENH-3731/3732/3733; enable production usage derivation and cut over the reader only after its gate passes, or record the evidence-backed unavailable/partial disposition.

## Impact

- **Priority**: P3 — closes one of the epic's six remaining host paths.
- **Effort**: Medium — native parser, lifecycle, and reader integration.
- **Risk**: Medium — silent double counting or stale usage if identity or trigger timing is wrong.
- **Breaking Change**: No CLI option change expected; a previously unverified fallback figure may become explicitly unavailable until stored evidence is current.

---

## Scope Boundary

**Coordination rule (2026-10-03):** EPIC-3562 § Shared Delivery Ownership governs all six delivery issues (ENH-3671–3676). The first lander owns the shared refresh/derive/freshness/trigger extension; later hosts extend the host-keyed dispatch and rebase. ENH-3731 owns shared canonical eligibility; ENH-3732/3733 own quality and snapshot integration. Host-specific adapter work stays here.

## Status

**Blocked** | Created: 2026-09-30 | Priority: P3


## Session Log

- Pre-implementation epic review - 2026-10-05 - Reconciled completed core/coverage/Stage 1/channel work and the remaining delivery-stage semantic/progress/reader gates. Added an actual production-disabled ingress test, shared proof/held-source recovery handoff and retained-reader closeout controls; preserved host-specific evidence blocking and independent adapter/raw work. Opus confidence 0.70; its suspected source-narrowing defect was refuted by the actual host/session selector call. No implementation or readiness pass is claimed.

- Pre-implementation epic review - 2026-10-05 - Added the selected-contract channel/logical-candidate extension to quality derive status and clarified conditional no-source closeout. Native publication requires all shared qualification owners and BUG-3735/3736; the matching hard evidence blocker and status are unchanged.

- Pre-implementation epic review - 2026-10-05 - Resolved the decomposed-parent publication gate to ENH-3731/3732/3733 together. Kept the matching native-evidence blocker and independent adapter/raw-retention work; a done ENH-3723 is not an implementation pass.

- Pre-implementation follow-up review - 2026-10-04 - `/ll:advise` with Opus (confidence 0.72): added shared qualification before production usage publication, all supported ingestion-route contract parity and explicit unsupported-route rejection, failed-derive controls and retained as-of semantics. No status, dependency or implementation change.
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:03 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
