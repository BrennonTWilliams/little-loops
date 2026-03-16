---
discovered_date: 2026-03-15
discovered_by: analyze-loop
source_loop: general-task
source_state: execute
---

# BUG-770: general-task loop terminated with error in execute state

## Summary

The `general-task` loop failed immediately on its first iteration. After entering the `execute` state, the loop terminated with a `fatal_error` before any action could complete. The run duration was 1ms, indicating the failure occurred at startup or initialization rather than during execution of loop actions.

## Loop Context

- **Loop**: `general-task`
- **State**: `execute`
- **Signal type**: fatal_error
- **Occurrences**: 1
- **Last observed**: 2026-03-16T03:49:10.576296+00:00

## History Excerpt

Events leading to this signal:

```json
[
  {
    "event": "loop_start",
    "ts": "2026-03-16T03:49:10.575094+00:00",
    "loop": "general-task"
  },
  {
    "event": "state_enter",
    "ts": "2026-03-16T03:49:10.575191+00:00",
    "state": "execute",
    "iteration": 1
  },
  {
    "event": "loop_complete",
    "ts": "2026-03-16T03:49:10.576296+00:00",
    "final_state": "execute",
    "iterations": 1,
    "terminated_by": "error"
  }
]
```

## Expected Behavior

The `execute` state should run its configured action and either transition to the next state or retry. A `fatal_error` termination on the very first iteration (1ms duration) should not occur during normal operation.

## Proposed Fix

1. Review the `general-task` loop YAML configuration (`.loops/general-task.yaml`) for misconfigured actions, missing required fields, or invalid state definitions in `execute`.
2. Check if any required environment variables or context inputs are missing at loop startup.
3. Run `ll-loop run general-task --dry-run` (if available) or inspect logs for the error message that caused the fatal termination.

## Acceptance Criteria

- [ ] Root cause of the fatal error in `execute` state is identified
- [ ] `general-task` loop completes at least one full iteration without error
- [ ] Loop YAML is validated and any misconfiguration is corrected

## Labels

`bug`, `loops`, `captured`

## Status

**Open** | Created: 2026-03-15 | Priority: P2
