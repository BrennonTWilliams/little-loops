"""CLI entry points for little-loops.

Provides command-line interfaces for automated issue management:
- ll-auto: Sequential issue processing
- ll-parallel: Parallel issue processing with git worktrees
- ll-messages: Extract user messages from Claude Code logs
- ll-sprint: Sprint and sequence management
- ll-sync: GitHub Issues sync
"""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path
from types import FrameType
from typing import Any

from little_loops.cli_args import (
    add_common_auto_args,
    add_config_arg,
    add_dry_run_arg,
    add_max_issues_arg,
    add_max_workers_arg,
    add_only_arg,
    add_quiet_arg,
    add_resume_arg,
    add_skip_analysis_arg,
    add_skip_arg,
    add_timeout_arg,
    parse_issue_ids,
)
from little_loops.config import BRConfig
from little_loops.dependency_graph import (
    DependencyGraph,
    WaveContentionNote,
    refine_waves_for_contention,
)
from little_loops.issue_manager import AutoManager
from little_loops.logger import Logger, format_duration
from little_loops.parallel.orchestrator import ParallelOrchestrator
from little_loops.sprint import SprintManager, SprintOptions, SprintState
from little_loops.sync import GitHubSyncManager, SyncResult, SyncStatus

# Module-level shutdown flag for ll-sprint signal handling (ENH-183)
_sprint_shutdown_requested: bool = False


def _sprint_signal_handler(signum: int, frame: FrameType | None) -> None:
    """Handle shutdown signals gracefully for ll-sprint.

    First signal: Set shutdown flag for graceful exit after current wave.
    Second signal: Force immediate exit.
    """
    global _sprint_shutdown_requested
    if _sprint_shutdown_requested:
        # Second signal - force exit
        print("\nForce shutdown requested", file=sys.stderr)
        sys.exit(1)
    _sprint_shutdown_requested = True
    print("\nShutdown requested, will exit after current wave...", file=sys.stderr)


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

    # Add common arguments from shared module
    add_common_auto_args(parser)

    # Add tool-specific arguments
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        default=None,
        help="Filter to specific category (bugs, features, enhancements)",
    )

    args = parser.parse_args()

    project_root = args.config or Path.cwd()
    config = BRConfig(project_root)

    # Parse issue ID filters
    only_ids = parse_issue_ids(args.only)
    skip_ids = parse_issue_ids(args.skip)

    manager = AutoManager(
        config=config,
        dry_run=args.dry_run,
        max_issues=args.max_issues,
        resume=args.resume,
        category=args.category,
        only_ids=only_ids,
        skip_ids=skip_ids,
        verbose=not args.quiet,
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

    # Parallel-specific arguments (--workers, not --max-workers)
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
        "--worktree-base",
        type=Path,
        default=None,
        help="Base directory for git worktrees",
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
        "--overlap-detection",
        action="store_true",
        help="Enable pre-flight overlap detection to reduce merge conflicts (ENH-143)",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="With --overlap-detection, warn about overlaps instead of serializing",
    )

    # Add common arguments from shared module
    add_dry_run_arg(parser)
    add_resume_arg(parser)
    add_timeout_arg(parser)
    add_quiet_arg(parser)
    add_only_arg(parser)
    add_skip_arg(parser)

    # Add max-issues and config individually (different help text needed)
    add_max_issues_arg(parser)
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
    only_ids = parse_issue_ids(args.only)
    skip_ids = parse_issue_ids(args.skip)

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
        overlap_detection=args.overlap_detection,
        serialize_overlapping=not args.warn_only,
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
    import json
    from datetime import datetime

    from little_loops.user_messages import (
        CommandRecord,
        UserMessage,
        extract_commands,
        extract_user_messages,
        get_project_folder,
    )

    parser = argparse.ArgumentParser(
        description="Extract user messages from Claude Code logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Last 100 messages to file
  %(prog)s -n 50                        # Last 50 messages
  %(prog)s --since 2026-01-01           # Messages since date
  %(prog)s -o output.jsonl              # Custom output path
  %(prog)s --stdout                     # Print to terminal
  %(prog)s --include-response-context   # Include response metadata
  %(prog)s --include-commands           # Include CLI commands
  %(prog)s --commands-only              # Extract only CLI commands
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
    parser.add_argument(
        "--include-response-context",
        action="store_true",
        help="Include metadata from assistant responses (tools used, files modified)",
    )
    parser.add_argument(
        "--skip-cli",
        action="store_true",
        help="Exclude CLI commands from output (included by default)",
    )
    parser.add_argument(
        "--commands-only",
        action="store_true",
        help="Extract only CLI commands, no user messages",
    )
    parser.add_argument(
        "--tools",
        type=str,
        default="Bash",
        help="Comma-separated list of tools to extract commands from (default: Bash)",
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

    # Parse tools list
    tools_list = [t.strip() for t in args.tools.split(",")]

    # Extract data based on flags
    messages: list[UserMessage] = []
    commands: list[CommandRecord] = []

    if not args.commands_only:
        messages = extract_user_messages(
            project_folder=project_folder,
            limit=None,  # Apply limit after merging
            since=since,
            include_agent_sessions=not args.exclude_agents,
            include_response_context=args.include_response_context,
        )

    if not args.skip_cli or args.commands_only:
        commands = extract_commands(
            project_folder=project_folder,
            limit=None,  # Apply limit after merging
            since=since,
            include_agent_sessions=not args.exclude_agents,
            tools=tools_list,
        )

    if not messages and not commands:
        logger.warning("No user messages or commands found")
        return 0

    # Merge and sort by timestamp
    combined: list[UserMessage | CommandRecord] = []
    combined.extend(messages)
    combined.extend(commands)
    combined.sort(key=lambda x: x.timestamp, reverse=True)

    # Apply limit
    if args.limit is not None:
        combined = combined[: args.limit]

    msg_count = len([x for x in combined if isinstance(x, UserMessage)])
    cmd_count = len([x for x in combined if isinstance(x, CommandRecord)])
    logger.info(f"Found {msg_count} messages, {cmd_count} commands")

    # Output
    if args.stdout:
        for item in combined:
            print(json.dumps(item.to_dict()))
    else:
        output_path = _save_combined(combined, args.output)
        logger.success(f"Saved {len(combined)} records to: {output_path}")

    return 0


def _save_combined(
    items: list,
    output_path: Path | None = None,
) -> Path:
    """Save combined messages and commands to JSONL file."""
    import json
    from datetime import datetime

    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = Path.cwd() / ".claude"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"user-messages-{timestamp}.jsonl"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item.to_dict()) + "\n")

    return output_path


def main_loop() -> int:
    """Entry point for ll-loop command.

    Execute FSM-based automation loops.

    Returns:
        Exit code (0 = success)
    """
    import yaml

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

    args = parser.parse_args(argv)

    logger = Logger(verbose=not getattr(args, "quiet", False))

    def get_builtin_loops_dir() -> Path:
        """Get the path to built-in loops bundled with the plugin."""
        return Path(__file__).parent.parent.parent / "loops"

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
        lock_manager = LockManager()
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
            executor = PersistentExecutor(fsm)
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

        loops_dir = Path(".loops")
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
            print("✓ Loop structure is valid (no check action to execute)")
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
            print("✓ Loop structure is valid (slash command not executed)")
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
            print(f"Would transition: {initial} → {next_state}")
        else:
            print(f"Would transition: {initial} → (no route for '{verdict}')")

        # Summary
        print()
        has_error = eval_result.verdict == "error" or "error" in eval_result.details
        if has_error:
            print("⚠ Loop has issues - review the error details above")
            return 1
        else:
            print("✓ Loop appears to be configured correctly")
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
                print(f"    Transition: {from_state} → {to_state}")

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
        print(f"States visited: {' → '.join(states_visited)}")
        print(f"Iterations: {result.iterations}")
        print(f"Would have executed {len(sim_runner.calls)} commands")
        print(f"Terminated by: {result.terminated_by}")

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
    add_max_workers_arg(create_parser, default=2)
    add_timeout_arg(create_parser, default=3600)
    add_skip_arg(
        create_parser,
        help_text="Comma-separated list of issue IDs to exclude from sprint (e.g., BUG-003,FEAT-004)",
    )

    # run subcommand
    run_parser = subparsers.add_parser("run", help="Execute a sprint")
    run_parser.add_argument("sprint", help="Sprint name to execute")
    add_dry_run_arg(run_parser)
    add_max_workers_arg(run_parser)
    add_timeout_arg(run_parser)
    add_config_arg(run_parser)
    add_resume_arg(run_parser)
    add_quiet_arg(run_parser)
    add_skip_arg(
        run_parser,
        help_text="Comma-separated list of issue IDs to skip during execution (e.g., BUG-003,FEAT-004)",
    )
    add_skip_analysis_arg(run_parser)

    # list subcommand
    list_parser = subparsers.add_parser("list", help="List all sprints")
    list_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed information"
    )

    # show subcommand
    show_parser = subparsers.add_parser("show", help="Show sprint details")
    show_parser.add_argument("sprint", help="Sprint name to show")
    add_config_arg(show_parser)
    add_skip_analysis_arg(show_parser)

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

    # Apply skip filter if provided
    skip_ids = parse_issue_ids(args.skip)
    if skip_ids:
        original_count = len(issues)
        issues = [i for i in issues if i not in skip_ids]
        skipped = original_count - len(issues)
        if skipped > 0:
            logger.info(
                f"Skipping {skipped} issue(s): {', '.join(sorted(skip_ids & set(issues) | skip_ids))}"
            )

    # Validate issues exist
    valid = manager.validate_issues(issues)
    invalid = set(issues) - set(valid.keys())

    if invalid:
        logger.warning(f"Issue IDs not found: {', '.join(sorted(invalid))}")

    options = SprintOptions(
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
    logger.info(f"  File: .sprints/{sprint.name}.yaml")

    if invalid:
        logger.warning(f"  Invalid issues: {', '.join(sorted(invalid))}")

    return 0


def _render_execution_plan(
    waves: list[list[Any]],
    dep_graph: DependencyGraph,
    contention_notes: list[WaveContentionNote | None] | None = None,
) -> str:
    """Render execution plan with wave groupings.

    Args:
        waves: List of execution waves from get_execution_waves()
        dep_graph: DependencyGraph for looking up blockers
        contention_notes: Optional per-wave contention annotations from
            refine_waves_for_contention(). Same length as waves.

    Returns:
        Formatted string showing wave structure
    """
    if not waves:
        return ""

    total_issues = sum(len(wave) for wave in waves)
    lines: list[str] = []

    lines.append("")
    lines.append("=" * 70)
    lines.append(f"EXECUTION PLAN ({total_issues} issues, {len(waves)} waves)")
    lines.append("=" * 70)

    for wave_num, wave in enumerate(waves, 1):
        lines.append("")
        if wave_num == 1:
            parallel_note = "(parallel)" if len(wave) > 1 else ""
        else:
            parallel_note = f"(after Wave {wave_num - 1})"
            if len(wave) > 1:
                parallel_note += " parallel"
        lines.append(f"Wave {wave_num} {parallel_note}:".strip())

        for i, issue in enumerate(wave):
            is_last = i == len(wave) - 1
            prefix = "  └── " if is_last else "  ├── "

            # Truncate title if too long
            title = issue.title
            if len(title) > 45:
                title = title[:42] + "..."

            lines.append(f"{prefix}{issue.issue_id}: {title} ({issue.priority})")

            # Show blockers for this issue
            blockers = dep_graph.blocked_by.get(issue.issue_id, set())
            if blockers:
                blocker_prefix = "      └── " if is_last else "  │   └── "
                blockers_str = ", ".join(sorted(blockers))
                lines.append(f"{blocker_prefix}blocked by: {blockers_str}")

        # Show file contention annotation if this wave was split
        if contention_notes and wave_num <= len(contention_notes):
            note = contention_notes[wave_num - 1]
            if note:
                lines.append(
                    f"  \u26a0  File contention \u2014 sub-wave "
                    f"{note.sub_wave_index + 1}/{note.total_sub_waves}"
                )
                paths_str = ", ".join(note.contended_paths[:3])
                if len(note.contended_paths) > 3:
                    paths_str += f" +{len(note.contended_paths) - 3} more"
                lines.append(f"     Contended: {paths_str}")

    return "\n".join(lines)


def _render_dependency_graph(
    waves: list[list[Any]],
    dep_graph: DependencyGraph,
) -> str:
    """Render ASCII dependency graph.

    Args:
        waves: List of execution waves
        dep_graph: DependencyGraph for looking up relationships

    Returns:
        Formatted string showing dependency arrows
    """
    if not waves or len(waves) <= 1:
        return ""

    lines: list[str] = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("DEPENDENCY GRAPH")
    lines.append("=" * 70)
    lines.append("")

    # Build chains: track which issues block what
    # Show each independent chain on its own line
    chains: list[str] = []
    visited: set[str] = set()

    def build_chain(issue_id: str) -> str:
        """Recursively build chain string from issue."""
        if issue_id in visited:
            return issue_id
        visited.add(issue_id)

        blocked_issues = sorted(dep_graph.blocks.get(issue_id, set()))
        if not blocked_issues:
            return issue_id

        if len(blocked_issues) == 1:
            return f"{issue_id} ──→ {build_chain(blocked_issues[0])}"
        else:
            # Multiple branches - show first inline, note others
            result = f"{issue_id} ──→ {build_chain(blocked_issues[0])}"
            for other in blocked_issues[1:]:
                if other not in visited:
                    chains.append(f"  {issue_id} ──→ {build_chain(other)}")
            return result

    # Find root issues (no blockers in this graph)
    roots: list[str] = []
    for wave in waves[:1]:  # First wave has roots
        for issue in wave:
            roots.append(issue.issue_id)

    for root in roots:
        if root not in visited:
            chain = build_chain(root)
            if chain:
                chains.insert(0, f"  {chain}")

    # Handle any isolated issues not in chains
    all_ids = {issue.issue_id for wave in waves for issue in wave}
    for issue_id in sorted(all_ids - visited):
        chains.append(f"  {issue_id}")

    lines.extend(chains)
    lines.append("")
    lines.append("Legend: ──→ blocks (must complete before)")

    return "\n".join(lines)


def _cmd_sprint_show(args: argparse.Namespace, manager: SprintManager) -> int:
    """Show sprint details with dependency visualization."""
    logger = Logger()
    sprint = manager.load(args.sprint)
    if not sprint:
        logger.error(f"Sprint not found: {args.sprint}")
        return 1

    # Validate issues
    valid = manager.validate_issues(sprint.issues)
    invalid = set(sprint.issues) - set(valid.keys())

    # Load full IssueInfo objects for dependency analysis
    issue_infos = manager.load_issue_infos(list(valid.keys()))
    dep_graph: DependencyGraph | None = None
    waves: list[list[Any]] = []
    contention_notes: list[WaveContentionNote | None] | None = None
    has_cycles = False

    if issue_infos:
        dep_graph = DependencyGraph.from_issues(issue_infos)
        has_cycles = dep_graph.has_cycles()

        if not has_cycles:
            waves = dep_graph.get_execution_waves()
            waves, contention_notes = refine_waves_for_contention(waves)

    print(f"Sprint: {sprint.name}")
    print(f"Description: {sprint.description or '(none)'}")
    print(f"Created: {sprint.created}")

    # Show execution plan if we have dependency info and no cycles
    if waves and dep_graph:
        print(_render_execution_plan(waves, dep_graph, contention_notes))
        print(_render_dependency_graph(waves, dep_graph))
    else:
        # Fallback to simple list if no valid issues or cycles
        print(f"Issues ({len(sprint.issues)}):")
        for issue_id in sprint.issues:
            status = "valid" if issue_id in valid else "NOT FOUND"
            print(f"  - {issue_id} ({status})")

        # Warn about cycles if detected
        if has_cycles and dep_graph:
            cycles = dep_graph.detect_cycles()
            print("\nWarning: Dependency cycles detected:")
            for cycle in cycles:
                print(f"  {' -> '.join(cycle)}")

    # Dependency analysis (ENH-301)
    if issue_infos and not args.skip_analysis:
        from little_loops.dependency_mapper import analyze_dependencies

        issue_contents = _build_issue_contents(issue_infos)
        dep_report = analyze_dependencies(issue_infos, issue_contents)
        _render_dependency_analysis(dep_report, logger)

    if sprint.options:
        print("\nOptions:")
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


def _get_sprint_state_file() -> Path:
    """Get path to sprint state file."""
    return Path.cwd() / ".sprint-state.json"


def _load_sprint_state(logger: Logger) -> SprintState | None:
    """Load sprint state from file."""
    import json

    state_file = _get_sprint_state_file()
    if not state_file.exists():
        return None
    try:
        data = json.loads(state_file.read_text())
        state = SprintState.from_dict(data)
        logger.info(f"State loaded from {state_file}")
        return state
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to load state: {e}")
        return None


def _save_sprint_state(state: SprintState, logger: Logger) -> None:
    """Save sprint state to file."""
    import json
    from datetime import datetime

    state.last_checkpoint = datetime.now().isoformat()
    state_file = _get_sprint_state_file()
    state_file.write_text(json.dumps(state.to_dict(), indent=2))
    logger.info(f"State saved to {state_file}")


def _cleanup_sprint_state(logger: Logger) -> None:
    """Remove sprint state file."""
    state_file = _get_sprint_state_file()
    if state_file.exists():
        state_file.unlink()
        logger.info("Sprint state file cleaned up")


def _build_issue_contents(issue_infos: list) -> dict[str, str]:
    """Build issue_id -> file content mapping for dependency analysis."""
    return {info.issue_id: info.path.read_text() for info in issue_infos if info.path.exists()}


def _render_dependency_analysis(report: Any, logger: Logger) -> None:
    """Display dependency analysis results in CLI format."""
    if not report.proposals and not report.validation.has_issues:
        return

    logger.header("Dependency Analysis", char="-", width=60)

    if report.proposals:
        logger.warning(f"Found {len(report.proposals)} potential missing dependency(ies):")
        for p in report.proposals:
            if p.conflict_score >= 0.7:
                conflict = "HIGH"
            elif p.conflict_score >= 0.4:
                conflict = "MEDIUM"
            else:
                conflict = "LOW"
            logger.warning(
                f"  {p.source_id} may depend on {p.target_id} "
                f"({conflict} conflict, {p.confidence:.0%} confidence)"
            )
            if p.overlapping_files:
                files = ", ".join(p.overlapping_files[:3])
                if len(p.overlapping_files) > 3:
                    files += " and more"
                logger.info(f"    Shared files: {files}")

    if report.validation.has_issues:
        v = report.validation
        if v.broken_refs:
            for issue_id, ref_id in v.broken_refs:
                logger.warning(f"  {issue_id}: references nonexistent {ref_id}")
        if v.stale_completed_refs:
            for issue_id, ref_id in v.stale_completed_refs:
                logger.warning(f"  {issue_id}: blocked by {ref_id} (completed)")
        if v.missing_backlinks:
            for issue_id, ref_id in v.missing_backlinks:
                logger.warning(f"  {issue_id} blocked by {ref_id}, but {ref_id} missing backlink")

    logger.info("Run /ll:map-dependencies to apply discovered dependencies")
    print()  # blank line separator


def _cmd_sprint_run(
    args: argparse.Namespace,
    manager: SprintManager,
    config: BRConfig,
) -> int:
    """Execute a sprint with dependency-aware scheduling."""
    from datetime import datetime

    logger = Logger(verbose=not args.quiet)

    # Setup signal handlers for graceful shutdown (ENH-183)
    global _sprint_shutdown_requested
    _sprint_shutdown_requested = False  # Reset in case of multiple runs
    signal.signal(signal.SIGINT, _sprint_signal_handler)
    signal.signal(signal.SIGTERM, _sprint_signal_handler)

    sprint = manager.load(args.sprint)
    if not sprint:
        logger.error(f"Sprint not found: {args.sprint}")
        return 1

    # Apply skip filter if provided
    issues_to_process = list(sprint.issues)
    skip_ids = parse_issue_ids(args.skip)
    if skip_ids:
        original_count = len(issues_to_process)
        issues_to_process = [i for i in issues_to_process if i not in skip_ids]
        skipped = original_count - len(issues_to_process)
        if skipped > 0:
            logger.info(f"Skipping {skipped} issue(s): {', '.join(sorted(skip_ids))}")

    # Validate issues exist
    valid = manager.validate_issues(issues_to_process)
    invalid = set(issues_to_process) - set(valid.keys())

    if invalid:
        logger.error(f"Issue IDs not found: {', '.join(sorted(invalid))}")
        logger.info("Cannot execute sprint with missing issues")
        return 1

    # Load full IssueInfo objects for dependency analysis
    issue_infos = manager.load_issue_infos(issues_to_process)
    if not issue_infos:
        logger.error("No issue files found")
        return 1

    # Dependency analysis (ENH-301)
    if not getattr(args, "skip_analysis", False):
        from little_loops.dependency_mapper import analyze_dependencies

        issue_contents = _build_issue_contents(issue_infos)
        dep_report = analyze_dependencies(issue_infos, issue_contents)
        _render_dependency_analysis(dep_report, logger)

    # Build dependency graph
    dep_graph = DependencyGraph.from_issues(issue_infos)

    # Detect cycles
    if dep_graph.has_cycles():
        cycles = dep_graph.detect_cycles()
        for cycle in cycles:
            logger.error(f"Dependency cycle detected: {' -> '.join(cycle)}")
        return 1

    # Get execution waves
    try:
        waves = dep_graph.get_execution_waves()
    except ValueError as e:
        logger.error(str(e))
        return 1

    # Refine waves for file contention (ENH-306)
    waves, contention_notes = refine_waves_for_contention(waves)

    # Display execution plan
    logger.info(f"Running sprint: {sprint.name}")
    logger.info("Dependency analysis:")
    for i, wave in enumerate(waves, 1):
        issue_ids = ", ".join(issue.issue_id for issue in wave)
        note = contention_notes[i - 1] if contention_notes else None
        if note:
            logger.info(
                f"  Wave {i}: {issue_ids}"
                f" [sub-wave {note.sub_wave_index + 1}/{note.total_sub_waves}]"
            )
        else:
            logger.info(f"  Wave {i}: {issue_ids}")

    if args.dry_run:
        logger.info("\nDry run mode - no changes will be made")
        return 0

    # Initialize or load state
    state: SprintState
    start_wave = 1

    if args.resume:
        loaded_state = _load_sprint_state(logger)
        if loaded_state and loaded_state.sprint_name == args.sprint:
            state = loaded_state
            # Find first incomplete wave by checking completed issues
            completed_set = set(state.completed_issues)
            for i, wave in enumerate(waves, 1):
                wave_issue_ids = {issue.issue_id for issue in wave}
                if not wave_issue_ids.issubset(completed_set):
                    start_wave = i
                    break
            else:
                # All waves completed
                logger.info("Sprint already completed - nothing to resume")
                _cleanup_sprint_state(logger)
                return 0
            logger.info(f"Resuming from wave {start_wave}/{len(waves)}")
            logger.info(f"  Previously completed: {len(state.completed_issues)} issues")
        else:
            if loaded_state:
                logger.warning(
                    f"State file is for sprint '{loaded_state.sprint_name}', "
                    f"not '{args.sprint}' - starting fresh"
                )
            else:
                logger.warning("No valid state found - starting fresh")
            state = SprintState(
                sprint_name=args.sprint,
                started_at=datetime.now().isoformat(),
            )
    else:
        # Fresh start - delete any old state
        _cleanup_sprint_state(logger)
        state = SprintState(
            sprint_name=args.sprint,
            started_at=datetime.now().isoformat(),
        )

    # Track exit status for error handling (ENH-185)
    exit_code = 0

    try:
        # Determine max workers
        max_workers = args.max_workers or (sprint.options.max_workers if sprint.options else 2)

        # Execute wave by wave
        completed: set[str] = set(state.completed_issues)
        failed_waves = 0
        total_duration = 0.0
        total_waves = len(waves)

        for wave_num, wave in enumerate(waves, 1):
            # Check for shutdown request (ENH-183)
            if _sprint_shutdown_requested:
                logger.warning("Shutdown requested - saving state and exiting")
                _save_sprint_state(state, logger)
                exit_code = 1
                return exit_code

            # Skip already-completed waves when resuming
            if wave_num < start_wave:
                continue

            wave_ids = [issue.issue_id for issue in wave]
            state.current_wave = wave_num
            logger.info(f"\nProcessing wave {wave_num}/{total_waves}: {', '.join(wave_ids)}")

            if len(wave) == 1:
                # Single issue — process in-place (no worktree overhead)
                from little_loops.issue_manager import process_issue_inplace

                issue_result = process_issue_inplace(
                    info=wave[0],
                    config=config,
                    logger=logger,
                    dry_run=args.dry_run,
                )
                total_duration += issue_result.duration
                if issue_result.success:
                    completed.update(wave_ids)
                    state.completed_issues.extend(wave_ids)
                    state.timing[wave_ids[0]] = {"total": issue_result.duration}
                    logger.success(f"Wave {wave_num}/{total_waves} completed: {wave_ids[0]}")
                else:
                    failed_waves += 1
                    completed.update(wave_ids)
                    state.completed_issues.extend(wave_ids)
                    state.failed_issues[wave_ids[0]] = "Issue processing failed"
                    logger.warning(f"Wave {wave_num}/{total_waves} had failures")
                _save_sprint_state(state, logger)
                if wave_num < total_waves:
                    logger.info(f"Continuing to wave {wave_num + 1}/{total_waves}...")
                    # Check for shutdown before next wave (ENH-183)
                    if _sprint_shutdown_requested:
                        logger.warning("Shutdown requested - exiting after wave completion")
                        exit_code = 1
                        return exit_code
            else:
                # Multi-issue — use ParallelOrchestrator with worktrees
                only_ids = set(wave_ids)
                parallel_config = config.create_parallel_config(
                    max_workers=min(max_workers, len(wave)),
                    only_ids=only_ids,
                    dry_run=args.dry_run,
                    overlap_detection=True,
                    serialize_overlapping=True,
                )

                orchestrator = ParallelOrchestrator(
                    parallel_config, config, Path.cwd(), wave_label=f"Wave {wave_num}/{total_waves}"
                )
                result = orchestrator.run()
                total_duration += orchestrator.execution_duration

                # Track completed/failed from this wave using per-issue results
                actually_completed = set(orchestrator.queue.completed_ids)
                actually_failed = set(orchestrator.queue.failed_ids)

                for issue_id in wave_ids:
                    if issue_id in actually_completed:
                        completed.add(issue_id)
                        state.completed_issues.append(issue_id)
                        state.timing[issue_id] = {
                            "total": orchestrator.execution_duration / len(wave)
                        }
                    elif issue_id in actually_failed:
                        completed.add(issue_id)
                        state.completed_issues.append(issue_id)
                        state.failed_issues[issue_id] = "Issue failed during wave execution"
                    # else: issue was neither completed nor failed (interrupted/stranded)
                    # — leave untracked so it can be retried on resume

                if result == 0:
                    logger.success(
                        f"Wave {wave_num}/{total_waves} completed: {', '.join(wave_ids)}"
                    )
                else:
                    failed_waves += 1
                    logger.warning(f"Wave {wave_num}/{total_waves} had failures")
                _save_sprint_state(state, logger)
                if wave_num < total_waves:
                    logger.info(f"Continuing to wave {wave_num + 1}/{total_waves}...")
                    # Check for shutdown before next wave (ENH-183)
                    if _sprint_shutdown_requested:
                        logger.warning("Shutdown requested - exiting after wave completion")
                        exit_code = 1
                        return exit_code

        wave_word = "wave" if len(waves) == 1 else "waves"
        logger.info(
            f"\nSprint completed: {len(completed)} issues processed ({len(waves)} {wave_word})"
        )
        logger.timing(f"Total execution time: {format_duration(total_duration)}")
        if failed_waves > 0:
            logger.warning(f"{failed_waves} wave(s) had failures")
            exit_code = 1
        else:
            # Clean up state on successful completion
            _cleanup_sprint_state(logger)

    except KeyboardInterrupt:
        # Belt-and-suspenders with signal handler (ENH-185)
        logger.warning("Sprint interrupted by user (KeyboardInterrupt)")
        exit_code = 130

    except Exception as e:
        # Catch unexpected exceptions (ENH-185)
        logger.error(f"Sprint failed unexpectedly: {e}")
        exit_code = 1

    finally:
        # Guaranteed state save on any non-success exit (ENH-185)
        if exit_code != 0:
            _save_sprint_state(state, logger)
            logger.info("State saved before exit")

    return exit_code


def main_history() -> int:
    """Entry point for ll-history command.

    Display summary statistics and analysis for completed issues.

    Returns:
        Exit code (0 = success)
    """
    from little_loops.issue_history import (
        calculate_analysis,
        calculate_summary,
        format_analysis_json,
        format_analysis_markdown,
        format_analysis_text,
        format_analysis_yaml,
        format_summary_json,
        format_summary_text,
        scan_completed_issues,
    )

    parser = argparse.ArgumentParser(
        prog="ll-history",
        description="Display summary statistics and analysis for completed issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s summary              # Show summary statistics
  %(prog)s summary --json       # Output as JSON
  %(prog)s analyze              # Full analysis report
  %(prog)s analyze --format markdown  # Markdown report
  %(prog)s analyze --compare 30 # Compare last 30 days to previous
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # summary subcommand (existing)
    summary_parser = subparsers.add_parser("summary", help="Show issue statistics")
    summary_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of formatted text",
    )
    summary_parser.add_argument(
        "-d",
        "--directory",
        type=Path,
        default=None,
        help="Path to issues directory (default: .issues)",
    )

    # analyze subcommand (new - FEAT-110)
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Full analysis with trends, subsystems, and debt metrics",
    )
    analyze_parser.add_argument(
        "-f",
        "--format",
        type=str,
        choices=["text", "json", "markdown", "yaml"],
        default="text",
        help="Output format (default: text)",
    )
    analyze_parser.add_argument(
        "-d",
        "--directory",
        type=Path,
        default=None,
        help="Path to issues directory (default: .issues)",
    )
    analyze_parser.add_argument(
        "-p",
        "--period",
        type=str,
        choices=["weekly", "monthly", "quarterly"],
        default="monthly",
        help="Grouping period for trends (default: monthly)",
    )
    analyze_parser.add_argument(
        "-c",
        "--compare",
        type=int,
        default=None,
        metavar="DAYS",
        help="Compare last N days to previous N days",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Determine directories
    issues_dir = args.directory or Path.cwd() / ".issues"
    completed_dir = issues_dir / "completed"

    if args.command == "summary":
        # Existing summary logic
        issues = scan_completed_issues(completed_dir)
        summary = calculate_summary(issues)

        if args.json:
            print(format_summary_json(summary))
        else:
            print(format_summary_text(summary))

        return 0

    if args.command == "analyze":
        # New analyze logic (FEAT-110)
        issues = scan_completed_issues(completed_dir)
        analysis = calculate_analysis(
            issues,
            issues_dir=issues_dir,
            period_type=args.period,
            compare_days=args.compare,
        )

        if args.format == "json":
            print(format_analysis_json(analysis))
        elif args.format == "yaml":
            print(format_analysis_yaml(analysis))
        elif args.format == "markdown":
            print(format_analysis_markdown(analysis))
        else:
            print(format_analysis_text(analysis))

        return 0

    return 1


# =============================================================================
# ll-sync: GitHub Issues Sync
# =============================================================================


def main_sync() -> int:
    """Entry point for ll-sync command.

    Sync local issues with GitHub Issues.

    Returns:
        Exit code (0 = success)
    """
    parser = argparse.ArgumentParser(
        prog="ll-sync",
        description="Sync local .issues/ files with GitHub Issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s status             # Show sync status
  %(prog)s push               # Push all local issues to GitHub
  %(prog)s push BUG-123       # Push specific issue
  %(prog)s pull               # Pull GitHub Issues to local
""",
    )

    subparsers = parser.add_subparsers(dest="action", help="Sync action")

    # Status subcommand
    subparsers.add_parser("status", help="Show sync status")

    # Push subcommand
    push_parser = subparsers.add_parser("push", help="Push local issues to GitHub")
    push_parser.add_argument(
        "issue_ids",
        nargs="*",
        help="Specific issue IDs to push (e.g., BUG-123)",
    )

    # Pull subcommand
    pull_parser = subparsers.add_parser("pull", help="Pull GitHub Issues to local")
    pull_parser.add_argument(
        "--labels",
        "-l",
        type=str,
        help="Filter by labels (comma-separated)",
    )

    # Common args
    add_config_arg(parser)
    add_quiet_arg(parser)
    add_dry_run_arg(parser)

    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        return 1

    project_root = args.config or Path.cwd()
    config = BRConfig(project_root)
    logger = Logger(verbose=not getattr(args, "quiet", False))

    # Check sync is enabled
    if not config.sync.enabled:
        logger.error("Sync is not enabled. Add to .claude/ll-config.json:")
        logger.error('  "sync": { "enabled": true }')
        return 1

    dry_run = getattr(args, "dry_run", False)
    manager = GitHubSyncManager(config, logger, dry_run=dry_run)

    if args.action == "status":
        status = manager.get_status()
        _print_sync_status(status, logger)
        return 0

    elif args.action == "push":
        if dry_run:
            logger.info("[DRY RUN] Showing what would be pushed (no changes will be made)")
        issue_ids = args.issue_ids if args.issue_ids else None
        result = manager.push_issues(issue_ids)
        _print_sync_result(result, logger)
        return 0 if result.success else 1

    elif args.action == "pull":
        if dry_run:
            logger.info("[DRY RUN] Showing what would be pulled (no changes will be made)")
        labels = args.labels.split(",") if args.labels else None
        result = manager.pull_issues(labels)
        _print_sync_result(result, logger)
        return 0 if result.success else 1

    return 1


def _print_sync_status(status: SyncStatus, logger: Logger) -> None:
    """Print sync status in formatted output."""
    logger.info("=" * 80)
    logger.info("SYNC STATUS")
    logger.info("=" * 80)
    logger.info(f"Provider: {status.provider}")
    logger.info(f"Repository: {status.repo}")
    logger.info("")
    logger.info(f"Local Issues:     {status.local_total}")
    logger.info(f"Synced to GitHub: {status.local_synced}")
    logger.info(f"GitHub Issues:    {status.github_total}")
    logger.info("")
    logger.info(f"Unsynced local:   {status.local_unsynced}  (local only, not on GitHub)")
    logger.info(f"GitHub-only:      {status.github_only}  (on GitHub, not local)")
    logger.info("=" * 80)


def _print_sync_result(result: SyncResult, logger: Logger) -> None:
    """Print sync result in formatted output."""
    logger.info("=" * 80)
    logger.info(f"SYNC {result.action.upper()} {'COMPLETE' if result.success else 'FAILED'}")
    logger.info("=" * 80)
    logger.info("")
    logger.info("## SUMMARY")
    logger.info(f"- Created: {len(result.created)}")
    logger.info(f"- Updated: {len(result.updated)}")
    logger.info(f"- Skipped: {len(result.skipped)}")
    logger.info(f"- Failed:  {len(result.failed)}")
    logger.info("")
    if result.created:
        logger.info("## CREATED")
        for item in result.created:
            logger.info(f"  - {item}")
        logger.info("")
    if result.updated:
        logger.info("## UPDATED")
        for item in result.updated:
            logger.info(f"  - {item}")
        logger.info("")
    if result.failed:
        logger.info("## FAILED")
        for issue_id, reason in result.failed:
            logger.error(f"  - {issue_id}: {reason}")
        logger.info("")
    if result.errors:
        logger.info("## ERRORS")
        for error in result.errors:
            logger.error(f"  - {error}")
    logger.info("=" * 80)


def main_verify_docs() -> int:
    """Entry point for ll-verify-docs command.

    Verify that documented counts (commands, agents, skills) match actual file counts.

    Returns:
        Exit code (0 = all match, 1 = mismatches found)
    """
    from little_loops.doc_counts import (
        fix_counts,
        format_result_json,
        format_result_markdown,
        format_result_text,
        verify_documentation,
    )

    parser = argparse.ArgumentParser(
        prog="ll-verify-docs",
        description="Verify documented counts match actual file counts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Check and show results
  %(prog)s --json             # Output as JSON
  %(prog)s --format markdown  # Markdown report
  %(prog)s --fix              # Auto-fix mismatches

Exit codes:
  0 - All counts match
  1 - Mismatches found
  2 - Error occurred
""",
    )

    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    parser.add_argument(
        "-f",
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format (default: text)",
    )

    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix count mismatches in documentation files",
    )

    parser.add_argument(
        "-C",
        "--directory",
        type=Path,
        default=None,
        help="Base directory (default: current directory)",
    )

    args = parser.parse_args()

    # Determine base directory
    base_dir = args.directory or Path.cwd()

    # Run verification
    result = verify_documentation(base_dir)

    # Format output
    if args.json or args.format == "json":
        output = format_result_json(result)
    elif args.format == "markdown":
        output = format_result_markdown(result)
    else:
        output = format_result_text(result)

    print(output)

    # Auto-fix if requested
    if args.fix and not result.all_match:
        fix_result = fix_counts(base_dir, result)
        print(
            f"\nFixed {fix_result.fixed_count} count(s) in {len(fix_result.files_modified)} file(s)"
        )

    # Return exit code based on results
    return 0 if result.all_match else 1


def main_check_links() -> int:
    """Entry point for ll-check-links command.

    Check markdown documentation for broken links.

    Returns:
        Exit code (0 = all links valid, 1 = broken links found, 2 = error)
    """
    from little_loops.link_checker import (
        check_markdown_links,
        format_result_json,
        format_result_markdown,
        format_result_text,
        load_ignore_patterns,
    )

    parser = argparse.ArgumentParser(
        prog="ll-check-links",
        description="Check markdown documentation for broken links",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Check all markdown files
  %(prog)s --json             # Output as JSON
  %(prog)s --format markdown  # Markdown report
  %(prog)s docs/              # Check specific directory
  %(prog)s --ignore 'http://localhost.*'  # Ignore pattern

Exit codes:
  0 - All links valid
  1 - Broken links found
  2 - Error occurred
""",
    )

    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    parser.add_argument(
        "-f",
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format (default: text)",
    )

    parser.add_argument(
        "-C",
        "--directory",
        type=Path,
        default=None,
        help="Base directory (default: current directory)",
    )

    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="Ignore URL patterns (can be used multiple times)",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Request timeout in seconds (default: 10)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show verbose output",
    )

    args = parser.parse_args()

    # Determine base directory
    base_dir = args.directory or Path.cwd()

    # Load ignore patterns from config + CLI args
    ignore_patterns = load_ignore_patterns(base_dir)
    ignore_patterns.extend(args.ignore)

    # Run link check
    result = check_markdown_links(base_dir, ignore_patterns, args.timeout, args.verbose)

    # Format output
    if args.json or args.format == "json":
        output = format_result_json(result)
    elif args.format == "markdown":
        output = format_result_markdown(result)
    else:
        output = format_result_text(result)

    print(output)

    # Return exit code based on results
    if result.has_errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main_auto())
