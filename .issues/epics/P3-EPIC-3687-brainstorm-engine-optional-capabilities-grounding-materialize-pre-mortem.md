---
id: EPIC-3687
type: EPIC
title: 'Brainstorm engine optional capabilities: grounding, materialize, pre-mortem'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T05:35:56Z'
labels:
- loops
- brainstorm
relates_to:
- EPIC-3581
---

# EPIC-3687: Brainstorm engine optional capabilities: grounding, materialize, pre-mortem

## Summary

Optional, profile-gated capabilities for the EPIC-3581 brainstorm engine, split out of EPIC-3581 on 2026-09-30 (fifth pre-implementation review, `/ll:advise` with Opus) so the core engine epic can close without waiting on P3/P4 optional work: **codebase grounding** (FEAT-3584), **visual materialize** (FEAT-3585) and the **annotate-only pre-mortem finisher** (FEAT-3586).

Each child lands with its own enablement in one change: widen `BUILT_CAPABILITIES` in `little_loops.brainstorm_engine`, flip its preset knob in the target profile(s) (FEAT-3583 § Shipped vs target), extend the profile-token wiring test, bump `max_steps`/`timeout` by its own cost, and record its own reference run. The `ground=web` follow-up (deferred out of v1) also belongs here.

## Impact

- **Priority**: P3 - optional capabilities; the core engine works without them
- **Effort**: Large - three gated capabilities (ground, materialize, pre-mortem) plus the deferred `ground=web`
- **Risk**: Low - each is gated behind a profile knob and lands with its own enablement
- **Breaking Change**: No

## Children
- **FEAT-3584** — Brainstorm ground state with codebase and web evidence probes (open; v1 = codebase only)
- **FEAT-3585** — Brainstorm materialize state: rendered mockups judged visually (open)
- **FEAT-3586** — Brainstorm optional pre-mortem finisher (open)

## Ordering

All children are blocked by EPIC-3581's core (FEAT-3667 → FEAT-3582 → FEAT-3583). The children are independent of each other.

## Success Metrics

- Each child's reference run (one per capability) is recorded in its own Session Log or `postmortems/`.
- No shipped profile enables a capability outside `BUILT_CAPABILITIES`.

## Status

**Open** | Created: 2026-09-30 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Owns cross-capability integration for the optional children: cross-child fixtures (ground+materialize below the finalist floor, reserve promotion then materialize drops) and all-features worst-case `max_steps`/`timeout` verification, deferred from FEAT-3596 (non-gating there). Each child records its own reference run and bumps its own budget cost.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:29 - `b32e58bb-e3b8-4048-9c71-1c2f63665ce9.jsonl`
