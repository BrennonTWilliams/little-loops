"""ll-artifact: Generate self-contained human-facing artifacts.

Provides:
- ``policy-builder`` (FEAT-2301): a single self-contained HTML page for
  visually authoring policy-router / rubric FSM loop YAML.
- ``design-md export`` (ENH-3268): a lossy export of a design-token profile
  to a valid DESIGN.md, for handoff to Cursor / Copilot / another
  little-loops project.
- ``render`` (FEAT-3036 Phase 1): deterministic ``template + data.json ->
  artifact`` rendering for user-authored ``.llat/`` artifact templates.

One module per subcommand (``policy_builder.py``, ``design_md.py``,
``render.py``), following the ``cli/issues/`` / ``cli/loop/`` convention
(decided 2026-08-23, FEAT-3036 § Second-pass decisions).
"""

from __future__ import annotations

import argparse
import sys

from little_loops.cli.artifact.design_md import cmd_design_md_export
from little_loops.cli.artifact.policy_builder import _themed_css_vars, cmd_policy_builder
from little_loops.cli.artifact.render import add_render_parser, cmd_render
from little_loops.cli.artifact.templatize import add_templatize_parser, cmd_templatize
from little_loops.cli.output import configure_output, use_color_enabled
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

__all__ = [
    "main_artifact",
    "cmd_policy_builder",
    "cmd_design_md_export",
    "cmd_render",
    "cmd_templatize",
    "_themed_css_vars",
]


def main_artifact() -> int:
    """Entry point for the ``ll-artifact`` command.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-artifact", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-artifact",
            description="Generate self-contained human-facing artifacts",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s policy-builder                  # Write policy-router-builder.html to the default output dir
  %(prog)s policy-builder -o build/        # Write to a custom directory
  %(prog)s design-md export                # Print the project's active profile as DESIGN.md to stdout
  %(prog)s design-md export -o DESIGN.md   # Write to a file
  %(prog)s design-md export --profile warm-paper --theme dark -o DESIGN.md
  %(prog)s render my-report --data data.json    # Deterministic render, no LLM call
  %(prog)s render my-report.llat -o build/      # Render a template given as a path
  %(prog)s templatize out/index.html docs/ARCHITECTURE.md \\
      -o arch-review.llat --regions map.json    # Splice a hand-written region map into a template

Exit codes:
  0 - Artifact generated successfully
  1 - Error occurred
  2 - templatize: round-trip verification rejected the extraction (see <out>.rejected/)
""",
        )
        subparsers = parser.add_subparsers(dest="command", required=True)

        pb = subparsers.add_parser(
            "policy-builder",
            help="Emit the self-contained policy-router / rubric loop builder HTML",
        )
        pb.add_argument(
            "-o",
            "--output",
            type=str,
            default=None,
            help="Output directory (default: config.artifacts.default_output_dir)",
        )

        design_md = subparsers.add_parser(
            "design-md",
            help="DESIGN.md interop for the project's design-token profiles",
        )
        design_md_subparsers = design_md.add_subparsers(dest="subcommand", required=True)

        dme = design_md_subparsers.add_parser(
            "export",
            help="Export a design-token profile as a single-theme DESIGN.md document",
        )
        dme.add_argument(
            "--profile",
            type=str,
            default=None,
            help=(
                "Named profile to export (project profiles dir first, then the "
                "packaged built-ins). Default: the project's active/configured source."
            ),
        )
        dme.add_argument(
            "--theme",
            type=str,
            default=None,
            help="Theme to flatten into the single-theme output (default: active_theme)",
        )
        dme.add_argument(
            "-o",
            "--output",
            type=str,
            default=None,
            help="Output file (default: stdout). The dropped-groups note always goes to stderr.",
        )

        add_render_parser(subparsers)
        add_templatize_parser(subparsers)

        args = parser.parse_args()

        configure_output()
        logger = Logger(use_color=use_color_enabled())

        if args.command == "policy-builder":
            return cmd_policy_builder(args, logger)
        if args.command == "design-md" and args.subcommand == "export":
            return cmd_design_md_export(args, logger)
        if args.command == "render":
            return cmd_render(args, logger)
        if args.command == "templatize":
            return cmd_templatize(args, logger)
        parser.error(f"unknown command: {args.command}")
        return 1
