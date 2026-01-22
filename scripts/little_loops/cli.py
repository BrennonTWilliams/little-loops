"""CLI entry points for little-loops.

Provides command-line interfaces for automated issue management:
- ll-auto: Sequential issue processing
- ll-parallel: Parallel issue processing with git worktrees
- ll-messages: Extract user messages from Claude Code logs
- ll-sprint: Sprint and sequence management
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from little_loops.config import BRConfig
from little_loops.issue_manager import AutoManager
from little_loops.logger import Logger
from little_loops.parallel.orchestrator import ParallelOrchestrator
from little_loops.sprint import SprintManager, SprintOptions


def main_auto() -> int:
    """Entry point for ll-auto command.

    Sequential automated issue management with Claude CLI.

    Returns:
        Exit code (0 = success)
    """
    parser = argparse.ArgumentParser(
        description="Automated sequential issue management with Claude CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Process all issues in priority order
  %(prog)s --max-issues 5     # Process at most 5 issues
  %(prog)s --resume           # Resume from previous state
  %(prog)s --dry-run          # Preview what would be processed
  %(prog)s --category bugs    # Only process bugs
  %(prog)s --only BUG-001,BUG-002  # Process only specific issues
  %(prog)s --skip BUG-003     # Skip specific issues
""",
    )

    parser.add_argument(
        "--resume",
        "-r",
        action="store_true",
        help="Resume from previous checkpoint",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--max-issues",
        "-m",
        type=int,
        default=0,
        help="Limit number of issues to process (0 = unlimited)",
    )
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        default=None,
        help="Filter to specific category (bugs, features, enhancements)",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Comma-separated list of issue IDs to process (e.g., BUG-001,FEAT-002)",
    )
    parser.add_argument(
        "--skip",
        type=str,
        default=None,
        help="Comma-separated list of issue IDs to skip (e.g., BUG-003,FEAT-004)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to project root (default: current directory)",
    )

    args = parser.parse_args()

    project_root = args.config or Path.cwd()
    config = BRConfig(project_root)

    # Parse issue ID filters
    only_ids = {i.strip().upper() for i in args.only.split(",")} if args.only else None
    skip_ids = {i.strip().upper() for i in args.skip.split(",")} if args.skip else None

    manager = AutoManager(
        config=config,
        dry_run=args.dry_run,
        max_issues=args.max_issues,
        resume=args.resume,
        category=args.category,
        only_ids=only_ids,
        skip_ids=skip_ids,
    )

    return manager.run()


def main_parallel() -> int:
    """Entry point for ll-parallel command.

    Parallel issue management using git worktrees.

    Returns:
        Exit code (0 = success)
    """
    parser = argparse.ArgumentParser(
        description="Parallel issue management with git worktrees",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Process with default workers
  %(prog)s --workers 3        # Use 3 parallel workers
  %(prog)s --dry-run          # Preview what would be processed
  %(prog)s --priority P1,P2   # Only process P1 and P2 issues
  %(prog)s --cleanup          # Clean up worktrees and exit
  %(prog)s --stream-output    # Stream Claude CLI output in real-time
  %(prog)s --only BUG-001,BUG-002  # Process only specific issues
  %(prog)s --skip BUG-003     # Skip specific issues
""",
    )

    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=None,
        help="Number of parallel workers (default: from config or 2)",
    )
    parser.add_argument(
        "--priority",
        "-p",
        type=str,
        default=None,
        help="Comma-separated priorities to process (default: all)",
    )
    parser.add_argument(
        "--max-issues",
        "-m",
        type=int,
        default=0,
        help="Maximum issues to process (0 = unlimited)",
    )
    parser.add_argument(
        "--worktree-base",
        type=Path,
        default=None,
        help="Base directory for git worktrees",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Preview without making changes",
    )
    parser.add_argument(
        "--resume",
        "-r",
        action="store_true",
        help="Resume from previous state",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=int,
        default=None,
        help="Timeout per issue in seconds",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress output",
    )
    parser.add_argument(
        "--cleanup",
        "-c",
        action="store_true",
        help="Clean up all worktrees and exit",
    )
    parser.add_argument(
        "--merge-pending",
        action="store_true",
        help="Attempt to merge pending work from previous interrupted runs",
    )
    parser.add_argument(
        "--clean-start",
        action="store_true",
        help="Remove all worktrees and start fresh (skip pending work check)",
    )
    parser.add_argument(
        "--ignore-pending",
        action="store_true",
        help="Report pending work but continue without merging",
    )
    parser.add_argument(
        "--stream-output",
        action="store_true",
        help="Stream Claude CLI subprocess output to console",
    )
    parser.add_argument(
        "--show-model",
        action="store_true",
        help="Make API call to verify and display model on worktree setup",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Comma-separated list of issue IDs to process (e.g., BUG-001,FEAT-002)",
    )
    parser.add_argument(
        "--skip",
        type=str,
        default=None,
        help="Comma-separated list of issue IDs to skip (e.g., BUG-003,FEAT-004)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to project root",
    )

    args = parser.parse_args()

    project_root = args.config or Path.cwd()
    config = BRConfig(project_root)

    logger = Logger(verbose=not args.quiet)

    # Handle cleanup mode
    if args.cleanup:
        from little_loops.parallel import WorkerPool

        parallel_config = config.create_parallel_config()
        pool = WorkerPool(parallel_config, config, logger, project_root)
        pool.cleanup_all_worktrees()
        logger.success("Cleanup complete")
        return 0

    # Build priority filter
    priority_filter = (
        [p.strip().upper() for p in args.priority.split(",")] if args.priority else None
    )

    # Parse issue ID filters
    only_ids = {i.strip().upper() for i in args.only.split(",")} if args.only else None
    skip_ids = {i.strip().upper() for i in args.skip.split(",")} if args.skip else None

    # Create parallel config with CLI overrides
    parallel_config = config.create_parallel_config(
        max_workers=args.workers,
        priority_filter=priority_filter,
        max_issues=args.max_issues,
        dry_run=args.dry_run,
        timeout_seconds=args.timeout,
        stream_output=args.stream_output if args.stream_output else None,
        show_model=args.show_model if args.show_model else None,
        only_ids=only_ids,
        skip_ids=skip_ids,
        merge_pending=args.merge_pending,
        clean_start=args.clean_start,
        ignore_pending=args.ignore_pending,
    )

    # Delete state file if not resuming
    if not args.resume:
        state_file = config.get_parallel_state_file()
        if state_file.exists():
            state_file.unlink()

    # Create and run orchestrator
    from little_loops.parallel import ParallelOrchestrator

    orchestrator = ParallelOrchestrator(
        parallel_config=parallel_config,
        br_config=config,
        repo_path=project_root,
        verbose=not args.quiet,
    )

    return orchestrator.run()


def main_messages() -> int:
    """Entry point for ll-messages command.

    Extract user messages from Claude Code session logs.

    Returns:
        Exit code (0 = success)
    """
    from datetime import datetime

    from little_loops.user_messages import (
        extract_user_messages,
        get_project_folder,
        print_messages_to_stdout,
        save_messages,
    )

    parser = argparse.ArgumentParser(
        description="Extract user messages from Claude Code logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                      # Last 100 messages to file
  %(prog)s -n 50                # Last 50 messages
  %(prog)s --since 2026-01-01   # Messages since date
  %(prog)s -o output.jsonl      # Custom output path
  %(prog)s --stdout             # Print to terminal
""",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=100,
        help="Maximum number of messages to extract (default: 100)",
    )
    parser.add_argument(
        "--since",
        type=str,
        help="Only include messages after this date (YYYY-MM-DD or ISO format)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output file path (default: .claude/user-messages-{timestamp}.jsonl)",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        help="Working directory to use (default: current directory)",
    )
    parser.add_argument(
        "--exclude-agents",
        action="store_true",
        help="Exclude agent session files (agent-*.jsonl)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print messages to stdout instead of writing to file",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose progress information",
    )

    args = parser.parse_args()

    logger = Logger(verbose=args.verbose)

    # Parse since date if provided
    since = None
    if args.since:
        try:
            # Try ISO format first
            since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
        except ValueError:
            try:
                # Try YYYY-MM-DD format
                since = datetime.strptime(args.since, "%Y-%m-%d")
            except ValueError:
                logger.error(f"Invalid date format: {args.since}")
                logger.error("Use YYYY-MM-DD or ISO format")
                return 1

    # Get project folder
    cwd = args.cwd or Path.cwd()
    project_folder = get_project_folder(cwd)

    if project_folder is None:
        logger.error(f"No Claude project folder found for: {cwd}")
        logger.error(f"Expected: ~/.claude/projects/{str(cwd).replace('/', '-')}")
        return 1

    logger.info(f"Project folder: {project_folder}")
    logger.info(f"Limit: {args.limit}")
    if since:
        logger.info(f"Since: {since}")

    # Extract messages
    messages = extract_user_messages(
        project_folder=project_folder,
        limit=args.limit,
        since=since,
        include_agent_sessions=not args.exclude_agents,
    )

    if not messages:
        logger.warning("No user messages found")
        return 0

    logger.info(f"Found {len(messages)} messages")

    # Output messages
    if args.stdout:
        print_messages_to_stdout(messages)
    else:
        output_path = save_messages(messages, args.output)
        logger.success(f"Saved {len(messages)} messages to: {output_path}")

    return 0


def main_loop() -> int:
    """Entry point for ll-loop command.

    Execute FSM-based automation loops.

    Returns:
        Exit code (0 = success)
    """
    import yaml

    from little_loops.fsm.compilers import compile_paradigm
    from little_loops.fsm.persistence import (
        PersistentExecutor,
        StatePersistence,
        get_loop_history,
        list_running_loops,
    )
    from little_loops.fsm.schema import FSMLoop
    from little_loops.fsm.validation import load_and_validate

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

    args = parser.parse_args(argv)

    logger = Logger(verbose=not getattr(args, "quiet", False))

    def resolve_loop_path(name_or_path: str) -> Path:
        """Resolve loop name to path, preferring compiled FSM over paradigm."""
        path = Path(name_or_path)
        if path.exists():
            return path

        # Try .loops/<name>.fsm.yaml first (compiled FSM)
        fsm_path = Path(".loops") / f"{name_or_path}.fsm.yaml"
        if fsm_path.exists():
            return fsm_path

        # Fall back to .loops/<name>.yaml (paradigm)
        loops_path = Path(".loops") / f"{name_or_path}.yaml"
        if loops_path.exists():
            return loops_path

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

        # Execute
        executor = PersistentExecutor(fsm)
        return run_foreground(executor, fsm)

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
            "states": {name: _state_to_dict(state) for name, state in fsm.states.items()},
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

    def _state_to_dict(state) -> dict:
        """Convert StateConfig to dict for YAML output."""
        d: dict = {}
        if state.action:
            d["action"] = state.action
        if state.evaluate:
            d["evaluate"] = {"type": state.evaluate.type}
            if state.evaluate.target is not None:
                d["evaluate"]["target"] = state.evaluate.target
            if state.evaluate.tolerance is not None:
                d["evaluate"]["tolerance"] = state.evaluate.tolerance
            if state.evaluate.previous is not None:
                d["evaluate"]["previous"] = state.evaluate.previous
            if state.evaluate.operator is not None:
                d["evaluate"]["operator"] = state.evaluate.operator
            if state.evaluate.pattern is not None:
                d["evaluate"]["pattern"] = state.evaluate.pattern
            if state.evaluate.path is not None:
                d["evaluate"]["path"] = state.evaluate.path
        if state.on_success:
            d["on_success"] = state.on_success
        if state.on_failure:
            d["on_failure"] = state.on_failure
        if state.on_error:
            d["on_error"] = state.on_error
        if state.next:
            d["next"] = state.next
        if state.route:
            d["route"] = state.route.routes
            if state.route.default:
                d["route"]["_"] = state.route.default
        if state.terminal:
            d["terminal"] = True
        if state.capture:
            d["capture"] = state.capture
        if state.timeout:
            d["timeout"] = state.timeout
        if state.on_maintain:
            d["on_maintain"] = state.on_maintain
        return d

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
        loops_dir = Path(".loops")

        if getattr(args, "running", False):
            states = list_running_loops(loops_dir)
            if not states:
                print("No running loops")
                return 0
            print("Running loops:")
            for state in states:
                print(f"  {state.loop_name}: {state.current_state} (iteration {state.iteration})")
            return 0

        # List all loop files
        if not loops_dir.exists():
            print("No .loops/ directory found")
            return 0

        yaml_files = list(loops_dir.glob("*.yaml"))
        if not yaml_files:
            print("No loops defined")
            return 0

        print("Available loops:")
        for path in sorted(yaml_files):
            print(f"  {path.stem}")
        return 0

    def cmd_status(loop_name: str) -> int:
        """Show loop status."""
        persistence = StatePersistence(loop_name)
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
        persistence = StatePersistence(loop_name)
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
        persistence = StatePersistence(loop_name)
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

        executor = PersistentExecutor(fsm)
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
        events = get_loop_history(loop_name)

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
    else:
        parser.print_help()
        return 1


def main_sprint() -> int:
    """Entry point for ll-sprint command.

    Manage and execute sprint/sequence definitions.

    Returns:
        Exit code (0 = success)
    """
    parser = argparse.ArgumentParser(
        prog="ll-sprint",
        description="Manage and execute sprint/sequence definitions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s create sprint-1 --issues BUG-001,FEAT-010 --description "Q1 fixes"
  %(prog)s run sprint-1
  %(prog)s run sprint-1 --parallel
  %(prog)s run sprint-1 --dry-run
  %(prog)s list
  %(prog)s show sprint-1
  %(prog)s delete sprint-1
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # create subcommand
    create_parser = subparsers.add_parser("create", help="Create a new sprint")
    create_parser.add_argument("name", help="Sprint name (used as filename)")
    create_parser.add_argument(
        "--issues",
        required=True,
        help="Comma-separated issue IDs (e.g., BUG-001,FEAT-010)",
    )
    create_parser.add_argument("--description", "-d", default="", help="Sprint description")
    create_parser.add_argument(
        "--mode",
        choices=["auto", "parallel"],
        default="auto",
        help="Default execution mode (default: auto)",
    )
    create_parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Default max workers for parallel mode (default: 4)",
    )
    create_parser.add_argument(
        "--timeout",
        type=int,
        default=3600,
        help="Default timeout in seconds (default: 3600)",
    )

    # run subcommand
    run_parser = subparsers.add_parser("run", help="Execute a sprint")
    run_parser.add_argument("sprint", help="Sprint name to execute")
    run_parser.add_argument(
        "--parallel",
        action="store_true",
        help="Execute in parallel mode (overrides sprint default)",
    )
    run_parser.add_argument(
        "--dry-run", "-n", action="store_true", help="Show execution plan without running"
    )
    run_parser.add_argument(
        "--max-workers",
        type=int,
        help="Override max workers for parallel mode",
    )
    run_parser.add_argument("--timeout", type=int, help="Override timeout in seconds")
    run_parser.add_argument("--config", type=Path, default=None, help="Path to project root")

    # list subcommand
    list_parser = subparsers.add_parser("list", help="List all sprints")
    list_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed information"
    )

    # show subcommand
    show_parser = subparsers.add_parser("show", help="Show sprint details")
    show_parser.add_argument("sprint", help="Sprint name to show")
    show_parser.add_argument("--config", type=Path, default=None, help="Path to project root")

    # delete subcommand
    delete_parser = subparsers.add_parser("delete", help="Delete a sprint")
    delete_parser.add_argument("sprint", help="Sprint name to delete")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Commands that don't need project root
    if args.command == "list":
        return _cmd_sprint_list(args, SprintManager())
    if args.command == "delete":
        return _cmd_sprint_delete(args, SprintManager())

    # Commands that need project root
    project_root = args.config if hasattr(args, "config") and args.config else Path.cwd()
    config = BRConfig(project_root)
    manager = SprintManager(config=config)

    if args.command == "create":
        return _cmd_sprint_create(args, manager)
    if args.command == "show":
        return _cmd_sprint_show(args, manager)
    if args.command == "run":
        return _cmd_sprint_run(args, manager, config)

    return 1


def _cmd_sprint_create(args: argparse.Namespace, manager: SprintManager) -> int:
    """Create a new sprint."""
    logger = Logger()
    issues = [i.strip().upper() for i in args.issues.split(",")]

    # Validate issues exist
    valid = manager.validate_issues(issues)
    invalid = set(issues) - set(valid.keys())

    if invalid:
        logger.warning(f"Issue IDs not found: {', '.join(sorted(invalid))}")

    options = SprintOptions(
        mode=args.mode,
        max_workers=args.max_workers,
        timeout=args.timeout,
    )

    sprint = manager.create(
        name=args.name,
        issues=issues,
        description=args.description,
        options=options,
    )

    logger.success(f"Created sprint: {sprint.name}")
    logger.info(f"  Description: {sprint.description or '(none)'}")
    logger.info(f"  Issues: {', '.join(sprint.issues)}")
    logger.info(f"  Mode: {sprint.options.mode if sprint.options else 'auto'}")
    logger.info(f"  File: .sprints/{sprint.name}.yaml")

    if invalid:
        logger.warning(f"  Invalid issues: {', '.join(sorted(invalid))}")

    return 0


def _cmd_sprint_show(args: argparse.Namespace, manager: SprintManager) -> int:
    """Show sprint details."""
    logger = Logger()
    sprint = manager.load(args.sprint)
    if not sprint:
        logger.error(f"Sprint not found: {args.sprint}")
        return 1

    # Validate issues
    valid = manager.validate_issues(sprint.issues)
    invalid = set(sprint.issues) - set(valid.keys())

    print(f"Sprint: {sprint.name}")
    print(f"Description: {sprint.description or '(none)'}")
    print(f"Created: {sprint.created}")
    print(f"Issues ({len(sprint.issues)}):")

    for issue_id in sprint.issues:
        status = "valid" if issue_id in valid else "NOT FOUND"
        print(f"  - {issue_id} ({status})")

    if sprint.options:
        print("Options:")
        print(f"  Mode: {sprint.options.mode}")
        print(f"  Max iterations: {sprint.options.max_iterations}")
        print(f"  Timeout: {sprint.options.timeout}s")
        print(f"  Max workers: {sprint.options.max_workers}")

    if invalid:
        print(f"\nWarning: {len(invalid)} issue(s) not found")

    return 0


def _cmd_sprint_list(args: argparse.Namespace, manager: SprintManager) -> int:
    """List all sprints."""
    sprints = manager.list_all()

    if not sprints:
        print("No sprints defined")
        return 0

    print(f"Available sprints ({len(sprints)}):")

    for sprint in sprints:
        if args.verbose:
            print(f"\n{sprint.name}:")
            print(f"  Description: {sprint.description or '(none)'}")
            print(f"  Issues: {', '.join(sprint.issues)}")
            print(f"  Created: {sprint.created}")
        else:
            desc = f" - {sprint.description}" if sprint.description else ""
            print(f"  {sprint.name}{desc}")

    return 0


def _cmd_sprint_delete(args: argparse.Namespace, manager: SprintManager) -> int:
    """Delete a sprint."""
    logger = Logger()
    if not manager.delete(args.sprint):
        logger.error(f"Sprint not found: {args.sprint}")
        return 1

    logger.success(f"Deleted sprint: {args.sprint}")
    return 0


def _cmd_sprint_run(
    args: argparse.Namespace,
    manager: SprintManager,
    config: BRConfig,
) -> int:
    """Execute a sprint."""
    logger = Logger()
    sprint = manager.load(args.sprint)
    if not sprint:
        logger.error(f"Sprint not found: {args.sprint}")
        return 1

    # Validate issues exist
    valid = manager.validate_issues(sprint.issues)
    invalid = set(sprint.issues) - set(valid.keys())

    if invalid:
        logger.error(f"Issue IDs not found: {', '.join(sorted(invalid))}")
        logger.info("Cannot execute sprint with missing issues")
        return 1

    # Determine execution mode
    parallel = args.parallel or (sprint.options and sprint.options.mode == "parallel")

    logger.info(f"Running sprint: {sprint.name}")
    logger.info(f"  Mode: {'parallel' if parallel else 'sequential'}")
    logger.info(f"  Issues: {', '.join(sprint.issues)}")

    if args.dry_run:
        logger.info("\nDry run mode - no changes will be made")
        return 0

    # Build only_ids set for filtering
    only_ids = set(sprint.issues)

    if parallel:
        # Execute via ParallelOrchestrator
        max_workers = args.max_workers or (sprint.options.max_workers if sprint.options else 4)

        parallel_config = config.create_parallel_config(
            max_workers=max_workers,
            only_ids=only_ids,
            dry_run=args.dry_run,
        )

        orchestrator = ParallelOrchestrator(parallel_config, config, Path.cwd())
        return orchestrator.run()
    else:
        # Execute via AutoManager
        auto_manager = AutoManager(
            config=config,
            dry_run=args.dry_run,
            only_ids=only_ids,
        )
        return auto_manager.run()


if __name__ == "__main__":
    sys.exit(main_auto())
