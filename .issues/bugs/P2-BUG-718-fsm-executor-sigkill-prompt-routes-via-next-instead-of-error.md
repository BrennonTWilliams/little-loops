---
discovered_commit: b44bf7c
discovered_branch: main
discovered_date: 2026-03-13T06:00:00Z
discovered_by: capture-issue
---

# BUG-718: FSM executor routes SIGKILL'd prompt actions via unconditional `next` instead of error path

## Summary

When a prompt action's Claude Code subprocess is killed by SIGKILL (exit code -9),
`_execute_state` in `fsm/executor.py` still returns the unconditional `state.next`
target. The FSM records `action_complete ✗ exit=-9` in history but then routes as
if the action completed normally, silently advancing the workflow with a corrupted
or missing result.

## Location

- **File**: `scripts/little_loops/fsm/executor.py`
- **Line(s)**: 504–512 (at scan commit: b44bf7c)
- **Anchor**: `in method FSMExecutor._execute_state()`
- **Code**:

```python
# Handle unconditional transition
if state.next:
    if state.action:
        result = self._run_action(state.action, state, ctx)
        self.prev_result = {
            "output": result.output,
            "exit_code": result.exit_code,
            "state": self.current_state,
        }
    return interpolate(state.next, ctx)   # ← always returns next, exit_code ignored
```

## Current Behavior

Observed in `issue-refinement-git` loop history:

```
02:19:16  action_complete   ✗ exit=-9  92709ms   ← SIGKILL
02:19:16  route             score_issues → refine_issues   ← normal next, not error
02:19:16  loop_complete     refine_issues  3 iter  [signal]
```

`score_issues` has `next: refine_issues`. The Claude Code subprocess was killed
(SIGKILL), producing no output and no AI-generated result. The FSM still transitioned
to `refine_issues`, which then ran with empty/missing context from the killed action.

## Expected Behavior

When a prompt action exits with a negative code (process killed by signal), the FSM
should either:

1. **Trigger shutdown** — treat a negative exit code the same as receiving a stop
   signal and begin graceful termination, OR
2. **Route via `on_error`** — if `on_error` is configured on the state, use it;
   otherwise fall back to shutdown, OR
3. **Override `next`** — skip the unconditional `next` and treat the kill as an
   unrecoverable action failure

Option 1 or 2 is preferred. Option 3 is a minimal fix.

## Root Cause

- **File**: `scripts/little_loops/fsm/executor.py`
- **Anchor**: `in method FSMExecutor._execute_state()`
- **Cause**: The `if state.next:` branch runs the action but returns `state.next`
  unconditionally without inspecting `result.exit_code`. Negative exit codes (killed
  by signal) and non-zero exit codes are both silently swallowed for states with
  unconditional `next` transitions, which are the standard choice for all prompt
  states.

## Motivation

Prompt states use `next` (not `on_success`/`on_failure`) because LLMs are expected
to detect errors internally and emit FSM signals. But SIGKILL prevents any output,
so the LLM never gets a chance to emit a signal. The result is a zombie transition:
the FSM advances to a state whose prerequisites (the killed action's output) were
never fulfilled. This silently corrupts the loop's execution integrity — downstream
states operate on absent data, producing unpredictable results and making loop
history misleading.

## Implementation Steps

1. In `_execute_state`, after `_run_action` returns for a state with `state.next`:
   - Check if `result.exit_code < 0` (killed by signal)
   - If so, call `self.request_shutdown()` to trigger graceful termination
2. Optionally, also check `state.on_error` as a fallback route before shutdown
3. Update `_run_action` to also detect when `process.returncode` is `None`
   and map it to `-9` explicitly (guards against the BUG-685 pattern in loop context)
4. Add a test using the `--scenario` mechanism to simulate a killed prompt action
   and verify shutdown is triggered instead of `next` routing

## Related Issues

- **BUG-685**: `process.returncode or 0` masks killed process in `subprocess_utils.py`
  (same class of bug, different subsystem — ll-auto/ll-parallel)
- **BUG-686**: Early returns in `_process_merge` skip `_current_issue_id` cleanup
  (pattern of skipping cleanup on abnormal exits)

## Steps to Reproduce

1. Run `ll-loop run <any-loop-with-prompt-states>`
2. Send SIGKILL to the Claude Code subprocess spawned by the prompt action
3. Observe history: `action_complete ✗ exit=-9` followed by a normal `next` route
4. The FSM advances to the next state despite the kill

## Session Log
- `/ll:capture-issue` - 2026-03-13T06:00:00Z - analysis of `ll-loop history issue-refinement-git`
