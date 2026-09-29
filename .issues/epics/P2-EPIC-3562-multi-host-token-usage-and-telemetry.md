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

Coordinate token usage ingestion, observation provenance, context-occupancy labeling/correctness, and runtime telemetry across the eight production hosts (Claude Code, Codex, OpenCode, Pi, Qwen, Gemini, OMP, Kimi Code). The epic has 14 children: 4 done and 10 open after the 2026-09-28 review, which split ENH-3543, ENH-3534 and ENH-3549. Native availability, ingestion support, observation provenance, coverage, and occupancy are separate contracts.

## Goal

Every token figure little-loops reports — for any production host — comes from a stored, normalized observation with explicit provenance and coverage qualification, counted once, and context occupancy is never confused with consumption.

## Scope

- **In scope**: host usage ingestion (Codex rollout, remaining hosts), Claude/Codex producer contracts, live/rollout identity and coverage selection, typed telemetry availability, context-hook occupancy labels, and stored-usage consumers (`ll-ctx-stats`, dashboard, quality regressions).
- **Out of scope**: pricing for non-Anthropic models, estimator accuracy, occupancy monitors for non-Claude hosts, Claude live/transcript overlap reconciliation.

## Impact

- **Priority**: P2 — multi-host token figures are currently mostly `unknown` and will double-count once rollout ingestion lands without selection.
- **Effort**: Large — 10 open children across session store, runners, readers and hooks.
- **Risk**: Medium — accounting errors are silent; mitigated by fixture-backed contracts and conservative unresolved defaults.

## Children

**Done**

- **ENH-3528** — Label token provenance per observation in ll-ctx-stats and exports
- **BUG-3542** — Raw-event backfill stamps the configured host instead of each handle's source host
- **ENH-3580** — Carry usage_events provenance columns through UsageEvent and shareable export
- **BUG-3587** — Invocation consumption is used as context occupancy

**Open — unblocked now**

- **ENH-3532** — Ingest Codex historical rollout token usage into usage_events (gate 1 key proposed; confirm fork-session case)
- **ENH-3544** — Typed runtime telemetry availability in the runtime host map
- **ENH-3545** — Label context-hook occupancy estimates and measurement staleness
- **ENH-3546** — Establish Claude usage producer contract and measured provenance (evidence capture first)
- **ENH-3647** — Carry Codex live session and invocation identity into usage_events (split from ENH-3543)
- **ENH-3648** — Survey token usage fields for OpenCode, Pi, Qwen, Gemini, OMP and Kimi Code (split from ENH-3534)
- **ENH-3649** — Session-reader isolation gate, no-session diagnostics and read-side fake-host coverage (split from ENH-3549)

**Open — blocked**

- **ENH-3543** — Shared live/rollout coverage selection for Codex usage (blocked by ENH-3532, ENH-3647; join spike first)
- **ENH-3549** — Consume stored usage for ll-ctx-stats cache rate (depends on ENH-3532; freshness gate)
- **ENH-3534** — Token usage ingestion for Qwen, Gemini, OMP and remaining hosts (blocked by ENH-3532, ENH-3544, ENH-3648)

## Implementation Order and Readiness

1. **Parallel, now:** ENH-3544 (capability matrix; Claude/Codex evidence only, others `unknown`), ENH-3545 (labels only), ENH-3546 (Claude fixture capture, then eligibility), ENH-3648 (six-host survey), ENH-3649 (isolation gate and diagnostics), **the ENH-3543 join spike** (fixtures only; must not gate ENH-3647), and **Codex fixture capture for ENH-3532** (fork, paginated thread, 0.154+ `token_usage_record`, re-emitted notification, non-advancing total).
2. **Codex identity:** agree the identity-basis, span field names **and the meaning of `session_id` (thread vs root; recommended thread, ENH-3532 gate 1 rule c)** across ENH-3532 and ENH-3647 (see § Schema coordination), then land ENH-3532 (rollout ingestion) and ENH-3647 (live identity) in either order. Readers keep the unreconciled-sum contract in between.
3. **Reconciliation:** ENH-3543 spikes the ordering join against the fixtures, then adds the selector, the `session_id` filter and reader/dashboard parity. If the spike refutes the join, the selector ships with conservative unresolved behavior only.
4. **Consumers:** ENH-3549's Claude path can ship once the session-id meaning is fixed; its Codex path follows ENH-3532. Its freshness gate is decided as B/C, and the hook-driven ingest (option A) is split into a separate issue. It adds the `session_id` selector filter itself if ENH-3543 has not.
5. **Remaining hosts:** ENH-3534 after ENH-3648's findings, ENH-3532's `UsageReplayRecord` contract and ENH-3544's vocabulary. Re-ingestion must address already-stripped payloads; unknown capability is not unsupported.

## Schema coordination

`SCHEMA_VERSION` is 55, and about 20 tests pin it. Up to three children add append-only migrations:

| Issue | Tables | Content |
|-------|--------|---------|
| ENH-3532 | `raw_events`, `usage_events` | native `ordinal` on `raw_events` (copied on replay; legacy rows stay NULL unless re-read); stream discriminator; `response_id` + source key + span `turn_id` on `usage_events`; partial dedup indexes (repair-first). Key revised 2026-09-29: `(host, response_id)` where `token_usage_record` exists, else `(host, payload.id, stream discriminator, ordinal)` |
| ENH-3647 | `usage_events` | identity-basis marker (host-observed vs local), if not added by ENH-3532 |
| ENH-3546 | `raw_events`, `usage_events` | producer-eligibility discriminator on `raw_events` (copied on replay) |

Rules: migrations take the next version in landing order and are never renumbered after landing. ENH-3532 and ENH-3647 fix the identity-basis/span column names together before either lands; whichever lands first adds shared columns and the other reuses them. Any replay-surviving attribute goes on `raw_events` first, since `rebuild()` regenerates `usage_events` from it (the BUG-3542 `host_basis` pattern).

## Shared-consumer notes

- `issue_history/quality_regressions.py` weights model composition by `COUNT(*) FROM usage_events WHERE session_id IS NOT NULL`, which today means `channel = 'transcript'`. `issue_history/agent_quality.py::_usage_totals` (cost per issue) likewise reads every row with a `session_id` through the selector and would double-count once live/rollout rows carry one. ENH-3532 and ENH-3647 each pin **both** to `channel = 'transcript'` (whichever lands first); ENH-3543 decides whether they later read through the selector.
- `select_usage_observations` gains a `session_id` filter (ENH-3543 / ENH-3549, whichever first) that reconciles before filtering.

## Cross-Issue Acceptance Criteria

- [ ] Source usage/cost/waste/quality and built-in snapshot/dashboard aggregates agree on selection, qualification and audit subtotals for matched, partial and unresolved coverage (ENH-3543).
- [ ] Canonical token components, event/request identity, run/state attribution, and report-window rules remain consistent through ingest, rebuild and export (ENH-3532/3543/3647).
- [ ] Legacy/unverified producer evidence is never promoted by rebuild; missing originals/usage remain explicit rather than fabricated measurements (ENH-3534/3546).
- [ ] Adding session identity to live or rollout rows never silently changes an existing aggregate (`quality_regressions` and `agent_quality` pins; ENH-3532/3647).
- [ ] A Codex observation is counted once across forks, resumes, paginated threads, re-emitted notifications and both `token_usage_record`/`token_count` event shapes; `session_id` means the same thing in ENH-3532, ENH-3647 and ENH-3549.
- [ ] Context consumption and occupancy have separate semantics (done in BUG-3587); baseline freshness survives estimate updates and fallback output exposes it (ENH-3545).

## Review Notes

Pre-implementation review 2026-09-24 applied to specifications only. Review 2026-09-28: refreshed stale child statuses (ENH-3580, BUG-3587 done); closed ENH-3532 gates 2–3 from fixtures and proposed a gate-1 key; split ENH-3543 → ENH-3647, ENH-3534 → ENH-3648, ENH-3549 → ENH-3649; added schema coordination, the `quality_regressions` consumer and ENH-3549's current-session freshness gate. Historical confidence scores do not certify the revised scopes. Child frontmatter is authoritative for status/progress.

Review 2026-09-29 (corpus check of `~/.codex/sessions` plus an opus consult): ENH-3532's `(host, session_id, ordinal)` key collides on forks and paginated threads and cannot dedupe duplicate notifications; newer Codex writes `token_usage_record` alongside `token_count`; `agent_quality._usage_totals` needed the same channel pin as `quality_regressions`; the ENH-3543 spike moved to step 1; ENH-3549 staged Claude-first with the hook-driven ingest split out; added missing `blocks` backlinks on ENH-3532 and normalized ENH-3549 to `blocked_by`. Fixtures are `codex-cli 0.152.1` while local sessions come from 0.154–0.158 alphas, so every Codex contract needs a current-version fixture.

## Status

**Open** | Created: 2026-09-24 | Priority: P2
