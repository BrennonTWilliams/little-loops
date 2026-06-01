"""ll-verify-docs and ll-check-links: Documentation verification commands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from little_loops.cli.output import configure_output, print_json, use_color_enabled
from little_loops.cli_args import add_json_arg
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context


def main_verify_docs() -> int:
    """Entry point for ll-verify-docs command.

    Verify that documented counts (commands, agents, skills) match actual file counts.

    Returns:
        Exit code (0 = all match, 1 = mismatches found)
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-verify-docs", sys.argv[1:]):
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

        configure_output()
        logger = Logger(use_color=use_color_enabled())

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
            logger.success(
                f"Fixed {fix_result.fixed_count} count(s) in {len(fix_result.files_modified)} file(s)"
            )

        # Return exit code based on results
        return 0 if result.all_match else 1


def main_verify_skill_budget() -> int:
    """Entry point for ll-verify-skill-budget command.

    Scan skill description tokens and fail if total exceeds the configured budget.

    Returns:
        Exit code (0 = under budget, 1 = over budget)
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-verify-skill-budget", sys.argv[1:]):
        from little_loops.doc_counts import (
            _DEFAULT_BUDGET_TOKENS,
            check_skill_budget,
        )

        parser = argparse.ArgumentParser(
            prog="ll-verify-skill-budget",
            description="Verify skill description token footprint stays within listing budget",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s                    # Check against default 2000-token budget
  %(prog)s --threshold 1500   # Custom token threshold

Exit codes:
  0 - Under budget
  1 - Over budget
""",
        )

        parser.add_argument(
            "--threshold",
            type=int,
            default=None,
            metavar="N",
            help=f"Token budget threshold (default: {_DEFAULT_BUDGET_TOKENS}; overrides ll-config.json)",
        )

        parser.add_argument(
            "-C",
            "--directory",
            type=Path,
            default=None,
            help="Base directory (default: current directory)",
        )

        add_json_arg(parser)

        args = parser.parse_args()

        configure_output()
        logger = Logger(use_color=use_color_enabled())

        base_dir = args.directory or Path.cwd()

        # Resolve threshold: CLI arg > config file > default
        threshold = args.threshold
        if threshold is None:
            try:
                from little_loops.config import BRConfig

                threshold = (
                    BRConfig(base_dir)
                    ._raw_config.get("skill_budget", {})
                    .get("threshold_tokens", _DEFAULT_BUDGET_TOKENS)
                )
            except Exception:
                threshold = _DEFAULT_BUDGET_TOKENS

        result = check_skill_budget(base_dir=base_dir, threshold_tokens=threshold)

        if args.json:
            print_json(
                {
                    "under_budget": result.under_budget,
                    "total_tokens": result.total_tokens,
                    "threshold_tokens": result.threshold_tokens,
                    "skills": [
                        {
                            "name": path.parent.name,
                            "char_count": len(desc),
                            "token_estimate": tokens,
                        }
                        for path, desc, tokens in result.skill_breakdown
                    ],
                    "violations": [
                        {
                            "name": path.parent.name,
                            "char_count": len(desc),
                            "token_estimate": tokens,
                        }
                        for path, desc, tokens in result.violations
                    ],
                }
            )
            return 0 if result.under_budget else 1

        # Per-skill breakdown header
        print("Skill Description Token Budget Check")
        print("=" * 40)
        print(f"Threshold: {result.threshold_tokens} tokens")
        print()

        if result.skill_breakdown:
            print(f"{'Tokens':>6}  Skill")
            print(f"{'------':>6}  {'-----'}")
            for skill_md, _, tokens in result.skill_breakdown:
                marker = " !" if tokens >= 200 else "  "
                print(f"{tokens:>6}{marker} {skill_md.parent.name}")
            print()

        if result.under_budget:
            logger.success(
                f"Total: {result.total_tokens} / {result.threshold_tokens} tokens — under budget"
            )
            return 0
        else:
            logger.error(
                f"Total: {result.total_tokens} / {result.threshold_tokens} tokens — OVER BUDGET"
            )
            if result.violations:
                print("\nTop contributors (≥200 tokens each):")
                for skill_md, _, tokens in result.violations:
                    print(f"  {tokens:>6}  {skill_md.parent.name}")
            return 1


def main_check_links() -> int:
    """Entry point for ll-check-links command.

    Check markdown documentation for broken links.

    Returns:
        Exit code (0 = all links valid, 1 = broken links found, 2 = error)
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-check-links", sys.argv[1:]):
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
            "-t",
            type=int,
            default=10,
            help="Request timeout in seconds (default: 10)",
        )

        parser.add_argument(
            "-w",
            "--workers",
            type=int,
            default=10,
            help="Maximum concurrent HTTP requests (default: 10)",
        )

        parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="Show verbose output",
        )

        args = parser.parse_args()

        configure_output()

        # Determine base directory
        base_dir = args.directory or Path.cwd()

        # Load ignore patterns from config + CLI args
        ignore_patterns = load_ignore_patterns(base_dir)
        ignore_patterns.extend(args.ignore)

        # Run link check
        result = check_markdown_links(
            base_dir, ignore_patterns, args.timeout, args.verbose, args.workers
        )

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
