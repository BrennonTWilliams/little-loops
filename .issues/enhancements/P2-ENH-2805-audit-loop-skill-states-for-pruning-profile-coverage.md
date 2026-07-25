---
id: ENH-2805
title: "Audit builtin-loop skill-invoking states for missing pruning_profile coverage"
type: ENH
priority: P2
status: open
captured_at: '2026-07-25T18:10:35Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
relates_to:
- ENH-2714
- EPIC-2456
labels:
- token-cost
- fsm
- loops
---

# ENH-2805: Audit builtin-loop skill-invoking states for missing pruning_profile coverage

## Summary

Sweep `scripts/little_loops/loops/*.yaml` for skill/command-invoking states
that run without a `pruning_profile` (state-level or loop default), rank them
by measured per-state token volume from `.ll/history.db` `usage_events`, and
apply profiles to the high-volume states.

## Motivation

A 2026-07-25 `usage_events` audit (last 7 days) established where fleet
tokens actually go:

- Loop **state-tagged** traffic (the only traffic `request_path: sdk` and the
  EPIC-2456 F1/F10 optimizations can touch) is **~1% of fleet tokens**
  (77 calls; 35K uncached input, 259K output, 4.0M cache-write).
- **Session-level** traffic (skill harness turns + interactive) carries the
  real spend: **20.5M output tokens** and **154M cache-creation tokens**
  (billed 1.25×) against 3.27B cache reads (~99% cached).

The SDK request-path work structurally cannot reduce this — no builtin skill
can move to the raw SDK (all 16 skills invoked from loops are tool-dependent:
shell, file writes, or subagents). The shipped levers that *do* target this
traffic are per-state `pruning_profile` (ENH-2714) and automation profiles,
but coverage was never audited after ENH-2714 landed.

Top three skill states by measured volume (7-day window):
`wire_issue` (9.9M cache-read / 1.03M cache-write / 89K out),
`refine_issue` (7.7M / 1.06M / 54K), `confidence_check` (10.9M / 1.05M / 52K)
— all in `autodev.yaml`.

## Implementation Steps

1. Script the sweep: for every non-`lib/` loop YAML, list skill/command
   states where neither the state nor the loop default sets
   `pruning_profile` (resolution mirrors `executor.py`'s
   `state.pruning_profile or fsm.pruning_profile`).
2. Join against `usage_events` per-state token sums (7- or 14-day window) to
   rank uncovered states by cache-write + output volume.
3. Apply appropriate profiles to the top-volume uncovered states
   (`autodev.yaml`'s `run_wire`/`refine_current`/`confidence_check` family
   first), respecting states that deliberately need full context.
4. Record the before/after comparison method so the win is measurable.

## Success Metric

Reduced `cache_creation_input_tokens` + `output_tokens` per state-visit for
the covered states, on a before/after `usage_events` comparison over
equivalent runs (same loop, same issue class).

## Scope Boundaries

- No changes to the pruning mechanism itself (ENH-2714 is shipped and
  unchanged) — this is a coverage audit + YAML application pass.
- No `request_path` / SDK-path work; that surface is complete and this issue
  exists precisely because it cannot address session-level spend.

## Session Log
- `/ll:capture-issue` - 2026-07-25T18:10:35Z

---

## Status
- Status: open
