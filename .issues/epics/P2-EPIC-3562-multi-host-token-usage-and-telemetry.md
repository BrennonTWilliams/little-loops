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

Coordinate token usage ingestion, observation provenance, context-occupancy labeling/correctness, and runtime telemetry across the eight production hosts (Claude Code, Codex, OpenCode, Pi, Qwen, Gemini, OMP, Kimi Code). The epic has 22 children: 15 done and 7 unresolved (ENH-3534 plus six per-host evidence follow-ups). Standalone ENH-3649 is also done. Native availability, ingestion support, observation provenance, coverage, and occupancy are separate contracts.

## Goal

Every canonical token-consumption figure for a production host comes from stored, normalized observations with explicit provenance and coverage qualification. Proven coverage is counted once. When overlap cannot be resolved, channel subtotals remain available for audit, but the canonical total and derived rate are unavailable rather than a potentially double-counted sum. Context occupancy is a separate context-state metric with estimate and staleness labels; it is never presented as consumption or as a `usage_events` observation.

## Scope

- **In scope**: host usage ingestion (Codex rollout, remaining hosts), Claude/Codex producer contracts, live/rollout identity and coverage selection, typed telemetry availability, context-hook occupancy labels, and stored-usage consumers (`ll-ctx-stats`, dashboard, quality regressions).
- **Out of scope**: pricing for non-Anthropic models, estimator accuracy, occupancy monitors for non-Claude hosts, Claude live/transcript overlap reconciliation, general session-reader isolation (ENH-3649).

## Composition Review

The 22 children cover the epic's named contracts and retain explicit per-host unknown-evidence owners. The first four contract groups are implemented for their proven hosts; ENH-3534 and its six evidence children remain:

| Contract | Children | Remaining evidence or handoff |
|----------|----------|-------------------------------|
| Observation provenance and host attribution | ENH-3528, BUG-3542, ENH-3580, ENH-3546 | Claude producer fixtures and durable eligibility in ENH-3546 |
| Codex rollout identity and live coverage | ENH-3532, ENH-3647, ENH-3655, ENH-3543 | Current-version request-key fixtures and ENH-3655's independent join verdict |
| Stored usage freshness and consumers | ENH-3651, ENH-3656, ENH-3549 | Claude numeric parity and as-of proof first; Codex runtime trigger and cutover later |
| Remaining production hosts | ENH-3648, ENH-3534, ENH-3544 | Survey findings may create child per-host issues where producer semantics differ |
| Context occupancy | BUG-3587, ENH-3545 | Labels and staleness remain open; general reader isolation is standalone ENH-3649 |

ENH-3655 and ENH-3656 are separate because their evidence/Claude work can start before the Codex blockers of ENH-3543/ENH-3549. A host with unknown native evidence or no proven stored trigger stays explicitly unavailable; it is not counted as completed eight-host coverage.

## Eight-host completion ledger

Track each host's native evidence, stored producer, current-session trigger, and reader verdict independently. These are owners for the remaining proofs, not claims that their work has already landed:

| Host | Native evidence | Stored producer | Current-session trigger | Reader verdict |
|------|-----------------|-----------------|-------------------------|----------------|
| Claude Code | Verified Claude 2.1.284 live/transcript captures (ENH-3546) | Stored measured observations with replay eligibility (ENH-3546/3651) | Captured Stop hook and trailing derive (ENH-3651) | Stored, host/session selected, freshness-qualified cache rate (ENH-3656) |
| Codex | 0.158.0 rollout/live captures; live-to-rollout native join refuted (ENH-3532/3655) | Stored rollout requests and live identity (ENH-3532/3647) | Captured Stop hook and detached derive (ENH-3549) | Stored, coverage-qualified rate; unresolved overlap has audit subtotals only (ENH-3543/3549) |
| OpenCode | Partial fields in real 1.1.53 live/stored captures; normalized input unknown (ENH-3660 open) | Native `step-finish` parts captured; ENH-3534 ingestion pending | No stored trigger proved; ENH-3534 or child | Incomplete; ENH-3549 or child |
| Pi | Unknown; 0.84.2 probe lacked API key (ENH-3661 open) | Unknown; ENH-3534 or child | Unknown; ENH-3534 or child | Incomplete; ENH-3549 or child |
| Qwen | Partial transcript fields in real 0.24.6 pair; live/cache identity unknown (ENH-3662 open) | Native pair captured; ENH-3534 dedup/ingestion pending | No stored trigger proved; ENH-3534 or child | Incomplete; ENH-3549 or child |
| Gemini | Unknown; historical capture has no CLI version and 0.46.0 probe lacked Vertex config (ENH-3663 open) | Unknown; ENH-3534 or child | Unknown; ENH-3534 or child | Incomplete; ENH-3549 or child |
| OMP | Unknown; CLI absent, existing fixtures synthetic (ENH-3664 open) | Unknown; ENH-3534 or child | Unknown; ENH-3534 or child | Incomplete; ENH-3549 or child |
| Kimi Code | Partial stored fields in real 0.30.0 capture; input/replay identity unknown (ENH-3665 open) | Native `usage.record` captured; ENH-3534 dedup/ingestion pending | No stored trigger proved; ENH-3534 or child | Incomplete; ENH-3549 or child |

Before closing the epic, replace each owner entry with an evidence-backed verdict for the in-scope consumption metrics and channels: implemented with a stored producer/trigger/reader where native usage is supported, or explicitly unavailable where native absence is proven. Partial native support is recorded per metric/channel, not collapsed to a host-wide `unsupported`. An `unknown` survey result, missing trigger for a supported current-session path, or open/deferred per-host follow-up keeps eight-host coverage incomplete. ENH-3648/3534 file per-host follow-ups with `parent: EPIC-3562`; a merely linked issue does not satisfy closure. If the intended scope shrinks, revise this goal and ledger explicitly instead of counting an unresolved host as done.

## Impact

- **Priority**: P2 — multi-host token figures are currently mostly `unknown` and will double-count once rollout ingestion lands without selection.
- **Effort**: Large — 18 open children across session store, runners, readers, hooks and six per-host evidence follow-ups from ENH-3648.
- **Risk**: Medium — accounting errors are silent; mitigated by fixture-backed contracts and conservative unresolved defaults.

## Children

**Done (15)**

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

**Blocked (1)**

- **ENH-3534** — Finish remaining-host ingestion after native contract evidence

**Open evidence children (6)**

- **ENH-3660** — Prove OpenCode cache and reasoning semantics
- **ENH-3661** — Capture Pi with a configured model
- **ENH-3662** — Prove Qwen live/cache and duplicate semantics
- **ENH-3663** — Capture versioned Gemini usage and identity
- **ENH-3664** — Capture real OMP usage
- **ENH-3665** — Prove Kimi component and replay identity

Standalone **ENH-3649** (reader isolation and diagnostics) is done and remains outside this epic's child count.

## Implementation Order and Readiness

Historical implementation sequence for the 15 completed children; the six host evidence contracts now determine the remaining path for ENH-3534.

1. **Parallel, now:** ENH-3544 (capability matrix; Claude/Codex evidence only, others `unknown`), ENH-3545 (labels only), ENH-3546 (Claude fixture capture, including repeated assistant records), ENH-3648 (six-host survey), **ENH-3655's unblocked join spike** (paired current-version live/rollout captures; must not gate ENH-3647), **Codex request-key fixture capture for ENH-3532** (fork, paginated thread, 0.154+ `token_usage_record`, mixed/partial event shapes, re-emitted notification, non-advancing total), and ENH-3651's catch-up/checkpoint/as-of design. Share Codex captures between ENH-3655 and ENH-3532. Standalone ENH-3649 may run independently and coordinates its `ll-ctx-stats` empty-discovery diagnostic with ENH-3656.
2. **Codex identity:** use the verified host + **thread** ID (`session_meta.payload.id` / live `thread.started.thread_id`) for usage rows; the root/parent `payload.session_id` is not the thread ID in a fork. Agree identity-basis and span field names across ENH-3532 and ENH-3647 (see § Schema coordination), then land ENH-3532 (rollout ingestion) and ENH-3647 (live identity) in either order. Interim readers may expose an unreconciled observation sum only as an audit subtotal, not a canonical total or rate.
3. **Reconciliation:** after ENH-3655 records PROVEN/REFUTED, ENH-3543 adds the selector, the paired verified-host/thread filter (if ENH-3656 has not), and reader/dashboard parity. If the spike refutes the join, the selector ships with conservative unresolved behavior only.
4. **Consumers:** ENH-3651 owns first-enable catch-up, atomic incremental derivation, a reader-visible source-tail/as-of proof, the Claude Code hook trigger, and fixture-backed transcript observation identity. ENH-3656 then checks numeric parity or an explicitly documented correction before shipping the Claude stored reader and stale-result diagnostics. ENH-3549 owns the Codex runtime trigger and final cutover after ENH-3532, ENH-3543 **and** the real Codex hook → ingest → incremental derive → read fixture pass. A host's direct reader retires only with a recorded stored replacement or evidence-backed unavailable verdict; neither counts an `unknown` host as completed coverage.
5. **Remaining hosts:** ENH-3534 after ENH-3648's findings, ENH-3532's `UsageReplayRecord` contract and ENH-3544's vocabulary. Re-ingestion must address already-stripped payloads; unknown capability is not unsupported.

## Schema coordination

`SCHEMA_VERSION` is 55, and about 20 tests pin it. The following children may add append-only migrations:

| Issue | Tables | Content |
|-------|--------|---------|
| ENH-3532 | `raw_events`, `usage_events` | native `ordinal` on `raw_events` (copied on replay; legacy rows stay NULL unless re-read); stream discriminator; `response_id` + source key + span `turn_id` on `usage_events`; partial dedup indexes (repair-first). Key revised 2026-09-29: `(host, response_id)` where `token_usage_record` exists, else `(host, payload.id, stream discriminator, ordinal)` |
| ENH-3647 | `usage_events` | identity-basis marker (host-observed vs local), if not added by ENH-3532 |
| ENH-3546 | `raw_events`, `usage_events` | producer-eligibility discriminator on `raw_events` (copied on replay) |
| ENH-3651 | `meta`, possibly `usage_events` | durable derive checkpoint, source-row link and fixture-backed transcript observation identity if the chosen atomic catch-up/retry design needs them; full rebuild and incremental derive update the checkpoint consistently |

Rules: migrations take the next version in landing order and are never renumbered after landing. ENH-3532 and ENH-3647 fix the identity-basis/span column names together before either lands; whichever lands first adds shared columns and the other reuses them. Any replay-surviving attribute goes on `raw_events` first, since `rebuild()` regenerates `usage_events` from it (the BUG-3542 `host_basis` pattern).

## Shared-consumer notes

- `quality_regressions.py` and `agent_quality.py` remain channel-pinned so newly identified Codex rows do not silently change existing aggregates.
- `select_usage_coverage` reconciles candidates for a verified host/thread pair before report filters. `select_usage_observations` delegates to the same policy. An ID-only call is rejected.

## Cross-Issue Acceptance Criteria

- [x] Source usage/cost/waste/quality and built-in snapshot/dashboard aggregates agree on selection, qualification and audit subtotals for matched, partial and unresolved coverage (ENH-3543).
- [x] Canonical token components, event/request identity, run/state attribution, and report-window rules remain consistent through ingest, rebuild and export (ENH-3532/3543/3647).
- [x] Legacy/unverified producer evidence is never promoted by rebuild; missing originals/usage remain explicit rather than fabricated measurements (ENH-3534/3546).
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
- [ ] Every production host has an evidence-backed terminal ledger verdict; unknown capability, absent trigger, or open/deferred per-host child leaves the epic open.

## Review Notes

Implementation review 2026-09-29: the full local suite passed (27,525 passed, 301 skipped); lint, format, host-map and private-reference verification passed. The configured mypy command is blocked by this environment's untyped `ruamel` dependency and older mypy/dependency stubs; no type-check pass is claimed. Eleven more epic children reached done, as did standalone ENH-3649. Six native producer contracts remain unproved, so ENH-3534 and the epic remain unresolved.

Pre-implementation review 2026-09-24 applied to specifications only. Review 2026-09-28: refreshed stale child statuses (ENH-3580, BUG-3587 done); closed ENH-3532 gates 2–3 from fixtures and proposed a gate-1 key; split ENH-3543 → ENH-3647, ENH-3534 → ENH-3648, ENH-3549 → ENH-3649; added schema coordination, the `quality_regressions` consumer and ENH-3549's current-session freshness gate. Historical confidence scores do not certify the revised scopes. Child frontmatter is authoritative for status/progress.

Review 2026-09-29 (corpus check of `~/.codex/sessions` plus an opus consult): ENH-3532's `(host, session_id, ordinal)` key collides on forks and paginated threads and cannot dedupe duplicate notifications; newer Codex writes `token_usage_record` alongside `token_count`; `agent_quality._usage_totals` needed the same channel pin as `quality_regressions`; the ENH-3543 spike moved to step 1; ENH-3549 staged Claude-first with the hook-driven ingest split out; added missing `blocks` backlinks on ENH-3532 and normalized ENH-3549 to `blocked_by`. Fixtures are `codex-cli 0.152.1` while local sessions come from 0.154–0.158 alphas, so every Codex contract needs a current-version fixture.

Follow-up review 2026-09-29: assigned shared incremental derivation and first-enable catch-up to ENH-3651, with Codex normalization remaining in ENH-3532; replaced file-wide `token_count` suppression with a mixed-stream evidence gate; fixed the thread/root ID contradiction; required host-qualified session filtering; and removed ENH-3549's superseded freshness options. These are specification changes only, and the producer fixtures, join spike and checkpoint design remain implementation gates.

Readiness follow-up 2026-09-29 (Sonnet critique and issue-graph check): ENH-3655 now owns the unblocked join spike, and ENH-3656 owns the Claude-first stored-reader stage. ENH-3543 and ENH-3549 retain hard dependencies for their production selector and Codex cutover. ENH-3651 supplies a selected-session as-of proof with its shared derive and Claude trigger; ENH-3549 owns the later Codex runtime trigger. A stale stored value and a manually driven Codex fixture cannot certify current-session freshness. Removed ENH-3549's superseded option-B acceptance text.

Review follow-up 2026-09-29: added Claude numeric-parity and transcript-identity gates, made unresolved sums audit-only rather than canonical rates, required an explicit eight-host closure verdict, and added ENH-3543 as a Codex reader-cutover blocker. General session-reader isolation (ENH-3649) is now standalone; its empty-discovery diagnostic still coordinates with ENH-3656. No implementation is claimed by these specification edits.

## Status

**Open** | Created: 2026-09-24 | Priority: P2
