---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
---

# ENH-533: `backoff` Field Defined in Schema But Never Enforced in Executor

## Summary

`FSMLoop.backoff` (seconds between iterations) is documented, parsed from YAML, serialized in `to_dict()`/`from_dict()`, forwarded by all four paradigm compilers, and displayed in CLI output — but `FSMExecutor.run()` and `PersistentExecutor.run()` never read `self.fsm.backoff` and contain no `time.sleep()` call. The field is silently ignored at runtime.

## Location

- **File**: `scripts/little_loops/fsm/executor.py`
- **Line(s)**: 360–434 (at scan commit: 47c81c8) — entire main while loop, no `backoff` reference
- **Anchor**: `in method FSMExecutor.run()`, main while loop
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/fsm/executor.py#L360-L434)
- **Code**:
```python
# schema.py: backoff: float | None = None  # "Seconds between iterations"
# executor.py main loop — no sleep:
while True:
    if self._shutdown_requested: ...
    if self.iteration >= self.fsm.max_iterations: ...
    # ... state execution, no time.sleep(self.fsm.backoff) ...
    self.current_state = resolved_next
```

## Current Behavior

Setting `backoff: 5` in a loop YAML has no effect. The executor iterates as fast as the action completes, regardless of the configured backoff value.

## Expected Behavior

After each iteration's state transition resolves, the executor sleeps for `fsm.backoff` seconds before starting the next iteration (if `backoff` is set and > 0).

## Motivation

Backoff is critical for rate-limiting loops that call external APIs, run expensive shell commands, or poll system state. Without it, loops can overwhelm rate limits, hammer APIs, or consume excessive CPU. This is a documented feature that users configure but that silently does nothing.

## Proposed Solution

Insert a sleep at the end of the main `while True` loop in both `FSMExecutor.run()` and `PersistentExecutor.run()`:

```python
# At end of FSMExecutor.run() while loop, after self.current_state = resolved_next:
if self.fsm.backoff and self.fsm.backoff > 0:
    time.sleep(self.fsm.backoff)
```

Respect `_shutdown_requested` during sleep (interruptible sleep):
```python
if self.fsm.backoff and self.fsm.backoff > 0:
    deadline = time.time() + self.fsm.backoff
    while time.time() < deadline:
        if self._shutdown_requested:
            break
        time.sleep(min(0.1, deadline - time.time()))
```

## Scope Boundaries

- Only affects the inter-iteration pause; does not change action execution timing
- Does not add per-state backoff (only loop-level `backoff` field)
- The `timeout` check still applies during backoff sleep

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor.run()`, end of main while loop
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor.run()`, same location

### Dependent Files (Callers/Importers)
- All paradigm compilers pass `backoff` through; no changes needed
- `scripts/little_loops/cli/loop/info.py` — `cmd_show` already displays backoff; no changes

### Similar Patterns
- N/A — first use of `backoff` at runtime

### Tests
- `scripts/tests/test_ll_loop_execution.py` — add: loop with `backoff=0.01` executes delay between iterations
- `scripts/tests/test_ll_loop_execution.py` — add: shutdown during backoff sleep terminates cleanly

### Documentation
- N/A — field is already documented in schema

### Configuration
- N/A

## Implementation Steps

1. Add interruptible sleep at the end of `FSMExecutor.run()` while loop
2. Apply same change to `PersistentExecutor.run()`
3. Ensure timeout check accounts for time spent sleeping (already handled since timeout is checked at top of loop)
4. Add tests: backoff delay observed, SIGTERM during backoff exits cleanly

## Impact

- **Priority**: P2 — Documented feature that silently doesn't work; users configuring `backoff` get no rate-limiting
- **Effort**: Small — ~10 lines in two locations
- **Risk**: Low — Purely additive sleep; no existing behavior removed or changed
- **Breaking Change**: No (users with `backoff: 0` or no `backoff` see no change)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ll-loop`, `executor`, `scan-codebase`

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`

---

**Open** | Created: 2026-03-03 | Priority: P2
