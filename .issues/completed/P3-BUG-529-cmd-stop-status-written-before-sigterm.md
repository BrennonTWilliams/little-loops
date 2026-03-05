---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
confidence_score: 95
outcome_confidence: 93
---

# BUG-529: `cmd_stop` Writes "interrupted" Status Before SIGTERM — State Can Diverge from Reality

## Summary

`cmd_stop` writes `status = "interrupted"` to the state file *before* sending SIGTERM to the background process. If the process is not running (already exited), this overwrites the process's own final status (e.g., `"terminal"` or `"max_iterations"`) with `"interrupted"`. If the process ignores SIGTERM (e.g., while running a long inner subprocess), it remains running with a state file that says it is stopped.

## Location

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Line(s)**: 93–113 (at scan commit: 47c81c8)
- **Anchor**: `in function cmd_stop()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/cli/loop/lifecycle.py#L93-L113)
- **Code**:
```python
state.status = "interrupted"
persistence.save_state(state)          # written BEFORE signal

pid = _read_pid_file(pid_file)
if pid is not None:
    if _process_alive(pid):
        os.kill(pid, signal.SIGTERM)   # signal sent AFTER write
```

## Current Behavior

1. State file written with `"interrupted"` before SIGTERM is sent
2. If process is already dead: its actual final status (e.g., `"terminal"`) is overwritten with `"interrupted"`
3. If process is running a non-interruptible inner subprocess: state says `"interrupted"` but process continues
4. `ll-loop status` and `ll-loop history` display incorrect state

## Expected Behavior

- If process is already dead: `cmd_stop` detects it and reports "loop not running" without overwriting state
- If process is alive: send SIGTERM, then wait briefly and update state only if process exits cleanly; otherwise report "stop signal sent, waiting for process to exit"

## Motivation

`ll-loop stop` is used in automation pipelines (e.g., `ll-sprint`) to cleanly terminate loops. A state file incorrectly set to `"interrupted"` causes downstream commands (e.g., `ll-auto`) that check loop state to misclassify the outcome.

## Steps to Reproduce

1. Run `ll-loop run slow-loop` (a loop with a long-running shell action)
2. Wait for the loop to complete naturally
3. Immediately after (race window): run `ll-loop stop slow-loop`
4. Observe: `ll-loop status slow-loop` shows `"interrupted"` instead of `"terminal"`

Or: run `ll-loop stop` against a loop running a `sleep 60` action; the state shows `"interrupted"` but `ll-loop status` shows the PID still alive.

## Actual Behavior

State file shows `"interrupted"` regardless of whether the process actually stopped.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Anchor**: `in function cmd_stop()`
- **Cause**: Premature state write before PID check and signal delivery; no check if process is already finished before overwriting state

## Proposed Solution

Restructure `cmd_stop` to:
1. Read PID file
2. If no PID / process not alive → report "loop not running" and return without modifying state
3. If alive → send SIGTERM
4. Optionally wait briefly (e.g., 2s) for process to exit, then verify state was written by process itself
5. Only write `"interrupted"` if process does not exit within the wait window

```python
pid = _read_pid_file(pid_file)
if pid is None or not _process_alive(pid):
    print(f"{loop_name} is not running")
    return 0

os.kill(pid, signal.SIGTERM)
# Optionally wait for process to self-update state
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_stop()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — routes `stop` subcommand to `cmd_stop()`

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_cli_loop_background.py` — add test: stop already-finished loop; verify state unchanged

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Move PID read and `_process_alive` check to *before* the state write
2. Return early if process is not alive (without modifying state)
3. Only write `"interrupted"` if process is confirmed alive at time of signal
4. Add test for stopping an already-completed loop

## Impact

- **Priority**: P3 — Incorrect state metadata; affects automation pipelines that inspect loop status
- **Effort**: Small — Re-ordering a few lines in `cmd_stop()`
- **Risk**: Low — Behavioral change only in edge case (process already dead when stop called)
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | CLI interface — `ll-loop stop` subcommand (line 1381) |
| `docs/guides/LOOPS_GUIDE.md` | Loop lifecycle and stop behavior (line 191) |

## Labels

`bug`, `ll-loop`, `lifecycle`, `scan-codebase`

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — Linked `docs/generalized-fsm-loop.md`; `test_cli_loop_lifecycle.py:76` (TestCmdStop) as test class
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`

---

## Blocks

- FEAT-543

---

**Completed** | Created: 2026-03-03 | Resolved: 2026-03-04 | Priority: P3

---

## Resolution

**Status**: Fixed

### Changes Made

- **`scripts/little_loops/cli/loop/lifecycle.py`** — Restructured `cmd_stop()` to check PID liveness *before* writing state:
  - If process is alive: send SIGTERM, then write `"interrupted"` to state
  - If process is dead (stale PID): clean up PID file only — do **not** overwrite state
  - If no PID file: write `"interrupted"` to state (no background process tracked)

- **`scripts/tests/test_cli_loop_background.py`** — Added `test_stop_dead_process_preserves_state` to `TestCmdStopWithPid`: verifies `save_state` is NOT called when a stale PID is found

---

## Session Log (continued)

- `/ll:manage-issue` — 2026-03-04 — fix applied
- `/ll:ready-issue` — 2026-03-04T00:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a084cb6b-96ce-430d-8850-1332de4f08a2.jsonl` — Fix confirmed in code; moving to completed/

---

## Tradeoff Review Note

**Reviewed**: 2026-03-03 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | LOW |
| Complexity added | MEDIUM |
| Technical debt risk | HIGH |
| Maintenance overhead | LOW |

### Recommendation
Update first — The edge-case timing semantics need to be specified carefully before implementation. HIGH tech debt risk from ordering-dependent logic. Before implementing, define: (1) the exact wait window after SIGTERM, (2) behavior when the process exits between PID check and SIGTERM, and (3) whether to poll for process exit or return immediately with "stop signal sent." A more detailed implementation plan addressing these timing semantics will reduce regression risk.
