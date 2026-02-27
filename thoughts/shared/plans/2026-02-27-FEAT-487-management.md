# Implementation Plan: FEAT-487 — `ll-loop run --background` daemon mode

## Overview

Implement background/daemon mode for `ll-loop run` using `subprocess.Popen(start_new_session=True)` to re-exec the loop as a detached process. Enhance `cmd_stop` to send SIGTERM via PID file, enhance `cmd_status` to show PID liveness, and register signal handlers for graceful shutdown.

## Design Decisions

1. **Detach strategy**: Use `subprocess.Popen(start_new_session=True)` to re-exec `ll-loop run <name> --foreground-internal`. This avoids `os.fork()` (Unix-only, per FEAT-431 closure). The parent writes PID, prints confirmation, exits. The child redirects stdout/stderr to a log file and runs normally.

2. **Internal flag**: Add `--foreground-internal` hidden argument. When `--background` is passed, re-exec with this flag replacing `--background`. When `--foreground-internal` is present, redirect stdio to log file and run in foreground (skip re-daemonization).

3. **PID file location**: `.loops/.running/<name>.pid` — co-located with existing `.state.json`, `.events.jsonl`, and `.lock` files.

4. **Log file location**: `.loops/.running/<name>.log` — stdout/stderr of the daemonized process.

5. **Signal handling**: Follow the sprint runner pattern (module-level flag + double-signal). Register SIGTERM/SIGINT handlers in `cmd_run()` that call `executor.request_shutdown()`. This benefits both foreground and background execution.

6. **PID file cleanup**: Use `atexit` handler + signal handler cleanup. The signal handler calls `request_shutdown()` AND schedules PID cleanup. The `atexit` handler removes the PID file on normal exit.

## Implementation Phases

### Phase 1: Signal Handler Registration in `run.py`

**File**: `scripts/little_loops/cli/loop/run.py`

Add module-level signal handler following the sprint runner pattern:

```python
import signal
import sys
from types import FrameType

# Module-level shutdown state for signal handling
_loop_shutdown_requested: bool = False
_loop_executor: Any = None

def _loop_signal_handler(signum: int, frame: FrameType | None) -> None:
    global _loop_shutdown_requested
    if _loop_shutdown_requested:
        print("\nForce shutdown requested", file=sys.stderr)
        sys.exit(1)
    _loop_shutdown_requested = True
    print("\nShutdown requested, will exit after current state...", file=sys.stderr)
    if _loop_executor is not None:
        _loop_executor.request_shutdown()
```

In `cmd_run()`, register before execution:
```python
global _loop_shutdown_requested, _loop_executor
_loop_shutdown_requested = False
_loop_executor = executor
signal.signal(signal.SIGINT, _loop_signal_handler)
signal.signal(signal.SIGTERM, _loop_signal_handler)
```

### Phase 2: Background Mode in `_helpers.py`

**File**: `scripts/little_loops/cli/loop/_helpers.py`

Add `run_background()` function:

```python
def run_background(loop_name: str, args: argparse.Namespace, loops_dir: Path) -> int:
    """Launch loop as a detached background process."""
    import subprocess

    running_dir = loops_dir / ".running"
    running_dir.mkdir(parents=True, exist_ok=True)

    pid_file = running_dir / f"{loop_name}.pid"
    log_file = running_dir / f"{loop_name}.log"

    # Build re-exec command: replace --background with --foreground-internal
    cmd = [sys.executable, "-m", "little_loops.cli", "loop", "run", loop_name, "--foreground-internal"]
    # Forward relevant args
    if getattr(args, "max_iterations", None):
        cmd.extend(["--max-iterations", str(args.max_iterations)])
    if getattr(args, "no_llm", False):
        cmd.append("--no-llm")
    if getattr(args, "llm_model", None):
        cmd.extend(["--llm-model", args.llm_model])
    if getattr(args, "quiet", False):
        cmd.append("--quiet")
    if getattr(args, "queue", False):
        cmd.append("--queue")

    log_fh = open(log_file, "w")
    process = subprocess.Popen(
        cmd,
        start_new_session=True,
        stdout=log_fh,
        stderr=log_fh,
        stdin=subprocess.DEVNULL,
    )

    pid_file.write_text(str(process.pid))
    print(f"Loop '{loop_name}' started in background (PID: {process.pid})")
    print(f"  Log: {log_file}")
    print(f"  Status: ll-loop status {loop_name}")
    print(f"  Stop: ll-loop stop {loop_name}")
    return 0
```

### Phase 3: Update `cmd_run()` to Dispatch Background Mode

**File**: `scripts/little_loops/cli/loop/run.py`

Replace the background stub (lines 63-65) with:
```python
if getattr(args, "background", False):
    return run_background(loop_name, args, loops_dir)
```

This must happen BEFORE lock acquisition (the child process will acquire its own lock).

Add handling for `--foreground-internal`: when present, redirect stdout/stderr to the log file and write PID file. Actually — simpler approach: the parent writes the PID and opens the log file. The child just inherits the redirected file descriptors from `Popen`. So `--foreground-internal` just needs to suppress re-daemonization and register PID file cleanup.

**Revised approach**:
- `--foreground-internal` flag means "I am the daemon child". It writes PID file cleanup via atexit.
- The parent (`--background`) opens the log file, spawns the child with stdout/stderr redirected, writes the PID file, and returns.
- Wait — the parent writes the PID and the log redirect. The child doesn't need to know about `--foreground-internal` for stdio since `Popen` handles that. But the child needs to clean up the PID file on exit.

**Final approach**:
- Parent (`--background`): spawns child via `Popen(start_new_session=True, stdout=log_fh, stderr=log_fh)`, writes `.pid` file, returns 0
- Child: runs as a normal `ll-loop run <name>` (via `--foreground-internal` which just means "skip background check, register atexit PID cleanup")
- `--foreground-internal` handler in `cmd_run()`: register `atexit` to clean up PID file, then continue to normal execution

### Phase 4: PID File Cleanup

**File**: `scripts/little_loops/cli/loop/run.py`

When `--foreground-internal` is detected:
```python
if getattr(args, "foreground_internal", False):
    import atexit
    pid_file = loops_dir / ".running" / f"{loop_name}.pid"
    def _cleanup_pid():
        pid_file.unlink(missing_ok=True)
    atexit.register(_cleanup_pid)
```

Also in the signal handler, clean up PID file:
```python
def _loop_signal_handler(signum, frame):
    global _loop_shutdown_requested
    if _loop_shutdown_requested:
        _cleanup_pid_file()  # Clean up on force exit too
        sys.exit(1)
    ...
```

### Phase 5: Enhance `cmd_stop()` in `lifecycle.py`

**File**: `scripts/little_loops/cli/loop/lifecycle.py`

After the existing state-file mutation, add PID-based stop:

```python
# Try PID-based stop (for background processes)
running_dir = loops_dir / ".running"
pid_file = running_dir / f"{loop_name}.pid"
if pid_file.exists():
    try:
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)  # Check if alive
            os.kill(pid, signal.SIGTERM)  # Send SIGTERM
            logger.success(f"Sent SIGTERM to {loop_name} (PID: {pid})")
        except OSError:
            logger.info(f"Process {pid} not running, cleaning up PID file")
            pid_file.unlink(missing_ok=True)
    except ValueError:
        logger.warning(f"Invalid PID file: {pid_file}")
        pid_file.unlink(missing_ok=True)
```

### Phase 6: Enhance `cmd_status()` in `lifecycle.py`

**File**: `scripts/little_loops/cli/loop/lifecycle.py`

After the existing state display, add PID info:

```python
# Show PID info if available
running_dir = loops_dir / ".running"
pid_file = running_dir / f"{loop_name}.pid"
if pid_file.exists():
    try:
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)
            print(f"PID: {pid} (running)")
        except OSError:
            print(f"PID: {pid} (not running - stale PID file)")
    except ValueError:
        pass
```

### Phase 7: Update `__init__.py` Argument Parser

**File**: `scripts/little_loops/cli/loop/__init__.py`

1. Update `--background` help text: remove "(not yet implemented)"
2. Add hidden `--foreground-internal` argument

```python
run_parser.add_argument(
    "--background", "-b", action="store_true", help="Run as background daemon"
)
run_parser.add_argument(
    "--foreground-internal", action="store_true", help=argparse.SUPPRESS,
)
```

### Phase 8: Tests

**File**: `scripts/tests/test_cli_loop_background.py` (new file)

Tests:
1. **Signal handler**: First signal sets flag + calls `request_shutdown()`, second forces exit
2. **`run_background()`**: Mocks `subprocess.Popen`, verifies `start_new_session=True`, PID file written, log file opened
3. **`cmd_stop` with PID file**: Verifies `os.kill(pid, SIGTERM)` called when PID file exists
4. **`cmd_stop` with stale PID**: Verifies cleanup when process not alive
5. **`cmd_status` with PID info**: Verifies PID and liveness displayed
6. **`cmd_run` dispatches to background**: Verifies `--background` calls `run_background()`
7. **`--foreground-internal` registers atexit**: Verifies PID cleanup registered

## Success Criteria

- [ ] `ll-loop run <name> --background` spawns detached process and returns immediately
- [ ] PID file written to `.loops/.running/<name>.pid`
- [ ] stdout/stderr redirected to `.loops/.running/<name>.log`
- [ ] `ll-loop status <name>` shows PID and liveness
- [ ] `ll-loop stop <name>` sends SIGTERM via PID file
- [ ] SIGTERM/SIGINT handler calls `executor.request_shutdown()`
- [ ] PID file cleaned up on exit (normal, signal, atexit)
- [ ] All tests pass
- [ ] Type checks pass
- [ ] Lint passes

## Files Modified

| File | Change |
|------|--------|
| `scripts/little_loops/cli/loop/run.py` | Signal handler, background dispatch, foreground-internal handling |
| `scripts/little_loops/cli/loop/_helpers.py` | `run_background()` function |
| `scripts/little_loops/cli/loop/lifecycle.py` | PID-based stop and status |
| `scripts/little_loops/cli/loop/__init__.py` | Update `--background` help, add `--foreground-internal` |
| `scripts/tests/test_cli_loop_background.py` | New test file for background mode |
