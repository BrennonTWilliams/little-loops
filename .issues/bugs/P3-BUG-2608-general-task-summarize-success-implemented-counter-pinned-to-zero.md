---
id: BUG-2608
title: general-task summarize_success reports implemented:0 on every successful run
type: BUG
status: done
priority: P3
captured_at: '2026-07-11T00:00:00Z'
discovered_date: '2026-07-11'
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
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

**Done** | Created: 2026-07-11 | Priority: P3

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Already fixed by commit `fa364119` ("fix(loops): report checked-criteria
  count in general-task summarize_success (BUG-2608)"), which landed in the
  same commit that added this issue file. `summarize_success` in
  `scripts/little_loops/loops/general-task.yaml:542-584` now computes
  `IMPLEMENTED=$(($TOTAL_DOD - $UNCHECKED_DOD))` (section-scoped to
  `## Verification Criteria`), replacing the prior `done_counts.total` source.
- Regression coverage added in the same commit:
  `scripts/tests/test_general_task_loop.py:1529` `TestENH2365SummarizeSuccess`,
  specifically `test_implemented_counts_checked_criteria_not_leftover` and
  `test_implemented_is_section_scoped` (lines ~1555-1635). Verified passing:
  `python -m pytest scripts/tests/test_general_task_loop.py::TestENH2365SummarizeSuccess -v`
  — 10/10 passed.
- No further implementation work remains. Marking `status: done`.

## Session Log
- `/ll:refine-issue` - 2026-07-11T20:37:58 - `37df9e19-5b6b-496d-b642-9c4e836e3f06.jsonl`
- `/ll:audit-loop-run` (consumer project) - 2026-07-11 - surfaced via general-task-audit-2026-07-11T153651.md
- `/ll:confidence-check` - 2026-07-11T20:41:00Z - `d8f60841-044f-46c6-ba32-0bfa3724b66c.jsonl`
