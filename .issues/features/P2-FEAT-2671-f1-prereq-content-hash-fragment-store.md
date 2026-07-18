---
id: FEAT-2671
title: "F1-prereq (a) — Content-hash fragment store"
type: FEAT
priority: P2
status: open
captured_at: '2026-07-18T15:15:21Z'
discovered_date: 2026-07-18
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- FEAT-2672
- FEAT-2673
blocks:
- FEAT-2673
decision_needed: false
labels:
- token-cost
- caching
- tier-2
---

# FEAT-2671: F1-prereq (a) — Content-hash fragment store

## Summary

New `scripts/little_loops/prompts/fragment_store.py` (~40 LOC): compute a
SHA-256 content hash over the stable prompt fragments —
`(skill_body, system_prompt, tool_definitions)` — and skip re-serialization
when the key is stable across invocations. Adapted from
`BerriAI/litellm/litellm/caching/caching.py`. This is EPIC-2456 § Children
[TBD-8], the first of two cache-stability prerequisites that must land
before F1 (`cache_control: ephemeral`, FEAT-2673) is enabled: a cache
breakpoint is only worth paying the 1.25x write premium for if the block
under it is byte-stable, and the fragment store is what proves stability.

## Motivation

F1's savings model (0.1x reads vs 1.25x writes, ~12.5x differential per the
cookbook anchors in EPIC-2456) collapses if the marked blocks churn between
calls — every churn is a fresh 1.25x write with no read to amortize it. A
content-hash store gives the cache-marking oracle (FEAT-2673) a cheap,
deterministic stability signal, and independently saves re-serialization
work on the prompt-assembly path.

## Implementation Steps

1. New module `scripts/little_loops/prompts/fragment_store.py` (~40 LOC):
   `fragment_key(skill_body, system_prompt, tool_definitions) -> str`
   (SHA-256 hex) plus a small keyed store with `get`/`put` and a
   hit-counter for measurement.
2. Hashing lives behind a small helper so F8's parent-prefix hoisting
   ([TBD-14]) can later share it via `lib/hashing.py` (EPIC-2456 Open
   Question #8 — share-or-duplicate decision is deferred to that capture;
   do not create `lib/hashing.py` speculatively here).
3. Wire into the prompt-assembly path (`fsm/runners.py`) read-only first:
   record hit/miss, change no behavior.

## Files to Modify

- new `scripts/little_loops/prompts/fragment_store.py` (~40 LOC)
- `scripts/little_loops/fsm/runners.py` (record-only wiring)
- new `scripts/tests/test_fragment_store.py`

## Acceptance Criteria

- [ ] SHA-256 key stable across repeated serialization of identical inputs;
      changes when any of the three fragments changes (regression test).
- [ ] Hit rate >= 80% across the locked Tier 0 trace set (ENH-2518 traces),
      per EPIC-2456 Success Metrics (F1 row).
- [ ] No behavior change to assembled prompts (record-only in this issue).

## Session Log
- `/ll:capture-issue` - 2026-07-18T15:15:21Z - captured from EPIC-2456 § Children [TBD-8] (source: thoughts/plans/2026-07-02-token-cost-reduction-architecture.md, Tier 2)

## Status

**Open** | Created: 2026-07-18 | Priority: P2
