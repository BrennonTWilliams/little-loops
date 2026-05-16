---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# FEAT-255: Implement background/daemon mode for ll-loop run

## Summary

The `ll-loop run` command advertises a `--background`/`-b` flag but the feature is completely unimplemented. When used, it logs a warning and falls through to foreground execution. The FSM loop system supports `maintain=True` for long-running loops that would benefit from daemonization with PID tracking, log redirection, and process management.

## Location

- **File**: `scripts/little_loops/cli.py`
- **Line(s)**: 568, 793-795 (at scan commit: a8f4144)
- **Anchor**: `in function cmd_run, --background argument`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/cli.py#L568)
- **Code**:
```python
# Argument definition
run_parser.add_argument(
    "--background", "-b", action="store_true", help="Run as daemon (not yet implemented)"
)

# Usage (lines 793-795)
if getattr(args, "background", False):
    logger.warning("Background mode not yet implemented, running in foreground")
```

## Current Behavior

Flag is accepted but ignored with a warning.

## Expected Behavior

Background mode should daemonize the loop process with PID file tracking, log file redirection, and ability to check status/stop via `ll-loop status` and `ll-loop stop`.

## Proposed Solution

Implement process daemonization using `os.fork()` or `subprocess.Popen` with `start_new_session=True`, redirect stdout/stderr to a log file under `.ll-loops/logs/`, write a PID file, and add monitoring via existing `ll-loop list` command.

## Impact

- **Severity**: Medium
- **Effort**: Large
- **Risk**: Medium

## Labels

`feature`, `priority-p3`

---

## Status
**Closed (Won't Fix)** | Created: 2026-02-06T03:41:30Z | Closed: 2026-02-05 | Priority: P3

**Closure reason**: YAGNI / over-engineered. Users already have nohup, &, screen, and tmux for backgrounding. The complexity of proper daemon management (PID files, orphan cleanup, crash recovery, signal handling) far outweighs the convenience.
