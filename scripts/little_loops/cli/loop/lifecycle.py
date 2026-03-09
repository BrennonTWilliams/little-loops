"""ll-loop lifecycle subcommands: status, stop, resume."""

from __future__ import annotations

import argparse
import atexit
import os
import signal
import time
from pathlib import Path

from little_loops.cli.loop._helpers import (
    EXIT_CODES,
    load_loop,
    register_loop_signal_handlers,
    run_background,
)
from little_loops.fsm.concurrency import _process_alive
from little_loops.logger import Logger


def _read_pid_file(pid_file: Path) -> int | None:
    """Read and validate a PID file.

    Returns:
        The PID as an integer, or None if the file doesn't exist or is invalid.
    """
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return None


def cmd_status(
    loop_name: str,
    loops_dir: Path,
    logger: Logger,
) -> int:
    """Show loop status."""
    from little_loops.fsm.persistence import StatePersistence

    persistence = StatePersistence(loop_name, loops_dir)
    state = persistence.load_state()

    if state is None:
        logger.error(f"No state found for: {loop_name}")
        return 1

    print(f"Loop: {state.loop_name}")
    print(f"Status: {state.status}")
    print(f"Current state: {state.current_state}")
    print(f"Iteration: {state.iteration}")
    print(f"Started: {state.started_at}")
    print(f"Updated: {state.updated_at}")

    # Show PID info if available (background mode)
    running_dir = loops_dir / ".running"
    pid_file = running_dir / f"{loop_name}.pid"
    pid = _read_pid_file(pid_file)
    if pid is not None:
        if _process_alive(pid):
            print(f"PID: {pid} (running)")
        else:
            print(f"PID: {pid} (not running - stale PID file)")

    if state.continuation_prompt:
        # Show truncated continuation context
        prompt_preview = state.continuation_prompt[:200]
        if len(state.continuation_prompt) > 200:
            prompt_preview += "..."
        print(f"Continuation context: {prompt_preview}")
    return 0


def cmd_stop(
    loop_name: str,
    loops_dir: Path,
    logger: Logger,
) -> int:
    """Stop a running loop."""
    from little_loops.fsm.persistence import StatePersistence

    persistence = StatePersistence(loop_name, loops_dir)
    state = persistence.load_state()

    if state is None:
        logger.error(f"No state found for: {loop_name}")
        return 1

    if state.status != "running":
        logger.error(f"Loop not running: {loop_name} (status: {state.status})")
        return 1

    # Check PID before modifying state to avoid overwriting the process's own final status.
    # Race condition: process may finish and write its terminal status between
    # cmd_stop's state read and a premature state write.
    running_dir = loops_dir / ".running"
    pid_file = running_dir / f"{loop_name}.pid"
    pid = _read_pid_file(pid_file)
    if pid is not None:
        if _process_alive(pid):
            # Process confirmed alive: send SIGTERM, then wait for exit
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                time.sleep(1)
                if not _process_alive(pid):
                    break
            else:
                # Still alive after grace period: force kill
                try:
                    os.kill(pid, signal.SIGKILL)
                    logger.warning(f"Sent SIGKILL to {loop_name} (PID: {pid})")
                except OSError:
                    pass  # Process exited between poll and kill
            state.status = "interrupted"
            persistence.save_state(state)
            pid_file.unlink(missing_ok=True)
            logger.success(f"Stopped {loop_name} (PID: {pid})")
        else:
            # Process already exited: preserve its final status, only clean up PID file
            logger.info(f"Process {pid} not running, cleaning up PID file")
            pid_file.unlink(missing_ok=True)
    else:
        # No PID file: no background process tracked, update state only
        state.status = "interrupted"
        persistence.save_state(state)
        logger.success(f"Marked {loop_name} as interrupted")

    return 0


def cmd_resume(
    loop_name: str,
    args: argparse.Namespace,
    loops_dir: Path,
    logger: Logger,
) -> int:
    """Resume an interrupted loop."""
    from little_loops.fsm.persistence import PersistentExecutor, StatePersistence

    # Background mode: spawn detached process and return
    if getattr(args, "background", False):
        return run_background(loop_name, args, loops_dir, subcommand="resume")

    # Register PID file for all foreground runs so cmd_stop can send SIGTERM (BUG-639).
    # Background-spawned processes (foreground_internal=True) have their PID written by the
    # parent in run_background(); plain foreground runs must write their own PID here.
    import os

    running_dir = loops_dir / ".running"
    running_dir.mkdir(parents=True, exist_ok=True)
    pid_file = running_dir / f"{loop_name}.pid"
    foreground_pid_file: Path | None = pid_file

    if not getattr(args, "foreground_internal", False):
        pid_file.write_text(str(os.getpid()))

    def _cleanup_pid() -> None:
        pid_file.unlink(missing_ok=True)

    atexit.register(_cleanup_pid)

    try:
        fsm = load_loop(loop_name, loops_dir, logger)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return 1

    for kv in getattr(args, "context", None) or []:
        if "=" not in kv:
            raise SystemExit(f"Invalid --context format: {kv!r} (expected KEY=VALUE)")
        key, _, value = kv.partition("=")
        fsm.context[key.strip()] = value.strip()

    # Check state before resuming to show context
    persistence = StatePersistence(loop_name, loops_dir)
    state = persistence.load_state()
    if state and state.status == "awaiting_continuation":
        print(f"Resuming from context handoff (iteration {state.iteration})...")
        if state.continuation_prompt:
            # Show truncated continuation context
            prompt_preview = state.continuation_prompt[:500]
            if len(state.continuation_prompt) > 500:
                prompt_preview += "..."
            print(f"Context: {prompt_preview}")
            print()

    executor = PersistentExecutor(fsm, loops_dir=loops_dir)

    # Register signal handlers for graceful shutdown (same as cmd_run)
    register_loop_signal_handlers(executor, pid_file=foreground_pid_file)

    result = executor.resume()

    if result is None:
        logger.warning(f"Nothing to resume for: {loop_name}")
        return 1

    duration_sec = result.duration_ms / 1000
    if duration_sec < 60:
        duration_str = f"{duration_sec:.1f}s"
    else:
        minutes = int(duration_sec // 60)
        seconds = duration_sec % 60
        duration_str = f"{minutes}m {seconds:.0f}s"

    logger.success(
        f"Resumed and completed: {result.final_state} "
        f"({result.iterations} iterations, {duration_str})"
    )
    return EXIT_CODES.get(result.terminated_by, 1)
