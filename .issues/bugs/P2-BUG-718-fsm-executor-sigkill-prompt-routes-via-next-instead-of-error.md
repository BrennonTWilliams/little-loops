---
discovered_commit: b44bf7c
discovered_branch: main
discovered_date: 2026-03-13T06:00:00Z
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 88
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

## Proposed Solution

In `FSMExecutor._execute_state()` (`scripts/little_loops/fsm/executor.py`), after `_run_action` returns for a state using `state.next`, add a negative exit code check before returning the next state:

```python
result = self._run_action(state.action, state, ctx)
self.prev_result = {
    "output": result.output,
    "exit_code": result.exit_code,
    "state": self.current_state,
}
if result.exit_code is not None and result.exit_code < 0:
    # Process killed by signal — trigger graceful shutdown instead of silently advancing
    if state.on_error:
        return interpolate(state.on_error, ctx)
    self.request_shutdown()
    return None
return interpolate(state.next, ctx)
```

Reuses the existing `request_shutdown()` mechanism — no new infrastructure required. The optional `state.on_error` fallback enables loop authors to handle SIGKILL with a custom recovery state rather than shutdown.

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

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._execute_state()` — add negative exit code check before returning `state.next`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/runner.py` — calls `_execute_state` in the main loop; shutdown signal from this fix will propagate via existing `request_shutdown()` mechanism
- Any FSM loop YAML configs using prompt states with `next` transitions (all existing loops affected)

### Similar Patterns
- `scripts/little_loops/subprocess_utils.py` — related BUG-685 pattern (`returncode or 0` mask); fix here should mirror detection logic for consistency
- `scripts/little_loops/fsm/executor.py` — `_process_merge` early-return pattern (BUG-686) — same class of cleanup-skip-on-abnormal-exit

### Tests
- `scripts/tests/test_fsm_executor.py` — add `--scenario` test simulating SIGKILL on a prompt action, verify `request_shutdown()` is called and `next` routing does not occur

### Documentation
- N/A

### Configuration
- N/A

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

## Impact

- **Priority**: P2 — SIGKILL silently corrupts loop execution integrity; downstream states operate on absent data, producing unpredictable results and misleading history
- **Effort**: Small — targeted ~5-10 line fix in `FSMExecutor._execute_state()`; reuses existing `request_shutdown()` mechanism
- **Risk**: Low — new behavior only triggers on negative exit codes (process killed by signal), a path currently always treated as normal success; does not affect positive or zero exit codes
- **Breaking Change**: No — all existing loops with prompt states continue to behave identically unless a SIGKILL occurs

## Labels

`fsm`, `executor`, `signal-handling`, `loop-integrity`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-13T06:00:00Z - analysis of `ll-loop history issue-refinement-git`
- `/ll:format-issue` - 2026-03-13T06:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1bce590-015a-4862-aabe-11dcbf71a389.jsonl`
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0dc8374e-5f2d-475d-9631-d7487ab7323f.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0dc8374e-5f2d-475d-9631-d7487ab7323f.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P2
