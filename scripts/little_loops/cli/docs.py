"""ll-verify-docs and ll-check-links: Documentation verification commands."""

from __future__ import annotations

import argparse
from pathlib import Path


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
