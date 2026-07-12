"""ll-code: Structural code-query CLI over the CodeQueryProvider protocol (FEAT-2576)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

from little_loops.cli.output import configure_output, print_json, use_color_enabled
from little_loops.cli_args import add_json_arg
from little_loops.codequery.core import CodeQueryError, CodeRef, Unsupported, resolve_provider
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context


def _default_provider() -> str:
    """Resolve the default provider name from ``BRConfig.code_query.provider``."""
    from little_loops.config import BRConfig

    return BRConfig(Path.cwd()).code_query.provider


def _print_refs(refs: list[CodeRef], logger: Logger) -> None:
    if not refs:
        logger.info("No results.")
        return
    for ref in refs:
        logger.info(f"  {ref.path}:{ref.line}  {ref.symbol}  ({ref.confidence}, {ref.kind})")


def main_code() -> int:
    """Entry point for ll-code command.

    Returns:
        Exit code: 0 = hits, 1 = no hits, 2 = provider error.
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-code", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-code",
            description="Structural code queries (callers, callees, imports, impact) via a "
            "pluggable provider protocol",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s status
  %(prog)s callers-of little_loops.issue_manager.IssueManager.load
  %(prog)s callees-of <symbol>
  %(prog)s importers-of little_loops/frontmatter.py
  %(prog)s defines little_loops/sync.py
  %(prog)s references <symbol>
  %(prog)s impact-of little_loops/state.py little_loops/events.py
  %(prog)s --provider fallback callers-of <symbol>
  %(prog)s --json callers-of <symbol>
""",
        )
        parser.add_argument(
            "--provider",
            default=None,
            help="Provider name to use, or 'auto' (default, from config) to pick the first "
            "available",
        )
        add_json_arg(parser)

        subparsers = parser.add_subparsers(dest="command", help="Available commands")

        subparsers.add_parser("status", help="Provider name, availability, freshness")

        callers_parser = subparsers.add_parser("callers-of", help="Who calls this symbol")
        callers_parser.add_argument("symbol")

        callees_parser = subparsers.add_parser("callees-of", help="What this symbol calls")
        callees_parser.add_argument("symbol")

        importers_parser = subparsers.add_parser(
            "importers-of", help="Who imports this module/file"
        )
        importers_parser.add_argument("module")

        defines_parser = subparsers.add_parser("defines", help="Symbols defined in a file")
        defines_parser.add_argument("path")

        references_parser = subparsers.add_parser(
            "references", help="All reference sites (defs + uses)"
        )
        references_parser.add_argument("symbol")

        impact_parser = subparsers.add_parser(
            "impact-of", help="Reverse transitive closure of files impacted by changes"
        )
        impact_parser.add_argument("paths", nargs="+")
        impact_parser.add_argument("--depth", type=int, default=2)

        args = parser.parse_args()

        configure_output()
        logger = Logger(use_color=use_color_enabled())

        if not args.command:
            parser.print_help()
            return 1

        try:
            provider = resolve_provider(args.provider or _default_provider())
        except CodeQueryError as exc:
            logger.error(str(exc))
            return 2

        status = provider.status()

        if args.command == "status":
            if args.json:
                print_json(
                    {
                        "provider": provider.name,
                        "available": status.available,
                        "freshness": status.freshness,
                        "indexed_at": status.indexed_at,
                        "detail": status.detail,
                        "capabilities": sorted(provider.capabilities()),
                    }
                )
            else:
                logger.info(f"provider: {provider.name}")
                logger.info(f"available: {status.available}")
                logger.info(f"freshness: {status.freshness}")
                logger.info(f"detail: {status.detail}")
            return 0

        try:
            if args.command == "callers-of":
                results = provider.callers_of(args.symbol)
            elif args.command == "callees-of":
                results = provider.callees_of(args.symbol)
            elif args.command == "importers-of":
                results = provider.importers_of(args.module)
            elif args.command == "defines":
                results = provider.defines(args.path)
            elif args.command == "references":
                results = provider.references(args.symbol)
            elif args.command == "impact-of":
                results = provider.impact_of(args.paths, depth=args.depth)
            else:
                parser.print_help()
                return 1
        except Unsupported as exc:
            logger.error(f"Provider {provider.name!r} does not support this query: {exc}")
            return 2
        except CodeQueryError as exc:
            logger.error(str(exc))
            return 2

        query_label = args.command.replace("-", "_")
        if args.json:
            print_json(
                {
                    "provider": provider.name,
                    "freshness": status.freshness,
                    "query": query_label,
                    "results": [asdict(ref) for ref in results],
                }
            )
        else:
            _print_refs(results, logger)

        return 0 if results else 1
