"""ll-loop run subcommand."""

from __future__ import annotations

import argparse
import atexit
import os
import re
from pathlib import Path

from little_loops.cli.loop._helpers import (
    get_builtin_loops_dir,
    print_execution_plan,
    register_loop_signal_handlers,
    resolve_loop_path,
    run_background,
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
    from little_loops.fsm.concurrency import LockManager
    from little_loops.fsm.persistence import PersistentExecutor
    from little_loops.fsm.validation import load_and_validate

    try:
        if getattr(args, "builtin", False):
            path = get_builtin_loops_dir() / f"{loop_name}.yaml"
            if not path.exists():
                logger.error(f"Built-in loop not found: {loop_name!r}")
                return 1
        else:
            path = resolve_loop_path(loop_name, loops_dir)
        fsm, _ = load_and_validate(path)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return 1

    # Apply overrides
    if args.max_iterations:
        fsm.max_iterations = args.max_iterations
    if args.delay is not None:
        fsm.backoff = args.delay
    if args.no_llm:
        fsm.llm.enabled = False
    if args.llm_model:
        fsm.llm.model = args.llm_model
    # Inject positional input arg before --context so --context can override
    if getattr(args, "input", None) is not None:
        fsm.context[fsm.input_key] = args.input
    for kv in getattr(args, "context", None) or []:
        if "=" not in kv:
            raise SystemExit(f"Invalid --context format: {kv!r} (expected KEY=VALUE)")
        key, _, value = kv.partition("=")
        fsm.context[key.strip()] = value.strip()

    if getattr(args, "handoff_threshold", None) is not None:
        if not (1 <= args.handoff_threshold <= 100):
            raise SystemExit("--handoff-threshold must be between 1 and 100")
        os.environ["LL_HANDOFF_THRESHOLD"] = str(args.handoff_threshold)

    if getattr(args, "context_limit", None) is not None:
        os.environ["LL_CONTEXT_LIMIT"] = str(args.context_limit)

    # Dry run
    if args.dry_run:
        print_execution_plan(fsm)
        return 0

    # Pre-run validation: check required context variables are present
    _ctx_var_re = re.compile(r"\$\{context\.([^}.]+)")
    missing_keys: set[str] = set()
    for state in fsm.states.values():
        templates = [state.action] if state.action else []
        if state.evaluate and state.evaluate.prompt:
            templates.append(state.evaluate.prompt)
        for template in templates:
            for m in _ctx_var_re.finditer(template):
                key = m.group(1)
                if key not in fsm.context:
                    missing_keys.add(key)
    if missing_keys:
        for key in sorted(missing_keys):
            logger.error(
                f"Missing required context variable: '{key}'. "
                f"Run with: ll-loop run {loop_name} --context {key}=VALUE"
            )
        return 1

    # Background mode: spawn detached process and return
    if getattr(args, "background", False):
        return run_background(loop_name, args, loops_dir)

    # Register PID file for all foreground runs so cmd_stop can send SIGTERM (BUG-639).
    # Background-spawned processes (foreground_internal=True) have their PID written by the
    # parent in run_background(); plain foreground runs must write their own PID here.
    running_dir = loops_dir / ".running"
    running_dir.mkdir(parents=True, exist_ok=True)
    pid_file = running_dir / f"{loop_name}.pid"
    foreground_pid_file: Path | None = pid_file

    if not getattr(args, "foreground_internal", False):
        pid_file.write_text(str(os.getpid()))

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
        register_loop_signal_handlers(executor, pid_file=foreground_pid_file)

        from little_loops.config import BRConfig

        cli_colors = BRConfig(Path.cwd()).cli.colors
        highlight_color = cli_colors.fsm_active_state
        edge_label_colors = cli_colors.fsm_edge_labels.to_dict()
        return run_foreground(
            executor, fsm, args, highlight_color=highlight_color, edge_label_colors=edge_label_colors
        )
    finally:
        lock_manager.release(fsm.name)
