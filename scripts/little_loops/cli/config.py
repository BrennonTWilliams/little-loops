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
from typing import TYPE_CHECKING

from little_loops.cli.output import configure_output
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

if TYPE_CHECKING:
    from little_loops.config import BRConfig


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
  0 - always (never-raise, config-or-default contract; a valid-but-unset key
      prints nothing on either stream, an unknown config *section* additionally
      warns on stderr)
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
            cfg = BRConfig(Path.cwd())
        except Exception as exc:
            print(f"Warning: could not load project config ({exc})", file=sys.stderr)
            return 0

        try:
            value = cfg.resolve_variable(args.key)
        except Exception:
            # resolve_variable() is a pure dict walk today (config/core.py) and
            # cannot raise, but the shape is kept so a future change there
            # degrades the same way construction failures do.
            value = None

        if value is not None:
            print(value)
        else:
            _warn_if_unknown_section(cfg, args.key)

        return 0


def _warn_if_unknown_section(cfg: BRConfig, key: str) -> None:
    """Warn on stderr if *key*'s root segment is not a known config section.

    Known roots are the union of ``cfg.to_dict()``'s top-level keys and
    ``config-schema.json``'s top-level ``properties`` keys — ``to_dict()``
    deliberately omits provenance-only keys like ``install_source``/``$schema``
    (see ENH-3021), so the schema is needed to avoid false-warning on those.
    """
    from little_loops.init.core import _load_schema

    root = key.split(".", 1)[0]
    known_roots = set(cfg.to_dict().keys())
    known_roots.update(_load_schema().get("properties", {}).keys())

    if root not in known_roots:
        print(
            f"Warning: {root!r} is not a known config section (ll-config get {key})",
            file=sys.stderr,
        )
