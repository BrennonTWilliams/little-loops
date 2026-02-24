"""ll-loop: Execute FSM-based automation loops."""

from __future__ import annotations

import argparse
from pathlib import Path

__all__ = ["main_loop"]


def main_loop() -> int:
    """Entry point for ll-loop command.

    Execute FSM-based automation loops.

    Returns:
        Exit code (0 = success)
    """
    from little_loops.cli.loop.config_cmds import cmd_compile, cmd_install, cmd_validate
    from little_loops.cli.loop.info import cmd_history, cmd_list, cmd_show
    from little_loops.cli.loop.lifecycle import cmd_resume, cmd_status, cmd_stop
    from little_loops.cli.loop.run import cmd_run
    from little_loops.cli.loop.testing import cmd_simulate, cmd_test
    from little_loops.config import BRConfig
    from little_loops.logger import Logger

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

    logger = Logger(verbose=not getattr(args, "quiet", False))

    # Dispatch commands
    if args.command == "run":
        return cmd_run(args.loop, args, loops_dir, logger)
    elif args.command == "compile":
        return cmd_compile(args, logger)
    elif args.command == "validate":
        return cmd_validate(args.loop, loops_dir, logger)
    elif args.command == "list":
        return cmd_list(args, loops_dir)
    elif args.command == "status":
        return cmd_status(args.loop, loops_dir, logger)
    elif args.command == "stop":
        return cmd_stop(args.loop, loops_dir, logger)
    elif args.command == "resume":
        return cmd_resume(args.loop, args, loops_dir, logger)
    elif args.command == "history":
        return cmd_history(args.loop, args, loops_dir)
    elif args.command == "test":
        return cmd_test(args.loop, loops_dir, logger)
    elif args.command == "simulate":
        return cmd_simulate(args.loop, args, loops_dir, logger)
    elif args.command == "install":
        return cmd_install(args.loop, loops_dir, logger)
    elif args.command == "show":
        return cmd_show(args.loop, loops_dir, logger)
    else:
        parser.print_help()
        return 1
