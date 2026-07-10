---
id: ENH-2577
title: general-task — guard the continue_work convergence spin after abandoned steps
type: ENH
priority: P3
status: open
discovered_date: "2026-07-10"
discovered_by: audit-loop-run
labels: [loops, fsm, general-task, stall-detection, audit]
relates_to:
- FEAT-1637
- BUG-1674
- ENH-2575
---

# ENH-2577: general-task — guard the continue_work convergence spin after abandoned steps

## Summary

Audit `general-task-audit-2026-07-09T232714.md` (03:41–03:55 UTC window): the
loop cycled `continue_work → select_step → check_done → count_done(on_no) →
continue_work` ~6 consecutive times with **zero `do_work`** in between.
`select_step` returned `NO_UNCHECKED_STEPS` in ~20ms each pass (plan steps
19–23 had all hit `max_step_attempts: 3` and were abandoned), yet each
`continue_work` burned 50–210s of LLM time re-deliberating without producing a
new actionable `- [ ]` step, until it finally self-assessed `WORK_COMPLETE`
with 12 hard criteria still open and handed off to `final_verify`.

## Why the existing stall detector doesn't catch this

FEAT-1637's `StallDetector` (and the BUG-1674 fix) treat auxiliary file
mutations between visits as progress. In this spin, `check_done` rewrites the
`## Sample Verification` section of `dod.md` every cycle, so each pass mutates
a file and the detector sees "slow but real progress." The spin is invisible
at the executor layer; the guard has to be loop-local (or the detector must
learn to exclude the loop's own bookkeeping artifacts, mirroring the
`repeated_failure.exclude_paths` mechanism this loop already configures for
`plan.md`/`dod.md`).

## Expected Behavior (design open — two candidate shapes)

1. **Loop-local stall counter**: `select_step` already emits
   `NO_UNCHECKED_STEPS`; persist a consecutive-occurrence counter in the run
   dir (cleared whenever a step is selected or continue_work appends a new
   step). When the counter reaches N (e.g. 3) with unchecked hard criteria
   remaining, route to the ENH-2575 partial-credit chain instead of another
   `continue_work` deliberation.
2. **Detector enhancement**: extend `StallDetector` progress accounting to
   honor the loop's `circuit.repeated_failure.exclude_paths` (mutations to
   excluded bookkeeping files don't count as progress), letting the generic
   window fire on this cycle.

Either way, N no-progress cycles must cost N × ~20ms shell + at most one
`continue_work` deliberation — not ~15 minutes of repeated LLM re-planning.

## Acceptance Criteria

- [ ] A `continue_work → select_step(NO_UNCHECKED_STEPS) → … → continue_work`
      cycle that appends no new plan step terminates in ≤N cycles by routing
      to the partial-credit chain (ENH-2575), not by continue_work
      self-assessing WORK_COMPLETE.
- [ ] Counter/detector resets on genuine progress (a step selected, a new
      remediation step appended, or a criterion flipped).
- [ ] Abandoned-step interaction covered: steps at `max_step_attempts` do not
      re-arm the spin.
- [ ] Shell-execution tests for the counter logic in
      `scripts/tests/test_general_task_loop.py`.

## Notes

From audit recommendation 3 (`general-task-audit-2026-07-09T232714.md`).
Distinct from the abandoned-step cap itself (already implemented in
`select_step`) — this guards what happens *after* every remaining step has
been abandoned.
