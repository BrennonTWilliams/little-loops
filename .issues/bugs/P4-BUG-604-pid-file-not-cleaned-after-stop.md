---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
confidence_score: 98
outcome_confidence: 92
---

# BUG-604: PID file not cleaned up after SIGTERM/SIGKILL stop path

## Summary

After `cmd_stop` sends SIGTERM (and optionally SIGKILL) to a loop process, it saves state as `"interrupted"` but never removes the PID file. The `pid_file.unlink(missing_ok=True)` call only executes in the "process already dead" branch, leaving stale PID files after successful stops.

## Location

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Line(s)**: 111-124 (at scan commit: c010880)
- **Anchor**: `in function cmd_stop()`, SIGTERM wait loop
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/c010880ecfc0941e7a5a59cc071248a4b1cbc557/scripts/little_loops/cli/loop/lifecycle.py#L111-L124)
- **Code**:
```python
os.kill(pid, signal.SIGTERM)
for _ in range(10):
    time.sleep(1)
    if not _process_alive(pid):
        break
else:
    try:
        os.kill(pid, signal.SIGKILL)
        logger.warning(f"Sent SIGKILL to {loop_name} (PID: {pid})")
    except OSError:
        pass
state.status = "interrupted"
persistence.save_state(state)
logger.success(f"Stopped {loop_name} (PID: {pid})")
# pid_file.unlink() is NOT called here
```

## Current Behavior

After stopping a loop, the PID file remains on disk. Subsequent `ll-loop status` shows "not running - stale PID file".

## Expected Behavior

The PID file should be removed after successfully stopping the process.

## Steps to Reproduce

1. Run a loop in background mode
2. Run `ll-loop stop <loop>`
3. Check `.loops/.running/<loop>.pid` — file still exists
4. Run `ll-loop status <loop>` — shows stale PID message instead of clean "stopped" status

## Root Cause

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Anchor**: `in function cmd_stop()`, SIGTERM/SIGKILL path
- **Cause**: `pid_file.unlink(missing_ok=True)` was only added to the "process already dead" early-exit branch (line 128) and not to the SIGTERM/SIGKILL success path. The two branches handle the same logical outcome (process is now stopped) but only one performs cleanup.

## Motivation

Stale PID files after a successful stop degrade the user experience and reliability of `ll-loop status`:

- **Misleading status output**: `ll-loop status <loop>` reports "not running - stale PID file" instead of a clean stopped state after every normal `stop` operation
- **Branch inconsistency**: The "process already dead" branch correctly cleans up the PID file; the SIGTERM/SIGKILL success path does not — same outcome, different cleanup behavior
- **Accumulation**: Long-running development cycles with frequent stop/start accumulate stale files in `.loops/.running/`

## Proposed Solution

Add `pid_file.unlink(missing_ok=True)` after `persistence.save_state(state)` in the SIGTERM/SIGKILL path.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/lifecycle.py` — add `pid_file.unlink(missing_ok=True)` after `persistence.save_state(state)` at approximately line 124

### Dependent Files (Callers/Importers)
- N/A — `cmd_stop` is a terminal command; PID file cleanup is internal

### Similar Patterns
- `scripts/little_loops/cli/loop/lifecycle.py:128` — "process already dead" branch already calls `pid_file.unlink(missing_ok=True)`

### Tests
- `scripts/tests/` — add test asserting PID file is absent after `cmd_stop` when process responds to SIGTERM

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Open `scripts/little_loops/cli/loop/lifecycle.py`
2. After `persistence.save_state(state)` in the SIGTERM/SIGKILL path (around line 124), add `pid_file.unlink(missing_ok=True)`
3. Verify the "process already dead" branch at line 128 still has its own `unlink` call
4. Run existing tests to confirm no regressions

## Impact

- **Priority**: P4 - Cosmetic issue, stale files don't cause functional problems
- **Effort**: Small - One-line addition
- **Risk**: Low - Cleanup operation
- **Breaking Change**: No

## Labels

`bug`, `ll-loop`, `lifecycle`

## Session Log
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — VALID: SIGTERM path at `lifecycle.py:110-124` confirmed; no `pid_file.unlink()` after `persistence.save_state(state)`; unlink only in "process already dead" branch at line 128
- `/ll:format-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — v2.0 format: added Root Cause, Motivation, Integration Map, Implementation Steps; added confidence_score and outcome_confidence to frontmatter; added Status footer
- `/ll:confidence-check` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — Readiness: 98/100 PROCEED; Outcome: 92/100 HIGH CONFIDENCE

---

## Status

**Open** | Created: 2026-03-06 | Priority: P4
