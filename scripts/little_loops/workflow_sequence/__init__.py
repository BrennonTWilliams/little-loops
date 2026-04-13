"""ll-workflows: Identify multi-step workflow patterns from user message history.

Identifies multi-step workflows and cross-session patterns using:
- Entity-based clustering
- Time-gap weighted boundaries
- Semantic similarity scoring
- Workflow template matching

Usage as CLI:
    ll-workflows analyze --input messages.jsonl --patterns step1.yaml
    ll-workflows analyze -i messages.jsonl -p patterns.yaml -o output.yaml

Usage as library:
    from little_loops.workflow_sequence import analyze_workflows

    result = analyze_workflows(
        messages_file=Path("user-messages.jsonl"),
        patterns_file=Path("step1-patterns.yaml"),
        output_file=Path("step2-workflows.yaml"),
    )
"""

from __future__ import annotations

from pathlib import Path

from little_loops.cli.output import configure_output, use_color_enabled
from little_loops.logger import Logger
from little_loops.workflow_sequence.analysis import (
    analyze_workflows,
    calculate_boundary_weight,
    entity_overlap,
    extract_entities,
    get_verb_class,
    semantic_similarity,
)
from little_loops.workflow_sequence.models import (
    EntityCluster,
    SessionLink,
    Workflow,
    WorkflowAnalysis,
    WorkflowBoundary,
)

_DEFAULT_INPUT_PATH = Path(".ll/workflow-analysis/step1-patterns.jsonl")

__all__ = [
    "analyze_workflows",
    "SessionLink",
    "EntityCluster",
    "WorkflowBoundary",
    "Workflow",
    "WorkflowAnalysis",
    "extract_entities",
    "calculate_boundary_weight",
    "entity_overlap",
    "get_verb_class",
    "semantic_similarity",
]


def main() -> int:
    """Entry point for ll-workflows command.

    Analyze workflows from user messages and Step 1 patterns.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Identify multi-step workflow patterns from user message history",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s analyze --patterns .ll/workflow-analysis/step1-patterns.yaml
  %(prog)s analyze -i messages.jsonl -p patterns.yaml -o output.yaml
  %(prog)s analyze --input .ll/user-messages.jsonl \\
                   --patterns .ll/workflow-analysis/step1-patterns.yaml

Pipeline (--input defaults to .ll/workflow-analysis/step1-patterns.jsonl):
  ll-messages --output .ll/workflow-analysis/step1-patterns.jsonl
  %(prog)s analyze --patterns .ll/workflow-analysis/step1-patterns.yaml
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # analyze subcommand
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze workflows from messages and patterns",
    )
    analyze_parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=_DEFAULT_INPUT_PATH,
        help=(
            "Input JSONL file with user messages"
            " (default: .ll/workflow-analysis/step1-patterns.jsonl)"
        ),
    )
    analyze_parser.add_argument(
        "-p",
        "--patterns",
        type=Path,
        required=True,
        help="Input YAML file from Step 1 (workflow-pattern-analyzer)",
    )
    analyze_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output file (default: .ll/workflow-analysis/step2-workflows.yaml or .json)",
    )
    analyze_parser.add_argument(
        "-f",
        "--format",
        choices=["yaml", "json"],
        default="yaml",
        help="Output format (default: yaml)",
    )
    analyze_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose progress information",
    )
    analyze_parser.add_argument(
        "--overlap-threshold",
        type=float,
        default=0.3,
        metavar="FLOAT",
        help="Minimum entity overlap to cluster messages together (default: 0.3)",
    )
    analyze_parser.add_argument(
        "--boundary-threshold",
        type=float,
        default=0.6,
        metavar="FLOAT",
        help="Minimum boundary score to split workflow segments (default: 0.6)",
    )

    args = parser.parse_args()

    configure_output()
    logger = Logger(use_color=use_color_enabled())

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "analyze":
        # Validate input files
        if not args.input.exists():
            logger.error(f"Input file not found: {args.input}")
            if args.input == _DEFAULT_INPUT_PATH:
                logger.info("  Run 'll-messages' first to generate the input file.")
            return 1

        if not args.patterns.exists():
            logger.error(f"Patterns file not found: {args.patterns}")
            return 1

        # Validate threshold ranges
        if not (0.0 <= args.overlap_threshold <= 1.0):
            logger.error(
                f"--overlap-threshold must be in [0.0, 1.0], got {args.overlap_threshold}"
            )
            return 1

        if not (0.0 <= args.boundary_threshold <= 1.0):
            logger.error(
                f"--boundary-threshold must be in [0.0, 1.0], got {args.boundary_threshold}"
            )
            return 1

        # Set default output path
        output_path = args.output
        if output_path is None:
            if args.format == "json":
                output_path = Path(".ll/workflow-analysis/step2-workflows.json")
            else:
                output_path = Path(".ll/workflow-analysis/step2-workflows.yaml")

        if args.verbose:
            logger.info(f"Input: {args.input}")
            logger.info(f"Patterns: {args.patterns}")
            logger.info(f"Output: {output_path}")

        try:
            analysis = analyze_workflows(
                messages_file=args.input,
                patterns_file=args.patterns,
                output_file=output_path,
                overlap_threshold=args.overlap_threshold,
                boundary_threshold=args.boundary_threshold,
                verbose=args.verbose,
                output_format=args.format,
            )

            if args.verbose:
                logger.info(f"Analyzed {analysis.metadata['message_count']} messages")
                logger.info(f"Found {len(analysis.session_links)} session links")
                logger.info(f"Found {len(analysis.entity_clusters)} entity clusters")
                logger.info(f"Detected {len(analysis.workflows)} workflows")
            logger.success(f"Output written to: {output_path}")

            return 0

        except Exception as e:
            logger.error(str(e))
            return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
