---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
---

# FEAT-487: Implement `ll-loop run --background` daemon mode

## Summary

The `--background` / `-b` flag is wired into the `ll-loop run` CLI parser with help text `"Run as daemon (not yet implemented)"`. When passed, it emits a warning and falls through to foreground execution. The daemon/background execution path has no implementation.

## Current Behavior

```python
# cli/loop/__init__.py:89
run_parser.add_argument(
    "--background", "-b", action="store_true", help="Run as daemon (not yet implemented)"
)

# cli/loop/run.py:63-65
if getattr(args, "background", False):
    logger.warning("Background mode not yet implemented, running in foreground")
```

## Expected Behavior

When `--background` is passed, the loop process detaches from the terminal, writes a PID file for management, redirects stdout/stderr to a log file, and continues execution as a daemon. Status can be checked via `ll-loop status`.

## Motivation

Long-running loops (e.g., continuous scan-and-fix loops) benefit from background execution so users can continue other work in the terminal. The flag is already declared in the CLI, so users expect it to work.

## Use Case

A developer starts a long-running scan loop: `ll-loop run continuous-scan --background`. The process detaches, writing its PID to `.loops/pids/continuous-scan.pid`. The developer checks status with `ll-loop status continuous-scan` and stops it with `ll-loop stop continuous-scan`.

## Acceptance Criteria

- [ ] `ll-loop run <name> --background` detaches the process from the terminal
- [ ] PID file written to `.loops/pids/<name>.pid` for management
- [ ] stdout/stderr redirected to `.loops/logs/<name>.log`
- [ ] `ll-loop status` shows running background loops
- [ ] `ll-loop stop <name>` sends SIGTERM to the background process
- [ ] Clean shutdown on SIGTERM (existing signal handling)
- [ ] PID file cleaned up on exit

## Proposed Solution

Use Python's `daemon` pattern (or `subprocess.Popen` with `start_new_session=True`) to detach the process. Write PID to `.loops/pids/` directory. Redirect output to `.loops/logs/`. Add `status` and `stop` subcommands to manage background loops.

## API/Interface

```bash
ll-loop run <name> --background   # Detach as daemon; writes PID to .loops/pids/<name>.pid
ll-loop stop <name>               # Send SIGTERM to background loop; removes PID file
ll-loop status [<name>]           # Show running background loops (enhanced from current)
```

## Implementation Steps

1. Create `.loops/pids/` and `.loops/logs/` directories
2. Implement process detachment in `cmd_run` when `--background` is set
3. Write PID file and redirect stdout/stderr
4. Add `stop` subcommand to send SIGTERM and clean up PID file
5. Enhance `status` subcommand to show running background loops
6. Add tests for daemon lifecycle

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py` — implement background mode
- `scripts/little_loops/cli/loop/__init__.py` — add `stop` subcommand parser
- `scripts/little_loops/cli/loop/lifecycle.py` — add `cmd_stop` implementation

### Dependent Files (Callers/Importers)
- N/A — new feature

### Similar Patterns
- N/A

### Tests
- `scripts/tests/` — add tests for daemon start/stop/status

### Documentation
- Update CLI help text to remove "(not yet implemented)"

### Configuration
- N/A

## Impact

- **Priority**: P3 — Completing a declared but unimplemented feature
- **Effort**: Large — Daemon management, PID files, signal handling
- **Risk**: Medium — Process management is platform-sensitive
- **Breaking Change**: No

## Labels

`feature`, `cli`, `loops`, `daemon`, `auto-generated`

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`
- `/ll:format-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a32a1e4-137e-4580-a6db-a31be30ec313.jsonl`
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Issue is well-specified with specific file references and daemon pattern; no knowledge gaps identified

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3
