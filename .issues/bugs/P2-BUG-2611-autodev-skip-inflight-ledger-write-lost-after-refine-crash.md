---
id: BUG-2611
captured_at: "2026-07-12T03:48:48Z"
discovered_date: 2026-07-12
discovered_by: capture-issue
status: open
---

# BUG-2611: autodev's skip_inflight ledger write is lost after a refine_current crash

## Summary

When `autodev`'s `refine_current` state (`scripts/little_loops/loops/autodev.yaml`)
crashes on its `refine-to-ready-issue` sub-loop invocation, it routes to
`skip_inflight`, which is supposed to append `"<ID>  refine_failed"` to
`autodev-skipped.txt` before advancing the queue. In a live run against
EPIC-2575 (run dir
`.loops/runs/auto-refine-and-implement-20260711T220542/`), this write never
landed: the issue (ENH-2577) that crashed is completely absent from
`autodev-passed.txt`, `autodev-skipped.txt`, `autodev-gate-blocked.txt`, and
`autodev-decision-unresolved.txt`. It vanished from the run with no ledger
trace at all, even though the queue correctly advanced past it to the next
issue.

## Current Behavior

1. `auto-refine-and-implement --context scope=EPIC-2575` ran `delegate` →
   `autodev` against the resolved issue set `ENH-2577,ENH-2578,FEAT-2576`.
2. `autodev` dequeued `ENH-2577` first (03:05:47Z) and started
   `refine-to-ready-issue`.
3. By 03:08:15Z that sub-loop had already failed and entered its `diagnose`
   state. The diagnostic LLM found the issue's Session Log completely
   untouched — no `refine-issue`/`wire-issue`/confidence-check entries were
   ever appended — meaning the crash happened very early (likely
   `resolve_issue` or `check_lifetime_limit`), before any real refinement
   work started.
4. `refine_current`'s `on_failure`/`on_error` both route to `skip_inflight`
   (autodev.yaml:138-152), which appends `"${captured.input.output}
   refine_failed"` to `${context.run_dir}/autodev-skipped.txt` and clears
   the inflight sentinel, then transitions to `dequeue_next`.
5. The queue did visibly advance — `ENH-2578` was dequeued next at
   03:08:58Z (confirmed via `.loops/.history/2026-07-12T030542-*/events.jsonl`)
   — which can only happen if `dequeue_next` was reached, which can only
   happen via `skip_inflight` (or `on_no`, which doesn't apply since the
   queue wasn't empty).
6. Despite that, the final `autodev-skipped.txt` for this run contains only
   one line: `ENH-2578  low_readiness`. The expected `ENH-2577
   refine_failed` line is missing.
7. `finalize` (auto-refine-and-implement.yaml) computes `SKIPPED_BREAKDOWN`
   and `PARKED_RATE` purely from `autodev-skipped.txt`'s line count, so the
   final `summary.json` for the run undercounts skips by exactly the
   crashed issue: `{"skipped":1,...}` instead of `{"skipped":2,...}`.
   ENH-2577 is invisible to every reporting surface (summary.json,
   `passed`/`not_closed`/`skipped` ledgers, `SKIPPED_BREAKDOWN`) even though
   it was dequeued, attempted, and crashed.

## Expected Behavior

Every issue popped from `autodev-queue.txt` should land in exactly one
terminal ledger (`autodev-passed.txt`, `autodev-skipped.txt`,
`autodev-gate-blocked.txt`, or `autodev-decision-unresolved.txt`) by the
time the run ends — there should be no path where an issue is dequeued,
worked on, and then disappears without a trace. A `refine_current` crash
specifically should reliably produce an `"<ID>  refine_failed"` line in
`autodev-skipped.txt` so `finalize`'s `SKIPPED_BREAKDOWN`/`PARKED_RATE`
accounting stays accurate and operators can see that the issue needs a
re-run rather than assuming it was silently deferred by design.

## Motivation

`SKIPPED_BREAKDOWN` and `PARKED_RATE` in `auto-refine-and-implement`'s
`finalize` state exist specifically so an operator can distinguish a
healthy run (e.g. "2 decomposed") from an unhealthy one without re-reading
`events.jsonl`. If `skip_inflight`'s write can silently disappear, that
visibility signal under-reports real failures — a crash that should read as
"1 refine_failed" instead reads as nothing, and the operator has to
manually diff `autodev-queue.txt`'s original input against every ledger
file (as was done to find this bug) to discover the missing issue.

## Proposed Solution

- **File**: `scripts/little_loops/loops/autodev.yaml`, `skip_inflight` state
  (line ~138)
- Investigate why the `echo "${captured.input.output}  refine_failed" >>
  ${context.run_dir}/autodev-skipped.txt` append didn't survive to the final
  file. Candidates to rule out:
  - A second, later truncation of `autodev-skipped.txt` clobbering the
    earlier append (grep confirms only one `printf '' >` truncation exists,
    at `init`, so this looks unlikely — but verify no `with_rate_limit_handling`
    retry re-enters `init` mid-run).
  - `${captured.input.output}` being empty/stale at the moment
    `skip_inflight` executes (e.g. the `input` capture var got overwritten
    by a nested sub-loop's own `context_passthrough` before `skip_inflight`
    reads it back).
  - A race between the epic-branch worktree (`delegate: worktree:
    ${captured.epic_branch.output}`, ENH-2609) and the run_dir path — if
    `skip_inflight`'s shell executes in the worktree but
    `${context.run_dir}` resolves to a path relative to the main repo (or
    vice versa), the append could land in a different physical file than
    the one `finalize` later reads.
- Reproduce directly: `ll-loop run autodev "ENH-2577" --context
  scope=EPIC-2575` (or a synthetic issue engineered to fail
  `resolve_issue`) and inspect `autodev-skipped.txt` immediately after
  `skip_inflight` fires, before the run continues, to confirm which
  hypothesis holds.
- Once the root cause is confirmed, the fix is likely either (a) resolving
  `run_dir` to an absolute, worktree-independent path before `skip_inflight`
  writes, or (b) re-reading the dequeued ID from `autodev-inflight` (which
  is written unconditionally at `dequeue_next`) instead of
  `${captured.input.output}` if the capture variable turns out to be the
  stale one.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `skip_inflight` state and
  possibly `dequeue_next`'s inflight-sentinel handling

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `finalize`
  state reads `autodev-skipped.txt` for `SKIPPED_BREAKDOWN`/`PARKED_RATE`
- Any other loop that calls `loop: autodev` (e.g. `sprint-refine-and-implement`
  if applicable) inherits the same undercounting risk

### Similar Patterns
- `mark_gate_blocked` and `record_decision_unresolved` (autodev.yaml) use
  the same "append to run_dir ledger file, then dequeue_next" idiom — worth
  auditing for the same failure mode once root cause is known, since they
  likely share whatever path-resolution issue affects `skip_inflight`

### Tests
- No existing test covers `refine_current` crashing mid-sub-loop and
  verifying the skip ledger; add one exercising `skip_inflight` under the
  epic-branch/worktree delegation path (ENH-2609) if that turns out to be
  the root cause

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 - Silently undercounts failures in the reporting layer
  that `auto-refine-and-implement`'s epic-branch mode (just landed) depends
  on for operator visibility; not data-destructive, but actively misleads
  anyone reading `summary.json` after a run.
- **Effort**: Small - Likely a path-resolution or capture-variable staleness
  fix scoped to one or two states in `autodev.yaml`.
- **Risk**: Low - Fix is isolated to bookkeeping/logging, not the core
  refine/implement control flow.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-07-12T03:48:48Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1d9db9d7-f5b8-4bb6-a582-c2b7b01b3900.jsonl`

---

**Open** | Created: 2026-07-12 | Priority: P2
