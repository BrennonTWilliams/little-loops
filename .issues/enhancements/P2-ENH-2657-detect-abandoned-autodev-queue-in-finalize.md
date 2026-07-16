---
id: ENH-2657
title: Detect an abandoned autodev queue in finalize (silent work loss on timeout)
type: ENH
priority: P2
status: open
discovered_date: 2026-07-16
captured_at: "2026-07-16T00:00:00Z"
discovered_by: capture-issue
labels:
  - enhancement
  - loops
  - autodev
  - finalize
  - observability
  - captured
---

# ENH-2657: Detect an abandoned autodev queue in finalize (silent work loss on timeout)

## Summary

When `auto-refine-and-implement` (via `sprint-refine-and-implement`) delegates a
large issue set to `autodev`, `autodev` drains its unified depth-first queue
(`${run_dir}/autodev-queue.txt`) one issue at a time. If `autodev` hits its
`timeout` (28800s / 8h) or `max_steps` (500) **mid-drain**, it terminates with a
**non-empty queue** — those issues were dispatched but never refined, never
implemented, and never parked with a skip reason. `finalize` in
`auto-refine-and-implement.yaml` never reads `autodev-queue.txt`, so these
abandoned issues appear in **none** of summary.json's counters (`closed`,
`skipped`, `not_closed`, `gate_blocked`, `inflight_unresolved`). The run reads a
clean partial and routes to the green `done` terminal.

`finalize` should read the residual `autodev-queue.txt` at completion, count it
as a distinct `abandoned` signal in summary.json, fold it into `parked_rate`,
and — like `phantom` (BUG-2636) — keep an abandoned-queue run off the green
`done` terminal.

## Motivation

- **Observed silent work loss.** In the `ll-marketing` run
  `sprint-refine-and-implement-20260715T182217` (EPIC-058): 27 issues dispatched,
  3 passed / 1 shipped, 11 parked, and **18 left undrained in
  `autodev-queue.txt`** when the 8h timeout fired (481m39s ≈ 480m = `timeout:
  28800`). Two of the 18 (`ENH-110`, `ENH-111`) were correctly-enqueued
  decomposition children at the front of the queue that simply never got their
  turn. summary.json reported `closed=1` and routed to `done`; the 18 abandoned
  issues were invisible. The operator had to hand-reconstruct the real outcome
  from the queue file.
- **Same class as BUG-2636, but wider.** BUG-2636 added `INFLIGHT_UNRESOLVED` to
  catch the single `autodev-inflight` sentinel left mid-implementation. That
  guard reads exactly one issue; it does not look at the residual queue. An
  entire undrained queue passes straight through the existing accounting.
- **The verdict/terminal is misleading, not just incomplete.** Because
  `CLOSED > 0` yields `partial` → `done` (finalize routing,
  `auto-refine-and-implement.yaml:883-924`), a run that abandoned 18 of 27
  dispatched issues renders green. There is no signal telling the operator to
  re-run to drain the remainder.
- **It reframes the budget conversation.** Knowing "18 abandoned at timeout" (vs
  "1 shipped, looks done") is what tells an operator to either raise the budget,
  shrink the scope, or land the wasted-slot prefilter (tracked separately). The
  counter is the prerequisite for that decision.

## Current Behavior

- `autodev` seeds `${run_dir}/autodev-queue.txt` from `context.input` at `init`
  and pops the head at each `dequeue_next`; it exits to its `done` terminal only
  when the queue is empty (`autodev.yaml:80-83`). On `timeout`/`max_steps` the
  FSM engine terminates with the queue still populated.
- `finalize` (`auto-refine-and-implement.yaml:676-924`) computes `CLOSED`,
  `NOT_CLOSED`, `SKIP`, `ERR`, `GATE_BLOCKED`, `DECISION_UNRESOLVED`,
  `INFLIGHT_UNRESOLVED` — but never reads `autodev-queue.txt`.
- `PARKED_RATE` denominator is the dispatched ledger, but its numerator omits the
  abandoned queue, so the rate understates the true incompletion.
- Verdict routing: `phantom` → `incomplete` (exit 1); everything else with
  `CLOSED > 0` → `done`. An abandoned-queue partial is indistinguishable from a
  clean partial.

## Expected Behavior

- `finalize` reads `${run_dir}/autodev-queue.txt`. Non-blank residual lines
  (excluding any already in the closed-now union, to be safe against a
  late-closing race) are counted as `ABANDONED` and the IDs are written to an
  `auto-refine-and-implement-abandoned.txt` artifact.
- summary.json gains an `"abandoned": N` field and the abandoned count is added
  to the `PARKED_RATE` numerator alongside `SKIP + NOT_CLOSED + GATE_BLOCKED +
  DECISION_UNRESOLVED + INFLIGHT_UNRESOLVED`.
- Verdict/terminal: a run with `ABANDONED > 0` must not route to green `done`.
  Preferred: treat a non-empty residual queue the same way `phantom` is treated
  (exit 1 → `incomplete`), OR introduce an `incomplete-abandoned` verdict that
  also routes to the `incomplete` terminal. A run that legitimately drained its
  queue (empty file) is unaffected.
- The `incomplete` terminal message names the abandoned count and points at the
  artifact so a re-run to drain is obvious.

## Proposed Solution

1. In `finalize` (`auto-refine-and-implement.yaml`), after the closed-now union
   is computed, add:
   ```sh
   : > "$RUN_DIR/$P-abandoned.txt"
   if [ -s "$RUN_DIR/autodev-queue.txt" ]; then
     grep '[^[:space:]]' "$RUN_DIR/autodev-queue.txt" | sort -u \
       | comm -23 - "$RUN_DIR/$P-closed-now-union.txt" \
       > "$RUN_DIR/$P-abandoned.txt" 2>/dev/null || true
   fi
   ABANDONED=$(count $P-abandoned.txt)
   ```
2. Add `ABANDONED` to the `PARKED_RATE` numerator.
3. Add `"abandoned":%s` to the summary.json printf and the human-readable echo.
4. Extend the verdict block so `ABANDONED > 0` cannot yield green `done`:
   either fold into the existing `phantom`/exit-1 path or add a dedicated
   `incomplete-abandoned` verdict routed to `incomplete`. Keep `CLOSED > 0` runs
   labeled as partial-progress in the *verdict string* (so real closures are
   still visible), but the *terminal* must be `incomplete` when work was
   abandoned.
5. Update the `incomplete` terminal message to mention the abandoned count.

## Acceptance Criteria

- [ ] `finalize` reads `autodev-queue.txt`; a non-empty residual queue produces
      `abandoned > 0` in summary.json and an
      `auto-refine-and-implement-abandoned.txt` artifact listing the IDs.
- [ ] The abandoned count is included in the `parked_rate` numerator.
- [ ] A run that abandoned ≥1 dispatched issue does NOT route to the green `done`
      terminal (renders as `incomplete` per `ll-loop`'s `_is_success` name check).
- [ ] A run that fully drained its queue (empty `autodev-queue.txt`) is
      unaffected: same verdict/terminal as today, `abandoned: 0`.
- [ ] A run where the residual queue entries all actually closed (late-close
      race) reports `abandoned: 0` (the closed-now-union subtraction holds).
- [ ] Test coverage in `scripts/tests/test_builtin_loops.py` (or a finalize-
      focused test) simulating a non-empty `autodev-queue.txt` at finalize and
      asserting the verdict/terminal + summary.json field.

## Sources

- Run artifacts:
  `<ll-marketing>/.loops/runs/sprint-refine-and-implement-20260715T182217/`
  (`autodev-queue.txt` = 18 undrained; `autodev-passed.txt`,
  `autodev-skipped.txt`, `auto-refine-and-implement-dispatched.txt`).
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:676-937` (finalize
  + incomplete terminal).
- `scripts/little_loops/loops/autodev.yaml:17-83` (queue seed/drain, max_steps
  500, timeout 28800).
- BUG-2636 (`INFLIGHT_UNRESOLVED`) — the single-sentinel precedent this
  generalizes.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — verdict/terminal signal honesty.
- `.claude/CLAUDE.md` § Loop Authoring (MR-1 non-LLM evaluator; this is a
  non-LLM ledger check).

## Status

open — captured 2026-07-16 from the EPIC-058 sprint-refine run analysis.

## Impact

- **Affected:** `auto-refine-and-implement.yaml` finalize, and by delegation
  every `sprint-refine-and-implement` / EPIC-scope autodev run that exceeds its
  budget mid-drain. No change to loops that drain fully.
- **Severity:** P2 — silent work loss. Dispatched issues vanish from the run
  summary with no counter and no non-green signal, so operators cannot tell a
  fully-drained partial from one that abandoned most of its set.
- **Risk of change:** low — additive ledger read + one summary field + a verdict
  branch; the empty-queue path (normal completion) is unchanged.

## Scope Boundaries

- **In scope:** finalize reading the residual queue, the `abandoned` counter,
  `parked_rate` inclusion, and keeping abandoned-queue runs off green `done`.
- **Out of scope:** the pre-dispatch readiness/dependency prefilter that would
  reduce wasted slots (separate ENH), raising or making the 8h `timeout`
  configurable, and any change to `autodev`'s own drain/step budget.

## Session Log

- 2026-07-16: Captured from forensic analysis of `ll-marketing` run
  `sprint-refine-and-implement-20260715T182217`. Confirmed 18 issues left in
  `autodev-queue.txt` at the 8h timeout, invisible to summary.json, run routed
  to green `done`.
