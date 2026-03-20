"""Shared helpers for ll-loop CLI subcommands."""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Any

from little_loops.cli.output import colorize, terminal_width

if TYPE_CHECKING:
    from little_loops.fsm.schema import FSMLoop
    from little_loops.logger import Logger

# Exit code mapping for terminated_by values
EXIT_CODES: dict[str, int] = {
    "terminal": 0,
    "signal": 0,
    "handoff": 0,
    "max_iterations": 1,
    "timeout": 1,
}

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
        # Kill any child subprocess currently blocking in the action runner
        inner = getattr(_loop_executor, "_executor", None)
        if inner is not None:
            runner = getattr(inner, "action_runner", None)
            if runner is not None:
                proc = getattr(runner, "_current_process", None)
                if proc is not None:
                    proc.kill()


def register_loop_signal_handlers(executor: Any, pid_file: Path | None = None) -> None:
    """Register SIGINT/SIGTERM handlers for graceful loop shutdown.

    Sets up signal handling so that Ctrl-C triggers a graceful shutdown
    (calls executor.request_shutdown()) rather than raising KeyboardInterrupt.
    A second Ctrl-C forces immediate exit with PID file cleanup.

    Args:
        executor: The PersistentExecutor instance to request shutdown on.
        pid_file: Optional path to PID file to clean up on forced exit.
    """
    global _loop_shutdown_requested, _loop_executor, _loop_pid_file
    _loop_shutdown_requested = False
    _loop_executor = executor
    _loop_pid_file = pid_file
    signal.signal(signal.SIGINT, _loop_signal_handler)
    signal.signal(signal.SIGTERM, _loop_signal_handler)


def get_builtin_loops_dir() -> Path:
    """Get the path to built-in loops bundled with the plugin."""
    return Path(__file__).parent.parent.parent.parent.parent / "loops"


def resolve_loop_path(name_or_path: str, loops_dir: Path) -> Path:
    """Resolve loop name to file path."""
    path = Path(name_or_path)
    if path.exists():
        return path

    # Try <loops_dir>/<name>.fsm.yaml first (compiled FSM)
    fsm_path = loops_dir / f"{name_or_path}.fsm.yaml"
    if fsm_path.exists():
        return fsm_path

    # Fall back to <loops_dir>/<name>.yaml
    loops_path = loops_dir / f"{name_or_path}.yaml"
    if loops_path.exists():
        return loops_path

    # Fall back to built-in loops from plugin directory
    builtin_path = get_builtin_loops_dir() / f"{name_or_path}.yaml"
    if builtin_path.exists():
        return builtin_path

    raise FileNotFoundError(f"Loop not found: {name_or_path}")


def load_loop(name_or_path: str, loops_dir: Path, logger: Logger) -> FSMLoop:
    """Load and validate a loop.

    Raises:
        FileNotFoundError: If loop not found.
        ValueError: If loop is invalid.
    """
    from little_loops.fsm.validation import load_and_validate

    path = resolve_loop_path(name_or_path, loops_dir)
    fsm, _ = load_and_validate(path)
    return fsm


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

    from little_loops.fsm.validation import load_and_validate

    path = resolve_loop_path(name_or_path, loops_dir)

    with open(path) as f:
        spec = yaml.safe_load(f)

    fsm, _ = load_and_validate(path)
    return fsm, spec


def print_execution_plan(fsm: FSMLoop) -> None:
    """Print dry-run execution plan."""
    tw = terminal_width()
    print(colorize(f"Execution plan for: {fsm.name}", "1"))
    print()
    print("States:")
    for name, state in fsm.states.items():
        terminal_marker = colorize(" [TERMINAL]", "32") if state.terminal else ""
        print(f"  {colorize(f'[{name}]', '1')}{terminal_marker}")
        if state.action:
            if state.action_type == "prompt":
                lines = state.action.strip().splitlines()
                preview = "\n      ".join(lines[:3])
                if len(lines) > 3 or len(state.action) > 200:
                    preview += " ..."
                print(f"    action: |\n      {preview}")
            else:
                max_action = tw - 16
                action_display = (
                    state.action[:max_action] + "..."
                    if len(state.action) > max_action
                    else state.action
                )
                print(f"    action: {action_display}")
        if state.evaluate:
            print(f"    evaluate: {state.evaluate.type}")
        if state.on_yes:
            print(f"    on_yes {colorize('->', '2')} {colorize(state.on_yes, '2')}")
        if state.on_no:
            print(f"    on_no {colorize('->', '2')} {colorize(state.on_no, '2')}")
        if state.on_error:
            print(f"    on_error {colorize('->', '2')} {colorize(state.on_error, '2')}")
        if state.next:
            print(f"    next {colorize('->', '2')} {colorize(state.next, '2')}")
        if state.route:
            print("    route:")
            for verdict, target in state.route.routes.items():
                print(f"      {verdict} {colorize('->', '2')} {colorize(target, '2')}")
            if state.route.default:
                print(f"      _ {colorize('->', '2')} {colorize(state.route.default, '2')}")
    print()
    print(f"Initial state: {fsm.initial}")
    print(f"Max iterations: {fsm.max_iterations}")
    if fsm.timeout:
        print(f"Timeout: {fsm.timeout}s")
    if fsm.context:
        print("Context:")
        for key, value in fsm.context.items():
            print(f"  {key}: {value!r}")


def run_background(
    loop_name: str, args: argparse.Namespace, loops_dir: Path, subcommand: str = "run"
) -> int:
    """Launch loop as a detached background process.

    Spawns a new process with start_new_session=True that re-executes
    the loop with --foreground-internal. The parent writes the PID file
    and returns immediately.

    Args:
        subcommand: The ll-loop subcommand to spawn ("run" or "resume").

    Returns:
        Exit code (0 = launched successfully).
    """
    running_dir = loops_dir / ".running"
    running_dir.mkdir(parents=True, exist_ok=True)

    pid_file = running_dir / f"{loop_name}.pid"
    log_file = running_dir / f"{loop_name}.log"

    # Build re-exec command with --foreground-internal instead of --background
    cmd = [
        sys.executable,
        "-m",
        "little_loops.cli.loop",
        subcommand,
        loop_name,
        "--foreground-internal",
    ]

    # Forward relevant args
    max_iter = getattr(args, "max_iterations", None)
    if max_iter:
        cmd.extend(["--max-iterations", str(max_iter)])
    if getattr(args, "no_llm", False):
        cmd.append("--no-llm")
    llm_model = getattr(args, "llm_model", None)
    if llm_model:
        cmd.extend(["--llm-model", llm_model])
    if getattr(args, "verbose", False):
        cmd.append("--verbose")
    if getattr(args, "show_diagrams", False):
        cmd.append("--show-diagrams")
    if getattr(args, "quiet", False):
        cmd.append("--quiet")
    if getattr(args, "queue", False):
        cmd.append("--queue")
    for kv in getattr(args, "context", None) or []:
        cmd.extend(["--context", kv])
    delay = getattr(args, "delay", None)
    if delay is not None:
        cmd.extend(["--delay", str(delay)])
    handoff_threshold = getattr(args, "handoff_threshold", None)
    if handoff_threshold is not None:
        cmd.extend(["--handoff-threshold", str(handoff_threshold)])
    context_limit = getattr(args, "context_limit", None)
    if context_limit is not None:
        cmd.extend(["--context-limit", str(context_limit)])

    with open(log_file, "w") as log_fh:
        process = subprocess.Popen(
            cmd,
            start_new_session=True,
            stdout=log_fh,
            stderr=log_fh,
            stdin=subprocess.DEVNULL,
        )

    pid_file.write_text(str(process.pid))
    print(
        f"Loop {colorize(loop_name, '1')} started in background (PID: {colorize(str(process.pid), '2')})"
    )
    print(f"  Log: {colorize(str(log_file), '2')}")
    print(f"  Status: {colorize(f'll-loop status {loop_name}', '2')}")
    print(f"  Stop:   {colorize(f'll-loop stop {loop_name}', '2')}")
    return 0


def run_foreground(
    executor: Any,
    fsm: FSMLoop,
    args: argparse.Namespace,
    highlight_color: str = "32",
    edge_label_colors: dict[str, str] | None = None,
) -> int:
    """Run loop with progress display.

    Args:
        highlight_color: ANSI SGR code for the active FSM state highlight in verbose mode.
        edge_label_colors: Optional label→SGR-code mapping for transition edge labels.

    Returns:
        Exit code (0 = success).
    """
    quiet = getattr(args, "quiet", False)
    verbose = getattr(args, "verbose", False)
    show_diagrams = getattr(args, "show_diagrams", False)
    clear_screen = getattr(args, "clear", False)
    if not quiet:
        print(f"Running loop: {colorize(fsm.name, '1')}")
        print(f"Max iterations: {colorize(str(fsm.max_iterations), '2')}")
        print()

    current_iteration = [0]  # Use list to allow mutation in closure
    loop_start_time = time.monotonic()

    def display_progress(event: dict) -> None:
        """Display progress for events."""
        event_type = event.get("event")
        depth = event.get("depth", 0)
        indent = "  " * depth
        tw = terminal_width()
        max_line = tw - 8 - len(indent)

        if event_type == "state_enter":
            current_iteration[0] = event.get("iteration", 0)
            state = event.get("state", "")
            if not quiet:
                elapsed_int = int(time.monotonic() - loop_start_time)
                if elapsed_int < 60:
                    elapsed_str = f"{elapsed_int}s"
                else:
                    elapsed_str = f"{elapsed_int // 60}m {elapsed_int % 60}s"
            if clear_screen and sys.stdout.isatty():
                print("\033[2J\033[H", end="", flush=True)
            if show_diagrams:
                from little_loops.cli.loop.layout import _render_fsm_diagram

                diagram = _render_fsm_diagram(
                    fsm,
                    highlight_state=state,
                    highlight_color=highlight_color,
                    edge_label_colors=edge_label_colors,
                )
                print(diagram, flush=True)
            if not quiet:
                print(
                    f"{indent}[{current_iteration[0]}/{fsm.max_iterations}] {colorize(state, '1')} ({colorize(elapsed_str, '2')})",
                    end="",
                    flush=True,
                )

        elif event_type == "action_start":
            if not quiet:
                action = event.get("action", "")
                is_prompt = event.get("is_prompt", False)
                if is_prompt:
                    lines = action.strip().splitlines()
                    line_count = len(lines)
                    prompt_badge = "\u2726"  # ✦
                    print(
                        f"{indent} -> {colorize(prompt_badge, '2')} {colorize(f'({line_count} lines)', '2')}",
                        flush=True,
                    )
                    show_count = line_count if verbose else min(5, line_count)
                    for line in lines[:show_count]:
                        display = line[:max_line] + "..." if len(line) > max_line else line
                        print(f"{indent}       {display}", flush=True)
                    if line_count > show_count:
                        print(f"{indent}       ... ({line_count - show_count} more lines)", flush=True)
                else:
                    action_display = action[:max_line] + "..." if len(action) > max_line else action
                    print(f"{indent} -> {colorize(action_display, '2')}", flush=True)

        elif event_type == "action_output":
            if not quiet and verbose:
                line = event.get("line", "")
                if line.strip():
                    display = line[:max_line] + "..." if len(line) > max_line else line
                    print(f"{indent}       {display}", flush=True)

        elif event_type == "action_complete":
            if not quiet:
                duration_ms = event.get("duration_ms", 0)
                exit_code = event.get("exit_code", 0)
                output_preview = event.get("output_preview")
                is_prompt = event.get("is_prompt", False)
                duration_sec = duration_ms / 1000
                if duration_sec < 60:
                    duration_str = f"{duration_sec:.1f}s"
                else:
                    minutes = int(duration_sec // 60)
                    seconds = duration_sec % 60
                    duration_str = f"{minutes}m {seconds:.0f}s"
                parts = [f"{indent}       ({colorize(duration_str, '2')})"]
                if exit_code == 124:
                    parts.append(colorize("timed out", "38;5;208"))
                elif exit_code != 0:
                    parts.append(colorize(f"exit: {exit_code}", "38;5;208"))
                print("  ".join(parts), flush=True)
                # Skip output preview for prompt states (already streamed) and in verbose mode
                # (lines already shown via action_output events). In non-verbose mode, show
                # a tail summary for shell states.
                if output_preview and not is_prompt and not verbose:
                    lines = [ln for ln in output_preview.splitlines() if ln.strip()]
                    show_lines = lines[-8:] if lines else []
                    for line in show_lines:
                        display = line[:max_line] + "..." if len(line) > max_line else line
                        print(f"{indent}       {display}", flush=True)

        elif event_type == "evaluate":
            if not quiet:
                verdict = event.get("verdict", "")
                confidence = event.get("confidence")
                reason = event.get("reason", "")
                error = event.get("error", "")
                if verdict in ("yes", "target", "progress"):
                    symbol = colorize("\u2713", "32")  # green checkmark
                    verdict_colored = colorize(verdict, "32")
                else:
                    symbol = colorize("\u2717", "38;5;208")  # orange x mark
                    verdict_colored = (
                        colorize(verdict, "38;5;208")
                        if verdict in ("no", "error")
                        else colorize(verdict, "2")
                    )
                # Build verdict line
                if error and verdict == "error":
                    verdict_line = f"{symbol} {verdict_colored}: {error}"
                elif confidence is not None:
                    verdict_line = (
                        f"{symbol} {verdict_colored} {colorize(f'({confidence:.2f})', '2')}"
                    )
                else:
                    verdict_line = f"{symbol} {verdict_colored}"
                print(f"{indent}       {verdict_line}", flush=True)
                # Show raw_preview for error verdicts to aid diagnosis
                raw_preview = event.get("raw_preview", "")
                if raw_preview and verdict == "error":
                    print(f"{indent}         raw: {raw_preview[:200]}", flush=True)
                # Show reason on a second line if present (and not already shown as error)
                if reason and not (error and verdict == "error"):
                    reason_display = reason[:300] + "..." if len(reason) > 300 else reason
                    print(f"{indent}         {reason_display}", flush=True)

        elif event_type == "route":
            if not quiet:
                to_state = event.get("to", "")
                print(f"{indent}       {colorize('->', '2')} {colorize(to_state, '1')}", flush=True)

    # Wire progress display via the proper observer slot on PersistentExecutor
    if not quiet or show_diagrams:
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
        if result.terminated_by == "terminal":
            state_colored = colorize(result.final_state, "32")
        else:
            state_colored = colorize(result.final_state, "38;5;208")
        print(f"Loop completed: {state_colored} ({result.iterations} iterations, {duration_str})")

    return EXIT_CODES.get(result.terminated_by, 1)
