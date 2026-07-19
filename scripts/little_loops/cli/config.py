"""ll-config: resolve and print a single configuration value.

Wraps ``BRConfig.resolve_variable()`` as a standalone CLI so shell-driven
skills (interactive/slash-command runs, not just ``ll-auto``'s
``skill_expander`` pre-expansion pass) can resolve a dot-path config value
on demand — e.g. ``ll-config get history.go_no_go.correction_penalty``.

Usage:
    ll-config get <key>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from little_loops.cli.output import configure_output
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ll-config",
        description="Resolve and print a single configuration value",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s get history.go_no_go.correction_penalty
  %(prog)s get project.src_dir

Exit codes:
  0 - always (never-raise, config-or-default contract; unknown keys print nothing)
""",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    get_parser = subparsers.add_parser(
        "get", help="Resolve a dot-path config key and print its value"
    )
    get_parser.add_argument(
        "key",
        metavar="KEY",
        help="Dot-separated config path (e.g. history.go_no_go.correction_penalty)",
    )
    return parser


def main_config() -> int:
    """Entry point for ll-config command.

    Returns:
        0 always — mirrors BRConfig.resolve_variable()'s never-raise, config-or-default contract.
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-config", sys.argv[1:]):
        configure_output()

        parser = _build_parser()
        args = parser.parse_args()

        from little_loops.config import BRConfig

        try:
            value = BRConfig(Path.cwd()).resolve_variable(args.key)
        except Exception:
            value = None

        if value is not None:
            print(value)

        return 0
