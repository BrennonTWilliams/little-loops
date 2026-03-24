---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 93
---

# ENH-485: Rate-limit state file writes in orchestrator main loop

## Summary

The orchestrator main loop calls `_save_state()` on every 100ms tick, including while waiting for the merge coordinator to drain. `_save_state()` writes `state_file.write_text(json.dumps(...))` on every iteration, unlike `_maybe_report_status()` which has a 5-second throttle.

## Current Behavior

When the queue is empty and workers are done but `merge_coordinator.pending_count > 0`, the main loop at `orchestrator.py:690-723` ticks every 100ms. Each tick calls `_save_state()` which writes the full state JSON to disk. This results in ~10 filesystem writes per second during the merge-waiting period.

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

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | Parallel mode orchestrator design (line 320), state persistence (line 763) |

## Labels

`enhancement`, `performance`, `parallel`, `auto-generated`

## Verification Notes

- **2026-03-05** — VALID. `_save_state()` at `orchestrator.py:494`; called unconditionally at line 683 in the main loop tick (100ms interval) with no throttle. `_maybe_report_status()` already throttled to 5s — the fix pattern is established. No `_last_save_time` attribute exists.

- **2026-03-06** — REFINEMENT COMPLETE. Codebase-driven research confirms:
  - **Problem verified**: Loop runs every 100ms (0.1s sleep at line 689) → ~10 writes/sec during merge wait
  - **Pattern confirmed**: `_maybe_report_status()` (line 558) uses identical throttle pattern with `_last_status_time` (initialized line 113)
  - **Implementation straightforward**: Add throttle guard to `_save_state()` following _maybe_report_status pattern
  - **Shutdown safety verified**: Explicit `_save_state()` calls in signal handlers preserve state on shutdown
  - **No dependencies**: No callers outside orchestrator, no configuration needed
  - **Test coverage sufficient**: Existing `test_save_state_writes_file()` and `test_concurrent_state_checkpoint()` tests cover state persistence

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-03-17_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- ENH-665 is listed as a formal blocker but the technical dependency is unclear — throttling `_save_state()` has no logical coupling to feature branch config. Confirm whether this dependency is intentional before starting.
- Minor ambiguity: two approaches mentioned (time-based throttle vs. write-on-change). Time-based (5s, matching `_maybe_report_status`) is the implied choice from the code sample and should be selected.

## Session Log
- `/ll:confidence-check` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/389dc9de-04e3-4aed-b74a-55808ef8e195.jsonl`
- `/ll:refine-issue` - 2026-03-24T03:30:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1b4320d8-11e5-4d53-b53f-70e2739aaa27.jsonl`
- `/ll:ready-issue` - 2026-03-23T05:59:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ab2782e-8c44-4dec-88a6-f477947d6c5a.jsonl`
- `/ll:confidence-check` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9126c24b-3b13-4d23-b5ce-cfbdd9d25883.jsonl`
- `/ll:verify-issues` - 2026-03-23T05:52:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a33da7f-6dc1-4101-a62c-c07c4786fb89.jsonl`
- `/ll:confidence-check` - 2026-03-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ca080b1f-e730-4767-86a3-c18f8cc098f4.jsonl`
- `/ll:refine-issue` - 2026-03-18T01:52:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/998bd9aa-1a49-4ab2-921c-6c64f9a90554.jsonl`
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`
- `/ll:format-issue` - 2026-02-24 - auto-format batch
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Issue is well-specified with specific line references and code sample; no knowledge gaps identified
- `/ll:refine-issue` - 2026-03-03 - Batch re-assessment: no new knowledge gaps; still blocked by FEAT-441
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c629849-3bc7-41ac-bef7-db62aeeb8917.jsonl`
- `/ll:refine-issue` - 2026-03-03T23:10:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` - Linked `docs/ARCHITECTURE.md` (lines 320, 763) to Related Key Documentation
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl`
- `agent:refine-issue` - 2026-03-06T21:30:00Z - Comprehensive codebase-driven refinement. Verified problem (100ms loop = ~10 writes/sec), confirmed pattern from `_maybe_report_status` (lines 558-569), checked shutdown safety, verified no external dependencies. Issue ready for implementation. Ready score: 86/100 → outcome confidence: 87/100. Both exceed thresholds; no additional cycles needed.
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: _save_state() called every 100ms tick, no throttle
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: `_save_state()` still unthrottled in main orchestrator loop
- `/ll:verify-issues` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ca080b1f-e730-4767-86a3-c18f8cc098f4.jsonl` — VALID: Problem confirmed. Line numbers have shifted since last verification — `_save_state()` now at line 519 (was 494), called at line 717 (was 683), `_maybe_report_status()` at line 592 (was 558), `_last_status_time` init at line 118 (was 113), sleep at line 723. No `_last_save_time` attribute exists — fix still needed.
- `/ll:refine-issue` - 2026-03-23T00:00:00Z - BLOCKER RESOLVED: ENH-665 completed and merged. Current line numbers: `_save_state()` at line 521, called at line 719, `_maybe_report_status()` at line 594, `_last_status_time` init at line 120, sleep at line 725. Issue is now unblocked and ready for implementation.

---

## Status

**Open** | Created: 2026-02-24 | Priority: P4
