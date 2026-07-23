---
id: ENH-2746
type: ENH
title: F3 compaction shrink ratio measured outside 50-70% gate band
priority: P3
status: open
captured_at: '2026-07-23T01:37:52Z'
discovered_date: '2026-07-23'
discovered_by: capture-issue
parent: EPIC-2456
labels:
- token-cost
- observability
- compaction
relates_to:
- EPIC-2456
- ENH-2719
- FEAT-2598
---

# ENH-2746: F3 compaction shrink ratio measured outside 50-70% gate band

## Summary

ENH-2719's realized-savings verification pass measured
`evict_sink_and_window()` (FEAT-2598's always-on structural eviction pass,
`sink_n=4`/`window_n=20` defaults) against 3 real on-disk session
transcripts. Shrink ratios were 89.6%, 73.8%, and 61.3% (mean 74.9%) —
2 of 3 exceed EPIC-2456's F3 gate band of 50-70%.

## Current Behavior

- `evict_sink_and_window` alone was measured (structural eviction only); the
  soft-threshold-gated `summarize_6_section` LLM pass was not exercised
  since it requires a live model call and was out of scope for a read-only
  measurement pass.
- The measured range (61.3-89.6%) oversh­oots the 50-70% gate on the two
  longer sessions, suggesting either the gate band was set against the
  combined eviction+summarization behavior (not eviction alone), or the
  default `sink_n`/`window_n` produce more aggressive shrinkage than
  intended on long sessions.

## Expected Behavior

Either:
1. Measure the combined structural-eviction + 6-section-summarization
   pipeline end-to-end (requires a live model call for the summarization
   step) and compare that ratio to the 50-70% gate, or
2. Reconcile the gate band itself if it was only ever meant to describe
   the always-on structural pass, and the observed 61-90% range is
   actually expected/acceptable.

## Proposed Solution

1. Determine (from `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md`
   or FEAT-2598's own issue) whether the 50-70% gate was scoped to
   structural eviction alone or the combined pipeline.
2. If combined: run a small opt-in measurement invoking
   `summarize_6_section` on the same 3 sessions and recompute the ratio.
3. If structural-only: update EPIC-2456's Success Metrics F3 line to
   reflect the actual measured range, or tune `sink_n`/`window_n` defaults
   if 61-90% is considered too aggressive.
4. Update `docs/observability/realized-savings-verification.md` with the
   resolved measurement.

## Impact

- **Priority**: P3 — a measurement/gate-definition reconciliation, not a
  functional regression (more aggressive shrinkage than the gate expected
  is not obviously harmful).
- **Effort**: Small — either a doc/gate update or one measurement run.
- **Risk**: Low.

## Labels

`token-cost`, `observability`, `compaction`, `captured`

## Status

**Open** | Created: 2026-07-23 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-07-23T01:37:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1b068faa-9da8-4bec-af30-feafda6b3309.jsonl`
