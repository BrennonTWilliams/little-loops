---
id: BUG-3026
status: open
captured_at: "2026-08-03T17:14:59Z"
discovered_date: 2026-08-03
discovered_by: capture-issue
testable: false
---

# ll-sprint fallback completion path fired for 3 of 10 issues in a single sprint run

## Summary

In an `ll-sprint run epic-3008` execution (10 issues, 10 waves), 3 of 10
issues (BUG-3012, ENH-3011, ENH-3014) hit the sprint runner's fallback
completion path instead of `/ll:manage-issue` completing the lifecycle
itself. `verify_issue_completed()` (`issue_lifecycle.py:741-775`) found the
issue's status still `open` after the `manage-issue` subprocess returned
exit 0, logged `Warning: {id} status=open (expected done/cancelled)` at
`issue_lifecycle.py:774`, and `process_issue_inplace()`
(`issue_manager.py:619`, fallback block at `issue_manager.py:1240-1338`)
recovered by detecting changed files via `verify_work_was_done()` /
`check_content_markers()` and calling `complete_issue_lifecycle()`
(`issue_lifecycle.py:1036-1076+`, logs `"Completing lifecycle for {id}
(command may have exited early)..."` at line 1076).

This fallback is intentional — its docstring (`issue_lifecycle.py:1044-1069`)
explicitly says it's "the path BUG-2963 was filed against: it fires after an
abnormal subloop exit, exactly when the deliverable is most likely to be
sitting uncommitted." So the fallback firing at all isn't itself the defect;
a 30% hit rate for a single sprint run is high enough to warrant checking
whether the *primary* completion path is regressing, not just confirming the
safety net still catches it.

## Current Behavior

All 3 fallback cases in this run shared a pattern in the session transcript:
the implementing agent explicitly waited on a **backgrounded
`python -m pytest scripts/tests/` run** via monitor/task notifications
("I'll wait for the background test run's completion notification rather
than poll", "I'll wait for the monitor to report the test suite finishing")
before proceeding to Phase 5 (finalize lifecycle: append session log, inject
`completed_at`, set status, commit). In each of these 3 cases, the
`manage-issue` subprocess returned exit 0 without status ever having been
flipped to `done`, and the sprint runner's fallback had to complete the
lifecycle and commit on its own behalf.

The other 7 issues in the same sprint run (all of which also ran the full
test suite in the foreground or background) completed normally through the
primary path with `Verified: {id} status=done`.

## Expected Behavior

`/ll:manage-issue` should reliably complete its own lifecycle (status flip +
commit) whenever it does the underlying work, without needing the sprint
runner's fallback to detect and repair an early exit. If the pattern is
specifically tied to backgrounded test-suite waits truncating the
`manage-issue` subprocess's turn before Phase 5 runs, that's the mechanism
to isolate and, if fixable, close.

## Motivation

The fallback path works, so no issue was silently lost in this run — but a
~30% rate on one sprint is high enough that it should be tracked rather than
assumed to be noise. If the root cause is a race between a backgrounded
subprocess (like a long `pytest` run) and the harness's turn/session
lifecycle for the `manage-issue` invocation, it will recur in every sprint
that runs the full suite per issue, and each recovery relies on
`verify_work_was_done()`'s file-diff heuristic correctly attributing changes
— a heuristic, not a guarantee.

## Steps to Reproduce

1. Run `ll-sprint run <epic-id>` on an epic with several issues that require
   running the full `python -m pytest scripts/tests/` suite as part of
   verification.
2. Observe that for a subset of issues, the `manage-issue` subprocess logs
   indicate it explicitly waited on a backgrounded test run via
   Monitor/task-notification before finalizing.
3. Check `ll-sprint`'s wave log for `Warning: {id} status=open (expected
   done/cancelled)` followed by `Fallback completion succeeded for {id}`
   for those issues, versus a clean `Verified: {id} status=done` for others.

## Root Cause

- **File**: `scripts/little_loops/issue_manager.py`
- **Anchor**: `in process_issue_inplace()`, fallback block at lines 1240-1338
- **Cause**: Not yet root-caused. Hypothesis from the transcript pattern:
  when the implementing agent backgrounds a long-running command (e.g. the
  full pytest suite) and explicitly defers finishing its turn until a
  notification arrives, something in the `manage-issue` subprocess's
  exit/turn-completion handling may return control (exit 0) to the sprint
  runner before the agent's own Phase 5 (finalize lifecycle) actually runs —
  possibly a turn-boundary or timeout interaction specific to
  backgrounded/monitored waits inside a non-interactive `claude -p`
  invocation. This needs to be confirmed by inspecting how `ll-sprint`
  invokes `manage-issue` (subprocess timeout/turn limits) alongside how the
  background-wait pattern behaves under `--dangerously-skip-permissions -p`
  batch mode specifically, since interactive sessions may not exhibit it.

## Proposed Solution

TBD - requires investigation. Two independent angles to check:
1. Whether `manage-issue`'s own prompt logic ever completes without
   reaching its Phase 5 finalize step when the implementing agent used a
   background/Monitor wait mid-turn — i.e., is Phase 5 actually being
   skipped, or is it running but its output isn't being captured/observed
   before the subprocess returns.
2. Whether `verify_work_was_done()` / `check_content_markers()` in the
   fallback path could be made to also record *why* the primary path
   didn't finish (e.g. tag the fallback commit or log line with a captured
   reason), so future occurrences carry a root-cause signal instead of just
   "may have exited early."

## Impact

- **Priority**: P3 - The fallback correctly recovers the work today, so no
  issues were lost, but a 30% rate on a single sprint run is a real
  regression signal worth tracking before it's assumed pre-existing/normal.
- **Effort**: Medium - requires reproducing the timing/race under
  `ll-sprint`'s actual subprocess invocation, not just reading code.
- **Risk**: Low - investigation-only; any fix would be internal to lifecycle
  completion detection, not user-facing surface area.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-03 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-08-03T17:16:22 - `4ad49473-6f8b-44cc-afa6-91e971b86c04.jsonl`
