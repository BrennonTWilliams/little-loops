---
id: FEAT-2672
title: "F1-prereq (b) — Deferred tool loading"
type: FEAT
priority: P2
status: open
captured_at: '2026-07-18T15:15:21Z'
discovered_date: 2026-07-18
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- FEAT-2671
- FEAT-2673
blocks:
- FEAT-2673
decision_needed: false
labels:
- token-cost
- caching
- tier-2
---

# FEAT-2672: F1-prereq (b) — Deferred tool loading

## Summary

New `scripts/little_loops/tools/deferred.py` (~90 LOC) implementing the
`defer_loading=True` + `tool_reference` pattern: full tool definitions are
withheld from the initial request and loaded on demand, so the cacheable
static prefix stays byte-stable while the tool catalog churns. This is
EPIC-2456 § Children [TBD-9], the second F1 cache-stability prerequisite.
Vendor-measured anchor: "cutting context usage by 90%+ while enabling
applications that scale to thousands of tools."

## Motivation

Tool-definition churn is the main threat to the F1 cache breakpoint: any
change in the serialized tool block invalidates the cached prefix and turns
reads back into 1.25x writes. Deferring tool bodies out of the static
prefix preserves the breakpoint across catalog churn, and independently
shrinks the initial prompt regardless of whether F1 caching is enabled.

## Implementation Steps

1. New module `scripts/little_loops/tools/deferred.py` (~90 LOC):
   `tool_reference` stub emission (name + one-line description + defer
   marker) and on-demand resolution of full definitions.
2. Integration point is the prompt-assembly path (`fsm/runners.py`) ahead
   of `resolve_host()`; behavior gated behind a config flag (default off
   until FEAT-2673 lands and measurements exist).
3. Use FEAT-2671's fragment hashes to verify prefix byte-stability across
   catalog churn in tests.

## Files to Modify

- new `scripts/little_loops/tools/deferred.py` (~90 LOC)
- `scripts/little_loops/fsm/runners.py` (gated wiring)
- new `scripts/tests/test_deferred_tools.py`

## Acceptance Criteria

- [ ] Cache breakpoint (static-prefix hash per FEAT-2671) survives a
      5-skill catalog churn (regression test, per EPIC-2456 Success
      Metrics F1 row).
- [ ] Deferred stubs round-trip: a deferred tool invoked by the model
      resolves to its full definition without error.
- [ ] Default-off; no behavior change unless the config flag is set.

## Session Log
- `/ll:capture-issue` - 2026-07-18T15:15:21Z - captured from EPIC-2456 § Children [TBD-9] (source: thoughts/plans/2026-07-02-token-cost-reduction-architecture.md, Tier 2)

## Status

**Open** | Created: 2026-07-18 | Priority: P2
