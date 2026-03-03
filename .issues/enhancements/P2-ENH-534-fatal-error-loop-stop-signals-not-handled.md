---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
---

# ENH-534: `FATAL_ERROR` and `LOOP_STOP` Signals Detected But Silently Dropped

## Summary

`SignalDetector` is initialized with three built-in patterns (`HANDOFF_SIGNAL`, `ERROR_SIGNAL`, `STOP_SIGNAL`) and detects all three. But `FSMExecutor._run_action()` only branches on `signal_type == "handoff"`. A `FATAL_ERROR: ...` or `LOOP_STOP: ...` marker in action output is detected and then silently discarded — the executor continues as if no signal was received.

## Location

- **File**: `scripts/little_loops/fsm/executor.py`
- **Line(s)**: 527–531 (at scan commit: 47c81c8)
- **Anchor**: `in method FSMExecutor._run_action()`, signal detection block
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/fsm/executor.py#L527-L531)
- **Code**:
```python
signal = self.signal_detector.detect_first(result.output)
if signal and signal.signal_type == "handoff":
    self._pending_handoff = signal
# signal_type "error" and "stop" fall through — silently ignored
```

Signal definitions in `signal_detector.py:74-76`:
```python
HANDOFF_SIGNAL = SignalPattern("handoff", r"CONTEXT_HANDOFF:\s*(.+)")
ERROR_SIGNAL   = SignalPattern("error",   r"FATAL_ERROR:\s*(.+)")
STOP_SIGNAL    = SignalPattern("stop",    r"LOOP_STOP:\s*(.*)")
```

## Current Behavior

- A Claude action that emits `FATAL_ERROR: disk full` → signal detected with `type="error"`, payload `"disk full"` → signal dropped → loop continues to next state
- A Claude action that emits `LOOP_STOP: goal achieved` → signal detected with `type="stop"`, payload `"goal achieved"` → signal dropped → loop continues normally

## Expected Behavior

- `FATAL_ERROR: ...` → executor terminates immediately with `terminated_by="error"`, records the error payload in the result
- `LOOP_STOP: ...` → executor requests graceful shutdown (equivalent to `request_shutdown()`, completes current iteration and exits with `terminated_by="signal"`)

## Motivation

`ERROR_SIGNAL` and `STOP_SIGNAL` are documented as built-in signals in the schema/signal_detector. Users writing Claude action prompts may include `FATAL_ERROR:` to signal an unrecoverable condition. Without handling, these signals are meaningless — automation loops cannot self-terminate on error conditions discovered inside action output.

## Proposed Solution

Extend the signal dispatch in `_run_action()`:

```python
signal = self.signal_detector.detect_first(result.output)
if signal:
    if signal.signal_type == "handoff":
        self._pending_handoff = signal
    elif signal.signal_type == "error":
        # Terminate immediately with error
        raise FatalSignalError(signal.payload)   # or use _finish("error")
    elif signal.signal_type == "stop":
        self.request_shutdown()   # graceful stop after current iteration
```

Since `_run_action` is called inside `_execute_state`, which is called inside `run()`, the cleanest approach is to set a flag on `self` (like `_pending_error`) and check it at the top of the `run()` loop, similar to how `_shutdown_requested` works.

## Scope Boundaries

- Only affects `FSMExecutor` and `PersistentExecutor`; does not change signal detection logic
- Does not change `HANDOFF_SIGNAL` behavior
- User-defined signal patterns are not affected

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._run_action()`, `FSMExecutor.run()` (add `_pending_error` flag check)
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor` inherits via `FSMExecutor`; may need `_finish()` update

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/signal_detector.py` — no changes needed; signals already defined
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume` may need to handle new `"error"` terminal status

### Similar Patterns
- `_shutdown_requested` flag pattern in `FSMExecutor` — reuse same approach for `_pending_error`

### Tests
- `scripts/tests/test_ll_loop_execution.py` — add: action output with `FATAL_ERROR:` terminates with error
- `scripts/tests/test_ll_loop_execution.py` — add: action output with `LOOP_STOP:` gracefully stops loop

### Documentation
- N/A — behavior is implied by signal pattern names

### Configuration
- N/A

## Implementation Steps

1. Add `_pending_error: str | None = None` field to `FSMExecutor`
2. In `_run_action()`, handle `signal_type == "error"` (set `_pending_error`) and `signal_type == "stop"` (call `request_shutdown()`)
3. At top of `run()` while loop, check `_pending_error` and call `_finish("error")`
4. Add tests for both signal types

## Impact

- **Priority**: P2 — Built-in signals that don't work; users can't rely on `FATAL_ERROR:` for error handling in automation
- **Effort**: Small-Medium — Flag + dispatch logic; touches `executor.py` and `persistence.py`
- **Risk**: Low — New code paths; no existing logic removed
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ll-loop`, `signals`, `executor`, `scan-codebase`

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`

---

**Open** | Created: 2026-03-03 | Priority: P2
