---
id: FEAT-3722
type: FEAT
title: ll-next producer-evidence attribution and opt-in activity pressure
priority: P4
status: deferred
discovered_by: ll-issues-create
discovered_date: '2026-10-04'
captured_at: '2026-10-04T01:29:51Z'
relates_to:
- EPIC-3710
- FEAT-3711
- FEAT-3721
deferred_by: human
deferred_date: '2026-10-04T01:40:00Z'
---

# FEAT-3722: ll-next producer-evidence attribution and opt-in activity pressure

## Summary

Holding issue for the pieces cut from FEAT-3711 after an Opus review (2026-10-03): (1) `ProducerEvidence` adapters with automatic **observed-acceptance** attribution, and (2) **opt-in activity-based bucket pressure**. Deferred: both are observational, there are no recommendation events to attribute yet, and default-off observational features tend to go unmeasured. Detached from EPIC-3710 because deferred is non-terminal and would strand the epic branch. Revive after FEAT-3711's explicit accept/feedback ships and real events exist.

## Preserved design (from FEAT-3711 review rounds, 2026-10-03)

### Producer evidence and attribution

- `ProducerEvidence(key, action_key, target_key, action_fingerprint|None, activity_bucket, event_at, available_at, availability_basis, provenance)`; stable semantic key rather than row IDs (skill rows can be rebuilt): skills = normalized session/timestamp/operation/explicit-target tuple, orchestration = driver/run_id/issue_id/start, loops = run_id. Exact argument tokens only (BUG-1 ≠ BUG-10); truncated (200-char skill args / 50-token argv), ambiguous or implicit targets are unknown.
- Operation evidence: `manage-issue` skill_events with explicit TYPE + fix/implement/improve + exact ID (exclude verify/plan/dry-run); `orchestration_runs` rows are evidence of a **pick/attempt**, not a passed gate; refinement skills match on the exact displayed `action_key` + explicit target; `loop_runs` usable only once completion is observable (`ended_at <= as_of`) and, for parameterized loops, only when input/context fingerprint-equals the offer. Sprint/scan adapters only where FEAT-3713 can verify exact target/scope.
- Backfilled skills lack reliable arrival timestamps: mark `event_time_proxy`.
- Attribution: same `action_key` + namespaced target + proven fingerprint with `shown.ts <= event_at <= shown.ts + match_window_days` (default 7); one producer credits **one** most recent eligible offer (ties by `rec_id`); coalesce duplicate evidence by semantic identity. Results are `accepted | unknown` with reasons; expiry never yields `ignored`. `cli_event_context` records exit 0 on a normal nonzero return, so CLI evidence has outcome unknown.
- Pure `derive_acceptance(shown, acknowledgements, producers, *, as_of, window) -> Mapping[str, AcceptanceResult]`.

### Opt-in activity pressure

- Settings: `next.pressure.enabled=false`, `next.pressure.cap_days=14`, `next.acceptance.match_window_days=7`.
- `pressure_v = min(max((as_of - t_v).total_seconds()/86400, 0), cap_days)/cap_days`, with `t_v` the latest qualified producer's available evidence time or an explicit acknowledgement in that bucket; no evidence → `pressure=null`, ordered as zero, with a diagnostic. Activity-bucket map: manage-issue implementation and per-issue picks → implement-issue; named refinement ops → refine-issue; qualified loop runs → run-loop; `resolve-blocker` pressure from explicit acknowledgements only.
- Pressure only reorders buckets within round-robin rounds (descending pressure, ties by canonical verb order); caps, dedup, alternates unchanged; display never changes `t_v`; `--type`/`--no-record` don't change selection.

## Revive criteria

- FEAT-3711 shipped with real `recommendation_events` rows; a usefulness check shows `ll-next` diverges meaningfully from `ll-issues next-issue`; a plan to measure pressure's effect exists.

## Status

**Deferred** | Created: 2026-10-04 | Priority: P4
