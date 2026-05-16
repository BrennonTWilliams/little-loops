---
discovered_date: 2026-03-30
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
---

# BUG-897: `ll-loop list --running` misses recently-started background loops

## Summary

When `ll-loop run <name> --background` launches a loop, the parent process writes a `.pid` file immediately, but the `.state.json` file is only created once the child process enters its first FSM state (several seconds later). Since `list_running_loops()` only globs for `*.state.json`, `ll-loop list --running` reports "No running loops" during this startup window.

## Current Behavior

Running `ll-loop list --running` immediately after `ll-loop run <name> --background` reports "No running loops" even though the loop process is alive. The `.pid` file exists in `.loops/.running/`, but `list_running_loops()` only globs for `*.state.json` files, which are not created until the child process enters its first FSM state (several seconds after launch).

## Expected Behavior

`ll-loop list --running` should show recently-started loops that have a `.pid` file but no `.state.json` yet. These should appear with a `status="starting"` indicator so the user knows the loop is initializing.

## Steps to Reproduce

1. Run `ll-loop run <name> --background` with any valid loop configuration
2. Immediately run `ll-loop list --running` (within 1-3 seconds)
3. Observe: output says "No running loops" despite the loop process being alive
4. Wait several seconds for the FSM to initialize, then run `ll-loop list --running` again
5. Observe: the loop now appears in the list

## Root Cause

- **File**: `scripts/little_loops/fsm/persistence.py`
- **Anchor**: `list_running_loops()` at line 499, glob at line 515
- **Cause**: `list_running_loops()` only globs `*.state.json` (line 515), but the state file is first written when `PersistentExecutor._handle_event()` receives a `state_enter` event (persistence.py:362-364), which happens after the child process bootstraps, acquires a scope lock, creates a `PersistentExecutor`, and enters the FSM main loop (executor.py:508-514). Meanwhile, the parent process writes `.pid` immediately after `Popen` at `_helpers.py:272`. The gap between PID file creation and first state file write makes loops invisible to `list_running_loops()` during startup.

## Motivation

This bug creates a confusing user experience during loop startup. Users who launch a background loop and immediately check its status see "No running loops", which can lead them to believe the loop failed to start. This undermines trust in the loop management system and may cause users to launch duplicate loops.

## Proposed Solution

Modify `list_running_loops()` in `scripts/little_loops/fsm/persistence.py` to also detect loops that have a `.pid` file but no `.state.json` yet. For each such orphan PID file:

1. Read the PID and check if the process is alive (using existing `_process_alive` from `concurrency.py`)
2. If alive, synthesize a `LoopState` with `status="starting"`, `current_state="(initializing)"`, `iteration=0`
3. If not alive, skip it (stale PID file from a crashed start)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The `_process_alive()` function at `concurrency.py:26-38` is a clean module-level function that accepts `pid: int` and returns `bool`; already imported by `lifecycle.py:18` — use the same import pattern
- `_read_pid_file()` at `lifecycle.py:39-50` handles the `.pid` read+validate pattern; either import it or inline the 3-line `int(pid_file.read_text().strip())` with `(ValueError, OSError)` guard
- `LoopState` requires all non-default fields at construction; the minimal synthetic state needs: `loop_name`, `current_state`, `iteration`, `captured`, `prev_result`, `last_result`, `started_at`, `updated_at`, `status` — see test factory at `test_ll_loop_commands.py:205-215` for a minimal construction example
- `_STATUS_COLORS` in `info.py:63` only maps `running`, `interrupted`, `stopped` — unmapped statuses fall to dim text (`"2"`); adding `"starting": "33"` (yellow) would give visual distinction
- The `LockManager` glob-and-alive-check pattern at `concurrency.py:169-178` and `concurrency.py:205-214` is the structural analogue: glob files → parse → check alive → keep or discard

## Implementation Steps

1. **Import `_process_alive`** — In `persistence.py`, add `from little_loops.fsm.concurrency import _process_alive` at the top-level imports
2. **Scan orphan PID files** — In `list_running_loops()` after the `*.state.json` glob loop (after line 520), collect loop names already in `states`. Then glob `running_dir.glob("*.pid")` and for each `.pid` file whose `stem` is not in the collected names:
   - Read PID: `int(pid_file.read_text().strip())` with `ValueError`/`OSError` guard (follow `lifecycle.py:47-48` pattern)
   - Check `_process_alive(pid)` — if `True`, synthesize and append:
     ```python
     LoopState(
         loop_name=pid_file.stem,
         current_state="(initializing)",
         iteration=0,
         captured={},
         prev_result=None,
         last_result=None,
         started_at="",
         updated_at="",
         status="starting",
         accumulated_ms=0,
     )
     ```
   - If `False`, skip (stale PID from crashed start)
3. **Add `"starting"` status color** — In `info.py:63`, add `"starting": "33"` (yellow) to `_STATUS_COLORS` dict
4. **Add tests** in `test_fsm_persistence.py` under `TestUtilityFunctions`:
   - Test: live PID + no state file → returns `LoopState` with `status="starting"` (mock `_process_alive` → `True`)
   - Test: stale PID + no state file → not returned (mock `_process_alive` → `False`)
   - Test: loop with both state file + PID → returns only the state-file version (no duplicate)
5. **Run tests**: `python -m pytest scripts/tests/test_fsm_persistence.py -v`

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py:499` — `list_running_loops()`: add `.pid` file scanning after `*.state.json` glob (line 515)
- `scripts/little_loops/cli/loop/info.py:63` — `_STATUS_COLORS` dict: add `"starting"` color entry (currently maps only `running`, `interrupted`, `stopped`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py:48-50` — sole production caller of `list_running_loops()`; accesses `.loop_name`, `.current_state`, `.iteration`, `.status`, `.accumulated_ms`
- `scripts/little_loops/fsm/__init__.py:108,173` — re-exports `list_running_loops` (no changes needed)

### Similar Patterns
- `scripts/little_loops/fsm/concurrency.py:26-38` — `_process_alive(pid: int) -> bool`: module-level function, returns `True` for live/EPERM, `False` only for ESRCH
- `scripts/little_loops/cli/loop/lifecycle.py:39-50` — `_read_pid_file(pid_file: Path) -> int | None`: reads and validates `.pid` file contents; consider importing or inlining this pattern
- `scripts/little_loops/fsm/concurrency.py:169,205` — `LockManager` globs `*.lock` files and checks `_process_alive()` for each; structural analogue for the `.pid` glob pattern
- `scripts/little_loops/fsm/persistence.py:391-406` — `PersistentExecutor._save_state()`: shows how `LoopState(...)` is manually constructed with all required fields

### Tests
- `scripts/tests/test_fsm_persistence.py:870` — `TestUtilityFunctions`: existing tests for `list_running_loops()` that populate `.running/` with state files; add sibling tests for PID-only scenarios
- `scripts/tests/test_cli_loop_lifecycle.py:127-154` — pattern for writing `.pid` files + mocking `_process_alive` with `side_effect` sequences
- `scripts/tests/test_cli_loop_background.py:139-157` — pattern for asserting `.pid` file contents after `run_background()`
- New test cases needed:
  - Live PID without `.state.json` → should return `LoopState` with `status="starting"`
  - Stale PID without `.state.json` → should be skipped (not returned)
  - Mixed: some loops with state files, some with PID-only → both should appear
  - Mock target: `"little_loops.fsm.persistence._process_alive"` (matching import location)

### Documentation
- `docs/reference/API.md` — documents `list_running_loops` API; update for `starting` status

### Configuration
- N/A

## Impact

- **Priority**: P3 — Confusing UX but no data loss; workaround is to wait a few seconds
- **Effort**: Small — Single function change with well-defined scope, reusing existing utilities
- **Risk**: Low — Additive change to existing function; existing behavior preserved for loops with state files
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/reference/API.md | Documents FSM persistence module and `list_running_loops` API |
| architecture | docs/ARCHITECTURE.md | FSM system design context |

## Labels

`bug`, `captured`

## Resolution

**Fixed** | Resolved: 2026-04-01 | By: `/ll:manage-issue bug fix BUG-897`

### Changes Made
- `scripts/little_loops/fsm/persistence.py`: Added `from little_loops.fsm.concurrency import _process_alive` import; added PID-file scanning in `list_running_loops()` after the `*.state.json` glob loop — synthesizes a `LoopState(status="starting", current_state="(initializing)", iteration=0)` for any live process with a `.pid` file but no state file yet
- `scripts/little_loops/cli/loop/info.py`: Added `"starting": "33"` (yellow) to `_STATUS_COLORS` so starting loops display with visual distinction
- `scripts/tests/test_fsm_persistence.py`: Added 3 test cases in `TestUtilityFunctions` — live PID only → `status="starting"`, stale PID → skipped, both files → no duplicate

### Verification
- All 3 new tests pass; 4006 pre-existing tests pass; lint and mypy clean

## Session Log
- `/ll:manage-issue` - 2026-04-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:ready-issue` - 2026-04-02T04:26:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/90944be6-c0ae-40b1-a19e-9351fa308847.jsonl`
- `/ll:confidence-check` - 2026-04-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fb231202-0547-4549-a812-a70ba1e322b5.jsonl`
- `/ll:refine-issue` - 2026-04-01T20:55:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fb231202-0547-4549-a812-a70ba1e322b5.jsonl`
- `/ll:format-issue` - 2026-04-01T20:50:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fb231202-0547-4549-a812-a70ba1e322b5.jsonl`
- `/ll:verify-issues` - 2026-04-01T17:45:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/712d1434-5c33-48b6-9de5-782d16771df5.jsonl`
- `/ll:capture-issue` - 2026-03-30T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c781d736-a85e-47b1-9ef5-625122a2c2ae.jsonl`

---

## Status

**Completed** | Created: 2026-03-30 | Resolved: 2026-04-01 | Priority: P3
