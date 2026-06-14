---
id: BUG-2144
type: BUG
priority: P2
captured_at: '2026-06-14T03:50:03Z'
discovered_date: '2026-06-14'
discovered_by: capture-issue
status: open
relates_to:
- ENH-303
- BUG-2141
confidence_score: 87
outcome_confidence: 78
score_complexity: 19
score_test_coverage: 16
score_ambiguity: 19
score_change_surface: 18
---

# BUG-2144: Sprint orchestrator deadlock — ENH-303 idle detection doesn't cover Option J sub-session

## Summary

ENH-303 added output-idle detection to `subprocess_utils.py` so that stuck subprocesses
are killed before the full timeout expires. However, when a sprint sequential worker
hits the context limit and Option J spawns a **new** Claude subprocess, the idle detector
covers the original subprocess (now dead) but has no handle on the Option J child.
The sprint orchestrator at `sprint/run.py:369` waits indefinitely for
`process_issue_inplace()` to return — which is itself waiting for the Option J child
to exit. With no hard timeout at the sprint level, the sprint deadlocks.

**Recovery today**: `ps aux | grep ll-sprint | awk '{print $2}' | xargs kill -9`

## Current Behavior

`sprint/run.py:369` calls `process_issue_inplace()` with no timeout:
```python
issue_result = process_issue_inplace(
    info=issue,
    config=config,
    logger=logger,
    dry_run=args.dry_run,
)
```

`process_issue_inplace()` calls `_run_with_continuation()`, which loops calling
`run_claude_command()`. Each call to `run_claude_command()` has idle detection via
`idle_timeout=parallel_config.idle_timeout_per_issue`. But:

1. The **original** session dies (context limit hit).
2. Option J spawns a **new** subprocess via `run_claude_command()` — this new call
   starts a fresh idle timer.
3. The new session blocks on user interaction (e.g., `AskUserQuestion`). It produces
   SOME initial output (enough to reset the idle timer), then goes silent waiting for
   a response.
4. If the idle timer was reset by the initial burst of output, the new subprocess
   continues running until its full timeout expires (default 3600s / 1 hour).
5. The sprint orchestrator has no independent watchdog — it only knows
   `process_issue_inplace()` hasn't returned.

**Observed (2026-06-13)**: Sprint blocked for 90+ minutes waiting for the rogue Option J
session. Manual kill was required.

## Expected Behavior

The sprint orchestrator should have a hard maximum per-issue wall-clock timeout,
independent of the subprocess idle detection. If an issue takes longer than
`sprint.max_issue_wall_clock_time` (configurable, suggested default 45 min), the
orchestrator kills the subprocess, marks the issue as failed with reason
`WALL_CLOCK_TIMEOUT`, and proceeds to the next issue.

## Root Cause

- **File**: `scripts/little_loops/cli/sprint/run.py`
- **Lines**: 369–390 (sequential issue dispatch loop, no timeout wrapper)
- **Anchor**: in function `_run_sprint_waves` or similar sequential dispatch

ENH-303's idle detection operates at the `run_claude_command()` level. Option J
spawns a new subprocess whose initial output resets the idle window. The sprint level
has no timeout that covers the total elapsed time for an issue across all subprocess
spawns (original + Option J + any further continuations).

## Proposed Fix

Add a per-issue wall-clock timeout at the sprint orchestrator level:

```python
import signal

MAX_ISSUE_TIME = config.sprint.max_issue_wall_clock_time or 2700  # 45 min default

def _timeout_handler(signum, frame):
    raise IssueWallClockTimeout(issue.issue_id)

signal.signal(signal.SIGALRM, _timeout_handler)
signal.alarm(MAX_ISSUE_TIME)
try:
    issue_result = process_issue_inplace(...)
except IssueWallClockTimeout:
    logger.error(f"  {issue.issue_id}: wall-clock timeout after {MAX_ISSUE_TIME}s — marking failed")
    issue_result = IssueProcessingResult(success=False, failure_reason="WALL_CLOCK_TIMEOUT", ...)
finally:
    signal.alarm(0)
```

Alternatively, run `process_issue_inplace` in a thread with `concurrent.futures.ThreadPoolExecutor`
and use `future.result(timeout=MAX_ISSUE_TIME)`.

Also: surface the timeout in sprint state so `ll-sprint show` reports it as
`TIMEOUT` rather than `FAILED`.

## Files to Modify

- `scripts/little_loops/cli/sprint/run.py` — sequential dispatch loop, add wall-clock timeout wrapper
- `scripts/little_loops/config.py` — add `sprint.max_issue_wall_clock_time` config key
- `config-schema.json` — document new config key

## Impact

- **Severity**: High — sprint deadlocks require manual intervention; no automatic recovery
- **Effort**: Small-Medium — timeout wrapper around one call site; config key addition
- **Risk**: Low — additive; only triggers on timeout which currently hangs forever anyway
- **Breaking Change**: No

## Related Issues

- ENH-303 (done): Add idle detection for ll-sprint subprocesses — covers subprocess-level idle, not sprint-level wall-clock
- BUG-2141: Option J loses sprint worker framing — root cause of the deadlock; this is the safety net
- ENH-2143: Sequential sprint worktree isolation — complementary containment

## Session Log
- `/ll:capture-issue` - 2026-06-14T03:50:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Status
**Open** | Priority: P2
