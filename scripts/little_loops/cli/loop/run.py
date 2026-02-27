"""ll-loop run subcommand."""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path
from types import FrameType
from typing import Any

from little_loops.cli.loop._helpers import (
    print_execution_plan,
    resolve_loop_path,
    run_background,
    run_foreground,
)
from little_loops.logger import Logger

# Module-level shutdown state for signal handling
_loop_shutdown_requested: bool = False
_loop_executor: Any = None
_loop_pid_file: Path | None = None


def _loop_signal_handler(signum: int, frame: FrameType | None) -> None:
    """Handle shutdown signals gracefully for ll-loop.

    First signal: Set shutdown flag for graceful exit after current state.
    Second signal: Force immediate exit.
    """
    global _loop_shutdown_requested
    if _loop_shutdown_requested:
        # Second signal - force exit
        if _loop_pid_file is not None:
            _loop_pid_file.unlink(missing_ok=True)
        print("\nForce shutdown requested", file=sys.stderr)
        sys.exit(1)
    _loop_shutdown_requested = True
    print("\nShutdown requested, will exit after current state...", file=sys.stderr)
    if _loop_executor is not None:
        _loop_executor.request_shutdown()


def cmd_run(
    loop_name: str,
    args: argparse.Namespace,
    loops_dir: Path,
    logger: Logger,
) -> int:
    """Run a loop."""
    import yaml

    from little_loops.fsm.compilers import compile_paradigm
    from little_loops.fsm.concurrency import LockManager
    from little_loops.fsm.persistence import PersistentExecutor
    from little_loops.fsm.validation import load_and_validate

    global _loop_shutdown_requested, _loop_executor, _loop_pid_file

    try:
        path = resolve_loop_path(loop_name, loops_dir)

        # Load the file to check format
        with open(path) as f:
            spec = yaml.safe_load(f)

        # Auto-compile if it's a paradigm file (has 'paradigm' but no 'initial')
        if "paradigm" in spec and "initial" not in spec:
            logger.info(f"Auto-compiling paradigm file: {path}")
            fsm = compile_paradigm(spec)
        else:
            fsm = load_and_validate(path)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return 1

    # Apply overrides
    if args.max_iterations:
        fsm.max_iterations = args.max_iterations
    if args.no_llm:
        fsm.llm.enabled = False
    if args.llm_model:
        fsm.llm.model = args.llm_model

    # Dry run
    if args.dry_run:
        print_execution_plan(fsm)
        return 0

    # Background mode: spawn detached process and return
    if getattr(args, "background", False):
        return run_background(loop_name, args, loops_dir)

    # If running as foreground-internal (spawned by --background), register PID cleanup
    if getattr(args, "foreground_internal", False):
        import atexit

        running_dir = loops_dir / ".running"
        pid_file = running_dir / f"{loop_name}.pid"
        _loop_pid_file = pid_file

        def _cleanup_pid() -> None:
            pid_file.unlink(missing_ok=True)

        atexit.register(_cleanup_pid)

    # Scope-based locking
    lock_manager = LockManager(loops_dir)
    scope = fsm.scope or ["."]

    if not lock_manager.acquire(fsm.name, scope):
        conflict = lock_manager.find_conflict(scope)
        if conflict and getattr(args, "queue", False):
            logger.info(f"Waiting for conflicting loop '{conflict.loop_name}' to finish...")
            if not lock_manager.wait_for_scope(scope, timeout=3600):
                logger.error("Timeout waiting for scope to become available")
                return 1
            # Re-acquire after waiting
            if not lock_manager.acquire(fsm.name, scope):
                logger.error("Failed to acquire lock after waiting")
                return 1
        elif conflict:
            logger.error(f"Scope conflict with running loop: {conflict.loop_name}")
            logger.info(f"  Conflicting scope: {conflict.scope}")
            logger.info("  Use --queue to wait for it to finish")
            return 1
        else:
            # Unexpected: find_conflict returned None but acquire failed
            logger.error("Failed to acquire scope lock (unknown reason)")
            return 1

    try:
        executor = PersistentExecutor(fsm, loops_dir=loops_dir)

        # Register signal handlers for graceful shutdown
        _loop_shutdown_requested = False
        _loop_executor = executor
        signal.signal(signal.SIGINT, _loop_signal_handler)
        signal.signal(signal.SIGTERM, _loop_signal_handler)

        return run_foreground(executor, fsm, args)
    finally:
        lock_manager.release(fsm.name)
