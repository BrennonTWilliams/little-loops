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
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._run_action()` (line 527–531: signal dispatch), `FSMExecutor.__init__()` (line 338: add `_pending_error` field alongside `_pending_handoff`), `FSMExecutor.run()` (line 362–363: add `_pending_error` check before/after the `_shutdown_requested` check)
- No changes needed to `scripts/little_loops/fsm/persistence.py` — see Research Findings Q3

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/signal_detector.py` — no changes needed; signals already defined
- `scripts/little_loops/cli/loop/lifecycle.py` — no changes needed; `cmd_resume` already handles `status="failed"` via the `PersistentExecutor.resume()` gate — see Research Findings Q1

### Similar Patterns
- `_pending_handoff` flag: declared at `executor.py:338`, set in `_run_action()` at line 527–530, checked in `run()` at line 409–410 — follow this exact pattern for `_pending_error`
- `_shutdown_requested` flag: declared at `executor.py:335`, set via `request_shutdown()` at line 340–346, checked in `run()` at line 362–363 — call `request_shutdown()` directly for `LOOP_STOP` signal (no new flag needed)

### Tests
- `scripts/tests/test_fsm_executor.py:1972` (`TestHandoffDetection` class) — follow this pattern for new signal-type tests: use `MagicMock(spec=SignalDetector)` with `mock_detector.detect_first.return_value = DetectedSignal(signal_type="error", payload="...", raw_match="FATAL_ERROR: ...")`
- `scripts/tests/test_fsm_executor.py:1606` (`TestSignalHandling` class) — reference for shutdown-signal test structure
- `scripts/tests/test_fsm_executor.py:1379` (`TestErrorHandling` class) — reference for `terminated_by="error"` test assertions

### Documentation
- N/A — behavior is implied by signal pattern names

### Configuration
- N/A

## Codebase Research Findings

_Added by `/ll:refine-issue` — answers the three questions raised in the Tradeoff Review:_

### Q1: How does `ll-loop resume` handle `status="error"` loops?

**Answer**: Blocked silently with a warning — no special handling needed.

Flow:
1. `FSMExecutor._finish("error")` is called → returns `ExecutionResult(terminated_by="error")`
2. `PersistentExecutor.run()` at `persistence.py:330` maps: `terminated_by="error"` → `final_status="failed"` (falls to the `else` branch)
3. `PersistentExecutor.resume()` at `persistence.py:364` gates: `state.status not in ("running", "awaiting_continuation")` → returns `None` for `"failed"`
4. `cmd_resume` at `lifecycle.py:152-153` logs `Warning: Nothing to resume for: {loop_name}` and exits with code 1

The status `"failed"` is treated identically to `"completed"` — both are non-resumable. No new handling required in `lifecycle.py`.

### Q2: Should `FATAL_ERROR` snapshot before terminating?

**Answer**: No special snapshot logic needed — `PersistentExecutor.run()` handles it automatically.

The `_pending_error` flag approach works cleanly with the existing persistence layer:
1. `_run_action()` detects signal, sets `self._pending_error = signal.payload`
2. `run()` loop checks flag, calls `self._finish("error", error=self._pending_error)`
3. `_finish()` at `executor.py:685-703` emits a `"loop_complete"` event (which triggers an interim `_save_state()` call in `PersistentExecutor._handle_event` at `persistence.py:274-275`)
4. `PersistentExecutor.run()` at `persistence.py:329-348` overwrites with the authoritative `status="failed"` snapshot

The existing `terminated_by="error"` → `final_status="failed"` mapping at `persistence.py:330` already handles this. No additional snapshot code needed.

### Q3: Does `PersistentExecutor` need a `_finish()` override?

**Answer**: No — and it's architecturally impossible. `PersistentExecutor` is a **composition wrapper**, not a subclass of `FSMExecutor` (`persistence.py:207`). It wraps `FSMExecutor` as `self._executor` (line 244) and handles final status in its own `run()` method after `self._executor.run()` returns (lines 329-348). The existing mapping already covers `terminated_by="error"` → `"failed"`. No changes to `PersistentExecutor` are needed.

## Implementation Steps

1. In `FSMExecutor.__init__()`, declare `self._pending_error: str | None = None` alongside `self._pending_handoff` at `executor.py:338`
2. In `FSMExecutor._run_action()`, extend the signal dispatch at `executor.py:527-531`:
   - `signal_type == "handoff"` → existing: `self._pending_handoff = signal` (unchanged)
   - `signal_type == "error"` → new: `self._pending_error = signal.payload`
   - `signal_type == "stop"` → new: `self.request_shutdown()` (reuses existing shutdown path at `executor.py:340-346`)
3. In `FSMExecutor.run()`, add `_pending_error` check near `executor.py:409-410` (after `_execute_state()` returns, alongside `_pending_handoff` check): `if self._pending_error: return self._finish("error", error=self._pending_error)`
4. Add tests following `TestHandoffDetection` at `test_fsm_executor.py:1972` — use `MagicMock(spec=SignalDetector)` to inject `DetectedSignal(signal_type="error", payload="disk full")` and `DetectedSignal(signal_type="stop", payload="goal achieved")`, then assert `result.terminated_by == "error"` and `result.terminated_by == "signal"` respectively

## Impact

- **Priority**: P2 — Built-in signals that don't work; users can't rely on `FATAL_ERROR:` for error handling in automation
- **Effort**: Small-Medium — Flag + dispatch logic; touches `executor.py` and `persistence.py`
- **Risk**: Low — New code paths; no existing logic removed
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | Structured events — signal patterns `FATAL_ERROR`, `LOOP_STOP`, `CONTEXT_HANDOFF` (line 1464), error handling (line 1196) |
| `docs/guides/LOOPS_GUIDE.md` | Loop control signals documentation (line 295) |

## Labels

`enhancement`, `ll-loop`, `signals`, `executor`, `scan-codebase`

## Resolution

**Status**: Resolved
**Resolved**: 2026-03-04

### Changes Made

- `scripts/little_loops/fsm/executor.py`:
  - Added `self._pending_error: str | None = None` field in `FSMExecutor.__init__()` alongside `_pending_handoff`
  - Extended signal dispatch in `_run_action()`: `signal_type == "error"` sets `self._pending_error = signal.payload`; `signal_type == "stop"` calls `self.request_shutdown()`
  - Added `_pending_error` check in `run()` after `_execute_state()` returns: calls `self._finish("error", error=self._pending_error)` when set
- `scripts/tests/test_fsm_executor.py`:
  - Added `TestFatalErrorAndStopSignals` class with 3 tests covering `FATAL_ERROR` termination, early-exit (no next-state traversal), and `LOOP_STOP` graceful shutdown

### Verification

- 84/84 tests pass (`python -m pytest scripts/tests/test_fsm_executor.py`)
- Ruff lint: clean
- Mypy: no issues

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — Linked `docs/generalized-fsm-loop.md`; updated test refs to `test_fsm_executor.py:1972` (TestHandoffDetection) and `:1606` (TestSignalHandling)
- `/ll:refine-issue` — 2026-03-04T00:34:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1d86080b-cd9a-4d75-867e-5546e0b8de04.jsonl` — Answered 3 Tradeoff Review questions; added precise line refs to Integration Map; added Codebase Research Findings section; refined Implementation Steps with exact executor.py anchors
- `/ll:manage-issue` — 2026-03-04T01:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/` — Implemented signal dispatch for error/stop; added TestFatalErrorAndStopSignals (3 tests); 84/84 pass

---

**Resolved** | Created: 2026-03-03 | Priority: P2

---

## Tradeoff Review Note

**Reviewed**: 2026-03-03 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | MEDIUM |
| Complexity added | MEDIUM |
| Technical debt risk | MEDIUM |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first — Before implementing, clarify the error-handling semantics to avoid tech debt: (1) How does `ll-loop resume` handle a loop terminated with `status="error"` — should it refuse to resume, warn, or treat as a normal resume point? (2) Should `FATAL_ERROR` write a final state snapshot before terminating, or terminate immediately? (3) Does `PersistentExecutor` need a separate `_finish()` override to handle error terminal state? Answering these questions will ensure the implementation is complete and doesn't require a follow-up rework pass.
