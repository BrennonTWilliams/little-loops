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

Coordinate token usage ingestion, observation provenance, context-occupancy labeling/correctness, and runtime telemetry across the eight production hosts (Claude Code, Codex, OpenCode, Pi, Qwen, Gemini, OMP, Kimi Code). The epic has 28 children: 16 done and 12 unresolved (six per-host evidence issues and six host delivery issues; shared ENH-3534 is done). Standalone ENH-3649 is also done. Native availability, ingestion support, observation provenance, coverage, and occupancy are separate contracts.

## Goal

Every canonical token-consumption figure for a production host comes from stored, normalized observations with explicit provenance and coverage qualification. Proven coverage is counted once. When overlap cannot be resolved, channel subtotals remain available for audit, but the canonical total and derived rate are unavailable rather than a potentially double-counted sum. Context occupancy is a separate context-state metric with estimate and staleness labels; it is never presented as consumption or as a `usage_events` observation.

## Scope

- **In scope**: host usage ingestion (Codex rollout, remaining hosts), Claude/Codex producer contracts, live/rollout identity and coverage selection, typed telemetry availability, context-hook occupancy labels, and stored-usage consumers (`ll-ctx-stats`, dashboard, quality regressions).
- **Out of scope**: pricing for non-Anthropic models, estimator accuracy, occupancy monitors for non-Claude hosts, Claude live/transcript overlap reconciliation, general session-reader isolation (ENH-3649).

## Composition Review

The 28 children cover the epic's named contracts. Claude and Codex have completed stored paths; the six remaining hosts each have a separate evidence issue and delivery issue. ENH-3534 (done 2026-09-30) owned only shared replay/refresh infrastructure:

| Contract | Children | Remaining evidence or handoff |
|----------|----------|-------------------------------|
| Observation provenance and host attribution | ENH-3528, BUG-3542, ENH-3580, ENH-3546 | Done for proven Claude/Codex paths; new hosts retain host-specific proof gates |
| Codex rollout identity and live coverage | ENH-3532, ENH-3647, ENH-3655, ENH-3543 | Done; unresolved overlap remains audit-only |
| Stored usage freshness and consumers | ENH-3651, ENH-3656, ENH-3549 | Done for Claude/Codex; remaining hosts need their own triggers and readers |
| Remaining production hosts | ENH-3648, ENH-3534, ENH-3544, ENH-3660–3665, ENH-3671–3676 | Evidence issues prove native contracts; matching delivery issues own producer → trigger → reader |
| Context occupancy | BUG-3587, ENH-3545 | Done; general reader isolation is standalone ENH-3649 |

Each delivery issue is blocked only by its matching host evidence issue, not by other hosts' access. A host with unknown native evidence or no proven stored trigger stays explicitly unavailable; it is not counted as completed eight-host coverage.

## Eight-host completion ledger

Track each host's native evidence, stored producer, current-session trigger, and reader verdict independently. These are owners for the remaining proofs, not claims that their work has already landed:

| Host | Native evidence | Stored producer | Current-session trigger | Reader verdict |
|------|-----------------|-----------------|-------------------------|----------------|
| Claude Code | Verified Claude 2.1.284 live/transcript captures (ENH-3546) | Stored measured observations with replay eligibility (ENH-3546/3651) | Captured Stop hook and trailing derive (ENH-3651) | Stored, host/session selected, freshness-qualified cache rate (ENH-3656) |
| Codex | 0.158.0 rollout/live captures; live-to-rollout native join refuted (ENH-3532/3655) | Stored rollout requests and live identity (ENH-3532/3647) | Captured Stop hook and detached derive (ENH-3549) | Stored, coverage-qualified rate; unresolved overlap has audit subtotals only (ENH-3543/3549) |
| OpenCode | Partial real 1.1.53 live/stored evidence; ENH-3660 must prove component and part identity | ENH-3671 | ENH-3671 | ENH-3671; incomplete |
| Pi | Unknown; 0.84.2 probe lacked API key (ENH-3661) | ENH-3672 | ENH-3672 | ENH-3672; incomplete |
| Qwen | Partial real 0.24.6 pair; ENH-3662 must capture a parser-ready source and prove duplicate identity | ENH-3673 | ENH-3673 | ENH-3673; incomplete |
| Gemini | Unknown current-version contract; ENH-3663 needs configured capture and message identity | ENH-3674 | ENH-3674 | ENH-3674; incomplete |
| OMP | Unknown; CLI absent and existing fixtures synthetic (ENH-3664) | ENH-3675 | ENH-3675 | ENH-3675; incomplete |
| Kimi Code | Partial real 0.30.0 stored evidence; ENH-3665 must prove components and replay identity | ENH-3676 | ENH-3676 | ENH-3676; incomplete |

For each host, the in-scope consumption path is the native channel selected for canonical current-session reporting, plus any observed live/stored copy that could duplicate it. Its input, output, cache-read, and cache-creation semantics, request grain/identity, and reasoning/output relation need evidence wherever those fields affect canonical figures. An unselected auxiliary channel may remain `unknown` only when the ledger explicitly marks it outside that canonical path and explains why it cannot affect counting.

Before closing the epic, replace each owner entry with an evidence-backed verdict: implemented with a stored producer, actual after-usage trigger, and freshness-qualified reader for every supported in-scope metric; or explicitly unavailable where native absence is proved. Partial native support is recorded per metric/channel. Supported components may be stored with missing components null, but canonical totals and rates that need missing components remain unavailable. A missing trigger for a supported current-session path, an in-scope `unknown`, or an open/deferred host child keeps the epic open. Each host delivery issue owns retiring its direct transcript fallback after a proved stored cutover or replacing it with an explicit unavailable diagnostic after a proved native absence. Close the epic only when all host evidence/delivery children are `done` or `cancelled`, with no unresolved in-scope verdict; a cancellation requires the ledger to explain why no work remains. If intended scope shrinks, revise this goal and ledger explicitly.

## Impact

- **Priority**: P2 — six production hosts still lack proved stored usage paths; silent accounting errors remain possible if native duplicates or partial fields are guessed.
- **Effort**: Large — 13 unresolved children span shared replay, six native contracts, and six host delivery paths.
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

**Open shared infrastructure (1)**

- **ENH-3534** — Shared infrastructure for remaining-host token usage ingestion

**Open evidence children (6)**

- **ENH-3660** — Prove OpenCode cache and reasoning semantics
- **ENH-3661** — Capture Pi with a configured model
- **ENH-3662** — Prove Qwen live/cache and duplicate semantics
- **ENH-3663** — Capture versioned Gemini usage and identity
- **ENH-3664** — Capture real OMP usage
- **ENH-3665** — Prove Kimi component and replay identity

**Blocked host delivery (6)**

- **ENH-3671** — Implement OpenCode stored token usage (blocked by ENH-3660)
- **ENH-3672** — Implement Pi stored token usage (blocked by ENH-3661)
- **ENH-3673** — Implement Qwen stored token usage (blocked by ENH-3662)
- **ENH-3674** — Implement Gemini stored token usage (blocked by ENH-3663)
- **ENH-3675** — Implement OMP stored token usage (blocked by ENH-3664)
- **ENH-3676** — Implement Kimi Code stored token usage (blocked by ENH-3665)

Standalone **ENH-3649** (reader isolation and diagnostics) is done and remains outside this epic's child count.

## Implementation Order and Readiness

1. ENH-3534 verifies the already implemented shared dispatch and source refresh independently of native access to any one host.
2. ENH-3660–3665 prove each host's native metric, grain, and identity contract. OpenCode and Kimi have partial real captures; Pi, Qwen, Gemini, and OMP need working model access or a real CLI capture. Missing access leaves the affected evidence unknown and the issue open or blocked.
3. When a host's contract is sufficient, only its matching ENH-3671–3676 delivery issue becomes actionable. That issue proves a parser-ready source, idempotent stored observation, current-session trigger, incremental derivation, shared selection, and freshness-qualified reader. Other hosts' evidence does not block it.
4. A delivery issue with evidence-backed native absence must first settle the direct-fallback behavior and unavailable diagnostic; cancel it only if no code or documentation work remains. For a partly supported host, ingest proved components and leave unsupported components null and dependent totals/rates unavailable. If no after-usage event exists, prove another current-session trigger or leave the issue open for a scope decision. The epic stays open for any in-scope unknown, missing trigger, or unresolved host child.

## Schema coordination

`SCHEMA_VERSION` is 58. ENH-3532, ENH-3647, ENH-3546, and ENH-3651 have already landed their shared replay, identity, eligibility, and derive-checkpoint migrations. A host delivery issue that needs a new column takes the next append-only version in landing order. Attributes needed after rebuild must survive on `raw_events`; source/request identity, verified host attribution, and reader-visible derive freshness must remain consistent through incremental derive and full rebuild.

## Shared-consumer notes

- `quality_regressions.py` and `agent_quality.py` remain channel-pinned so newly identified Codex rows do not silently change existing aggregates.
- `select_usage_coverage` reconciles candidates for a verified host/thread pair before report filters. `select_usage_observations` delegates to the same policy. An ID-only call is rejected.

## Cross-Issue Acceptance Criteria

- [x] Source usage/cost/waste/quality and built-in snapshot/dashboard aggregates agree on selection, qualification and audit subtotals for matched, partial and unresolved coverage (ENH-3543).
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
- [ ] ENH-3660–3665 record per-metric/channel native verdicts and replay identity with versioned evidence; failed authentication, absent CLI access, or zero-only samples remain `unknown`, never `unsupported`. No evidence issue closes with an unresolved in-scope canonical-path verdict.
- [ ] For each supported remaining-host path, its matching ENH-3671–3676 issue proves parser-ready native input → stored qualified observation → actual current-session trigger → incremental derive → host/session-selected, freshness-qualified reader; replay and duplicate sources do not inflate canonical totals.
- [ ] Every production host has an evidence-backed terminal ledger verdict, including partial-component and direct-fallback disposition; in-scope unknown capability, absent trigger, or open/deferred per-host child leaves the epic open.

## Review Notes

Pre-implementation issue revision 2026-09-29: split ENH-3534 to shared replay/refresh work, created host delivery children ENH-3671–3676 with one evidence blocker each, and assigned their producer/trigger/reader ownership in the ledger. ENH-3660–3665 now require per-metric/channel evidence verdicts and explicit access blockers; Qwen needs a parser-ready native capture. A Sonnet follow-up tightened the in-scope unknown, partial-support, missing-trigger, and direct-fallback closeout rules. Counts, implementation order, and schema version reflect the current issue graph and code. No host ingestion implementation is claimed by these issue edits.

Implementation review 2026-09-29: the full local suite passed (27,525 passed, 301 skipped); lint, format, host-map and private-reference verification passed. The configured mypy command is blocked by this environment's untyped `ruamel` dependency and older mypy/dependency stubs; no type-check pass is claimed. Eleven more epic children reached done, as did standalone ENH-3649. Six native producer contracts remain unproved, so ENH-3534 and the epic remain unresolved.

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
- Evidence tiers: source-cited producer evidence is a distinct lower tier (provider-keyed, version-pinned, marked separately in `TelemetryCapability`); it never satisfies a delivery issue's Completion Rule or licenses measured canonical totals/rates without a captured nonzero-cache sample.
- Partial support: a component may be stored null only when it is evidence-backed unsupported or the ledger names it outside the canonical path — never while `unknown`. Unblocking a host on a partial contract needs an explicit per-host ledger revision here.
- Missing gate (to add under the Kimi/OpenCode work): a test asserting each fixture README verdict table agrees with the typed telemetry map; `test_verify_host_map.py` checks completeness only.
