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

Coordinate token usage ingestion, observation provenance, context-occupancy labeling/correctness, and runtime telemetry across the eight production hosts (Claude Code, Codex, OpenCode, Pi, Qwen, Gemini, OMP, Kimi Code). The epic has 11 children: 2 done and 9 open after the pre-implementation review. Native availability, ingestion support, observation provenance, coverage, and occupancy are separate contracts.

## Children

- **ENH-3528** — Label token provenance per observation in ll-ctx-stats and exports (done)
- **ENH-3532** — Ingest Codex historical rollout token usage into usage_events (open)
- **ENH-3534** — Token usage ingestion for Qwen, Gemini, OMP and remaining hosts (open)
- **ENH-3543** — Codex live identity plumbing and shared live-rollout coverage selection (open)
- **ENH-3544** — Typed runtime telemetry availability in the runtime host map (open)
- **ENH-3545** — Label context-hook occupancy estimates and measurement staleness (open)
- **ENH-3546** — Establish Claude usage producer contract and measured provenance (open)
- **ENH-3549** — Finish session-reader isolation and consume stored usage in ll-ctx-stats (open)
- **BUG-3542** — Raw-event backfill stamps the configured host instead of each handle's source host (done)
- **ENH-3580** — Carry usage_events provenance columns through UsageEvent and shareable export (open)
- **BUG-3587** — Invocation consumption is used as context occupancy (open)

## Implementation Order and Readiness

1. ENH-3580 can land independently. Finalize ENH-3544's typed metric/channel matrix; native capability is separate from ingestion support.
2. Resolve ENH-3532's persisted source/request identity gates and ENH-3543's producer-backed live-to-span correlation before their implementations. Reuse `session_id`/`invocation_id`; agree span/basis fields before migrations. ENH-3532 ingestion precedes ENH-3543 reconciliation, with conservative reporting in between.
3. ENH-3546 must establish host/path eligibility and preserve legacy uncertainty across rebuild. Its evidence work can proceed independently.
4. Survey remaining hosts in ENH-3534, then implement against ENH-3532's replay foundation and ENH-3544's capability vocabulary. Re-ingestion must address already-stripped payloads; unknown capability is not unsupported.
5. ENH-3549 consumes stored normalized usage through the existing selector; reuse completed reader migration and spike evidence. Its diagnostics/gates can proceed before full host ingestion.
6. ENH-3545 adds labels/staleness and propagates them through fallback reports without changing numeric guard behavior. BUG-3587 separately corrects consumption-as-occupancy decisions; no dependency cycle is required.

## Cross-Issue Acceptance Criteria

- [ ] Source usage/cost/waste and built-in snapshot/dashboard aggregates agree on selection, qualification and audit subtotals for matched, partial and unresolved coverage (ENH-3543).
- [ ] Canonical token components, event/request identity, run/state attribution, and report-window rules remain consistent through ingest, rebuild and export (ENH-3532/3543).
- [ ] Legacy/unverified producer evidence is never promoted by rebuild; missing originals/usage remain explicit rather than fabricated measurements (ENH-3534/3546).
- [ ] Context consumption and occupancy have separate semantics, baseline freshness survives estimate updates, and fallback output exposes the distinction (ENH-3545/BUG-3587).

## Review Notes

Pre-implementation review applied to specifications only. Open evidence gates remain open; historical confidence scores are not a new implementation-readiness approval. Child frontmatter is authoritative for status/progress.
