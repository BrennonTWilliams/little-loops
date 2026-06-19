"""ll-loop: Execute FSM-based automation loops."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from little_loops.cli.loop.diagram_modes import _parse_show_diagrams
from little_loops.cli_args import add_context_limit_arg, add_handoff_threshold_arg
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

__all__ = ["main_loop"]


def main_loop() -> int:
    """Entry point for ll-loop command.

    Execute FSM-based automation loops.

    Returns:
        Exit code (0 = success)
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-loop", sys.argv[1:]):
        from little_loops.cli.loop.config_cmds import cmd_install, cmd_validate
        from little_loops.cli.loop.edit_routes import cmd_edit_routes
        from little_loops.cli.loop.info import (
            cmd_audit_meta,
            cmd_calibrate_budget,
            cmd_diagnose_evaluators,
            cmd_fragments,
            cmd_history,
            cmd_list,
            cmd_promote_baseline,
            cmd_show,
        )
        from little_loops.cli.loop.lifecycle import cmd_monitor, cmd_resume, cmd_status, cmd_stop
        from little_loops.cli.loop.next_loop import cmd_next_loop
        from little_loops.cli.loop.run import cmd_run
        from little_loops.cli.loop.testing import cmd_simulate, cmd_test
        from little_loops.config import BRConfig
        from little_loops.logger import Logger

        # Load config for loops_dir
        config = BRConfig(Path.cwd())
        from little_loops.cli.output import configure_output

        configure_output(config.cli)
        loops_dir = Path(config.loops.loops_dir)

        # Check if first positional arg is a subcommand or a loop name
        # This enables "ll-loop fix-types" shorthand for "ll-loop run fix-types"
        known_subcommands = {
            "run",
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
            "fragments",
            "next-loop",
            "audit-meta",
            "calibrate-budget",
            "diagnose-evaluators",
            "promote-baseline",
            "edit-routes",
            "monitor",
            # aliases
            "r",
            "c",
            "val",
            "l",
            "st",
            "res",
            "h",
            "t",
            "sim",
            "s",
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
  %(prog)s run fix-types --worktree # Run in isolated git worktree
  %(prog)s run fix-types --dry-run  # Show execution plan
  %(prog)s validate fix-types     # Validate loop definition
  %(prog)s test fix-types         # Run single test iteration
  %(prog)s simulate fix-types     # Interactive simulation (dry-run with prompts)
  %(prog)s list                   # List available loops
  %(prog)s list --running         # List running loops
  %(prog)s status fix-types       # Show loop status
  %(prog)s stop fix-types         # Stop a running loop
  %(prog)s resume fix-types       # Resume interrupted loop
  %(prog)s history fix-types      # Show execution history
  %(prog)s next-loop              # Suggest next loop from history
  %(prog)s next-loop --count 3    # Top 3 suggestions
  %(prog)s audit-meta fix-types   # Summarize meta-eval agreement stats
  %(prog)s monitor fix-types      # Attach to a running loop and render FSM state
""",
        )

        subparsers = parser.add_subparsers(dest="command")

        # Run subcommand
        run_parser = subparsers.add_parser("run", aliases=["r"], help="Run a loop")
        run_parser.set_defaults(command="run")
        run_parser.add_argument("loop", help="Loop name or path")
        run_parser.add_argument(
            "input",
            nargs="?",
            default=None,
            help="If valid JSON object with keys matching defined context variables, unpacks into those keys; otherwise stored as a string in context[input_key]",
        )
        run_parser.add_argument(
            "--max-steps",
            "-n",
            type=int,
            help="Override step cap (max individual state transitions)",
        )
        run_parser.add_argument(
            "--max-iterations", type=int, help="Override full-pass cap (max complete loop cycles)"
        )
        run_parser.add_argument(
            "--delay",
            type=float,
            default=None,
            metavar="SECONDS",
            help="Sleep N seconds between iterations (useful for recording)",
        )
        run_parser.add_argument("--no-llm", action="store_true", help="Disable LLM evaluation")
        run_parser.add_argument(
            "--model",
            type=str,
            dest="run_model",
            metavar="MODEL_ID",
            help="Default model for host-CLI action states (prompt/slash-command). Per-state model: overrides this.",
        )
        run_parser.add_argument(
            "--llm-model",
            type=str,
            metavar="MODEL_ID",
            help="Override model for FSM evaluator/judge states (distinct from --model).",
        )
        run_parser.add_argument(
            "--dry-run", action="store_true", help="Show execution plan without running"
        )
        run_parser.add_argument(
            "--background", "-b", action="store_true", help="Run as background daemon"
        )
        run_parser.add_argument(
            "--foreground-internal",
            action="store_true",
            help=argparse.SUPPRESS,
        )
        run_parser.add_argument("--instance-id", type=str, default=None, help=argparse.SUPPRESS)
        run_parser.add_argument(
            "--quiet", "--qt", action="store_true", help="Suppress progress output"
        )
        run_parser.add_argument(
            "--follow",
            "-f",
            action="store_true",
            help="Stream FSM state transitions to stdout as they fire (mirrors 'll-loop history' format)",
        )
        run_parser.add_argument(
            "--verbose",
            "-v",
            action="store_true",
            help="Show full prompt at action start (default: single-line preview)",
        )
        run_parser.add_argument(
            "--show-diagrams",
            nargs="?",
            const=True,
            default=None,
            type=_parse_show_diagrams,
            metavar="MODE",
            help=(
                "Display the FSM diagram after each step. MODE is a topology "
                "(layered|neighborhood|inline) or a preset (detailed|summary|clean|local|slim|oneline). "
                "Bare --show-diagrams defaults to the 'summary' preset (layered, main-path scope). "
                "Use --diagram-edge-labels, --diagram-state-detail, --diagram-scope to override "
                "individual preset facets."
            ),
        )
        run_parser.add_argument(
            "--diagram-edge-labels",
            choices=["on", "off"],
            default=None,
            metavar="on|off",
            help="Show or hide edge labels in the FSM diagram (default: on). Overrides preset.",
        )
        run_parser.add_argument(
            "--diagram-state-detail",
            choices=["title", "full"],
            default=None,
            metavar="title|full",
            help="State box content: 'title' = name only, 'full' = include action body (default: full). Overrides preset.",
        )
        run_parser.add_argument(
            "--diagram-scope",
            choices=["main", "full"],
            default=None,
            metavar="main|full",
            help="Edge scope: 'main' hides off-happy-path edges, 'full' shows all (default: full). Overrides preset.",
        )
        run_parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear terminal before each iteration (useful with --show-diagrams); uses the alternate screen buffer when combined with --show-diagrams to avoid scrollback contamination",
        )
        run_parser.add_argument(
            "--queue", "-q", action="store_true", help="Wait for conflicting loops to finish"
        )
        run_parser.add_argument(
            "--no-lock", action="store_true", help="Skip scope lock (for demos/recordings)"
        )
        run_parser.add_argument(
            "--context",
            action="append",
            default=[],
            metavar="KEY=VALUE",
            help="Override a context variable (can be repeated)",
        )
        run_parser.add_argument(
            "--program-md",
            type=Path,
            default=None,
            metavar="PATH",
            help="Path to program.md steering file (default: .ll/program.md when present)",
        )
        run_parser.add_argument(
            "--builtin",
            action="store_true",
            help="Load loop from built-ins directory (bypasses project .loops/ lookup)",
        )
        run_parser.add_argument(
            "--worktree",
            action="store_true",
            help=(
                "Run loop in an isolated git worktree on a new branch named "
                "TIMESTAMP-LOOP-NAME; worktree and branch are removed on exit"
            ),
        )
        add_handoff_threshold_arg(run_parser)
        add_context_limit_arg(run_parser)
        run_parser.add_argument(
            "--baseline", action="store_true", help="Run with ungated baseline arm for comparison"
        )
        run_parser.add_argument(
            "--baseline-skill",
            type=str,
            default=None,
            metavar="SKILL",
            help="Override the auto-extracted baseline skill",
        )
        run_parser.add_argument(
            "--items",
            type=int,
            default=None,
            metavar="N",
            help="Limit sample size for baseline comparison",
        )
        run_parser.add_argument(
            "--cross-host",
            action="store_true",
            help="Re-run the loop on a second available host and append a cross-host comparison table",
        )

        # Validate subcommand
        validate_parser = subparsers.add_parser(
            "validate", aliases=["val"], help="Validate loop definition"
        )
        validate_parser.set_defaults(command="validate")
        validate_parser.add_argument("loop", help="Loop name or path")
        validate_parser.add_argument("-j", "--json", action="store_true", help="Output as JSON")

        # List subcommand
        list_parser = subparsers.add_parser("list", aliases=["l"], help="List loops")
        list_parser.set_defaults(command="list")
        list_parser.add_argument("--running", action="store_true", help="Only show running loops")
        list_parser.add_argument(
            "--status",
            help="Filter running loops by status (e.g., interrupted, awaiting_continuation)",
        )
        list_parser.add_argument("-j", "--json", action="store_true", help="Output as JSON array")
        list_parser.add_argument("--builtin", action="store_true", help="Show only built-in loops")
        list_parser.add_argument(
            "--category",
            "-c",
            type=str,
            default=None,
            help="Filter to loops in a specific category",
        )
        list_parser.add_argument(
            "--label",
            action="append",
            dest="label",
            metavar="LABEL",
            help="Filter by label tag (repeatable)",
        )
        list_parser.add_argument(
            "-a",
            "--all",
            action="store_true",
            help="Include internal sub-loops and examples (hidden by default)",
        )
        list_parser.add_argument(
            "--internal",
            action="store_true",
            help="Show only internal (delegated-only) sub-loops",
        )
        list_parser.add_argument(
            "--examples",
            action="store_true",
            help="Show only example/template loops",
        )
        list_parser.add_argument(
            "--visibility",
            choices=["public", "internal", "example", "all"],
            default=None,
            metavar="{public,internal,example,all}",
            help=(
                "Filter loops by visibility tier. "
                "'public' (default view) returns only routable loops; "
                "'internal'/'example' narrow to those tiers; "
                "'all' shows everything. Composes with --label and --json."
            ),
        )

        # Status subcommand
        status_parser = subparsers.add_parser("status", aliases=["st"], help="Show loop status")
        status_parser.set_defaults(command="status")
        status_parser.add_argument("loop", help="Loop name")
        status_parser.add_argument(
            "-j", "--json", action="store_true", help="Output loop state as JSON"
        )

        # Stop subcommand
        stop_parser = subparsers.add_parser("stop", help="Stop a running loop")
        stop_parser.add_argument("loop", help="Loop name")

        # Resume subcommand
        resume_parser = subparsers.add_parser(
            "resume", aliases=["res"], help="Resume an interrupted loop"
        )
        resume_parser.set_defaults(command="resume")
        resume_parser.add_argument("loop", help="Loop name or path")
        resume_parser.add_argument(
            "--background",
            "-b",
            action="store_true",
            help="Resume as a detached background process",
        )
        resume_parser.add_argument(
            "--foreground-internal",
            action="store_true",
            help=argparse.SUPPRESS,
        )
        resume_parser.add_argument(
            "--instance-id",
            type=str,
            default=None,
            help="Instance ID to resume (auto-detected if omitted)",
        )
        resume_parser.add_argument(
            "--context",
            action="append",
            default=[],
            metavar="KEY=VALUE",
            help="Override a context variable (can be repeated)",
        )
        resume_parser.add_argument(
            "--show-diagrams",
            nargs="?",
            const=True,
            default=None,
            type=_parse_show_diagrams,
            metavar="MODE",
            help=(
                "Display the FSM diagram after each step. MODE is a topology "
                "(layered|neighborhood|inline) or a preset (detailed|summary|clean|local|slim|oneline). "
                "Bare --show-diagrams defaults to the 'summary' preset (layered, main-path scope). "
                "Use --diagram-edge-labels, --diagram-state-detail, --diagram-scope to override "
                "individual preset facets."
            ),
        )
        resume_parser.add_argument(
            "--diagram-edge-labels",
            choices=["on", "off"],
            default=None,
            metavar="on|off",
            help="Show or hide edge labels in the FSM diagram (default: on). Overrides preset.",
        )
        resume_parser.add_argument(
            "--diagram-state-detail",
            choices=["title", "full"],
            default=None,
            metavar="title|full",
            help="State box content: 'title' = name only, 'full' = include action body (default: full). Overrides preset.",
        )
        resume_parser.add_argument(
            "--diagram-scope",
            choices=["main", "full"],
            default=None,
            metavar="main|full",
            help="Edge scope: 'main' hides off-happy-path edges, 'full' shows all (default: full). Overrides preset.",
        )
        resume_parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear terminal before each iteration (useful with --show-diagrams); uses the alternate screen buffer when combined with --show-diagrams to avoid scrollback contamination",
        )
        resume_parser.add_argument(
            "--delay",
            type=float,
            default=None,
            metavar="SECONDS",
            help="Sleep N seconds between iterations (useful for recording)",
        )
        add_handoff_threshold_arg(resume_parser)
        add_context_limit_arg(resume_parser)

        # History subcommand
        history_parser = subparsers.add_parser(
            "history",
            aliases=["h"],
            help="List archived loop runs or show events for a specific run",
        )
        history_parser.set_defaults(command="history")
        history_parser.add_argument("loop", help="Loop name")
        history_parser.add_argument(
            "run_id",
            nargs="?",
            default=None,
            help="Run ID (compact timestamp) to show events for; omit to list archived runs",
        )
        history_parser.add_argument(
            "--tail", "-n", type=int, default=50, help="Last N events (default: 50)"
        )
        history_parser.add_argument(
            "--verbose",
            "-v",
            action="store_true",
            help="Show action output lines and LLM call details",
        )
        history_parser.add_argument(
            "--full",
            action="store_true",
            help="Show untruncated prompts and output (implies --verbose)",
        )
        history_parser.add_argument(
            "-j", "--json", action="store_true", help="Output events as JSON array"
        )
        history_parser.add_argument(
            "--event",
            "-e",
            type=str,
            default=None,
            help="Filter by event type (e.g. evaluate, route)",
        )
        history_parser.add_argument(
            "--state",
            "-s",
            type=str,
            default=None,
            help="Filter by state name (matches state, from, or to fields)",
        )
        history_parser.add_argument(
            "--since",
            "-S",
            type=str,
            default=None,
            metavar="DURATION",
            help="Filter to events within time window (e.g. 1h, 30m, 2d)",
        )

        # Test subcommand
        test_parser = subparsers.add_parser(
            "test", aliases=["t"], help="Run a single test iteration to verify loop configuration"
        )
        test_parser.set_defaults(command="test")
        test_parser.add_argument("loop", help="Loop name")
        test_parser.add_argument(
            "--state", help="Test a specific state instead of the initial state"
        )
        test_parser.add_argument(
            "--exit-code",
            type=int,
            dest="exit_code",
            metavar="N",
            help="Simulated exit code for slash-command states (skips interactive prompt)",
        )

        # Simulate subcommand
        simulate_parser = subparsers.add_parser(
            "simulate",
            aliases=["sim"],
            help="Trace loop execution interactively without running commands",
        )
        simulate_parser.set_defaults(command="simulate")
        simulate_parser.add_argument("loop", help="Loop name or path")
        simulate_parser.add_argument(
            "--scenario",
            choices=["all-pass", "all-fail", "all-error", "first-fail", "alternating"],
            help="Auto-select results based on pattern instead of prompting (exit codes: 0=success, 1=failure, 2=error)",
        )
        simulate_parser.add_argument(
            "--max-steps",
            "-n",
            type=int,
            help="Override step cap for simulation (default: min of loop config or 20)",
        )
        simulate_parser.add_argument(
            "--max-iterations",
            type=int,
            help="Override full-pass cap for simulation",
        )

        # Install subcommand
        install_parser = subparsers.add_parser(
            "install",
            help="Copy a built-in loop to .loops/ for customization",
        )
        install_parser.add_argument("loop", help="Built-in loop name to install")

        # Show subcommand
        show_parser = subparsers.add_parser(
            "show", aliases=["s"], help="Show loop details and structure"
        )
        show_parser.set_defaults(command="show")
        show_parser.add_argument("loop", help="Loop name or path")
        show_parser.add_argument(
            "--verbose", "-v", action="store_true", help="Show full action text and evaluate prompt"
        )
        show_parser.add_argument(
            "-j", "--json", action="store_true", help="Output FSM config as JSON"
        )
        show_parser.add_argument(
            "--resolved",
            action="store_true",
            help="Expand sub-loop states inline under _subloop key",
        )
        show_parser.add_argument(
            "--show-diagrams",
            nargs="?",
            const=True,
            default=None,
            type=_parse_show_diagrams,
            metavar="MODE",
            help=(
                "Display the FSM diagram using a specific rendering mode. MODE is a topology "
                "(layered|neighborhood|inline) or a preset (detailed|summary|clean|local|slim|oneline). "
                "Bare --show-diagrams defaults to the 'summary' preset (layered, main-path scope). "
                "Use --diagram-edge-labels, --diagram-state-detail, --diagram-scope to override "
                "individual preset facets."
            ),
        )
        show_parser.add_argument(
            "--diagram-edge-labels",
            choices=["on", "off"],
            default=None,
            metavar="on|off",
            help="Show or hide edge labels in the FSM diagram (default: on). Overrides preset.",
        )
        show_parser.add_argument(
            "--diagram-state-detail",
            choices=["title", "full"],
            default=None,
            metavar="title|full",
            help="State box content: 'title' = name only, 'full' = include action body (default: full). Overrides preset.",
        )
        show_parser.add_argument(
            "--diagram-scope",
            choices=["main", "full"],
            default=None,
            metavar="main|full",
            help="Edge scope: 'main' hides off-happy-path edges, 'full' shows all (default: full). Overrides preset.",
        )

        # Fragments subcommand
        fragments_parser = subparsers.add_parser(
            "fragments",
            help="List fragments in a library file with descriptions",
        )
        fragments_parser.set_defaults(command="fragments")
        fragments_parser.add_argument(
            "lib",
            help="Fragment library file path (e.g. lib/common.yaml, lib/cli.yaml)",
        )

        # Next-loop subcommand
        next_loop_parser = subparsers.add_parser(
            "next-loop",
            help="Suggest next loop(s) to run based on execution history",
        )
        next_loop_parser.set_defaults(command="next-loop")
        next_loop_parser.add_argument(
            "--count",
            "-n",
            type=int,
            default=1,
            metavar="N",
            help="Number of suggestions to return (default: 1)",
        )
        next_loop_parser.add_argument(
            "-j",
            "--json",
            action="store_true",
            help="Output suggestions as JSON array",
        )
        next_loop_parser.add_argument(
            "--execute",
            action="store_true",
            help="Run the top suggestion immediately via the same path as ll-loop run",
        )
        next_loop_parser.add_argument(
            "--exclude",
            action="append",
            default=[],
            metavar="NAME",
            help="Exclude a loop name from suggestions (repeatable)",
        )

        # Audit-meta subcommand
        audit_meta_parser = subparsers.add_parser(
            "audit-meta",
            help="Summarize meta-eval.jsonl agreement stats from archived runs",
        )
        audit_meta_parser.set_defaults(command="audit-meta")
        audit_meta_parser.add_argument("loop", help="Loop name")
        audit_meta_parser.add_argument("-j", "--json", action="store_true", help="Output as JSON")

        # Monitor subcommand (FEAT-1764)
        monitor_parser = subparsers.add_parser(
            "monitor",
            help="Attach to a running loop and render its FSM state in realtime",
        )
        monitor_parser.set_defaults(command="monitor")
        monitor_parser.add_argument("loop", help="Loop name")
        monitor_parser.add_argument(
            "--show-diagrams",
            nargs="?",
            const=True,
            default=None,
            type=_parse_show_diagrams,
            metavar="MODE",
            help=(
                "Display the FSM diagram after each step. MODE is a topology "
                "(layered|neighborhood|inline) or a preset (detailed|summary|clean|local|slim|oneline). "
                "Bare --show-diagrams defaults to the 'summary' preset (layered, main-path scope). "
                "Use --diagram-edge-labels, --diagram-state-detail, --diagram-scope to override "
                "individual preset facets."
            ),
        )
        monitor_parser.add_argument(
            "--diagram-edge-labels",
            choices=["on", "off"],
            default=None,
            metavar="on|off",
            help="Show or hide edge labels in the FSM diagram (default: on). Overrides preset.",
        )
        monitor_parser.add_argument(
            "--diagram-state-detail",
            choices=["title", "full"],
            default=None,
            metavar="title|full",
            help="State box content: 'title' = name only, 'full' = include action body (default: full). Overrides preset.",
        )
        monitor_parser.add_argument(
            "--diagram-scope",
            choices=["main", "full"],
            default=None,
            metavar="main|full",
            help="Edge scope: 'main' hides off-happy-path edges, 'full' shows all (default: full). Overrides preset.",
        )
        monitor_parser.add_argument(
            "--clear",
            action="store_true",
            default=True,
            help="Clear terminal before each iteration (default: on). Uses the alternate screen buffer when combined with --show-diagrams to avoid scrollback contamination",
        )
        monitor_parser.add_argument(
            "--no-clear",
            action="store_false",
            dest="clear",
            help="Disable terminal clearing between iterations (scroll output instead)",
        )
        monitor_parser.add_argument(
            "--quiet", "--qt", action="store_true", help="Suppress progress output"
        )
        monitor_parser.add_argument(
            "--verbose", "-v", action="store_true", help="Show full prompt at action start"
        )

        # Diagnose-evaluators subcommand
        diagnose_eval_parser = subparsers.add_parser(
            "diagnose-evaluators",
            help="Detect non-discriminating evaluators from run history",
        )
        diagnose_eval_parser.set_defaults(command="diagnose-evaluators")
        diagnose_eval_parser.add_argument("loop", help="Loop name")
        diagnose_eval_parser.add_argument(
            "--threshold",
            type=float,
            default=0.05,
            help="Variance floor below which a state is flagged (default: 0.05)",
        )
        diagnose_eval_parser.add_argument(
            "--min-runs",
            type=int,
            default=10,
            help="Minimum runs required for meaningful variance (default: 10)",
        )
        diagnose_eval_parser.add_argument(
            "-j", "--json", action="store_true", help="Output as JSON"
        )

        # Calibrate-budget subcommand
        calibrate_budget_parser = subparsers.add_parser(
            "calibrate-budget",
            help="Report per-evaluator Bernoulli variance to guide max_iterations calibration",
        )
        calibrate_budget_parser.set_defaults(command="calibrate-budget")
        calibrate_budget_parser.add_argument("loop", help="Loop name")
        calibrate_budget_parser.add_argument(
            "--threshold",
            type=float,
            default=0.05,
            help="Variance floor below which a state is flagged (default: 0.05)",
        )
        calibrate_budget_parser.add_argument(
            "--min-runs",
            type=int,
            default=10,
            help="Minimum runs required for meaningful variance (default: 10)",
        )
        calibrate_budget_parser.add_argument(
            "-j", "--json", action="store_true", help="Output as JSON"
        )

        # Promote-baseline subcommand
        promote_bl_parser = subparsers.add_parser(
            "promote-baseline",
            help="Promote the latest run's output as the new comparator baseline",
        )
        promote_bl_parser.set_defaults(command="promote-baseline")
        promote_bl_parser.add_argument("loop", help="Loop name")

        # Edit-routes subcommand
        edit_routes_parser = subparsers.add_parser(
            "edit-routes",
            help="Render and edit a loop's routing logic as a decision table",
        )
        edit_routes_parser.set_defaults(command="edit-routes")
        edit_routes_parser.add_argument("loop", help="Loop name or path")
        edit_routes_parser.add_argument(
            "--format",
            choices=["markdown", "csv"],
            default="markdown",
            metavar="{markdown,csv}",
            help="Output format for the table (default: markdown)",
        )
        edit_routes_parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print table to stdout without opening editor",
        )
        edit_routes_parser.add_argument(
            "--no-warnings",
            action="store_true",
            help="Skip gap/conflict detection output",
        )

        args = parser.parse_args(argv)

        # Backfill run defaults from config when CLI flags are at their argparse defaults.
        if args.command == "run":
            rd = config.loops.run_defaults
            if not args.clear and rd.clear:
                args.clear = True
            if args.show_diagrams is None and rd.show_diagrams is not None:
                args.show_diagrams = True if rd.show_diagrams == "default" else rd.show_diagrams

        logger = Logger(verbose=not getattr(args, "quiet", False))

        # Dispatch commands
        if args.command == "run":
            return cmd_run(args.loop, args, loops_dir, logger)
        elif args.command == "validate":
            return cmd_validate(args.loop, args, loops_dir, logger)
        elif args.command == "list":
            return cmd_list(args, loops_dir)
        elif args.command == "status":
            return cmd_status(args.loop, loops_dir, logger, args)
        elif args.command == "stop":
            return cmd_stop(args.loop, loops_dir, logger)
        elif args.command == "resume":
            return cmd_resume(args.loop, args, loops_dir, logger)
        elif args.command == "history":
            return cmd_history(args.loop, getattr(args, "run_id", None), args, loops_dir)
        elif args.command == "test":
            return cmd_test(args.loop, args, loops_dir, logger)
        elif args.command == "simulate":
            return cmd_simulate(args.loop, args, loops_dir, logger)
        elif args.command == "install":
            return cmd_install(args.loop, loops_dir, logger)
        elif args.command == "show":
            return cmd_show(args.loop, args, loops_dir, logger)
        elif args.command == "fragments":
            return cmd_fragments(args.lib, args, loops_dir, logger)
        elif args.command == "next-loop":
            return cmd_next_loop(args, loops_dir, logger)
        elif args.command == "audit-meta":
            return cmd_audit_meta(args.loop, args, loops_dir)
        elif args.command == "calibrate-budget":
            return cmd_calibrate_budget(args.loop, args, loops_dir)
        elif args.command == "diagnose-evaluators":
            return cmd_diagnose_evaluators(args.loop, args, loops_dir)
        elif args.command == "promote-baseline":
            return cmd_promote_baseline(args.loop, args, loops_dir)
        elif args.command == "edit-routes":
            return cmd_edit_routes(args.loop, args, loops_dir, logger)
        elif args.command == "monitor":
            return cmd_monitor(args, loops_dir)
        else:
            parser.print_help()
            return 1
