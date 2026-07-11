---
id: BUG-2608
title: general-task summarize_success reports implemented:0 on every successful run
type: BUG
status: open
priority: P3
captured_at: "2026-07-11T00:00:00Z"
discovered_date: "2026-07-11"
discovered_by: audit-loop-run
relates_to:
- BUG-2170
- ENH-2119
- ENH-2365
- ENH-2575
labels:
- general-task
- loops
- reporting-correctness
---

# BUG-2608: general-task summarize_success reports implemented:0 on every successful run

## Summary

`scripts/little_loops/loops/general-task.yaml`'s `summarize_success` state
(lines 542-564) populates `summary.json`'s `implemented` field from
`done_counts.total`. But `total` is the count of *remaining unchecked* criteria,
and the `count_done` gate (lines 443-448) only routes to the success path
(`final_verify` → … → `summarize_success`) when `.total == 0`. So `implemented`
is **structurally pinned to 0 on every successful run** — a value
indistinguishable from total failure.

This was surfaced by an `/ll:audit-loop-run` audit of a real 144-iteration
`general-task` run (48/48 DoD criteria checked, `npm test` 1390/1390) whose
`summary.json` nonetheless read `{"verdict":"success","implemented":0,...}`.

## Current Behavior

Every successful `general-task` run writes `"implemented": 0`. The audit
avoided misclassifying the run as a failure only by tracing FSM semantics.

## Expected Behavior

`implemented` should report the count of **checked** Verification Criteria
(48 for the audited run), matching the section-scoped accounting used by
`count_done` (lines 406-411) and `write_partial_summary`'s `checked` field
(ENH-2575, lines 691-698).

## Motivation / Downstream Consequence

`/ll:audit-loop-run` Step 6a keys `honest-failure` classification on
`implemented == 0`. Any aggregator reading `implemented > 0` as a success
signal would misclassify *every* successful `general-task` run as a failure.
This is the same bug class already recorded for other loops — BUG-2170
(rn-implement implemented-count undercounts) and ENH-2119 (rn-remediate: move
counter increment to emit-implemented) — now confirmed a third time in
general-task.

## Proposed Solution

In `summarize_success`, source `implemented` from `dod.md` as
`CHECKED = TOTAL_DOD - UNCHECKED_DOD` (section-scoped to `## Verification
Criteria`, mirroring `count_done` / `write_partial_summary`), instead of from
`done_counts.total`. `failed_finals` continues to come from `final_counts`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — `summarize_success` action.

### Similar Patterns
- `general-task.yaml` `write_partial_summary` (lines 664-703) — the
  `CHECKED = TOTAL - UNCHECKED` awk accounting to mirror.
- `general-task.yaml` `count_done` (lines 388-411) — authoritative
  section-scoped criterion counting.

### Tests
- `scripts/tests/test_general_task_loop.py::TestENH2365SummarizeSuccess` — add
  a shell-execution test (mirroring `TestENH2575PartialCredit`) that runs the
  `summarize_success` action against a dod.md with N checked criteria and
  asserts `summary.json.implemented == N` (would fail on the current
  `done_counts.total` code, which yields 0).

## Impact

- **Priority**: P3 - Reporting correctness; does not change loop success/failure
  behavior, but corrupts downstream success/failure aggregation.
- **Effort**: Small - single shell action edit + one behavioral test.
- **Risk**: Low - reuses existing section-scoped awk accounting.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-07-11 | Priority: P3

## Session Log
- `/ll:audit-loop-run` (consumer project) - 2026-07-11 - surfaced via general-task-audit-2026-07-11T153651.md
