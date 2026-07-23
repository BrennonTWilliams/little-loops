---
id: ENH-2743
title: Add closed_via_recovery counter to sprint-refine-and-implement summary.json for parked-then-closed issues
type: ENH
priority: P3
status: open
captured_at: '2026-07-23T00:25:52Z'
discovered_date: 2026-07-23
discovered_by: audit
size: Small
labels:
- loops
- visibility
- captured
---

# ENH-2743: Add closed_via_recovery counter to sprint-refine-and-implement summary.json for parked-then-closed issues

## Summary

`sprint-refine-and-implement`'s `finalize` state currently reports `closed`
and `skipped` counts in `summary.json`, but has no way to tell whether a
skipped/parked issue was later closed via an alternate path within the same
run (e.g. `ll-auto` re-implementing after the sprint queue released the
lock).

In an audited run (`.loops/.history/2026-07-18T045753-sprint-refine-and-implement/`),
2 issues were skipped by the autodev sub-loop (`skipped_breakdown:
low_readiness=1, refine_failed=1`) but both issues' working-tree status ended
up `status: done` by the time the run finished. The current `closed=4` count
misses them, and `parked_rate=0.1429` overstates the actual
permanently-parked ratio. A reviewer reading `summary.json` alone sees a 4/2
split that looks like the run "failed to handle" 2 issues, when actually both
self-resolved.

## Current Behavior

`summary.json` reports `closed`, `skipped`, and `skipped_breakdown` with no
signal distinguishing permanently-parked issues from ones that were
subsequently closed by a different path during the same run.

## Expected Behavior

`summary.json` includes a `closed_via_recovery` field counting skipped
issues whose working-tree status reached `done` before the run's `finalize`
state ran.

## Proposed Solution

In the `finalize` state's action, compute `CLOSED_VIA_RECOVERY` via `comm -12`
between the run's skipped-ids file and a fresh done-ids snapshot, mirroring
the BUG-2403 / ENH-1418 done-now snapshot pattern:

```bash
CLOSED_VIA_RECOVERY=$(comm -12 \
  "$RUN_DIR/$P-skipped-ids.txt" \
  "$RUN_DIR/$P-done-new.txt" \
  | wc -l)
```

Add `"closed_via_recovery": <N>` to the `summary.json` output alongside the
existing `closed`/`skipped`/`skipped_breakdown` fields.

## Implementation Steps

1. Confirm the `finalize` state already writes a skipped-ids file (per the
   `skipped_breakdown` mechanism, ENH-2404) and identify/add an equivalent
   done-ids snapshot at finalize time.
2. Add the `comm -12` computation for `CLOSED_VIA_RECOVERY`.
3. Add `closed_via_recovery` to the `summary.json` JSON payload.
4. Add a test/fixture run asserting a skipped-then-done issue is counted.

## Sources

- `audit-loop-run-sprint-refine-and-implement-2026-07-18T045753.md` —
  Proposal #3 (visibility)

## Session Log
- `/ll:capture-issue` - 2026-07-23T00:25:52Z - `01b32c17-cae1-4173-b77e-b51fe2c99146.jsonl`
