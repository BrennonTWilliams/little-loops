---
id: BUG-2289
title: rn-decompose records decomposed parent in both skipped.txt and decomposed_count — summary breakdown double-counts
priority: P3
type: BUG
status: open
captured_at: '2026-06-25T13:53:17Z'
discovered_date: '2026-06-25'
discovered_by: audit-loop-run
source_loop: rn-implement
source_state: report
affects: scripts/little_loops/loops/rn-decompose.yaml
labels:
- rn-implement
- rn-decompose
- telemetry
---

# BUG-2289: rn-decompose records decomposed parent in both skipped.txt and decomposed_count — summary breakdown double-counts

## Summary

In the `rn-implement` run `2026-06-25T065113`, `summary.json` reported
`total_processed: 8`, but the outcome buckets sum to **9**:
`implemented: 6 + decomposed: 1 + skipped: 1 + blocked: 1`. The single
decomposed parent (ENH-2272) was tallied in **two** mutually-exclusive
buckets — `decomposed` and `skipped`.

Root cause: when `rn-decompose` decomposes a parent, its `enqueue_children`
state appends the parent ID to `skipped.txt` (`rn-decompose.yaml:209`,
comment "Mark parent as skipped (decomposed)") **and** increments
`decomposed_count.txt` (`rn-decompose.yaml:213`). The `report` state in
`rn-implement` then reads `skipped` from `wc -l skipped.txt` and `decomposed`
from `decomposed_count.txt` as if they were disjoint outcomes
(`rn-implement.yaml:916`), so the decomposed parent is counted once as
`decomposed` and again as `skipped`.

The `skip_issue` state (`rn-implement.yaml:885`, the only *intended* writer to
`skipped.txt`) never executed in this run — verified: 0 routes to `skip_issue`
across all 795 events. The `skipped.txt` entry came entirely from the
`rn-decompose` write.

## Current Behavior

- Run `2026-06-25T065113-rn-implement`, 8 issues dequeued
- `decomposed_count.txt`: `1` (ENH-2272)
- `skipped.txt`: `ENH-2272` (1 entry)
- `subloop_outcome_ENH-2272.txt`: `DECOMPOSED`
- `summary.json`: `total_processed: 8`, buckets sum to 9
- The breakdown over-reports by exactly the number of decomposed parents.

## Expected Behavior

A decomposed parent is counted in exactly one outcome bucket (`decomposed`).
The sum of `implemented + decomposed + skipped + deferred + blocked +
depth_capped + failed` (plus diagnostic tallies) should never exceed
`total_processed`.

## Steps to Reproduce

1. Queue an issue large enough to trigger decomposition (e.g. an ENH that
   `rn-decompose` splits into children).
2. Run `ll-loop run rn-implement "<id>"`.
3. After completion, inspect the run dir:
   `cat .loops/runs/rn-implement-<ts>/skipped.txt` and
   `cat .loops/runs/rn-implement-<ts>/decomposed_count.txt`.
4. Observe the decomposed parent appears in **both** `skipped.txt` and the
   `decomposed_count` tally.
5. In `summary.json`, observe the outcome buckets sum to more than
   `total_processed`.

## Root Cause

- **File**: `scripts/little_loops/loops/rn-decompose.yaml`
- **Anchor**: `enqueue_children` state, line 209
- **Cause**: `echo "$ID" >> "$RUN_DIR/skipped.txt"` writes the decomposed
  parent into the report-tally file that `rn-implement`'s `report` state
  treats as a disjoint outcome bucket. The parent is already accounted for via
  `decomposed_count.txt` (incremented four lines later) and via
  `finalize_parent` writing the `DECOMPOSED` outcome token. The `skipped.txt`
  write is redundant for tallying and actively wrong for the breakdown math.
  The original intent ("mark parent as skipped") appears to have been a
  re-dequeue guard, but queue removal + `visited.txt` already prevent
  re-processing — `skipped.txt` is purely a report tally.

## Acceptance Criteria

1. A decomposed parent is no longer written to `skipped.txt` (or, if a
   "decomposed parents" record is wanted, it is kept in a separate file that
   the `report` state does not fold into the `skipped` bucket).
2. After a run containing at least one decomposition, the `summary.json`
   outcome buckets sum to ≤ `total_processed`.
3. A regression test asserts that `enqueue_children` in `rn-decompose.yaml`
   does not append the parent ID to `skipped.txt`, OR that `report`'s tallied
   buckets do not double-count a decomposed parent.

## Proposed Solution

**Option A (preferred)**: Remove the `echo "$ID" >> "$RUN_DIR/skipped.txt"`
line at `rn-decompose.yaml:209`. The parent is already tracked by
`decomposed_count.txt` and the `DECOMPOSED` outcome token; queue removal and
`visited.txt` handle re-dequeue prevention, so the skip-tally write is pure
double-counting.

**Option B**: Keep the parent record but redirect it to a dedicated file
(e.g. `decomposed_parents.txt`) that the `report` state does not sum into the
`skipped` bucket.

## Impact

- **Priority**: P3 — Telemetry inaccuracy in session reports; does not block
  issue implementation but misreports run outcomes (breakdown exceeds total).
- **Effort**: Small — likely a one-line removal in `rn-decompose.yaml` plus a
  test.
- **Risk**: Low — confined to a report-tally write in loop YAML; no Python or
  FSM-engine changes.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-25 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-06-25T13:53:17Z - `fe374318-c8a2-454a-82dd-24bd83653458.jsonl`
