"""ll-issues locate-options: expose enumerable option spans for an issue (ENH-2950).

Widens `ll-issues check-decidable`'s boolean gate into a full data frontend so
decide-issue Phase 3/3b can read spans instead of re-implementing the same
precedence chain (`issue_parser.locate_enumerable_options`) in prose.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

    from little_loops.config import BRConfig


def cmd_locate_options(config: BRConfig, args: argparse.Namespace) -> int:
    """Print the located enumerable options for an issue.

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id (str) and optional .json (bool)

    Returns:
        0 if the issue is found (regardless of option count), 1 if not found.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.cli.output import print_json
    from little_loops.issue_parser import locate_enumerable_options

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    located = locate_enumerable_options(path.read_text())

    if getattr(args, "json", False):
        print_json({"id": args.issue_id, **located.to_dict()})
        return 0

    print(f"{args.issue_id}: {located.count} enumerable option(s)")
    if located.pattern is not None:
        print(f"  pattern: {located.pattern}")
    if located.heading is not None:
        print(f"  heading: {located.heading}")
    for option in located.options:
        print(f"  - {option.label} (lines {option.start_line}-{option.end_line})")
    if located.residual_directive is not None:
        rd = located.residual_directive
        line = rd.options[0].start_line if rd.options else "?"
        print(f"  + residual decision directive in '{rd.heading}' (line {line}) — not counted")
    return 0
