---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# FEAT-431: Background/daemon mode for loop execution

## Summary

The `ll-loop run` CLI already accepts a `--background` flag but logs a warning that it's not implemented and falls back to foreground execution. Implement daemon mode so FSM loops can run detached from the terminal.

## Current Behavior

```python
if getattr(args, "background", False):
    logger.warning("Background mode not yet implemented, running in foreground")
```

The `--background` flag is accepted but does nothing useful.

## Expected Behavior

`ll-loop run <loop> --background` detaches the loop process from the terminal, writes PID to a file for later management, and redirects output to a log file. Users can check status and stop daemon loops via `ll-loop status` and `ll-loop stop`.

## Motivation

Long-running FSM loops (CI watchers, continuous deployment, periodic scans) need to run detached from the terminal. Users currently have to use `nohup` or `screen`/`tmux` as workarounds. Native daemon support makes the workflow self-contained.

## Use Case

A developer starts a continuous integration loop (`ll-loop run ci-watcher --background`) that monitors for new issues and processes them automatically. They close their terminal and the loop continues running. Later, they check status with `ll-loop status ci-watcher` and stop it with `ll-loop stop ci-watcher`.

## Acceptance Criteria

- `--background` flag detaches process from terminal
- PID file written to `.loops/.running/<name>.pid`
- stdout/stderr redirected to `.loops/.running/<name>.log`
- `ll-loop status <name>` shows running state and PID
- `ll-loop stop <name>` sends SIGTERM to background loop
- Graceful shutdown on SIGTERM (saves state before exit)

## Proposed Solution

Use `os.fork()` + `os.setsid()` for Unix daemon pattern, or `subprocess.Popen` with detached process group. Write PID to `.loops/.running/<name>.pid`. Add `status` and `stop` subcommands.

```python
def daemonize(loop_name: str, args: Namespace) -> None:
    pid = os.fork()
    if pid > 0:
        # Parent: write PID and exit
        pid_file = Path(f".loops/.running/{loop_name}.pid")
        pid_file.write_text(str(pid))
        print(f"Loop '{loop_name}' started in background (PID: {pid})")
        return
    # Child: setsid, redirect IO, run loop
    os.setsid()
    # ... redirect stdout/stderr to log file ...
    run_loop(loop_name, args)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py` — implement daemon mode
- `scripts/little_loops/cli/loop/__init__.py` — add status/stop subcommands

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/engine.py` — needs graceful shutdown handler

### Similar Patterns
- N/A

### Tests
- `scripts/tests/` — add tests for daemon lifecycle (start, status, stop)

### Documentation
- Update CLI help text

### Configuration
- N/A

## Implementation Steps

1. Implement daemonize function with fork/setsid
2. Add PID file and log file management
3. Add `ll-loop status` and `ll-loop stop` subcommands
4. Add SIGTERM handler in engine for graceful shutdown
5. Test daemon lifecycle

## Impact

- **Priority**: P3 - Enables common use case, flag already exists
- **Effort**: Medium - Daemon management, signal handling, new subcommands
- **Risk**: Medium - Process management is tricky, needs careful testing
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `fsm`, `cli`

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`

---

**Open** | Created: 2026-02-15 | Priority: P3
