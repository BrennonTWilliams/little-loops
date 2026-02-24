---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
---

# ENH-485: Rate-limit state file writes in orchestrator main loop

## Summary

The orchestrator main loop calls `_save_state()` on every 100ms tick, including while waiting for the merge coordinator to drain. `_save_state()` writes `state_file.write_text(json.dumps(...))` on every iteration, unlike `_maybe_report_status()` which has a 5-second throttle.

## Current Behavior

When the queue is empty and workers are done but `merge_coordinator.pending_count > 0`, the main loop at `orchestrator.py:637-670` ticks every 100ms. Each tick calls `_save_state()` which writes the full state JSON to disk. This results in ~10 filesystem writes per second during the merge-waiting period.

## Expected Behavior

`_save_state()` should be throttled (e.g., every 5 seconds) similar to `_maybe_report_status()`, or should only write when state has actually changed.

## Motivation

Reduces unnecessary filesystem I/O during the merge-waiting phase. While not a correctness issue, the repeated writes add unnecessary disk activity.

## Proposed Solution

Add a time-based throttle to `_save_state()`:

```python
def _save_state(self) -> None:
    now = time.time()
    if now - self._last_save_time < 5.0:
        return
    self._last_save_time = now
    # ... existing save logic ...
```

Or alternatively, call `_save_state()` only when state actually changes (issue completed/failed/started).

## Scope Boundaries

- **In scope**: Adding rate-limiting to `_save_state` calls
- **Out of scope**: Changing state persistence format, modifying main loop structure

## Implementation Steps

1. Add `_last_save_time` attribute to orchestrator
2. Add time-based throttle (5s interval) to `_save_state()`
3. Ensure state is still saved on shutdown and signal handling

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — add throttle to `_save_state`

### Dependent Files (Callers/Importers)
- N/A — internal optimization

### Similar Patterns
- `_maybe_report_status` already uses time-based throttling

### Tests
- N/A — internal timing optimization

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P4 — Performance optimization, no user-visible impact
- **Effort**: Small — Add time-based guard
- **Risk**: Low — Reduces write frequency, state is still saved on shutdown
- **Breaking Change**: No

## Labels

`enhancement`, `performance`, `parallel`, `auto-generated`

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`
- `/ll:format-issue` - 2026-02-24 - auto-format batch

---

## Status

**Open** | Created: 2026-02-24 | Priority: P4
