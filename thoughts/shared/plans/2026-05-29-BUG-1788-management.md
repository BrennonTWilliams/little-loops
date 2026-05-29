# BUG-1788: Nested loop names crash background runs - Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P2-BUG-1788-nested-loop-names-crash-background-runs.md
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

`_make_instance_id()` preserves `/` in loop names, producing instance IDs like `generated/inkscape-task-20260529T130816`. When these are used to construct file paths under `.loops/.running/`, the intermediate directory (e.g., `generated/`) doesn't exist — only `.running/` is created. The `open()` call crashes with `FileNotFoundError`.

### Crash Sites (verified against current code)
1. `_helpers.py:1032` — `open(log_file, "w")` in `run_background()`
2. `_helpers.py:1041` — `pid_file.write_text(...)` in `run_background()`
3. `_helpers.py:1092` — `open(_log_path, "w")` in `run_foreground()`
4. `run.py:255` — `pid_file.write_text(...)` in `cmd_run()` foreground path
5. `concurrency.py:139` — `open(lock_file, "w")` in `LockManager.acquire()`
6. `lifecycle.py:423` — `pid_file.write_text(...)` in `cmd_resume()`

## Solution Approach

Add `parent.mkdir(parents=True, exist_ok=True)` before each write site. This matches the canonical pattern from `file_utils.py:47,76` and the BUG-438 fix in `worktree_utils.py:89`.

## Implementation Phases

### Phase 0: Write Tests — Red (TDD)
- Add nested-name tests in test_cli_loop_background.py (TestRunBackground)
- Verify tests fail with FileNotFoundError against current code

### Phase 1: Fix write sites
- `_helpers.py`: `run_background()` — one `mkdir` before log/pid writes
- `_helpers.py`: `run_foreground()` — one `mkdir` before log write
- `run.py`: `cmd_run()` — one `mkdir` before pid write
- `concurrency.py`: `LockManager.acquire()` — one `mkdir` before lock write
- `lifecycle.py`: `cmd_resume()` — one `mkdir` before pid write

### Phase 2: Verify tests pass (Green)

## Testing Strategy
- Add nested name test to existing `TestRunBackground` class
- Verify with `python -m pytest scripts/tests/test_cli_loop_background.py -v`
