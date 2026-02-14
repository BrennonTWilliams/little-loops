"""ll-loop run subcommand."""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.cli.loop._helpers import (
    print_execution_plan,
    resolve_loop_path,
    run_foreground,
)
from little_loops.logger import Logger


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

    # Background mode not implemented
    if getattr(args, "background", False):
        logger.warning("Background mode not yet implemented, running in foreground")

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
        return run_foreground(executor, fsm, args)
    finally:
        lock_manager.release(fsm.name)
