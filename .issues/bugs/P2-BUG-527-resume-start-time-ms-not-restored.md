---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
---

# BUG-527: `PersistentExecutor.resume` Doesn't Restore `start_time_ms` — Duration Stats Wrong After Resume

## Summary

When resuming an interrupted loop, `PersistentExecutor.resume` restores `started_at` (ISO timestamp) from persisted state but does not restore `start_time_ms` (the monotonic ms value). `FSMExecutor.run()` resets `start_time_ms` to `_now_ms()` at the top of `run()`, so the resumed execution measures only the resumed segment's wall time. The reported `duration_ms` and `${loop.elapsed_ms}` interpolation variable both reflect post-resume time, not total loop time.

## Location

- **File**: `scripts/little_loops/fsm/persistence.py`
- **Line(s)**: 367–392 (at scan commit: 47c81c8)
- **Anchor**: `in method PersistentExecutor.resume()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/fsm/persistence.py#L367-L392)
- **Code**:
```python
self._executor.current_state = state.current_state
self._executor.iteration = state.iteration
self._executor.captured = state.captured
self._executor.prev_result = state.prev_result
self._executor.started_at = state.started_at   # ISO timestamp restored
self._last_result = state.last_result
# start_time_ms NOT restored; FSMExecutor.run() will reset it to _now_ms()
```

## Current Behavior

After `ll-loop resume <name>`, the completed loop reports `duration_ms` reflecting only time since resume. `${loop.elapsed_ms}` and `${loop.elapsed}` in action prompts also count only from resume. The `started_at` ISO timestamp is correct (restored from state), but `start_time_ms` is not, creating an inconsistency between the two time representations.

## Expected Behavior

After resume, `duration_ms` reflects total time from the original start (including the interrupted segment). `${loop.elapsed_ms}` and `${loop.elapsed}` are accurate from the perspective of the loop's lifetime.

## Motivation

`${loop.elapsed}` is used in LLM prompts and loop logic (e.g., "abort if elapsed > 30 minutes"). After a resume, this value silently resets to 0, potentially allowing a resumed loop to exceed its intended wall-time budget without the prompt or evaluator knowing.

## Steps to Reproduce

1. Create a slow loop (e.g., 5 iterations with 10s sleep via `backoff`)
2. Start it: `ll-loop run slow-loop`
3. After 2 iterations, interrupt with Ctrl+C
4. Resume: `ll-loop resume slow-loop`
5. Observe: the summary shows duration only from step 4, not the original start at step 2

## Actual Behavior

Reported `duration_ms` covers only the resumed segment. `${loop.elapsed}` resets to ~0 at resume time.

## Root Cause

- **File**: `scripts/little_loops/fsm/persistence.py`
- **Anchor**: `in method PersistentExecutor.resume()`
- **Cause**: `start_time_ms` is a runtime monotonic clock value that is not persisted (correctly, since it's process-local). But `resume()` doesn't account for elapsed time already accumulated before the interruption.

## Proposed Solution

Persist the accumulated duration in the state file, then offset `start_time_ms` on resume:

```python
# In LoopState (or as a new field):
accumulated_ms: int = 0

# In PersistentExecutor._finish() / _save_state():
state.accumulated_ms = _now_ms() - self._executor.start_time_ms + state.accumulated_ms

# In PersistentExecutor.resume():
# Set start_time_ms such that elapsed = (now - start_time_ms) = time since original start
# Equivalent: fake start_time_ms = now - accumulated_ms
self._executor.start_time_ms = _now_ms() - state.accumulated_ms
```

Alternatively, add `elapsed_before_resume_ms` to `LoopState` and use it to offset the final `duration_ms` in `_finish()`.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor.resume()`, `_finish()`, `LoopState`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` displays `result.duration_ms`
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._build_context()` uses `start_time_ms` for `${loop.elapsed_ms}`

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_ll_loop_execution.py` — add resume-then-complete test verifying accumulated duration

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `accumulated_ms: int = 0` field to `LoopState`
2. In `PersistentExecutor._finish()`, store elapsed ms into `accumulated_ms` before saving final state
3. In `PersistentExecutor.resume()`, offset `start_time_ms` to account for accumulated time
4. Update `${loop.elapsed_ms}` context building if needed
5. Add test: interrupt loop after N iterations, resume, verify reported `duration_ms` ≥ pre-interrupt time

## Impact

- **Priority**: P2 — Silently wrong duration reporting; can break time-budget logic in LLM prompts
- **Effort**: Small — Field addition + 2 method changes
- **Risk**: Low — New field with default `0` is backwards compatible; runtime change isolated to `PersistentExecutor`
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `ll-loop`, `persistence`, `scan-codebase`

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`

---

**Open** | Created: 2026-03-03 | Priority: P2
