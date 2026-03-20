---
id: FEAT-837
priority: P3
type: FEAT
status: open
discovered_date: 2026-03-20
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 93
---

# FEAT-837: ll-loop run sub-loop state shows full sub-state output

## Summary

When `ll-loop run` executes a loop that contains a state whose action is a sub-loop invocation, the CLI output for that state should stream or display the full sub-state-level output produced by the sub-loop — not just a high-level "entered sub-loop" or silent transition.

## Current Behavior

When a parent loop transitions into a state that triggers a sub-loop, the CLI output at the parent level does not surface the sub-loop's internal state transitions, action outputs, or terminal results. The sub-loop execution is effectively a black box from the perspective of the parent's CLI output.

## Expected Behavior

When the parent loop enters a sub-loop state, the CLI output should include the full output from the sub-loop execution: each state transition, action output, and terminal state should be visible in the terminal, clearly scoped/indented to indicate sub-loop depth.

## Motivation

Without sub-state output, debugging a parent loop that delegates to a sub-loop is impractical — the user cannot see what the sub-loop is doing, which states it enters, or why it terminates. This is especially painful for nested automation pipelines where the sub-loop failure mode is the primary thing to diagnose.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The fix is entirely in the event-callback chain. The child `FSMExecutor` in `_execute_sub_loop()` (`executor.py:584-588`) is constructed without an `event_callback`, so it defaults to `lambda _: None` (`executor.py:370`). All child state transitions, action outputs, and routing events are silently discarded.

**Approach**: Forward a depth-annotated wrapper of the parent's `event_callback` to the child executor. The wrapper injects a `"depth"` key into each event dict before passing it upstream. `display_progress` in `_helpers.py:306` reads `depth` and prefixes output with `"  " * depth` (2 spaces per level), matching the indent convention used in `WorkerPool._run_claude_command` (`worker_pool.py:686`) and `issue_manager.run_claude` (`issue_manager.py:113`).

**Specific change in `_execute_sub_loop()`** (`executor.py:584`):
```python
# Before (no callback — child events discarded):
child_executor = FSMExecutor(
    child_fsm,
    action_runner=self.action_runner,
    loops_dir=self.loops_dir,
)

# After (forward parent callback with depth annotation):
depth = getattr(self, "_depth", 0) + 1

def _sub_event_callback(event: dict) -> None:
    self.event_callback({**event, "depth": depth})

child_executor = FSMExecutor(
    child_fsm,
    action_runner=self.action_runner,
    loops_dir=self.loops_dir,
    event_callback=_sub_event_callback,
)
```

`display_progress` in `_helpers.py:306` would then read `depth = event.get("depth", 0)` and prefix all printed lines with `"  " * depth`.

As a bonus, `LoopState.active_sub_loop` (`persistence.py:92`) already exists as a stub field for this observability use-case — it is never populated at runtime and could be set here.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/fsm/executor.py:563-600` — `_execute_sub_loop()`: pass a depth-annotated callback wrapper to the child `FSMExecutor` constructor (currently no `event_callback` arg at line 584)
- `scripts/little_loops/cli/loop/_helpers.py:306-441` — `display_progress()`: read `depth = event.get("depth", 0)` and apply `"  " * depth` indent prefix to all printed lines (currently has fixed 7-space indent at line 310)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:602-621` — `_execute_state()`: branches to `_execute_sub_loop()` when `state.loop is not None` (line 615); no changes needed here
- `scripts/little_loops/fsm/executor.py:350-374` — `FSMExecutor.__init__()`: already accepts `event_callback` param (line 353); no changes needed
- `scripts/little_loops/fsm/persistence.py:341-369` — `PersistentExecutor._handle_event()`: relays every event to `_on_event` (line 368), which is where `display_progress` is wired (line 440 in `_helpers.py`); no changes needed
- `scripts/little_loops/fsm/persistence.py:92` — `LoopState.active_sub_loop`: existing stub field for sub-loop observability; candidate for population during `_execute_sub_loop()` (optional)

### Similar Patterns
- `scripts/little_loops/parallel/worker_pool.py:686-729` — `WorkerPool._run_claude_command()`: uses `"  {line}"` (2-space indent) for forwarded subprocess output — same indent convention to follow
- `scripts/little_loops/issue_manager.py:113-124` — `run_claude()`: identical `"  {line}"` pattern for forwarded subprocess output
- `scripts/little_loops/cli/loop/layout.py:106,121` — `_SUB_LOOP_BADGE = "↳⟳"`: existing visual marker for sub-loop states; could prefix `state_enter` output for sub-loop depth levels

### Tests
- `scripts/tests/test_fsm_executor.py:3233-3378` — `TestSubLoopExecution`: existing tests for sub-loop routing — extend with `event_callback=events.append` to assert child events appear in parent's collected event list
- `scripts/tests/test_ll_loop_display.py:34-51` — `MockExecutor`: inject depth-annotated events (`{"event": "state_enter", "depth": 1, ...}`) and assert indented output via `capsys.readouterr()`
- `scripts/tests/test_fsm_executor.py:1152-1203` — `event_callback=events.append` pattern for capturing all emitted events in a list

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — "Composable Sub-Loops" section: may need a note on sub-loop output visibility

## API/Interface

```python
# FSMExecutor._execute_sub_loop() — updated signature (no public API change)
# executor.py:563

def _execute_sub_loop(self, state: StateConfig, ctx: InterpolationContext) -> str | None:
    ...
    depth = getattr(self, "_depth", 0) + 1

    def _sub_event_callback(event: dict) -> None:
        # Inject nesting depth so display_progress can indent accordingly
        self.event_callback({**event, "depth": depth})

    child_executor = FSMExecutor(
        child_fsm,
        action_runner=self.action_runner,
        loops_dir=self.loops_dir,
        event_callback=_sub_event_callback,
    )
    child_executor._depth = depth  # propagate depth for further nesting
    child_result = child_executor.run()
    ...

# display_progress in run_foreground() — depth-aware indentation
# _helpers.py:306

def display_progress(event: dict) -> None:
    event_type = event.get("event")
    depth = event.get("depth", 0)
    indent = "  " * depth          # 2 spaces per nesting level
    tw = terminal_width()
    max_line = tw - 8 - len(indent)

    if event_type == "state_enter":
        state = event.get("state", "")
        ...
        print(f"{indent}[{current_iteration[0]}/{fsm.max_iterations}] {colorize(state, '1')} ...")
    elif event_type == "action_output":
        if not quiet and verbose:
            line = event.get("line", "")
            print(f"{indent}       {line[:max_line]}", flush=True)
    ...
```

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Add depth-annotated callback wrapper in `_execute_sub_loop()`** (`executor.py:584`): Before constructing `child_executor`, compute `depth = getattr(self, "_depth", 0) + 1`. Define `_sub_event_callback` that injects `"depth": depth` into every event dict and calls `self.event_callback`. Pass it as `event_callback=_sub_event_callback` to `FSMExecutor(...)`. Set `child_executor._depth = depth` to propagate nesting for deeper sub-loops.

2. **Add depth-aware indentation to `display_progress()`** (`_helpers.py:306`): Read `depth = event.get("depth", 0)` at the top of the closure. Compute `indent = "  " * depth`. Prefix all `print()` calls with `indent`. Adjust `max_line = tw - 8 - len(indent)` to account for the added prefix. Follow the 2-space-per-level convention from `worker_pool.py:686`.

3. **Optionally populate `LoopState.active_sub_loop`** (`persistence.py:92`): At the start of `_execute_sub_loop()`, emit an event or directly set the persistence state's `active_sub_loop` to `state.loop` so the state file reflects which sub-loop is running. Clear it after `child_executor.run()` returns.

4. **Extend `TestHierarchicalFSMSubLoopExecution`** (`test_fsm_executor.py:3233`): Add a test with `event_callback=events.append` that asserts child `state_enter` / `action_complete` events appear in the collected list with the `"depth": 1` key set.

5. **Extend `TestDisplayProgressEvents`** (`test_ll_loop_display.py`): Use `MockExecutor` (line 34) to inject events with `"depth": 1` and assert via `capsys.readouterr()` that output lines are prefixed with `"  "` (2-space indent).

## Impact

- **Priority**: P3 - Needed for practical debugging of nested FSM automation
- **Effort**: Small/Medium - likely a matter of forwarding stdout/stderr from the child process
- **Risk**: Low - output-only change, no behavioral side effects
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `captured`, `ll-loop`, `cli-output`, `sub-loop`

## Status

**Open** | Created: 2026-03-20 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-03-20T18:09:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/346bcd11-2121-427d-87da-c8c172089341.jsonl`
- `/ll:confidence-check` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9b913cdb-30ae-4f85-948f-0a1ee629b59a.jsonl`
- `/ll:refine-issue` - 2026-03-20T18:04:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e7180749-0a2c-4750-bf04-c0450201c88c.jsonl`
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/707beb95-6757-467e-96fe-ecc041ee03ed.jsonl`
