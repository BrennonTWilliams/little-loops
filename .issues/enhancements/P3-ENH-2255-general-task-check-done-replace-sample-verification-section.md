---
id: ENH-2255
type: ENH
priority: P3
status: done
captured_at: '2026-06-22T14:50:06Z'
completed_at: '2026-06-22T15:05:03Z'
discovered_date: 2026-06-22
discovered_by: capture-issue
labels:
- enhancement
- fsm
- general-task
- reliability
confidence_score: 100
outcome_confidence: 98
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 23
score_change_surface: 25
---

# ENH-2255: general-task check_done should replace (not append) the Sample Verification section

## Motivation

The `general-task` loop's `check_done` state appends a brand-new `## Sample
Verification` section to `dod.md` on every iteration. Over a long run these
accumulate without bound — the audited run `2026-06-22T002024-general-task`
ended with **26** stacked Sample Verification sections in a single DoD file.

Two concrete costs:
1. **Context bloat.** `check_done` and `count_done` re-read the entire DoD file
   each iteration, so the file the LLM ingests grows monotonically with iteration
   count — wasted tokens that scale with run length.
2. **Historical-FAILED accumulation.** Because old sections persist, stale
   `FAILED` lines from earlier iterations pile up. This is exactly what enabled
   the completion-detection poison-pill bug: `count_done` summed `FAILED_SAMPLES`
   across the whole accumulated tail, permanently blocking the gate at a historical
   value of 5.

The gate poison-pill itself was already fixed by dropping `FAILED_SAMPLES` from
`count_done`'s `TOTAL` (Proposal 1) plus a `WORK_COMPLETE` escape hatch in
`continue_work` (Proposal 3). This ENH is the cleaner **upstream** fix: bound the
accumulation at the source so the failure mode cannot recur in any form and the DoD
file stays small.

## Summary

Change `check_done`'s action prompt so each iteration **replaces** the previous
`## Sample Verification` section in `${context.run_dir}/dod.md` rather than
appending a new one. Only the most recent spot-check survives, which is all any
downstream reader needs — the section is a transient per-iteration spot-check, not
an audit trail.

## Current Behavior

`check_done` (`scripts/little_loops/loops/general-task.yaml`, action prompt ~lines
318–333) instructs the agent to *"Append a `## Sample Verification` section to the
DoD file."* Each iteration appends, so sections stack and the file grows unbounded.

## Expected Behavior

Each `check_done` pass rewrites the single trailing `## Sample Verification`
section: if one already exists, replace its contents in place (or delete + rewrite);
if none exists, create it. The DoD file contains at most one Sample Verification
section at any time, reflecting only the latest spot-check.

## Implementation Steps

1. In `scripts/little_loops/loops/general-task.yaml`, edit the `check_done` action
   prompt (Step 3 — Sample re-verification, ~lines 318–333) to instruct the agent
   to first remove any existing `## Sample Verification` section before writing the
   new one — i.e. "replace the prior section" rather than "append a section."
   Keep the exact `## Sample Verification` header and the `- [x]`/`- [ ] ... FAILED`
   line format unchanged.
2. Confirm `count_done`'s `FAILED_SAMPLES` awk and `count_final` continue to parse
   the (now single) section correctly. With only one section the existing awk is
   robust regardless of the in-section reset behavior; no awk change is strictly
   required, but consider tightening it for clarity.
3. Verify the existing assertions that `check_done.action` contains the literal
   `"## Sample Verification"` still hold — they only check the header is referenced,
   which "replace the `## Sample Verification` section" satisfies
   (`scripts/tests/test_general_task_loop.py` ~lines 111–114 and ~267–268).
4. Add a unit test asserting `check_done.action` instructs replacement (e.g. the
   prompt contains "replace" near "Sample Verification" and does not say "append … a
   new" Sample Verification section).

## Scope Boundaries

- **In scope**: `check_done` prompt wording in `general-task.yaml`; a unit test for
  the replace semantics; optional clarity tightening of the `FAILED_SAMPLES` awk.
- **Out of scope**: The `count_done` gate change and `continue_work` escape hatch
  (already landed); other loop YAMLs; persisting Sample Verification history
  elsewhere (explicitly not wanted — the section is transient).

## Acceptance Criteria

- [ ] `check_done.action` instructs the agent to replace, not append, the
  `## Sample Verification` section
- [ ] A general-task run produces at most one `## Sample Verification` section in
  `dod.md` regardless of iteration count
- [ ] Existing tests asserting the `## Sample Verification` header is referenced
  still pass
- [ ] `ll-loop validate general-task` reports valid
- [ ] Tests pass: `python -m pytest scripts/tests/test_general_task_loop.py -q`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — `check_done` action prompt
- `scripts/tests/test_general_task_loop.py` — add replace-semantics assertion

### Similar Patterns
- The `final_verify` state appends a `## Final Verification` section once per run
  (terminal), so it does not have the accumulation problem and should stay append.

### Tests
- `scripts/tests/test_general_task_loop.py` — `TestChange2CheckDoneReconcileAndSampleVerify`

### Documentation
- N/A — internal loop behavior; no public API change

## Impact

- **Priority**: P3 — Reliability/efficiency cleanup; the acute failure (gate
  poison-pill) is already fixed, this removes the underlying accumulation that
  enabled it and trims per-iteration context cost.
- **Effort**: Small — one prompt edit + one test.
- **Risk**: Low — prompt-only behavior change; downstream parsers read the same
  header/format, just one section instead of many.
- **Breaking Change**: No

## Context

Follow-up to the completion-detection fix landed on 2026-06-22 (Proposals 1 + 3
from `general-task-loop-audit-2026-06-22.md`). Observed in loop run
`2026-06-22T002024-general-task`: 26 stacked `## Sample Verification` sections
accumulated over 200 iterations; historical `FAILED` lines in those sections
poisoned `count_done`'s `FAILED_SAMPLES` total and blocked self-detected
completion despite all 19 plan steps and 42 DoD criteria being satisfied.

## Status

**Open** | Created: 2026-06-22 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-22T15:02:39 - `3bb3dd2d-4a79-403f-8c6e-2490d2cee8c0.jsonl`
- `/ll:confidence-check` - 2026-06-22T00:00:00Z - `b1ccd26b-f585-48b3-aef5-e5849cb56700.jsonl`
- `/ll:format-issue` - 2026-06-22T14:56:57 - `fbdc25da-bfa8-461a-94b5-26bba2297470.jsonl`
- `/ll:capture-issue` - 2026-06-22T14:50:06Z - `bcaa0571-6edd-4292-b878-2b56b7b28560.jsonl`
