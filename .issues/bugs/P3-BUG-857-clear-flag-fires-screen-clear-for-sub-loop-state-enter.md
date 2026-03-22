---
id: BUG-857
type: BUG
priority: P3
status: active
discovered_date: 2026-03-21
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
---

# BUG-857: --clear Flag Fires Screen Clear for Sub-Loop state_enter Events

## Summary

When running `ll-loop run ... --clear`, the screen clears on every `state_enter` event regardless of nesting depth. With a sub-loop state, each child FSM state entry triggers a spurious screen clear — causing the parent state header to flash and disappear immediately and the terminal to flicker once per child state transition for the entire duration of the sub-loop. The fix is a one-line change to guard the clear with `depth == 0`.

## Current Behavior

Running `ll-loop run <loop.yaml> --clear` (or `--clear --show-diagrams`) with a loop that contains a sub-loop state causes rapid screen flickering. The parent state header (`[N/M] run_sub_loop (Ts)`) is printed, then immediately erased by the first child `state_enter` event. Every subsequent child state transition triggers another spurious clear. From the user perspective, "the --clear flag fails to actually clear from before the state start" because the parent header never stays on screen long enough to be seen.

## Expected Behavior

Screen clears fire only for depth-0 (parent FSM) `state_enter` events. Child sub-loop state entries do not trigger a clear. The parent state diagram stays stable and readable throughout the entire sub-loop execution.

## Motivation

The `--clear` flag exists to create a stable "live dashboard" effect, especially when combined with `--show-diagrams`. Sub-loop clears completely defeat this purpose — the screen becomes an unreadable flicker during any sub-loop state. The fix is a one-line guard using `depth`, a variable already in scope at the clear site.

## Steps to Reproduce

1. Create a loop YAML with at least one sub-loop state
2. Run `ll-loop run <loop.yaml> --clear --show-diagrams`
3. Observe: screen clears rapidly once per child state transition while inside the sub-loop state
4. Parent state header disappears immediately on sub-loop entry

## Root Cause

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Anchor**: `display_progress()`, line 333 — the `state_enter` clear block
- **Cause**: The screen-clear condition has no `depth == 0` guard. The `depth` variable is extracted at line 319 (`depth = event.get("depth", 0)`) and used at line 335 for other parent-only logic, but line 333's clear fires for all depths. Child sub-loop states emit `state_enter` events with `depth=1` (or deeper) that bubble up through the event callback chain to `display_progress`, triggering spurious clears.

## Location

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Line**: 333
- **Anchor**: `display_progress()`, `state_enter` handler
- **Code**:
```python
# Current (buggy) — line 333
if clear_screen and sys.stdout.isatty():
    print("\033[2J\033[H", end="", flush=True)
```

## Proposed Solution

Add `and depth == 0` to the existing clear condition:

```python
# Before (line 333)
if clear_screen and sys.stdout.isatty():

# After
if clear_screen and sys.stdout.isatty() and depth == 0:
```

This is a one-line change. The `depth` variable is already in scope (line 319) and the `if depth == 0:` pattern is already used on line 335 directly below for other parent-only logic.

**Event flow after fix:**
```
Parent state_enter "run_sub_loop"  (depth=0) → CLEAR ✓ → shows "[2/10] run_sub_loop (Xs)"
  Child state_enter "X"            (depth=1) → no clear ✓ → child output accumulates
    child action runs...
  Child state_enter "Y"            (depth=1) → no clear ✓ → child output accumulates
    child action runs...
  ...child loop_complete
Parent state_enter "done"          (depth=0) → CLEAR ✓ → shows "[3/10] done (Ys)"
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — line 333 (the only change needed)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py:479` — wires `display_progress` into `executor._on_event` inside `run_foreground()`
- `scripts/little_loops/cli/loop/run.py` — calls `run_foreground()` (the function that sets up the callback)

### Similar Patterns
- Line 335 in same function already uses `if depth == 0:` for other parent-only display logic

### Tests
- `scripts/tests/test_ll_loop_display.py` — add test alongside existing `test_clear_flag_emits_ansi_clear_when_tty` in `TestRunForeground`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Open `scripts/little_loops/cli/loop/_helpers.py`, line 333
2. Change `if clear_screen and sys.stdout.isatty():` to `if clear_screen and sys.stdout.isatty() and depth == 0:`
3. In `scripts/tests/test_ll_loop_display.py`, add `test_clear_flag_suppressed_for_sub_loop_state_enter` to `TestDisplayProgressEvents` (the class that has `_make_fsm()` and `_make_args()` helpers, alongside `test_clear_flag_emits_ansi_clear_when_tty` at line ~1689):
   ```python
   def test_clear_flag_suppressed_for_sub_loop_state_enter(
       self, capsys: pytest.CaptureFixture[str]
   ) -> None:
       """--clear flag does NOT emit clear-screen for depth>0 (sub-loop) state_enter events."""
       events = [
           {"event": "state_enter", "state": "child_state", "iteration": 1, "depth": 1},
       ]
       executor = MockExecutor(events)
       with patch("sys.stdout.isatty", return_value=True):
           run_foreground(executor, self._make_fsm(), self._make_args(clear=True))
       out = capsys.readouterr().out
       assert "\033[2J" not in out
   ```
4. Run `python -m pytest scripts/tests/test_ll_loop_display.py -k "clear" -v` — all clear tests should pass
5. Manually verify with a sub-loop loop + `--clear --show-diagrams` — parent diagram stays stable during sub-loop execution

## Impact

- **Priority**: P3 - Functional bug; defeats the `--clear` flag's dashboard purpose with any sub-loop configuration
- **Effort**: Small - One line change + one test
- **Risk**: Low - Depth guard uses an already-available variable; pattern already used nearby
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `ll-loop`, `clear`, `sub-loop`, `display`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-03-21T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/67c676ba-82ac-4237-b939-729e88d85e2f.jsonl`
- `/ll:refine-issue` - 2026-03-22T03:00:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2366b16-8efd-4448-a7f8-095332982c3d.jsonl`
- `/ll:format-issue` - 2026-03-22T02:56:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a86c9d2-b725-4d32-b86b-f32c9bdd6720.jsonl`
- `/ll:capture-issue` - 2026-03-21T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fbb74e23-bb67-47cf-ae22-17dea4c26b9f.jsonl`

---

## Status

**Open** | Created: 2026-03-21 | Priority: P3
