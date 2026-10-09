---
id: ENH-3675
type: ENH
title: Implement OMP stored token usage
priority: P3
status: blocked
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:24:21Z'
parent: EPIC-3562
labels:
- observability
- multi-host
- usage-ingestion
blocked_by:
- ENH-3664
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
- ENH-3751
- ENH-3770
---

# ENH-3675: Implement OMP stored token usage

## Summary

Deliver OMP token usage from a proved native source to stored, normalized observations and a freshness-qualified session reader. ENH-3664 owns the producer contract; ENH-3534 owns shared replay and refresh infrastructure. This issue owns OMP parsing, identity, normalization, current-session trigger, capability entries, and reader cutover. It has no dependency on another host's evidence.

## Current Behavior

The OMP CLI was absent during the survey, and existing usage fixtures are synthetic. `normalize_omp_session` retains entry `id` as `uuid` and `message.model`, but drops `message.usage`, `message.provider`, `message.api`, the session header and non-conversational context. `parse_omp_session` reports normalized-event enumeration as `line_no`, rather than physical JSONL positions. The shared usage Stop worker and ll-ctx-stats stored cache-rate path currently serve Claude and Codex only. Other hosts retain the direct transcript fallback where it applies.

## Expected Behavior

Use a real versioned OMP session to retain captured native usage plus provider/source-version/session/request context through the file-level normalizer and prove its source identity. Preserve existing content/tool normalization while extending the telemetry/context handoff; copying only `message.usage` cannot qualify historical records. Derive disjoint input, cache-read, cache-creation, and output components only where ENH-3664 proves the semantics. A supported native field is not automatically a measured stored observation. Keep unproved components null/unknown; do not infer zero, request identity, or non-overlap from matching counts. Use the shared coverage selector and verified host/session identity for canonical reporting.

If ENH-3664 proves partial native support, store the proved components with null evidence-backed unsupported components as `unknown`, audit-only rows under the current row-level provenance contract; canonical totals/rates that require missing components stay unavailable. If native absence is proved for every in-scope path, this issue still owns the direct-fallback disposition and explicit unavailable diagnostic; mark it done after that work, or cancel only if no change remains. An in-scope unknown keeps this issue blocked and the epic incomplete. If no after-usage event exists, prove another current-session trigger or keep this issue open for an explicit epic scope decision.

ENH-3534 is done and supplies the baseline `UsageReplayRecord`, `HostUsageState`, `normalize_host_usage` where applicable, `refresh_raw_events`, and derive checkpoint contract. This delivery issue owns its native adapter and required integration, coordinating shared source refresh, incremental derive, freshness, and trigger changes under EPIC-3562 § Shared Delivery Ownership, with shared regression tests. Preserve the baseline replay guarantees; no other host's evidence becomes a hard blocker.

## Runtime Qualification and Cutover Gate

Qualify each observation using the runtime provider and source/CLI version from the evidence issue's verified native source. Match the captured contract exactly or apply its specifically evidenced compatibility policy. Absent/unmatched provider/version or unproved attribution/identity remains audit-only with a visible reason and unavailable dependent canonical figures. A broad typed host capability never substitutes for this check.

Persist the ingest-time contract reference, provider/version evidence and qualification disposition on `raw_events`, using existing metadata where sufficient, so incremental derive and rebuild make the same decision. A later CLI upgrade or provider configuration must not promote old unknowns; requalification requires new source evidence and an explicit tested operation.

ENH-3723 was closed by decomposition. ENH-3731 (core/source), ENH-3733 (snapshot/dashboard), BUG-3735/3736 (scoped coverage/Stage 1), ENH-3748 (channel scope), ENH-3744/3745 (semantic proof/source progress), ENH-3747 (search survival) and ENH-3770 (guarded reconciliation/witness publication) are done. Consume their landed APIs and regression contracts; ENH-3732 (quality/workspace) remains a publication gate, and ENH-3746 (retained-reader admission) remains a reader-cutover/closeout gate. A terminal decomposed parent never substitutes for shipped behavior. Existing source, snapshot and quality readers discover `usage_events`, so the complete shared qualification matrix is required before publishing this host's new native observations. Native capture, parser/adapter development, raw-event retention and isolated-fixture derivation can proceed first after this host's matching evidence issue. Add qualified/partial/mismatch/wildcard cases to the shared source/snapshot/quality/session-reader matrix and evaluate implemented behavior, not issue statuses at runtime. The retained `blocked_by: BUG-3736` edge is already satisfied; no new whole-issue scheduling edges are introduced. Keep ENH-3746 admission and combined source-local freshness tests as cutover controls without narrowing the host/session figure.

**Ingress parity:** cover historical `lifecycle._backfill_raw_events`, current `refresh_usage_source` or the proved host equivalent, and parser-upgrade `usage_refresh.refresh_raw_events`, followed by stored-cursor replay. The first delivery lander owns the shared host-keyed contract-resolution seam under the epic's ownership rule. Each production route uses the same native provider/version evidence and preserves its ingest-time marker through raw storage and guarded derive. ENH-3770 deliberately refuses rawless `writers._backfill_usage_events(list[Path])` mutation and pricing: retain that fail-closed behavior. `writers._iter_usage_replay_records` direct inputs are a read-only recognition/qualification parity control, with explicit rejection for unsupported shapes; a native source must first acquire durable raw rows before publishing observations. Unchanged previously unqualified rows cannot be promoted by a later parser/contract change; requalification remains an explicit operation outside this delivery. Do not require every host to adopt the single-file interface.

**Quality derive-status integration:** the shared delivery seam also extends ENH-3732's pure retained-raw source/channel and logical-candidate classification for this host's selected contract. A matched transcript candidate with no derived observation must report `derive_gap` (or pending/lagging proof), even if another request in the session is already stored. Proved excluded-channel-only sources remain `out_of_scope`; a missing/unmatched channel or identity is unavailable rather than guessed from the host name. Extend ENH-3744's shared pure recognition/key/coalescing/correspondence interface using ingest-time evidence; never add a second quality-only candidate algorithm. The read-only helper never reads native files, calls the write normalizer or invokes derivation. Raw pruning and held-source append/context-recovery must use the same producer rule, with ENH-3745's source-local progress contract; unprovable context cannot become intentional non-usage. Include this path in the host's quality publication matrix and follow the first-lander shared ownership rule.

**No-source closeout:** if the evidence issue proves no in-scope usage-bearing path, the producer/replay/trigger criteria below are inapplicable. The delivery still proves the explicit unavailable diagnostic, retirement of any unqualified direct fallback, retained-history behavior and scoped ledger disposition. This branch cannot be used for missing access, an unproved field or an unproved trigger on a supported source. A partial source still needs its real ingestion/replay/trigger proofs.

## Program Design

- **Producer input**: real OMP assistant message.usage; ENH-3664 supplies the versioned field and component contract.
- **Replay identity**: the ENH-3664 proved message/request key scoped to a session. The key is scoped by verified host and session and survives full rebuild; copied or conflicting records remain unknown until resolved.
- **Stored path**: adapt the captured native shape through shared recognition and the stored-cursor writer into `usage_events`, with disjoint nullable components and durable raw identity/context. Extend ENH-3770's `usage_replay.apply_replay` planner inputs rather than writing/pricing directly or restoring delete/reinsert. Retain its no-op identity/cost preservation, preflight conflict handling, payload/envelope identity checks, source acquisition authority, unresolved pending and post-write witness/completion updates. Extend the shared pure producer recognition used by `usage_proof` and the replay adapter together; a Claude-shaped payload does not grant the Claude native qualification contract. Preserve ENH-3770's exact-durable-raw unqualified audit insertion and exact-link no-op allowance without an acquired source head when identity is compatible and protected overlap is unambiguous. That allowance grants no qualification, positive supplier/context witness, completion, freshness or hold release; those require their evidenced authority. Rawless inputs remain refused.
- **Current session**: use the evidence issue's event and source-write timing candidate, then prove a real trigger after usage is persisted. Extend `usage_stop.handle`/`backfill_worker._run_usage_trigger` or a host-specific equivalent. A read-time refresh is acceptable only when tested against a real post-write source and committed as-of boundary; a manually invoked worker alone does not prove current-session freshness.
- **Reader**: `ll-ctx-stats` selects the verified host/session through `select_usage_coverage`, checks `usage_source_freshness`, and exposes a canonical rate only for qualified non-overlapping components.

### Signatures

- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — existing parser entry point; preserve native usage needed by this host.
- `_backfill_usage_events(conn, source, *, search_scope=None, reindex_all=False, report=None, plan_out=None) -> int` — existing guarded writer in `writers.py`; production uses its stored cursor with durable raw IDs. `report` carries unresolved source work, while `plan_out` plans without mutation/pricing/indexing. Preserve rawless direct-input refusal and route native normalization through the existing planner.
- `_derive_usage_incremental_disposition(conn)` — landed mutation/progress owner in `lifecycle.py`; `_derive_usage_incremental_conn(conn) -> int` is only its count wrapper. Consume source-local pending/acquisition/witness state rather than treating the count or global raw-ID checkpoint as completion.
- `_run_usage_trigger(db_path: Path, source: Path, host: str, requested_at_ns: int) -> int` — existing Claude/Codex worker path; reuse only after this host's event timing and source are proved.

### Call Path

- Verified native source layout → host discovery/parser adapter (`iter_events` where applicable) → `raw_events` → `_backfill_usage_events` → `usage_replay.apply_replay` → `usage_events` → `select_usage_coverage` → `_compute_cache_rate_from_usage` → `ll-ctx-stats`.
- Proved post-write host event or read-time refresh → host adapter/worker or tested equivalent → incremental derive checkpoint → reader freshness check.

## Integration Map

- Session discovery/parser/normalizer and replay writer under scripts/little_loops/session_store/; coordinate extensions to `refresh_usage_source`, `_derive_usage_incremental_disposition`, `usage_source_freshness`, and shared tests under EPIC-3562 § Shared Delivery Ownership; ENH-3731 owns shared canonical eligibility; ENH-3732/3733 own quality and snapshot integration. Verify append, overwrite, rotation, or file-tree mutation behavior against the real native source before reusing a cursor.
- Include `lifecycle._backfill_raw_events`, `lifecycle._refresh_codex_usage_source`'s first-cursor certification, `usage_refresh.refresh_raw_events` with its `_expected_contract`/`_event_metadata`/`_inserted_matches` helpers (ENH-3751 replaced the removed `_event_signature`) and read-only `writers._iter_usage_replay_records` parity in contract-routing changes; those seams currently compute Claude-specific markers (`claude_transcript_contract`, the Claude-shaped `sessionId`). The first lander turns `_expected_contract` into the host-keyed dispatch. Preserve ENH-3751's monotonic marker rule (a NULL `usage_contract` may be promoted from the verified original source; a persisted marker is never changed or removed), stored evidence for unchanged rows and test explicit rejection of unsupported direct-source layouts.
- `omp.py:normalize_omp_session` / `sessions.py:parse_omp_session`: extend native usage/provider/version/context retention and a proved native position mapping. The current normalized enumeration cannot be fed directly to physical-line acquisition accounting. `lifecycle._ACCOUNTED_HOSTS` currently admits only Claude/Codex; extend shared acquisition/failure staging for the evidenced native OMP source instead of adding its host to that set and guessing offsets. Keep title-slot rewrites and skipped metadata distinct from usage value changes.
- OMP lifecycle adapter and scripts/little_loops/hooks/usage_stop.py or another proved after-usage trigger; scripts/little_loops/cli/backfill_worker.py and incremental derivation.
- scripts/little_loops/cli/ctx_stats.py and scripts/little_loops/history_reader/usage.py shared selection; scripts/little_loops/host_runner.py typed telemetry entries.
- Real versioned fixtures and contract notes under scripts/tests/fixtures/omp/; parser, replay, hook-worker, reader, and capability tests; update the CLI/host compatibility documentation.

## Acceptance Criteria

- [ ] An actual ingress/registration test proves that the host's new production usage derivation remains disabled until the publication gate passes; exercise historical/current/parser-refresh → durable-raw → stored-cursor routes that this host supports, plus direct-input refusal. Native adapter/raw-retention and isolated-fixture work cannot switch it on early. Enable only with the shared qualified/partial/mismatch/wildcard consumer matrix; evaluate shipped qualification/retention behavior rather than looking up issue statuses at runtime, and do not add a general feature-flag framework solely for this gate.
- [ ] Native candidate/coalescing proof composes with ENH-3744 pruning/held-source recovery and ENH-3745 source-local completion; missing retained context and pending work below a global checkpoint stay unavailable. Reader cutover/closeout also proves ENH-3746 admission after raw pruning without narrowing the host/session metric population. Preserve ENH-3747's landed search reconciliation alongside guarded replay.
- [ ] The selected transcript contract extends member-local retained-raw derive-status classification: an existing observation cannot hide another missing logical candidate; excluded-channel-only and unmatched/identity-missing controls fail safely. A proved no-source branch instead passes the unavailable-reader/fallback/ledger tests without fabricating producer or trigger proof; supported/partial paths pass the producer criteria below.
- [ ] Production enablement happens only after ENH-3731/3732/3733, BUG-3735/3736 and ENH-3744/3745 pass. Until then, native adapter/raw-retention work cannot register a production derive route that publishes these observations into existing unqualified readers; isolated-fixture derivation is allowed. After enablement, the real source/snapshot/quality/session-reader matrix keeps partial/mismatch/wildcard cases unavailable, without changing coverage-only selected-row counts to hide rejected contributors.

- [ ] Runtime matching, unmatched provider, absent provider/version, unproved version, and unproved identity fixtures enforce the evidence-backed qualification policy. Unsupported versions/providers cannot inherit a measured host-level verdict; diagnostics explain audit-only/unavailable results.
- [ ] Ingest-time qualification evidence survives on `raw_events`; incremental derive, full rebuild, and later CLI/provider changes produce the same qualified or unknown disposition without promoting old rows.
- [ ] **History-sanitizer identity contract (EPIC-3562 § Shared Delivery Ownership).** Extend `usage_proof.PROOF_IDENTITY_PATHS` and its existing `TestSanitizerParity` for the stored string replay identity, model and actually consumed qualification-context paths (including provider/version where used). Those paths resolve through `pii._protocol_rules(host, event_type)`, reusing existing Claude-shaped protection only where the actual stored shape matches. Secret-shaped string identity/context (`ghp_`+36 alphanumerics, an `AKIA` key, a JWT) raises `unsafe_identity` with content-free per-line refusal; distinct refused identities never collapse into one observation. Numeric usage components are captured values rather than protected identity paths: preserve their types/values through sanitization and test malformed-component rejection/unknown disposition separately, without coercing them to zero. Source-derived observations equal those rebuilt from sanitized raw rows. OMP's normalizer maps entry IDs onto the protected `uuid` path; confirm the identity and context ENH-3664 selects are covered once the native source is captured.
- [ ] Before enabling production derivation of new native usage observations and before reader cutover/closeout, ENH-3731/3732/3733 implement the recorded policy, BUG-3735 preserves wildcard coverage through scoped selection, BUG-3736 preserves the Stage 1 safety floor, ENH-3744/3745 prove semantic retention and source-local completion, ENH-3746 passes retained-reader admission before cutover, and this host's source/snapshot/quality/session-reader parity cases pass, including partial/mismatch rows and any documented stricter measured-only rate rule. Capture/adapter/raw-retention work can proceed first without publishing unqualified canonical figures through existing readers.
- [ ] Historical ingest, current refresh and parser-upgrade refresh followed by stored-cursor derive agree on the native fixture's contract evidence and qualification. Direct-source recognition parity is read-only; rawless direct-file replay writes/prices nothing and unsupported shapes have an explicit tested rejection. Repeated parser refresh preserves unchanged ingest-time markers and does not qualify old unknowns. A failed derive/rebuild stays unavailable or freshness-unknown until an explicit successful retry, even if the next source read is unchanged; no fresh-zero result is certified.
- [ ] Preserve ENH-3723's as-of compatibility contract: otherwise qualified retained historical values carry freshness/lag/as-of metadata and are never described as current when freshness is stale/unknown. Source loss retains historical observations; component-incomplete session rates remain unavailable rather than using a complete subset.
- [ ] ENH-3664 records a versioned, sanitized producer contract for every implemented metric/channel: fields, inclusivity, omissions, request grain/reset behavior, reasoning/output relation, and stable source identity; unresolved items remain explicit unknowns.
- [ ] Real OMP source tests cover a title-slot-only rewrite, inserted/skipped metadata, a native assistant usage update and resumed/copied or branched context where selected. Non-usage rewrites preserve committed usage identity/cost without repricing; replay and source completion use the proved native generation/physical-to-normalized position mapping. Header/provider/version/request context survives raw storage when qualification consumes it; missing or contradictory context stays pending/unavailable rather than inheriting a model/provider from current configuration.
- [ ] A parser-replayable fixture in the real native source layout passes through discovery/parser, raw_events, usage_events, and the shared selector. It preserves the native usage fields needed for this host and does not change unrelated normalized content; a reduced JSONL excerpt alone cannot satisfy this gate.
- [ ] Each qualified observation publishes the actual value supplier and every separately retained context record consumed by qualification. Extend `QualificationDependency`'s current `model`/`closure` role set and shared position mapping narrowly where the captured contract requires provider/version/session/request context; do not overload those roles or invent physical lines. Native context/source loss invalidates the same consumed frontier used by proof, replay and readers; unavailable authority/context withholds positive witnesses/completion.
- [ ] Guarded replay tests extend ENH-3770's invariants for this native host: unchanged/older/compatible copies preserve observation ID, stored cost, timestamps and actual supplier without pricing; cross-source identity/model/component conflicts preflight before mutation and keep bounded pending; held-source distinct appends and parser-refresh retries use acquired authority, durable witnesses and post-write proof. Missing native generation/order cannot authorize value replacement, positive completion or hold release. Exact-link unqualified audit insertion/no-op without an acquired head passes its existing narrow identity/overlap controls and publishes no positive witnesses/completion; qualified mutations, positive witnesses/completion and hold release require their proved authority. No broad usage delete/reinsert or rawless mutation is added.
- [ ] Proven repeated, resumed, live/stored, and copied records are counted once per native request. Full rebuild, incremental derive, and repeated refresh of available originals agree; missing originals or unverified attribution never manufacture measured usage.
- [ ] The runtime OMP trigger is actually registered/enabled: the existing TypeScript adapter only wires `session_start`/`tool_result`, and `usage_stop.handle` both excludes OMP and suppresses `LL_NON_INTERACTIVE` automation calls. Wire a proved native after-usage event or a tested read-time equivalent and define interactive/automation disposition explicitly; a manual worker or sessionless `build_blocking_json` capture cannot certify the runtime trigger.
- [ ] A proved OMP current-session trigger runs after native usage is persisted and drives the real adapter or read-time equivalent → ingest → incremental derive → stored read path. The selected host/session has a committed as-of/freshness proof; a failed or skipped refresh cannot appear fresh.
- [ ] A row with a proved component but a null evidence-backed unsupported canonical component remains `unknown` and audit-only under the current row-level provenance contract; missing dependent totals/rates stay unavailable. Any component-level measured exception requires an explicit tested contract and epic ledger revision.
- [ ] A partial host may close when proved components are stored with replay and freshness qualification as audit-only rows, the selected reader emits an explicit unavailable diagnostic for dependent canonical figures, and the epic ledger records that terminal partial disposition; in-scope unknowns still block closure.
- [ ] This issue owns the OMP direct-fallback disposition. `ll-ctx-stats` switches to the stored reader only after the end-to-end path passes, or emits an explicit unavailable diagnostic after proved native absence. Missing store, partial components, and unresolved overlap never produce a fabricated canonical rate; audit subtotals remain labeled.
- [ ] The typed telemetry map and epic ledger record supported, unsupported, or unknown for each metric/channel separately from ingestion status. Documentation and tests cover the host's actual native shape.

## Scope Boundaries

- **In scope**: OMP native usage ingestion, request identity, current-session trigger, freshness-qualified stored read, capability entries, and fixture-backed tests.
- **Out of scope**: non-Anthropic pricing, non-Claude context occupancy, and other hosts' producer contracts.

## Implementation Steps

1. Consume ENH-3664's provider/version-qualified native contract, real layout, identity and source-write timing evidence.
2. Implement the native adapter and durable ingest-time qualification; coordinate shared seams under the epic ownership rule.
3. Extend shared producer proof and ENH-3770's guarded replay for this native shape; prove acquisition/position mapping, replay/update preservation, incremental/full parity, a real current-session trigger and freshness recovery.
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

- Pre-implementation epic review - 2026-10-08 - Reconciled completed snapshot/proof/progress/search/guarded-replay work and kept quality publication/retained-reader cutover gates independent of adapter work. Replaced the obsolete direct-file mutation assumption with durable-raw stored replay/read-only parity, named the actual disposition/planner/report seams, and required native no-op/conflict/pending/witness controls while preserving the headless exact-link unqualified audit allowance. Sanitizer tests extend the existing string identity/context declaration and keep numeric type/value controls separate. Evidence blocker and status remain unchanged; no implementation or readiness claim.

- Pre-implementation epic review - 2026-10-07 - Corrected the ingress-seam citation (`usage_refresh._event_signature` was removed by ENH-3751; actual seams are `_expected_contract`/`_event_metadata`/`_inserted_matches` plus first-cursor certification) and added the monotonic-marker rule. Added the history-sanitizer identity contract (EPIC-3562 § Shared Delivery Ownership): ENH-3751 sanitizes every ingest path and only `pii._protocol_rules` protects replay identity, which no delivery listed. Opus consult (confidence 0.72) corrected my first framing: Claude-shaped hosts already get the Claude path table; the concrete exposure is Kimi's raw passthrough and any new adapter/identity field outside that table. No implementation or readiness claim.

- Pre-implementation epic review - 2026-10-05 - Reconciled completed core/coverage/Stage 1/channel work and the remaining delivery-stage semantic/progress/reader gates. Added an actual production-disabled ingress test, shared proof/held-source recovery handoff and retained-reader closeout controls; preserved host-specific evidence blocking and independent adapter/raw work. Opus confidence 0.70; its suspected source-narrowing defect was refuted by the actual host/session selector call. No implementation or readiness pass is claimed.

- Pre-implementation epic review - 2026-10-05 - Added the selected-contract channel/logical-candidate extension to quality derive status and clarified conditional no-source closeout. Native publication requires all shared qualification owners and BUG-3735/3736; the matching hard evidence blocker and status are unchanged.

- Pre-implementation epic review - 2026-10-05 - Resolved the decomposed-parent publication gate to ENH-3731/3732/3733 together. Kept the matching native-evidence blocker and independent adapter/raw-retention work; a done ENH-3723 is not an implementation pass.

- Pre-implementation follow-up review - 2026-10-04 - `/ll:advise` with Opus (confidence 0.72): added shared qualification before production usage publication, all supported ingestion-route contract parity and explicit unsupported-route rejection, failed-derive controls and retained as-of semantics. No status, dependency or implementation change.
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:02 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
