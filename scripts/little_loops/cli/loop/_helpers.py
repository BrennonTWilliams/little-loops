"""Shared helpers for ll-loop CLI subcommands."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.fsm.schema import FSMLoop
    from little_loops.logger import Logger


def get_builtin_loops_dir() -> Path:
    """Get the path to built-in loops bundled with the plugin."""
    return Path(__file__).parent.parent.parent.parent.parent / "loops"


def resolve_loop_path(name_or_path: str, loops_dir: Path) -> Path:
    """Resolve loop name to path, preferring compiled FSM over paradigm."""
    path = Path(name_or_path)
    if path.exists():
        return path

    # Try <loops_dir>/<name>.fsm.yaml first (compiled FSM)
    fsm_path = loops_dir / f"{name_or_path}.fsm.yaml"
    if fsm_path.exists():
        return fsm_path

    # Fall back to <loops_dir>/<name>.yaml (paradigm)
    loops_path = loops_dir / f"{name_or_path}.yaml"
    if loops_path.exists():
        return loops_path

    # Fall back to built-in loops from plugin directory
    builtin_path = get_builtin_loops_dir() / f"{name_or_path}.yaml"
    if builtin_path.exists():
        return builtin_path

    raise FileNotFoundError(f"Loop not found: {name_or_path}")


def load_loop(name_or_path: str, loops_dir: Path, logger: Logger) -> FSMLoop:
    """Load and validate a loop, auto-compiling paradigm files.

    Raises:
        FileNotFoundError: If loop not found.
        ValueError: If loop is invalid.
    """
    import yaml

    from little_loops.fsm.compilers import compile_paradigm
    from little_loops.fsm.validation import load_and_validate

    path = resolve_loop_path(name_or_path, loops_dir)

    with open(path) as f:
        spec = yaml.safe_load(f)

    # Auto-compile if it's a paradigm file (has 'paradigm' but no 'initial')
    if "paradigm" in spec and "initial" not in spec:
        logger.info(f"Auto-compiling paradigm file: {path}")
        return compile_paradigm(spec)
    else:
        return load_and_validate(path)


def load_loop_with_spec(
    name_or_path: str, loops_dir: Path, logger: Logger
) -> tuple[FSMLoop, dict[str, Any]]:
    """Load a loop and return both the FSMLoop and raw spec dict.

    Used by commands that need access to raw YAML fields (e.g., description).

    Raises:
        FileNotFoundError: If loop not found.
        ValueError: If loop is invalid.
    """
    import yaml

    from little_loops.fsm.compilers import compile_paradigm
    from little_loops.fsm.validation import load_and_validate

    path = resolve_loop_path(name_or_path, loops_dir)

    with open(path) as f:
        spec = yaml.safe_load(f)

    if "paradigm" in spec and "initial" not in spec:
        logger.info(f"Auto-compiling paradigm file: {path}")
        fsm = compile_paradigm(spec)
    else:
        fsm = load_and_validate(path)

    return fsm, spec


def print_execution_plan(fsm: FSMLoop) -> None:
    """Print dry-run execution plan."""
    print(f"Execution plan for: {fsm.name}")
    print()
    print("States:")
    for name, state in fsm.states.items():
        terminal_marker = " [TERMINAL]" if state.terminal else ""
        print(f"  [{name}]{terminal_marker}")
        if state.action:
            if len(state.action) > 70:
                action_display = state.action[:70] + "..."
            else:
                action_display = state.action
            print(f"    action: {action_display}")
        if state.evaluate:
            print(f"    evaluate: {state.evaluate.type}")
        if state.on_success:
            print(f"    on_success -> {state.on_success}")
        if state.on_failure:
            print(f"    on_failure -> {state.on_failure}")
        if state.on_error:
            print(f"    on_error -> {state.on_error}")
        if state.next:
            print(f"    next -> {state.next}")
        if state.route:
            print("    route:")
            for verdict, target in state.route.routes.items():
                print(f"      {verdict} -> {target}")
            if state.route.default:
                print(f"      _ -> {state.route.default}")
    print()
    print(f"Initial state: {fsm.initial}")
    print(f"Max iterations: {fsm.max_iterations}")
    if fsm.timeout:
        print(f"Timeout: {fsm.timeout}s")


def run_foreground(executor: Any, fsm: FSMLoop, args: argparse.Namespace) -> int:
    """Run loop with progress display.

    Returns:
        Exit code (0 = success).
    """
    quiet = getattr(args, "quiet", False)
    if not quiet:
        print(f"Running loop: {fsm.name}")
        print(f"Max iterations: {fsm.max_iterations}")
        print()

    current_iteration = [0]  # Use list to allow mutation in closure
    loop_start_time = time.monotonic()

    def display_progress(event: dict) -> None:
        """Display progress for events."""
        event_type = event.get("event")

        if event_type == "state_enter":
            current_iteration[0] = event.get("iteration", 0)
            state = event.get("state", "")
            elapsed_int = int(time.monotonic() - loop_start_time)
            if elapsed_int < 60:
                elapsed_str = f"{elapsed_int}s"
            else:
                elapsed_str = f"{elapsed_int // 60}m {elapsed_int % 60}s"
            print(
                f"[{current_iteration[0]}/{fsm.max_iterations}] {state} ({elapsed_str})",
                end="",
                flush=True,
            )

        elif event_type == "action_start":
            action = event.get("action", "")
            action_display = action[:60] + "..." if len(action) > 60 else action
            print(f" -> {action_display}", flush=True)

        elif event_type == "evaluate":
            verdict = event.get("verdict", "")
            confidence = event.get("confidence")
            if verdict in ("success", "target", "progress"):
                symbol = "\u2713"  # checkmark
            else:
                symbol = "\u2717"  # x mark
            if confidence is not None:
                print(f"       {symbol} {verdict} (confidence: {confidence:.2f})", flush=True)
            else:
                print(f"       {symbol} {verdict}", flush=True)

        elif event_type == "route":
            to_state = event.get("to", "")
            print(f"       -> {to_state}", flush=True)

    # Wire progress display via the proper observer slot on PersistentExecutor
    if not quiet:
        executor._on_event = display_progress

    result = executor.run()

    if not quiet:
        print()
        duration_sec = result.duration_ms / 1000
        if duration_sec < 60:
            duration_str = f"{duration_sec:.1f}s"
        else:
            minutes = int(duration_sec // 60)
            seconds = duration_sec % 60
            duration_str = f"{minutes}m {seconds:.0f}s"
        print(
            f"Loop completed: {result.final_state} ({result.iterations} iterations, {duration_str})"
        )

    return 0 if result.terminated_by == "terminal" else 1
