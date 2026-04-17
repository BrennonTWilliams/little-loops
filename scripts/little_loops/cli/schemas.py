"""ll-generate-schemas: Generate JSON Schema files for all LLEvent types."""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.cli.output import configure_output, use_color_enabled
from little_loops.logger import Logger


def main_generate_schemas() -> int:
    """Entry point for ll-generate-schemas command.

    Generate JSON Schema (draft-07) files for all 22 LLEvent types and write them
    to docs/reference/schemas/ (or a custom output directory).

    Returns:
        Exit code (0 = success, 1 = error)
    """
    from little_loops.generate_schemas import generate_schemas

    parser = argparse.ArgumentParser(
        prog="ll-generate-schemas",
        description="Generate JSON Schema files for all LLEvent types",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                             # Write to docs/reference/schemas/
  %(prog)s --output path/to/schemas/   # Custom output directory

Exit codes:
  0 - Schemas generated successfully
  1 - Error occurred
""",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: docs/reference/schemas/ relative to cwd)",
    )

    args = parser.parse_args()

    configure_output()
    logger = Logger(use_color=use_color_enabled())

    output_dir = args.output or Path.cwd() / "docs" / "reference" / "schemas"

    try:
        paths = generate_schemas(output_dir)
        logger.success(f"Generated {len(paths)} schema(s) in {output_dir}/")
        return 0
    except Exception as exc:
        logger.error(str(exc))
        return 1
