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

Coordinate token usage ingestion, observation provenance, context-occupancy labeling/correctness, and runtime telemetry across the eight production hosts (Claude Code, Codex, OpenCode, Pi, Qwen, Gemini, OMP, Kimi Code). The epic has 15 children: 4 done and 11 open after the 2026-09-28 review, which split ENH-3543, ENH-3534 and ENH-3549, and the 2026-09-29 review, which split ENH-3651 out of ENH-3549. Native availability, ingestion support, observation provenance, coverage, and occupancy are separate contracts.

## Goal

Every token figure little-loops reports — for any production host — comes from a stored, normalized observation with explicit provenance and coverage qualification, counted once, and context occupancy is never confused with consumption.

## Scope

- **In scope**: host usage ingestion (Codex rollout, remaining hosts), Claude/Codex producer contracts, live/rollout identity and coverage selection, typed telemetry availability, context-hook occupancy labels, and stored-usage consumers (`ll-ctx-stats`, dashboard, quality regressions).
- **Out of scope**: pricing for non-Anthropic models, estimator accuracy, occupancy monitors for non-Claude hosts, Claude live/transcript overlap reconciliation.

## Impact

- **Priority**: P2 — multi-host token figures are currently mostly `unknown` and will double-count once rollout ingestion lands without selection.
- **Effort**: Large — 11 open children across session store, runners, readers and hooks.
- **Risk**: Medium — accounting errors are silent; mitigated by fixture-backed contracts and conservative unresolved defaults.

## Children

**Done**

- **ENH-3528** — Label token provenance per observation in ll-ctx-stats and exports
- **BUG-3542** — Raw-event backfill stamps the configured host instead of each handle's source host
- **ENH-3580** — Carry usage_events provenance columns through UsageEvent and shareable export
- **BUG-3587** — Invocation consumption is used as context occupancy

**Open — unblocked now**

- **ENH-3532** — Ingest Codex historical rollout token usage into usage_events (gate 1 key and mixed event-shape coverage need current-version fixtures)
- **ENH-3544** — Typed runtime telemetry availability in the runtime host map
- **ENH-3545** — Label context-hook occupancy estimates and measurement staleness
- **ENH-3546** — Establish Claude usage producer contract and measured provenance (evidence capture first)
- **ENH-3647** — Carry Codex live session and invocation identity into usage_events (split from ENH-3543)
- **ENH-3648** — Survey token usage fields for OpenCode, Pi, Qwen, Gemini, OMP and Kimi Code (split from ENH-3534)
- **ENH-3649** — Session-reader isolation gate, no-session diagnostics and read-side fake-host coverage (split from ENH-3549)
- **ENH-3651** — Hook-driven incremental ingest, initial catch-up and shared derive of replayable usage into usage_events (split from ENH-3549; blocks it)

**Open — blocked**

- **ENH-3543** — Shared live/rollout coverage selection for Codex usage (blocked by ENH-3532, ENH-3647; join spike first)
- **ENH-3549** — Consume stored usage for ll-ctx-stats cache rate (blocked by ENH-3532 for Codex, ENH-3651 for stored freshness)
- **ENH-3534** — Token usage ingestion for Qwen, Gemini, OMP and remaining hosts (blocked by ENH-3532, ENH-3544, ENH-3648)
- **ENH-3655** — Prove Codex live-to-rollout span join (open)
- **ENH-3656** — Cut over Claude cache rate to stored usage (open)




## Implementation Order and Readiness

1. **Parallel, now:** ENH-3544 (capability matrix; Claude/Codex evidence only, others `unknown`), ENH-3545 (labels only), ENH-3546 (Claude fixture capture, then eligibility), ENH-3648 (six-host survey), ENH-3649 (isolation gate and diagnostics), **the ENH-3543 join spike** (fixtures only; must not gate ENH-3647), **Codex fixture capture for ENH-3532** (fork, paginated thread, 0.154+ `token_usage_record`, mixed/partial event shapes, re-emitted notification, non-advancing total), and ENH-3651's catch-up/checkpoint design.
2. **Codex identity:** use the verified host + **thread** ID (`session_meta.payload.id` / live `thread.started.thread_id`) for usage rows; the root/parent `payload.session_id` is not the thread ID in a fork. Agree identity-basis and span field names across ENH-3532 and ENH-3647 (see § Schema coordination), then land ENH-3532 (rollout ingestion) and ENH-3647 (live identity) in either order. Readers keep the unreconciled-sum contract in between.
3. **Reconciliation:** ENH-3543 spikes the ordering join against the fixtures, then adds the selector, the paired verified-host/thread filter and reader/dashboard parity. If the spike refutes the join, the selector ships with conservative unresolved behavior only.
4. **Consumers:** ENH-3651 owns first-enable catch-up of already-ingested raw rows, atomic incremental derivation for replayable usage channels (including rollout once ENH-3532 lands), and the host-specific hook trigger. ENH-3549's Claude path ships after its current-session stored read is proven; the Codex path waits for ENH-3532 **and** the combined Codex ingest → incremental derive → read fixture. ENH-3549 adds the paired host/session selector filter itself if ENH-3543 has not. Other hosts without a stored producer/trigger report unavailable until ENH-3534 or a linked host-specific issue lands; they do not count toward completed eight-host coverage.
5. **Remaining hosts:** ENH-3534 after ENH-3648's findings, ENH-3532's `UsageReplayRecord` contract and ENH-3544's vocabulary. Re-ingestion must address already-stripped payloads; unknown capability is not unsupported.

## Schema coordination

`SCHEMA_VERSION` is 55, and about 20 tests pin it. The following children may add append-only migrations:

| Issue | Tables | Content |
|-------|--------|---------|
| ENH-3532 | `raw_events`, `usage_events` | native `ordinal` on `raw_events` (copied on replay; legacy rows stay NULL unless re-read); stream discriminator; `response_id` + source key + span `turn_id` on `usage_events`; partial dedup indexes (repair-first). Key revised 2026-09-29: `(host, response_id)` where `token_usage_record` exists, else `(host, payload.id, stream discriminator, ordinal)` |
| ENH-3647 | `usage_events` | identity-basis marker (host-observed vs local), if not added by ENH-3532 |
| ENH-3546 | `raw_events`, `usage_events` | producer-eligibility discriminator on `raw_events` (copied on replay) |
| ENH-3651 | `meta`, possibly `usage_events` | durable derive checkpoint and source-row identity if the chosen atomic catch-up/retry design needs them; full rebuild and incremental derive update the checkpoint consistently |

Rules: migrations take the next version in landing order and are never renumbered after landing. ENH-3532 and ENH-3647 fix the identity-basis/span column names together before either lands; whichever lands first adds shared columns and the other reuses them. Any replay-surviving attribute goes on `raw_events` first, since `rebuild()` regenerates `usage_events` from it (the BUG-3542 `host_basis` pattern).

## Shared-consumer notes

- `issue_history/quality_regressions.py` weights model composition by `COUNT(*) FROM usage_events WHERE session_id IS NOT NULL`, which today means `channel = 'transcript'`. `issue_history/agent_quality.py::_usage_totals` (cost per issue) likewise reads every row with a `session_id` through the selector and would double-count once live/rollout rows carry one. ENH-3532 and ENH-3647 each pin **both** to `channel = 'transcript'` (whichever lands first); ENH-3543 decides whether they later read through the selector.
- `select_usage_observations` gains a paired `host` + `session_id` filter (ENH-3543 / ENH-3549, whichever first); an ID-only call is rejected. Candidate matching is limited to a verified host/thread pair, then report filters apply after reconciliation.

## Cross-Issue Acceptance Criteria

- [ ] Source usage/cost/waste/quality and built-in snapshot/dashboard aggregates agree on selection, qualification and audit subtotals for matched, partial and unresolved coverage (ENH-3543).
- [ ] Canonical token components, event/request identity, run/state attribution, and report-window rules remain consistent through ingest, rebuild and export (ENH-3532/3543/3647).
- [ ] Legacy/unverified producer evidence is never promoted by rebuild; missing originals/usage remain explicit rather than fabricated measurements (ENH-3534/3546).
- [ ] Adding session identity to live or rollout rows never silently changes an existing aggregate (`quality_regressions` and `agent_quality` pins; ENH-3532/3647).
- [ ] A Codex observation is counted once across forks, resumes, paginated threads, re-emitted notifications and both `token_usage_record`/`token_count` event shapes; `session_id` means the same thing in ENH-3532, ENH-3647 and ENH-3549.
- [ ] Mixed/partial Codex event streams never lose old-shape-only usage through file-wide suppression; overlapping old/new records are counted once only when request coverage is proven, otherwise remain explicitly unresolved (ENH-3532).
- [ ] First-enable and normalizer-version catch-up materialize previously ingested raw usage in either ENH-3532/ENH-3651 landing order; incremental rows and their checkpoint commit atomically, rebuild preserves the checkpoint contract, and Codex rollout reaches the stored reader without a per-turn full rebuild (ENH-3651/3532/3549).
- [ ] A selected session is qualified by verified host plus thread ID; same-ID rows from another host or unverified host attribution cannot enter its cache-rate figure (ENH-3543/3549).
- [ ] Context consumption and occupancy have separate semantics (done in BUG-3587); baseline freshness survives estimate updates and fallback output exposes it (ENH-3545).

## Review Notes

Pre-implementation review 2026-09-24 applied to specifications only. Review 2026-09-28: refreshed stale child statuses (ENH-3580, BUG-3587 done); closed ENH-3532 gates 2–3 from fixtures and proposed a gate-1 key; split ENH-3543 → ENH-3647, ENH-3534 → ENH-3648, ENH-3549 → ENH-3649; added schema coordination, the `quality_regressions` consumer and ENH-3549's current-session freshness gate. Historical confidence scores do not certify the revised scopes. Child frontmatter is authoritative for status/progress.

Review 2026-09-29 (corpus check of `~/.codex/sessions` plus an opus consult): ENH-3532's `(host, session_id, ordinal)` key collides on forks and paginated threads and cannot dedupe duplicate notifications; newer Codex writes `token_usage_record` alongside `token_count`; `agent_quality._usage_totals` needed the same channel pin as `quality_regressions`; the ENH-3543 spike moved to step 1; ENH-3549 staged Claude-first with the hook-driven ingest split out; added missing `blocks` backlinks on ENH-3532 and normalized ENH-3549 to `blocked_by`. Fixtures are `codex-cli 0.152.1` while local sessions come from 0.154–0.158 alphas, so every Codex contract needs a current-version fixture.

Follow-up review 2026-09-29: assigned shared incremental derivation and first-enable catch-up to ENH-3651, with Codex normalization remaining in ENH-3532; replaced file-wide `token_count` suppression with a mixed-stream evidence gate; fixed the thread/root ID contradiction; required host-qualified session filtering; and removed ENH-3549's superseded freshness options. These are specification changes only, and the producer fixtures, join spike and checkpoint design remain implementation gates.

## Status

**Open** | Created: 2026-09-24 | Priority: P2