---
discovered_date: 2026-03-08
discovered_by: manual-observation
completed_date: 2026-03-08
---

# BUG-655: Off-Path State Highlighting Missing in FSM Diagram

## Summary

`ll-loop run --show-diagrams` failed to highlight off-path states (e.g., `fix`, reached via `on_failure`) even when they were the current active state. Only main-path states received the green border and bold name treatment introduced in FEAT-637.

## Root Cause

`scripts/little_loops/cli/loop/info.py` rendered the FSM diagram in two separate phases:

1. **Main-path rendering** (lines 592–635): Applied `is_highlighted` check and `_bc()` colorize helper to all box-drawing characters and bold-colorized the state name.
2. **Off-path rendering** (lines 860–893): Hard-coded plain box-drawing chars with zero references to `highlight_state`, `highlight_color`, or any colorize helper.

## Fix

**File:** `scripts/little_loops/cli/loop/info.py` — off-path box block (lines 860–893)

Mirrored the main-path highlighting pattern in the off-path block:

1. Added `is_highlighted` check per off-path state: `highlight_state is not None and off_s == highlight_state`
2. Defined `_bc_off()` helper identical in structure to the main-path `_bc()`.
3. Applied `_bc_off()` to all six box-drawing elements: top border (`┌─┐`), side pipes (`│`), bottom border (`└─┘`).
4. For the first content line (state name) when highlighted, replaced character-by-character writes with a single `colorize(line, f"{highlight_color};1")` call and blank-string slots — matching the main-path approach exactly.

## Verification

- All 119 existing tests passed with no regressions (`test_fsm_executor.py`, `test_sprint_integration.py`).
- Visual: when the loop enters the `fix` state, its box outline is green and the state name is bold-green, matching `evaluate` behavior.
