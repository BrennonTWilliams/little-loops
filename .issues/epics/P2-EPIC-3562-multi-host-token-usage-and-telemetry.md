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

Each ENH-3660–3665 evidence issue selects the canonical native channel/source, or records an evidence-backed no-source verdict, in its fixture README and this ledger before it can close. Record provider and CLI version, any observed copy that could duplicate a selected source, and why an excluded auxiliary channel cannot change the canonical figure. The selected path's input, output, cache-read, and cache-creation semantics, request grain/identity, and reasoning/output relation need evidence wherever they affect canonical figures. An unselected auxiliary channel may remain `unknown` only with that explicit exclusion and non-duplication reason.

`TelemetryCapability` describes native availability for fields named like normalized `usage_events` components. It does not certify stored measurement, evidence tier, or a separate reasoning-token column. A raw field that cannot yet be mapped to the named component (for example inclusive `tokens.input` with unknown cache splitting) stays `unknown`. A captured native field marked `supported` can still have unresolved normalization or identity and cannot by itself produce a measured observation. `token_reporting_summary: full` means native field availability across channels, never a measured stored total.

The fixture README records provider, version, evidence tier, inclusivity, omission behavior, and reasoning/output relationship for each metric/channel. Source-cited producer evidence is provisional: a source-only typed-map entry stays `unknown` with a source-cited note until captured native evidence supports `supported` or affirmative evidence supports `unsupported`. A host-level `supported` claim needs at least one captured provider/version case and a note naming its scope; it does not certify every provider. Table-backed `TelemetryCapability.note` entries cite stable `README:<row-id>` evidence IDs for the shared test.

Record reasoning inclusion in the README and the `output_tokens` note; an unresolved output/reasoning relation prevents a measured normalized output figure. The first of ENH-3660/3665 to prepare a closing change adds one shared, parameterized README-to-map evidence test and table format; ENH-3665 owns it if both proceed together. The test covers only the six remaining hosts with a structured table, and each later evidence issue adds its host's rows. Claude/Codex and not-yet-captured hosts retain their existing verification until their tables exist. A nonzero-cache capture is required to claim a supported cache component's measured semantics when cache behavior affects a canonical figure or rate. It is not required for an evidence-backed unsupported cache component.

Before closing the epic, replace each owner entry with an evidence-backed verdict: implemented with a stored producer, actual after-usage trigger, and freshness-qualified reader for every supported in-scope metric; or explicitly unavailable where native absence is proved. Failed authentication, absent CLI installation, and zero-only samples are `unknown`, never evidence-backed no-source verdicts. Partial native support is recorded per metric/channel. Supported components may be stored with missing components null as audit observations. Under the current row-level provenance contract, a row missing a required canonical component remains `unknown`, even if its present fields are proved; dependent canonical totals and rates remain unavailable. A partial-host delivery issue may close after it stores proved components with replay and freshness qualification and emits an explicit unavailable diagnostic for dependent canonical figures, with the ledger explaining that audit-only disposition. A host delivery issue may propose a separately tested component-level qualification contract if it needs a measured component figure from such a row. A missing trigger for a supported current-session path, an in-scope `unknown`, or an open/deferred host child keeps the epic open. Each host delivery issue owns retiring its direct transcript fallback after a proved stored cutover or replacing it with an explicit unavailable diagnostic after a proved native absence or evidence-backed partial support. Close the epic only when all host evidence/delivery children are `done` or `cancelled`, with no unresolved in-scope verdict; a cancellation requires the ledger to explain why no work remains. If intended scope shrinks, revise this goal and ledger explicitly.

## Impact

- **Priority**: P2 — six production hosts still lack proved stored usage paths; silent accounting errors remain possible if native duplicates or partial fields are guessed.
- **Effort**: Large — 12 unresolved children span six native contracts and six host delivery paths; shared replay is done.
- **Risk**: Medium — accounting errors are silent; mitigated by fixture-backed contracts and conservative unresolved defaults.

## Children

**Done (16)**

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
- **BUG-3696** — ll-loop usage table est_cost n/a: claude-sonnet-5-5 missing from MODEL_PRICING, no approximate fallback (open)


## Implementation Order and Readiness

1. ENH-3534's shared dispatch and safe refresh baseline is done. Each delivery issue owns the extensions needed for its native source layout, derive behavior, and trigger, with shared regression tests.
2. ENH-3660–3665 prove each host's native metric, grain, identity, and canonical source decision or no-source verdict, and record a candidate after-usage trigger or its absence early. OpenCode and Kimi have partial real captures; Pi, Qwen, Gemini, and OMP need working model access or a real CLI capture. Missing access leaves affected evidence unknown and the issue open or blocked.
3. When a host's contract is sufficient, only its matching ENH-3671–3676 delivery issue becomes actionable. That issue proves a parser-ready **real native source layout**, idempotent stored observation, current-session trigger, incremental derivation, shared selection, and freshness-qualified reader. Other hosts' evidence does not block it. ENH-3671 must first replace the assumed OpenCode JSONL discovery path with an adapter for the captured storage tree.
4. A delivery issue with evidence-backed native absence must first settle the direct-fallback behavior and unavailable diagnostic; cancel it only if no code or documentation work remains. For a partly supported host, store proved components with unsupported components null as audit observations; dependent canonical totals/rates stay unavailable under the current row-level provenance rule. If no after-usage event exists, prove another current-session trigger or leave the issue open for a scope decision. The epic stays open for any in-scope unknown, missing trigger, or unresolved host child.

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
- [ ] ENH-3660–3665 select each host's canonical source or prove no native source, classify possible duplicate channels in the ledger, then record per-metric/channel native verdicts and replay identity with versioned evidence. Failed authentication, absent CLI access, or zero-only samples remain `unknown`, never `unsupported`. Source-only evidence stays a provisional README tier and typed-map `unknown`; no evidence issue closes with an unresolved in-scope canonical-path verdict. One shared README-to-map evidence test covers all six hosts.
- [ ] For each supported remaining-host path, its matching ENH-3671–3676 issue proves discovery of the real native source layout → stored qualified observation → actual current-session trigger → incremental derive → host/session-selected, freshness-qualified reader; replay and duplicate sources do not inflate canonical totals. Each delivery issue owns the needed shared-seam extension and regression tests.
- [ ] Every production host has an evidence-backed terminal ledger verdict, including partial-component and direct-fallback disposition; in-scope unknown capability, absent trigger, or open/deferred per-host child leaves the epic open.

## Review Notes

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

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): In addition to append-only schema-version ordering: for shared usage seams (`refresh_usage_source`, `_derive_usage_incremental_conn`, `usage_source_freshness`, `_run_usage_trigger` dispatch, shared tests), the first per-host delivery issue (ENH-3671/3672/3673 and later) to land owns the change; later hosts extend via host-keyed dispatch and rebase.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:31 - `b32e58bb-e3b8-4048-9c71-1c2f63665ce9.jsonl`