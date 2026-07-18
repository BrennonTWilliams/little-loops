---
id: FEAT-2674
title: "F10 — Speculative cache warming hook (+ max_tokens=0 alt)"
type: FEAT
priority: P2
status: open
captured_at: '2026-07-18T15:15:21Z'
discovered_date: 2026-07-18
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- FEAT-2673
depends_on:
- FEAT-2673
decision_needed: false
labels:
- token-cost
- caching
- tier-2
- hooks
---

# FEAT-2674: F10 — Speculative cache warming hook

## Summary

New `scripts/little_loops/skills/speculative.py` (~80 LOC): a `SkillStart`
hook that fires an async cache-warming request when `cache.warmable == true`
and the assembled prompt exceeds 50K tokens, so the first real invocation
of a long-running skill lands on a warm cache. Include the SDK-level
`max_tokens=0` primitive as the cheaper background-warm alternative for
deterministic cases. This is EPIC-2456 § Children [TBD-11] — Goal #6.
**Depends on FEAT-2673 (F1)** — warming is meaningless without the
`cache_control` primitive in place.

## Motivation

Long-running skills with >50K-token prompts currently pay full input price
on first invocation (~0% cache hit). Warming shifts that first hit to the
0.1x read rate for a 1.25x one-time write fired off the critical path.

## Implementation Steps

1. New `scripts/little_loops/skills/speculative.py` (~80 LOC): warming
   request built via FEAT-2673's `build_anthropic_request()`; async
   fire-and-forget with the `max_tokens=0` variant where applicable.
2. `hooks/hooks.json`: add `SkillStart` hook entry, gated on
   `cache.warmable == true` and the 50K-token threshold (configurable
   under the `cache.*` namespace).
3. Verify hits via F5 telemetry (`cache_read_input_tokens`).

## Files to Modify

- new `scripts/little_loops/skills/speculative.py` (~80 LOC)
- `hooks/hooks.json` (SkillStart entry)
- `config-schema.json`, `.ll/ll-config.json` (`cache.warmable`, threshold)
- new `scripts/tests/test_speculative_warming.py`

## Acceptance Criteria

- [ ] Cache hit rate on warmed long-running skills >80% (vs ~0% without
      warming) on prompts >50K tokens (EPIC-2456 Success Metrics, F10 row).
- [ ] Warming request never blocks the skill's real invocation (async;
      failure is logged and swallowed).
- [ ] Default off unless `cache.warmable == true`.

## Session Log
- `/ll:capture-issue` - 2026-07-18T15:15:21Z - captured from EPIC-2456 § Children [TBD-11] (source: thoughts/plans/2026-07-02-token-cost-reduction-architecture.md, Tier 2)

## Status

**Open** | Created: 2026-07-18 | Priority: P2
