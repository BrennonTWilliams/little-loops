---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 86
---

# BUG-600: `cmd_resume` does not register signal handlers — Ctrl-C skips graceful shutdown

## Summary

`cmd_resume` creates a `PersistentExecutor` and calls `executor.resume()` without installing SIGINT/SIGTERM signal handlers. Unlike `cmd_run`, which registers `_loop_signal_handler` for graceful shutdown, `cmd_resume` leaves default Python signal handling in place. Pressing Ctrl-C during a resumed loop raises `KeyboardInterrupt` directly instead of calling `executor.request_shutdown()`, so the final state is not saved as `"interrupted"` and any mid-action subprocess is not killed cleanly.

## Location

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Line(s)**: 138-188 (at scan commit: c010880)
- **Anchor**: `in function cmd_resume()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/c010880ecfc0941e7a5a59cc071248a4b1cbc557/scripts/little_loops/cli/loop/lifecycle.py#L138-L188)
- **Code**:
```python
executor = PersistentExecutor(fsm, loops_dir=loops_dir)
result = executor.resume()
```

Compare with `cmd_run` in `run.py:148-151`:
```python
_loop_shutdown_requested = False
_loop_executor = executor
signal.signal(signal.SIGINT, _loop_signal_handler)
signal.signal(signal.SIGTERM, _loop_signal_handler)
```

## Current Behavior

When a user resumes a loop and presses Ctrl-C, Python's default `KeyboardInterrupt` propagates without calling `executor.request_shutdown()`. The state file retains its last checkpoint status (e.g., `"running"`) rather than being updated to `"interrupted"`.

## Expected Behavior

`cmd_resume` should install the same signal handlers as `cmd_run` so that Ctrl-C triggers graceful shutdown, saves state as `"interrupted"`, and a second Ctrl-C forces immediate exit with PID cleanup.

## Motivation

Unhandled Ctrl-C during resumed loops bypasses graceful shutdown, leaving state unsaved as "interrupted" and leaving subprocesses running. This inconsistency between `cmd_run` and `cmd_resume` erodes user trust in the lifecycle management system and makes cleanup harder for long-running loops.

## Steps to Reproduce

1. Run a long-running loop that saves `"running"` state
2. Interrupt it (or wait for `"interrupted"` status)
3. Run `ll-loop resume <loop>`
4. Press Ctrl-C mid-execution
5. Observe: `KeyboardInterrupt` propagates without calling `executor.request_shutdown()`

## Root Cause

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Anchor**: `in function cmd_resume()`
- **Cause**: The function creates a `PersistentExecutor` and calls `resume()` directly without registering signal handlers. The `_loop_signal_handler` and related module-level variables (`_loop_shutdown_requested`, `_loop_executor`) are defined in `run.py` and not imported or replicated in `lifecycle.py`.

## Proposed Solution

Import or replicate the signal handler registration pattern from `cmd_run` into `cmd_resume`. Before calling `executor.resume()`, register `_loop_signal_handler` on `SIGINT` and `SIGTERM`. Consider extracting the signal handler setup into a shared helper in `_helpers.py` to avoid duplicating the pattern.

## Implementation Steps

1. Extract signal handler setup from `run.py` into a shared helper in `_helpers.py`
2. Call the shared helper in both `cmd_run` and `cmd_resume` before executing
3. Add test coverage for Ctrl-C during resumed loops

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/lifecycle.py` — add signal handler registration to `cmd_resume()`
- `scripts/little_loops/cli/loop/run.py` — optionally extract `_loop_signal_handler` into shared helper

### Dependent Files (Callers/Importers)
- N/A — signal handler registration is internal to command execution

### Similar Patterns
- `scripts/little_loops/cli/loop/run.py:148-151` — `cmd_run` signal handler registration pattern

### Tests
- `scripts/tests/` — add test for graceful shutdown during resumed loops

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 - User-facing bug affecting loop lifecycle reliability during resume
- **Effort**: Small - Signal handler code already exists in `run.py`, just needs to be shared
- **Risk**: Low - Well-tested pattern in `cmd_run`, applying same pattern to `cmd_resume`
- **Breaking Change**: No

## Labels

`bug`, `ll-loop`, `lifecycle`

## Session Log
- `/ll:confidence-check` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96debe7befc6b.jsonl` — readiness: 100/100 PROCEED, outcome: 86/100 HIGH CONFIDENCE
- `/ll:format-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96debe7befc6b.jsonl` — Added Motivation, Integration Map sections (v2.0 alignment); added confidence_score and outcome_confidence to frontmatter
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — VALID: `cmd_resume` at `lifecycle.py:138-188` confirmed; no signal handler registration before `executor.resume()`; `_loop_signal_handler` confirmed in `run.py:150-151`

---

## Status

**Open** | Created: 2026-03-06 | Priority: P2
