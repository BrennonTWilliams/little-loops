---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
confidence_score: 97
outcome_confidence: 90
---

# ENH-607: `PersistentExecutor` writes state file twice per state transition

## Summary

`PersistentExecutor._handle_event` triggers `_save_state()` for `state_enter`, `route`, and `loop_complete` events. A single state transition emits both `route` and `state_enter` in sequence, causing two consecutive JSON serializations and file writes per transition. The `route` write is redundant because `state_enter` fires immediately after with the same `current_state` data.

## Current Behavior

Each state transition produces two `_save_state()` calls (one for `route`, one for `state_enter`). For a loop with 50 iterations and 2 transitions each, that's 200 JSON serializations + 200 file writes for in-progress state saves alone.

## Expected Behavior

Remove `route` from the trigger set to halve the number of in-progress state writes. The `route` event's destination state matches the upcoming `state_enter`'s state — no information is lost.

## Motivation

Every in-progress state transition triggers two I/O operations where one suffices:

- **Unnecessary I/O**: `route` and `state_enter` fire back-to-back in the same thread with identical `current_state`; the `route` write is always overwritten within microseconds
- **Compounding overhead**: A 50-iteration loop with 2 transitions per iteration produces 200 writes where 100 suffice — 2x the file I/O for zero additional durability
- **Crash safety unaffected**: The `route`-to-`state_enter` window is sub-millisecond on the same thread; a crash in that window causes re-entry of the same state, which is already the correct resume behavior

## Scope Boundaries

**In scope:**
- Removing `route` from the `_save_state` trigger condition in `_handle_event`

**Out of scope:**
- Batching or debouncing state writes
- Changing event emission order
- Modifying `loop_complete` or `state_enter` trigger behavior

## Proposed Solution

Change the trigger condition in `_handle_event` at `persistence.py:284-287`:

```python
# Before:
if event_type in ("state_enter", "route", "loop_complete"):
    self._save_state()

# After:
if event_type in ("state_enter", "loop_complete"):
    self._save_state()
```

The crash window between `route` and `state_enter` is extremely narrow (microseconds, same thread). If resumed after a crash in that window, the state would be re-entered from the same `current_state`, which is correct behavior.

## Success Metrics

- [ ] `_save_state()` call count halved in integration tests for multi-transition loops
- [ ] Existing resume behavior unchanged: crash-then-resume re-enters `current_state` correctly
- [ ] All tests in `scripts/tests/` pass unchanged

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — remove `"route"` from trigger set in `_handle_event` at line 286

### Dependent Files (Callers/Importers)
- N/A — `_handle_event` is called internally by `PersistentExecutor`; no external callers affected

### Similar Patterns
- N/A

### Tests
- `scripts/tests/` — verify existing persistence tests pass; optionally add assertion that save count equals transition count (not 2x)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Open `scripts/little_loops/fsm/persistence.py` at line 286
2. Change `("state_enter", "route", "loop_complete")` to `("state_enter", "loop_complete")`
3. Run existing tests to confirm no regressions

## Impact

- **Priority**: P4 - Performance improvement, reduces I/O by ~50% for state persistence
- **Effort**: Small - One-line change
- **Risk**: Low - Narrow crash window is the only theoretical concern
- **Breaking Change**: No

## Labels

`enhancement`, `ll-loop`, `performance`

## Session Log
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — VALID: `if event_type in ("state_enter", "route", "loop_complete"):` confirmed at `persistence.py:286`
- `/ll:format-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — v2.0 format: added Motivation, Scope Boundaries restructure, Success Metrics, Integration Map, Implementation Steps; added confidence_score and outcome_confidence to frontmatter
- `/ll:confidence-check` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — Readiness: 97/100 PROCEED; Outcome: 90/100 HIGH CONFIDENCE

---

## Status

**Open** | Created: 2026-03-06 | Priority: P4
