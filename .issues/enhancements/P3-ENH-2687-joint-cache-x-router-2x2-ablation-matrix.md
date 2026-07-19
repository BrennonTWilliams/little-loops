---
id: ENH-2687
title: "Joint cache \xD7 router 2\xD72 ablation matrix (EPIC-2456 [TBD-19], OQ #7)"
type: ENH
priority: P3
status: deferred
captured_at: '2026-07-19T00:10:20Z'
discovered_date: 2026-07-19
discovered_by: manage-issue
parent: EPIC-2456
relates_to:
- FEAT-2673
- FEAT-2674
labels:
- token-cost
- caching
- routing
- tier-4
deferred_by: human
deferred_date: '2026-07-19T00:11:50Z'
---

# ENH-2687: Joint cache × router 2×2 ablation matrix

## Summary

EPIC-2456 § Cross-tier verification `[TBD-19]` — a joint cache (Tier 2, F1)
× router (Tier 4) 2×2 ablation matrix
(`scripts/little_loops/dev/measure_cache_routing_interaction.py`) verifying
whether the cache-marking oracle (FEAT-2673) and the in-process model router
(Tier 4, `[TBD-18]`, not yet built) interact — e.g. router-driven model
switches invalidating a stable-prefix cache hit, or the two levers'
cost savings failing to compose additively — on representative `ll-loop`
traces.

## Current Behavior

No ablation harness exists. FEAT-2673 ships the cache-marking oracle
standalone, gated behind `orchestration.request_path == "sdk"`, with no
measurement of its interaction with Tier 4 routing.

## Expected Behavior

A greenfield research script exercises all four combinations (cache on/off ×
router on/off) against representative `ll-loop` traces and reports whether
the two levers compose additively or interact (e.g. router-induced model
switches breaking cache-key stability).

## Motivation

EPIC-2456 Open Question #7 flags this as a required decision "before
[F1] ships" per FEAT-2673's acceptance criteria. Filed as its own tracked
issue (rather than blocking FEAT-2673's merge) because Tier 4 routing
(`[TBD-16]`–`[TBD-18]`) doesn't exist yet — there is no router to ablate
against. `status: deferred` reflects that this is blocked on Tier 4 landing,
not abandoned.

## Impact

- **Priority**: P3 — cross-tier verification work, not user-facing; useful
  once Tier 4 exists, moot before then.
- **Effort**: Unknown — depends on Tier 4's router shape once built.
- **Risk**: Low — pure measurement/research output, no production code path.

## Files to Modify

- New `scripts/little_loops/dev/measure_cache_routing_interaction.py`

## Acceptance Criteria

- [ ] Ablation script exercises cache on/off × router on/off (4 cells) against
      representative `ll-loop` traces.
- [ ] Report documents whether cache and router savings compose additively or
      interact (e.g. router model-switches breaking FEAT-2671 fragment-key
      stability).
- [ ] Findings feed back into EPIC-2456 OQ #7 as a resolved decision.

## Session Log
- `/ll:manage-issue` - 2026-07-19T00:10:20Z - filed while implementing FEAT-2673 (its AC required filing/linking this issue before F1 ships; deferred pending Tier 4 routing work which doesn't exist yet)

## Status

**Deferred** | Created: 2026-07-19 | Priority: P3
