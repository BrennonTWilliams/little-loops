"""ll-loop lifecycle subcommands: status, stop, resume."""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.cli.loop._helpers import load_loop
from little_loops.logger import Logger


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

    try:
        fsm = load_loop(loop_name, loops_dir, logger)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return 1

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
    return 0 if result.terminated_by == "terminal" else 1
