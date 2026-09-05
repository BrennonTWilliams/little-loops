---
id: BUG-3390
type: BUG
title: 'autodev: dead outcome_gate_waived path, stale guard-2 capture provenance,
  no post-implement closure check, and unwired go-no-go escalation'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-04'
captured_at: '2026-09-04T21:11:07Z'
---

# BUG-3390: autodev: dead outcome_gate_waived path, stale guard-2 capture provenance, no post-implement closure check, and unwired go-no-go escalation

## Summary

Deep audit of `scripts/little_loops/loops/autodev.yaml` (79 states) and its sub-loops found five real defects and one unwired skill hook:

1. `outcome_gate_waived` is dead end-to-end: `regate_after_atomic_remediation` and `recheck_after_size_review` read it from `ll-issues show --json`, which never emits the key; `check_passed`/`recheck_after_decide`/`recheck_scores` use bare `ll-issues check-readiness`, which never reads it. `/ll:go-no-go`'s designed escalation valve (stamp the waiver on GO over an `oversized_atomic` deferral) therefore never lets an issue through, and the loop never invokes go-no-go anyway. `check-readiness` also lets config thresholds silently override explicit `--readiness/--outcome` args, so a per-run `--context readiness_threshold=NN` is honored by the inline gates but not the CLI gates.
2. Guard-2 stale-capture provenance gap: `check_size_review_ran_this_pass` proceeds to `check_guard2_verdict` (which regexes the run-scoped `captured.size_review_output`) whenever a negative marker written only by `check_broke_down` is absent. `rerun_confidence_after_wire.next` and `rerun_confidence_after_spike.next` reach it via `enqueue_or_skip` without running `run_size_review` or `check_broke_down`, so on a multi-issue run the second issue can be sent through `remediate_oversized_atomic` and deferred `oversized_atomic` on a previous issue's output.
3. No immediate post-implementation verification: `implement_current` exit 0 routes straight to `dequeue_next`; `ll-auto` exits 0 on "Issues processed: 0" (postmortem 2026-07-29). Only caught at `finalize_done`, with no reason, and `autodev-inflight` is never cleared on the success path.
4. Double ledger when the child loop defers a decision: `refine-to-ready-issue.yaml` `record_decision_unresolved` writes `autodev-decision-unresolved.txt` then exits `failed` without `classify_terminal`, so autodev's `skip_inflight` also ledgers `refine_failed`.
5. `refine_current` carries `fragment: with_rate_limit_handling` and `on_rate_limit_exhausted` on a `loop:` call state; both are inert (429 interception is gated on `action_result`, which sub-loop states never produce).
6. `/ll:go-no-go` Step 3f skips the findings write-back (and the waiver stamp) when it has no novel findings, so a GO can fail to stamp.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Proposed Solution

- `ll-issues show --json` emits `outcome_gate_waived`; `ll-issues check-readiness` gains `--honor-waiver` and lets explicit CLI thresholds win over config; the three CLI-based autodev gates pass `--honor-waiver`.
- Wire `/ll:go-no-go --auto` once per issue per run after an `oversized_atomic` deferral (`check_go_no_go_eligible → run_go_no_go → check_go_no_go_waiver → reopen_waived → decide_current`).
- Positive `autodev-size-review-ran-this-pass` marker written by `count_repair_cycle_size_review`; `check_size_review_ran_this_pass` requires it and fails closed on error.
- New `verify_impl_closed` state after `implement_current` success: re-read status, ledger `impl_exit0_not_closed` to `autodev-unverified.txt` when not closed, clear `autodev-inflight` on both branches; `finalize_done` dedupes reasoned lines.
- `skip_inflight` suppresses `refine_failed` when the ID is already in `autodev-decision-unresolved.txt`.
- Drop the inert keys from `refine_current`; add a structural test forbidding them on any `loop:` state.
- go-no-go SKILL.md: stamp the waiver on GO regardless of `HAS_FINDINGS`.
- Update `docs/guides/LOOPS_REFERENCE.md` (references deleted `run_decide`, omits ~18 states, four-vs-five entry points).

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- [ ] `ll-issues show <ID> --json` emits `outcome_gate_waived`
- [ ] `ll-issues check-readiness <ID> --honor-waiver` passes the outcome half when the flag is set; readiness still enforced; explicit `--readiness/--outcome` override config
- [ ] `check_passed`, `recheck_after_decide`, `recheck_scores` pass `--honor-waiver`
- [ ] go-no-go escalation states exist with one-shot marker; `check_atomic_design_remedy.on_no → check_go_no_go_eligible`
- [ ] `check_size_review_ran_this_pass` requires the positive marker; only `count_repair_cycle_size_review` writes it; `on_error → recheck_after_size_review`
- [ ] `implement_current.on_yes → verify_impl_closed`; unverified ledger line `ID  impl_exit0_not_closed`; inflight cleared on both branches; `finalize_done` counts a reasoned line once
- [ ] `skip_inflight` does not ledger `refine_failed` for an ID already in `autodev-decision-unresolved.txt`
- [ ] No `loop:` state in autodev declares `on_rate_limit_exhausted` or `with_rate_limit_handling`
- [ ] `ll-loop validate autodev` clean; `python -m pytest scripts/tests/` passes

## Status

**Open** | Created: 2026-09-04 | Priority: P2
