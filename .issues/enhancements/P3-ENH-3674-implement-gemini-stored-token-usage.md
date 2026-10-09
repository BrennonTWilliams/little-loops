---
id: ENH-3674
type: ENH
title: Implement Gemini stored token usage
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
- ENH-3663
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

# ENH-3674: Implement Gemini stored token usage

## Summary

Deliver Gemini token usage from a proved native source to stored, normalized observations and a freshness-qualified session reader. ENH-3663 owns the producer contract; ENH-3534 owns shared replay and refresh infrastructure. This issue owns Gemini parsing, identity, normalization, current-session trigger, capability entries, and reader cutover. It has no dependency on another host's evidence.

## Current Behavior

A real historical tokens pair has an unknown CLI version and a repeated message ID. The current file-level normalizer drops tokens; the 0.46.0 live probe lacked Vertex configuration. The shared usage Stop worker and ll-ctx-stats stored cache-rate path currently serve Claude and Codex only. Other hosts retain the direct transcript fallback where it applies.

## Expected Behavior

Preserve native tokens through the file-level normalizer and distinguish an updated message from a new request using the proved identity and grain. Derive disjoint input, cache-read, cache-creation, and output components only where ENH-3663 proves the semantics. A supported native field is not automatically a measured stored observation. Keep unproved components null/unknown; do not infer zero, request identity, or non-overlap from matching counts. Use the shared coverage selector and verified host/session identity for canonical reporting.

If ENH-3663 proves partial native support, store the proved components with null evidence-backed unsupported components as `unknown`, audit-only rows under the current row-level provenance contract; canonical totals/rates that require missing components stay unavailable. If native absence is proved for every in-scope path, this issue still owns the direct-fallback disposition and explicit unavailable diagnostic; mark it done after that work, or cancel only if no change remains. An in-scope unknown keeps this issue blocked and the epic incomplete. If no after-usage event exists, prove another current-session trigger or keep this issue open for an explicit epic scope decision.

ENH-3534 is done and supplies the baseline `UsageReplayRecord`, `HostUsageState`, `normalize_host_usage` where applicable, `refresh_raw_events`, and derive checkpoint contract. This delivery issue owns its native adapter and required integration, coordinating shared source refresh, incremental derive, freshness, and trigger changes under EPIC-3562 § Shared Delivery Ownership, with shared regression tests. Preserve the baseline replay guarantees; no other host's evidence becomes a hard blocker.

## Runtime Qualification and Cutover Gate

Qualify each observation using the runtime provider and source/CLI version from the evidence issue's verified native source. Match the captured contract exactly or apply its specifically evidenced compatibility policy. Absent/unmatched provider/version or unproved attribution/identity remains audit-only with a visible reason and unavailable dependent canonical figures. A broad typed host capability never substitutes for this check.

Persist the ingest-time contract reference, provider/version evidence and qualification disposition on `raw_events`, using existing metadata where sufficient, so incremental derive and rebuild make the same decision. A later CLI upgrade or provider configuration must not promote old unknowns; requalification requires new source evidence and an explicit tested operation.

ENH-3723 was closed by decomposition. ENH-3731/3733 (core/source and snapshot/dashboard), BUG-3735/3736 (wildcard coverage and Stage 1 retention), and ENH-3744/3745/3747/3748 (semantic proof, source-local progress, search and channel scope) are done. ENH-3770 is also done and supplies guarded replay, held-source recovery, supplier/context witnesses and proved hold release. ENH-3732 remains the quality/workspace publication owner; related ENH-3746 retained-reader admission remains a reader-cutover/closeout gate. Keep the landed controls and extend their host-qualified/partial/mismatch matrix before publishing this host's new `usage_events`; existing reports discover those rows before the session-reader switch. Native capture, parser/adapter work, raw retention and isolated-fixture derivation may proceed after ENH-3663 supplies its contract. The retained `blocked_by: BUG-3736` edge is satisfied; these are tested delivery-stage gates, not new whole-issue scheduling edges or runtime issue-status checks. Keep related ENH-3746 admission and combined freshness tests as reader-cutover controls; preserve the landed ENH-3747 search contract.

**Ingress parity:** cover historical `lifecycle._backfill_raw_events`, current `refresh_usage_source` or the proved host equivalent, parser-upgrade `usage_refresh.refresh_raw_events`, and direct-source `writers._iter_usage_replay_records`. The first delivery lander owns the shared host-keyed contract-resolution seam under the epic's ownership rule. Each supported route uses the same native provider/version evidence and preserves its ingest-time marker through raw storage and derive. Unchanged previously unqualified rows cannot be promoted by a later parser/contract change; requalification remains an explicit operation outside this delivery. A legacy direct-source route that cannot handle this native shape must explicitly reject it rather than apply Claude's contract or silently certify different usage. Do not require every host to adopt the single-file interface.

**Guarded replay integration (ENH-3770, landed):** `_backfill_usage_events` collects targets; `usage_replay.apply_replay` plans every insert/replacement/qualification/demotion before it mutates or prices rows, using `usage_reconcile.decide`. Add Gemini's evidenced identity, update/generation order and qualification context through this seam and the shared pure `usage_proof` recognition, not a second mutation policy or broad delete/reinsert. Production targets always require durable raw-row links. Qualified mutations and positive supplier/context witnesses, source completion, figure as-of publication and hold release require the shared action's verified acquisition/generation authority. Preserve ENH-3770's narrow headless allowance: an exact surviving raw identity, compatible payload/envelope and no ambiguous protected overlap can authorize a first unqualified audit insert under existing pricing semantics or an unchanged exact-link audit no-op, without an acquired head; it grants no promotion, value replacement or positive certification. Complete proved conflict invalidation remains governed by the shared policy. A raw-less direct-file decoder still cannot mutate or price usage or certify freshness. A supported direct route must ingest retained raw first and replay its stored envelope, or explicitly refuse writes. For actions authorized to publish witnesses, persist the actual applied-value supplier and consumed context with observation mutations, pending/completion and search effects in the caller transaction; a headless audit insert grants no affirmative witness or completion. Existing shared context roles cover `model`/`closure`; any additional provider/version/request/session dependency requires an evidenced narrow mapping/role extension. Neither normalized output enumeration nor raw allocation order proves native revision order. Preserve audit values and pending work under missing/pruned/held or contradictory context, and exercise below-checkpoint recovery and hold release against the actual selected native contract.

**Quality derive-status integration:** the shared delivery seam also extends ENH-3732's pure retained-raw source/channel and logical-candidate classification for this host's selected contract. A matched transcript candidate with no derived observation must report `derive_gap` (or pending/lagging proof), even if another request in the session is already stored. Proved excluded-channel-only sources remain `out_of_scope`; a missing/unmatched channel or identity is unavailable rather than guessed from the host name. Extend ENH-3744's shared pure recognition/key/coalescing/correspondence interface using ingest-time evidence; never add a second quality-only candidate algorithm. The read-only helper never reads native files, calls the write normalizer or invokes derivation. Raw pruning and held-source append/context-recovery must use the same producer rule, with ENH-3745's source-local progress contract; unprovable context cannot become intentional non-usage. Include this path in the host's quality publication matrix and follow the first-lander shared ownership rule.

**No-source closeout:** if the evidence issue proves no in-scope usage-bearing path, the producer/replay/trigger criteria below are inapplicable. The delivery still proves the explicit unavailable diagnostic, retirement of any unqualified direct fallback, retained-history behavior and scoped ledger disposition. This branch cannot be used for missing access, an unproved field or an unproved trigger on a supported source. A partial source still needs its real ingestion/replay/trigger proofs.

## Program Design

- **Producer input**: file-level Gemini message tokens; ENH-3663 supplies the versioned field and component contract, including `tokens.tool`/total relationships and journal patch/rewind semantics. Legacy whole-document `.json` remains outside discovery unless its evidence-backed scope is explicitly selected.
- **Replay identity**: the ENH-3663 proved message/request key and update-versus-new-request rule. The key is scoped by verified host and session and survives full rebuild; copied or conflicting records remain unknown until resolved.
- **Mutation policy**: apply ENH-3663's repeated-ID update and patch/rewind rule through guarded replay. A proved replacement supersedes the previous usage transactionally; a proved distinct request receives its evidenced identity. Visible-history removal does not prove consumption retraction. Changed token values must not be frozen by generic monotonic-field refresh checks; missing revision authority preserves the committed row with pending work.
- **Change witness**: name the native revision or stat/content witness for the entire stored message collection. It must notice revisions before the final message even when record count, last message ID and last usage values are unchanged. A bounded append-tail witness alone cannot certify this mutable layout; a source change during parsing/derive cannot commit a fresh proof.
- **Stored path**: adapt the native record into retained `raw_events` and evidence-backed guarded replay targets with disjoint nullable components and durable source attribution. Reuse ENH-3770's `usage_replay`/`usage_reconcile` mutation policy and ENH-3745 source-state/witness storage alongside the baseline refresh/checkpoint interfaces. Preserve the actual native record/item position and required header/patch context; `parse_gemini_session` currently numbers normalized output, so those positions cannot be compared directly to a physical acquisition line boundary.
- **Current session**: use the evidence issue's event and source-write timing candidate, then prove a real trigger after usage is persisted. Extend `usage_stop.handle`/`backfill_worker._run_usage_trigger` or a host-specific equivalent. A read-time refresh is acceptable only when tested against a real post-write source and committed as-of boundary; a manually invoked worker alone does not prove current-session freshness.
- **Reader**: `ll-ctx-stats` selects the verified host/session through `select_usage_coverage`, checks `usage_source_freshness`, and exposes a canonical rate only for qualified non-overlapping components.

### Signatures

- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — existing parser entry point; preserve native usage needed by this host.
- `_backfill_usage_events(conn, source, *, search_scope=None, reindex_all=False, report=None, plan_out=None) -> int` — existing guarded replay collector; extend host-specific recognition/targets and `usage_replay.apply_replay`, retaining report/side-effect-free plan behavior.
- `_derive_usage_incremental_disposition(conn, attempt=None)` — landed mutation/progress owner; `_derive_usage_incremental_conn(conn) -> int` is its count-only wrapper, so its count cannot certify source-local completion.
- `_run_usage_trigger(db_path: Path, source: Path, host: str, requested_at_ns: int) -> int` — existing Claude/Codex worker path; reuse only after this host's event timing and source are proved.

### Call Path

- Verified native source layout → host discovery/parser adapter (`iter_events` where applicable) → `raw_events` → `_backfill_usage_events` → `usage_replay.apply_replay` / `usage_reconcile.decide` → `usage_events` plus supplier/context witnesses → `select_usage_coverage` → `_compute_cache_rate_from_usage` → `ll-ctx-stats`.
- Proved post-write host event or read-time refresh → host adapter/worker or tested equivalent → incremental derive checkpoint → reader freshness check.

## Integration Map

- Session discovery/parser/normalizer and replay writer under scripts/little_loops/session_store/; coordinate extensions to `refresh_usage_source`, `_derive_usage_incremental_disposition`, `usage_source_freshness`, and shared tests under EPIC-3562 § Shared Delivery Ownership; ENH-3731 owns shared canonical eligibility; ENH-3732/3733 own quality and snapshot integration. Verify append, overwrite, rotation, or file-tree mutation behavior against the real native source before reusing a cursor.
- Include `lifecycle._backfill_raw_events`, `lifecycle._refresh_codex_usage_source`'s first-cursor certification, `usage_refresh.refresh_raw_events` with its `_expected_contract`/`_event_metadata`/`_inserted_matches` helpers (ENH-3751 replaced the removed `_event_signature`) and `writers._iter_usage_replay_records` in contract-routing changes; those seams currently compute Claude-specific markers (`claude_transcript_contract`, the Claude-shaped `sessionId`). The first lander turns `_expected_contract` into the host-keyed dispatch. Preserve ENH-3751's monotonic marker rule (a NULL `usage_contract` may be promoted from the verified original source; a persisted marker is never changed or removed), stored evidence for unchanged rows and test explicit rejection of unsupported direct-source layouts.
- Gemini lifecycle adapter and scripts/little_loops/hooks/usage_stop.py or another proved after-usage trigger; scripts/little_loops/cli/backfill_worker.py and incremental derivation.
- scripts/little_loops/cli/ctx_stats.py and scripts/little_loops/history_reader/usage.py shared selection; scripts/little_loops/host_runner.py typed telemetry entries.
- Real versioned fixtures and contract notes under scripts/tests/fixtures/gemini/; parser, replay, hook-worker, reader, and capability tests; update the CLI/host compatibility documentation.
- `session_store/usage_proof.py` and `usage_replay.py`/`usage_reconcile.py` supply shared recognition and guarded mutation; `usage_source_state.py` supplies acquisition/completion/pending and supplier/context witnesses. Extend their host cases and the landed `test_enh3770_usage_reconcile.py`/`test_enh3770_guarded_replay.py` contracts, preserving concurrent changes and the ENH-3747 search seam.

## Acceptance Criteria

- [ ] Ordered header/patch/repeated-ID/rewind fixtures preserve ENH-3663's recorded-consumption rule through sanitized raw retention and rebuild. A visibility-only rewind cannot retract consumption or fabricate a fresh zero. Expanded inline tool results and `$set.messages` items retain a stable native supplier/item mapping instead of pretending normalized enumeration is a physical line; header/provider/version context survives source loss and pruning where required, with missing context unavailable. Unrelated content/tool parsing stays equivalent.
- [ ] The host target participates in ENH-3770 guarded planning with a durable raw supplier and the actual consumed qualification-context frontier. Full rebuild, repeated refresh and incremental/below-checkpoint retry agree; raw-less inputs cannot mutate or price usage. Exact-durable-raw unqualified audit insertion and unchanged exact-link no-op remain allowed without a head when the shared policy proves compatible identity and no protected overlap; they cannot promote, replace values, certify witnesses/completion/as-of or release a hold. Qualified mutation and positive certification controls require valid acquired authority, while complete conflict invalidation follows the shared policy. Copied conflicts, missing/pruned supplier/context and held-source recovery preserve protected observations and stay pending until the shared policy permits a proved action; atomic witness/completion/search and rollback controls pass. Native same-position rewrites require an evidenced generation/revision rule; Claude's append-only snapshot order cannot certify them. No broad delete/reinsert or host-only policy bypass is introduced.
- [ ] An actual ingress/registration test proves that the host's new production usage derivation remains disabled until the publication gate passes; exercise historical/current/parser-refresh/direct-source routes that this host supports. Native adapter/raw-retention and isolated-fixture work cannot switch it on early. Enable only with the shared qualified/partial/mismatch/wildcard consumer matrix; evaluate shipped qualification/retention behavior rather than looking up issue statuses at runtime, and do not add a general feature-flag framework solely for this gate.
- [ ] Native candidate/coalescing proof composes with ENH-3744 pruning/held-source recovery and ENH-3745 source-local completion; missing retained context and pending work below a global checkpoint stay unavailable. Reader cutover/closeout also proves ENH-3746 admission after raw pruning without narrowing the host/session metric population. Search restoration is independently owned by ENH-3747.
- [ ] The selected transcript contract extends member-local retained-raw derive-status classification: an existing observation cannot hide another missing logical candidate; excluded-channel-only and unmatched/identity-missing controls fail safely. A proved no-source branch instead passes the unavailable-reader/fallback/ledger tests without fabricating producer or trigger proof; supported/partial paths pass the producer criteria below.
- [ ] Production enablement happens only after ENH-3731/3732/3733, BUG-3735/3736 and ENH-3744/3745 pass. Until then, native adapter/raw-retention work cannot register a production derive route that publishes these observations into existing unqualified readers; isolated-fixture derivation is allowed. After enablement, the real source/snapshot/quality/session-reader matrix keeps partial/mismatch/wildcard cases unavailable, without changing coverage-only selected-row counts to hide rejected contributors.

- [ ] For ENH-3663's update-capable selected contract, an ordered repeated-message-ID fixture changes input/output/cache values and finishes with a valid record. Apply its proved replacement-versus-distinct-request rule: no duplicate sum and no frozen earlier value. A proved immutable-finalized selected contract instead tests finalized/no-update and identical-copy controls plus fail-closed handling of contradictory changed-value records. Incremental derive, repeated refresh and full rebuild agree on the contract's final values and observation counts; unproved historical repeated IDs do not qualify a new contract.
- [ ] Revise an earlier message's counters while leaving record count, last message ID and last usage values unchanged. The whole-source change witness detects the change: a proved mutable contract applies its authorized revision, while an immutable contract retains committed consumption with pending/unavailable mutation. Freshness recovers only after a successful contract-valid acquisition/derive or proved restoration. A concurrent source mutation cannot commit a fresh proof for inconsistent contents.
- [ ] Malformed/in-progress updates make freshness stale/unknown while retaining the last committed observations; a valid finalized update followed by successful derive restores the correct qualified reader result. Use EPIC-3562's source retention and freshness rule: missing or unreadable originals do not retract recorded consumption or produce a fresh zero. Generic field-preservation checks must not permanently reject a legitimate counter revision.
- [ ] Runtime matching, unmatched provider, absent provider/version, unproved version, and unproved identity fixtures enforce the evidence-backed qualification policy. Unsupported versions/providers cannot inherit a measured host-level verdict; diagnostics explain audit-only/unavailable results.
- [ ] Ingest-time qualification evidence survives on `raw_events`; incremental derive, full rebuild, and later CLI/provider changes produce the same qualified or unknown disposition without promoting old rows.
- [ ] **History-sanitizer identity contract (EPIC-3562 § Shared Delivery Ownership).** Extend `usage_proof.PROOF_IDENTITY_PATHS` and its existing `TestSanitizerParity` for the stored string replay identity, model and consumed qualification-context paths (including provider/version where used). Those paths resolve through `pii._protocol_rules(host, event_type)`, reusing existing Claude-shaped protection only where the actual shape matches. Secret-shaped string identity/context (`ghp_`+36 alphanumerics, an `AKIA` key, a JWT) raises `unsafe_identity` with content-free per-line refusal; distinct refused identities never collapse. Numeric usage fields are captured values rather than identities: preserve their types/values and fail malformed components safely. Source-derived observations equal those rebuilt from sanitized raw rows. Gemini currently maps message `id` to protected `uuid`; additionally cover the selected revision identity and retained header/provider/version context wherever ENH-3663 locates it.
- [ ] Before enabling production derivation of new native usage observations and before reader cutover/closeout, ENH-3731/3732/3733 implement the recorded policy, BUG-3735 preserves wildcard coverage through scoped selection, BUG-3736 preserves the Stage 1 safety floor, ENH-3744/3745 prove semantic retention and source-local completion, ENH-3746 passes retained-reader admission before cutover, and this host's source/snapshot/quality/session-reader parity cases pass, including partial/mismatch rows and any documented stricter measured-only rate rule. Capture/adapter/raw-retention work can proceed first without publishing unqualified canonical figures through existing readers.
- [ ] Historical ingest, current refresh, parser-upgrade refresh and supported direct-source replay agree on the native fixture's contract evidence and derived qualification; unsupported direct-source shapes have an explicit tested rejection. Repeated parser refresh preserves unchanged ingest-time markers and does not qualify old unknowns. A failed derive/rebuild stays unavailable or freshness-unknown until an explicit successful retry, even if the next source read is unchanged; no fresh-zero result is certified.
- [ ] Preserve ENH-3723's as-of compatibility contract: otherwise qualified retained historical values carry freshness/lag/as-of metadata and are never described as current when freshness is stale/unknown. Source loss retains historical observations; component-incomplete session rates remain unavailable rather than using a complete subset.
- [ ] ENH-3663 records a versioned, sanitized producer contract for every implemented metric/channel: fields, inclusivity, omissions, request grain/reset behavior, reasoning/output relation, and stable source identity; unresolved items remain explicit unknowns.
- [ ] A parser-replayable fixture in the real native source layout passes through discovery/parser, raw_events, usage_events, and the shared selector. It preserves the native usage fields needed for this host and does not change unrelated normalized content; a reduced JSONL excerpt alone cannot satisfy this gate.
- [ ] Proven repeated, resumed, live/stored, and copied records are counted once per native request. Full rebuild, incremental derive, and repeated refresh of available originals agree; missing originals or unverified attribution never manufacture measured usage.
- [ ] A proved Gemini current-session trigger runs after native usage is persisted and drives the real adapter or read-time equivalent → ingest → incremental derive → stored read path. The selected host/session has a committed as-of/freshness proof; a failed or skipped refresh cannot appear fresh.
- [ ] A row with a proved component but a null evidence-backed unsupported canonical component remains `unknown` and audit-only under the current row-level provenance contract; missing dependent totals/rates stay unavailable. Any component-level measured exception requires an explicit tested contract and epic ledger revision.
- [ ] A partial host may close when proved components are stored with replay and freshness qualification as audit-only rows, the selected reader emits an explicit unavailable diagnostic for dependent canonical figures, and the epic ledger records that terminal partial disposition; in-scope unknowns still block closure.
- [ ] This issue owns the Gemini direct-fallback disposition. `ll-ctx-stats` switches to the stored reader only after the end-to-end path passes, or emits an explicit unavailable diagnostic after proved native absence. Missing store, partial components, and unresolved overlap never produce a fabricated canonical rate; audit subtotals remain labeled.
- [ ] The typed telemetry map and epic ledger record supported, unsupported, or unknown for each metric/channel separately from ingestion status. Documentation and tests cover the host's actual native shape.

## Scope Boundaries

- **In scope**: Gemini native usage ingestion, request identity, current-session trigger, freshness-qualified stored read, capability entries, and fixture-backed tests.
- **Out of scope**: non-Anthropic pricing, non-Claude context occupancy, and other hosts' producer contracts.

## Implementation Steps

1. Consume ENH-3663's provider/version-qualified native contract, real layout, identity and source-write timing evidence.
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

- Pre-implementation epic review - 2026-10-08 - Reconciled completed shared controls and ENH-3770's landed guarded planner; added durable supplier/acquisition/context and held/below-checkpoint recovery integration instead of raw-less or destructive replay. Added native journal patch/rewind and physical-record/item mapping controls for repeated-ID changes, and corrected sanitizer work to extend the existing string identity/context declaration separately from numeric components. Evidence blocker and status unchanged.

- Pre-implementation epic review - 2026-10-07 - Corrected the ingress-seam citation (`usage_refresh._event_signature` was removed by ENH-3751; actual seams are `_expected_contract`/`_event_metadata`/`_inserted_matches` plus first-cursor certification) and added the monotonic-marker rule. Added the history-sanitizer identity contract (EPIC-3562 § Shared Delivery Ownership): ENH-3751 sanitizes every ingest path and only `pii._protocol_rules` protects replay identity, which no delivery listed. Opus consult (confidence 0.72) corrected my first framing: Claude-shaped hosts already get the Claude path table; the concrete exposure is Kimi's raw passthrough and any new adapter/identity field outside that table. No implementation or readiness claim.

- Pre-implementation epic review - 2026-10-05 - Reconciled completed core/coverage/Stage 1/channel work and the remaining delivery-stage semantic/progress/reader gates. Added an actual production-disabled ingress test, shared proof/held-source recovery handoff and retained-reader closeout controls; preserved host-specific evidence blocking and independent adapter/raw work. Opus confidence 0.70; its suspected source-narrowing defect was refuted by the actual host/session selector call. No implementation or readiness pass is claimed.

- Pre-implementation epic review - 2026-10-05 - Added the selected-contract channel/logical-candidate extension to quality derive status and clarified conditional no-source closeout. Native publication requires all shared qualification owners and BUG-3735/3736; the matching hard evidence blocker and status are unchanged.

- Pre-implementation epic review - 2026-10-05 - Resolved the decomposed-parent publication gate to ENH-3731/3732/3733 together. Kept the matching native-evidence blocker and independent adapter/raw-retention work; a done ENH-3723 is not an implementation pass.

- Pre-implementation follow-up review - 2026-10-04 - `/ll:advise` with Opus (confidence 0.72): added shared qualification before production usage publication, all supported ingestion-route contract parity and explicit unsupported-route rejection, failed-derive controls and retained as-of semantics. Added the whole-message-source change witness and earlier-record/concurrent-mutation tests. No status, dependency or implementation change.

- Pre-implementation epic review - 2026-10-04 - Aligned update failures and source disappearance with the epic's retained-history/stale-freshness rule. Existing repeated-ID identity and valid-update recovery gates remain in place.

- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:02 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
