---
id: ENH-3381
type: ENH
title: Record ENH-2990 live skip rate
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-03'
captured_at: '2026-09-03T00:36:34Z'
parent: EPIC-3023
labels:
- issues
- measurement
- cost
---

# ENH-3381: Record ENH-2990 live skip rate

## Summary

ENH-2990 shipped live instrumentation for `ll-issues research-triage`
(`research_triage_events`, `history.db` schema v46) but the sample threshold
for a defensible live figure had not yet accumulated when it closed. This
issue holds only ENH-2990's Implementation Step 6: fill in the stub
`## Threshold Validation (ENH-2990 — live)` entry in ENH-2971 once enough
data has accumulated.

## Current Behavior

`research_triage_events` accumulates rows on every `ll-issues research-triage`
invocation (autodev.yaml's critical path via `/ll:refine-issue` Step 3.0), but
no one has read them back yet. ENH-2971's `## Threshold Validation (ENH-2990
— live)` section is a stub pending the figure.

## Expected Behavior

Once at least **1,500 re-refine axis rows** (`refined_at IS NOT NULL`, ≈500
invocations) have accumulated — ENH-2990 estimated ~3 weeks of `autodev.yaml`
traffic at the 22–37 invocations/day steady-state rate — run
`history_reader.research_triage_stats()` (or the equivalent SQL recorded in
ENH-2971's stub section) and fill in the entry with:

- The production skip rate and coverage-only counterfactual, per axis and in
  aggregate.
- The `program_design_unmet` override count (excluded from the rates).
- A comparison against ENH-2971's 33.7%/8.6% corpus figures.
- If `stale` dominates the gap, open a follow-up issue to narrow the
  Staleness Check's granularity (ENH-2990's own noted next step).

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

1. Check row volume: `sqlite3 .ll/history.db "SELECT COUNT(*) FROM
   research_triage_events WHERE refined_at IS NOT NULL"`.
2. If ≥1,500, call `little_loops.history_reader.research_triage_stats()` (or
   run the SQL in ENH-2971's stub section directly) and transcribe the
   result into ENH-2971's `## Threshold Validation (ENH-2990 — live)`
   section, replacing the "Pending" placeholder.
3. If below threshold, defer and re-check later — do not implement partial
   figures.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Effort**: Trivial — a read-and-transcribe once the data exists.
- **Expected benefit**: Closes the 4x uncertainty ENH-2990 was written to
  resolve, with a real measurement instead of a corpus proxy.
- **Risk**: None — read-only.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: reading the accumulated telemetry and recording the figure.
- **Out of scope**: any further instrumentation change, and acting on the
  result (a follow-up issue is what should absorb that, not this one).

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.issues/enhancements/P3-ENH-2990-measure-live-re-refine-skip-rate-for-research-triage.md` | The instrumentation this issue reads back from |
| `.issues/enhancements/P3-ENH-2971-refine-issue-spawns-three-subagents-unconditionally.md` § Threshold Validation | Where the figure gets recorded |

## Status

**Open** | Created: 2026-09-03 | Priority: P3
