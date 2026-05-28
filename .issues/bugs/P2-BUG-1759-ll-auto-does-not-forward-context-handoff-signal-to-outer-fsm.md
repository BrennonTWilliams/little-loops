---
id: BUG-1759
title: ll-auto does not forward CONTEXT_HANDOFF signal to outer FSM loop
type: BUG
status: open
priority: P2
captured_at: '2026-05-28T00:42:55Z'
discovered_date: '2026-05-28'
discovered_by: capture-issue
labels:
- bug
- ll-loop
- fsm
- autodev
- handoff
---

# BUG-1759: ll-auto does not forward CONTEXT_HANDOFF signal to outer FSM loop

## Summary

When the autodev FSM runs `ll-auto` as a subprocess action, `ll-auto` internally spawns a Claude manage-issue session. If that Claude session hits its context limit and emits `CONTEXT_HANDOFF:` to its own stdout, `ll-auto` does not forward this signal to its own stdout. The outer autodev FSM's `signal_detector` only sees `ll-auto`'s stdout — so it never detects the handoff and cannot take any terminal action for that iteration.

## Root Cause

- **File**: `scripts/little_loops/fsm/signal_detector.py`, `scripts/little_loops/fsm/executor.py`
- **Function**: `SignalDetector.detect_first()` / `_run_action()` `on_output_line` callback
- **Explanation**: The `signal_detector` correctly detects `CONTEXT_HANDOFF:` in direct Claude action output (when `ll-loop run` calls Claude directly). But when the action is `ll-auto`, the subprocess chain is `autodev FSM → ll-auto → claude manage-issue`. The Claude process emits `CONTEXT_HANDOFF:` to `ll-auto`'s internal subprocess pipe, not to `ll-auto`'s own stdout. `ll-auto` does not surface this signal upward, so the autodev FSM's executor receives no handoff event and continues waiting.

## Observed Behavior

During the 2026-05-27 autodev stuck incident: ENH-1702's Claude subprocess hit context limit (301%), spawned a continuation session, and completed the work. But `ll-auto` (PID 31860) kept running waiting for the inner process; the outer autodev FSM never received a handoff signal and hung in `implement_current` for 4+ hours with no events since 6:56 PM.

## Expected Behavior

When `ll-auto`'s child Claude process emits `CONTEXT_HANDOFF:`, `ll-auto` should either:
1. Print `CONTEXT_HANDOFF: <payload>` to its own stdout so the outer FSM can detect and handle it, OR
2. Exit with a specific exit code that the autodev FSM routes as a terminal/handoff state

Alternatively, the autodev FSM's `implement_current` state should have a mandatory wall-clock timeout (via BUG-1723's `idle_timeout`) so a stuck `ll-auto` subprocess is killed after a configurable threshold regardless of signal propagation.

## Implementation Steps

1. Identify where `ll-auto` reads output from its child Claude subprocess (likely in `scripts/little_loops/cli/auto.py` or equivalent)
2. Add signal detection on `ll-auto`'s child stdout — when `CONTEXT_HANDOFF:` is detected, print it to `ll-auto`'s own stdout and exit cleanly
3. Alternatively: add a handoff exit code (e.g. 75) that the autodev FSM's `implement_current` state routes to a terminal path
4. Update autodev loop YAML to handle the handoff route if using exit code approach
5. Add test covering: `ll-auto` child emits `CONTEXT_HANDOFF:` → outer FSM detects it

## Related Issues

- BUG-1723: Wire idle_timeout through FSM schema — complementary fix; idle_timeout would unblock the hang even without signal propagation
- BUG-819 (done): Missed handoff in WorkerPool silently continues as success — different code path (parallel worker pool, not FSM action runner)

## Session Log
- `/ll:capture-issue` - 2026-05-28T00:42:55Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
