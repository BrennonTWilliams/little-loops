"""Shared helpers for ll-loop CLI subcommands."""

from __future__ import annotations

import argparse
import subprocess
import sys
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
            if state.action_type == "prompt":
                lines = state.action.strip().splitlines()
                preview = "\n      ".join(lines[:3])
                if len(lines) > 3 or len(state.action) > 200:
                    preview += " ..."
                print(f"    action: |\n      {preview}")
            else:
                action_display = state.action[:70] + "..." if len(state.action) > 70 else state.action
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


def run_background(loop_name: str, args: argparse.Namespace, loops_dir: Path) -> int:
    """Launch loop as a detached background process.

    Spawns a new process with start_new_session=True that re-executes
    the loop with --foreground-internal. The parent writes the PID file
    and returns immediately.

    Returns:
        Exit code (0 = launched successfully).
    """
    running_dir = loops_dir / ".running"
    running_dir.mkdir(parents=True, exist_ok=True)

    pid_file = running_dir / f"{loop_name}.pid"
    log_file = running_dir / f"{loop_name}.log"

    # Build re-exec command with --foreground-internal instead of --background
    cmd = [sys.executable, "-m", "little_loops.cli.loop", "run", loop_name, "--foreground-internal"]

    # Forward relevant args
    max_iter = getattr(args, "max_iterations", None)
    if max_iter:
        cmd.extend(["--max-iterations", str(max_iter)])
    if getattr(args, "no_llm", False):
        cmd.append("--no-llm")
    llm_model = getattr(args, "llm_model", None)
    if llm_model:
        cmd.extend(["--llm-model", llm_model])
    if getattr(args, "quiet", False):
        cmd.append("--quiet")
    if getattr(args, "queue", False):
        cmd.append("--queue")

    log_fh = open(log_file, "w")  # noqa: SIM115
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
            is_prompt = event.get("is_prompt", False)
            prefix = "[prompt] " if is_prompt else ""
            max_len = 120 - len(prefix)
            action_display = action[:max_len] + "..." if len(action) > max_len else action
            print(f" -> {prefix}{action_display}", flush=True)

        elif event_type == "action_complete":
            duration_ms = event.get("duration_ms", 0)
            exit_code = event.get("exit_code", 0)
            output_preview = event.get("output_preview")
            duration_sec = duration_ms / 1000
            if duration_sec < 60:
                duration_str = f"{duration_sec:.1f}s"
            else:
                minutes = int(duration_sec // 60)
                seconds = duration_sec % 60
                duration_str = f"{minutes}m {seconds:.0f}s"
            parts = [f"       ({duration_str})"]
            if exit_code != 0:
                parts.append(f"exit: {exit_code}")
            print("  ".join(parts), flush=True)
            if output_preview:
                is_prompt = event.get("is_prompt", False)
                lines = [ln for ln in output_preview.splitlines() if ln.strip()]
                if is_prompt:
                    # Show last 3 lines for prompts to give more context
                    show_lines = lines[-3:] if lines else []
                    for line in show_lines:
                        display = line[:120] + "..." if len(line) > 120 else line
                        print(f"       ...{display}", flush=True)
                else:
                    # Show last 8 lines for shell commands (table/report output)
                    show_lines = lines[-8:] if lines else []
                    for line in show_lines:
                        display = line[:120] + "..." if len(line) > 120 else line
                        print(f"       {display}", flush=True)

        elif event_type == "evaluate":
            verdict = event.get("verdict", "")
            confidence = event.get("confidence")
            reason = event.get("reason", "")
            error = event.get("error", "")
            if verdict in ("success", "target", "progress"):
                symbol = "\u2713"  # checkmark
            else:
                symbol = "\u2717"  # x mark
            # Build verdict line
            if error and verdict == "error":
                verdict_line = f"{symbol} {verdict}: {error}"
            elif confidence is not None:
                verdict_line = f"{symbol} {verdict} ({confidence:.2f})"
            else:
                verdict_line = f"{symbol} {verdict}"
            print(f"       {verdict_line}", flush=True)
            # Show reason on a second line if present (and not already shown as error)
            if reason and not (error and verdict == "error"):
                reason_display = reason[:300] + "..." if len(reason) > 300 else reason
                print(f"         {reason_display}", flush=True)

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
