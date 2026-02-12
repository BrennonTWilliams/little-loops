"""ll-loop: Execute FSM-based automation loops."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def main_loop() -> int:
    """Entry point for ll-loop command.

    Execute FSM-based automation loops.

    Returns:
        Exit code (0 = success)
    """
    import yaml

    from little_loops.config import BRConfig
    from little_loops.fsm.compilers import compile_paradigm
    from little_loops.fsm.concurrency import LockManager
    from little_loops.fsm.persistence import (
        PersistentExecutor,
        StatePersistence,
        get_loop_history,
        list_running_loops,
    )
    from little_loops.fsm.schema import FSMLoop
    from little_loops.fsm.validation import load_and_validate

    # Load config for loops_dir
    config = BRConfig(Path.cwd())
    loops_dir = Path(config.loops.loops_dir)

    # Check if first positional arg is a subcommand or a loop name
    # This enables "ll-loop fix-types" shorthand for "ll-loop run fix-types"
    known_subcommands = {
        "run",
        "compile",
        "validate",
        "list",
        "status",
        "stop",
        "resume",
        "history",
        "test",
        "simulate",
        "install",
        "show",
    }

    # Pre-process args: if first positional arg is not a subcommand, insert "run"
    import sys as _sys

    argv = _sys.argv[1:]
    if argv and not argv[0].startswith("-") and argv[0] not in known_subcommands:
        # First arg is a loop name, not a subcommand - insert "run"
        argv = ["run"] + argv

    parser = argparse.ArgumentParser(
        prog="ll-loop",
        description="Execute FSM-based automation loops",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s fix-types              # Run loop from .loops/fix-types.yaml
  %(prog)s run fix-types --dry-run  # Show execution plan
  %(prog)s validate fix-types     # Validate loop definition
  %(prog)s test fix-types         # Run single test iteration
  %(prog)s simulate fix-types     # Interactive simulation (dry-run with prompts)
  %(prog)s compile paradigm.yaml  # Compile paradigm to FSM
  %(prog)s list                   # List available loops
  %(prog)s list --running         # List running loops
  %(prog)s status fix-types       # Show loop status
  %(prog)s stop fix-types         # Stop a running loop
  %(prog)s resume fix-types       # Resume interrupted loop
  %(prog)s history fix-types      # Show execution history
""",
    )

    subparsers = parser.add_subparsers(dest="command")

    # Run subcommand
    run_parser = subparsers.add_parser("run", help="Run a loop")
    run_parser.add_argument("loop", help="Loop name or path")
    run_parser.add_argument("--max-iterations", "-n", type=int, help="Override iteration limit")
    run_parser.add_argument("--no-llm", action="store_true", help="Disable LLM evaluation")
    run_parser.add_argument("--llm-model", type=str, help="Override LLM model")
    run_parser.add_argument(
        "--dry-run", action="store_true", help="Show execution plan without running"
    )
    run_parser.add_argument(
        "--background", "-b", action="store_true", help="Run as daemon (not yet implemented)"
    )
    run_parser.add_argument("--quiet", "-q", action="store_true", help="Suppress progress output")
    run_parser.add_argument(
        "--queue", action="store_true", help="Wait for conflicting loops to finish"
    )

    # Compile subcommand
    compile_parser = subparsers.add_parser("compile", help="Compile paradigm to FSM")
    compile_parser.add_argument("input", help="Input paradigm YAML file")
    compile_parser.add_argument("-o", "--output", help="Output FSM YAML file")

    # Validate subcommand
    validate_parser = subparsers.add_parser("validate", help="Validate loop definition")
    validate_parser.add_argument("loop", help="Loop name or path")

    # List subcommand
    list_parser = subparsers.add_parser("list", help="List loops")
    list_parser.add_argument("--running", action="store_true", help="Only show running loops")

    # Status subcommand
    status_parser = subparsers.add_parser("status", help="Show loop status")
    status_parser.add_argument("loop", help="Loop name")

    # Stop subcommand
    stop_parser = subparsers.add_parser("stop", help="Stop a running loop")
    stop_parser.add_argument("loop", help="Loop name")

    # Resume subcommand
    resume_parser = subparsers.add_parser("resume", help="Resume an interrupted loop")
    resume_parser.add_argument("loop", help="Loop name or path")

    # History subcommand
    history_parser = subparsers.add_parser("history", help="Show loop execution history")
    history_parser.add_argument("loop", help="Loop name")
    history_parser.add_argument(
        "--tail", "-n", type=int, default=50, help="Last N events (default: 50)"
    )

    # Test subcommand
    test_parser = subparsers.add_parser(
        "test", help="Run a single test iteration to verify loop configuration"
    )
    test_parser.add_argument("loop", help="Loop name")

    # Simulate subcommand
    simulate_parser = subparsers.add_parser(
        "simulate",
        help="Trace loop execution interactively without running commands",
    )
    simulate_parser.add_argument("loop", help="Loop name or path")
    simulate_parser.add_argument(
        "--scenario",
        choices=["all-pass", "all-fail", "first-fail", "alternating"],
        help="Auto-select results based on pattern instead of prompting",
    )
    simulate_parser.add_argument(
        "--max-iterations",
        "-n",
        type=int,
        help="Override max iterations for simulation (default: min of loop config or 20)",
    )

    # Install subcommand
    install_parser = subparsers.add_parser(
        "install",
        help="Copy a built-in loop to .loops/ for customization",
    )
    install_parser.add_argument("loop", help="Built-in loop name to install")

    # Show subcommand
    show_parser = subparsers.add_parser("show", help="Show loop details and structure")
    show_parser.add_argument("loop", help="Loop name or path")

    args = parser.parse_args(argv)

    from little_loops.logger import Logger

    logger = Logger(verbose=not getattr(args, "quiet", False))

    def get_builtin_loops_dir() -> Path:
        """Get the path to built-in loops bundled with the plugin."""
        return Path(__file__).parent.parent.parent.parent / "loops"

    def resolve_loop_path(name_or_path: str) -> Path:
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

    def run_foreground(executor: PersistentExecutor, fsm: FSMLoop) -> int:
        """Run loop with progress display."""
        if not getattr(args, "quiet", False):
            print(f"Running loop: {fsm.name}")
            print(f"Max iterations: {fsm.max_iterations}")
            print()

        current_iteration = [0]  # Use list to allow mutation in closure

        def display_progress(event: dict) -> None:
            """Display progress for events."""
            event_type = event.get("event")

            if event_type == "state_enter":
                current_iteration[0] = event.get("iteration", 0)
                state = event.get("state", "")
                print(f"[{current_iteration[0]}/{fsm.max_iterations}] {state}", end="")

            elif event_type == "action_start":
                action = event.get("action", "")
                action_display = action[:60] + "..." if len(action) > 60 else action
                print(f" -> {action_display}")

            elif event_type == "evaluate":
                verdict = event.get("verdict", "")
                confidence = event.get("confidence")
                if verdict in ("success", "target", "progress"):
                    symbol = "\u2713"  # checkmark
                else:
                    symbol = "\u2717"  # x mark
                if confidence is not None:
                    print(f"       {symbol} {verdict} (confidence: {confidence:.2f})")
                else:
                    print(f"       {symbol} {verdict}")

            elif event_type == "route":
                to_state = event.get("to", "")
                print(f"       -> {to_state}")

        # Create wrapper to combine persistence callback with progress display
        original_handle = executor._handle_event
        quiet = getattr(args, "quiet", False)

        def combined_handler(event: dict) -> None:
            original_handle(event)
            if not quiet:
                display_progress(event)

        # Use object.__setattr__ to bypass method assignment check
        object.__setattr__(executor, "_handle_event", combined_handler)

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
                f"Loop completed: {result.final_state} "
                f"({result.iterations} iterations, {duration_str})"
            )

        return 0 if result.terminated_by == "terminal" else 1

    def cmd_run(loop_name: str) -> int:
        """Run a loop."""
        try:
            path = resolve_loop_path(loop_name)

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
            return run_foreground(executor, fsm)
        finally:
            lock_manager.release(fsm.name)

    def cmd_compile() -> int:
        """Compile paradigm YAML to FSM."""
        input_path = Path(args.input)
        if not input_path.exists():
            logger.error(f"Input file not found: {input_path}")
            return 1

        try:
            with open(input_path) as f:
                spec = yaml.safe_load(f)
            fsm = compile_paradigm(spec)
        except ValueError as e:
            logger.error(f"Compilation error: {e}")
            return 1
        except yaml.YAMLError as e:
            logger.error(f"YAML parse error: {e}")
            return 1

        output_path = (
            Path(args.output)
            if args.output
            else Path(str(input_path).replace(".yaml", ".fsm.yaml"))
        )

        # Convert FSMLoop to dict for YAML output
        fsm_dict: dict[str, Any] = {
            "name": fsm.name,
            "paradigm": fsm.paradigm,
            "initial": fsm.initial,
            "states": {name: state.to_dict() for name, state in fsm.states.items()},
            "max_iterations": fsm.max_iterations,
        }
        if fsm.context:
            fsm_dict["context"] = fsm.context
        if fsm.maintain:
            fsm_dict["maintain"] = fsm.maintain
        if fsm.backoff:
            fsm_dict["backoff"] = fsm.backoff
        if fsm.timeout:
            fsm_dict["timeout"] = fsm.timeout

        with open(output_path, "w") as f:
            yaml.dump(fsm_dict, f, default_flow_style=False, sort_keys=False)

        logger.success(f"Compiled to: {output_path}")
        return 0

    def cmd_validate(loop_name: str) -> int:
        """Validate a loop definition."""
        try:
            path = resolve_loop_path(loop_name)

            # Load the file to check format
            with open(path) as f:
                spec = yaml.safe_load(f)

            # Auto-compile if it's a paradigm file (has 'paradigm' but no 'initial')
            if "paradigm" in spec and "initial" not in spec:
                logger.info(f"Compiling paradigm file for validation: {path}")
                fsm = compile_paradigm(spec)
            else:
                fsm = load_and_validate(path)

            logger.success(f"{loop_name} is valid")
            print(f"  States: {', '.join(fsm.states.keys())}")
            print(f"  Initial: {fsm.initial}")
            print(f"  Max iterations: {fsm.max_iterations}")
            return 0
        except FileNotFoundError as e:
            logger.error(str(e))
            return 1
        except ValueError as e:
            logger.error(f"{loop_name} is invalid: {e}")
            return 1

    def cmd_list() -> int:
        """List loops."""
        if getattr(args, "running", False):
            states = list_running_loops(loops_dir)
            if not states:
                print("No running loops")
                return 0
            print("Running loops:")
            for state in states:
                print(f"  {state.loop_name}: {state.current_state} (iteration {state.iteration})")
            return 0

        # Collect project loops
        project_names: set[str] = set()
        yaml_files: list[Path] = []
        if loops_dir.exists():
            yaml_files = list(loops_dir.glob("*.yaml"))
            project_names = {p.stem for p in yaml_files}

        # Collect built-in loops (excluding those overridden by project)
        builtin_dir = get_builtin_loops_dir()
        builtin_files: list[Path] = []
        if builtin_dir.exists():
            builtin_files = [
                f for f in sorted(builtin_dir.glob("*.yaml")) if f.stem not in project_names
            ]

        if not yaml_files and not builtin_files:
            print("No loops available")
            return 0

        print("Available loops:")
        for path in sorted(yaml_files):
            print(f"  {path.stem}")
        for path in builtin_files:
            print(f"  {path.stem}  [built-in]")
        return 0

    def cmd_install(loop_name: str) -> int:
        """Copy a built-in loop to .loops/ for customization."""
        import shutil

        builtin_dir = get_builtin_loops_dir()
        source = builtin_dir / f"{loop_name}.yaml"

        if not source.exists():
            available = [f.stem for f in builtin_dir.glob("*.yaml")] if builtin_dir.exists() else []
            logger.error(f"No built-in loop named '{loop_name}'")
            if available:
                print(f"Available built-in loops: {', '.join(sorted(available))}")
            return 1

        loops_dir.mkdir(exist_ok=True)
        dest = loops_dir / f"{loop_name}.yaml"

        if dest.exists():
            logger.error(f"Loop already exists: {dest}")
            print("Remove it first or edit it directly.")
            return 1

        shutil.copy2(source, dest)
        print(f"Installed {loop_name} to {dest}")
        print("You can now customize it by editing the file.")
        return 0

    def cmd_status(loop_name: str) -> int:
        """Show loop status."""
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

    def cmd_stop(loop_name: str) -> int:
        """Stop a running loop."""
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

    def cmd_resume(loop_name: str) -> int:
        """Resume an interrupted loop."""
        try:
            path = resolve_loop_path(loop_name)

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

    def cmd_history(loop_name: str) -> int:
        """Show loop history."""
        events = get_loop_history(loop_name, loops_dir)

        if not events:
            print(f"No history for: {loop_name}")
            return 0

        # Show last N events
        tail = getattr(args, "tail", 50)
        for event in events[-tail:]:
            ts = event.get("ts", "")[:19]  # Truncate to seconds
            event_type = event.get("event", "")
            details = {k: v for k, v in event.items() if k not in ("event", "ts")}
            print(f"{ts} {event_type}: {details}")

        return 0

    def cmd_test(loop_name: str) -> int:
        """Run a single test iteration to verify loop configuration.

        Executes the initial state's action and evaluation, then reports
        what the loop would do without actually transitioning further.
        """
        from little_loops.fsm.evaluators import EvaluationResult, evaluate, evaluate_exit_code
        from little_loops.fsm.executor import DefaultActionRunner
        from little_loops.fsm.interpolation import InterpolationContext

        try:
            path = resolve_loop_path(loop_name)

            # Load the file to check format
            with open(path) as f:
                spec = yaml.safe_load(f)

            # Auto-compile if it's a paradigm file
            if "paradigm" in spec and "initial" not in spec:
                fsm = compile_paradigm(spec)
            else:
                fsm = load_and_validate(path)
        except FileNotFoundError as e:
            logger.error(str(e))
            return 1
        except ValueError as e:
            logger.error(f"Validation error: {e}")
            return 1

        # Get initial state
        initial = fsm.initial
        state_config = fsm.states[initial]

        print(f"## Test Iteration: {loop_name}")
        print()
        print(f"State: {initial}")

        # If no action, report and exit
        if not state_config.action:
            print(f"Initial state '{initial}' has no action to test")
            print()
            print("\u2713 Loop structure is valid (no check action to execute)")
            return 0

        action = state_config.action
        is_slash = action.startswith("/") or state_config.action_type in (
            "prompt",
            "slash_command",
        )

        print(f"Action: {action}")
        print()

        if is_slash:
            print("Note: Slash commands require Claude CLI; skipping actual execution.")
            print()
            print("Verdict: SKIPPED (slash command)")
            print()
            print("\u2713 Loop structure is valid (slash command not executed)")
            return 0

        # Run the action
        runner = DefaultActionRunner()
        timeout = state_config.timeout or 120
        result = runner.run(action, timeout=timeout, is_slash_command=False)

        print(f"Exit code: {result.exit_code}")

        # Truncate output for display
        output_lines = result.output.strip().split("\n")
        if len(output_lines) > 10:
            extra = len(output_lines) - 10
            output_preview = "\n".join(output_lines[:10]) + f"\n... ({extra} more lines)"
        elif len(result.output) > 500:
            output_preview = result.output[:500] + "..."
        else:
            output_preview = result.output.strip() if result.output.strip() else "(empty)"

        print(f"Output:\n{output_preview}")

        if result.stderr:
            stderr_lines = result.stderr.strip().split("\n")
            if len(stderr_lines) > 5:
                extra = len(stderr_lines) - 5
                stderr_preview = "\n".join(stderr_lines[:5]) + f"\n... ({extra} more lines)"
            else:
                stderr_preview = result.stderr.strip()
            print(f"Stderr:\n{stderr_preview}")

        print()

        # Evaluate
        ctx = InterpolationContext()
        eval_result: EvaluationResult

        if state_config.evaluate:
            eval_result = evaluate(
                config=state_config.evaluate,
                output=result.output,
                exit_code=result.exit_code,
                context=ctx,
            )
            evaluator_type: str = state_config.evaluate.type
        else:
            # Default to exit_code evaluation
            eval_result = evaluate_exit_code(result.exit_code)
            evaluator_type = "exit_code (default)"

        print(f"Evaluator: {evaluator_type}")
        print(f"Verdict: {eval_result.verdict.upper()}")

        if eval_result.details:
            for key, value in eval_result.details.items():
                if key != "exit_code" or evaluator_type != "exit_code (default)":
                    print(f"  {key}: {value}")

        # Determine next state based on verdict
        verdict = eval_result.verdict
        next_state = None

        if state_config.route:
            routes = state_config.route.routes
            if verdict in routes:
                next_state = routes[verdict]
            elif state_config.route.default:
                next_state = state_config.route.default
        else:
            if verdict == "success" and state_config.on_success:
                next_state = state_config.on_success
            elif verdict == "failure" and state_config.on_failure:
                next_state = state_config.on_failure
            elif verdict == "error" and state_config.on_error:
                next_state = state_config.on_error

        print()
        if next_state:
            print(f"Would transition: {initial} \u2192 {next_state}")
        else:
            print(f"Would transition: {initial} \u2192 (no route for '{verdict}')")

        # Summary
        print()
        has_error = eval_result.verdict == "error" or "error" in eval_result.details
        if has_error:
            print("\u26a0 Loop has issues - review the error details above")
            return 1
        else:
            print("\u2713 Loop appears to be configured correctly")
            return 0

    def cmd_simulate(loop_name: str) -> int:
        """Run interactive simulation of loop execution.

        Traces through loop logic without executing commands, allowing users
        to verify state transitions and understand loop behavior.
        """
        from little_loops.fsm.executor import FSMExecutor, SimulationActionRunner

        try:
            path = resolve_loop_path(loop_name)

            # Load the file to check format
            with open(path) as f:
                spec = yaml.safe_load(f)

            # Auto-compile if it's a paradigm file
            if "paradigm" in spec and "initial" not in spec:
                fsm = compile_paradigm(spec)
            else:
                fsm = load_and_validate(path)
        except FileNotFoundError as e:
            logger.error(str(e))
            return 1
        except ValueError as e:
            logger.error(f"Validation error: {e}")
            return 1

        # Apply CLI overrides
        if args.max_iterations:
            fsm.max_iterations = args.max_iterations
        else:
            # Limit iterations for simulation safety (cap at 20 unless overridden)
            if fsm.max_iterations > 20:
                logger.info(
                    f"Limiting simulation to 20 iterations (loop config: {fsm.max_iterations})"
                )
                fsm.max_iterations = 20

        # Create simulation runner
        sim_runner = SimulationActionRunner(scenario=args.scenario)

        # Track simulation state
        states_visited: list[str] = []

        def simulation_callback(event: dict) -> None:
            """Display simulation progress."""
            event_type = event.get("event")

            if event_type == "state_enter":
                iteration = event.get("iteration", 0)
                state = event.get("state", "")
                states_visited.append(state)
                print()
                print(f"[{iteration}] State: {state}")

            elif event_type == "action_start":
                action = event.get("action", "")
                action_display = action[:70] + "..." if len(action) > 70 else action
                print(f"    Action: {action_display}")

            elif event_type == "evaluate":
                evaluator = event.get("type", "exit_code")
                verdict = event.get("verdict", "")
                print(f"    Evaluator: {evaluator}")
                print(f"    Result: {verdict.upper()}")

            elif event_type == "route":
                from_state = event.get("from", "")
                to_state = event.get("to", "")
                print(f"    Transition: {from_state} \u2192 {to_state}")

        # Print header
        mode_str = f"scenario={args.scenario}" if args.scenario else "interactive"
        print(f"=== SIMULATION: {fsm.name} ({mode_str}) ===")

        # Run simulation
        executor = FSMExecutor(
            fsm,
            event_callback=simulation_callback,
            action_runner=sim_runner,
        )
        result = executor.run()

        # Print summary
        print()
        print("=== Summary ===")
        arrow = " \u2192 "
        print(f"States visited: {arrow.join(states_visited)}")
        print(f"Iterations: {result.iterations}")
        print(f"Would have executed {len(sim_runner.calls)} commands")
        print(f"Terminated by: {result.terminated_by}")

        return 0

    def cmd_show(loop_name: str) -> int:
        """Show loop details and structure."""
        try:
            path = resolve_loop_path(loop_name)

            with open(path) as f:
                spec = yaml.safe_load(f)

            # Auto-compile paradigm files
            if "paradigm" in spec and "initial" not in spec:
                fsm = compile_paradigm(spec)
            else:
                fsm = load_and_validate(path)
        except FileNotFoundError as e:
            logger.error(str(e))
            return 1
        except ValueError as e:
            logger.error(f"Invalid loop: {e}")
            return 1

        # --- Metadata ---
        print(f"Loop: {fsm.name}")
        if fsm.paradigm:
            print(f"Paradigm: {fsm.paradigm}")
        description = spec.get("description", "").strip()
        if description:
            print(f"Description: {description}")
        print(f"Max iterations: {fsm.max_iterations}")
        if fsm.timeout:
            print(f"Timeout: {fsm.timeout}s")
        if fsm.backoff:
            print(f"Backoff: {fsm.backoff}s")
        if fsm.maintain:
            print("Maintain: yes (restarts after completion)")
        if fsm.context:
            print(f"Context variables: {', '.join(fsm.context.keys())}")
        if fsm.scope:
            print(f"Scope: {', '.join(fsm.scope)}")
        print(f"Source: {path}")

        # --- States & Transitions ---
        print()
        print("States:")
        for name, state in fsm.states.items():
            terminal_marker = " [TERMINAL]" if state.terminal else ""
            initial_marker = " [INITIAL]" if name == fsm.initial else ""
            print(f"  [{name}]{initial_marker}{terminal_marker}")
            if state.action:
                action_display = state.action[:70] + "..." if len(state.action) > 70 else state.action
                print(f"    action: {action_display}")
            if state.action_type:
                print(f"    type: {state.action_type}")
            if state.evaluate:
                print(f"    evaluate: {state.evaluate.type}")
            if state.on_success:
                print(f"    on_success ──→ {state.on_success}")
            if state.on_failure:
                print(f"    on_failure ──→ {state.on_failure}")
            if state.on_error:
                print(f"    on_error ──→ {state.on_error}")
            if state.next:
                print(f"    next ──→ {state.next}")
            if state.route:
                print("    route:")
                for verdict, target in state.route.routes.items():
                    print(f"      {verdict} ──→ {target}")
                if state.route.default:
                    print(f"      _ ──→ {state.route.default}")

        # --- ASCII FSM Diagram ---
        print()
        print("Diagram:")
        # Build adjacency for diagram
        edges: list[tuple[str, str, str]] = []  # (from, to, label)
        for name, state in fsm.states.items():
            if state.on_success:
                edges.append((name, state.on_success, "success"))
            if state.on_failure:
                edges.append((name, state.on_failure, "fail"))
            if state.on_error:
                edges.append((name, state.on_error, "error"))
            if state.next:
                edges.append((name, state.next, "next"))
            if state.route:
                for verdict, target in state.route.routes.items():
                    edges.append((name, target, verdict))
                if state.route.default:
                    edges.append((name, state.route.default, "_"))

        # Trace linear path from initial state for main flow
        visited: set[str] = set()
        main_path: list[str] = []
        current = fsm.initial
        while current and current not in visited:
            visited.add(current)
            main_path.append(current)
            st = fsm.states.get(current)
            if not st or st.terminal:
                break
            # Follow primary transition
            nxt = st.on_success or st.next
            if nxt:
                current = nxt
            elif st.route:
                # Pick first route entry as primary
                first_target = next(iter(st.route.routes.values()), None)
                current = first_target or st.route.default or ""
            else:
                break

        # Render main flow
        if main_path:
            flow_parts = [f"[{s}]" for s in main_path]
            print(f"  {' ──→ '.join(flow_parts)}")

        # Render back-edges and alternate transitions
        for src, dst, label in edges:
            if src in visited and dst in visited:
                # Skip edges already shown in main flow
                src_idx = main_path.index(src) if src in main_path else -1
                dst_idx = main_path.index(dst) if dst in main_path else -1
                if dst_idx == src_idx + 1 and label in ("success", "next"):
                    continue
            print(f"  [{src}] ──({label})──→ [{dst}]")

        # --- Run Command ---
        print()
        print("Run command:")
        print(f"  ll-loop run {loop_name}")

        return 0

    # Dispatch commands
    if args.command == "run":
        return cmd_run(args.loop)
    elif args.command == "compile":
        return cmd_compile()
    elif args.command == "validate":
        return cmd_validate(args.loop)
    elif args.command == "list":
        return cmd_list()
    elif args.command == "status":
        return cmd_status(args.loop)
    elif args.command == "stop":
        return cmd_stop(args.loop)
    elif args.command == "resume":
        return cmd_resume(args.loop)
    elif args.command == "history":
        return cmd_history(args.loop)
    elif args.command == "test":
        return cmd_test(args.loop)
    elif args.command == "simulate":
        return cmd_simulate(args.loop)
    elif args.command == "install":
        return cmd_install(args.loop)
    elif args.command == "show":
        return cmd_show(args.loop)
    else:
        parser.print_help()
        return 1
